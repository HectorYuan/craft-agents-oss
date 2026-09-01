"""流式输出服务 -- 对接 ZenSkill LLM provider / Agent Engine，零 UI 依赖。

- stream_from_llm(): 直接调 LLM provider（原始 TUI 路径）
- stream_from_agent(): 走 AgentLoop，获得工具/能力/会话管理

两者产出相同的 {type, content} dict 格式。
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _resolve_provider(model: Optional[str] = None):
    """根据模型名解析 provider，支持 model-switcher key 注入。"""
    if not model:
        return None

    try:
        from zenskill.core.llm_provider import DeepSeekLLMProvider
    except ImportError:
        return None

    # DeepSeek 模型
    if model.startswith("deepseek"):
        # 尝试从 model-switcher 获取 key
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            try:
                import sqlite3
                from pathlib import Path
                db_path = Path.home() / ".model-switch" / "modelswitcher.db"
                if db_path.exists():
                    conn = sqlite3.connect(str(db_path))
                    rows = conn.execute(
                        "SELECT es.var_value FROM key_accounts ka "
                        "JOIN env_vars es ON ka.key_env = es.var_name "
                        "WHERE ka.pool_name = 'deepseek'"
                    ).fetchall()
                    conn.close()
                    if rows:
                        key = rows[0][0]
                        os.environ["DEEPSEEK_API_KEY"] = key
            except Exception as e:
                logger.debug("从 model-switcher 获取 DeepSeek key 失败: %s", e)

        if key:
            try:
                return DeepSeekLLMProvider(api_key=key)
            except Exception as e:
                logger.debug("创建 DeepSeek provider 失败: %s", e)

    return None


async def stream_from_llm(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    on_reasoning: Optional[Callable[[str], None]] = None,
    on_token: Optional[Callable[[str], None]] = None,
) -> AsyncIterator[Dict[str, str]]:
    """从 LLM 流式获取回复。

    Yields:
        {"type": "reasoning", "content": "..."}  -- 推理/思考过程
        {"type": "content", "content": "..."}    -- 正式回复内容
        {"type": "error", "content": "..."}      -- 错误信息
        {"type": "done", "content": ""}          -- 流结束

    如果 provider 不支持流式，fallback 到非流式逐字符 yield。
    """
    try:
        from zenskill.core.llm_provider import get_llm_provider, ChatMessage
    except ImportError:
        yield {"type": "error", "content": "LLM 模块未安装"}
        yield {"type": "done", "content": ""}
        return

    provider = _resolve_provider(model) or get_llm_provider()
    if not provider:
        yield {"type": "error", "content": "LLM provider 不可用，请设置 API Key"}
        yield {"type": "done", "content": ""}
        return

    llm_messages = [ChatMessage(role=m["role"], content=m["content"]) for m in messages]

    # 优先尝试流式
    if hasattr(provider, "stream_chat"):
        try:
            async for chunk in provider.stream_chat(llm_messages):
                ctype = chunk.get("type", "content")
                ctext = chunk.get("content", "")

                if ctype == "reasoning":
                    if on_reasoning:
                        on_reasoning(ctext)
                    yield {"type": "reasoning", "content": ctext}
                elif ctype == "content":
                    if on_token:
                        on_token(ctext)
                    yield {"type": "content", "content": ctext}

            yield {"type": "done", "content": ""}
            return
        except Exception as e:
            logger.debug("流式调用失败，降级到非流式: %s", e)

    # fallback: 非流式 + 逐字符 yield
    try:
        response = await provider.chat(llm_messages)
        content = response.content
        for char in content:
            if on_token:
                on_token(char)
            yield {"type": "content", "content": char}
            await asyncio.sleep(0.008)
        yield {"type": "done", "content": ""}
    except Exception as e:
        yield {"type": "error", "content": f"LLM 调用失败: {e}"}
        yield {"type": "done", "content": ""}


async def stream_from_agent(
    user_input: str,
    history: List[Dict[str, str]],
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    with_memory: bool = False,
    with_skills: bool = False,
    max_steps: int = 5,
) -> AsyncIterator[Dict[str, str]]:
    """Agent Engine 流式输出，兼容 TUI chunk 格式。

    走 AgentLoop 路径，获得工具执行、能力注入等全部 agent 能力。

    Yields:
        {"type": "reasoning", "content": "..."}  -- 思考过程
        {"type": "content", "content": "..."}    -- 正式回复
        {"type": "tool_start", "content": "..."} -- 工具开始执行
        {"type": "tool_end", "content": "..."}   -- 工具执行完成
        {"type": "error", "content": "..."}      -- 错误
        {"type": "done", "content": ""}          -- 流结束
    """
    try:
        from zenskill.runtime.agent.providers import resolve_model, create_stream
        from zenskill.runtime.agent.agent_loop import AgentLoop, AgentLoopConfig
        from zenskill.runtime.agent.types import (
            Context, UserMessage, AssistantMessage, TextContent,
        )
        from zenskill.runtime.agent.tools import create_default_tools, DEFAULT_SYSTEM_PROMPT
        from zenskill.runtime.agent.builtin_capabilities import (
            MemoryCapability, SummaryCapability,
        )
        from zenskill.runtime.agent.capability import CapabilityHost
    except ImportError as e:
        yield {"type": "error", "content": f"Agent engine 模块未安装: {e}"}
        yield {"type": "done", "content": ""}
        return

    # 解析模型
    try:
        model_config = resolve_model(model)
    except Exception as e:
        yield {"type": "error", "content": f"模型解析失败: {e}"}
        yield {"type": "done", "content": ""}
        return

    # 构建 capability host（简化版：memory + summary）
    caps = []
    if with_memory:
        caps.append(MemoryCapability())
    caps.append(SummaryCapability())
    host = CapabilityHost(caps)

    # 构建 system prompt
    prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
    if with_skills:
        try:
            from zenskill.runtime.agent.mcp_capability import format_skills_prompt
            section = format_skills_prompt()
            if section:
                prompt = host.build_system_prompt(prompt) + "\n\n" + section
        except Exception:
            prompt = host.build_system_prompt(prompt)
    else:
        prompt = host.build_system_prompt(prompt)

    # 转换 TUI history → agent messages
    messages = []
    for m in history:
        role = m.get("role", "user")
        content = m.get("content", "")
        if not content:
            continue
        if role == "user":
            messages.append(UserMessage(content=content))
        elif role == "assistant":
            messages.append(AssistantMessage(content=[TextContent(content)]))
    messages.append(UserMessage(content=user_input))

    # 构建 context + tools
    tools = create_default_tools(".") + host.extra_tools
    context = Context(
        messages=messages,
        system_prompt=prompt,
        tools=tools,
    )

    # 创建 agent loop
    stream_fn = create_stream(model_config)
    abort_event = asyncio.Event()
    host_hooks = host.hooks()

    config = AgentLoopConfig(
        stream=stream_fn,
        model=model_config,
        max_steps=max_steps,
        abort_event=abort_event,
        **host_hooks,
    )
    loop = AgentLoop(config)

    # 运行并映射事件
    try:
        async for ev in loop.run(context):
            etype = type(ev).__name__

            if etype == "MessageUpdate":
                delta = ev.delta
                dtype = type(delta).__name__
                if dtype == "TextDelta":
                    yield {"type": "content", "content": delta.text}
                elif dtype == "ThinkingDelta":
                    yield {"type": "reasoning", "content": delta.thinking}

            elif etype == "ToolExecutionStart":
                yield {"type": "tool_start", "content": f"[{ev.tool_name}]"}

            elif etype == "ToolExecutionEnd":
                status = "fail" if ev.is_error else "ok"
                output = ev.result.text()[:80] if hasattr(ev.result, "text") else ""
                suffix = f" → {status}: {output}" if output else f" → {status}"
                yield {"type": "tool_end", "content": f"[{ev.tool_name}]{suffix}"}

            elif etype == "MessageEnd":
                msg = ev.message
                if hasattr(msg, "stop_reason") and msg.stop_reason in ("error", "aborted"):
                    yield {"type": "error", "content": msg.error_message or str(msg.stop_reason)}

        yield {"type": "done", "content": ""}

    except asyncio.CancelledError:
        abort_event.set()
        yield {"type": "done", "content": ""}
    except Exception as e:
        yield {"type": "error", "content": f"Agent engine 错误: {e}"}
        yield {"type": "done", "content": ""}
