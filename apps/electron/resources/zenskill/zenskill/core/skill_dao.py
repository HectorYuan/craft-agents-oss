"""
SkillDAO — 统一数据访问层 (Phase D: D1C-D1D)

所有持久化操作的单一入口。替代分散的 JSON/JSONL 读写。

用法:
    from zenskill.core.skill_dao import SkillDAO
    SkillDAO.upsert("my-skill", name="My Skill", category="dev")
    SkillDAO.record_event("my-skill", "reflection", "Great progress")
    SkillDAO.rate("my-skill", 4.5, comment="Solid", user="alice")
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .database import db

logger = logging.getLogger(__name__)


def _uid() -> str:
    return f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"


class SkillDAO:
    """技能数据访问对象"""

    # ═══════════════════════════════════════════════════════
    # Skill Registry CRUD
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def upsert(skill_id: str, **fields) -> None:
        """插入或更新技能注册信息

        自动处理:
        - 首次插入设置 created_at/installed_at
        - 更新时设置 updated_at
        - tags 自动 JSON 序列化
        """
        allowed = {
            "name", "display_name", "description", "icon",
            "source", "source_market", "source_url", "source_format",
            "license", "author", "version",
            "category", "difficulty", "tags",
            "install_method", "content_hash", "verified", "is_active",
            "adapter", "entry_point",
        }
        data = {k: v for k, v in fields.items() if k in allowed}
        if not data:
            return

        if "tags" in data and isinstance(data["tags"], list):
            data["tags"] = json.dumps(data["tags"], ensure_ascii=False)

        # 版本变化时自动记录历史 (P2-3)
        if "version" in data:
            try:
                SkillDAO.record_version(
                    skill_id,
                    data["version"],
                    source_url=data.get("source_url", ""),
                    content_hash=data.get("content_hash", ""),
                    only_if_changed=True,
                )
            except Exception:
                pass

        # 列名来自调用方 kwargs，插入前以白名单硬校验（标识符防注入）
        unexpected = set(data) - allowed
        if unexpected:
            raise ValueError(f"Invalid skill_registry columns: {sorted(unexpected)}")

        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        values = list(data.values())

        set_clause = ", ".join(f"{k} = excluded.{k}" for k in data)

        db.execute(f"""
            INSERT INTO skill_registry (skill_id, {cols})
            VALUES (?, {placeholders})
            ON CONFLICT(skill_id) DO UPDATE SET
                {set_clause},
                updated_at = datetime('now')
        """, [skill_id] + values)

    @staticmethod
    def delete(skill_id: str) -> bool:
        """删除技能 (CASCADE 清除所有关联数据)"""
        with db.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM skill_registry WHERE skill_id = ?", (skill_id,)
            )
            return cursor.rowcount > 0

    @staticmethod
    def get(skill_id: str) -> Optional[Dict[str, Any]]:
        """获取技能注册信息"""
        with db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM skill_registry WHERE skill_id = ?", (skill_id,)
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def list_all(
        category: Optional[str] = None,
        difficulty: Optional[str] = None,
        source: Optional[str] = None,
        is_active: bool = True,
    ) -> List[Dict[str, Any]]:
        """列出所有技能"""
        query = "SELECT * FROM skill_registry WHERE is_active = ?"
        params: list = [1 if is_active else 0]
        if category:
            query += " AND category = ?"
            params.append(category)
        if difficulty:
            query += " AND difficulty = ?"
            params.append(difficulty)
        if source:
            query += " AND source = ?"
            params.append(source)
        query += " ORDER BY updated_at DESC"
        with db.connect() as conn:
            return [dict(r) for r in conn.execute(query, params).fetchall()]

    @staticmethod
    def exists(skill_id: str) -> bool:
        rows = db.execute(
            "SELECT 1 FROM skill_registry WHERE skill_id = ?", (skill_id,)
        )
        return len(rows) > 0

    # ═══════════════════════════════════════════════════════
    # Events
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def record_event(
        skill_id: str,
        action: str,
        content: str = "",
        success: bool = True,
        duration_ms: float = 0.0,
        tags: str = "",
        metadata: Optional[Dict] = None,
    ) -> int:
        """记录交互事件 → 自动更新 cultivation 统计 (单事务)"""
        with db.connect() as conn:
            cursor = conn.execute("""
                INSERT INTO skill_events (skill_id, action, content, success, duration_ms, tags, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (skill_id, action, content, int(success), duration_ms, tags,
                  json.dumps(metadata or {}, ensure_ascii=False)))
            event_id = cursor.lastrowid

            conn.execute("""
                INSERT INTO skill_cultivation (skill_id, total_interactions, success_count,
                    fail_count, last_interaction_at)
                VALUES (?, 1, ?, ?, datetime('now'))
                ON CONFLICT(skill_id) DO UPDATE SET
                    total_interactions = total_interactions + 1,
                    success_count = success_count + ?,
                    fail_count = fail_count + ?,
                    last_interaction_at = datetime('now'),
                    updated_at = datetime('now')
            """, (skill_id, int(success), int(not success), int(success), int(not success)))

            return event_id

    @staticmethod
    def get_events(
        skill_id: str, limit: int = 20, action: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM skill_events WHERE skill_id = ?"
        params: list = [skill_id]
        if action:
            query += " AND action = ?"
            params.append(action)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return db.execute(query, params)

    @staticmethod
    def get_event_count(skill_id: str) -> int:
        rows = db.execute(
            "SELECT count(*) as c FROM skill_events WHERE skill_id = ?", (skill_id,)
        )
        return rows[0]["c"] if rows else 0

    # ═══════════════════════════════════════════════════════
    # Cultivation
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def get_cultivation(skill_id: str) -> Optional[Dict[str, Any]]:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM skill_cultivation WHERE skill_id = ?", (skill_id,)
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def update_cultivation(skill_id: str, **fields) -> None:
        allowed = {"level", "level_progress", "avg_duration_ms"}
        data = {k: v for k, v in fields.items() if k in allowed}
        if not data:
            return
        # 固定列全量 UPDATE（COALESCE 保留未指定列），无动态 SQL 拼接
        db.execute(
            """
            UPDATE skill_cultivation SET
                level = COALESCE(?, level),
                level_progress = COALESCE(?, level_progress),
                avg_duration_ms = COALESCE(?, avg_duration_ms),
                updated_at = datetime('now')
            WHERE skill_id = ?
            """,
            (
                data.get("level"),
                data.get("level_progress"),
                data.get("avg_duration_ms"),
                skill_id,
            ),
        )

    # ═══════════════════════════════════════════════════════
    # Abilities
    # ═══════════════════════════════════════════════════════

    _ABILITY_SQL = (
        "INSERT INTO skill_abilities "
        "(skill_id, proficiency, stability, satisfaction, responsiveness, memory) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(skill_id) DO UPDATE SET "
        "proficiency = excluded.proficiency, "
        "stability = excluded.stability, "
        "satisfaction = excluded.satisfaction, "
        "responsiveness = excluded.responsiveness, "
        "memory = excluded.memory, "
        "updated_at = datetime('now')"
    )

    @classmethod
    def upsert_abilities(cls, skill_id: str, **scores) -> None:
        """更新五维能力（固定列全量 upsert，无动态 SQL 拼接）"""
        dims = ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]
        data = {k: v for k, v in scores.items() if k in dims}
        if not data:
            return
        db.execute(cls._ABILITY_SQL, (
            skill_id,
            data.get("proficiency", 0.2),
            data.get("stability", 0.2),
            data.get("satisfaction", 0.2),
            data.get("responsiveness", 0.2),
            data.get("memory", 0.2),
        ))

    @staticmethod
    def get_abilities(skill_id: str) -> Optional[Dict[str, Any]]:
        rows = db.execute(
            "SELECT * FROM skill_abilities WHERE skill_id = ?", (skill_id,)
        )
        return rows[0] if rows else None

    # ═══════════════════════════════════════════════════════
    # Ratings
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def rate(
        skill_id: str, score: float, comment: str = "", user: str = "anonymous"
    ) -> None:
        """给技能打分 → 自动更新 user_ratings + skill_ratings"""
        score = max(1.0, min(5.0, score))
        with db.connect() as conn:
            conn.execute("""
                INSERT INTO user_ratings (skill_id, score, comment, user_name)
                VALUES (?, ?, ?, ?)
            """, (skill_id, score, comment, user))

            row = conn.execute("""
                SELECT AVG(score) AS avg, COUNT(*) AS cnt
                FROM user_ratings WHERE skill_id = ?
            """, (skill_id,)).fetchone()

            conn.execute("""
                INSERT INTO skill_ratings (skill_id, user_score, user_rating_count, user_rating_avg)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(skill_id) DO UPDATE SET
                    user_score = excluded.user_score,
                    user_rating_count = excluded.user_rating_count,
                    user_rating_avg = excluded.user_rating_avg,
                    updated_at = datetime('now')
            """, (skill_id, (row["avg"] or 0) / 5.0, row["cnt"], round(row["avg"] or 0, 2)))

    @staticmethod
    def get_ratings(skill_id: str) -> Optional[Dict[str, Any]]:
        rows = db.execute(
            "SELECT * FROM skill_ratings WHERE skill_id = ?", (skill_id,)
        )
        return rows[0] if rows else None

    @staticmethod
    def get_user_ratings(skill_id: str) -> List[Dict[str, Any]]:
        return db.execute(
            "SELECT * FROM user_ratings WHERE skill_id = ? ORDER BY rated_at DESC",
            (skill_id,),
        )

    @staticmethod
    def update_rating_dimensions(skill_id: str, **dimensions) -> None:
        """更新评级维度 (test_coverage, metadata_completeness, ...)"""
        allowed = {
            "test_coverage", "metadata_completeness", "user_score",
            "usage_score", "maintenance_score", "security_audit",
            "overall", "star_level", "star_icon",
        }
        data = {k: v for k, v in dimensions.items() if k in allowed}
        if not data:
            return
        set_clause = ", ".join(f"{k} = ?" for k in data)
        db.execute(
            f"INSERT INTO skill_ratings (skill_id, {', '.join(data.keys())}) "
            f"VALUES (?, {', '.join('?' for _ in data)}) "
            f"ON CONFLICT(skill_id) DO UPDATE SET {set_clause}, updated_at = datetime('now')",
            [skill_id] + list(data.values()),
        )

    # ═══════════════════════════════════════════════════════
    # Dependencies
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def add_dependency(
        skill_id: str,
        dep_skill_id: str,
        dep_type: str = "prerequisite",
        strength: float = 0.5,
        dep_version: str = "",
    ) -> None:
        db.execute("""
            INSERT OR REPLACE INTO skill_dependencies
                (skill_id, dep_skill_id, dep_type, dep_version, strength)
            VALUES (?, ?, ?, ?, ?)
        """, (skill_id, dep_skill_id, dep_type, dep_version, strength))

    @staticmethod
    def get_dependencies(skill_id: str) -> List[Dict[str, Any]]:
        return db.execute("""
            SELECT d.*, r.name AS dep_name, r.category AS dep_category
            FROM skill_dependencies d
            JOIN skill_registry r ON d.dep_skill_id = r.skill_id
            WHERE d.skill_id = ?
            ORDER BY d.strength DESC
        """, (skill_id,))

    @staticmethod
    def get_dependencies_raw(skill_id: str) -> List[Dict[str, Any]]:
        """不含 JOIN 的原始依赖边（依赖解析器用于检测未注册依赖）"""
        return db.execute(
            "SELECT * FROM skill_dependencies WHERE skill_id = ?", (skill_id,)
        )

    # ═══════════════════════════════════════════════════════
    # Version History (P2-3)
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def record_version(
        skill_id: str,
        version: str,
        source_url: str = "",
        content_hash: str = "",
        only_if_changed: bool = False,
    ) -> None:
        """记录版本历史

        only_if_changed=True 时，与最新历史记录或当前注册版本相同则跳过
        """
        with db.connect() as conn:
            if only_if_changed:
                latest = conn.execute(
                    """
                    SELECT version FROM skill_version_history
                    WHERE skill_id = ? ORDER BY id DESC LIMIT 1
                    """,
                    (skill_id,),
                ).fetchone()
                if latest and latest["version"] == version:
                    return
                if not latest:
                    current = conn.execute(
                        "SELECT version FROM skill_registry WHERE skill_id = ?",
                        (skill_id,),
                    ).fetchone()
                    if current and current["version"] == version:
                        return

            conn.execute(
                """
                INSERT INTO skill_version_history
                    (skill_id, version, source_url, content_hash)
                VALUES (?, ?, ?, ?)
                """,
                (skill_id, version, source_url, content_hash),
            )

    @staticmethod
    def get_version_history(skill_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """版本历史（新在前）"""
        return db.execute(
            """
            SELECT * FROM skill_version_history WHERE skill_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (skill_id, limit),
        )

    @staticmethod
    def remove_dependency(skill_id: str, dep_skill_id: str) -> None:
        db.execute(
            "DELETE FROM skill_dependencies WHERE skill_id = ? AND dep_skill_id = ?",
            (skill_id, dep_skill_id),
        )

    # ═══════════════════════════════════════════════════════
    # Milestones
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def add_milestone(
        skill_id: str, level: str, description: str = "", unlocked_abilities: Optional[List[str]] = None
    ) -> int:
        with db.connect() as conn:
            cursor = conn.execute("""
                INSERT INTO skill_milestones (skill_id, level, achieved_at, description, unlocked_abilities)
                VALUES (?, ?, datetime('now'), ?, ?)
            """, (skill_id, level, description, json.dumps(unlocked_abilities or [])))
            return cursor.lastrowid

    @staticmethod
    def get_milestones(skill_id: str) -> List[Dict[str, Any]]:
        return db.execute(
            "SELECT * FROM skill_milestones WHERE skill_id = ? ORDER BY achieved_at",
            (skill_id,),
        )

    # ═══════════════════════════════════════════════════════
    # Goals
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def add_goal(skill_id: str, dimension: str, target: float) -> int:
        with db.connect() as conn:
            cursor = conn.execute("""
                INSERT INTO skill_goals (skill_id, dimension, target)
                VALUES (?, ?, ?)
            """, (skill_id, dimension, target))
            return cursor.lastrowid

    @staticmethod
    def complete_goal(goal_id: int) -> None:
        db.execute(
            "UPDATE skill_goals SET status='completed', completed_at=datetime('now') WHERE goal_id=?",
            (goal_id,),
        )

    @staticmethod
    def get_goals(skill_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM skill_goals WHERE skill_id = ?"
        params: list = [skill_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        return db.execute(query, params)

    # ═══════════════════════════════════════════════════════
    # Insights
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def add_insight(
        skill_id: str, type_: str, title: str, description: str = "", priority: str = "medium"
    ) -> int:
        with db.connect() as conn:
            cursor = conn.execute("""
                INSERT INTO skill_insights (skill_id, type, title, description, priority)
                VALUES (?, ?, ?, ?, ?)
            """, (skill_id, type_, title, description, priority))
            return cursor.lastrowid

    @staticmethod
    def mark_insight_read(insight_id: int) -> None:
        db.execute("UPDATE skill_insights SET is_read=1 WHERE insight_id=?", (insight_id,))

    @staticmethod
    def get_insights(
        skill_id: str, unread_only: bool = False, limit: int = 20
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM skill_insights WHERE skill_id = ?"
        params: list = [skill_id]
        if unread_only:
            query += " AND is_read = 0"
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return db.execute(query, params)

    # ═══════════════════════════════════════════════════════
    # Tasks
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def add_task(
        skill_id: str, title: str, description: str = "", difficulty: str = "easy"
    ) -> int:
        with db.connect() as conn:
            cursor = conn.execute("""
                INSERT INTO skill_tasks (skill_id, title, description, difficulty)
                VALUES (?, ?, ?, ?)
            """, (skill_id, title, description, difficulty))
            return cursor.lastrowid

    @staticmethod
    def complete_task(task_id: int, rating: float = 0.0) -> None:
        db.execute(
            "UPDATE skill_tasks SET status='completed', rating=?, completed_at=datetime('now') WHERE task_id=?",
            (rating, task_id),
        )

    @staticmethod
    def get_tasks(skill_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM skill_tasks WHERE skill_id = ?"
        params: list = [skill_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        return db.execute(query, params)

    # ═══════════════════════════════════════════════════════
    # Metrics
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def record_metric(skill_id: str, metric_type: str, metric_data: dict) -> int:
        with db.connect() as conn:
            cursor = conn.execute("""
                INSERT INTO skill_metrics (skill_id, metric_type, metric_data)
                VALUES (?, ?, ?)
            """, (skill_id, metric_type, json.dumps(metric_data, ensure_ascii=False)))
            return cursor.lastrowid

    @staticmethod
    def get_metrics(
        skill_id: str, metric_type: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM skill_metrics WHERE skill_id = ?"
        params: list = [skill_id]
        if metric_type:
            query += " AND metric_type = ?"
            params.append(metric_type)
        query += " ORDER BY sampled_at DESC LIMIT ?"
        params.append(limit)
        return db.execute(query, params)

    # ═══════════════════════════════════════════════════════
    # Batch operations
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def batch_record_events(events: List[Tuple]) -> None:
        """批量记录事件 [(skill_id, action, content, success, duration_ms), ...]"""
        with db.connect() as conn:
            conn.executemany("""
                INSERT INTO skill_events (skill_id, action, content, success, duration_ms)
                VALUES (?, ?, ?, ?, ?)
            """, events)

    @staticmethod
    def batch_upsert_skills(skills: List[Dict]) -> None:
        """批量注册技能"""
        for s in skills:
            SkillDAO.upsert(s["skill_id"], **{k: v for k, v in s.items() if k != "skill_id"})

    # ═══════════════════════════════════════════════════════
    # SkillSpec 全量持久化 (Phase S5)
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def upsert_spec(spec: "SkillSpec") -> bool:
        """以 SkillSpec 为中心的全量持久化

        一次调用写入:
        - skill_registry (身份/分类/来源)
        - skill_cultivation (等级/统计)
        - skill_abilities (五维权重)
        - skill_dependencies (前置依赖)
        - skill_tasks (练习任务)

        Args:
            spec: SkillSpec 实例

        Returns:
            True 如果全部成功
        """
        try:
            # 1. Registry（tags 传 list，upsert 内部统一 JSON 序列化）
            verified_int = 1 if spec.verified else 0
            active_int = 1 if spec.is_active else 0

            SkillDAO.upsert(
                spec.id,
                name=spec.name,
                display_name=spec.display_name,
                description=spec.description,
                icon=spec.icon,
                version=spec.version,
                category=spec.category,
                difficulty=spec.difficulty,
                tags=spec.tags or [],
                author=spec.author,
                source=spec.source,
                source_market=spec.source_market,
                source_url=spec.source_url,
                source_format=spec.source_format,
                license=spec.license,
                content_hash=spec.content_hash,
                verified=verified_int,
                is_active=active_int,
                adapter=spec.adapter,
                entry_point=spec.entry_point,
            )

            # 2. Cultivation — 确保记录存在
            existing = SkillDAO.get_cultivation(spec.id)
            if not existing:
                db.execute("""
                    INSERT INTO skill_cultivation (skill_id, level, total_interactions,
                        success_count, fail_count, last_interaction_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (spec.id, spec.level or "NOVICE", spec.usage_count or 0,
                      int(spec.usage_count * spec.success_rate) if spec.usage_count else 0,
                      int(spec.usage_count * (1 - spec.success_rate)) if spec.usage_count else 0,
                      spec.last_used or None))
            else:
                SkillDAO.update_cultivation(spec.id, level=spec.level)

            # 3. Abilities (五维)
            if any([spec.proficiency_weight != 0.2, spec.stability_weight != 0.2,
                    spec.satisfaction_weight != 0.2, spec.responsiveness_weight != 0.2,
                    spec.memory_weight != 0.2]) or True:  # 总是写入确保记录存在
                SkillDAO.upsert_abilities(
                    spec.id,
                    proficiency=spec.proficiency_weight,
                    stability=spec.stability_weight,
                    satisfaction=spec.satisfaction_weight,
                    responsiveness=spec.responsiveness_weight,
                    memory=spec.memory_weight,
                )

            # 4. Dependencies（支持 "dep-id@>=1.2" 版本约束语法）
            for dep in spec.prerequisites:
                dep_id, _, constraint = dep.partition("@")
                if SkillDAO.exists(dep_id):
                    SkillDAO.add_dependency(
                        spec.id, dep_id, "requires", dep_version=constraint
                    )

            # 5. Practice tasks（练习任务属于 skill_tasks，而非 skill_goals 的能力维度）
            for task in spec.practice_tasks:
                task_desc = task.get("description", "")
                if not task_desc:
                    continue
                try:
                    SkillDAO.add_task(
                        spec.id,
                        title=task_desc[:100],
                        description=task_desc,
                        difficulty=task.get("level", "easy"),
                    )
                except Exception:
                    pass

            logger.info(f"SkillSpec persisted: {spec.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to persist SkillSpec {spec.id}: {e}")
            return False
