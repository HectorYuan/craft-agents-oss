"""
MCPServer — stdio JSON-RPC MCP 服务端

最小合规闭环：initialize / notifications/initialized / ping / tools/list /
tools/call / prompts/list / resources/list（后两者返回空列表，部分 client
会探测）。工具执行异常按 MCP 规范返回 isError 的 tool result（而非
JSON-RPC error），让 agent 能读到错误原因。

入口：`zenskill mcp serve` 或 `python -m zenskill.runtime.mcp.server`
"""

from __future__ import annotations

import json
import sys
from typing import Any, BinaryIO, Optional

from .protocol import (
    LATEST_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    classify_message,
    parse_message_line,
)
from .registry import ServerToolRegistry, build_default_registry


class MethodNotFound(Exception):
    """JSON-RPC 层：未知 method（-32601）"""


class InvalidToolParams(Exception):
    """tools/call 层：未知工具名（-32602）"""


class MCPServer:
    """同步 stdio MCP server（请求串行处理）"""

    def __init__(self, registry: ServerToolRegistry, *, name: str = "zenskill"):
        self._registry = registry
        self._name = name
        self._initialized = False

    def handle_message(self, obj: dict[str, Any]) -> Optional[dict[str, Any]]:
        """处理一条已解析的消息；notification 返回 None"""
        kind = classify_message(obj)

        if kind != "request":
            # notification（含 notifications/initialized）与非法消息：不回应
            if kind == "notification" and obj.get("method") == "notifications/initialized":
                self._initialized = True
            return None

        request_id = obj.get("id")
        method = obj.get("method", "")
        params = obj.get("params") or {}

        try:
            result = self._dispatch(method, params)
        except MethodNotFound:
            return self._error_response(request_id, -32601, f"Method not found: {method}")
        except InvalidToolParams as e:
            return self._error_response(request_id, -32602, str(e))
        except Exception as e:
            return self._error_response(request_id, -32603, f"Internal error: {e}")

        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "initialize":
            return self._initialize(params)
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self._registry.list_specs()}
        if method == "tools/call":
            return self._call_tool(params)
        if method == "prompts/list":
            return {"prompts": []}
        if method == "resources/list":
            return {"resources": []}

        raise MethodNotFound(method)

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        peer_version = params.get("protocolVersion")
        version = (
            peer_version
            if peer_version in SUPPORTED_PROTOCOL_VERSIONS
            else LATEST_PROTOCOL_VERSION
        )
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": self._name, "version": "2.6.0"},
        }

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        try:
            text = self._registry.call(name, arguments)
        except KeyError:
            raise InvalidToolParams(f"Unknown tool: {name}")
        except Exception as e:
            return {
                "content": [{"type": "text", "text": f"tool error: {e}"}],
                "isError": True,
            }
        return {
            "content": [{"type": "text", "text": text}],
            "isError": False,
        }

    @staticmethod
    def _error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    def serve(self, stdin: Optional[BinaryIO] = None, stdout: Optional[BinaryIO] = None) -> None:
        """主循环：逐行读 stdin，响应写 stdout（UTF-8）"""
        stdin = stdin or sys.stdin.buffer
        stdout = stdout or sys.stdout.buffer
        for raw_line in stdin:
            obj = parse_message_line(raw_line.decode("utf-8", errors="replace"))
            if obj is None:
                continue
            response = self.handle_message(obj)
            if response is not None:
                stdout.write((json.dumps(response, ensure_ascii=False) + "\n").encode())
                stdout.flush()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    registry = build_default_registry()
    server = MCPServer(registry)
    server.serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
