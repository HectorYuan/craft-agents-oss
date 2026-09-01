"""权限模式定义"""

from __future__ import annotations

from enum import Enum


class PermissionMode(Enum):
    """四档权限模式

    FULL: 完全访问 — 所有操作自动执行
    RESTRICTED: 受限模式 — 写操作需确认
    PLAN: 只读规划 — 禁止修改操作
    SANDBOX: 沙箱隔离 — 白名单控制
    """

    FULL = "full"
    RESTRICTED = "restricted"
    PLAN = "plan"
    SANDBOX = "sandbox"


class ToolCategory(Enum):
    """工具操作分类

    READ: 读操作（文件读取、搜索、查询）
    WRITE: 写操作（文件写入、创建、删除）
    EXECUTE: 执行操作（shell 命令、脚本）
    NETWORK: 网络操作（HTTP 请求、下载）
    SYSTEM: 系统操作（进程管理、环境变量）
    """

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"
    SYSTEM = "system"


# 工具分类映射：工具名 → 操作分类
TOOL_CATEGORIES: dict[str, ToolCategory] = {
    # 内置工具
    "read_file": ToolCategory.READ,
    "write_file": ToolCategory.WRITE,
    "list_directory": ToolCategory.READ,
    "search_files": ToolCategory.READ,
    "run_command": ToolCategory.EXECUTE,
    "python_execute": ToolCategory.EXECUTE,
    "http_request": ToolCategory.NETWORK,
    "memory_recall": ToolCategory.READ,
    "memory_remember": ToolCategory.WRITE,
    "skill_chain_run": ToolCategory.EXECUTE,
    # agent 引擎工具（runtime/agent/tools.py）
    "read": ToolCategory.READ,
    "grep": ToolCategory.READ,
    "find": ToolCategory.READ,
    "ls": ToolCategory.READ,
    "write": ToolCategory.WRITE,
    "edit": ToolCategory.WRITE,
    "bash": ToolCategory.EXECUTE,
    # MCP 工具（默认归类为 EXECUTE）
    "default": ToolCategory.EXECUTE,
}


def classify_tool(tool_name: str) -> ToolCategory:
    """分类工具操作类型

    Args:
        tool_name: 工具名称

    Returns:
        工具操作分类
    """
    return TOOL_CATEGORIES.get(tool_name, TOOL_CATEGORIES["default"])


# 模式-分类权限矩阵：(mode, category) → requires_confirm
PERMISSION_MATRIX: dict[tuple[PermissionMode, ToolCategory], bool] = {
    # FULL 模式：所有操作自动执行
    (PermissionMode.FULL, ToolCategory.READ): False,
    (PermissionMode.FULL, ToolCategory.WRITE): False,
    (PermissionMode.FULL, ToolCategory.EXECUTE): False,
    (PermissionMode.FULL, ToolCategory.NETWORK): False,
    (PermissionMode.FULL, ToolCategory.SYSTEM): False,
    # RESTRICTED 模式：写操作需确认
    (PermissionMode.RESTRICTED, ToolCategory.READ): False,
    (PermissionMode.RESTRICTED, ToolCategory.WRITE): True,
    (PermissionMode.RESTRICTED, ToolCategory.EXECUTE): True,
    (PermissionMode.RESTRICTED, ToolCategory.NETWORK): True,
    (PermissionMode.RESTRICTED, ToolCategory.SYSTEM): True,
    # PLAN 模式：只允许读操作
    (PermissionMode.PLAN, ToolCategory.READ): False,
    (PermissionMode.PLAN, ToolCategory.WRITE): True,  # 拒绝
    (PermissionMode.PLAN, ToolCategory.EXECUTE): True,  # 拒绝
    (PermissionMode.PLAN, ToolCategory.NETWORK): True,  # 拒绝
    (PermissionMode.PLAN, ToolCategory.SYSTEM): True,  # 拒绝
    # SANDBOX 模式：由 Sandbox 检查白名单
    (PermissionMode.SANDBOX, ToolCategory.READ): False,
    (PermissionMode.SANDBOX, ToolCategory.WRITE): True,
    (PermissionMode.SANDBOX, ToolCategory.EXECUTE): True,
    (PermissionMode.SANDBOX, ToolCategory.NETWORK): True,
    (PermissionMode.SANDBOX, ToolCategory.SYSTEM): True,
}
