"""
即时反馈与奖励 (7P)

基于会话状态、工具序列和事件流生成微反馈、连击奖励与每日成就。
"""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from zenskill.mirroring.event_collector import EventCollector


class InstantFeedbackEngine:
    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id
        self.collector = EventCollector()

    def generate(self, state: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        state = state or self._load_session_state()
        feedback = []
        tool_count = int(state.get("tool_count", 0) or 0)
        recent_tools = state.get("recent_tools", []) if isinstance(state.get("recent_tools", []), list) else []
        elapsed_min = self._elapsed_min(state)

        pattern = self._pattern_feedback(recent_tools)
        if pattern:
            feedback.append(pattern)

        streak = self._streak_feedback(tool_count)
        if streak:
            feedback.append(streak)

        daily = self._daily_achievement()
        if daily:
            feedback.append(daily)

        health = self._healthy_pace(tool_count, elapsed_min)
        if health:
            feedback.append(health)

        return feedback

    def generate_one_line(self, state: Dict[str, Any] | None = None) -> str:
        items = self.generate(state)
        if not items:
            return ""
        item = items[0]
        return f"{item['icon']} {item['message']}"

    def format_report(self) -> str:
        items = self.generate()
        lines = ["🎁 即时反馈与奖励 (7P)", "═" * 50, ""]
        if not items:
            lines.append("   暂无即时奖励信号，继续使用后会自动生成")
            return "\n".join(lines)
        for item in items:
            lines.append(f"   {item['icon']} [{item['type']}] {item['message']}")
            if item.get("detail"):
                lines.append(f"      {item['detail']}")
        return "\n".join(lines)

    def _load_session_state(self) -> Dict[str, Any]:
        path = Path.home() / ".zenskill" / "session" / "current.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}

    def _elapsed_min(self, state: Dict[str, Any]) -> float:
        started = state.get("started")
        if not isinstance(started, (int, float)):
            return 0.0
        return max(0.0, (time.time() - started) / 60)

    def _pattern_feedback(self, recent_tools: List[str]) -> Dict[str, Any] | None:
        tail5 = recent_tools[-5:]
        tail3 = recent_tools[-3:]
        if len(tail5) >= 5 and "Read" in tail5 and "Edit" in tail5:
            return {"type": "习惯", "icon": "👍", "message": "先读后改，保持了稳健的修改节奏", "detail": "读取上下文后再编辑，能减少误改和返工"}
        if len(tail3) >= 3 and "Bash" in tail3 and ("Read" in tail3 or "Edit" in tail3):
            return {"type": "验证", "icon": "✅", "message": "执行后及时检查，验证意识在线", "detail": "把检查嵌入工作流，有助于尽早发现偏差"}
        if len(set(tail5)) >= 3:
            return {"type": "节奏", "icon": "🔄", "message": "多工具协同良好，正在形成闭环", "detail": "探索、修改、验证之间保持切换"}
        return None

    def _streak_feedback(self, tool_count: int) -> Dict[str, Any] | None:
        if tool_count > 0 and tool_count % 25 == 0:
            return {"type": "连击", "icon": "🔥", "message": f"连续 {tool_count} 次操作，专注度很高", "detail": "建议在下一个自然节点做一次短暂停顿和状态检查"}
        if tool_count > 0 and tool_count % 10 == 0:
            return {"type": "连击", "icon": "✨", "message": f"完成 {tool_count} 次连续操作", "detail": "保持小步快跑，并继续用测试或 smoke check 收口"}
        if tool_count > 0 and tool_count % 5 == 0:
            return {"type": "微奖励", "icon": "⭐", "message": f"已完成 {tool_count} 次工具调用", "detail": "稳定推进中"}
        return None

    def _daily_achievement(self) -> Dict[str, Any] | None:
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        events = self.collector.get_events_since(start)
        if not events:
            return None
        actions = Counter(event.action for event in events if event.action)
        skill_count = len({event.skill_id for event in events})
        if len(events) >= 50:
            return {"type": "每日成就", "icon": "🏅", "message": f"今日已记录 {len(events)} 个事件", "detail": "高活跃日，适合结束前做一次总结沉淀"}
        if skill_count >= 3:
            return {"type": "每日成就", "icon": "🌟", "message": f"今日跨 {skill_count} 个技能活动", "detail": "跨域活动增加了迁移学习机会"}
        if actions:
            action, count = actions.most_common(1)[0]
            if count >= 5:
                return {"type": "每日成就", "icon": "📌", "message": f"今日高频动作：{action} × {count}", "detail": "可以把高频动作沉淀成模板或快捷路径"}
        return None

    def _healthy_pace(self, tool_count: int, elapsed_min: float) -> Dict[str, Any] | None:
        if elapsed_min <= 0 or tool_count <= 0:
            return None
        pace = tool_count / max(elapsed_min, 1)
        if 0.2 <= pace <= 3 and elapsed_min >= 10:
            return {"type": "节奏", "icon": "🟢", "message": "当前工作节奏稳定", "detail": f"约 {pace:.1f} 次工具调用/分钟"}
        return None
