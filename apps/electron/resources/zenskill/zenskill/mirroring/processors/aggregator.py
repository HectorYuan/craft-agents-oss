"""
信号聚合器

将多个采集器的信号合并为统一的用户画像视图。
"""

from collections import Counter
from typing import Any, Dict, List, Optional


class SignalAggregator:
    """跨采集器信号聚合"""

    def aggregate(self, events: List[Dict]) -> Dict[str, Any]:
        """聚合所有事件信号"""
        if not events:
            return {"total_events": 0, "sources": [], "summary": {}}

        sources = list(set(e.get("source", "unknown") for e in events))
        all_signals: Dict[str, Any] = {}
        for e in events:
            signal = e.get("signal", {})
            for k, v in signal.items():
                if k not in all_signals:
                    all_signals[k] = v
                elif isinstance(v, (int, float)):
                    all_signals[k] = all_signals.get(k, 0) + v

        # 衍生洞察
        insights = self._derive_insights(events)

        return {
            "total_events": len(events),
            "sources": sources,
            "signals": all_signals,
            "insights": insights,
        }

    def _derive_insights(self, events: List[Dict]) -> List[str]:
        """从聚合信号中推导理解"""
        insights = []

        for e in events:
            s = e.get("signal", {})
            src = e.get("source", "")

            if src == "claude_code_history":
                style = s.get("expression_style", "")
                msg = s.get("total_messages", 0)
                if style == "concise" and msg > 50:
                    insights.append("偏好简洁表达 — 频繁使用短指令")
                peak = s.get("peak_hour", -1)
                if 0 <= peak <= 5:
                    insights.append(f"深夜活跃型 — 峰值在凌晨 {peak}:00")

            if src == "claude_code_tasks":
                rate = s.get("completion_rate", 0)
                if rate < 50:
                    insights.append(f"任务完成率偏低 ({rate}%)")
                gran = s.get("task_granularity", "")
                if gran:
                    insights.append(f"偏好{ {'fine':'细', 'medium':'中', 'coarse':'粗'}.get(gran, gran)}粒度任务")

            if src == "claude_code_plans":
                plans = s.get("total_plans", 0)
                style = s.get("iteration_style", "")
                if style == "many_small_plans" and plans > 10:
                    insights.append("高频小计划模式 — 快速迭代偏好")

            if src == "claude_core_settings":
                lang = s.get("dominant_language", "")
                if lang == "chinese":
                    insights.append("中文优先环境")

        return insights
