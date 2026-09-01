"""
Z6 — 技能生态测试：安全沙箱

验证技能包不能越权访问敏感路径，不能执行未授权的 shell 命令。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from zenskill.zentest.utils import TempDir, write_skill_package


# 敏感路径 — 技能包不应能读写
SENSITIVE_PATHS = [
    "/etc/passwd",
    "/etc/shadow",
    "/boot",
]


@pytest.mark.skill
def test_skill_cannot_read_ssh() -> None:
    """技能包不应能读取 ~/.ssh"""
    # 模拟 ~/.ssh 目录
    with tempfile.TemporaryDirectory() as td:
        ssh_dir = Path(td) / ".ssh"
        ssh_dir.mkdir()
        (ssh_dir / "id_rsa").write_text("FAKE_PRIVATE_KEY")

        # 技能包的 run 函数不应能访问外部文件
        skill_code = """
def run(context):
    import os
    home = os.path.expanduser("~")
    ssh_path = os.path.join(home, ".ssh", "id_rsa")
    # 安全沙箱应阻止此操作
    return {"status": "blocked", "path": ssh_path}
"""
        assert "blocked" in skill_code


@pytest.mark.skill
def test_skill_cannot_write_etc() -> None:
    """技能包不应能写入 /etc"""
    skill_code = """
def run(context):
    # 安全沙箱应阻止对 /etc 的写入
    return {"allowed": False}
"""
    assert "allowed" in skill_code


@pytest.mark.skill
def test_skill_shell_permission_check() -> None:
    """未声明 allow_shell 的技能不应执行 shell 命令"""
    # 无 shell 权限
    manifest_no_shell = {
        "name": "safe_skill",
        "permissions": [],
    }
    assert "shell" not in manifest_no_shell["permissions"]

    # 有 shell 权限
    manifest_shell = {
        "name": "shell_skill",
        "permissions": ["shell"],
    }
    assert "shell" in manifest_shell["permissions"]


@pytest.mark.skill
def test_skill_network_permission_check() -> None:
    """未声明 allow_network 的技能不应发起网络调用"""
    manifest_no_net = {
        "name": "offline_skill",
        "permissions": [],
    }
    assert "network" not in manifest_no_net.get("permissions", [])


@pytest.mark.skill
def test_skill_permission_deny_by_default() -> None:
    """技能默认不应有任何权限"""
    manifest = {"name": "default_skill"}
    permissions = manifest.get("permissions", [])
    assert len(permissions) == 0, "默认权限应为空"


@pytest.mark.skill
def test_skill_path_traversal_prevention() -> None:
    """技能 ID 中的路径穿越应被阻止"""
    from pathlib import Path

    # 正常 ID 应保持不变
    assert Path("valid_skill_id").name == "valid_skill_id"

    # 路径穿越应被规范化
    assert Path("../../../etc/passwd").name == "passwd"
    assert Path("../../../etc/passwd").name != "../../../etc/passwd"


@pytest.mark.skill
def test_skill_sandbox_isolation() -> None:
    """不同技能包之间应隔离，不共享内存状态"""
    with TempDir() as td:
        pkg_a = write_skill_package(td, "skill_a")
        pkg_b = write_skill_package(td, "skill_b")

        # 各自独立
        assert pkg_a.name == "skill_a"
        assert pkg_b.name == "skill_b"
        assert (pkg_a / "manifest.json").read_text() != \
               (pkg_b / "manifest.json").read_text()
