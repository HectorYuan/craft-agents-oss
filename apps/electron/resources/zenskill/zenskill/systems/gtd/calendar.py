"""
8.7E: Calendar 日程引擎

时间盒管理 — 真实日期绑定, 重复规则, 时段规划。
日/周视图, 冲突检测, 智能排期建议。
"""

from __future__ import annotations

import calendar as cal_mod
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

REPEAT_OFFSETS = {"daily": 1, "weekly": 7, "monthly": 30, "yearly": 365}


@dataclass
class CalendarEvent:
    id: str
    action_id: str = ""
    title: str = ""
    date: str = ""        # YYYY-MM-DD
    time_str: str = ""    # HH:MM
    end_time: str = ""    # HH:MM
    repeat_rule: str = "" # daily/weekly/monthly/none
    reminder_before_min: int = 15
    period: str = ""      # morning/afternoon/evening
    profile: str = ""     # 所属 profile（空=当前激活）
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

    def to_dict(self) -> dict:
        return {
            "id": self.id, "action_id": self.action_id, "title": self.title,
            "date": self.date, "time_str": self.time_str, "end_time": self.end_time,
            "repeat_rule": self.repeat_rule,
            "reminder_before_min": self.reminder_before_min,
            "period": self.period, "profile": self.profile,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CalendarEvent":
        return cls(
            id=data.get("id", ""), action_id=data.get("action_id", ""),
            title=data.get("title", ""), date=data.get("date", ""),
            time_str=data.get("time_str", ""), end_time=data.get("end_time", ""),
            repeat_rule=data.get("repeat_rule", ""),
            reminder_before_min=data.get("reminder_before_min", 15),
            period=data.get("period", ""),
            profile=data.get("profile", ""),
            created_at=data.get("created_at", ""),
        )


class CalendarEngine:
    """日程管理引擎"""
    _id_counter: int = 0

    @classmethod
    def _next_id(cls) -> str:
        cls._id_counter += 1
        return f"cal_{int(time.time() * 1000)}_{cls._id_counter}"

    def __init__(self, data_dir: str = ""):
        if data_dir:
            self._data_dir = Path(data_dir)
        else:
            from ...core.paths import get_user_data_dir
            self._data_dir = get_user_data_dir() / "gtd"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._data_dir / "calendar.jsonl"

    @staticmethod
    def _current_profile() -> str:
        """获取当前激活的 profile 名称"""
        try:
            from ...core.paths import get_active_profile
            return get_active_profile()
        except Exception:
            return "default"

    def add(self, date: str, title: str, **kwargs) -> CalendarEvent:
        event = CalendarEvent(
            id=CalendarEngine._next_id(),
            date=date, title=title,
            profile=self._current_profile(),
            **{k: v for k, v in kwargs.items()
               if k in CalendarEvent.__dataclass_fields__},
        )
        # 自动判断时段
        if not event.period and event.time_str:
            hour = int(event.time_str.split(":")[0])
            event.period = "morning" if hour < 12 else ("afternoon" if hour < 18 else "evening")
        self._append(event)
        self._sync_to_sqlite(event)
        return event

    def schedule_action(self, action_id: str, date: str, time_str: str = "09:00",
                        repeat: str = "") -> CalendarEvent:
        """将 Action 排入日程"""
        from .action import ActionEngine
        ae = ActionEngine()
        action = ae.get(action_id)
        title = action.title if action else action_id
        return self.add(date=date, title=title, action_id=action_id,
                        time_str=time_str, repeat_rule=repeat)

    def today(self) -> list[CalendarEvent]:
        today = time.strftime("%Y-%m-%d")
        return self._on_date(today)

    def week(self, start_date: str = "") -> list[list[CalendarEvent]]:
        if not start_date:
            start_date = time.strftime("%Y-%m-%d")
        d = datetime.strptime(start_date, "%Y-%m-%d")
        # 本周一
        monday = d - timedelta(days=d.weekday())
        result = []
        for i in range(7):
            date_str = (monday + timedelta(days=i)).strftime("%Y-%m-%d")
            result.append(self._on_date(date_str))
        return result

    def month_view(self, year: int = 0, month: int = 0) -> dict:
        if not year:
            year = datetime.now().year
        if not month:
            month = datetime.now().month
        all_events = self._read_all()
        by_date: dict[str, int] = {}  # YYYY-MM-DD → count
        all_month_events: list[dict] = []  # flat array (frontend filter expects list)
        _, days_in_month = cal_mod.monthrange(year, month)
        for day in range(1, days_in_month + 1):
            date_str = f"{year:04d}-{month:02d}-{day:02d}"
            day_events = self._collect_day(all_events, date_str)
            if day_events:
                by_date[date_str] = len(day_events)
                all_month_events.extend(e.to_dict() for e in day_events)
        return {
            "year": year, "month": month,
            "month_name": cal_mod.month_name[month],
            "days": by_date,
            "events": all_month_events,
        }

    def suggest(self) -> list[dict]:
        """智能排期 — 基于历史活跃时段建议"""
        today = time.strftime("%Y-%m-%d")
        events = self._read_all()
        # 统计各时段的事件数
        periods = {"morning": [], "afternoon": [], "evening": []}
        for e in events[-100:]:
            if e.period in periods:
                periods[e.period].append(e)
        best_period = max(periods, key=lambda p: len(periods[p]))

        # 检查冲突
        today_events = self._on_date(today)
        busy_times = set()
        for e in today_events:
            if e.time_str:
                busy_times.add(e.time_str)

        suggestions = []
        slots = ["09:00", "10:00", "14:00", "16:00", "20:00"]
        hour_period = {"09": "morning", "10": "morning",
                       "14": "afternoon", "16": "afternoon", "20": "evening"}
        for slot in slots:
            if slot not in busy_times:
                suggestions.append({"date": today, "time": slot,
                                    "period": hour_period.get(slot[:2], best_period)})
        return suggestions[:3]

    def update(self, event_id: str, **kwargs) -> Optional[CalendarEvent]:
        """更新日程事件字段（读取全部 → 原地修改 → rewrite）。

        time_str 变更时自动重算 period（显式传 period 除外）；
        成功后同步 SQLite（JSONL 为准，失败仅 warning）。
        """
        events = self._read_all()
        found: Optional[CalendarEvent] = None
        allowed = set(CalendarEvent.__dataclass_fields__) - {"id"}
        for e in events:
            if e.id != event_id:
                continue
            for k, v in kwargs.items():
                if k in allowed and v is not None:
                    setattr(e, k, v)
            if "time_str" in kwargs and "period" not in kwargs and e.time_str:
                try:
                    hour = int(e.time_str.split(":")[0])
                    e.period = "morning" if hour < 12 else (
                        "afternoon" if hour < 18 else "evening")
                except (ValueError, IndexError):
                    pass
            found = e
        if found is None:
            return None
        self._rewrite(events)
        self._sync_to_sqlite(found)
        return found

    def delete(self, event_id: str) -> bool:
        events = self._read_all()
        filtered = [e for e in events if e.id != event_id]
        if len(filtered) != len(events):
            self._rewrite(filtered)
            self._delete_from_sqlite(event_id)
            return True
        return False

    # ── 内部 ──

    def _on_date(self, date_str: str) -> list[CalendarEvent]:
        return self._collect_day(self._read_all(), date_str)

    def _collect_day(self, events: list[CalendarEvent], date_str: str) -> list[CalendarEvent]:
        """收集指定日期事件（精确匹配 + 重复规则展开）。

        按 (id, date) 去重：同一条事件同一天只出现一次——精确匹配命中后
        不再走 repeat 展开，避免 daily/weekly 事件在起始日出现双份。"""
        result: list[CalendarEvent] = []
        seen: set[tuple[str, str]] = set()
        for e in events:
            if e.date == date_str:
                key = (e.id, date_str)
                if key not in seen:
                    seen.add(key)
                    result.append(e)
            elif e.repeat_rule:
                for x in self._expand_repeat(e, date_str):
                    key = (x.id, x.date or date_str)
                    if key not in seen:
                        seen.add(key)
                        result.append(x)
        result.sort(key=lambda e: e.time_str or "23:59")
        return result

    def _expand_repeat(self, event: CalendarEvent, target_date: str) -> list[CalendarEvent]:
        """将重复事件展开到目标日期"""
        if not event.date:
            return []
        try:
            start = datetime.strptime(event.date, "%Y-%m-%d")
            target = datetime.strptime(target_date, "%Y-%m-%d")
            offset = REPEAT_OFFSETS.get(event.repeat_rule)
            if not offset or target < start:
                return []
            days_diff = (target - start).days
            if days_diff % offset == 0:
                return [CalendarEvent(
                    id=event.id, action_id=event.action_id,
                    title=event.title, date=target_date,
                    time_str=event.time_str, period=event.period,
                )]
        except Exception:
            pass
        return []

    def _read_all(self) -> list[CalendarEvent]:
        if not self._file.exists():
            return []
        events = []
        for line in self._file.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                events.append(CalendarEvent.from_dict(json.loads(line)))
            except Exception:
                continue
        return events

    def _append(self, event: CalendarEvent) -> None:
        with open(self._file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def _rewrite(self, events: list[CalendarEvent]) -> None:
        lines = [json.dumps(e.to_dict(), ensure_ascii=False) for e in events]
        self._file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _sync_to_sqlite(self, event: CalendarEvent) -> None:
        """JSONL 写入后同步到 SQLite（逐条，WAL 模式）。失败仅 warning 不阻塞。"""
        try:
            from ...core.database import db
            with db.connect() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO gtd_calendar
                       (event_id, title, date, time_str, period,
                        repeat_rule, status, created_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (event.id, event.title, event.date, event.time_str,
                     event.period, event.repeat_rule, "scheduled",
                     event.created_at)
                )
        except Exception:
            logger.warning("SQLite sync failed for calendar event %s, JSONL is authoritative", event.id)

    def _delete_from_sqlite(self, event_id: str) -> None:
        """从 SQLite 删除日程事件（JSONL rewrite 后调用）。失败仅 warning 不阻塞。"""
        try:
            from ...core.database import db
            with db.connect() as conn:
                conn.execute("DELETE FROM gtd_calendar WHERE event_id=?", (event_id,))
        except Exception:
            logger.warning("SQLite delete failed for calendar event %s", event_id)
