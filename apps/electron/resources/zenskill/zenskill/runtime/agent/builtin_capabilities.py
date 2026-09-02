"""内建 Capability：Memory（M4-2）与 Reflection（M4-3）。

MemoryCapability：把 runtime/memory 三层存储接入 agent 循环——
before_turn 注入相关记忆（修复"记忆从未进 prompt"的断裂），
after_turn 记录任务级 episode，暴露 memory_remember/memory_recall 工具。

ReflectionCapability：把 runtime/reflection 降级为观察者——
after_tool 对错误结果做 SelfEvaluator 分类并写入 ERROR 记忆，
重试决策完全交还 LLM 循环（M1 已验证模型自纠）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .capability import AgentCapability
from .types import (
    AgentToolResult,
    Context,
    FunctionTool,
    Message,
    TextContent,
    ToolResultMessage,
    UserMessage,
)

logger = logging.getLogger(__name__)


def _last_user_text(messages: List[Message]) -> str:
    for m in reversed(messages):
        if isinstance(m, UserMessage):
            return m.text()
    return ""


def _make_context_manager(memory_root: Optional[str]):
    from ..memory.context_manager import ContextManager
    from ..memory.long_term import LongTermMemory
    from ..memory.short_term import ShortTermMemory

    short_term = ShortTermMemory(memory_dir=memory_root)
    long_term = LongTermMemory(memory_dir=memory_root)
    return ContextManager(short_term=short_term, long_term=long_term)


def _tokens(text: str) -> set:
    """分词：英文按空格，CJK 逐字（中文无空格分隔符）"""
    result = set()
    for w in text.lower().split():
        has_cjk = any(0x4E00 <= ord(ch) <= 0x9FFF for ch in w)
        if has_cjk:
            for ch in w:
                if 0x4E00 <= ord(ch) <= 0x9FFF:
                    result.add(ch)
        elif len(w) > 2:
            result.add(w)
    return result


class MemoryCapability(AgentCapability):
    name = "memory"
    priority = 20

    def __init__(self, memory_root: Optional[str] = None, max_memories: int = 5) -> None:
        self._root = memory_root
        self._max = max_memories
        self._manager = None

    def _ensure_manager(self):
        if self._manager is None:
            self._manager = _make_context_manager(self._root)
        return self._manager

    async def before_turn(self, messages: List[Message]) -> Optional[List[Message]]:
        task = _last_user_text(messages)
        if not task:
            return None
        try:
            ctx = await self._ensure_manager().get_context(task)
        except Exception:
            ctx = {}
        memories = list(ctx.get("memories") or [])

        if not memories:
            # ShortTermMemory.recall 要求 query 为 content 子串，长任务查短
            # 记忆会落空：退化为 recall("") 获取全部记忆 + 词重叠过滤
            try:
                task_tokens = _tokens(task)
                all_entries = await self._ensure_manager().short_term.recall("", limit=20)
                for entry in all_entries:
                    entry_tokens = _tokens(entry.content) | _tokens(" ".join(entry.tags))
                    if len(task_tokens & entry_tokens) >= 1:
                        memories.append({"content": entry.content})
            except Exception as e:
                logger.debug("MemoryCapability: recall fallback degraded: %s: %s",
                             type(e).__name__, e)

        lines: List[str] = []
        for memory in memories[: self._max]:
            content = getattr(memory, "content", None)
            if content is None and isinstance(memory, dict):
                content = memory.get("content")
            if content:
                lines.append(f"- {str(content)[:200]}")
        for err in (ctx.get("avoid_errors") or [])[:3]:
            text = err if isinstance(err, str) else (
                getattr(err, "content", None)
                or (err.get("content") if isinstance(err, dict) else None)
            )
            if text:
                lines.append(f"- past error to avoid: {str(text)[:200]}")
        if not lines:
            return None
        injected = UserMessage(
            content="[system-memory] Relevant memories from previous sessions:\n"
            + "\n".join(lines)
        )
        return [injected] + list(messages)

    async def after_turn(self, context: Context, last_message: Any) -> None:
        summary = ""
        if isinstance(last_message, object) and hasattr(last_message, "text"):
            try:
                summary = last_message.text()[:500]
            except Exception:
                summary = ""
        if not summary:
            # 工具调用消息 text() 为空，记录工具名+参数作为 episode
            tool_calls = getattr(last_message, "tool_calls", lambda: [])()
            if tool_calls:
                parts = []
                for tc in tool_calls[:3]:
                    args_str = ", ".join(f"{k}={str(v)[:30]}" for k, v in list(tc.arguments.items())[:2])
                    parts.append(f"{tc.name}({args_str})")
                summary = f"called: {', '.join(parts)}"
        if not summary:
            return
        try:
            from ..memory.memory_store import MemoryEntry, MemoryType
            entry = MemoryEntry(
                content=summary,
                memory_type=MemoryType.FACT,
                tags=["agent-session"],
            )
            await self._ensure_manager().short_term.remember(entry)
        except Exception as e:
            logger.warning("MemoryCapability: episode persist failed: %s: %s",
                           type(e).__name__, e)

    def get_tools(self) -> List[Any]:
        async def do_remember(params: Dict[str, Any]) -> AgentToolResult:
            from ..memory.memory_store import MemoryEntry, MemoryType
            entry = MemoryEntry(
                content=params["content"],
                memory_type=MemoryType.FACT,
                tags=list(params.get("tags") or []),
            )
            await self._ensure_manager().short_term.remember(entry)
            return AgentToolResult(content=[TextContent("remembered")])

        async def do_recall(params: Dict[str, Any]) -> AgentToolResult:
            manager = self._ensure_manager()
            entries = await manager.short_term.recall(
                params["query"], limit=int(params.get("limit", 5) or 5)
            )
            if not entries:
                return AgentToolResult(content=[TextContent("[no memories]")])
            lines = [f"- {e.content[:200]}" for e in entries]
            return AgentToolResult(content=[TextContent("\n".join(lines))])

        return [
            FunctionTool(
                "memory_remember",
                "Store a durable fact or lesson for future sessions.",
                {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["content"],
                },
                do_remember,
            ),
            FunctionTool(
                "memory_recall",
                "Recall memories relevant to a query from previous sessions.",
                {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["query"],
                },
                do_recall,
            ),
        ]


class ReflectionCapability(AgentCapability):
    name = "reflection"
    priority = 60

    def __init__(self, memory_root: Optional[str] = None, reflect_interval: int = 5) -> None:
        self._root = memory_root
        self._evaluator = None
        self.error_count = 0
        self._turn_count = 0
        self._reflect_interval = reflect_interval

    def prompt_section(self) -> Optional[str]:
        return (
            "<reflection>\n"
            "After each tool call, briefly assess:\n"
            "1. Did the tool succeed?\n"
            "2. Did the result match your expectation?\n"
            "3. Are you closer to completing the task?\n"
            "If the answer to any is no, adjust your approach before proceeding. "
            "Do not retry the exact same failing command.\n"
            "</reflection>"
        )

    async def after_tool(self, result: ToolResultMessage) -> Optional[ToolResultMessage]:
        if not result.is_error:
            return None
        self.error_count += 1
        error_type = "UNKNOWN"
        try:
            from ..mcp_client import ToolResult
            from ..reflection.self_evaluator import SelfEvaluator
            if self._evaluator is None:
                self._evaluator = SelfEvaluator()
            evaluation = await self._evaluator.evaluate(
                task="",
                tool_name=result.tool_name,
                args={},
                result=ToolResult(success=False, error=result.text()[:500], is_error=True),
                context={},
            )
            raw_type = getattr(evaluation, "error_type", None)
            error_type = getattr(raw_type, "value", str(raw_type or "UNKNOWN"))
        except Exception as e:
            logger.debug("ReflectionCapability: error evaluation degraded: %s: %s",
                         type(e).__name__, e)
        try:
            manager = _make_context_manager(self._root)
            await manager.remember_error(
                task="",
                tool_name=result.tool_name,
                args={},
                error=f"[{error_type}] {result.text()[:300]}",
            )
        except Exception as e:
            logger.warning("ReflectionCapability: remember_error failed: %s: %s",
                           type(e).__name__, e)
        return None

    async def after_turn(self, context: Context, last_message: Any) -> None:
        """每 N 轮注入反思提示（E4-2）"""
        self._turn_count += 1
        if self._turn_count > 0 and self._turn_count % self._reflect_interval == 0:
            prompt = UserMessage(
                content=(
                    f"[system] Reflection checkpoint (turn {self._turn_count}): "
                    f"Review your progress so far. Are you on track? "
                    f"If not, adjust your approach. Summarize what you've done and what remains."
                )
            )
            context.messages.append(prompt)


class SummaryCapability(AgentCapability):
    """大响应摘要：工具返回超长结果时调 LLM 摘要或截断，避免撑爆上下文（E3-4）。"""
    name = "summary"
    priority = 70

    def __init__(self, llm_simple_chat=None, max_chars: int = 15000) -> None:
        self._llm = llm_simple_chat
        self._max = max_chars

    async def after_tool(self, result: ToolResultMessage) -> Optional[ToolResultMessage]:
        text = result.text()
        if len(text) <= self._max:
            return None

        # 尝试 LLM 摘要
        if self._llm is not None:
            try:
                summary = await self._llm(
                    f"Summarize the following tool output in 3-5 sentences. "
                    f"Keep key information (file paths, error messages, important values).\n\n{text[:8000]}"
                )
                prefix = f"[Summarized from {len(text)} chars] "
                result.content = [TextContent(prefix + summary)]
                return result
            except Exception:
                pass

        # 回退：硬截断
        truncated = text[:self._max // 2] + "\n...\n" + text[-self._max // 2:]
        prefix = f"[truncated from {len(text)} chars] "
        result.content = [TextContent(prefix + truncated)]
        return result


_TASK_PATTERNS = {
    "bug": ["bug", "fix", "修复", "错误", "error", "broken", "crash", "崩溃", "报错"],
    "code": ["写", "实现", "create", "implement", "add", "新增", "添加", "write", "编写"],
    "refactor": ["重构", "refactor", "优化", "重写", "clean up", "整理"],
    "research": ["分析", "调查", "调研", "explain", "analyze", "understand", "理解", "describe", "描述"],
    "test": ["测试", "test", "verify", "验证", "check", "检查"],
}

_TASK_STRATEGIES = {
    "bug": "[strategy: fix bug] 1. Read relevant code 2. Locate the bug 3. Understand root cause 4. Fix 5. Verify fix",
    "code": "[strategy: write code] 1. Understand requirements 2. Design approach 3. Implement 4. Test 5. Review",
    "refactor": "[strategy: refactor] 1. Read existing code 2. Plan changes 3. Refactor incrementally 4. Verify each step",
    "research": "[strategy: research] 1. Search/grep for relevant code 2. Read key files 3. Summarize findings",
    "test": "[strategy: test] 1. Read the code to test 2. Write tests 3. Run tests 4. Fix failures",
}


class TaskTypeCapability(AgentCapability):
    """根据用户消息自动分类任务类型，在消息前注入策略提示（E2-2）。"""
    name = "task_type"
    priority = 10  # 最高优先级，最早执行

    def before_turn(self, messages: List[Message]) -> Optional[List[Message]]:
        # 只在第一轮（只有 user 消息时）注入
        user_msgs = [m for m in messages if isinstance(m, UserMessage)]
        if len(user_msgs) != 1:
            return None
        task = user_msgs[0].text().lower()
        for task_type, keywords in _TASK_PATTERNS.items():
            if any(kw in task for kw in keywords):
                strategy = _TASK_STRATEGIES[task_type]
                injected = UserMessage(content=f"[system] {strategy}")
                return [injected] + list(messages)
        return None
