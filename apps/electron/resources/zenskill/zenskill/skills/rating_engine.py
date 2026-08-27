"""
Skill Rating Engine (Phase 9V)

自动化 + 社区的技能质量评估体系。

评级体系:
  ⭐⭐⭐⭐⭐ Platinum (5) — 卓越品质，官方推荐
  ⭐⭐⭐⭐ Gold (4)      — 高质量，推荐使用
  ⭐⭐⭐ Silver (3)      — 质量合格，可以使用
  ⭐⭐ Bronze (2)       — 基本可用，建议谨慎
  ⭐ Experimental (1)   — 实验性，不推荐生产使用

评估维度:
  ✅ 自动化测试 (30%) — 技能包测试套件通过率
  📊 元数据完整性 (15%) — 文档、示例、变更日志
  ⭐ 用户评分 (25%) — 实际使用者的平均评分
  👥 使用量 (15%) — 活跃使用次数、留存率
  🔄 维护活跃度 (10%) — 更新频率
  🛡️ 安全审计 (5%, 必须通过) — 安全检查
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 评级常量
# ═══════════════════════════════════════════════════════════════

STAR_LEVELS = [
    (0.0,  "Experimental", "⭐"),
    (1.5,  "Bronze",       "⭐⭐"),
    (2.5,  "Silver",       "⭐⭐⭐"),
    (3.5,  "Gold",         "⭐⭐⭐⭐"),
    (4.5,  "Platinum",     "⭐⭐⭐⭐⭐"),
]

# 评估维度权重 (总和 100%)
DIMENSION_WEIGHTS = {
    "test_coverage": 0.30,
    "metadata_completeness": 0.15,
    "user_score": 0.25,
    "usage_score": 0.15,
    "maintenance_score": 0.10,
    "security_audit": 0.05,  # gate: 不通过则整体 0
}

DIMENSION_NAMES = {
    "test_coverage": "自动化测试",
    "metadata_completeness": "元数据完整性",
    "user_score": "用户评分",
    "usage_score": "使用量",
    "maintenance_score": "维护活跃度",
    "security_audit": "安全审计",
}

DIMENSION_ICONS = {
    "test_coverage": "✅",
    "metadata_completeness": "📊",
    "user_score": "⭐",
    "usage_score": "👥",
    "maintenance_score": "🔄",
    "security_audit": "🛡️",
}


# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class UserRating:
    """单个用户评分记录"""
    score: float           # 1-5
    comment: str = ""
    user: str = "anonymous"
    rated_at: str = field(default_factory=lambda: datetime.now().isoformat()[:19])


@dataclass
class SkillRating:
    """技能完整评级"""
    skill_id: str
    skill_name: str = ""

    # 各维度得分 (0-1)
    test_coverage: float = 0.0
    metadata_completeness: float = 0.0
    user_score: float = 0.0
    usage_score: float = 0.0
    maintenance_score: float = 0.0
    security_audit: float = 1.0  # 默认通过

    # 综合
    overall: float = 0.0    # 0-5
    star_level: str = "Experimental"
    star_icon: str = "⭐"

    # 用户评分
    user_rating_count: int = 0
    user_rating_avg: float = 0.0

    # 更新时间
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat()[:19])

    def compute_overall(self) -> float:
        """重新计算综合评分 0-5"""
        # 安全检查：未通过则整体 0
        if self.security_audit < 0.5:
            self.overall = 0.0
            self.star_level = "Experimental"
            self.star_icon = "⭐"
            return 0.0

        weighted = (
            self.test_coverage * DIMENSION_WEIGHTS["test_coverage"]
            + self.metadata_completeness * DIMENSION_WEIGHTS["metadata_completeness"]
            + self.user_score * DIMENSION_WEIGHTS["user_score"]
            + self.usage_score * DIMENSION_WEIGHTS["usage_score"]
            + self.maintenance_score * DIMENSION_WEIGHTS["maintenance_score"]
            + self.security_audit * DIMENSION_WEIGHTS["security_audit"]
        )

        # 映射 0-1 → 0-5
        self.overall = round(weighted * 5, 2)

        # 确定星级
        for threshold, level, icon in reversed(STAR_LEVELS):
            if self.overall >= threshold:
                self.star_level = level
                self.star_icon = icon
                break

        return self.overall

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "overall": self.overall,
            "star_level": self.star_level,
            "star_icon": self.star_icon,
            "dimensions": {
                k: {
                    "score": round(getattr(self, k, 0.0), 2),
                    "weight": DIMENSION_WEIGHTS.get(k, 0),
                    "name": DIMENSION_NAMES.get(k, k),
                    "icon": DIMENSION_ICONS.get(k, ""),
                }
                for k in DIMENSION_WEIGHTS
            },
            "user_rating_count": self.user_rating_count,
            "user_rating_avg": round(self.user_rating_avg, 2),
            "updated_at": self.updated_at,
        }


# ═══════════════════════════════════════════════════════════════
# 评级引擎
# ═══════════════════════════════════════════════════════════════

class SkillRatingEngine:
    """
    技能质量评级引擎

    职责:
    - 计算技能综合评分
    - 管理用户评分 (CRUD)
    - 持久化评级数据到 ~/.zenskill/ratings/
    - 与 SkillSearchEngine 集成
    """

    def __init__(self):
        self._ratings_dir = Path.home() / ".zenskill" / "ratings"
        self._ratings_dir.mkdir(parents=True, exist_ok=True)
        self._use_db = self._check_db_available()

    @staticmethod
    def _check_db_available() -> bool:
        """检查 SQLite 是否可用且有数据"""
        try:
            from zenskill.core.database import db
            return db.table_exists("skill_ratings")
        except Exception:
            return False

    # ── 评级计算 ──

    def rate(self, skill_id: str, skill_name: str = "") -> SkillRating:
        """
        对指定技能执行评级

        优先从 SQLite (Phase D) 读取，fallback 到文件系统。
        """
        # Phase D: 从 SQLite 快速获取
        if self._use_db:
            try:
                from zenskill.core.skill_dao import SkillDAO
                from zenskill.core.skill_profile import SkillProfile
                profile = SkillProfile.load(skill_id)
                if profile:
                    saved = SkillDAO.get_ratings(skill_id)
                    rating = SkillRating(
                        skill_id=skill_id,
                        skill_name=profile.name,
                        test_coverage=saved.get("test_coverage", 0.0) if saved else 0.0,
                        metadata_completeness=saved.get("metadata_completeness", 0.0) if saved else 0.0,
                        user_score=saved.get("user_score", 0.0) if saved else 0.0,
                        usage_score=min(profile.total_interactions / 200, 1.0),
                        maintenance_score=saved.get("maintenance_score", 0.0) if saved else 0.0,
                        security_audit=saved.get("security_audit", 1.0) if saved else 1.0,
                        overall=saved.get("overall", 0.0) if saved else 0.0,
                        star_level=saved.get("star_level", "Experimental") if saved else "Experimental",
                        star_icon=saved.get("star_icon", "⭐") if saved else "⭐",
                        user_rating_count=saved.get("user_rating_count", 0) if saved else 0,
                        user_rating_avg=saved.get("user_rating_avg", 0.0) if saved else 0.0,
                        updated_at=saved.get("updated_at", "") if saved else "",
                    )
                    # Re-compute from live data if needed
                    if saved and saved.get("user_rating_count", 0) > 0:
                        rating.user_score = rating.user_rating_avg / 5.0
                    rating.compute_overall()
                    return rating
            except Exception:
                pass

        # Fallback: 文件系统模式 (原逻辑)
        return self._rate_from_fs(skill_id, skill_name)

    def _rate_from_fs(self, skill_id: str, skill_name: str = "") -> SkillRating:
        rating = SkillRating(skill_id=skill_id, skill_name=skill_name or skill_id)

        # 1. 从已保存的评级数据加载
        saved = self._load_rating(skill_id)
        if saved:
            # 保留持久化的数据作为基础
            for dim in DIMENSION_WEIGHTS:
                if dim in saved.get("dimensions", {}):
                    setattr(rating, dim, saved["dimensions"][dim].get("score", 0.0))
            rating.user_rating_count = saved.get("user_rating_count", 0)
            rating.user_rating_avg = saved.get("user_rating_avg", 0.0)
            # user_score 从 user_rating_avg 重新计算
            if rating.user_rating_count > 0:
                rating.user_score = rating.user_rating_avg / 5.0

        # 2. 从 SkillStateManager 补充使用统计
        try:
            from zenskill.core.paths import SkillStateManager
            mgr = SkillStateManager(skill_id)
            state = mgr.load()
            usage_count = state.get("usage_count", 0)
            metrics = state.get("metrics", {})
            success_rate = metrics.get("success_rate", 0.0)

            # usage_score: 使用量 → 0-1
            rating.usage_score = min(usage_count / 200, 1.0)

            # test_coverage: 从成功率推断 (简化)
            if success_rate > 0:
                rating.test_coverage = max(rating.test_coverage, success_rate * 0.8)

        except Exception:
            pass

        # 3. 从搜索引擎索引补充
        try:
            from zenskill.skills.search_engine import SkillSearchEngine
            engine = SkillSearchEngine()
            entry = engine.get_entry(skill_id)
            if entry:
                rating.skill_name = entry.name or skill_name

                # metadata_completeness: 检查元数据字段
                completeness = 0.0
                checks = [
                    bool(entry.description),            # 1
                    bool(entry.tags),                    # 2
                    entry.version != "0.1.0",            # 3
                    bool(entry.author),                  # 4
                    entry.source != "builtin",           # 5
                ]
                completeness = sum(1 for c in checks if c) / len(checks)
                rating.metadata_completeness = max(rating.metadata_completeness, completeness)

                # maintenance_score: 从版本和来源推断
                if entry.source == "installed" or entry.source == "package":
                    rating.maintenance_score = max(rating.maintenance_score, 0.6)
                if entry.version and entry.version != "0.1.0":
                    rating.maintenance_score = max(rating.maintenance_score, 0.7)

                # 使用已有 rating 作为基础
                if entry.rating > 0:
                    existing_overall = entry.rating / 5.0
                    # 反向映射到 user_score
                    rating.user_score = max(rating.user_score, existing_overall)

        except Exception:
            pass

        # 4. 计算综合评分
        rating.compute_overall()

        # 5. 持久化
        self._save_rating(rating)

        return rating

    # ── 用户评分 ──

    def add_user_rating(self, skill_id: str, score: float,
                        comment: str = "", user: str = "anonymous") -> SkillRating:
        """添加用户评分 — 优先 DAO，fallback 文件系统"""
        if self._use_db:
            try:
                from zenskill.core.skill_dao import SkillDAO
                SkillDAO.rate(skill_id, score, comment, user)
                return self.rate(skill_id)
            except Exception:
                pass
        return self._add_user_rating_fs(skill_id, score, comment, user)

    def _add_user_rating_fs(self, skill_id: str, score: float,
                            comment: str = "", user: str = "anonymous") -> SkillRating:
        score = max(1.0, min(5.0, score))

        # 加载已有评级或创建新评级
        saved = self._load_rating(skill_id)
        skill_name = skill_id
        if saved:
            skill_name = saved.get("skill_name", skill_id)
        rating = SkillRating(skill_id=skill_id, skill_name=skill_name)

        # 从搜索引擎获取基本信息
        try:
            from zenskill.skills.search_engine import SkillSearchEngine
            engine = SkillSearchEngine()
            entry = engine.get_entry(skill_id)
            if entry:
                skill_name = entry.name
                rating.skill_name = entry.name
        except Exception:
            pass

        # 读取已有用户评分
        user_ratings = self._load_user_ratings(skill_id)
        user_ratings.append(UserRating(score=score, comment=comment, user=user))

        # 计算平均分
        scores = [r.score for r in user_ratings]
        rating.user_rating_count = len(scores)
        rating.user_rating_avg = sum(scores) / len(scores)

        # user_score = 平均分映射到 0-1
        rating.user_score = rating.user_rating_avg / 5.0

        # 从已有持久化加载其他维度（不覆盖 user_score，因为刚更新了）
        if saved:
            for dim in DIMENSION_WEIGHTS:
                if dim == "user_score":
                    continue  # 保留新计算的用户评分
                if dim in saved.get("dimensions", {}):
                    setattr(rating, dim, saved["dimensions"][dim].get("score", 0.0))

        # 持久化用户评分
        self._save_user_ratings(skill_id, user_ratings)

        # 计算综合评分并持久化
        rating.compute_overall()
        self._save_rating(rating)

        return rating

    def get_user_ratings(self, skill_id: str) -> List[Dict[str, Any]]:
        """获取用户评分列表"""
        ratings = self._load_user_ratings(skill_id)
        return [
            {
                "score": r.score,
                "comment": r.comment,
                "user": r.user,
                "rated_at": r.rated_at,
            }
            for r in ratings
        ]

    # ── 集成到搜索引擎 ──

    def enrich_search_index(self) -> Dict[str, Any]:
        """
        将评级数据回写到 SkillSearchEngine 索引

        在搜索引擎 build_index 后调用，填充每个条目的 rating 字段。
        """
        try:
            from zenskill.skills.search_engine import SkillSearchEngine
            engine = SkillSearchEngine()
            engine.build_index()
            enriched = 0

            for skill_id in list(engine._index.keys()):
                rating = self.rate(skill_id)
                entry = engine._index.get(skill_id)
                if entry:
                    entry.rating = rating.overall
                    enriched += 1

            return {"enriched": enriched}
        except Exception as e:
            return {"enriched": 0, "error": str(e)}

    # ── 持久化 ──

    def _rating_path(self, skill_id: str) -> Path:
        return self._ratings_dir / f"{skill_id}_rating.json"

    def _user_ratings_path(self, skill_id: str) -> Path:
        return self._ratings_dir / f"{skill_id}_user_ratings.jsonl"

    def _load_rating(self, skill_id: str) -> Optional[Dict[str, Any]]:
        path = self._rating_path(skill_id)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return None

    def _save_rating(self, rating: SkillRating) -> None:
        path = self._rating_path(rating.skill_id)
        try:
            path.write_text(
                json.dumps(rating.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"保存评级失败 {rating.skill_id}: {e}")

    def _load_user_ratings(self, skill_id: str) -> List[UserRating]:
        path = self._user_ratings_path(skill_id)
        results = []
        if path.exists():
            try:
                for line in path.read_text(encoding="utf-8").strip().split("\n"):
                    if line:
                        data = json.loads(line)
                        results.append(UserRating(**data))
            except Exception:
                pass
        return results

    def _save_user_ratings(self, skill_id: str, ratings: List[UserRating]) -> None:
        path = self._user_ratings_path(skill_id)
        try:
            lines = [json.dumps(asdict(r), ensure_ascii=False) for r in ratings]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception as e:
            logger.warning(f"保存用户评分失败 {skill_id}: {e}")

    # ── 批量评级 ──

    def rate_all(self) -> List[Dict[str, Any]]:
        """对所有已知技能执行评级"""
        results = []
        try:
            from zenskill.skills.search_engine import SkillSearchEngine
            engine = SkillSearchEngine()
            engine.build_index()
            for skill_id in engine._index:
                entry = engine._index[skill_id]
                rating = self.rate(skill_id, entry.name)
                results.append({
                    "skill_id": skill_id,
                    "name": entry.name,
                    "overall": rating.overall,
                    "star_level": rating.star_level,
                    "star_icon": rating.star_icon,
                })
        except Exception as e:
            logger.warning(f"批量评级失败: {e}")
        return results

    def get_rating(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """获取已保存的评级结果 — 优先 DB"""
        if self._use_db:
            try:
                return self.rate(skill_id).to_dict()
            except Exception:
                pass
        data = self._load_rating(skill_id)
        return data if data else None

    def list_ratings(self) -> List[Dict[str, Any]]:
        """列出所有已评级的技能 — 优先 DB"""
        if self._use_db:
            try:
                from zenskill.core.database import db
                with db.connect() as conn:
                    rows = conn.execute(
                        "SELECT r.skill_id, COALESCE(s.name, r.skill_id) as name, "
                        "r.overall, r.star_level, r.star_icon "
                        "FROM skill_ratings r "
                        "LEFT JOIN skill_registry s ON r.skill_id = s.skill_id"
                    ).fetchall()
                    return [dict(r) for r in rows]
            except Exception:
                pass
        # Fallback: file system
        results = []
        if not self._ratings_dir.exists():
            return results
        for f in sorted(self._ratings_dir.glob("*_rating.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append({
                    "skill_id": data.get("skill_id", f.stem.replace("_rating", "")),
                    "name": data.get("skill_name", ""),
                    "overall": data.get("overall", 0),
                    "star_level": data.get("star_level", ""),
                    "star_icon": data.get("star_icon", ""),
                })
            except Exception:
                pass
        return results
