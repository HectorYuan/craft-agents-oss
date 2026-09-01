"""
SkillProfile — 技能聚合视图 (Phase D: D2A-D2B)

从 SQLite 的 8+ 表中通过 JOIN 一次性获取技能的完整画像。
替代分散的 JSON/JSONL 读取，提供统一只读视图。

用法:
    profile = SkillProfile.load("zenskill-core")
    profiles = SkillProfile.list_all(category="dev")
    results = SkillProfile.search("python")
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .database import db
from .skill_dao import SkillDAO


@dataclass
class SkillProfile:
    """技能完整画像 — 从 SQLite 聚合的单次快照"""

    # ── 身份 ──
    skill_id: str = ""
    name: str = ""
    display_name: str = ""
    description: str = ""
    icon: str = "📚"

    # ── 来源 ──
    source: str = "builtin"
    source_market: str = ""
    source_url: str = ""
    source_format: str = ""
    license: str = ""
    author: str = ""
    version: str = "0.1.0"

    # ── 分类 ──
    category: str = "general"
    difficulty: str = "beginner"
    tags: List[str] = field(default_factory=list)

    # ── 修炼 ──
    level: str = "NOVICE"
    level_progress: float = 0.0
    total_interactions: int = 0
    success_count: int = 0
    fail_count: int = 0
    success_rate: float = 0.0
    last_interaction_at: str = ""

    # ── 五维能力 ──
    proficiency: float = 0.0
    stability: float = 0.0
    satisfaction: float = 0.0
    responsiveness: float = 0.0
    memory: float = 0.0

    # ── 评级 ──
    rating_overall: float = 0.0
    star_level: str = "Experimental"
    star_icon: str = "⭐"
    user_rating_avg: float = 0.0
    user_rating_count: int = 0

    # ── 元数据 ──
    is_active: bool = True
    verified: bool = False
    adapter: str = ""
    entry_point: str = ""
    created_at: str = ""
    updated_at: str = ""
    installed_at: str = ""

    def to_spec(self) -> "SkillSpec":
        """投影到 SkillSpec (Phase S)

        SkillProfile 是聚合视图, SkillSpec 是规范。
        这是 Profile → Spec 的逆向投影（有损）。
        """
        from .skill_spec import SkillSpec, CapabilitySpec
        from .skill_types import SkillType
        try:
            st = SkillType(self.category) if self.category in (
                "execution", "analysis", "creation", "coordination", "knowledge", "general"
            ) else SkillType.GENERAL
        except ValueError:
            st = SkillType.GENERAL

        return SkillSpec(
            id=self.skill_id,
            name=self.name,
            display_name=self.display_name,
            description=self.description,
            icon=self.icon,
            version=self.version,
            category=self.category,
            skill_type=st,
            difficulty=self.difficulty,
            tags=list(self.tags),
            author=self.author,
            license=self.license,
            source=self.source,
            source_market=self.source_market,
            source_url=self.source_url,
            source_format=self.source_format,
            verified=self.verified,
            adapter=self.adapter,
            entry_point=self.entry_point,
            level=self.level,
            proficiency_weight=self.proficiency,
            stability_weight=self.stability,
            satisfaction_weight=self.satisfaction,
            responsiveness_weight=self.responsiveness,
            memory_weight=self.memory,
            success_rate=self.success_rate,
            usage_count=self.total_interactions,
            last_used=self.last_interaction_at,
            is_active=self.is_active,
            created_at=self.created_at,
            updated_at=self.updated_at,
            installed_at=self.installed_at,
        )

    # ═══════════════════════════════════════════════════════
    # Factory methods
    # ═══════════════════════════════════════════════════════

    @classmethod
    def load(cls, skill_id: str) -> Optional["SkillProfile"]:
        """从 SQLite 加载技能的完整画像"""
        with db.connect() as conn:
            row = conn.execute("""
                SELECT
                    r.*,
                    c.level, c.level_progress, c.total_interactions,
                    c.success_count, c.fail_count,
                    c.last_interaction_at,
                    a.proficiency, a.stability, a.satisfaction,
                    a.responsiveness, a.memory,
                    rt.overall AS rating_overall,
                    rt.star_level, rt.star_icon,
                    rt.user_rating_avg, rt.user_rating_count
                FROM skill_registry r
                LEFT JOIN skill_cultivation c ON r.skill_id = c.skill_id
                LEFT JOIN skill_abilities a ON r.skill_id = a.skill_id
                LEFT JOIN skill_ratings rt ON r.skill_id = rt.skill_id
                WHERE r.skill_id = ?
            """, (skill_id,)).fetchone()

            if not row:
                return None
            return cls._from_row(row)

    @classmethod
    def list_all(
        cls,
        category: Optional[str] = None,
        difficulty: Optional[str] = None,
        source: Optional[str] = None,
        min_rating: float = 0.0,
        is_active: bool = True,
        limit: int = 100,
    ) -> List["SkillProfile"]:
        """列出所有技能画像"""
        query = """
            SELECT
                r.*,
                c.level, c.level_progress, c.total_interactions,
                c.success_count, c.fail_count, c.last_interaction_at,
                a.proficiency, a.stability, a.satisfaction,
                a.responsiveness, a.memory,
                rt.overall AS rating_overall,
                rt.star_level, rt.star_icon,
                rt.user_rating_avg, rt.user_rating_count
            FROM skill_registry r
            LEFT JOIN skill_cultivation c ON r.skill_id = c.skill_id
            LEFT JOIN skill_abilities a ON r.skill_id = a.skill_id
            LEFT JOIN skill_ratings rt ON r.skill_id = rt.skill_id
            WHERE r.is_active = ?
        """
        params: list = [1 if is_active else 0]

        if category:
            query += " AND r.category = ?"
            params.append(category)
        if difficulty:
            query += " AND r.difficulty = ?"
            params.append(difficulty)
        if source:
            query += " AND r.source = ?"
            params.append(source)
        if min_rating > 0:
            query += " AND rt.overall >= ?"
            params.append(min_rating)

        query += " ORDER BY r.updated_at DESC LIMIT ?"
        params.append(limit)

        with db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [cls._from_row(r) for r in rows]

    @classmethod
    def search(
        cls,
        query: str,
        category: Optional[str] = None,
        difficulty: Optional[str] = None,
        top_k: int = 20,
    ) -> List["SkillProfile"]:
        """FTS5 全文搜索技能

        优先 FTS5，回退到 LIKE 匹配。
        """
        query = query.strip()
        if not query:
            return []

        with db.connect() as conn:
            # 尝试 FTS5
            try:
                fts_query = " OR ".join(f'"{w}"' for w in query.split() if len(w) >= 2)
                if not fts_query:
                    fts_query = f'"{query}"'
                base = """
                    SELECT r.*, c.level, c.level_progress, c.total_interactions,
                           c.success_count, c.fail_count, c.last_interaction_at,
                           a.proficiency, a.stability, a.satisfaction,
                           a.responsiveness, a.memory,
                           rt.overall AS rating_overall, rt.star_level, rt.star_icon,
                           rt.user_rating_avg, rt.user_rating_count
                    FROM skill_registry r
                    JOIN skill_fts fts ON r.rowid = fts.rowid
                    LEFT JOIN skill_cultivation c ON r.skill_id = c.skill_id
                    LEFT JOIN skill_abilities a ON r.skill_id = a.skill_id
                    LEFT JOIN skill_ratings rt ON r.skill_id = rt.skill_id
                    WHERE skill_fts MATCH ? AND r.is_active = 1
                """
                params: list = [fts_query]
                if category:
                    base += " AND r.category = ?"
                    params.append(category)
                if difficulty:
                    base += " AND r.difficulty = ?"
                    params.append(difficulty)
                base += " ORDER BY rank LIMIT ?"
                params.append(top_k)
                rows = conn.execute(base, params).fetchall()
                if rows:
                    return [cls._from_row(r) for r in rows]
            except Exception:
                pass

            # 回退: LIKE
            like = f"%{query}%"
            fallback = """
                SELECT r.*, c.level, c.level_progress, c.total_interactions,
                       c.success_count, c.fail_count, c.last_interaction_at,
                       a.proficiency, a.stability, a.satisfaction,
                       a.responsiveness, a.memory,
                       rt.overall AS rating_overall, rt.star_level, rt.star_icon,
                       rt.user_rating_avg, rt.user_rating_count
                FROM skill_registry r
                LEFT JOIN skill_cultivation c ON r.skill_id = c.skill_id
                LEFT JOIN skill_abilities a ON r.skill_id = c.skill_id
                LEFT JOIN skill_ratings rt ON r.skill_id = r.skill_id
                WHERE r.is_active = 1
                  AND (r.name LIKE ? OR r.display_name LIKE ?
                       OR r.description LIKE ? OR r.tags LIKE ?)
            """
            params = [like, like, like, like]
            if category:
                fallback += " AND r.category = ?"
                params.append(category)
            if difficulty:
                fallback += " AND r.difficulty = ?"
                params.append(difficulty)
            fallback += " LIMIT ?"
            params.append(top_k)
            rows = conn.execute(fallback, params).fetchall()
            return [cls._from_row(r) for r in rows]

    @classmethod
    def get_recent_events(cls, skill_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        return SkillDAO.get_events(skill_id, limit=limit)

    @classmethod
    def get_insights(
        cls, skill_id: str, unread_only: bool = False, limit: int = 20
    ) -> List[Dict[str, Any]]:
        return SkillDAO.get_insights(skill_id, unread_only=unread_only, limit=limit)

    @classmethod
    def get_dependencies(cls, skill_id: str) -> List[Dict[str, Any]]:
        return SkillDAO.get_dependencies(skill_id)

    @classmethod
    def get_goals(cls, skill_id: str) -> List[Dict[str, Any]]:
        return SkillDAO.get_goals(skill_id)

    @classmethod
    def get_tasks(cls, skill_id: str) -> List[Dict[str, Any]]:
        return SkillDAO.get_tasks(skill_id)

    @classmethod
    def get_milestones(cls, skill_id: str) -> List[Dict[str, Any]]:
        return SkillDAO.get_milestones(skill_id)

    @classmethod
    def get_user_ratings(cls, skill_id: str) -> List[Dict[str, Any]]:
        return SkillDAO.get_user_ratings(skill_id)

    @classmethod
    def get_metrics(cls, skill_id: str, metric_type: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        return SkillDAO.get_metrics(skill_id, metric_type=metric_type, limit=limit)

    @classmethod
    def count(cls) -> int:
        rows = db.execute("SELECT count(*) as c FROM skill_registry WHERE is_active = 1")
        return rows[0]["c"] if rows else 0

    # ═══════════════════════════════════════════════════════
    # Parsing
    # ═══════════════════════════════════════════════════════

    @classmethod
    def _from_row(cls, row) -> "SkillProfile":
        d = dict(row)
        # 计算派生字段
        total = max((d.get("success_count", 0) or 0) + (d.get("fail_count", 0) or 0), 1)
        success_rate = round((d.get("success_count", 0) or 0) / total, 2)
        # 解析 tags JSON
        tags_raw = d.pop("tags", "[]")
        if isinstance(tags_raw, str):
            try:
                tags_raw = json.loads(tags_raw)
            except (json.JSONDecodeError, TypeError):
                # 仅兼容历史逗号串写入（upsert_spec 旧格式）；无逗号的非法值仍丢弃
                if "," in tags_raw:
                    tags_raw = [t.strip() for t in tags_raw.split(",") if t.strip()]
                else:
                    tags_raw = []
        if not isinstance(tags_raw, list):
            tags_raw = []

        return cls(
            skill_id=d.get("skill_id", ""),
            name=d.get("name", ""),
            display_name=d.get("display_name", ""),
            description=d.get("description", ""),
            icon=d.get("icon", "📚"),
            source=d.get("source", "builtin"),
            source_market=d.get("source_market", ""),
            source_url=d.get("source_url", ""),
            source_format=d.get("source_format", ""),
            license=d.get("license", ""),
            author=d.get("author", ""),
            version=d.get("version", "0.1.0"),
            category=d.get("category", "general"),
            difficulty=d.get("difficulty", "beginner"),
            tags=tags_raw,
            level=d.get("level", "NOVICE"),
            level_progress=d.get("level_progress", 0.0) or 0.0,
            total_interactions=d.get("total_interactions", 0) or 0,
            success_count=d.get("success_count", 0) or 0,
            fail_count=d.get("fail_count", 0) or 0,
            success_rate=success_rate,
            last_interaction_at=d.get("last_interaction_at", "") or "",
            proficiency=d.get("proficiency", 0.0) or 0.0,
            stability=d.get("stability", 0.0) or 0.0,
            satisfaction=d.get("satisfaction", 0.0) or 0.0,
            responsiveness=d.get("responsiveness", 0.0) or 0.0,
            memory=d.get("memory", 0.0) or 0.0,
            rating_overall=d.get("rating_overall", 0.0) or 0.0,
            star_level=d.get("star_level", "Experimental"),
            star_icon=d.get("star_icon", "⭐"),
            user_rating_avg=d.get("user_rating_avg", 0.0) or 0.0,
            user_rating_count=d.get("user_rating_count", 0) or 0,
            is_active=bool(d.get("is_active", 1)),
            verified=bool(d.get("verified", 0)),
            adapter=d.get("adapter", ""),
            entry_point=d.get("entry_point", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            installed_at=d.get("installed_at", ""),
        )

    # ═══════════════════════════════════════════════════════
    # 桥接 — 兼容现有 SearchEngine / RatingEngine
    # ═══════════════════════════════════════════════════════

    def to_search_entry(self):
        """转换为 SkillIndexEntry (兼容 9U 搜索引擎)"""
        try:
            from zenskill.skills.search_engine import SkillIndexEntry
        except ImportError:
            return None
        # 只传 SkillIndexEntry 已有的字段
        return SkillIndexEntry(
            skill_id=self.skill_id,
            name=self.name,
            description=self.description,
            category=self.category,
            difficulty=self.difficulty,
            tags=self.tags,
            author=self.author,
            version=self.version,
            source=self.source,
            usage_count=self.total_interactions,
            level=self.level,
            success_rate=self.success_rate,
            rating=self.rating_overall,
        )

    def to_dict(self) -> Dict[str, Any]:
        """JSON 序列化"""
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "icon": self.icon,
            "source": self.source,
            "source_market": self.source_market,
            "source_url": self.source_url,
            "category": self.category,
            "difficulty": self.difficulty,
            "tags": self.tags,
            "level": self.level,
            "level_progress": self.level_progress,
            "total_interactions": self.total_interactions,
            "success_rate": self.success_rate,
            "proficiency": self.proficiency,
            "stability": self.stability,
            "satisfaction": self.satisfaction,
            "responsiveness": self.responsiveness,
            "memory": self.memory,
            "rating_overall": self.rating_overall,
            "star_level": self.star_level,
            "star_icon": self.star_icon,
            "user_rating_avg": self.user_rating_avg,
            "user_rating_count": self.user_rating_count,
            "is_active": self.is_active,
            "verified": self.verified,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
