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


def should_compact(used_tokens: int, context_window: int,
                   reserve: int = DEFAULT_RESERVE_TOKENS) -> bool:
    return used_tokens > context_window - reserve


def find_cut_point(messages: List[Message],
                   keep_recent_tokens: int = DEFAULT_KEEP_RECENT_TOKENS) -> Optional[int]:
    """从尾向前累积 token 预算找截断点，对齐到 turn 边界（UserMessage 开头）。

    返回截断索引（0 < i < len）：messages[:i] 被摘要，messages[i:] 保留。
    """
    budget = 0
    for i in range(len(messages) - 1, 0, -1):
        budget += estimate_tokens([messages[i]])
        if budget > keep_recent_tokens:
            # i 之后的消息超预算：在 (i, len) 内向前找最近的 turn 边界
            for j in range(i + 1, len(messages)):
                if isinstance(messages[j], UserMessage):
                    return j
            return i + 1
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

    前缀消息从 entry 链上由 compaction.firstKeptEntryId 指向保留起点；
    build_context 会用摘要替换被压缩前缀。
    """
    built = session.build_context()
    messages: List[Message] = built["messages"]
    used = estimate_tokens(messages)
    if not should_compact(used, context_window, reserve):
        return None

    chain = session.walk()
    # M2 限定每分支压缩一次：已有 compaction 时摘要叠加会使 entry 映射失效
    if any(e.type == "compaction" for e in chain):
        return None

    cut = find_cut_point(messages, keep_recent_tokens)
    if cut is None or cut <= 0:
        return None

    summary = await summarize_prefix(messages[:cut], stream, model)

    # 保留段第一条消息对应的 entry id（当前分支 walk 与 messages 一一对应）
    message_entries = [e for e in chain if e.type == "message"]
    first_kept_entry_id = None
    if cut < len(message_entries):
        first_kept_entry_id = message_entries[cut].id

    entry = session.append("compaction", {
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
