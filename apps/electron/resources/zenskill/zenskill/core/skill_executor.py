"""Deprecated: 已更名 skill_deployer.py (P1-1)

SkillExecutor 名不副实（仅部署复制，不执行），真实执行在
zenskill/runtime/。本 shim 保留一版 re-export，外部导入路径不变。
"""

from .skill_deployer import (
    SkillDeployer,
    SkillExecutionResult,
    discover_skill,
    get_skills_dir,
    load_skill_manifest,
)

SkillExecutor = SkillDeployer

__all__ = [
    "SkillExecutor",
    "SkillDeployer",
    "SkillExecutionResult",
    "discover_skill",
    "get_skills_dir",
    "load_skill_manifest",
]
