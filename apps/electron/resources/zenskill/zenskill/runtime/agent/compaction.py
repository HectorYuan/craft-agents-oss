"""会话压缩（参照 pi compaction：阈值触发、保尾预算、turn 边界对齐）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .session import Session
from .types import AssistantMessage, Context, Message, UserMessage

DEFAULT_RESERVE_TOKENS = 16384
DEFAULT_KEEP_RECENT_TOKENS = 20000


def estimate_tokens(messages: List[Message]) -> int:
    """估算 token 数（委托给 types.py 的统一实现）"""
    from .types import estimate_context_tokens
    return estimate_context_tokens(messages)


def context_pressure(used_tokens: int, context_window: int,
                     reserve: int = DEFAULT_RESERVE_TOKENS) -> str:
    """上下文压力三态（P2-7）：normal / warning (>=0.8) / compress (>=1.0)。

    should_compact 的底层实现；RPC get_state 用它向宿主暴露压力观测。
    """
    capacity = max(context_window - reserve, 1)
    ratio = used_tokens / capacity
    if ratio >= 1.0:
        return "compress"
    if ratio >= 0.8:
        return "warning"
    return "normal"


def should_compact(used_tokens: int, context_window: int,
                   reserve: int = DEFAULT_RESERVE_TOKENS) -> bool:
    return context_pressure(used_tokens, context_window, reserve) == "compress"


def find_cut_point(messages: List[Message],
                   keep_recent_tokens: int = DEFAULT_KEEP_RECENT_TOKENS) -> Optional[int]:
    """从尾向前累积 token 预算找截断点，对齐到 turn 边界（UserMessage 开头）。

    返回截断索引（0 < i < len）：messages[:i] 被摘要，messages[i:] 保留。
    保留段必须以 UserMessage 开头——否则压缩后上下文以孤立 tool_calls/
    ToolResultMessage 开头，LLM API 会拒绝（HTTP 400）。找不到安全边界时
    返回 None 跳过压缩。
    """
    budget = 0
    for i in range(len(messages) - 1, 0, -1):
        budget += estimate_tokens([messages[i]])
        if budget > keep_recent_tokens:
            # 优先：i 之后向前找最近的 turn 边界
            for j in range(i + 1, len(messages)):
                if isinstance(messages[j], UserMessage):
                    return j
            # 回退：从 i 向后扫找 UserMessage（预算略超但边界安全）
            for k in range(i, 0, -1):
                if isinstance(messages[k], UserMessage):
                    return k
            # 全序列无 UserMessage：无安全 turn 边界，放弃压缩
            return None
    return None


@dataclass
class CompactionResult:
    summary: str
    cut_index: int
    tokens_before: int
    tokens_after: int


async def summarize_prefix(messages: List[Message], stream, model) -> str:
    """用当前模型把前缀对话摘要为一段文字（一次 LLM 调用）"""
    # 确保消息序列合法：不以 tool_calls 结尾（LLM API 要求 tool_calls 后跟 tool result）
    safe_messages = list(messages)
    while safe_messages:
        last = safe_messages[-1]
        if type(last).__name__ == "AssistantMessage" and last.tool_calls():
            safe_messages.pop()
        elif type(last).__name__ == "ToolResultMessage":
            safe_messages.pop()
        else:
            break
    if not safe_messages:
        return "conversation start"

    prompt = (
        "You are a conversation summarizer. Produce a concise summary of the "
        "full history. Keep: task goal, key decisions, file paths touched, "
        "tool results of record, and unresolved issues. Be concise.\n\n"
    )
    summary_context = Context(
        messages=safe_messages + [UserMessage(content=prompt)],
    )
    parts: List[str] = []
    async for ev in stream(model, summary_context, None):
        etype = type(ev).__name__
        if etype == "TextDelta":
            parts.append(ev.text)
        elif etype == "StreamError":
            raise RuntimeError(f"compaction summarization failed: {ev.error.error_message}")
    return "".join(parts).strip()


async def compact_session(session: Session, stream, model,
                          context_window: int = 128_000,
                          keep_recent_tokens: int = DEFAULT_KEEP_RECENT_TOKENS,
                          reserve: int = DEFAULT_RESERVE_TOKENS) -> Optional[CompactionResult]:
    """若超过阈值则压缩当前分支：摘要前缀 + compaction entry 落盘。

    支持重复压缩：entry 映射通过 collect_pairs 计算（与 build_context 同源，
    已考虑历史 compaction 折叠），新摘要会把旧摘要一并卷入。
    """
    collected, _model = session.collect_pairs()
    messages: List[Message] = [m for _, m in collected]
    used = estimate_tokens(messages)
    if not should_compact(used, context_window, reserve):
        return None

    cut = find_cut_point(messages, keep_recent_tokens)
    if cut is None or cut <= 0:
        return None

    summary = await summarize_prefix(messages[:cut], stream, model)

    # 保留段第一条消息对应的 entry id（collected 与 messages 一一对应）
    first_kept_entry_id = None
    if cut < len(collected):
        first_kept_entry_id = collected[cut][0]

    session.append("compaction", {
        "summary": summary,
        "firstKeptEntryId": first_kept_entry_id,
        "tokensBefore": used,
        "details": {"cutIndex": cut, "contextWindow": context_window},
    })
    tokens_after = estimate_tokens(
        [UserMessage(content=summary)] + messages[cut:]
    )
    return CompactionResult(
        summary=summary,
        cut_index=cut,
        tokens_before=used,
        tokens_after=tokens_after,
    )
