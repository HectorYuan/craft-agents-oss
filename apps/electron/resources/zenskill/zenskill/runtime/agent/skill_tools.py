"""Skill → Tool 自动发现：将 SKILL.md 转换为 AgentTool。

扫描 ~/.agents/skills/*/SKILL.md，每个 skill 变为一个 tool：
- tool name: skill_{name}
- description: frontmatter 的 description
- run: 返回 SKILL.md body（LLM 获取技能指令）

渐进披露：当 skill 数量 > max_tools 时，折叠为 2 个 meta-tool：
- skill_list: 列出所有 skill name + description
- skill_load: 按 name 加载 skill body
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .types import AgentTool, AgentToolResult, FunctionTool, TextContent

DEFAULT_SKILLS_DIRS = [str(Path.home() / ".agents" / "skills")]
MAX_BODY_CHARS = 12000
CACHE_TTL_SECONDS = 300  # 5 分钟 TTL 缓存

# TTL 缓存：key=(skills_dirs, max_tools) -> (expire_at, tools)
_skill_cache: Dict[Tuple[Tuple[str, ...], int], Tuple[float, List[AgentTool]]] = {}
_skill_cache_lock = threading.Lock()


def clear_skill_cache() -> None:
    """清空 load_skill_tools 的 TTL 缓存。"""
    with _skill_cache_lock:
        _skill_cache.clear()


def _cache_key(skills_dirs: List[str], max_tools: int) -> Tuple[Tuple[str, ...], int]:
    return (tuple(skills_dirs), max_tools)


def load_skill_tools(
    skills_dirs: Optional[List[str]] = None,
    max_tools: int = 30,
) -> List[AgentTool]:
    """扫描 SKILL.md 目录，返回 AgentTool 列表（超过 max_tools 时折叠）。

    结果按 (skills_dirs, max_tools) 缓存 CACHE_TTL_SECONDS（5 分钟），
    避免重复扫描磁盘；调用 clear_skill_cache() 可手动失效。
    """
    if skills_dirs is None:
        skills_dirs = DEFAULT_SKILLS_DIRS

    key = _cache_key(skills_dirs, max_tools)
    now = time.monotonic()

    with _skill_cache_lock:
        hit = _skill_cache.get(key)
        if hit is not None:
            expire_at, tools = hit
            if now < expire_at:
                return list(tools)  # 返回副本，避免调用方修改缓存内容
            _skill_cache.pop(key, None)

    skills = _discover_skills(skills_dirs)
    if not skills:
        tools: List[AgentTool] = []
    elif len(skills) <= max_tools:
        tools = [_make_skill_tool(s) for s in skills]
    else:
        tools = _make_folded_tools(skills)

    with _skill_cache_lock:
        _skill_cache[key] = (time.monotonic() + CACHE_TTL_SECONDS, tools)
    return list(tools)


def _discover_skills(skills_dirs: List[str]) -> List[Dict[str, str]]:
    """扫描目录，返回 [{name, description, path}] 列表。"""
    from ...skills.frontmatter import parse_skill_md

    skills: List[Dict[str, str]] = []
    for base in skills_dirs:
        root = Path(base)
        if not root.is_dir():
            continue
        for skill_md in sorted(root.glob("*/SKILL.md")):
            try:
                meta, _ = parse_skill_md(skill_md)
                name = meta.name or skill_md.parent.name
                desc = meta.description or ""
                if not name or not desc:
                    continue
                skills.append({
                    "name": name,
                    "description": desc.strip(),
                    "path": str(skill_md),
                })
            except Exception:
                continue
    return skills


def _make_skill_tool(skill: Dict[str, str]) -> AgentTool:
    """单个 skill → AgentTool。"""
    tool_name = f"skill_{skill['name']}"
    description = skill["description"]
    skill_path = skill["path"]

    async def _run(params: Dict[str, Any]) -> AgentToolResult:
        try:
            body = Path(skill_path).read_text(encoding="utf-8")
            # 去掉 frontmatter 部分
            if body.startswith("---"):
                lines = body.split("\n")
                end = -1
                for i, line in enumerate(lines[1:], 1):
                    if line.strip() == "---":
                        end = i
                        break
                if end > 0:
                    body = "\n".join(lines[end + 1:]).strip()
            if len(body) > MAX_BODY_CHARS:
                body = body[:MAX_BODY_CHARS] + f"\n\n... (truncated, {len(skill['path'])} total chars)"
            return AgentToolResult(content=[TextContent(body)])
        except Exception as e:
            return AgentToolResult(
                content=[TextContent(f"Failed to load skill {skill['name']}: {e}")],
                is_error=True,
            )

    tool = FunctionTool(
        name=tool_name,
        description=description,
        parameters={"type": "object", "properties": {}},
        fn=_run,
        concurrency_safe=True,  # 纯读 SKILL.md，无副作用
    )
    return tool


def _make_folded_tools(skills: List[Dict[str, str]]) -> List[AgentTool]:
    """折叠模式：skill_list + skill_load 两个 meta-tool。"""
    skill_map = {s["name"]: s for s in skills}

    async def _list_fn(params: Dict[str, Any]) -> AgentToolResult:
        lines = [f"- {s['name']}: {s['description'][:120]}" for s in skills]
        listing = f"{len(skills)} skills available (call skill_load to use one):\n" + "\n".join(lines)
        return AgentToolResult(content=[TextContent(listing)])

    async def _load_fn(params: Dict[str, Any]) -> AgentToolResult:
        name = params.get("name", "")
        skill = skill_map.get(name)
        if not skill:
            return AgentToolResult(
                content=[TextContent(f"Unknown skill: {name}. Use skill_list to see available skills.")],
                is_error=True,
            )
        return await _make_skill_tool(skill).run("skill_load", params)

    return [
        FunctionTool(
            name="skill_list",
            description="List all available skills with their names and descriptions.",
            parameters={"type": "object", "properties": {}},
            fn=_list_fn,
            concurrency_safe=True,
        ),
        FunctionTool(
            name="skill_load",
            description="Load a skill's full instructions by name. Use skill_list first to find the name.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name from skill_list"},
                },
                "required": ["name"],
            },
            fn=_load_fn,
            concurrency_safe=True,
        ),
    ]
