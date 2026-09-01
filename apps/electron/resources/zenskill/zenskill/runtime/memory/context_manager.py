"""上下文管理器 — 记忆注入"""

from __future__ import annotations

from typing import Any

from .memory_store import MemoryEntry, MemoryStore, MemoryType
from .short_term import ShortTermMemory
from .long_term import LongTermMemory


class ContextManager:
    """上下文管理器

    整合短期和长期记忆，为执行提供上下文。

    使用方式：
        ctx = ContextManager(short_term, long_term)
        context = await ctx.get_context("读取配置文件")
        # context 包含相关记忆、历史错误、用户偏好等
    """

    def __init__(
        self,
        short_term: ShortTermMemory | None = None,
        long_term: LongTermMemory | None = None,
    ) -> None:
        """初始化上下文管理器

        Args:
            short_term: 短期记忆
            long_term: 长期记忆
        """
        self._short_term = short_term or ShortTermMemory()
        self._long_term = long_term

    @property
    def short_term(self) -> ShortTermMemory:
        return self._short_term

    @property
    def long_term(self) -> LongTermMemory | None:
        return self._long_term

    async def get_context(self, task: str) -> dict[str, Any]:
        """获取任务相关上下文

        整合短期和长期记忆，构建完整的执行上下文。

        Args:
            task: 任务描述

        Returns:
            上下文字典，包含：
            - memories: 相关记忆列表
            - avoid_errors: 应避免的错误模式
            - procedures: 成功的执行流程
            - preferences: 用户偏好
        """
        context: dict[str, Any] = {
            "task": task,
            "memories": [],
            "avoid_errors": [],
            "procedures": [],
            "preferences": [],
        }

        # 从短期记忆获取
        short_memories = await self._short_term.recall(task, limit=5)
        for mem in short_memories:
            context["memories"].append(mem.to_dict())
            if mem.memory_type == MemoryType.ERROR:
                context["avoid_errors"].append(mem.content)
            elif mem.memory_type == MemoryType.PROCEDURE:
                context["procedures"].append(mem.content)
            elif mem.memory_type == MemoryType.PREFERENCE:
                context["preferences"].append(mem.content)

        # 从长期记忆获取
        if self._long_term:
            long_memories = await self._long_term.recall(task, limit=5)
            for mem in long_memories:
                # 去重
                if not any(m["id"] == mem.id for m in context["memories"]):
                    context["memories"].append(mem.to_dict())
                    if mem.memory_type == MemoryType.ERROR:
                        context["avoid_errors"].append(mem.content)
                    elif mem.memory_type == MemoryType.PROCEDURE:
                        context["procedures"].append(mem.content)
                    elif mem.memory_type == MemoryType.PREFERENCE:
                        context["preferences"].append(mem.content)

        return context

    async def remember_success(
        self,
        task: str,
        tool_name: str,
        args: dict[str, Any],
        output: str,
    ) -> None:
        """记录成功的执行

        Args:
            task: 任务描述
            tool_name: 工具名称
            args: 工具参数
            output: 执行输出
        """
        entry = MemoryEntry(
            content=f"Success: {tool_name}({args}) → {output[:100]}",
            memory_type=MemoryType.PROCEDURE,
            source="tool_execution",
            context={"task": task, "tool": tool_name, "args": args},
            importance=0.6,
            tags=[tool_name, "success"],
        )
        await self._short_term.remember(entry)

        if self._long_term:
            await self._long_term.remember(entry)

    async def remember_error(
        self,
        task: str,
        tool_name: str,
        args: dict[str, Any],
        error: str,
    ) -> None:
        """记录失败的执行

        Args:
            task: 任务描述
            tool_name: 工具名称
            args: 工具参数
            error: 错误信息
        """
        entry = MemoryEntry(
            content=f"Error: {tool_name}({args}) → {error}",
            memory_type=MemoryType.ERROR,
            source="tool_execution",
            context={"task": task, "tool": tool_name, "args": args, "error": error},
            importance=0.7,  # 错误记忆更重要
            tags=[tool_name, "error"],
        )
        await self._short_term.remember(entry)

        if self._long_term:
            await self._long_term.remember(entry)

    async def remember_preference(
        self,
        preference: str,
        source: str = "user_input",
    ) -> None:
        """记录用户偏好

        Args:
            preference: 偏好描述
            source: 来源
        """
        entry = MemoryEntry(
            content=preference,
            memory_type=MemoryType.PREFERENCE,
            source=source,
            importance=0.8,
            tags=["preference"],
        )
        await self._short_term.remember(entry)

        if self._long_term:
            await self._long_term.remember(entry)

    async def consolidate(self) -> None:
        """整合记忆"""
        await self._short_term.consolidate()
        if self._long_term:
            await self._long_term.consolidate()

    async def clear(self) -> None:
        """清空所有记忆"""
        await self._short_term.clear()
        if self._long_term:
            await self._long_term.clear()
