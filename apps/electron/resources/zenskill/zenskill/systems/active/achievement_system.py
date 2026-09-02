"""成就与徽章系统 (7Y)"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List

from zenskill.core.paths import SkillStateManager, atomic_write_json, get_user_data_dir
from zenskill.mirroring.event_collector import EventCollector
from zenskill.mirroring.models import EventType
from zenskill.systems.active.habit_tracker import HabitTracker


@dataclass
class Badge:
    badge_id: str
    title: str
    tier: str
    icon: str
    description: str
    unlocked: bool
    progress: float
    detail: str


class AchievementSystem:
    LEVEL_BADGES = [
        ("novice", "新手", "🌱", "NOVICE"),
        ("apprentice", "学徒", "🌿", "APPRENTICE"),
        ("adept", "熟手", "🪴", "ADEPT"),
        ("expert", "专家", "🌳", "EXPERT"),
        ("master", "大师", "🏆", "MASTER"),
    ]
    LEVEL_ORDER = {"NOVICE": 0, "APPRENTICE": 1, "ADEPT": 2, "EXPERT": 3, "MASTER": 4}

    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id
        self.collector = EventCollector()
        self._history_path = get_user_data_dir() / "growth" / "achievements.json"

    def _load_history(self) -> Dict[str, Dict[str, str]]:
        """解锁历史（终身制）：{badge_id: {title, unlocked_at}}"""
        try:
            data = json.loads(self._history_path.read_text(encoding="utf-8"))
            return data.get(self.skill_id, {})
        except Exception:
            return {}

    def _record_unlocks(self, realtime_unlocked: List[Badge],
                        history: Dict[str, Dict[str, str]]) -> List[str]:
        """新解锁落盘（惰性，覆盖 CLI/TUI/MCP 全部入口）。返回本次新解锁 id。"""
        new_ids = [b.badge_id for b in realtime_unlocked if b.badge_id not in history]
        if not new_ids:
            return []
        now = datetime.now().isoformat()
        merged = dict(history)
        for b in realtime_unlocked:
            if b.badge_id in new_ids:
                merged[b.badge_id] = {"title": b.title, "unlocked_at": now}
        try:
            all_data: Dict[str, Any] = {}
            if self._history_path.exists():
                all_data = json.loads(self._history_path.read_text(encoding="utf-8"))
            all_data[self.skill_id] = merged
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(self._history_path, all_data)
        except Exception:
            pass
        return new_ids

    def evaluate(self) -> Dict[str, Any]:
        state = SkillStateManager(self.skill_id).load()
        events = self.collector.query(skill_id=self.skill_id, limit=10000)
        recent_start = (datetime.now() - timedelta(days=7)).timestamp()
        recent_events = [event for event in events if event.timestamp >= recent_start]
        habit_data = HabitTracker(self.skill_id).analyze(days=28)
        # 反思活动记录在 episodes（zenloop 不写 EventCollector）——供两源合并
        episode_reflections = sum(
            1 for ep in state.get("episodes", [])
            if "reflection" in str(ep.get("action", "")).lower()
        )
        badges = []
        badges.extend(self._level_badges(state))
        badges.extend(self._usage_badges(state))
        badges.extend(self._activity_badges(recent_events))
        badges.extend(self._habit_badges(habit_data))
        badges.extend(self._quality_badges(events, episode_reflections=episode_reflections))

        # 终身制：历史 ∪ 实时——进度可回落，解锁不回落
        history = self._load_history()
        new_ids = [b.badge_id for b in badges if b.unlocked and b.badge_id not in history]
        if new_ids:
            history = self._record_unlocks(
                [b for b in badges if b.unlocked], history)
        for badge in badges:
            if not badge.unlocked and badge.badge_id in history:
                badge.unlocked = True

        unlocked = [badge for badge in badges if badge.unlocked]
        locked = [badge for badge in badges if not badge.unlocked]
        locked.sort(key=lambda badge: badge.progress, reverse=True)
        return {
            "skill_id": self.skill_id,
            "unlocked": unlocked,
            "locked": locked,
            "total": len(badges),
            "unlocked_count": len(unlocked),
            "completion_rate": len(unlocked) / max(1, len(badges)),
            "new_unlocks": new_ids,
            "generated_at": datetime.now().isoformat(),
        }

    def format_report(self) -> str:
        data = self.evaluate()
        lines = ["🏅 成就与徽章系统 (7Y)", "═" * 50, ""]
        lines.append(f"   解锁进度: {data['unlocked_count']}/{data['total']} ({data['completion_rate']:.0%})")
        lines.append("")
        if data["unlocked"]:
            lines.append("   已解锁:")
            for badge in data["unlocked"]:
                lines.append(f"   {badge.icon} [{badge.tier}] {badge.title} — {badge.description}")
                if badge.detail:
                    lines.append(f"      {badge.detail}")
        else:
            lines.append("   暂无已解锁徽章，继续使用后会自动点亮")
        if data["locked"]:
            lines.append("")
            lines.append("   接近解锁:")
            for badge in data["locked"][:5]:
                bar = self._bar(badge.progress)
                lines.append(f"   {badge.icon} {badge.title} [{bar}] {badge.progress:.0%}")
                lines.append(f"      {badge.detail}")
        return "\n".join(lines)

    def _level_badges(self, state: Dict[str, Any]) -> List[Badge]:
        level = state.get("level", "NOVICE")
        current = self.LEVEL_ORDER.get(level, 0)
        badges = []
        for badge_id, title, icon, target in self.LEVEL_BADGES:
            target_order = self.LEVEL_ORDER[target]
            unlocked = current >= target_order
            progress = 1.0 if unlocked else min(0.99, current / max(1, target_order))
            badges.append(Badge(f"level_{badge_id}", title, "里程碑", icon, f"达到 {target} 境界", unlocked, progress, f"当前境界: {level}"))
        return badges

    def _usage_badges(self, state: Dict[str, Any]) -> List[Badge]:
        usage = int(state.get("usage_count", 0) or 0)
        specs = [
            ("first_10", "起步十练", "✨", 10),
            ("fifty_runs", "稳定修炼", "💪", 50),
            ("two_hundred", "长期主义", "🔥", 200),
            ("five_hundred", "千锤百炼", "🏔️", 500),
        ]
        return [Badge(f"usage_{bid}", title, "使用", icon, f"累计使用 {target} 次", usage >= target, min(1.0, usage / target), f"当前 {usage}/{target} 次") for bid, title, icon, target in specs]

    def _activity_badges(self, events: List[Any]) -> List[Badge]:
        total = len(events)
        skill_count = len({event.skill_id for event in events})
        session_count = len({event.session_id for event in events if event.session_id})
        return [
            Badge("activity_weekly_20", "本周活跃", "活跃", "📈", "7 天内记录 20 个事件", total >= 20, min(1.0, total / 20), f"本周事件 {total}/20"),
            Badge("activity_session_5", "连续会话者", "活跃", "🧭", "7 天内出现 5 个会话", session_count >= 5, min(1.0, session_count / 5), f"本周会话 {session_count}/5"),
            Badge("activity_cross_skill", "跨域探索者", "活跃", "🌐", "7 天内跨 3 个技能活动", skill_count >= 3, min(1.0, skill_count / 3), f"本周技能 {skill_count}/3"),
        ]

    def _habit_badges(self, habit_data: Dict[str, Any]) -> List[Badge]:
        reports = habit_data.get("habits", [])
        best = max((int(report.get("best_streak", 0)) for report in reports), default=0)
        active = sum(1 for report in reports if report.get("streak", 0) > 0)
        return [
            Badge("habit_first_streak", "习惯萌芽", "习惯", "🌤️", "任一习惯连续 3 天", best >= 3, min(1.0, best / 3), f"最佳连续 {best}/3 天"),
            Badge("habit_week", "七日不辍", "习惯", "📅", "任一习惯连续 7 天", best >= 7, min(1.0, best / 7), f"最佳连续 {best}/7 天"),
            Badge("habit_multi", "多线养成", "习惯", "🧩", "同时保持 2 个习惯", active >= 2, min(1.0, active / 2), f"当前活跃习惯 {active}/2"),
        ]

    def _quality_badges(self, events: List[Any], episode_reflections: int = 0) -> List[Badge]:
        total = len(events)
        success = sum(1 for event in events if event.success)
        errors = sum(1 for event in events if event.event_type == EventType.ERROR or not event.success)
        reflections = sum(1 for event in events if event.event_type == EventType.REFLECTION or "reflection" in str(event.action).lower())
        # 反思活动记录在 episodes（zenloop 不写 EventCollector）——两源合并
        reflections += episode_reflections
        success_rate = success / max(1, total)
        return [
            Badge("quality_stable", "稳定执行者", "质量", "🛡️", "成功率达到 90% 且事件不少于 20", total >= 20 and success_rate >= 0.9, min(1.0, success_rate / 0.9) if total >= 20 else min(0.8, total / 20), f"成功率 {success_rate:.0%}，事件 {total}/20"),
            Badge("quality_bug_hunter", "Bug 猎手", "质量", "🐞", "累计记录 10 个错误/失败并持续改进", errors >= 10, min(1.0, errors / 10), f"错误/失败 {errors}/10"),
            Badge("quality_reflector", "反思者", "质量", "🪞", "累计 5 次反思沉淀", reflections >= 5, min(1.0, reflections / 5), f"反思 {reflections}/5"),
        ]

    def _bar(self, progress: float, width: int = 12) -> str:
        filled = int(max(0.0, min(progress, 1.0)) * width)
        return "█" * filled + "░" * (width - filled)
