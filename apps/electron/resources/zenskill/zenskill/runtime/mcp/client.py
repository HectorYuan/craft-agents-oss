"""
MCPClient — MCP 客户端（stdio）

公共 API 与旧 runtime/mcp_client.py 完全兼容（connect/list_tools/call_tool/
disconnect/health_check/connected），内部重写为 StdioTransport：

- 响应按 id 路由，对端乱序推送 notification 不影响请求结果
- initialize 成功后发送 notifications/initialized（补齐握手第二步）
- stderr 由传输层持续消费
- 协议版本协商（发送最新版，按对端响应协商回退）
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from .protocol import (
    CLIENT_INFO,
    LATEST_PROTOCOL_VERSION,
    MCPTool,
    ToolResult,
    negotiate_version,
)
from .transport import HttpStreamTransport, StdioTransport, TransportError


class MCPClient:
    """轻量级 MCP 客户端（stdio 传输）"""

    def __init__(
        self,
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
        max_reconnects: int = 2,
    ):
        self._transport: Optional[StdioTransport | HttpStreamTransport] = None
        self._connected: bool = False
        self._connect_timeout: float = connect_timeout
        self._read_timeout: float = read_timeout
        self._max_reconnects: int = max_reconnects
        self._reconnect_count: int = 0
        self._server_path: Optional[str] = None
        self._server_command: Optional[list[str]] = None
        self.negotiated_version: Optional[str] = None

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self, server_path: str | list[str]) -> None:
        """
        连接 MCP Server

        Args:
            server_path: MCP Server 可执行文件路径/命令数组，或 http(s):// URL
                         （Streamable HTTP 传输）
                         例如: "mcp-server"、"http://localhost:8080/mcp"

        Raises:
            ConnectionError: 连接失败
        """
        if self._connected:
            await self.disconnect()

        if isinstance(server_path, list):
            self._server_command = list(server_path)
            self._server_path = " ".join(server_path)
        else:
            self._server_command = None if server_path.startswith(("http://", "https://")) else [server_path]
            self._server_path = server_path

        try:
            await self._do_connect()
        except Exception as e:
            self._connected = False
            raise ConnectionError(f"Failed to connect to MCP server: {e}")

    async def _do_connect(self) -> None:
        if self._server_path is None:
            raise ConnectionError("No server path configured")

        if self._server_command is None:
            # Streamable HTTP：URL 直连（无子进程，重连 = 重建 transport）
            from .transport import HttpStreamTransport
            self._transport = HttpStreamTransport(
                self._server_path, timeout=self._read_timeout,
            )
        else:
            self._transport = StdioTransport(self._server_command)
        await self._transport.start()
        self._connected = True
        self._reconnect_count = 0

        await asyncio.wait_for(self._initialize(), timeout=self._connect_timeout)

    async def _reconnect(self) -> bool:
        """尝试重连"""
        if self._reconnect_count >= self._max_reconnects:
            return False
        self._reconnect_count += 1
        try:
            await self.disconnect()
            await self._do_connect()
            return True
        except Exception:
            return False

    async def _initialize(self) -> None:
        """initialize 握手 + 版本协商 + notifications/initialized"""
        result = await self._request("initialize", {
            "protocolVersion": LATEST_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        })
        self.negotiated_version = negotiate_version(
            result.get("protocolVersion") if isinstance(result, dict) else None
        )
        await self._transport.send_notification("notifications/initialized")

    async def _request(self, method: str, params: dict[str, Any]) -> Any:
        """带一次重连重试的请求"""
        for attempt in range(2):
            if self._transport is None:
                raise ConnectionError("Not connected to MCP server")
            try:
                return await self._transport.request(
                    method, params, timeout=self._read_timeout
                )
            except (TransportError, BrokenPipeError) as e:
                if attempt == 0 and await self._reconnect():
                    continue
                self._connected = False
                raise ConnectionError(f"MCP request failed: {e}")
        raise ConnectionError("MCP request failed after retry")

    async def disconnect(self) -> None:
        """断开连接"""
        if self._transport is not None:
            await self._transport.stop()
            self._transport = None
        self._connected = False

    async def list_tools(self) -> list[MCPTool]:
        """列出可用工具"""
        result = await self._request("tools/list", {})
        if not isinstance(result, dict):
            return []
        return [MCPTool.from_dict(t) for t in result.get("tools", [])]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """调用工具"""
        try:
            result = await self._request("tools/call", {
                "name": name,
                "arguments": arguments,
            })
        except ConnectionError as e:
            return ToolResult(success=False, error=str(e), is_error=True)

        if not isinstance(result, dict):
            return ToolResult(success=False, error="Malformed tool result", is_error=True)

        return ToolResult(
            success=not result.get("isError", False),
            content=result.get("content", []),
            is_error=result.get("isError", False),
        )

    async def health_check(self) -> bool:
        """健康检查"""
        if not self._connected or self._transport is None:
            return False
        try:
            await self._transport.request("ping", {}, timeout=self._read_timeout)
            return True
        except Exception:
            return False
