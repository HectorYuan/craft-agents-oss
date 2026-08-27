"""
8.7C: Project 引擎

需要 >1 步完成的目标 → 项目化管理。
支持子项目嵌套、技能关联、停滞检测, 内置模板库。
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
class GTDProject:
    id: str
    name: str
    outcome: str = ""
    status: str = "active"  # active / someday / done / archived
    next_action_id: str = ""
    parent_project_id: str = ""
    review_date: str = ""
    notes: str = ""
    skill_id: str = ""
    profile: str = ""  # 所属 profile（空=当前激活）
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    completed_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "outcome": self.outcome,
            "status": self.status, "next_action_id": self.next_action_id,
            "parent_project_id": self.parent_project_id, "review_date": self.review_date,
            "notes": self.notes, "skill_id": self.skill_id,
            "profile": self.profile,
            "created_at": self.created_at, "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GTDProject":
        return cls(
            id=data.get("id", ""), name=data.get("name", ""),
            outcome=data.get("outcome", ""), status=data.get("status", "active"),
            next_action_id=data.get("next_action_id", ""),
            parent_project_id=data.get("parent_project_id", ""),
            review_date=data.get("review_date", ""),
            notes=data.get("notes", ""), skill_id=data.get("skill_id", ""),
            profile=data.get("profile", ""),
            created_at=data.get("created_at", ""),
            completed_at=data.get("completed_at", ""),
        )


# 预置项目模板
PROJECT_TEMPLATES = {
    "learn-skill": {
        "name": "学习新技能",
        "outcome": "掌握新技能的基础并完成 3 个实践项目",
        "notes": "使用 skill tutor 获取学习风格建议, 设置每日练习 Action",
    },
    "refactor": {
        "name": "代码重构",
        "outcome": "提升代码质量和可维护性, 测试覆盖率 ≥ 80%",
        "notes": "先诊断 (doctor state), 再拆解为模块级 Action, 每次一个 PR",
    },
    "interview-prep": {
        "name": "面试准备",
        "outcome": "完成技术面试准备, 覆盖算法/系统设计/行为面试",
        "notes": "每日练习 1 道算法题, 每周 1 次模拟面试",
    },
    "side-project": {
        "name": "副项目",
        "outcome": "发布 MVP 版本, 获得前 10 个用户反馈",
        "notes": "先定义 MVP 范围, 按 feature 拆解为 Action, 每周 Review 进度",
    },
    "gtd-weekly": {
        "name": "GTD 周回顾",
        "outcome": "Inbox 清零, Project 进度检查, 下周计划制定",
        "notes": "每周末执行, 使用 review weekly 命令, 更新所有 Project 状态",
    },
}


class ProjectEngine:
    """GTD Project 管理引擎"""

    def __init__(self, data_dir: str = ""):
        if data_dir:
            self._data_dir = Path(data_dir)
        else:
            from ...core.paths import get_user_data_dir
            self._data_dir = get_user_data_dir() / "gtd" / "projects"
        self._data_dir.mkdir(parents=True, exist_ok=True)

    _id_counter: int = 0

    def _next_id(self) -> str:
        ProjectEngine._id_counter += 1
        return f"proj_{int(time.time() * 1000)}_{ProjectEngine._id_counter}"

    @staticmethod
    def _current_profile() -> str:
        """获取当前激活的 profile 名称"""
        try:
            from ...core.paths import get_active_profile
            return get_active_profile()
        except Exception:
            return "default"

    def create(self, name: str, **kwargs) -> GTDProject:
        proj = GTDProject(
            id=self._next_id(),
            name=name,
            profile=self._current_profile(),
            **{k: v for k, v in kwargs.items()
               if k in GTDProject.__dataclass_fields__},
        )
        self._save(proj)
        return proj

    def get(self, project_id: str) -> Optional[GTDProject]:
        path = self._path(project_id)
        if not path.exists():
            return None
        try:
            return GTDProject.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def list(self, status: str = "active", parent_id: str = "") -> list[GTDProject]:
        projects = []
        for path in sorted(self._data_dir.glob("*.json")):
            try:
                p = GTDProject.from_dict(json.loads(path.read_text(encoding="utf-8")))
                if status != "all" and p.status != status:
                    continue
                if parent_id and p.parent_project_id != parent_id:
                    continue
                projects.append(p)
            except Exception:
                continue
        return projects

    def update(self, project_id: str, **kwargs) -> Optional[GTDProject]:
        proj = self.get(project_id)
        if not proj:
            return None
        for k, v in kwargs.items():
            if hasattr(proj, k) and v is not None:
                setattr(proj, k, v)
        self._save(proj)
        return proj

    def done(self, project_id: str) -> bool:
        proj = self.get(project_id)
        if not proj:
            return False
        proj.status = "done"
        proj.completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save(proj)
        # 记录技能成长
        if proj.skill_id:
            self._record_skill_growth(proj)
        return True

    def archive(self, project_id: str) -> bool:
        return self.update(project_id, status="archived")

    def set_next_action(self, project_id: str, action_id: str) -> bool:
        return self.update(project_id, next_action_id=action_id) is not None

    def review(self, project_id: str) -> bool:
        return self.update(project_id,
                           review_date=time.strftime("%Y-%m-%dT%H:%M:%S"))

    def dashboard(self) -> dict:
        projects = self.list(status="all")
        active = [p for p in projects if p.status == "active"]
        stale = []
        for p in active:
            if p.review_date:
                try:
                    last = time.mktime(time.strptime(p.review_date[:10], "%Y-%m-%d"))
                    if (time.time() - last) > 7 * 86400:
                        stale.append(p)
                except Exception:
                    stale.append(p)
            else:
                try:
                    created = time.mktime(time.strptime(p.created_at[:10], "%Y-%m-%d"))
                    if (time.time() - created) > 7 * 86400:
                        stale.append(p)
                except Exception:
                    pass
        return {
            "total": len(projects),
            "active": len(active),
            "stale": len(stale),
            "done": sum(1 for p in projects if p.status == "done"),
            "someday": sum(1 for p in projects if p.status == "someday"),
            "stale_projects": [p.name for p in stale[:5]],
        }

    def template_list(self) -> list[dict]:
        return [{"key": k, "name": v["name"], "outcome": v["outcome"]}
                for k, v in PROJECT_TEMPLATES.items()]

    def template_use(self, template_key: str, name: str = "") -> Optional[GTDProject]:
        tmpl = PROJECT_TEMPLATES.get(template_key)
        if not tmpl:
            return None
        return self.create(name=name or tmpl["name"],
                           outcome=tmpl["outcome"], notes=tmpl["notes"])

    # ── 内部 ──

    def _path(self, project_id: str) -> Path:
        return self._data_dir / f"{project_id}.json"

    def _save(self, proj: GTDProject) -> None:
        self._path(proj.id).write_text(
            json.dumps(proj.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def _record_skill_growth(self, proj: GTDProject) -> None:
        try:
            from ...core.paths import SkillStateManager
            mgr = SkillStateManager(proj.skill_id)
            mgr.record_episode(
                action=f"project_done: {proj.name}",
                content=f"完成 GTD Project: {proj.outcome}",
                success=True, duration_ms=0,
            )
        except Exception:
            pass
