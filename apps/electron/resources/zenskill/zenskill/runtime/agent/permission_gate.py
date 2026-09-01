"""PermissionGate：把 runtime/permission 的模式与沙箱包成 agent 引擎的 before_tool_call 钩子。

模式语义（复用 PermissionMode）：
- full：放行一切
- plan：只读规划，write/edit/bash 全部拒绝
- restricted / sandbox：Sandbox 白名单（路径 + 命令），未知工具拒绝
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from ..permission.permission_mode import PermissionMode
from ..permission.sandbox import Sandbox, SandboxConfig

AGENT_ALLOWED_COMMANDS = [
    "python3", "pip", "git", "ls", "cat", "grep", "find", "rg",
    "echo", "pwd", "mkdir", "cp", "mv", "touch", "head", "tail", "wc",
    "sort", "uniq", "diff", "date", "which", "seq", "test", "true", "false",
    "sed", "awk",
]

_READ_ONLY_TOOLS = {"read", "grep", "find", "ls"}
_PATH_TOOLS = {"read", "write", "edit", "grep", "find", "ls"}


class PermissionGate:
    def __init__(
        self,
        mode: str = "full",
        cwd: Optional[str] = None,
        sandbox_config: Optional[SandboxConfig] = None,
        confirm: Optional[Any] = None,
    ) -> None:
        """confirm(tool_call, params) -> bool：restricted 模式下写/执行类工具的
        行内确认回调（CLI input / RPC 交互事件的落点，M4-6）。"""
        self.mode = PermissionMode(mode)
        self.cwd = cwd or os.getcwd()
        self.confirm = confirm
        if self.mode in (PermissionMode.RESTRICTED, PermissionMode.SANDBOX):
            config = sandbox_config or SandboxConfig(allowed_commands=AGENT_ALLOWED_COMMANDS)
            self.sandbox = Sandbox(config, workspace=self.cwd)
        else:
            self.sandbox = None

    def __call__(self, tool_call, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        name = tool_call.name

        if self.mode == PermissionMode.FULL:
            return None

        if self.mode == PermissionMode.PLAN:
            if name not in _READ_ONLY_TOOLS:
                return {
                    "block": True,
                    "reason": f"tool '{name}' is not allowed in plan mode (read-only)",
                }
            return None

        # restricted / sandbox
        if name == "bash":
            ok, reason = self.sandbox.check_command(params.get("command", ""))
            if not ok:
                return {"block": True, "reason": reason}
        elif name in _PATH_TOOLS:
            raw = params.get("path") or params.get("directory") or "."
            target = raw if os.path.isabs(raw) else os.path.join(self.cwd, raw)
            ok, reason = self.sandbox.check_path(target)
            if not ok:
                return {"block": True, "reason": reason}
        elif name not in _READ_ONLY_TOOLS:
            return {
                "block": True,
                "reason": f"tool '{name}' is not in the sandbox tool whitelist",
            }

        if (
            self.mode == PermissionMode.RESTRICTED
            and self.confirm is not None
            and name not in _READ_ONLY_TOOLS
        ):
            try:
                approved = self.confirm(tool_call, params)
            except Exception:
                approved = False
            if not approved:
                return {"block": True, "reason": "user declined the action"}
        return None
