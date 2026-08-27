"""流式输出服务 -- 对接 ZenSkill LLM provider，零 UI 依赖。

从 screens/chat.py:271 的 _stream_chat 提取，
改为 AsyncIterator[str] 接口，支持 reasoning/content 两阶段。
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
