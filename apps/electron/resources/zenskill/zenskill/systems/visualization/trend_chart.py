"""
ZenSkill - 成长趋势 ASCII 图

将历史指标数据可视化为 ASCII 折线图，
直观展示能力成长轨迹。
"""

from __future__ import annotations

from typing import List, Dict, Optional
from dataclasses import dataclass
import time


@dataclass
class MetricPoint:
    """指标采样点"""
    timestamp: float
    interaction_count: int
    success_rate: float
    user_satisfaction: float
    avg_response_time_ms: float
    memory_usage_count: int
    level: str

    @classmethod
    def from_manifest(cls, manifest) -> "MetricPoint":
        """从 SkillManifest 创建采样点"""
        success_rate = manifest.stats.successful_executions / max(1, manifest.stats.total_interactions)
        return cls(
            timestamp=time.time(),
            interaction_count=manifest.stats.total_interactions,
            success_rate=success_rate,
            user_satisfaction=manifest.stats.user_feedback_score,
            avg_response_time_ms=manifest.stats.average_response_time_ms,
            memory_usage_count=manifest.stats.memory_usage_count,
            level=manifest.current_level.name,
        )


class TrendChartGenerator:
    """成长趋势 ASCII 图生成器"""

    # 支持的维度
    DIMENSIONS = {
        "composite": "综合能力",
        "proficiency": "熟练度",
        "stability": "稳定性",
        "satisfaction": "满意度",
        "responsiveness": "响应力",
        "memory": "记忆力",
    }

    def __init__(self, max_points: int = 50):
        """
        初始化趋势图生成器

        Args:
            max_points: 最多保留的采样点数
        """
        self.max_points = max_points
        self.metrics_history: List[MetricPoint] = []

    def add_metric_point(self, point: MetricPoint) -> None:
        """
        添加一个指标采样点

        Args:
            point: 指标采样点
        """
        self.metrics_history.append(point)

        # 超过最大点数，移除最旧的
        if len(self.metrics_history) > self.max_points:
            self.metrics_history = self.metrics_history[-self.max_points:]

    def get_value_for_dimension(self, point: MetricPoint, dimension: str) -> int:
        """
        获取指定维度的数值（0-100）

        Args:
            point: 指标采样点
            dimension: 维度名称

        Returns:
            维度数值（0-100）
        """
        if dimension == "composite":
            # 综合得分（加权平均）
            proficiency = min(100, point.interaction_count // 5)
            stability = round(point.success_rate * 100)
            satisfaction = round(point.user_satisfaction * 100)
            responsiveness = max(0, round(100 - point.avg_response_time_ms / 50))
            memory = min(100, point.memory_usage_count // 2)

            composite = (
                proficiency * 0.3
                + stability * 0.25
                + satisfaction * 0.2
                + responsiveness * 0.15
                + memory * 0.1
            )
            return round(composite)

        elif dimension == "proficiency":
            return min(100, point.interaction_count // 5)

        elif dimension == "stability":
            return round(point.success_rate * 100)

        elif dimension == "satisfaction":
            return round(point.user_satisfaction * 100)

        elif dimension == "responsiveness":
            return max(0, round(100 - point.avg_response_time_ms / 50))

        elif dimension == "memory":
            return min(100, point.memory_usage_count // 2)

        else:
            return 0

    def generate_trend_ascii(
        self,
        dimension: str = "composite",
        n_points: int = 20,
        chart_height: int = 6,
    ) -> str:
        """
        生成 ASCII 趋势图

        Args:
            dimension: 要展示的维度
            n_points: 展示的数据点数
            chart_height: 图表高度（行数）

        Returns:
            ASCII 趋势图字符串
        """
        if not self.metrics_history:
            return "暂无历史数据，继续使用以积累成长记录 🌱"

        dimension_name = self.DIMENSIONS.get(dimension, dimension)

        # 获取最近 n 个点
        points = self.metrics_history[-n_points:]
        values = [self.get_value_for_dimension(p, dimension) for p in points]

        if not values:
            return "数据不足"

        lines = []

        # 标题
        lines.append(f"📈 {dimension_name}成长趋势（最近 {len(points)} 次采样）")
        lines.append("═" * (n_points + 15))

        # 生成图表
        chart = self._generate_line_chart(values, chart_height)
        lines.extend(chart)

        # 境界变化标记
        level_changes = self._find_level_changes(points)
        if level_changes:
            lines.append("")
            lines.append("🏆 里程碑：")
            for idx, level in level_changes:
                lines.append(f"   第 {idx + 1} 次采样：晋升 {level}")

        return "\n".join(lines)

    def _generate_line_chart(self, values: List[int], height: int) -> List[str]:
        """
        生成折线图

        Args:
            values: 数据值列表
            height: 图表高度

        Returns:
            折线图行列表
        """
        lines = []
        max_val = max(values)
        min_val = min(values)
        value_range = max(max_val - min_val, 1)

        # 归一化到图表高度
        normalized = [round((v - min_val) / value_range * (height - 1)) for v in values]

        # 生成每一行
        for row in range(height - 1, -1, -1):
            # Y 轴刻度
            y_value = min_val + round(row * value_range / (height - 1))
            line = f"{y_value:4d} ┤"

            # 每个数据点
            for val in normalized:
                if val == row:
                    line += "██"
                elif val > row:
                    line += "██"
                else:
                    line += "  "

            lines.append(line)

        # X 轴基线
        x_axis = "     └" + "─" * len(values) * 2
        lines.append(x_axis)

        return lines

    def _find_level_changes(self, points: List[MetricPoint]) -> List[tuple]:
        """
        找出境界变化的位置

        Args:
            points: 指标点列表

        Returns:
            (索引, 新境界) 列表
        """
        changes = []
        if len(points) < 2:
            return changes

        prev_level = points[0].level
        for i, point in enumerate(points[1:], start=1):
            if point.level != prev_level:
                changes.append((i, point.level))
                prev_level = point.level

        return changes

    def generate_composite_trend(self, n_points: int = 20) -> str:
        """
        生成综合能力趋势图

        Args:
            n_points: 数据点数

        Returns:
            ASCII 趋势图字符串
        """
        return self.generate_trend_ascii("composite", n_points)

    def generate_all_trends_summary(self, n_points: int = 10) -> str:
        """
        生成所有维度的趋势摘要

        Args:
            n_points: 数据点数

        Returns:
            趋势摘要字符串
        """
        if not self.metrics_history:
            return "暂无历史数据 🌱"

        lines = []
        lines.append("📊 全维度成长趋势摘要")
        lines.append("═" * 35)

        for dim in ["composite", "proficiency", "stability", "satisfaction"]:
            dim_name = self.DIMENSIONS.get(dim, dim)
            points = self.metrics_history[-n_points:]
            values = [self.get_value_for_dimension(p, dim) for p in points]

            if values:
                first, last = values[0], values[-1]
                change = last - first
                change_str = f"+{change}" if change >= 0 else f"{change}"
                arrow = "↗️" if change > 0 else "↘️" if change < 0 else "➡️"

                lines.append(f"  {dim_name:4s}: {first:3d} → {last:3d} ({change_str}) {arrow}")

        return "\n".join(lines)
