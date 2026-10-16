"""进程级单例状态统一重置注册表。

背景：共享 test.db 的"文件边界重置"实验（见 tests/conftest.py）实测三轮
67→5→69 波动——根因是进程级单例（router/engine/缓存）在库重建后与内存态
分叉。稳定隔离需要"库文件重置 + 全部已知单例状态重置"成对出现。

用途：
1. 测试隔离：conftest 在测试文件边界调用 reset_all()（ZENSKILL_TEST_DB_RESET=on）
2. 运行时自愈：state_doctor / 热重载场景可复用（按名重置 reset_one）

约定：resetter 必须幂等、内部 import（防循环依赖）、异常自吞（重置失败
只记 debug 日志，绝不抛出——测试路径上抛错会把隔离问题放大成收集错误）。
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Tuple

logger = logging.getLogger(__name__)

_RESETTERS: Dict[str, Callable[[], None]] = {}


def register_reset(name: str, fn: Callable[[], None]) -> None:
    _RESETTERS[name] = fn


def reset_one(name: str) -> bool:
    fn = _RESETTERS.get(name)
    if fn is None:
        return False
    try:
        fn()
        return True
    except Exception as e:  # 重置失败不放大
        logger.debug("state reset %s failed: %s", name, e)
        return False


def reset_all(exclude: Tuple[str, ...] = ()) -> List[str]:
    """执行全部重置器，返回失败名单（成功的不打扰日志）。"""
    failed: List[str] = []
    for name, fn in _RESETTERS.items():
        if name in exclude:
            continue
        try:
            fn()
        except Exception as e:
            logger.debug("state reset %s failed: %s", name, e)
            failed.append(name)
    return failed


def registered_names() -> List[str]:
    return sorted(_RESETTERS)


# ── 内置重置器 ────────────────────────────────────────────────────


def _reset_database() -> None:
    from zenskill.core.database import db

    # 长连接持有 -wal/-shm 句柄：不先关，Windows unlink 被拒、
    # Linux 残留幽灵 inode（连接复用 M1 引入，reset 必须显式握手）
    db.close_pool()
    base = db._db_path
    from pathlib import Path

    for suffix in ("", "-wal", "-shm"):
        f = Path(str(base) + suffix)
        try:
            f.unlink()
        except FileNotFoundError:
            pass
    db._initialized = False
    db._initializing = False


def _reset_skill_tools_caches() -> None:
    from zenskill.runtime.agent import skill_tools as st

    st._index_cache = None
    st._skill_cache.clear()


def _reset_skill_router() -> None:
    from zenskill.skill_router import skill_router

    skill_router._routes.clear()
    skill_router._keyword_index.clear()
    skill_router._register_builtin_skills()


def _reset_llm_config() -> None:
    from zenskill.core.llm_config import llm_config

    llm_config._config = None


def _reset_governance_touch() -> None:
    from zenskill.skills import skill_governance as sg

    sg._touch_ts.clear()


def _reset_system_registry() -> None:
    from zenskill.core.registry import SystemRegistry

    SystemRegistry.reset()  # cls._instance=None + _initialized=False


register_reset("database", _reset_database)
register_reset("skill_tools_caches", _reset_skill_tools_caches)
register_reset("skill_router", _reset_skill_router)
register_reset("llm_config", _reset_llm_config)
register_reset("governance_touch", _reset_governance_touch)
register_reset("system_registry", _reset_system_registry)
# 注意：fusion_router/routing_learner 不入重置——它们承载
# 导入期注册（TUI 视图/信号源等），文件边界清空会让后续文件拿到空注册表
# （实测 13 failed 聚类实证）；且与 DB 耦合弱，不是分叉源。
