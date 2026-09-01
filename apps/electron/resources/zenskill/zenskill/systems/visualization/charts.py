"""
ZenSkill - 高级 ASCII 图表生成器

提供精美的纯文本数据可视化：
- 真正的折线图
- 火花线（迷你趋势）
- 境界进度条（带里程碑标记）
- 增强型五维雷达图（带变化对比）
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any


class ASCIICharts:
    """ASCII 图表生成器"""

    # 火花线字符集（从低到高）
    SPARK_CHARS = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

    @classmethod
    def line_chart(
        cls,
        values: List[int],
        height: int = 6,
        width: Optional[int] = None,
        title: str = "趋势图",
        show_axis: bool = True,
    ) -> str:
        """
        生成真正的 ASCII 折线图

        Args:
            values: 数据值列表
            height: 图表高度（行数）
            width: 图表宽度（列数，默认自动）
            title: 图表标题
            show_axis: 是否显示坐标轴

        Returns:
            ASCII 折线图字符串
        """
        if not values:
            return "暂无数据"

        # 边界检查
        if not isinstance(height, int) or height < 2:
            height = 6
        if not isinstance(title, str) or not title:
            title = "趋势图"

        n_points = len(values)
        max_val = max(values)
        min_val = min(values)
        value_range = max(max_val - min_val, 1)

        lines = []

        # 标题
        lines.append(f"📈 {title}（最近 {n_points} 采样）")
        lines.append("═" * (n_points * 2 + 10))

        # 生成图表每一行
        for row in range(height - 1, -1, -1):
            # Y 轴刻度
            y_value = min_val + round(row * value_range / (height - 1))
            line = f"{y_value:4d} ┤" if show_axis else "     "

            # 每个数据点
            for i, val in enumerate(values):
                # 归一化到当前行高度
                normalized = round((val - min_val) / value_range * (height - 1))

                if normalized == row:
                    # 数据点在行上
                    line += "██"
                elif normalized > row:
                    # 数据点在上方，显示填充
                    line += "██"
                else:
                    # 数据点在下方，显示空白
                    line += "  "

            lines.append(line)

        # X 轴基线
        if show_axis:
            x_axis = "     └" + "─" * n_points * 2
            lines.append(x_axis)

        return "\n".join(lines)

    @classmethod
    def sparkline(
        cls,
        values: List[int],
        min_max_normalize: bool = True,
    ) -> str:
        """
        生成火花线（迷你趋势图，一行显示）

        Args:
            values: 数据值列表
            min_max_normalize: 是否归一化到 min-max 范围

        Returns:
            火花线字符串
        """
        if not values:
            return ""

        # 边界检查：确保是列表且元素是数字
        try:
            if min_max_normalize:
                max_val = max(values)
                min_val = min(values)
                value_range = max(max_val - min_val, 1)

                # 归一化到 0-7 范围
                normalized = [
                    min(7, max(0, round((v - min_val) / value_range * 7)))
                    for v in values
                ]
            else:
                # 直接使用 0-7 的值
                normalized = [min(7, max(0, int(v) if v is not None else 0)) for v in values]
        except (TypeError, ValueError):
            return ""

        return "".join(cls.SPARK_CHARS[n] for n in normalized)

    @classmethod
    def level_progress_bar(
        cls,
        progress_pct: float,
        current_level: str,
        next_level: str,
        width: int = 30,
    ) -> str:
        """
        生成境界进度条（带里程碑标记）

        Args:
            progress_pct: 当前境界进度百分比（0-100）
            current_level: 当前境界名称
            next_level: 下一境界名称
            width: 进度条宽度

        Returns:
            境界进度条字符串
        """
        # 边界检查
        if not isinstance(width, int) or width < 10:
            width = 30
        if not isinstance(progress_pct, (int, float)):
            progress_pct = 0
        progress_pct = max(0.0, min(100.0, float(progress_pct)))
        if not isinstance(current_level, str):
            current_level = str(current_level)
        if not isinstance(next_level, str):
            next_level = str(next_level)

        filled = round(progress_pct / 100 * width)
        filled = min(filled, width)
        empty = width - filled

        lines = []
        lines.append(f"🏅 当前境界: {current_level}")

        # 主进度条
        bar = "█" * filled + "░" * empty
        lines.append(f"   [{bar}] {progress_pct:.1f}%")

        # 里程碑标记线
        half_pos = width // 2
        marker_line = "   " + current_level + " " + "─" * (width - len(current_level) - len(next_level) - 2) + " " + next_level

        # 在中间位置添加里程碑标记
        milestone_pos = len("   " + current_level + " ") + half_pos
        marker_chars = list(marker_line)
        if milestone_pos < len(marker_chars):
            marker_chars[milestone_pos] = "┼"

        lines.append("".join(marker_chars))

        return "\n".join(lines)

    @classmethod
    def enhanced_radar_chart(
        cls,
        scores: Dict[str, int],
        previous_scores: Optional[Dict[str, int]] = None,
        width: int = 25,
        title: str = "五维能力雷达",
    ) -> str:
        """
        生成增强型五维雷达图（支持显示变化对比）

        Args:
            scores: 当前得分字典
            previous_scores: 上一次得分（可选，用于对比变化）
            width: 进度条宽度
            title: 图表标题

        Returns:
            增强型雷达图字符串
        """
        dimension_names = {
            "proficiency": "熟练度",
            "stability": "稳定性",
            "satisfaction": "满意度",
            "responsiveness": "响应力",
            "memory": "记忆力",
        }

        # 边界检查
        if not isinstance(scores, dict):
            scores = {}
        if not isinstance(width, int) or width < 10:
            width = 25
        if not isinstance(title, str) or not title:
            title = "五维能力雷达"

        lines = []

        # 标题
        if previous_scores and isinstance(previous_scores, dict) and previous_scores:
            try:
                prev_composite = round(sum(previous_scores.values()) / max(1, len(previous_scores)))
                curr_composite = round(sum(scores.values()) / max(1, len(scores)))
                change = curr_composite - prev_composite
                change_str = f"+{change}" if change >= 0 else str(change)
            except (TypeError, ValueError):
                change_str = ""
                previous_scores = None
            lines.append(f"🧠 {title} (vs 上次: {change_str})")
        else:
            lines.append(f"🧠 {title}")

        lines.append("═" * (width + 15))

        # 每个维度的进度条 + 变化对比
        for key, dim_name in dimension_names.items():
            score = scores.get(key, 0)
            filled = round(score / 100 * width)
            filled = min(filled, width)
            empty = width - filled

            bar = "█" * filled + "░" * empty

            # 变化对比标记
            change_str = ""
            if previous_scores and key in previous_scores:
                change = score - previous_scores[key]
                if change > 0:
                    change_str = f" ▲{change}"
                elif change < 0:
                    change_str = f" ▼{change}"
                else:
                    change_str = " ─"

            lines.append(f"  {dim_name:4s} {bar} {score:3d}{change_str}")

        lines.append("═" * (width + 15))

        # 综合得分（避免空字典除零）
        if scores:
            composite = round(sum(scores.values()) / len(scores))
        else:
            composite = 0
        grade, grade_icon = cls._get_grade(composite)
        lines.append(f"📊 综合能力: {composite:3d} 分 | {grade_icon} {grade}")

        return "\n".join(lines)

    @classmethod
    def _get_grade(cls, score: int) -> tuple[str, str]:
        """根据综合得分获得评级和图标"""
        if score >= 90:
            return "大师级", "🏆"
        elif score >= 75:
            return "专家级", "⭐"
        elif score >= 60:
            return "熟练级", "💪"
        elif score >= 40:
            return "进阶中", "📖"
        else:
            return "新手期", "🌱"

    @classmethod
    def simple_bar_chart(
        cls,
        data: Dict[str, int],
        width: int = 30,
        title: str = "数据对比",
    ) -> str:
        """
        生成简单的横向柱状图

        Args:
            data: 标签 -> 数值字典
            width: 最长条的宽度
            title: 图表标题

        Returns:
            柱状图字符串
        """
        # 边界检查
        if not isinstance(data, dict) or not data:
            return "暂无数据"
        if not isinstance(width, int) or width < 10:
            width = 30
        if not isinstance(title, str) or not title:
            title = "数据对比"

        try:
            max_val = max(v for v in data.values() if isinstance(v, (int, float)))
            max_label_len = max(len(str(label)) for label in data.keys())
        except (TypeError, ValueError):
            return "暂无数据"

        lines = []
        lines.append(f"📊 {title}")
        lines.append("═" * (width + max_label_len + 5))

        for label, value in data.items():
            bar_len = round(value / max(max_val, 1) * width)
            bar = "█" * bar_len
            lines.append(f"  {label:{max_label_len}s} {bar} {value}")

        return "\n".join(lines)

    @classmethod
    def trend_summary_with_sparkline(
        cls,
        values: List[int],
        dimension_name: str = "综合能力",
    ) -> str:
        """
        生成带火花线的趋势摘要（一行显示）

        Args:
            values: 历史数值列表
            dimension_name: 维度名称

        Returns:
            趋势摘要字符串
        """
        # 边界检查
        if not isinstance(values, list) or len(values) < 2:
            return f"📊 {dimension_name}: 数据不足，继续积累中"
        if not isinstance(dimension_name, str) or not dimension_name:
            dimension_name = "综合能力"

        # 确保所有值是数字
        try:
            first = int(values[0]) if values[0] is not None else 0
            last = int(values[-1]) if values[-1] is not None else 0
            change = last - first
        except (TypeError, ValueError):
            return f"📊 {dimension_name}: 数据格式异常"

        first = values[0]
        last = values[-1]
        change = last - first

        spark = cls.sparkline(values)

        arrow = "↗️" if change > 0 else "↘️" if change < 0 else "➡️"
        change_str = f"+{change}" if change >= 0 else str(change)

        return f"📊 {dimension_name}: {spark} {arrow} {change_str}"
