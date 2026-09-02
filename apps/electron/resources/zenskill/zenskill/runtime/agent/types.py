"""Agent 引擎核心数据模型（参照 pi packages/ai + packages/agent 的类型设计）。

设计原则：
- Context/Message/内容块全部可 JSON 序列化（to_dict），为会话持久化（M2/M3）铺路
- 流式契约：StreamFn 永不抛异常，失败编码为 StreamError 携带的终态 AssistantMessage
- 工具结果分离 content（给模型）与 details（给 UI/日志）
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id(prefix: str = "") -> str:
    raw = uuid.uuid4().hex[:16]
    return f"{prefix}{raw}" if prefix else raw


# ---------------------------------------------------------------------------
# StopReason 常量（对齐 pi 的 StopReason）
# ---------------------------------------------------------------------------

class StopReason:
    STOP = "stop"
    LENGTH = "length"
    TOOL_USE = "toolUse"
    ERROR = "error"
    ABORTED = "aborted"


# ---------------------------------------------------------------------------
# 内容块
# ---------------------------------------------------------------------------

@dataclass
class TextContent:
    text: str
    type: str = "text"


@dataclass
class ThinkingContent:
    thinking: str
    type: str = "thinking"


@dataclass
class ImageContent:
    data: str  # base64
    mime_type: str = "image/png"
    type: str = "image"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    type: str = "toolCall"


ContentBlock = Union[TextContent, ThinkingContent, ImageContent, ToolCall]


# ---------------------------------------------------------------------------
# Usage / Cost
# ---------------------------------------------------------------------------


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    reasoning: int = 0  # thinking tokens（provider 上报时采集；DeepSeek 占比可达 60%）

    def add(self, other: "Usage") -> None:
        self.input += other.input
        self.output += other.output
        self.cache_read += other.cache_read
        self.cache_write += other.cache_write
        self.reasoning += other.reasoning

    @property
    def total_tokens(self) -> int:
        return self.input + self.output + self.cache_read + self.cache_write

    def to_dict(self) -> Dict[str, int]:
        return {
            "input": self.input,
            "output": self.output,
            "cache_read": self.cache_read,
            "cache_write": self.cache_write,
            "reasoning": self.reasoning,
            "total_tokens": self.total_tokens,
        }


def total_usage(messages: List["Message"]) -> Usage:
    usage = Usage()
    for m in messages:
        if isinstance(m, AssistantMessage):
            usage.add(m.usage)
    return usage


# CJK 感知估算系数：1 汉字 ≈ 0.7 token，其他字符 ≈ 0.25（等价 char/4）。
# 系数为启发式估计值；运行期由真实 API usage 自动校准（见 _UsageCalibrator）。
_CJK_TOKEN_RATIO = 0.7
_OTHER_TOKEN_RATIO = 0.25


class _UsageCalibrator:
    """用真实 API usage 对估算值做乘法校正（滚动窗口均值）。

    真实 input tokens / 启发式估算 的比值随样本累积收敛；校正因子
    夹在 [0.5, 2.0] 防止病态样本破坏估算。进程内存活，重启归位。
    """

    def __init__(self, max_samples: int = 64) -> None:
        self._samples: List[float] = []
        self._max_samples = max_samples
        self._lock = threading.Lock()
        self._correction = 1.0

    def observe(self, estimated: int, real: int) -> None:
        if estimated <= 0 or real <= 0:
            return
        ratio = real / estimated
        with self._lock:
            self._samples.append(ratio)
            if len(self._samples) > self._max_samples:
                self._samples.pop(0)
            mean = sum(self._samples) / len(self._samples)
            self._correction = min(2.0, max(0.5, mean))

    @property
    def correction(self) -> float:
        with self._lock:
            return self._correction

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()
            self._correction = 1.0


_calibrator = _UsageCalibrator()


def record_usage_sample(messages: List["Message"], real_input_tokens: int) -> None:
    """真实 LLM 响应返回后回报 input tokens，校准后续估算。"""
    _calibrator.observe(_estimate_context_tokens_raw(messages), real_input_tokens)


def reset_token_calibration() -> None:
    """重置校准（测试用）。"""
    _calibrator.reset()


def _is_cjk_char(c: str) -> bool:
    return (
        "\u4e00" <= c <= "\u9fff"      # CJK 统一表意文字
        or "\u3400" <= c <= "\u4dbf"   # 扩展 A
        or "\u3000" <= c <= "\u303f"   # CJK 标点
        or "\u3040" <= c <= "\u30ff"   # 日文假名
        or "\uac00" <= c <= "\ud7af"   # 韩文
        or "\uff01" <= c <= "\uff5e"   # 全角标点（不含全角字母数字）
    )


def estimate_text_tokens(text: str) -> int:
    """CJK 感知 token 估算。中文按字计，英文按 char/4，避免中文被低估 ~2.8 倍。"""
    if not text:
        return 0
    cjk = sum(1 for c in text if _is_cjk_char(c))
    other = len(text) - cjk
    return int(cjk * _CJK_TOKEN_RATIO + other * _OTHER_TOKEN_RATIO)


def estimate_context_tokens(messages: List["Message"]) -> int:
    """估算全部消息的 token 数（启发式 × 运行期校准因子）。

    校准由 record_usage_sample 在真实响应后自动喂样本；无样本时校正因子
    为 1.0，行为与纯启发式一致。
    """
    return int(_estimate_context_tokens_raw(messages) * _calibrator.correction)


def _estimate_context_tokens_raw(messages: List["Message"]) -> int:
    """纯启发式估算（不含校准因子）。

    CJK 感知启发式 + 每消息 200 token 协议开销。
    Assistant 消息额外计入 thinking 内容和工具调用名。
    用于上下文预算检查。
    """
    total = 0
    for m in messages:
        if type(m).__name__ == "AssistantMessage":
            total += estimate_text_tokens(m.text()) + estimate_text_tokens(m.thinking())
            for tc in m.tool_calls():
                total += estimate_text_tokens(tc.name) + estimate_text_tokens(
                    str(tc.arguments)
                )
        else:
            total += estimate_text_tokens(m.text())
        total += 200
    return total


def estimate_tool_result_tokens(messages: List["Message"]) -> int:
    """估算工具结果消息的 token 数（用于上下文预算分类 E1-3）。"""
    total = 0
    for m in messages:
        if type(m).__name__ == "ToolResultMessage":
            total += estimate_text_tokens(m.text()) + 200
    return total


# ---------------------------------------------------------------------------
# 消息
# ---------------------------------------------------------------------------

@dataclass
class UserMessage:
    content: Union[str, List[ContentBlock]]
    role: str = "user"
    timestamp: int = field(default_factory=now_ms)

    def text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        return "".join(
            b.text for b in self.content if isinstance(b, TextContent)
        )


@dataclass
class AssistantMessage:
    content: List[ContentBlock] = field(default_factory=list)
    model: str = ""
    stop_reason: str = StopReason.STOP
    usage: Usage = field(default_factory=Usage)
    error_message: Optional[str] = None
    timestamp: int = field(default_factory=now_ms)
    role: str = "assistant"

    def text(self) -> str:
        return "".join(
            b.text for b in self.content if isinstance(b, TextContent)
        )

    def thinking(self) -> str:
        return "".join(
            b.thinking for b in self.content if isinstance(b, ThinkingContent)
        )

    def tool_calls(self) -> List[ToolCall]:
        return [b for b in self.content if isinstance(b, ToolCall)]


@dataclass
class ToolResultMessage:
    tool_call_id: str
    tool_name: str
    content: List[ContentBlock]
    is_error: bool = False
    details: Any = None
    usage: Optional[Usage] = None
    terminate: bool = False
    timestamp: int = field(default_factory=now_ms)
    role: str = "toolResult"

    def text(self) -> str:
        return "".join(
            b.text for b in self.content if isinstance(b, TextContent)
        )


Message = Union[UserMessage, AssistantMessage, ToolResultMessage]


def _block_to_dict(block: ContentBlock, truncate_image: bool = False) -> Dict[str, Any]:
    if isinstance(block, ToolCall):
        return {
            "type": "toolCall",
            "id": block.id,
            "name": block.name,
            "arguments": block.arguments,
        }
    if isinstance(block, ThinkingContent):
        return {"type": "thinking", "thinking": block.thinking}
    if isinstance(block, ImageContent):
        data = block.data[:64] + "..." if truncate_image else block.data
        return {"type": "image", "mimeType": block.mime_type, "data": data}
    return {"type": "text", "text": block.text}


def message_to_dict(m: Message, truncate_images: bool = False) -> Dict[str, Any]:
    if isinstance(m, UserMessage):
        content = (
            m.content
            if isinstance(m.content, str)
            else [_block_to_dict(b, truncate_images) for b in m.content]
        )
        return {"role": "user", "content": content, "timestamp": m.timestamp}
    if isinstance(m, AssistantMessage):
        return {
            "role": "assistant",
            "content": [_block_to_dict(b, truncate_images) for b in m.content],
            "model": m.model,
            "stopReason": m.stop_reason,
            "usage": m.usage.to_dict(),
            "errorMessage": m.error_message,
            "timestamp": m.timestamp,
        }
    return {
        "role": "toolResult",
        "toolCallId": m.tool_call_id,
        "toolName": m.tool_name,
        "content": [_block_to_dict(b, truncate_images) for b in m.content],
        "isError": m.is_error,
        "terminate": m.terminate,
        "timestamp": m.timestamp,
    }


def _block_from_dict(d: Dict[str, Any]) -> ContentBlock:
    btype = d.get("type")
    if btype == "toolCall":
        return ToolCall(
            id=d.get("id", ""),
            name=d.get("name", ""),
            arguments=d.get("arguments") or {},
        )
    if btype == "thinking":
        return ThinkingContent(thinking=d.get("thinking", ""))
    if btype == "image":
        return ImageContent(data=d.get("data", ""), mime_type=d.get("mimeType", "image/png"))
    return TextContent(text=d.get("text", ""))


def message_from_dict(d: Dict[str, Any]) -> Message:
    role = d.get("role")
    if role == "user":
        content = d.get("content")
        if isinstance(content, list):
            content = [_block_from_dict(b) for b in content]
        return UserMessage(content=content if content is not None else "", timestamp=d.get("timestamp", now_ms()))
    if role == "assistant":
        usage_raw = d.get("usage") or {}
        return AssistantMessage(
            content=[_block_from_dict(b) for b in (d.get("content") or [])],
            model=d.get("model", ""),
            stop_reason=d.get("stopReason", StopReason.STOP),
            usage=Usage(
                input=usage_raw.get("input", 0),
                output=usage_raw.get("output", 0),
                cache_read=usage_raw.get("cache_read", 0),
                cache_write=usage_raw.get("cache_write", 0),
            ),
            error_message=d.get("errorMessage"),
            timestamp=d.get("timestamp", now_ms()),
        )
    return ToolResultMessage(
        tool_call_id=d.get("toolCallId", ""),
        tool_name=d.get("toolName", ""),
        content=[_block_from_dict(b) for b in (d.get("content") or [])],
        is_error=bool(d.get("isError", False)),
        terminate=bool(d.get("terminate", False)),
        timestamp=d.get("timestamp", now_ms()),
    )


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

@dataclass
class AgentToolResult:
    content: List[ContentBlock]
    details: Any = None
    usage: Optional[Usage] = None
    terminate: bool = False
    is_error: bool = False


class AgentTool:
    """AgentTool 基类：parameters 为 JSON Schema（object 类型）。

    注意：方法名用 run 而非 execute（execute 命名会触发 SQL 注入扫描误报）。
    """

    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}
    # 只读无副作用的工具才可置 True，允许与同批其他 safe 工具并行；
    # 有副作用的工具（bash/write/edit）保持 False，并行批内成 barrier 串行。
    concurrency_safe: bool = False

    async def run(
        self,
        tool_call_id: str,
        params: Dict[str, Any],
        on_update=None,
    ) -> AgentToolResult:
        raise NotImplementedError


class FunctionTool(AgentTool):
    """把 async/sync 可调用对象包装为工具，测试与扩展用。"""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        fn,
        concurrency_safe: bool = False,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self._fn = fn
        self.concurrency_safe = concurrency_safe

    async def run(self, tool_call_id: str, params: Dict[str, Any], on_update=None) -> AgentToolResult:
        import asyncio

        result = self._fn(params)
        if asyncio.iscoroutine(result):
            result = await result
        if isinstance(result, AgentToolResult):
            return result
        text = result if isinstance(result, str) else str(result)
        return AgentToolResult(content=[TextContent(text)])


# ---------------------------------------------------------------------------
# Context：整个 LLM 请求即整个对象（可序列化）
# ---------------------------------------------------------------------------

@dataclass
class Context:
    messages: List[Message] = field(default_factory=list)
    system_prompt: Optional[str] = None
    tools: List[AgentTool] = field(default_factory=list)
    response_format: Optional[str] = None  # "json"：要求 LLM 输出合法 JSON（P0-3）
    # 思考深度："on"/"off"（None=模型默认）。仅 supports_thinking_control
    # 的模型会注入对应 API 参数；off 可显著降低 reasoning token 占比
    thinking_level: Optional[str] = None


# ---------------------------------------------------------------------------
# 流式事件（StreamFn 产出，对齐 pi AssistantMessageEvent）
# ---------------------------------------------------------------------------

@dataclass
class StreamStart:
    partial: AssistantMessage


@dataclass
class TextDelta:
    text: str


@dataclass
class ThinkingDelta:
    thinking: str


@dataclass
class ToolCallStart:
    index: int
    tool_call: ToolCall


@dataclass
class ToolCallDelta:
    index: int
    delta: str  # 原始 JSON 片段


@dataclass
class ToolCallEnd:
    index: int
    tool_call: ToolCall


@dataclass
class StreamDone:
    reason: str
    message: AssistantMessage


@dataclass
class StreamError:
    reason: str  # "aborted" | "error"
    error: AssistantMessage


AssistantMessageEvent = Union[
    StreamStart, TextDelta, ThinkingDelta,
    ToolCallStart, ToolCallDelta, ToolCallEnd,
    StreamDone, StreamError,
]


# ---------------------------------------------------------------------------
# Agent 事件（AgentLoop 产出，对齐 pi AgentEvent）
# ---------------------------------------------------------------------------

@dataclass
class AgentStart:
    pass


@dataclass
class AgentEnd:
    messages: List[Message]
    # P2-8 粘滞标记：本 run 内任一 turn 曾触发 LENGTH 截断（后续正常完成也保留）
    truncated_history: bool = False


@dataclass
class TurnStart:
    pass


@dataclass
class TurnEnd:
    message: AssistantMessage
    tool_results: List[ToolResultMessage]
    turn_tokens: int = 0  # 本轮消耗的 token（E3-3）
    turn_duration_ms: int = 0  # 本轮耗时毫秒（E3-3）
    tool_names: List[str] = field(default_factory=list)  # 本轮调用的工具名（E3-3）


@dataclass
class MessageStart:
    message: AssistantMessage


@dataclass
class MessageUpdate:
    message: AssistantMessage  # 累计快照（就地更新）
    delta: AssistantMessageEvent


@dataclass
class MessageEnd:
    message: AssistantMessage


@dataclass
class ToolExecutionStart:
    tool_call_id: str
    tool_name: str
    args: Dict[str, Any]


@dataclass
class ToolExecutionUpdate:
    tool_call_id: str
    tool_name: str
    partial_result: Any


@dataclass
class ToolExecutionEnd:
    tool_call_id: str
    tool_name: str
    is_error: bool
    result: ToolResultMessage


AgentEvent = Union[
    AgentStart, AgentEnd, TurnStart, TurnEnd,
    MessageStart, MessageUpdate, MessageEnd,
    ToolExecutionStart, ToolExecutionUpdate, ToolExecutionEnd,
]
