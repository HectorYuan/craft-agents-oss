"""
MCP Client — 兼容 façade

实现已迁移至 zenskill/runtime/mcp/（protocol/transport/client），本文件仅保留
`from .mcp_client import ...` 的历史导入路径（10+ 模块依赖）。新代码请直接
导入 zenskill.runtime.mcp。
"""

from .mcp.protocol import (
    MCPErrorCode,
    MCPMessageType,
    MCPRequest,
    MCPResponse,
    MCPTool,
    ToolResult,
)
from .mcp.client import MCPClient

__all__ = [
    "MCPClient",
    "MCPTool",
    "ToolResult",
    "MCPRequest",
    "MCPResponse",
    "MCPMessageType",
    "MCPErrorCode",
]
