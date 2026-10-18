"""记忆体系 MCP 工具（P2-S1）— 三层暴露 + 规则式三元组富化。

独立文件模式：全部实现 + register_memory_tools(registry) 在此，
registry.py 仅加 2 行（import + 调用），避开并行线活跃修改区。

工具面（5 个）:
- memory_stats             三层计数 + 容量告警（near_limit）
- memory_semantic_query    semantic facts 检索（关键词/entity）
- memory_consolidate       enrich_and_consolidate（episodic → 补三元组 → semantic）
- memory_session_reminders CrossSession 回忆卡片（"N 天前你讨论过…"）
- memory_sessions_index    跨会话索引摘要（sessions/clusters/links）

设计要点（见 docs/p2_memory_three_layers_plan.md）:
- F1 修正: semantic 0 条是结构性空转（episodes 无三元组 metadata）——
  enrich_and_consolidate 规则式生成三元组后再走原 consolidate
- F3 确认: CrossSessionMemory 已有真实索引（372 sessions/125 clusters）
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_EPISODIC_NEAR_LIMIT_RATIO = 0.9


# ── 三元组富化（F1 核心修正）──

def _extract_triplet(ep: dict, default_skill_id: str) -> dict | None:
    """规则式三元组：从 episode 平面字段生成 (subject, predicate, object)。

    语义：'某技能 在某动作中 做了什么（结果如何）'
    确定性规则，无 LLM 依赖。
    """
    content = str(ep.get("content") or "").strip()
    if not content or len(content) < 4:
        return None
    return {
        "subject": ep.get("skill_id") or default_skill_id,
        "predicate": str(ep.get("action") or "general")[:60],
        "object": content[:200],
    }


def _episode_signature(triplet: dict) -> str:
    return json.dumps(triplet, sort_keys=True, ensure_ascii=False)


async def enrich_and_consolidate(skill_id: str = "zenskill-core",
                                 top_n: int = 50) -> dict:
    """在 MetaMemory 的 episodic 层（桥接后的 988 条）就地补三元组 → consolidate。

    数据通路：MetaMemory 初始化时 _bridge_if_empty 桥接 SkillStateManager episodes
    → MemoryItem（metadata 空）→ 本函数对 MemoryItem.metadata 就地补三元组
    → mm.consolidate() 只升华有三元组的条目。

    幂等：同 (subject, predicate, object) 去重；
    SemanticMemory.store 对已存在 fact 提升置信度而非重复插入。
    """
    from ..memory.meta_memory import MetaMemory

    mm = MetaMemory(skill_id=skill_id)
    episodes = list(mm.episodic._episodes.values())
    if not episodes:
        return {"enriched": 0, "consolidated": 0, "reason": "episodic empty"}

    # 候选排序：success 加权 + recency（列表尾部更新），取 top_n
    scored = []
    for i, item in enumerate(episodes):
        score = 1.0 + i / max(1, len(episodes))  # bridge 按序追加，尾部最新
        scored.append((score, i, item))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    candidates = [item for _, _, item in scored[:top_n]]

    # 就地补三元组 metadata + 去重
    enriched = 0
    seen_signatures: set[str] = set()
    for item in candidates:
        # tags 里第一个非 "bridged" 且非纯数字的作为动作语义
        non_bridge = [t for t in (item.tags or set())
                      if t != "bridged" and not t.isdigit()]
        action_tag = sorted(non_bridge)[0] if non_bridge else "general"
        ep_like = {
            "skill_id": skill_id,
            "action": action_tag,
            "content": item.content,
        }
        triplet = _extract_triplet(ep_like, skill_id)
        if not triplet:
            continue
        sig = _episode_signature(triplet)
        if sig in seen_signatures:
            continue
        seen_signatures.add(sig)
        item.metadata = {**(item.metadata or {}), **triplet}
        item.importance = max(item.importance, 0.7)
        enriched += 1

    consolidated = await mm.consolidate()
    return {"enriched": enriched, "consolidated": consolidated}


# ── MCP 工具实现 ──

def _memory_stats(a: dict[str, Any]) -> Any:
    from ..memory.meta_memory import MetaMemory

    skill_id = str(a.get("skill_id") or "zenskill-core")
    mm = MetaMemory(skill_id=skill_id)
    stats = mm.get_stats()
    episodic_count = stats.get("episodic", {}).get("count", 0)
    capacity = stats.get("episodic", {}).get("capacity", 1000)
    near_limit = capacity > 0 and episodic_count / capacity > _EPISODIC_NEAR_LIMIT_RATIO
    return {
        "working": stats.get("working", {}),
        "episodic": {**stats.get("episodic", {}), "near_limit": near_limit},
        "semantic": stats.get("semantic", {}),
        "skill_id": skill_id,
    }


def _memory_semantic_query(a: dict[str, Any]) -> Any:
    from ..memory.semantic_memory import SemanticMemory

    skill_id = str(a.get("skill_id") or "zenskill-core")
    sm = SemanticMemory(skill_id=skill_id)
    query = str(a.get("query") or "").strip()
    limit = int(a.get("limit", 20) or 20)
    facts = list(sm._facts.values())
    if query:
        q = query.lower()
        facts = [f for f in facts
                 if q in f.subject.lower() or q in f.predicate.lower()
                 or q in f.object.lower()]
    facts.sort(key=lambda f: f.confidence, reverse=True)
    return {"count": len(facts), "facts": [
        {"subject": f.subject, "predicate": f.predicate,
         "object": f.object, "confidence": f.confidence}
        for f in facts[:limit]
    ]}


def _memory_consolidate(a: dict[str, Any]) -> Any:
    skill_id = str(a.get("skill_id") or "zenskill-core")
    top_n = int(a.get("top_n", 50) or 50)
    import asyncio
    result = asyncio.run(enrich_and_consolidate(skill_id=skill_id, top_n=top_n))
    return result


def _memory_session_reminders(a: dict[str, Any]) -> Any:
    from ..memory.cross_session import CrossSessionMemory

    window_days = int(a.get("window_days", 7) or 7)
    csm = CrossSessionMemory()
    reminders = csm.get_reminders(window_days=window_days)
    return {"count": len(reminders), "reminders": reminders[:20]}


def _memory_sessions_index(a: dict[str, Any]) -> Any:
    from ..memory.cross_session import CrossSessionMemory

    force = bool(a.get("force", False))
    csm = CrossSessionMemory()
    summary = csm.build_index(force=force)
    return summary


def register_memory_tools(registry) -> None:
    """registry.build_default_registry() 尾部调用（2 行接线）。"""
    registry.register(
        "memory_stats",
        "三层记忆统计：working/episodic/semantic 计数与容量（episodic 接近上限时 near_limit 告警）",
        _memory_stats,
        {"type": "object", "properties": {
            "skill_id": {"type": "string", "description": "技能 ID，默认 zenskill-core"},
        }},
    )
    registry.register(
        "memory_semantic_query",
        "语义记忆（facts 三元组）检索：按关键词过滤 subject/predicate/object",
        _memory_semantic_query,
        {"type": "object", "properties": {
            "query": {"type": "string", "description": "关键词（空 = 全量）"},
            "limit": {"type": "integer", "description": "返回数量，默认 20"},
            "skill_id": {"type": "string"},
        }},
    )
    registry.register(
        "memory_consolidate",
        "记忆升华：规则式三元组富化 top-N episodes 后走 consolidate（episodic→semantic）",
        _memory_consolidate,
        {"type": "object", "properties": {
            "skill_id": {"type": "string"},
            "top_n": {"type": "integer", "description": "富化条数，默认 50"},
        }},
    )
    registry.register(
        "memory_session_reminders",
        "跨会话回忆卡片：'N 天前你讨论过…'（基于话题聚类与 session links）",
        _memory_session_reminders,
        {"type": "object", "properties": {
            "window_days": {"type": "integer", "description": "回顾窗口天数，默认 7"},
        }},
    )
    registry.register(
        "memory_sessions_index",
        "跨会话记忆索引：session/cluster/link 计数与项目清单（force 重建索引）",
        _memory_sessions_index,
        {"type": "object", "properties": {
            "force": {"type": "boolean", "description": "强制重建索引"},
        }},
    )
