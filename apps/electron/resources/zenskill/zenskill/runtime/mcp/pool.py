"""MCPClientPool：多 MCP 服务器统一管理，server__tool 前缀路由。

用法：
    pool = MCPClientPool()
    await pool.add_server("fs", ["python", "fs_server.py"])
    await pool.add_server("git", ["python", "git_server.py"])
    tools = await pool.list_all_tools()      # [(server, MCPTool), ...]
    result = await pool.call_tool("fs", "read_file", {"path": "..."})
    await pool.disconnect_all()
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from .client import MCPClient
from .protocol import MCPTool, ToolResult

logger = logging.getLogger(__name__)


class MCPClientPool:
    """命名服务器池；call_tool 按 (server_name, tool_name) 路由。"""

    def __init__(self) -> None:
        self._clients: Dict[str, MCPClient] = {}

    @property
    def server_names(self) -> List[str]:
        return list(self._clients.keys())

    def get_client(self, server_name: str) -> MCPClient:
        client = self._clients.get(server_name)
        if client is None:
            raise KeyError(f"unknown mcp server: {server_name} (have: {self.server_names})")
        return client

    async def add_server(self, name: str, command: "list[str] | str") -> None:
        """连接一个 MCP 服务器（命令数组或 http(s):// URL）；同名覆盖前先断开旧连接。"""
        if name in self._clients:
            try:
                await self._clients[name].disconnect()
            except Exception:
                pass
        client = MCPClient()
        await client.connect(command)
        self._clients[name] = client
        target = command if isinstance(command, str) else " ".join(command)
        logger.info("mcp pool: server '%s' connected (%s)", name, target)

    def remove_server(self, name: str) -> None:
        client = self._clients.pop(name, None)
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                pass

    async def list_all_tools(self) -> List[Tuple[str, MCPTool]]:
        """聚合所有服务器的工具列表；单服务器失败不影响其余。"""
        pairs: List[Tuple[str, MCPTool]] = []
        for name, client in self._clients.items():
            try:
                for tool in await client.list_tools():
                    pairs.append((name, tool))
            except Exception as e:
                logger.warning("mcp pool: list_tools failed for '%s': %s", name, e)
        return pairs

    async def call_tool(self, server_name: str, tool_name: str,
                        arguments: Dict[str, Any]) -> ToolResult:
        return await self.get_client(server_name).call_tool(tool_name, arguments)

    async def disconnect_all(self) -> None:
        for name, client in list(self._clients.items()):
            try:
                await client.disconnect()
            except Exception:
                pass
            self._clients.pop(name, None)
