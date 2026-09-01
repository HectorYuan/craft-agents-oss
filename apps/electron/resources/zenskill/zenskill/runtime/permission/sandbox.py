"""安全沙箱"""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .permission_mode import ToolCategory


@dataclass
class SandboxConfig:
    """沙箱配置"""

    allowed_paths: list[str] = field(default_factory=lambda: ["${WORKSPACE}/**", "/tmp/zenskill/**"])
    denied_paths: list[str] = field(default_factory=lambda: ["~/.ssh/**", "~/.gnupg/**", "/etc/passwd"])
    allowed_commands: list[str] = field(default_factory=lambda: ["python3", "pip", "git", "ls", "cat", "grep", "find"])
    denied_commands: list[str] = field(default_factory=lambda: ["rm -rf /", "sudo", "chmod 777"])
    timeout_seconds: int = 30
    max_output_bytes: int = 1048576  # 1MB

    @classmethod
    def from_yaml(cls, path: str) -> SandboxConfig:
        """从 YAML 文件加载配置"""
        try:
            import yaml
            with open(path) as f:
                data = yaml.safe_load(f)
            sandbox_data = data.get("sandbox", {})
            return cls(
                allowed_paths=sandbox_data.get("allowed_paths", cls.allowed_paths),
                denied_paths=sandbox_data.get("denied_paths", cls.denied_paths),
                allowed_commands=sandbox_data.get("allowed_commands", cls.allowed_commands),
                denied_commands=sandbox_data.get("denied_commands", cls.denied_commands),
                timeout_seconds=sandbox_data.get("timeout_seconds", cls.timeout_seconds),
                max_output_bytes=sandbox_data.get("max_output_bytes", cls.max_output_bytes),
            )
        except Exception:
            return cls()


class Sandbox:
    """安全沙箱

    提供路径白名单、命令白名单、超时控制等安全机制。

    使用方式：
        sandbox = Sandbox(SandboxConfig())
        allowed, reason = await sandbox.check("read_file", {"path": "/tmp/test.txt"})
        if not allowed:
            print(f"Permission denied: {reason}")
    """

    def __init__(self, config: SandboxConfig | None = None, workspace: str | None = None):
        """初始化沙箱

        Args:
            config: 沙箱配置
            workspace: 工作空间路径（用于 ${WORKSPACE} 变量替换）
        """
        self._config = config or SandboxConfig()
        self._workspace = workspace or os.getcwd()
        self._expanded_allowed_paths = self._expand_paths(self._config.allowed_paths)
        self._expanded_denied_paths = self._expand_paths(self._config.denied_paths)

    def _expand_paths(self, paths: list[str]) -> list[str]:
        """展开路径变量"""
        expanded = []
        for p in paths:
            p = p.replace("${WORKSPACE}", self._workspace)
            p = os.path.expanduser(p)
            expanded.append(p)
        return expanded

    def _match_path(self, path: str, patterns: list[str]) -> bool:
        """检查路径是否匹配模式列表"""
        path = os.path.abspath(path)
        for pattern in patterns:
            pattern = os.path.abspath(pattern)
            # 处理 ** 通配符：dir/** 匹配 dir 自身与 dir 下任意路径
            if "**" in pattern:
                prefix = pattern.split("**")[0].rstrip("/")
                if prefix and (path == prefix or path.startswith(prefix + "/")):
                    return True
            # 处理普通通配符
            if fnmatch.fnmatch(path, pattern):
                return True
            # 处理目录边界匹配（"/data" 只匹配自身与 "/data/..."，不匹配 "/database"）
            stripped = pattern.rstrip("/")
            if path == stripped or path.startswith(stripped + "/"):
                return True
        return False

    def check_path(self, path: str) -> tuple[bool, str]:
        """检查单个路径（agent 引擎 PermissionGate 使用）"""
        return self._check_path(path)

    def check_command(self, command: str) -> tuple[bool, str]:
        """检查单条命令（agent 引擎 PermissionGate 使用）"""
        return self._check_command(command)

    def _check_path(self, path: str) -> tuple[bool, str]:
        """检查路径权限

        Returns:
            (allowed, reason)
        """
        # 先检查拒绝列表
        if self._match_path(path, self._expanded_denied_paths):
            return False, f"Path denied by sandbox: {path}"

        # 再检查允许列表
        if self._match_path(path, self._expanded_allowed_paths):
            return True, ""

        return False, f"Path not in sandbox whitelist: {path}"

    def _check_command(self, command: str) -> tuple[bool, str]:
        """检查命令权限

        Returns:
            (allowed, reason)
        """
        # 提取命令主程序
        cmd_parts = command.strip().split()
        if not cmd_parts:
            return False, "Empty command"

        cmd_name = cmd_parts[0]

        # 检查拒绝列表
        for denied in self._config.denied_commands:
            if command.startswith(denied) or cmd_name == denied:
                return False, f"Command denied by sandbox: {command}"

        # 检查允许列表
        if cmd_name in self._config.allowed_commands:
            return True, ""

        return False, f"Command not in sandbox whitelist: {cmd_name}"

    async def check(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> tuple[bool, str]:
        """检查工具调用权限

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            (allowed, reason)
        """
        return self._check_tool_sync(tool_name, args)

    def check_sync(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> tuple[bool, str]:
        """同步版本的权限检查（用于测试）"""
        return self._check_tool_sync(tool_name, args)

    def _check_tool_sync(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> tuple[bool, str]:
        # 文件操作工具
        if tool_name in ("read_file", "write_file", "list_directory"):
            path = args.get("path", args.get("directory", ""))
            if path:
                return self._check_path(path)
            return True, ""

        # 搜索工具
        if tool_name == "search_files":
            directory = args.get("directory", "")
            if directory:
                return self._check_path(directory)
            return True, ""

        # 命令执行工具
        if tool_name == "run_command":
            command = args.get("command", "")
            if command:
                return self._check_command(command)
            return False, "No command specified"

        # Python 执行工具
        if tool_name == "python_execute":
            # Python 执行受超时限制，路径由具体实现控制
            return True, ""

        # HTTP 请求工具
        if tool_name == "http_request":
            # HTTP 请求默认允许，可扩展 URL 黑名单
            return True, ""

        # 记忆工具
        if tool_name in ("memory_recall", "memory_remember"):
            return True, ""

        # 技能链工具
        if tool_name == "skill_chain_run":
            return True, ""

        # agent 引擎工具（runtime/agent/tools.py）
        if tool_name in ("read", "edit", "grep", "find", "ls"):
            path = args.get("path", args.get("directory", ""))
            if path:
                return self._check_path(path)
            return True, ""

        if tool_name == "write":
            path = args.get("path", "")
            if path:
                return self._check_path(path)
            return False, "No path specified"

        if tool_name == "bash":
            command = args.get("command", "")
            if command:
                return self._check_command(command)
            return False, "No command specified"

        # 未知工具默认拒绝
        return False, f"Unknown tool in sandbox: {tool_name}"
