"""
8.7U: 旧系统迁移

将旧的 Goal/Task/Habit 数据迁移到 GTD 系统:
- Goal → GTD Project (outcome=目标维度达标)
- Task → GTD Action (保留现有数据，补充 context/energy)
- Habit → Calendar repeat events
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from zenskill.core.paths import get_user_data_dir

logger = logging.getLogger(__name__)

# 维度 → 上下文映射
DIMENSION_CONTEXT = {
    "proficiency": "coding",
    "stability": "review",
    "satisfaction": "reflect",
    "responsiveness": "quick-win",
    "memory": "learning",
}

# 难度 → 能量映射
DIFFICULTY_ENERGY = {
    "easy": "low",
    "medium": "medium",
    "hard": "high",
}


class GTDMigrator:
    """GTD 数据迁移器"""

    def __init__(self, data_dir: str = ""):
        self._data_dir = data_dir or str(get_user_data_dir())
        self._base = Path(self._data_dir)
        self._project_file = self._base / "gtd" / "projects.jsonl"
        self._action_file = self._base / "gtd" / "actions.jsonl"
        self._calendar_file = self._base / "gtd" / "calendar.jsonl"

    def migrate_goals(self, skill_id: str = "zenskill-core") -> Dict[str, Any]:
        """Goal → GTD Project"""
        goals_file = self._base / "goals" / f"{skill_id}_goals.jsonl"
        if not goals_file.exists():
            return {"migrated": 0, "skipped": 0, "reason": "no goals file"}

        goals = []
        for line in goals_file.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                try:
                    goals.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        # 加载已有项目，避免重复
        existing_outcomes = set()
        if self._project_file.exists():
            for line in self._project_file.read_text(encoding="utf-8").strip().split("\n"):
                if line.strip():
                    try:
                        p = json.loads(line)
                        existing_outcomes.add(p.get("outcome", ""))
                    except json.JSONDecodeError:
                        continue

        migrated = 0
        skipped = 0
        now = datetime.now().isoformat()
        counter = int(time.time() * 1000) % 100000

        for goal in goals:
            dim = goal.get("dimension", "composite")
            target = goal.get("target_score", 0)
            outcome = f"目标维度达标: {dim} {target}分"

            # 跳过已迁移的
            if outcome in existing_outcomes:
                skipped += 1
                continue

            status_map = {"active": "active", "completed": "done", "failed": "dropped"}
            project = {
                "project_id": f"proj_mig_{counter}",
                "outcome": outcome,
                "status": status_map.get(goal.get("status", "active"), "active"),
                "context": DIMENSION_CONTEXT.get(dim, "general"),
                "energy": "medium",
                "skill_id": skill_id,
                "created_at": goal.get("created_at", now),
                "updated_at": now,
                "next_actions": [],
                "migrated_from": goal.get("goal_id", ""),
            }
            self._append_jsonl(self._project_file, project)
            existing_outcomes.add(outcome)
            migrated += 1
            counter += 1

        return {"migrated": migrated, "skipped": skipped, "total": len(goals)}

    def migrate_tasks(self, skill_id: str = "zenskill-core") -> Dict[str, Any]:
        """Task → GTD Action"""
        tasks_file = self._base / "tasks" / f"{skill_id}_tasks.jsonl"
        if not tasks_file.exists():
            return {"migrated": 0, "skipped": 0, "reason": "no tasks file"}

        tasks = []
        for line in tasks_file.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                try:
                    tasks.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        # 加载已有 action，按 title 去重
        existing_titles = set()
        if self._action_file.exists():
            for line in self._action_file.read_text(encoding="utf-8").strip().split("\n"):
                if line.strip():
                    try:
                        a = json.loads(line)
                        existing_titles.add(a.get("title", ""))
                    except json.JSONDecodeError:
                        continue

        migrated = 0
        skipped = 0
        now = datetime.now().isoformat()
        counter = int(time.time() * 1000) % 100000

        for task in tasks:
            title = task.get("title", "")
            if not title or title in existing_titles:
                skipped += 1
                continue

            dims = task.get("target_dimensions", [])
            context = DIMENSION_CONTEXT.get(dims[0], "general") if dims else "general"
            difficulty = task.get("difficulty", "medium")
            energy = DIFFICULTY_ENERGY.get(difficulty, "medium")

            status = "done" if task.get("is_completed") else "pending"
            action = {
                "action_id": f"act_mig_{counter}",
                "title": title,
                "description": task.get("description", ""),
                "status": status,
                "context": context,
                "energy": energy,
                "priority": task.get("priority", 1.0),
                "project_id": "",
                "skill_id": skill_id,
                "created_at": now,
                "completed_at": task.get("completed_at"),
                "migrated_from": task.get("task_id", ""),
            }
            self._append_jsonl(self._action_file, action)
            existing_titles.add(title)
            migrated += 1
            counter += 1

        return {"migrated": migrated, "skipped": skipped, "total": len(tasks)}

    def migrate_habits(self, skill_id: str = "zenskill-core") -> Dict[str, Any]:
        """Habit → Calendar repeat events"""
        habits_file = self._base / "growth" / "habits.json"
        if not habits_file.exists():
            return {"migrated": 0, "skipped": 0, "reason": "no habits file"}

        try:
            data = json.loads(habits_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"migrated": 0, "skipped": 0, "reason": "corrupted habits file"}

        habits = list(data.get("habits", {}).values())
        if not habits:
            return {"migrated": 0, "skipped": 0, "reason": "no habits defined"}

        # 加载已有日历事件，按 title 去重
        existing_titles = set()
        if self._calendar_file.exists():
            for line in self._calendar_file.read_text(encoding="utf-8").strip().split("\n"):
                if line.strip():
                    try:
                        e = json.loads(line)
                        existing_titles.add(e.get("title", ""))
                    except json.JSONDecodeError:
                        continue

        migrated = 0
        skipped = 0
        now = datetime.now().isoformat()
        counter = int(time.time() * 1000) % 100000

        for habit in habits:
            title = habit.get("title", "")
            if not title or title in existing_titles:
                skipped += 1
                continue

            event = {
                "event_id": f"evt_mig_{counter}",
                "title": title,
                "description": f"[习惯迁移] {habit.get('action_contains', '')}",
                "start_time": datetime.now().strftime("%Y-%m-%d") + "T09:00:00",
                "end_time": datetime.now().strftime("%Y-%m-%d") + "T09:30:00",
                "repeat": "daily",
                "context": "habit",
                "energy": "low",
                "status": "active",
                "created_at": now,
                "migrated_from": habit.get("habit_id", ""),
            }
            self._append_jsonl(self._calendar_file, event)
            existing_titles.add(title)
            migrated += 1
            counter += 1

        return {"migrated": migrated, "skipped": skipped, "total": len(habits)}

    def migrate_all(self, skill_id: str = "zenskill-core") -> Dict[str, Any]:
        """运行全量迁移"""
        return {
            "goals": self.migrate_goals(skill_id),
            "tasks": self.migrate_tasks(skill_id),
            "habits": self.migrate_habits(skill_id),
            "migrated_at": datetime.now().isoformat(),
        }

    def _append_jsonl(self, path: Path, record: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
