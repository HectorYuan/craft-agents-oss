"""共享 HTTP 重试工具：指数退避 + jitter + Retry-After 支持。

两个 provider（openai_completions / anthropic_messages）共用此模块，
消除重复的重试逻辑。
"""
from __future__ import annotations

import asyncio
import random
import re
from typing import Optional, Tuple

import aiohttp


# 429/5xx 之外的可重试连接错误
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


# tools 参数降级判定（P1-6）：仅 HTTP 400 且错误体同时指向
# tools/function 参数与"不接受"语义时触发剥参重试。
# 429/5xx/连接错误永不触发——那类错误与 tools 无关，剥参会无故剥夺
# LLM 的工具能力。
_TOOL_PARAM_RE = re.compile(r"\b(tools?|functions?)\b", re.IGNORECASE)
_TOOL_REJECT_RE = re.compile(
    r"unsupported|not\s+support|invalid|unexpected|unknown", re.IGNORECASE
)


def should_degrade_tools(error: Optional[str]) -> bool:
    """判断错误是否为"provider 不接受 tools 参数"，可剥参降级重试。

    仅 HTTP 400 且错误体同时含工具参数词（tool/function）与拒绝语义词
    （unsupported/not support/invalid/...）时为 True。
    """
    if not error or not error.startswith("HTTP 400"):
        return False
    body = error.split(":", 1)[1] if ":" in error else error
    return bool(_TOOL_PARAM_RE.search(body) and _TOOL_REJECT_RE.search(body))


def strip_tools_from_payload(payload: dict) -> dict:
    """返回剥离 tools/tool_choice 的 payload 副本（降级为纯对话请求）。"""
    stripped = dict(payload)
    stripped.pop("tools", None)
    stripped.pop("tool_choice", None)
    return stripped


def compute_backoff(
    retry_count: int,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    retry_after: Optional[str] = None,
) -> float:
    """计算退避时间（秒），含 jitter 防惊群。

    优先使用 Retry-After header（若提供且合法），否则用指数退避。
    jitter = random uniform [0, 0.5 * delay]。
    """
    if retry_after is not None:
        try:
            wait = min(float(retry_after), max_delay)
            return wait + random.uniform(0, 0.5)
        except (TypeError, ValueError):
            pass
    delay = min(base_delay * (2 ** retry_count), max_delay)
    return delay + random.uniform(0, delay * 0.5)


async def retry_post(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict,
    payload: dict,
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
) -> Tuple[Optional[aiohttp.ClientResponse], Optional[str]]:
    """带重试的 HTTP POST。返回 (response, error_message)。

    - 成功 (200): 返回 (response, None)
    - 可重试耗尽: 返回 (None, error_message)
    - 不可重试错误: 返回 (None, error_message)

    调用方需负责关闭 response。
    """
    last_error = ""
    for attempt in range(max_retries + 1):
        try:
            resp = await session.post(url, headers=headers, json=payload)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            if attempt < max_retries:
                wait = compute_backoff(attempt, base_delay, max_delay)
                await asyncio.sleep(wait)
                continue
            return None, f"connection failed after {max_retries + 1} attempts: {last_error}"

        if resp.status == 200:
            return resp, None

        body = (await resp.text())[:500]
        status = resp.status
        retry_after = resp.headers.get("Retry-After")
        resp.close()

        if status in RETRYABLE_STATUSES and attempt < max_retries:
            wait = compute_backoff(attempt, base_delay, max_delay, retry_after)
            await asyncio.sleep(wait)
            continue

        return None, f"HTTP {status}: {body}"

    return None, f"failed after {max_retries + 1} attempts: {last_error}"
