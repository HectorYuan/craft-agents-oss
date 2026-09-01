"""习惯养成追踪 (7X)"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from zenskill.core.paths import atomic_write_json, get_user_data_dir
from zenskill.mirroring.event_collector import EventCollector


@dataclass
class HabitDefinition:
    habit_id: str
    title: str
    skill_id: str
    target_count: int
    action_contains: str
    created_at: str
    updated_at: str


class HabitTracker:
    DEFAULT_TEMPLATES = {
        "daily_python": {"title": "每天至少完成 1 次 Python 相关操作", "skill_id": "python", "target_count": 1, "action_contains": ""},
        "debug_loop": {"title": "每天至少完成 1 次调试闭环", "skill_id": "zenskill-core", "target_count": 1, "action_contains": "debug"},
        "cli_tui": {"title": "每天练习 CLI/TUI 工作流", "skill_id": "zenskill-core", "target_count": 1, "action_contains": ""},
        "reflection": {"title": "每天做 1 次反思沉淀", "skill_id": "zenskill-core", "target_count": 1, "action_contains": "reflection"},
    }

    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id
        self.path = get_user_data_dir() / "growth" / "habits.json"
        self.collector = EventCollector()

    def list_habits(self) -> List[HabitDefinition]:
        data = self._load()
        habits = data.get("habits", {})
        return [HabitDefinition(**item) for item in habits.values()]

    def add_habit(self, habit_id: str, title: str, target_count: int = 1, skill_id: Optional[str] = None, action_contains: str = "") -> HabitDefinition:
        clean_id = self._normalize_id(habit_id)
        now = datetime.now().isoformat()
        data = self._load()
        existing = data.setdefault("habits", {}).get(clean_id)
        habit = HabitDefinition(
            habit_id=clean_id,
            title=title.strip(),
            skill_id=skill_id or self.skill_id,
            target_count=max(1, int(target_count)),
            action_contains=action_contains.strip().lower(),
            created_at=existing.get("created_at", now) if existing else now,
            updated_at=now,
        )
        data["habits"][clean_id] = asdict(habit)
        data["updated_at"] = now
        self._save(data)
        return habit

    def apply_template(self, template_id: str) -> HabitDefinition:
        clean_id = self._normalize_id(template_id)
        if clean_id not in self.DEFAULT_TEMPLATES:
            raise ValueError(f"未知习惯模板: {template_id}")
        tpl = self.DEFAULT_TEMPLATES[clean_id]
        return self.add_habit(clean_id, tpl["title"], tpl["target_count"], tpl["skill_id"], tpl["action_contains"])

    def remove_habit(self, habit_id: str) -> bool:
        data = self._load()
        clean_id = self._normalize_id(habit_id)
        if clean_id not in data.get("habits", {}):
            return False
        del data["habits"][clean_id]
        data["updated_at"] = datetime.now().isoformat()
        self._save(data)
        return True

    def check_in(self, habit_id: str) -> Dict[str, Any]:
        """记录一次习惯打卡（写入一条可被 _matches 匹配的成功事件）"""
        habits = {h.habit_id: h for h in self.list_habits()}
        clean_id = self._normalize_id(habit_id)
        habit = habits.get(clean_id)
        if not habit:
            raise ValueError(f"未知习惯: {habit_id}")
        action = f"habit:{clean_id}"
        if habit.action_contains:
            action += f" {habit.action_contains}"
        self.collector.record_skill_execution(
            skill_id=habit.skill_id or self.skill_id,
            task=action,
            success=True,
            duration_ms=0,
        )
        report = self.analyze(days=7)
        for r in report["habits"]:
            if r["habit"]["habit_id"] == clean_id:
                return {
                    "ok": True,
                    "habit_id": clean_id,
                    "title": habit.title,
                    "streak": r["streak"],
                    "completion_rate": r["completion_rate"],
                }
        return {"ok": True, "habit_id": clean_id, "title": habit.title}

    def analyze(self, days: int = 28) -> Dict[str, Any]:
        habits = self.list_habits()
        end = date.today()
        dates = [end - timedelta(days=i) for i in range(days - 1, -1, -1)]
        start_ts = datetime.combine(dates[0], datetime.min.time()).timestamp()
        events = self.collector.query(since=start_ts, limit=10000)
        reports = []
        for habit in habits:
            daily = {d.isoformat(): 0 for d in dates}
            for event in events:
                if not self._matches(habit, event):
                    continue
                day = datetime.fromtimestamp(event.timestamp).date().isoformat()
                if day in daily:
                    daily[day] += 1
            completed = {day: count >= habit.target_count for day, count in daily.items()}
            reports.append({
                "habit": asdict(habit),
                "daily": daily,
                "completed": completed,
                "streak": self._current_streak(completed),
                "best_streak": self._best_streak(completed),
                "completion_rate": sum(1 for ok in completed.values() if ok) / max(1, len(completed)),
                "risk": self._risk(completed),
            })
        return {"days": days, "habits": reports, "generated_at": datetime.now().isoformat()}

    def format_report(self, days: int = 28) -> str:
        data = self.analyze(days)
        lines = ["📅 习惯养成追踪 (7X)", "═" * 50, ""]
        if not data["habits"]:
            lines.extend([
                "   暂无习惯定义",
                "   可用模板: " + ", ".join(sorted(self.DEFAULT_TEMPLATES)),
                "   试试: zenskill growth habits --action apply --id cli_tui",
            ])
            return "\n".join(lines)
        for report in data["habits"]:
            habit = report["habit"]
            grid = self._calendar_grid(report["completed"])
            risk_label = {"low": "低", "medium": "中", "high": "高"}.get(report["risk"], report["risk"])
            lines.append(f"   • {habit['title']} ({habit['habit_id']})")
            lines.append(f"     连续 {report['streak']} 天 | 最佳 {report['best_streak']} 天 | 完成率 {report['completion_rate']:.0%} | 中断风险 {risk_label}")
            lines.append(f"     {grid}")
            suggestion = self._suggestion(report)
            if suggestion:
                lines.append(f"     建议: {suggestion}")
            lines.append("")
        return "\n".join(lines).rstrip()

    @classmethod
    def format_templates(cls) -> str:
        lines = ["📚 习惯模板库", "═" * 50, ""]
        for template_id, item in sorted(cls.DEFAULT_TEMPLATES.items()):
            lines.append(f"   • {template_id:12s} {item['title']}")
        return "\n".join(lines)

    def export_habits(self, output: Optional[str] = None) -> str:
        data = {"habits": [asdict(item) for item in self.list_habits()], "exported_at": datetime.now().isoformat()}
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if output:
            out = Path(output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            return str(out)
        return text

    def import_habits(self, source: str) -> int:
        raw = json.loads(Path(source).read_text(encoding="utf-8"))
        items = raw.get("habits", raw if isinstance(raw, list) else [])
        count = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            self.add_habit(item.get("habit_id", item.get("id", "")), item.get("title", ""), item.get("target_count", 1), item.get("skill_id", self.skill_id), item.get("action_contains", ""))
            count += 1
        return count

    def _matches(self, habit: HabitDefinition, event: Any) -> bool:
        if habit.skill_id and habit.skill_id != event.skill_id:
            return False
        if habit.action_contains and habit.action_contains not in str(event.action).lower():
            return False
        return bool(event.success)

    def _current_streak(self, completed: Dict[str, bool]) -> int:
        streak = 0
        for day in sorted(completed.keys(), reverse=True):
            if not completed[day]:
                break
            streak += 1
        return streak

    def _best_streak(self, completed: Dict[str, bool]) -> int:
        best = 0
        current = 0
        for day in sorted(completed.keys()):
            if completed[day]:
                current += 1
                best = max(best, current)
            else:
                current = 0
        return best

    def _risk(self, completed: Dict[str, bool]) -> str:
        recent = [completed[day] for day in sorted(completed.keys())[-7:]]
        misses = recent.count(False)
        if misses >= 4:
            return "high"
        if misses >= 2:
            return "medium"
        return "low"

    def _calendar_grid(self, completed: Dict[str, bool]) -> str:
        cells = []
        for day in sorted(completed.keys()):
            cells.append("■" if completed[day] else "·")
        return "".join(cells)

    def _suggestion(self, report: Dict[str, Any]) -> str:
        if report["streak"] >= 7:
            return "习惯已进入稳定期，可以适度提高目标强度"
        if report["risk"] == "high":
            return "目标可能偏重，建议降低每日门槛或改成隔日节奏"
        if report["completion_rate"] < 0.5:
            return "先把目标缩小到 2 分钟即可完成的最小动作"
        return "保持当前节奏，优先不中断连续性"

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "habits": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"version": 1, "habits": {}}

    def _save(self, data: Dict[str, Any]) -> None:
        atomic_write_json(self.path, data)

    @staticmethod
    def _normalize_id(value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value).strip().lower()).strip("_")
        if not cleaned:
            raise ValueError("习惯 ID 不能为空")
        return cleaned
