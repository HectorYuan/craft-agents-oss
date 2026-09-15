"""陪伴事件埋点 — 记录 companion 相关交互到 mirroring 生态。"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CompanionEventRecorder:
    """记录 companion 相关事件（displayed / insight_clicked / feedback）到 event collector。"""

    def __init__(self, event_collector: Any = None) -> None:
        self._ec = event_collector

    def record_displayed(
        self, mood: str, energy_level: str, has_insight: bool
    ) -> None:
        """companion_summary 渲染时调用"""
        if not self._ec:
            return
        try:
            self._ec.record_skill_execution(
                skill_id="companion",
                task="companion_displayed",
                success=True,
                context={
                    "mood": mood,
                    "energy_level": energy_level,
                    "has_insight": has_insight,
                },
            )
        except Exception:
            pass

    def record_insight_clicked(
        self, insight_type: str, source: str = ""
    ) -> None:
        """top_insight 被点击时调用"""
        if not self._ec:
            return
        try:
            self._ec.record_skill_execution(
                skill_id="companion",
                task="insight_clicked",
                success=True,
                context={"insight_type": insight_type, "source": source},
            )
        except Exception:
            pass

    def record_feedback(self, feedback_type: str) -> None:
        """instant_feedback 触发时调用"""
        if not self._ec:
            return
        try:
            self._ec.record_skill_execution(
                skill_id="companion",
                task="feedback_triggered",
                success=True,
                context={"feedback_type": feedback_type},
            )
        except Exception:
            pass
