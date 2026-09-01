"""mcp 命令组 — `zenskill mcp serve` 启动 stdio MCP server

供 Craft Agents 等 MCP 客户端作为 source 接入：
    {"type": "mcp", "mcp": {"transport": "stdio",
     "command": "zenskill", "args": ["mcp", "serve"]}}
"""

from __future__ import annotations

import argparse
from typing import Any

from ..runtime.mcp.registry import ServerToolRegistry, build_default_registry
from ..runtime.mcp.server import MCPServer


def cmd_mcp_serve(args: argparse.Namespace) -> int:
    registry = build_default_registry()

    prefixes = [p.strip() for p in (getattr(args, "tools_filter", "") or "").split(",") if p.strip()]
    if prefixes:
        registry = registry.filter_by_prefixes(prefixes)
        if registry.tool_count == 0:
            print(f"no tools match prefixes: {prefixes}", flush=True)
            return 1

    name = getattr(args, "name", "zenskill") or "zenskill"
    server = MCPServer(registry, name=name)
    server.serve()
    return 0


def register_mcp_parser(subparsers: Any) -> None:
    """注册 mcp 命令组（由 __main__.main 调用）"""
    mcp_parser = subparsers.add_parser("mcp", help="MCP (Model Context Protocol) 服务")
    mcp_sub = mcp_parser.add_subparsers(dest="subcommand", help="MCP 操作")
    serve_p = mcp_sub.add_parser(
        "serve",
        help="启动 stdio MCP server（供 Craft Agents 等 GUI 作为 source 接入）",
    )
    serve_p.add_argument(
        "--tools", default="", dest="tools_filter",
        help="工具名前缀过滤，逗号分隔（默认全部）",
    )
    serve_p.add_argument(
        "--name", default="zenskill",
        help="serverInfo 报告的服务名（默认 zenskill）",
    )
    serve_p.set_defaults(func=cmd_mcp_serve)
