"""治理过滤查询（G1）：dormant/archived/deleted 技能不进入注入与检索池。

降级链（保可用性优先）：
1. ZENSKILL_SKILL_FILTER=off → 直通（测试与逃生开关）；
2. skill_governance 表缺失/查询异常 → 降级查 skill_registry.is_active（0 剔除）；
3. 再异常 → 直通并记 warning。

所有消费方必须批量调用（单次调用内一次 DB 查询），禁止逐 slug 查询（防 N+1）。
"""
from __future__ import annotations

import logging
import os
from typing import Iterable, List, Set, Tuple

logger = logging.getLogger(__name__)

EXCLUDED_STATES = ("dormant", "archived", "deleted")

_CHUNK = 400  # SQLite 绑定变量上限保守分块


def _default_db():
    from zenskill.core.database import db
    return db


def filter_slugs(slugs: Iterable[str], db=None) -> Tuple[Set[str], Set[str]]:
    """批量过滤 slug，返回 (kept, excluded)。

    kept: 可进入注入/检索池的 slug 集合；
    excluded: 被治理剔除的 slug（dormant/archived/deleted，
    供 dormant_hits 唤醒提示位使用）。
    """
    wanted = set(slugs)
    if not wanted:
        return set(), set()
    if os.environ.get("ZENSKILL_SKILL_FILTER", "").strip().lower() == "off":
        return set(wanted), set()

    d = db if db is not None else _default_db()
    try:
        excluded = _filter_by_governance(wanted, d)
        return wanted - excluded, excluded
    except Exception as e:
        logger.debug("governance filter unavailable (%s), "
                     "falling back to skill_registry.is_active", e)
    try:
        excluded = _filter_by_registry(wanted, d)
        return wanted - excluded, excluded
    except Exception as e:
        logger.warning("skill governance filter degraded to passthrough: %s", e)
        return set(wanted), set()


def _in_clause(slugs: List[str]) -> str:
    return f"slug IN ({','.join('?' * len(slugs))})"


def _filter_by_governance(slugs: Set[str], d) -> Set[str]:
    with d.connect() as conn:
        hit = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='skill_governance'"
        ).fetchone()
        if hit is None:
            raise LookupError("skill_governance table missing")
        excluded: Set[str] = set()
        ordered = sorted(slugs)
        for i in range(0, len(ordered), _CHUNK):
            chunk = ordered[i:i + _CHUNK]
            rows = conn.execute(
                f"SELECT slug FROM skill_governance "
                f"WHERE state IN ({','.join('?' * len(EXCLUDED_STATES))}) "
                f"AND {_in_clause(chunk)}",
                EXCLUDED_STATES + tuple(chunk),
            ).fetchall()
            excluded.update(r[0] for r in rows)
    return excluded


def _filter_by_registry(slugs: Set[str], d) -> Set[str]:
    with d.connect() as conn:
        excluded: Set[str] = set()
        ordered = sorted(slugs)
        for i in range(0, len(ordered), _CHUNK):
            chunk = ordered[i:i + _CHUNK]
            rows = conn.execute(
                f"SELECT skill_id FROM skill_registry "
                f"WHERE is_active = 0 AND skill_id IN ({','.join('?' * len(chunk))})",
                tuple(chunk),
            ).fetchall()
            excluded.update(r[0] for r in rows)
    return excluded
