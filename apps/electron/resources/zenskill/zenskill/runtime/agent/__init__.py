"""ZenSkill Agent 引擎（参照 pi coding agent 架构，M1：LLM 驱动 tool_use 循环）。

与旧 ExecutionLoop（关键词路由）共存；经 `zenskill run --engine agent` 启用。
"""
from .agent_loop import AgentLoop, AgentLoopConfig
from .types import (
    AgentEnd,
    AgentEvent,
    AgentStart,
    AgentTool,
    AgentToolResult,
    AssistantMessage,
    AssistantMessageEvent,
    ContentBlock,
    Context,
    FunctionTool,
    ImageContent,
    Message,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    StopReason,
    StreamDone,
    StreamError,
    StreamStart,
    TextContent,
    TextDelta,
    ThinkingContent,
    ThinkingDelta,
    ToolCall,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallStart,
    ToolExecutionEnd,
    ToolExecutionStart,
    ToolExecutionUpdate,
    ToolResultMessage,
    TurnEnd,
    TurnStart,
    Usage,
    UserMessage,
    message_from_dict,
    message_to_dict,
    total_usage,
)
from .validation import ToolValidationError, validate_tool_arguments
from .permission_gate import PermissionGate
from .capability import AgentCapability, CapabilityHost
from .providers import ModelConfig, build_model_config, create_stream, resolve_model
from .providers.faux import FauxStreamFn
from .tools import (
    DEFAULT_SYSTEM_PROMPT,
    BashTool,
    EditTool,
    FindTool,
    GrepTool,
    ListTool,
    ReadTool,
    WriteTool,
    create_default_tools,
)

__all__ = [
    "AgentLoop", "AgentLoopConfig",
    "AgentTool", "AgentToolResult", "FunctionTool",
    "Context", "Message", "UserMessage", "AssistantMessage", "ToolResultMessage",
    "TextContent", "ThinkingContent", "ImageContent", "ToolCall", "ContentBlock",
    "Usage", "total_usage", "message_to_dict", "message_from_dict",
    "StopReason",
    "StreamStart", "TextDelta", "ThinkingDelta", "ToolCallStart", "ToolCallDelta",
    "ToolCallEnd", "StreamDone", "StreamError", "AssistantMessageEvent",
    "AgentStart", "AgentEnd", "TurnStart", "TurnEnd", "MessageStart", "MessageUpdate",
    "MessageEnd", "ToolExecutionStart", "ToolExecutionUpdate", "ToolExecutionEnd",
    "AgentEvent",
    "ToolValidationError", "validate_tool_arguments", "PermissionGate",
    "AgentCapability", "CapabilityHost",
    "ModelConfig", "build_model_config", "create_stream", "resolve_model",
    "FauxStreamFn",
    "DEFAULT_SYSTEM_PROMPT", "BashTool", "EditTool", "ReadTool", "WriteTool",
    "GrepTool", "FindTool", "ListTool", "create_default_tools",
]
