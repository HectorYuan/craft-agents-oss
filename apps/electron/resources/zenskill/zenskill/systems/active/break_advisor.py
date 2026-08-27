"""
智能间歇建议 (7V)

基于会话数据提供番茄工作法休息提醒和最佳学习时段分析。
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional


class BreakAdvisor:
    """智能间歇建议引擎"""

    # 番茄钟设置
    POMODORO_WORK = 25  # 分钟
    POMODORO_BREAK = 5
    LONG_BREAK_AFTER = 4  # 个番茄钟后长休息
    LONG_BREAK = 15  # 分钟

    def __init__(self):
        self._data_dir = Path.home() / ".zenskill" / "session"

    def check(self, tool_count: int, elapsed_min: float) -> List[Dict]:
        """检查当前是否需要休息建议

        Returns:
            [{"type": "pomodoro/long_break/fatigue/optimal_hour", "message": "..."}]
        """
        suggestions = []

        # 番茄钟检测
        pomodoros = int(elapsed_min / self.POMODORO_WORK)
        if pomodoros >= 1 and elapsed_min % self.POMODORO_WORK < 2:
            if pomodoros % self.LONG_BREAK_AFTER == 0:
                suggestions.append({
                    "type": "long_break",
                    "message": f"已完成 {pomodoros} 个番茄钟, 建议长休息 {self.LONG_BREAK} 分钟",
                    "priority": "high",
                })
            else:
                suggestions.append({
                    "type": "pomodoro",
                    "message": f"番茄钟 #{pomodoros} 完成, 建议休息 {self.POMODORO_BREAK} 分钟",
                    "priority": "medium",
                })

        # 疲劳检测
        if elapsed_min > 120:
            suggestions.append({
                "type": "fatigue",
                "message": f"已连续工作 {elapsed_min:.0f} 分钟 (>2小时), 强烈建议休息",
                "priority": "critical",
            })
        elif elapsed_min > 60 and tool_count > 30:
            suggestions.append({
                "type": "fatigue",
                "message": "高强度工作 1 小时, 建议站起来活动",
                "priority": "high",
            })

        # 最佳时段分析
        optimal = self._get_optimal_hours()
        if optimal:
            current_hour = time.localtime(time.time()).tm_hour
            if current_hour not in optimal["hours"]:
                suggestions.append({
                    "type": "optimal_hour",
                    "message": f"你的最佳学习时段是 {', '.join(f'{h}:00' for h in optimal['hours'][:3])}, 当前时段效率可能较低",
                    "priority": "low",
                })

        return suggestions

    def get_pomodoro_status(self, elapsed_min: float) -> str:
        """获取番茄钟状态"""
        pomodoros = int(elapsed_min / self.POMODORO_WORK)
        minutes_in_current = int(elapsed_min % self.POMODORO_WORK)
        remaining = self.POMODORO_WORK - minutes_in_current

        bar_w = 20
        filled = int(minutes_in_current / self.POMODORO_WORK * bar_w)
        bar = "█" * filled + "░" * (bar_w - filled)

        return (
            f"🍅 番茄钟 #{pomodoros + 1} [{bar}] {minutes_in_current}/{self.POMODORO_WORK}min"
            f" ({'休息!' if remaining <= 0 else f'还剩 {remaining}min'})"
        )

    def _get_optimal_hours(self) -> Optional[Dict]:
        """分析历史工具使用时段, 找到最佳学习时段"""
        try:
            events_file = Path.home() / ".zenskill" / "mirroring" / "events.jsonl"
            if not events_file.exists():
                return None

            hours = []
            for line in events_file.read_text().splitlines()[:2000]:
                try:
                    e = json.loads(line)
                    ts = e.get("timestamp", "")
                    if ts:
                        h = time.localtime(
                            time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
                        ).tm_hour
                        hours.append(h)
                except Exception:
                    continue

            if not hours:
                return None

            counter = Counter(hours)
            most_common = counter.most_common(4)
            return {
                "hours": [h for h, _ in most_common],
                "counts": {str(h): c for h, c in most_common},
            }
        except Exception:
            return None

    def get_daily_rhythm(self) -> str:
        """获取每日活跃节奏分析"""
        optimal = self._get_optimal_hours()
        if not optimal:
            return "📊 数据积累中, 需要更多使用记录来分析活跃时段"

        lines = ["📊 历史活跃时段", "═" * 40]
        max_count = max(optimal["counts"].values())

        for h in range(24):
            count = optimal["counts"].get(str(h), 0)
            bar_w = 20
            filled = int(count / max(max_count, 1) * bar_w) if max_count > 0 else 0
            bar = "█" * filled + "░" * (bar_w - filled)
            marker = " ← 峰值" if h in optimal["hours"] else ""
            if count > 0:
                lines.append(f"  {h:02d}:00 [{bar}] {count}次{marker}")

        return "\n".join(lines)
