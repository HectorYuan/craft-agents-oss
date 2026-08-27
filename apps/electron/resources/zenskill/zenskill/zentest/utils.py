"""
ZenTest 测试工具函数

提供路径隔离、CLI 子进程执行、临时环境等通用测试工具。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════
# 路径与环境隔离
# ═══════════════════════════════════════════════════════════════

def isolated_env(extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """创建一个隔离的测试环境变量字典"""
    env = os.environ.copy()
    # 屏蔽可能影响测试的环境变量
    for key in list(env.keys()):
        if key.startswith("ZENSKILL_"):
            del env[key]
    if extra_env:
        env.update(extra_env)
    return env


def with_temp_home(fn):
    """装饰器：将 HOME 临时指向临时目录后执行"""
    import functools
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                return fn(*args, **kwargs)
            finally:
                if old_home is not None:
                    os.environ["HOME"] = old_home
                else:
                    del os.environ["HOME"]
    return wrapper


# ═══════════════════════════════════════════════════════════════
# CLI 子进程执行
# ═══════════════════════════════════════════════════════════════

CommandResult = Tuple[int, str, str]


def run_zenskill(args: List[str], **kwargs: Any) -> CommandResult:
    """运行 zenskill CLI 命令并返回 (exit_code, stdout, stderr)"""
    cmd = [sys.executable, "-m", "zenskill", *args]
    env = isolated_env(kwargs.pop("env", None))
    result = subprocess.run(
        cmd, capture_output=True, text=True, env=env, timeout=60, **kwargs
    )
    return (result.returncode, result.stdout, result.stderr)


def run_zenskill_with_input(
    args: List[str], input_text: str, **kwargs: Any
) -> CommandResult:
    """运行 zenskill CLI 命令并传递 stdin 输入"""
    cmd = [sys.executable, "-m", "zenskill", *args]
    env = isolated_env(kwargs.pop("env", None))
    result = subprocess.run(
        cmd, capture_output=True, text=True, env=env,
        input=input_text, timeout=60, **kwargs
    )
    return (result.returncode, result.stdout, result.stderr)


# ═══════════════════════════════════════════════════════════════
# 临时目录上下文管理器
# ═══════════════════════════════════════════════════════════════

class TempDir:
    """临时目录上下文管理器"""

    def __init__(self, prefix: str = "zentest_"):
        self._tmp = tempfile.TemporaryDirectory(prefix=prefix)
        self.path = Path(self._tmp.name)

    def __enter__(self) -> Path:
        return self.path

    def __exit__(self, *args: Any) -> None:
        self._tmp.cleanup()


# ═══════════════════════════════════════════════════════════════
# 文件操作辅助
# ═══════════════════════════════════════════════════════════════

def touch(path: Path) -> Path:
    """创建空文件并返回路径"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def write_skill_package(base: Path, name: str,
                         version: str = "1.0.0") -> Path:
    """创建一个最小可用的技能包目录结构"""
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": name,
        "version": version,
        "description": f"Test skill {name}",
        "author": "zentest",
        "min_zenskill_version": "1.0.0",
        "entry": "skill.py",
        "permissions": [],
    }
    (skill_dir / "manifest.json").write_text(
        __import__("json").dumps(manifest, indent=2)
    )

    skill_code = f"""
def run(context):
    return {{"skill": "{name}", "status": "ok"}}
"""
    (skill_dir / "skill.py").write_text(skill_code.strip())

    return skill_dir
