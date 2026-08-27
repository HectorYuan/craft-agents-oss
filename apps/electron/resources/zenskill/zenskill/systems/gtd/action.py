"""
8.7B: Action 引擎

GTD 核心单元 — 原子化下一步行动。
Context 感知 / Priority 排序 / Energy 需求 / 重复规则。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GTDAction:
    id: str
    title: str
    description: str = ""
    contexts: list[str] = field(default_factory=list)
    priority: str = "P2"
    energy_required: int = 5
    due_date: str = ""
    estimated_minutes: int = 25
    project_id: str = ""
    skill_id: str = ""
    status: str = "pending"  # pending → next → done / delegated / incubating
    repeat_rule: str = ""
    profile: str = ""  # 所属 profile（空=当前激活）
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    completed_at: str = ""
    energy_invested: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "description": self.description,
            "contexts": self.contexts, "priority": self.priority,
            "energy_required": self.energy_required, "due_date": self.due_date,
            "estimated_minutes": self.estimated_minutes, "project_id": self.project_id,
            "skill_id": self.skill_id, "status": self.status,
            "repeat_rule": self.repeat_rule, "profile": self.profile,
            "created_at": self.created_at,
            "completed_at": self.completed_at, "energy_invested": self.energy_invested,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GTDAction":
        return cls(
            id=data.get("id", ""), title=data.get("title", ""),
            description=data.get("description", ""),
            contexts=data.get("contexts", []), priority=data.get("priority", "P2"),
            energy_required=data.get("energy_required", 5),
            due_date=data.get("due_date", ""),
            estimated_minutes=data.get("estimated_minutes", 25),
            project_id=data.get("project_id", ""), skill_id=data.get("skill_id", ""),
            status=data.get("status", "pending"),
            repeat_rule=data.get("repeat_rule", ""),
            profile=data.get("profile", ""),
            created_at=data.get("created_at", ""),
            completed_at=data.get("completed_at", ""),
            energy_invested=data.get("energy_invested", 0),
        )


class ActionEngine:
    """GTD Action 管理引擎"""

    PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    ENERGY_MAP = {"easy": 3, "medium": 5, "hard": 8, "extreme": 10}
    _id_counter: int = 0

    @classmethod
    def _next_id(cls) -> str:
        cls._id_counter += 1
        return f"act_{int(time.time() * 1000)}_{cls._id_counter}"

    def __init__(self, data_dir: str = ""):
        if data_dir:
            self._data_dir = Path(data_dir)
        else:
            from ...core.paths import get_user_data_dir
            self._data_dir = get_user_data_dir() / "gtd"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._data_dir / "actions.jsonl"

    @staticmethod
    def _current_profile() -> str:
        """获取当前激活的 profile 名称"""
        try:
            from ...core.paths import get_active_profile
            return get_active_profile()
        except Exception:
            return "default"

    def add(self, title: str, **kwargs) -> GTDAction:
        action = GTDAction(
            id=ActionEngine._next_id(),
            title=title,
            profile=self._current_profile(),
            **{k: v for k, v in kwargs.items()
               if k in GTDAction.__dataclass_fields__},
        )
        # 如果 energy_required 是字符串, 映射为数字
        if isinstance(action.energy_required, str):
            action.energy_required = self.ENERGY_MAP.get(
                action.energy_required.lower(), 5)
        self._append(action)
        return action

    def list(self, status: str = "pending", project_id: str = "",
             context: str = "", priority: str = "", due_today: bool = False,
             limit: int = 50) -> list[GTDAction]:
        items = self._read_all()
        if status != "all":
            items = [i for i in items if i.status == status]
        if project_id:
            items = [i for i in items if i.project_id == project_id]
        if context:
            items = [i for i in items if context in i.contexts]
        if priority:
            items = [i for i in items if i.priority == priority]
        if due_today:
            today = time.strftime("%Y-%m-%d")
            items = [i for i in items if i.due_date[:10] == today]

        # 按 priority 排序
        items.sort(key=lambda a: self.PRIORITY_ORDER.get(a.priority, 2))
        return items[:limit]

    def get(self, action_id: str) -> Optional[GTDAction]:
        for a in self._read_all():
            if a.id == action_id:
                return a
        return None

    def done(self, action_id: str, energy_invested: int = 0) -> bool:
        return self._update_status(action_id, "done", energy_invested=energy_invested)

    def mark_next(self, action_id: str) -> bool:
        return self._update_status(action_id, "next")

    def delegate(self, action_id: str) -> bool:
        return self._update_status(action_id, "delegated")

    def incubate(self, action_id: str) -> bool:
        return self._update_status(action_id, "incubating")

    def delete(self, action_id: str) -> bool:
        items = self._read_all()
        filtered = [a for a in items if a.id != action_id]
        if len(filtered) != len(items):
            self._rewrite(filtered)
            return True
        return False

    def edit(self, action_id: str, **kwargs) -> Optional[GTDAction]:
        items = self._read_all()
        for a in items:
            if a.id == action_id:
                for k, v in kwargs.items():
                    if hasattr(a, k) and v is not None:
                        setattr(a, k, v)
                self._rewrite(items)
                return a
        return None

    def next_actions(self, limit: int = 5) -> list[GTDAction]:
        """智能推荐下一步 — 按 context+energy+priority 排序"""
        pending = self.list(status="pending", limit=100)
        # 有 due_date 的优先, 再按 priority 排序
        scored = []
        for a in pending:
            score = self.PRIORITY_ORDER.get(a.priority, 2) * 10
            if a.due_date:
                try:
                    due = time.mktime(time.strptime(a.due_date[:10], "%Y-%m-%d"))
                    days_left = (due - time.time()) / 86400
                    if days_left <= 0:
                        score -= 50  # 逾期, 紧急
                    elif days_left <= 1:
                        score -= 30  # 今天到期
                    elif days_left <= 3:
                        score -= 10  # 3天内
                except Exception:
                    pass
            scored.append((a, score))
        scored.sort(key=lambda x: x[1])
        return [a for a, _ in scored[:limit]]

    def stats(self) -> dict:
        items = self._read_all()
        pending = sum(1 for a in items if a.status in ("pending", "next"))
        done = sum(1 for a in items if a.status == "done")
        overdue = sum(1 for a in items
                      if a.status in ("pending", "next") and a.due_date
                      and a.due_date[:10] < time.strftime("%Y-%m-%d"))
        return {"total": len(items), "pending": pending, "done": done,
                "overdue": overdue, "completion_rate": done / max(len(items), 1)}

    # ── 内部 ──

    def _read_all(self) -> list[GTDAction]:
        if not self._file.exists():
            return []
        items = []
        for line in self._file.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                items.append(GTDAction.from_dict(json.loads(line)))
            except Exception:
                continue
        return items

    def _append(self, action: GTDAction) -> None:
        with open(self._file, "a", encoding="utf-8") as f:
            f.write(json.dumps(action.to_dict(), ensure_ascii=False) + "\n")

    def _rewrite(self, items: list[GTDAction]) -> None:
        lines = [json.dumps(a.to_dict(), ensure_ascii=False) for a in items]
        self._file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _update_status(self, action_id: str, status: str, **extra) -> bool:
        items = self._read_all()
        for a in items:
            if a.id == action_id:
                a.status = status
                if status == "done":
                    a.completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                for k, v in extra.items():
                    if hasattr(a, k):
                        setattr(a, k, v)
                self._rewrite(items)
                # 完成时记录成长（rewrite 后再记录，避免覆盖）
                if status == "done" and a.skill_id:
                    self._record_skill_growth(a)
                # 重复任务: 创建下一个实例（rewrite 后再创建）
                if status == "done" and a.repeat_rule:
                    self._create_next_repeat(a)
                return True
        return False

    def _record_skill_growth(self, action: GTDAction) -> None:
        try:
            from ...core.paths import SkillStateManager
            mgr = SkillStateManager(action.skill_id)
            mgr.record_episode(
                action=f"gtd_action: {action.title}",
                content=f"完成 GTD Action: energy={action.energy_invested}",
                success=True, duration_ms=action.estimated_minutes * 60000,
            )
        except Exception:
            pass

    def _create_next_repeat(self, action: GTDAction) -> None:
        """创建下一个重复任务实例"""
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        offset = {"daily": 1, "weekly": 7, "monthly": 30}.get(action.repeat_rule, 7)
        next_due = (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%d")
        self.add(
            title=action.title, description=action.description,
            contexts=action.contexts, priority=action.priority,
            energy_required=action.energy_required,
            due_date=next_due, project_id=action.project_id,
            skill_id=action.skill_id, repeat_rule=action.repeat_rule,
        )
