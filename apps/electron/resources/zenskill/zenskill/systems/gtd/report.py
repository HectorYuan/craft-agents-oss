"""
8.7X: GTD 报告引擎

- 周报: 完成数、项目进度、能量趋势、Incubating 产出
- 月报: 项目完成率、技能成长关联、时间分配、效率评分
- 格式: Markdown (Human) + JSON (Machine)
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from zenskill.core.paths import get_user_data_dir

logger = logging.getLogger(__name__)


class GTDReportEngine:
    """GTD 报告引擎"""

    def __init__(self, data_dir: str = ""):
        self._data_dir = data_dir or str(get_user_data_dir())
        self._base = Path(self._data_dir) / "gtd"

    def weekly_report(self, weeks: int = 1) -> Dict[str, Any]:
        """生成周报数据"""
        now = datetime.now()
        start = now - timedelta(weeks=weeks)

        actions = self._load_jsonl("actions.jsonl")
        projects = self._load_jsonl("projects.jsonl")
        inbox = self._load_jsonl("inbox.jsonl")
        calendar = self._load_jsonl("calendar.jsonl")

        # 本周完成的 Action
        done_this_week = [
            a for a in actions
            if a.get("status") == "done"
            and a.get("completed_at", "") >= start.isoformat()
        ]

        # 本周新增的 Action
        new_this_week = [
            a for a in actions
            if a.get("created_at", "") >= start.isoformat()
        ]

        # 待办 Action
        pending = [a for a in actions if a.get("status") == "pending"]

        # 项目统计
        active_projects = [p for p in projects if p.get("status") == "active"]
        done_projects = [
            p for p in projects
            if p.get("status") == "done"
            and p.get("updated_at", "") >= start.isoformat()
        ]

        # Inbox 统计
        inbox_new = [
            i for i in inbox
            if i.get("created_at", "") >= start.isoformat()
        ]
        inbox_unprocessed = [i for i in inbox if i.get("status") == "pending"]

        # 上下文分布
        context_counter = Counter()
        for a in done_this_week:
            ctx = a.get("contexts", a.get("context", "general"))
            if isinstance(ctx, list):
                context_counter.update(ctx)
            else:
                context_counter[ctx] += 1

        # 能量投入
        energy_invested = sum(a.get("energy_invested", a.get("energy_required", 0)) for a in done_this_week)

        result = {
            "report_type": "weekly",
            "period": {"start": start.isoformat(), "end": now.isoformat(), "weeks": weeks},
            "actions": {
                "done": len(done_this_week),
                "new": len(new_this_week),
                "pending": len(pending),
                "completion_rate": len(done_this_week) / max(1, len(done_this_week) + len(pending)),
            },
            "projects": {
                "active": len(active_projects),
                "completed": len(done_projects),
                "stale": self._count_stale(projects),
            },
            "inbox": {
                "new": len(inbox_new),
                "unprocessed": len(inbox_unprocessed),
            },
            "contexts": dict(context_counter.most_common()),
            "energy_invested": energy_invested,
            "generated_at": now.isoformat(),
        }

        return result

    def monthly_report(self, months: int = 1) -> Dict[str, Any]:
        """生成月报数据"""
        now = datetime.now()
        start = now - timedelta(days=30 * months)

        actions = self._load_jsonl("actions.jsonl")
        projects = self._load_jsonl("projects.jsonl")

        # 本月完成
        done_this_month = [
            a for a in actions
            if a.get("status") == "done"
            and a.get("completed_at", "") >= start.isoformat()
        ]

        # 按周统计完成趋势
        weekly_trend = defaultdict(int)
        for a in done_this_month:
            completed = a.get("completed_at", "")
            if completed:
                try:
                    dt = datetime.fromisoformat(completed)
                    week_key = dt.strftime("%Y-W%W")
                    weekly_trend[week_key] += 1
                except ValueError:
                    pass

        # 项目完成率
        all_projects = [p for p in projects if p.get("created_at", "") >= start.isoformat()]
        done_projects = [p for p in all_projects if p.get("status") == "done"]

        # 技能关联分析
        skill_counter = Counter()
        for a in done_this_month:
            skill = a.get("skill_id", "")
            if skill:
                skill_counter[skill] += 1

        # 上下文效率 (每个上下文的平均完成时间)
        context_stats = defaultdict(lambda: {"count": 0, "total_minutes": 0})
        for a in done_this_month:
            ctx = a.get("contexts", a.get("context", "general"))
            if isinstance(ctx, list):
                ctx = ctx[0] if ctx else "general"
            est = a.get("estimated_minutes", 0)
            context_stats[ctx]["count"] += 1
            context_stats[ctx]["total_minutes"] += est

        # 效率评分 (0-100)
        completion_rate = len(done_this_month) / max(1, len(actions))
        project_rate = len(done_projects) / max(1, len(all_projects)) if all_projects else 0.5
        efficiency_score = int((completion_rate * 50 + project_rate * 50))

        result = {
            "report_type": "monthly",
            "period": {"start": start.isoformat(), "end": now.isoformat(), "months": months},
            "actions": {
                "done": len(done_this_month),
                "total": len(actions),
                "completion_rate": completion_rate,
            },
            "projects": {
                "total": len(all_projects),
                "done": len(done_projects),
                "completion_rate": project_rate,
            },
            "weekly_trend": dict(sorted(weekly_trend.items())),
            "skills": dict(skill_counter.most_common(10)),
            "context_efficiency": {
                ctx: {
                    "count": stats["count"],
                    "avg_minutes": round(stats["total_minutes"] / max(1, stats["count"]), 1),
                }
                for ctx, stats in context_stats.items()
            },
            "efficiency_score": efficiency_score,
            "generated_at": now.isoformat(),
        }

        return result

    def format_weekly_markdown(self, data: Dict[str, Any]) -> str:
        """格式化周报为 Markdown"""
        lines = [
            "# GTD 周报",
            "",
            f"**周期**: {data['period']['start'][:10]} ~ {data['period']['end'][:10]}",
            "",
            "## 行动统计",
            "",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| ✅ 完成 | {data['actions']['done']} |",
            f"| 📥 新增 | {data['actions']['new']} |",
            f"| ⏳ 待办 | {data['actions']['pending']} |",
            f"| 📊 完成率 | {data['actions']['completion_rate']:.0%} |",
            "",
            "## 项目状态",
            "",
            f"- 🟢 活跃: {data['projects']['active']}",
            f"- ✅ 本周完成: {data['projects']['completed']}",
            f"- ⚠️ 停滞 (>7天): {data['projects']['stale']}",
            "",
            "## Inbox",
            "",
            f"- 📥 新增: {data['inbox']['new']}",
            f"- ⏳ 未处理: {data['inbox']['unprocessed']}",
        ]

        if data.get("contexts"):
            lines.extend(["", "## 上下文分布", ""])
            for ctx, count in sorted(data["contexts"].items(), key=lambda x: -x[1]):
                lines.append(f"- **{ctx}**: {count}")

        lines.extend([
            "",
            "## 能量投入",
            "",
            f"本周总能量投入: **{data['energy_invested']}** 单位",
            "",
            f"---",
            f"*生成于 {data['generated_at'][:19]}*",
        ])

        return "\n".join(lines)

    def format_monthly_markdown(self, data: Dict[str, Any]) -> str:
        """格式化月报为 Markdown"""
        lines = [
            "# GTD 月报",
            "",
            f"**周期**: {data['period']['start'][:10]} ~ {data['period']['end'][:10]}",
            "",
            "## 总览",
            "",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| ✅ 完成 Action | {data['actions']['done']} |",
            f"| 📦 完成 Project | {data['projects']['done']} |",
            f"| 📊 Action 完成率 | {data['actions']['completion_rate']:.0%} |",
            f"| 📊 Project 完成率 | {data['projects']['completion_rate']:.0%} |",
            f"| ⭐ 效率评分 | {data['efficiency_score']}/100 |",
        ]

        if data.get("weekly_trend"):
            lines.extend(["", "## 每周趋势", ""])
            for week, count in sorted(data["weekly_trend"].items()):
                bar = "█" * min(count, 20)
                lines.append(f"- {week}: {bar} ({count})")

        if data.get("skills"):
            lines.extend(["", "## 技能关联", ""])
            for skill, count in sorted(data["skills"].items(), key=lambda x: -x[1]):
                lines.append(f"- **{skill}**: {count} 次")

        if data.get("context_efficiency"):
            lines.extend(["", "## 上下文效率", ""])
            lines.append("| 上下文 | 完成数 | 平均耗时 |")
            lines.append("|--------|--------|----------|")
            for ctx, stats in sorted(data["context_efficiency"].items(), key=lambda x: -x[1]["count"]):
                lines.append(f"| {ctx} | {stats['count']} | {stats['avg_minutes']}min |")

        lines.extend([
            "",
            f"---",
            f"*生成于 {data['generated_at'][:19]}*",
        ])

        return "\n".join(lines)

    def _load_jsonl(self, filename: str) -> List[Dict[str, Any]]:
        path = self._base / filename
        if not path.exists():
            return []
        records = []
        for line in path.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    def _count_stale(self, projects: List[Dict[str, Any]], days: int = 7) -> int:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        return sum(
            1 for p in projects
            if p.get("status") == "active"
            and p.get("updated_at", "") < cutoff
        )
