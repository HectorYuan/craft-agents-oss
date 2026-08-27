"""
MCP 协议层 — 数据类、消息构造/解析、版本协商（纯逻辑，无 IO）

数据类从 runtime/mcp_client.py 迁移而来，字段与语义保持不变；
mcp_client.py 保留为兼容 façade（10+ 模块从该路径导入）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


LATEST_PROTOCOL_VERSION = "2025-06-18"

SUPPORTED_PROTOCOL_VERSIONS = [
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
]

CLIENT_INFO = {"name": "zenskill-runtime", "version": "1.0.0"}


class MCPMessageType(str, Enum):
    """MCP 消息类型"""
    REQUEST = "request"
    RESPONSE = "response"
    ERROR = "error"
    NOTIFICATION = "notification"


class MCPErrorCode(int, Enum):
    """MCP 错误码（JSON-RPC 2.0 保留区间）"""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


@dataclass
class MCPTool:
    """MCP 工具定义"""
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPTool:
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            input_schema=data.get("inputSchema", {}),
        )


@dataclass
class ToolResult:
    """工具调用结果"""
    success: bool
    content: Any = None
    error: Optional[str] = None
    is_error: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "content": self.content,
            "error": self.error,
            "isError": self.is_error,
        }


@dataclass
class MCPRequest:
    """MCP 请求消息"""
    id: int
    method: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "jsonrpc": "2.0",
            "id": self.id,
            "method": self.method,
            "params": self.params,
        })


@dataclass
class MCPResponse:
    """MCP 响应消息"""
    id: int
    result: Any = None
    error: Optional[dict[str, Any]] = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> MCPResponse:
        return cls(
            id=data.get("id", 0),
            result=data.get("result"),
            error=data.get("error"),
        )

    @property
    def success(self) -> bool:
        return self.error is None


def negotiate_version(peer_version: str | None) -> str:
    """版本协商：取双方共同支持的最新版，无法协商时宽松回退旧版"""
    if peer_version in SUPPORTED_PROTOCOL_VERSIONS:
        return peer_version
    return "2024-11-05"


def make_request_line(request_id: int, method: str, params: dict[str, Any]) -> str:
    """构造一行 JSON-RPC 请求（带 id）"""
    return MCPRequest(id=request_id, method=method, params=params).to_json()


def make_notification_line(method: str, params: dict[str, Any] | None = None) -> str:
    """构造一行 JSON-RPC notification（无 id）"""
    return json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
    })


def parse_message_line(line: str) -> dict[str, Any] | None:
    """解析一行 JSON；非法/空行返回 None"""
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def classify_message(obj: dict[str, Any]) -> str:
    """
    分类一条已解析的 JSON-RPC 消息：
    - "response":      有 id 无 method（对端对本地请求的应答）
    - "request":       有 id 有 method（对端发来的请求）
    - "notification":  无 id（单向通知）
    - "invalid":       结构不合法
    """
    has_id = "id" in obj and obj["id"] is not None
    has_method = isinstance(obj.get("method"), str) and bool(obj.get("method"))
    if has_id and has_method:
        return "request"
    if has_id:
        return "response"
    if has_method:
        return "notification"
    return "invalid"
