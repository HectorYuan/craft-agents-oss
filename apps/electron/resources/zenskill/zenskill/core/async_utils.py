"""async 兼容助手：sync 代码路径中运行协程。

问题背景：sync 包装函数内直接 asyncio.run()，若该包装又被 async 上下文
调用（如 SkillAgent.chat → 记忆整合），在 pytest-asyncio / 运行中事件循环
内会抛 "asyncio.run() cannot be called from a running event loop"。

解法：无运行中循环时走 asyncio.run（原语义不变）；有循环时把协程丢进
独立线程用自己的事件循环跑（标准逃生舱）。CLI/TUI 顶层调用路径行为不变。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Coroutine


def run_coro_sync(coro: Coroutine[Any, Any, Any]) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()
