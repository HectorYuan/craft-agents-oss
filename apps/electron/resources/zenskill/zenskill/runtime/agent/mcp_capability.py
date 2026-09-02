"""McpCapability（M4-4）：MCP 工具接入 agent 引擎 + skills 渐进披露。

- MCP 服务器工具转 AgentTool，名称加 mcp__<server>__<tool> 前缀防冲突
- 工具数超过阈值时折叠为 mcp_list_tools / mcp_call_tool 两个元工具
  （渐进披露：先给目录，模型按需调用，避免 pi 批评的 MCP 上下文膨胀）
- format_skills_prompt：~/.agents/skills 下 SKILL.md 元数据格式化为
  系统提示词 XML 块（name+description，正文按需 read）
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .capability import AgentCapability
from .types import AgentTool, AgentToolResult, FunctionTool, TextContent

DEFAULT_TOOL_THRESHOLD = 30


def _mcp_tool_wrapper(client, server_name: str, mcp_tool, is_pool: bool = False) -> AgentTool:
    prefixed = f"mcp__{server_name}__{mcp_tool.name}"

    async def run(tool_call_id: str, params: Dict[str, Any], on_update=None) -> AgentToolResult:
        if is_pool:
            result = await client.call_tool(server_name, mcp_tool.name, params)
        else:
            result = await client.call_tool(mcp_tool.name, params)
        text = str(result.content if result.content is not None else "")
        if result.is_error or not result.success:
            text = text or (result.error or "mcp tool failed")
            return AgentToolResult(content=[TextContent(text)], is_error=True)
        return AgentToolResult(content=[TextContent(text)])

    class _Wrapper(AgentTool):
        pass

    wrapper = _Wrapper()
    wrapper.name = prefixed
    wrapper.description = (mcp_tool.description or "")[:1024]
    wrapper.parameters = mcp_tool.input_schema or {"type": "object", "properties": {}}
    wrapper.run = run  # type: ignore[method-assign]
    return wrapper


class McpCapability(AgentCapability):
    name = "mcp"
    priority = 40

    def __init__(self, client, server_name: str = "server",
                 tool_threshold: int = DEFAULT_TOOL_THRESHOLD,
                 discover_ttl: float = 300.0) -> None:
        # client 可为单个 MCPClient 或多服务器 MCPClientPool（list_all_tools 接口）
        self._pool = client if hasattr(client, "list_all_tools") else None
        self._client = client
        self._server = server_name
        self._threshold = tool_threshold
        self._tools: Optional[List[AgentTool]] = None
        self._folded = False
        self._ttl = discover_ttl  # 工具目录缓存秒数；MCP 服务器热更新工具后自动重发现
        self._discovered_at: float = -1e18

    async def discover(self, force: bool = False) -> List[AgentTool]:
        """列出并转换 MCP 工具（折叠判定在此时做；TTL 内缓存，超时或 force 重发现）"""
        if (self._tools is not None and not force
                and time.monotonic() - self._discovered_at < self._ttl):
            return self._folded_tools()
        if self._pool is not None:
            pairs = await self._pool.list_all_tools()
            wrapped = [
                _mcp_tool_wrapper(self._pool, server, t, is_pool=True)
                for server, t in pairs
            ]
        else:
            mcp_tools = await self._client.list_tools()
            wrapped = [_mcp_tool_wrapper(self._client, self._server, t) for t in mcp_tools]
        self._folded = len(wrapped) > self._threshold
        self._tools = wrapped
        self._discovered_at = time.monotonic()
        return self._folded_tools()

    def _folded_tools(self) -> List[AgentTool]:
        assert self._tools is not None
        if not self._folded:
            return self._tools

        async def do_list(params: Dict[str, Any]) -> AgentToolResult:
            listing = "\n".join(
                f"- {t.name}: {t.description[:120]}" for t in self._tools
            )
            return AgentToolResult(
                content=[TextContent(
                    f"{len(self._tools)} tools available "
                    f"(call mcp_call_tool to use one):\n{listing}"
                )]
            )

        async def do_call(params: Dict[str, Any]) -> AgentToolResult:
            name = params["name"]
            match = next((t for t in self._tools if t.name == name), None)
            if match is None:
                return AgentToolResult(
                    content=[TextContent(f"unknown mcp tool: {name}")], is_error=True
                )
            return await match.run("mcp_call", params.get("arguments") or {}, None)

        return [
            FunctionTool(
                "mcp_list_tools",
                "List tools available on the connected MCP server.",
                {"type": "object", "properties": {}},
                do_list,
            ),
            FunctionTool(
                "mcp_call_tool",
                "Call a tool on the connected MCP server by its prefixed name.",
                {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Prefixed tool name from mcp_list_tools"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["name"],
                },
                do_call,
            ),
        ]

    def get_tools(self) -> List[AgentTool]:
        if self._tools is None:
            return []
        return self._folded_tools()

    def prompt_section(self) -> Optional[str]:
        if not self._folded or not self._tools:
            return None
        return (
            "<mcp>\n"
            f"An MCP server is connected with {len(self._tools)} tools. Use "
            "mcp_list_tools to see them and mcp_call_tool to invoke one.\n"
            "</mcp>"
        )


def _escape_prompt_text(s: str) -> str:
    """转义嵌入提示词 XML 框架的文本，防 skill 描述破坏框架（</skill> 注入）。"""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_prompt_attr(s: str) -> str:
    """转义 XML 属性值（含引号）。"""
    return _escape_prompt_text(s).replace('"', "&quot;")


def format_skills_prompt(skills_dirs: Optional[List[str]] = None,
                         max_skills: int = 100) -> Optional[str]:
    """扫描 SKILL.md 目录，返回系统提示词 XML 块（渐进披露：只含元数据）"""
    if skills_dirs is None:
        skills_dirs = [str(Path.home() / ".agents" / "skills")]
    entries: List[str] = []
    for base in skills_dirs:
        root = Path(base)
        if not root.is_dir():
            continue
        for skill_md in sorted(root.glob("*/SKILL.md")):
            try:
                from ...skills.frontmatter import parse_skill_md
                meta, _ = parse_skill_md(skill_md)
                raw = meta.to_dict() if hasattr(meta, "to_dict") else {}
            except Exception:
                continue
            if not raw:
                continue
            name = str(raw.get("name") or skill_md.parent.name)
            desc = str(raw.get("description") or "").strip()
            if not desc:
                continue
            safe_name = _escape_prompt_attr(name)
            safe_desc = _escape_prompt_text(desc[:400])
            entries.append(f'<skill name="{safe_name}">\n{safe_desc}\n</skill>')
            if len(entries) >= max_skills:
                break
    if not entries:
        return None
    return (
        "<available-skills>\n"
        "Skills below are detailed guides. To use one, call the skill_load tool "
        "(or read its SKILL.md with the read tool as fallback).\n"
        + "\n".join(entries)
        + "\n</available-skills>"
    )
