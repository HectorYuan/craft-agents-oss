# ZenSkill - 平台适配层

from .base import PlatformAdapter, PlatformType, InstallResult, ExecutionResult
from .coze import CozeAdapter
from .pip import PipAdapter
from .claude import ClaudeAdapter
from .openclaw import OpenClawAdapter
from .hermes import HermesAdapter
from .codex import CodexAdapter
from .deploy import (
    DeployAdapter,
    LocalDeployAdapter,
    CursorDeployAdapter,
    OpencodeDeployAdapter,
    get_deploy_adapter,
    load_deploy_config,
)
from .installer import SkillInstaller, install_skill, check_skill_status

__all__ = [
    # 基类
    "PlatformAdapter",
    "PlatformType",
    "InstallResult",
    "ExecutionResult",
    # 平台适配器
    "CozeAdapter",
    "PipAdapter",
    "ClaudeAdapter",
    "OpenClawAdapter",
    "HermesAdapter",
    "CodexAdapter",
    # 部署型适配器 (P1-1)
    "DeployAdapter",
    "LocalDeployAdapter",
    "CursorDeployAdapter",
    "OpencodeDeployAdapter",
    "get_deploy_adapter",
    "load_deploy_config",
    # 安装器
    "SkillInstaller",
    "install_skill",
    "check_skill_status",
]
