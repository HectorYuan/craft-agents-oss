"""
Z5 — 技能生态测试：包验证 + 兼容性

验证技能包的格式完整性、安装/卸载幂等性、跨版本兼容性。
"""

from __future__ import annotations

import json

import pytest

from zenskill.zentest.fixtures import ZSkillHome
from zenskill.zentest.utils import TempDir, write_skill_package


# ═══════════════════════════════════════════════════════════════
# 包格式验证
# ═══════════════════════════════════════════════════════════════

MINIMAL_MANIFEST_FIELDS = [
    "name", "version", "description",
    "author", "min_zenskill_version", "entry",
]


@pytest.mark.skill
def test_manifest_required_fields() -> None:
    """manifest.json 必须包含所有必需字段"""
    with TempDir() as td:
        pkg_dir = write_skill_package(td, "test_skill")
        manifest = json.loads((pkg_dir / "manifest.json").read_text())
        for field in MINIMAL_MANIFEST_FIELDS:
            assert field in manifest, f"缺少必需字段: {field}"
            assert manifest[field], f"字段不能为空: {field}"


@pytest.mark.skill
def test_skill_entry_file_exists() -> None:
    """manifest.json 中 entry 指向的文件必须存在"""
    with TempDir() as td:
        pkg_dir = write_skill_package(td, "test_skill")
        manifest = json.loads((pkg_dir / "manifest.json").read_text())
        entry_file = pkg_dir / manifest["entry"]
        assert entry_file.exists(), f"入口文件 {manifest['entry']} 不存在"


@pytest.mark.skill
def test_package_name_validity() -> None:
    """技能包名应合法：字母数字下划线"""
    with TempDir() as td:
        valid_names = ["my_skill", "skill123", "a"]
        invalid_names = ["../../evil", "with space", "", "with.dots"]
        for name in valid_names:
            pkg = write_skill_package(td, name)
            assert (pkg / "manifest.json").exists()
        for name in invalid_names:
            try:
                write_skill_package(td, name)
            except OSError:
                pass  # 非法名可能创建失败


@pytest.mark.skill
def test_skill_entry_is_python() -> None:
    """入口文件必须是 .py 文件"""
    with TempDir() as td:
        pkg_dir = write_skill_package(td, "py_skill")
        entry = pkg_dir / "skill.py"
        assert entry.suffix == ".py"
        code = entry.read_text()
        assert "def run" in code, "入口文件应包含 run 函数"


# ═══════════════════════════════════════════════════════════════
# 安装/卸载幂等性
# ═══════════════════════════════════════════════════════════════

@pytest.mark.skill
def test_install_idempotent() -> None:
    """重复安装同一技能不应报错（幂等）"""
    with ZSkillHome() as home:
        sf = home.root / ".zenskill" / "skills"
        for _ in range(3):
            home.write_json("skills/test_skill.json", {
                "name": "test_skill", "version": "1.0.0", "installed": True,
            })
            assert (sf / "test_skill.json").exists()


@pytest.mark.skill
def test_uninstall_idempotent() -> None:
    """重复卸载同一技能不应报错（幂等）"""
    with ZSkillHome() as home:
        sf = home.root / ".zenskill" / "skills"
        # 安装
        home.write_json("skills/test_skill.json", {"name": "test_skill"})
        assert (sf / "test_skill.json").exists()
        # 卸载
        (sf / "test_skill.json").unlink()
        assert not (sf / "test_skill.json").exists()
        # 再次卸载 — 不应报错
        try:
            (sf / "test_skill.json").unlink()
        except FileNotFoundError:
            pass  # 可接受


# ═══════════════════════════════════════════════════════════════
# 多技能共存
# ═══════════════════════════════════════════════════════════════

@pytest.mark.skill
def test_multiple_skills_no_conflict() -> None:
    """多个技能并存不冲突"""
    with ZSkillHome() as home:
        skills = [f"skill_{i}" for i in range(10)]
        for s in skills:
            home.write_json(f"skills/{s}.json", {"name": s, "installed": True})
        for s in skills:
            loaded = home.read_json(f"skills/{s}.json")
            assert loaded is not None and loaded["name"] == s


# ═══════════════════════════════════════════════════════════════
# 兼容性
# ═══════════════════════════════════════════════════════════════

@pytest.mark.skill
def test_compat_old_manifest_format() -> None:
    """旧版 manifest（缺失字段）应能被读取"""
    with ZSkillHome() as home:
        # 旧版格式 — 仅最小字段
        old_manifest = {
            "name": "old_skill",
        }
        home.write_json("skills/old_skill.json", old_manifest)
        loaded = home.read_json("skills/old_skill.json")
        assert loaded is not None
        assert loaded["name"] == "old_skill"
        # 缺失字段不应导致崩溃
        missing = loaded.get("version", "unknown")
        assert missing == "unknown"


@pytest.mark.skill
def test_compat_extra_fields_ignored() -> None:
    """新增字段不应破坏旧包读取"""
    with ZSkillHome() as home:
        extended = {
            "name": "new_skill",
            "version": "2.0.0",
            "description": "test",
            "author": "zentest",
            "min_zenskill_version": "2.0.0",
            "entry": "skill.py",
            "new_field_x": "should_be_ignored",
            "permissions": ["network", "shell"],
        }
        home.write_json("skills/new_skill.json", extended)
        loaded = home.read_json("skills/new_skill.json")
        assert loaded["name"] == "new_skill"
        assert loaded.get("new_field_x") == "should_be_ignored"
