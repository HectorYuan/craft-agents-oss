"""共享 HTTP 重试工具：指数退避 + jitter + Retry-After 支持。

两个 provider（openai_completions / anthropic_messages）共用此模块，
消除重复的重试逻辑。
"""
from __future__ import annotations

import asyncio
import random
from typing import Optional, Tuple

import aiohttp


# 429/5xx 之外的可重试连接错误
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


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
