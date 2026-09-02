"""SubAgent 委派工具：子任务在隔离子上下文中执行，只把最终文本交回父 agent。

- 双重递归防护：子 agent 工具集构造时不包含 delegate（结构上不可再委派）
  + depth/max_depth 深度校验（防御纵深）
- 子上下文全新：不继承父对话历史，避免上下文膨胀；系统提示词继承父级
- on_update 转发子 agent 进度（父级 UI 可见子任务执行到第几轮）
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .agent_loop import AgentLoop, AgentLoopConfig
from .tools import DEFAULT_SYSTEM_PROMPT, create_default_tools
from .types import AgentTool, AgentToolResult, Context, TextContent, UserMessage

logger = logging.getLogger(__name__)


class DelegateTool(AgentTool):
    """把聚焦子任务委派给隔离子 agent。"""

    name = "delegate"
    description = (
        "Delegate a focused subtask to a sub-agent with a fresh context. "
        "The sub-agent has the same core tools but NO conversation history — "
        "the task description must be self-contained. Use for isolated "
        "research/exploration/drafting steps whose full transcript would "
        "waste the main context; only the sub-agent's final answer returns. "
        "Do NOT delegate simple single-tool actions."
    )
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Self-contained subtask description (the sub-agent sees nothing else)",
            },
            "max_steps": {
                "type": "integer",
                "description": "Max tool-execution turns for the sub-agent (default 6, cap 12)",
            },
        },
        "required": ["task"],
    }

    def __init__(
        self,
        stream_fn,
        model,
        cwd: str = ".",
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_depth: int = 2,
        depth: int = 0,
        default_max_steps: int = 6,
        extra_tools: Optional[List[AgentTool]] = None,
    ) -> None:
        self._stream_fn = stream_fn
        self._model = model
        self._cwd = cwd
        self._system_prompt = system_prompt
        self._max_depth = max_depth
        self._depth = depth
        self._default_max_steps = default_max_steps
        self._extra_tools = extra_tools or []

    async def run(self, tool_call_id: str, params: Dict[str, Any], on_update=None) -> AgentToolResult:
        if self._depth >= self._max_depth:
            return AgentToolResult(
                content=[TextContent(f"Delegation depth limit reached ({self._max_depth}). Handle this task yourself.")],
                is_error=True,
            )
        task = (params.get("task") or "").strip()
        if not task:
            return AgentToolResult(
                content=[TextContent("delegate requires 'task' parameter.")],
                is_error=True,
            )
        steps = params.get("max_steps") or self._default_max_steps
        steps = max(1, min(int(steps), 12))

        # 子工具集：核心工具 + 能力工具，不含 delegate（结构级递归防护）
        sub_tools = create_default_tools(self._cwd) + self._extra_tools

        sub_context = Context(
            messages=[UserMessage(content=task)],
            system_prompt=self._system_prompt,
            tools=sub_tools,
        )
        config = AgentLoopConfig(
            stream=self._stream_fn,
            model=self._model,
            max_steps=steps,
        )
        sub_loop = AgentLoop(config)

        final_text = ""
        turn = 0
        try:
            async for ev in sub_loop.run(sub_context):
                etype = type(ev).__name__
                if etype == "TurnStart":
                    turn += 1
                    if on_update is not None:
                        on_update(f"sub-agent turn {turn}")
                elif etype == "ToolExecutionStart" and on_update is not None:
                    on_update(f"sub-agent: {ev.tool_name}")
                elif etype == "MessageEnd":
                    msg = ev.message
                    if hasattr(msg, "text"):
                        text = msg.text()
                        if text:
                            final_text = text
        except Exception as e:
            return AgentToolResult(
                content=[TextContent(f"Sub-agent failed: {type(e).__name__}: {e}")],
                is_error=True,
            )

        if not final_text:
            return AgentToolResult(
                content=[TextContent("Sub-agent finished without a text answer.")],
                is_error=True,
            )
        if len(final_text) > 8000:
            final_text = final_text[:4000] + "\n\n... (truncated) ...\n\n" + final_text[-2000:]
        return AgentToolResult(content=[TextContent(final_text)])
