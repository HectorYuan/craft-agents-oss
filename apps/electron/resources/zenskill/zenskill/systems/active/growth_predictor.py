"""Skill growth prediction engine (8F)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ...core.paths import SkillStateManager


@dataclass
class DimensionPrediction:
    dimension: str
    current: float
    slope: float           # 每周增长率
    next_milestone: int
    days_to_milestone: int   # -1 表示无法预测
    status: str             # growing | stagnant | declining


@dataclass
class GrowthPrediction:
    skill_id: str
    level: str
    dimensions: list[DimensionPrediction] = field(default_factory=list)
    overall_slope: float = 0.0
    predicted_level_up: str = ""
    days_to_level_up: int = -1

    def format(self) -> str:
        lines = [f"🔮 技能成长预测: {self.skill_id}"]
        lines.append(f"═" * 55)
        lines.append(f"  当前境界: {self.level}")
        lines.append("")

        icons = {"growing": "📈", "stagnant": "➡️", "declining": "📉"}
        names = {"proficiency": "熟练度", "stability": "稳定性", "satisfaction": "满意度",
                 "responsiveness": "响应力", "memory": "记忆度"}

        for d in self.dimensions:
            icon = icons.get(d.status, "  ")
            eta = f"{d.days_to_milestone}天" if d.days_to_milestone > 0 else "--"
            lines.append(f"  {icon} {names.get(d.dimension, d.dimension):6s} "
                        f"{d.current:3.0f}%  "
                        f"{d.slope:+.1f}/周  达标 {d.next_milestone}%: {eta}")

        lines.append("")

        if self.predicted_level_up:
            if self.days_to_level_up > 0:
                lines.append(f"  🎯 预计 {self.days_to_level_up} 天后晋升 {self.predicted_level_up}")
            else:
                lines.append(f"  ℹ️  近期无明显晋升趋势")
        lines.append("")

        # 建议
        stagnant = [d for d in self.dimensions if d.status == "stagnant"]
        declining = [d for d in self.dimensions if d.status == "declining"]
        if declining:
            lines.append(f"  ⚠️  衰退维度: {', '.join(names.get(d.dimension, d.dimension) for d in declining)}")
            lines.append(f"  建议: 增加针对性练习")
        elif stagnant:
            lines.append(f"  💡 停滞维度: {', '.join(names.get(d.dimension, d.dimension) for d in stagnant)}")
            lines.append(f"  建议: 尝试不同的练习方式")

        return "\n".join(lines)


class GrowthPredictor:
    """技能成长预测器"""

    LEVEL_THRESHOLDS = {"NOVICE": 0, "APPRENTICE": 10, "ADEPT": 50, "EXPERT": 200, "MASTER": 500}

    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id

    def predict(self) -> GrowthPrediction:
        state = SkillStateManager(self.skill_id).load()
        level = state.get("level", "NOVICE")
        usage = state.get("usage_count", 0)

        dims = self._get_dimension_history()
        predictions = []
        total_slope = 0.0

        for dim, values in dims.items():
            pred = self._predict_dimension(dim, values)
            predictions.append(pred)
            total_slope += pred.slope

        avg_slope = total_slope / max(len(predictions), 1)
        next_level = self._next_level(level)
        days = self._estimate_level_up(usage, avg_slope, level, next_level)

        return GrowthPrediction(
            skill_id=self.skill_id,
            level=level,
            dimensions=predictions,
            overall_slope=round(avg_slope, 1),
            predicted_level_up=next_level,
            days_to_level_up=days,
        )

    def _get_dimension_history(self) -> dict[str, list[tuple[float, float]]]:
        """获取各维度的 (timestamp, score) 序列"""
        try:
            from zenskill.systems.visualization.metrics_store import MetricsStore
            store = MetricsStore(self.skill_id)
            snapshots = store.get_all_snapshots()
        except Exception:
            snapshots = []

        dims: dict[str, list[tuple[float, float]]] = {
            "proficiency": [], "stability": [], "satisfaction": [],
            "responsiveness": [], "memory": [],
        }

        for s in snapshots:
            ts = getattr(s, "timestamp", None)
            if ts is None:
                continue
            if hasattr(ts, "timestamp"):
                ts = ts.timestamp()
            elif isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts).timestamp()
                except ValueError:
                    continue
            scores = getattr(s, "ability_scores", {})
            if isinstance(scores, dict):
                for dim in dims:
                    if dim in scores:
                        dims[dim].append((float(ts), float(scores[dim])))

        return dims

    def _predict_dimension(self, dim: str, values: list[tuple[float, float]]) -> DimensionPrediction:
        if len(values) < 3:
            return DimensionPrediction(dim, 0, 0.0, 50, -1, "stagnant")

        # 简单线性回归
        n = len(values)
        ts = [v[0] for v in values]
        ys = [v[1] for v in values]
        mean_t = sum(ts) / n
        mean_y = sum(ys) / n
        num = sum((ts[i] - mean_t) * (ys[i] - mean_y) for i in range(n))
        den = sum((t - mean_t) ** 2 for t in ts)
        slope_per_second = num / den if den > 0 else 0.0
        slope_per_week = slope_per_second * 7 * 86400

        current = ys[-1]
        status = "growing" if slope_per_week > 0.5 else "stagnant" if slope_per_week > -0.5 else "declining"

        # 下一个里程碑：50, 60, 70, 80, 90, 100
        milestones = [50, 60, 70, 80, 90, 100]
        next_ms = 100
        for ms in milestones:
            if ms > current + 2:
                next_ms = ms
                break
        days = -1
        if slope_per_week > 0.01:
            weekly = max(slope_per_week, 0.01)
            days = int((next_ms - current) / weekly * 7)

        return DimensionPrediction(dim, current, round(slope_per_week, 1), next_ms, days, status)

    @classmethod
    def _next_level(cls, current: str) -> str:
        order = ["NOVICE", "APPRENTICE", "ADEPT", "EXPERT", "MASTER"]
        try:
            idx = order.index(current)
            return order[idx + 1] if idx + 1 < len(order) else ""
        except ValueError:
            return ""

    @classmethod
    def _estimate_level_up(cls, usage: int, slope: float, current: str, next_level: str) -> int:
        if not next_level or slope <= 0:
            return -1
        current_threshold = cls.LEVEL_THRESHOLDS.get(current, 0)
        next_threshold = cls.LEVEL_THRESHOLDS.get(next_level, current_threshold + 50)
        remaining = next_threshold - usage
        if remaining <= 0:
            return -1
        return max(int(remaining / max(slope, 0.01)), 1)
