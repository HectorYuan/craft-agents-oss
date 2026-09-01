"""Capability 插件体系（参照 AgentSwarm capabilities/base.py 的 LEGO 模式，M4-1）。

Capability = 类级扩展：生命周期（on_init/on_stop）+ 循环钩子 + get_tools()。
CapabilityHost 按 priority（0-100，小者先）排序并把钩子串接成 M1 AgentLoop
的配置回调；与 AgentSwarm 的差异：不引入 P0-P4 五层枚举，数字优先级即可。

桥接映射：
- before_turn(messages)  -> transform_context（返回新列表可注入消息）
- before_tool(tc, params) -> before_tool_call（首个 veto 生效）
- after_tool(result)      -> after_tool_call（链式）
- after_turn(ctx, last)   -> prepare_next_turn
- prompt_section()        -> build_system_prompt() 拼接段
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .types import AgentTool, Context, Message, ToolCall, ToolResultMessage


async def _call(fn, *args):
    result = fn(*args)
    if asyncio.iscoroutine(result):
        result = await result
    return result


class AgentCapability:
    name: str = "capability"
    priority: int = 50

    def on_init(self, host: "CapabilityHost") -> None:
        pass

    def on_stop(self) -> None:
        pass

    def get_tools(self) -> List[AgentTool]:
        return []

    def prompt_section(self) -> Optional[str]:
        return None

    def before_turn(self, messages: List[Message]) -> Optional[List[Message]]:
        return None

    def after_turn(self, context: Context, last_message: Any) -> None:
        pass

    def before_tool(self, tool_call: ToolCall, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return None

    def after_tool(self, result: ToolResultMessage) -> Optional[ToolResultMessage]:
        return None


class CapabilityHost:
    def __init__(self, capabilities: Optional[List[AgentCapability]] = None) -> None:
        self.capabilities: List[AgentCapability] = sorted(
            capabilities or [], key=lambda c: c.priority
        )
        self.extra_tools: List[AgentTool] = []
        self._prompt_sections: List[str] = []
        self._initialized = False

    def add(self, capability: AgentCapability) -> None:
        self.capabilities.append(capability)
        self.capabilities.sort(key=lambda c: c.priority)
        if self._initialized:
            capability.on_init(self)

    def remove(self, name: str) -> bool:
        for i, cap in enumerate(self.capabilities):
            if cap.name == name:
                self.capabilities.pop(i).on_stop()
                return True
        return False

    def register_tool(self, tool: AgentTool) -> None:
        self.extra_tools.append(tool)

    def add_prompt_section(self, section: str) -> None:
        self._prompt_sections.append(section)

    def initialize(self) -> None:
        if self._initialized:
            return
        for cap in self.capabilities:
            cap.on_init(self)
            for tool in cap.get_tools():
                self.register_tool(tool)
            section = cap.prompt_section()
            if section:
                self._prompt_sections.append(section)
        self._initialized = True

    def shutdown(self) -> None:
        for cap in self.capabilities:
            cap.on_stop()
        self._initialized = False

    def build_system_prompt(self, base: str) -> str:
        self.initialize()
        parts = [base] + [s for s in self._prompt_sections if s]
        return "\n\n".join(p.rstrip() for p in parts if p and p.strip())

    # ------------------------------------------------------------------
    # 桥接为 AgentLoopConfig 回调
    # ------------------------------------------------------------------

    def hooks(self) -> Dict[str, Any]:
        self.initialize()
        kw: Dict[str, Any] = {}

        if self.capabilities:
            async def transform_context(messages: List[Message]) -> List[Message]:
                current = list(messages)
                for cap in self.capabilities:
                    injected = await _call(cap.before_turn, current)
                    if injected is not None:
                        current = list(injected)
                return current
            kw["transform_context"] = transform_context

            async def before_tool_call(tool_call: ToolCall, params: Dict[str, Any]):
                for cap in self.capabilities:
                    veto = await _call(cap.before_tool, tool_call, params)
                    if isinstance(veto, dict) and veto.get("block"):
                        return veto
                return None
            kw["before_tool_call"] = before_tool_call

            async def after_tool_call(result: ToolResultMessage):
                for cap in self.capabilities:
                    patched = await _call(cap.after_tool, result)
                    if patched is not None:
                        result = patched
                return result
            kw["after_tool_call"] = after_tool_call

            async def prepare_next_turn(context: Context, last_message: Any) -> None:
                for cap in self.capabilities:
                    await _call(cap.after_turn, context, last_message)
            kw["prepare_next_turn"] = prepare_next_turn

        return kw
