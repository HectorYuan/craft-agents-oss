"""Growth share card data extraction.

从现有成长引擎提取分享卡片所需数据（复用 growth_exporter 的数据源）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

LEVEL_NAMES = {
    "NOVICE": "见习者",
    "APPRENTICE": "学徒",
    "ADEPT": "熟练者",
    "EXPERT": "专家",
    "MASTER": "大师",
}

LEVEL_THRESHOLDS = [(0, "NOVICE"), (10, "APPRENTICE"), (50, "ADEPT"), (200, "EXPERT"), (500, "MASTER")]

DIMENSION_NAMES = {
    "proficiency": "熟练度",
    "stability": "稳定性",
    "satisfaction": "满意度",
    "responsiveness": "响应力",
    "memory": "记忆度",
}


class GrowthCardData:
    """从现有引擎提取分享卡片所需数据。"""

    def __init__(self, user_id: str = "default", skill_id: str = "zenskill-core"):
        self.user_id = user_id
        self.skill_id = skill_id

    def get_card_data(self) -> dict:
        """提取卡片所需全部数据。"""
        return {
            "user_id": self.user_id,
            "level": self._get_level(),
            "level_name": self._get_level_name(),
            "progress_pct": self._get_progress_pct(),
            "dimensions": self._get_dimensions(),
            "achievements": self._get_recent_achievements(n=3),
            "total_interactions": self._get_total_interactions(),
            "date": self._get_date(),
        }

    # ── 各字段提取 ──────────────────────────────────────

    def _get_state(self) -> Dict[str, Any]:
        try:
            from ..core.paths import SkillStateManager

            return SkillStateManager(self.skill_id).load() or {}
        except Exception:
            return {}

    def _get_level(self) -> str:
        state = self._get_state()
        level = state.get("level")
        if level:
            return level
        try:
            from ..core.paths import SkillStateManager

            return SkillStateManager(self.skill_id).get_level()
        except Exception:
            return "NOVICE"

    def _get_level_name(self) -> str:
        return LEVEL_NAMES.get(self._get_level(), self._get_level())

    def _get_total_interactions(self) -> int:
        return int(self._get_state().get("usage_count", 0) or 0)

    def _get_progress_pct(self) -> int:
        """当前境界到下一境界的进度百分比（MASTER 视为 100）。"""
        usage = self._get_total_interactions()
        level = self._get_level()
        for i, (threshold, name) in enumerate(LEVEL_THRESHOLDS):
            if name == level:
                if i + 1 >= len(LEVEL_THRESHOLDS):
                    return 100
                lo, hi = threshold, LEVEL_THRESHOLDS[i + 1][0]
                span = max(hi - lo, 1)
                return min(100, max(0, int((usage - lo) / span * 100)))
        return 0

    def _get_dimensions(self) -> List[Dict[str, Any]]:
        """五维能力，按分数降序，附带中文名。"""
        scores = self._get_ability_scores()
        dims = []
        for key, score in scores.items():
            if key == "composite":
                continue
            dims.append({
                "key": key,
                "name": DIMENSION_NAMES.get(key, key),
                "score": int(score) if isinstance(score, (int, float)) else 0,
            })
        dims.sort(key=lambda d: d["score"], reverse=True)
        return dims

    def _get_ability_scores(self) -> Dict[str, Any]:
        try:
            from ..systems.visualization.metrics_store import MetricsStore

            store = MetricsStore(self.skill_id)
            snapshots = store.get_all_snapshots()
            if snapshots:
                return dict(snapshots[-1].ability_scores or {})
        except Exception:
            pass
        return {}

    def _get_recent_achievements(self, n: int = 3) -> List[str]:
        """最近成就：优先庆祝型洞察，退化到里程碑/境界突破记录。"""
        achievements: List[str] = []
        try:
            from ..systems.active.proactive_insight import ProactiveInsightEngine

            for ins in ProactiveInsightEngine(self.skill_id).get_unread_insights():
                title = getattr(ins, "title", "")
                if title:
                    achievements.append(title)
        except Exception:
            pass
        if not achievements:
            for m in reversed(self._get_state().get("milestones", []) or []):
                if isinstance(m, dict) and m.get("type") == "level_up":
                    achievements.append(f"境界突破 {m.get('from', '?')} → {m.get('to', '?')}")
        return achievements[:n]

    def _get_date(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")
