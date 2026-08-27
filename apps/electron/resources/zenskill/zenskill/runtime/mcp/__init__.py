"""
MCP 共享协议层 — client/server 双向复用

- protocol:  数据类、消息构造/解析、版本协商（无 IO）
- transport: stdio JSON-RPC 传输（reader 协程 + id 路由 + stderr 消费）
- client:    MCPClient（API 兼容旧 runtime/mcp_client.py）
"""

from .protocol import (
    CLIENT_INFO,
    LATEST_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    MCPErrorCode,
    MCPMessageType,
    MCPRequest,
    MCPResponse,
    MCPTool,
    ToolResult,
    classify_message,
    make_notification_line,
    make_request_line,
    negotiate_version,
    parse_message_line,
)
from .transport import StdioTransport, TransportError
from .client import MCPClient

__all__ = [
    "CLIENT_INFO",
    "LATEST_PROTOCOL_VERSION",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "MCPErrorCode",
    "MCPMessageType",
    "MCPRequest",
    "MCPResponse",
    "MCPTool",
    "ToolResult",
    "MCPClient",
    "StdioTransport",
    "TransportError",
    "classify_message",
    "make_notification_line",
    "make_request_line",
    "negotiate_version",
    "parse_message_line",
]
