"""
8.7Z: GTD 健康度评分系统

GTD 健康度评分: 捕获率/完成率/清理率/能量效率/Review 频率
年度 GTD 回顾: 完成 Action 总数、最活跃 Project、最高效时段
与 ZenSkill 技能成长联动的综合评分卡
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from zenskill.core.paths import get_user_data_dir

logger = logging.getLogger(__name__)

# 权重配置
HEALTH_WEIGHTS = {
    "capture_rate": 0.20,      # 捕获率: Inbox 处理效率
    "completion_rate": 0.25,   # 完成率: Action 完成比例
    "cleanup_rate": 0.15,      # 清理率: 项目/孵化清理效率
    "energy_efficiency": 0.20, # 能量效率: 能量投入产出比
    "review_frequency": 0.20,  # Review 频率: 回顾规律性
}


class GTDHealthEngine:
    """GTD 健康度评分引擎"""

    def __init__(self, data_dir: str = ""):
        self._data_dir = data_dir or str(get_user_data_dir())
        self._base = Path(self._data_dir) / "gtd"

    def compute_health(self, days: int = 30) -> Dict[str, Any]:
        """计算 GTD 健康度评分"""
        now = datetime.now()
        start = now - timedelta(days=days)

        actions = self._load_jsonl("actions.jsonl")
        projects = self._load_jsonl("projects.jsonl")
        inbox = self._load_jsonl("inbox.jsonl")
        calendar = self._load_jsonl("calendar.jsonl")

        # 1. 捕获率: Inbox 处理效率
        inbox_total = len([i for i in inbox if i.get("created_at", "") >= start.isoformat()])
        inbox_done = len([
            i for i in inbox
            if i.get("created_at", "") >= start.isoformat()
            and i.get("status") != "pending"
        ])
        capture_rate = inbox_done / max(1, inbox_total)

        # 2. 完成率: Action 完成比例
        actions_in_period = [
            a for a in actions
            if a.get("created_at", "") >= start.isoformat()
            or a.get("completed_at", "") >= start.isoformat()
        ]
        done_actions = [a for a in actions_in_period if a.get("status") == "done"]
        actions_done_count = len(done_actions)
        completion_rate = actions_done_count / max(1, len(actions_in_period))

        # 3. 清理率: 项目/孵化清理效率
        projects_active = len([p for p in projects if p.get("status") == "active"])
        projects_total = len(projects)
        projects_done = len([p for p in projects if p.get("status") == "done"])
        cleanup_rate = projects_done / max(1, projects_total)

        # 4. 能量效率: 能量投入产出比
        energy_invested = sum(
            a.get("energy_invested", a.get("energy_required", 0))
            for a in done_actions
        )
        # 产出价值 = 完成的 Action 数量 * 平均优先级
        def _priority_value(p):
            if isinstance(p, (int, float)):
                return float(p)
            if isinstance(p, str):
                # P0=1.0, P1=0.8, P2=0.6, P3=0.4
                mapping = {"P0": 1.0, "P1": 0.8, "P2": 0.6, "P3": 0.4}
                return mapping.get(p.upper(), 0.5)
            return 0.5

        avg_priority = sum(_priority_value(a.get("priority", 0.5)) for a in done_actions) / max(1, actions_done_count)
        output_value = actions_done_count * avg_priority
        energy_efficiency = output_value / max(1, energy_invested) if energy_invested > 0 else 0.5

        # 5. Review 频率: 回顾规律性 (基于日历事件)
        review_events = [
            e for e in calendar
            if "review" in e.get("title", "").lower()
            or "回顾" in e.get("title", "")
        ]
        review_count = len(review_events)
        # 假设每周至少应该回顾一次
        expected_reviews = days / 7
        review_frequency = min(1.0, review_count / max(1, expected_reviews))

        # 综合评分
        scores = {
            "capture_rate": capture_rate,
            "completion_rate": completion_rate,
            "cleanup_rate": cleanup_rate,
            "energy_efficiency": min(1.0, energy_efficiency),
            "review_frequency": review_frequency,
        }

        weighted_score = sum(
            scores[k] * HEALTH_WEIGHTS[k]
            for k in HEALTH_WEIGHTS
        )

        # 评级
        if weighted_score >= 0.9:
            grade = "S"
            label = "卓越"
        elif weighted_score >= 0.75:
            grade = "A"
            label = "优秀"
        elif weighted_score >= 0.6:
            grade = "B"
            label = "良好"
        elif weighted_score >= 0.4:
            grade = "C"
            label = "一般"
        else:
            grade = "D"
            label = "需改进"

        return {
            "health_score": round(weighted_score * 100, 1),
            "grade": grade,
            "label": label,
            "scores": {k: round(v * 100, 1) for k, v in scores.items()},
            "details": {
                "inbox_total": inbox_total,
                "inbox_done": inbox_done,
                "actions_total": len(actions_in_period),
                "actions_done": actions_done_count,
                "projects_active": projects_active,
                "projects_done": projects_done,
                "energy_invested": energy_invested,
                "review_count": review_count,
            },
            "period_days": days,
            "generated_at": now.isoformat(),
        }

    def annual_review(self, year: int = 0) -> Dict[str, Any]:
        """年度 GTD 回顾"""
        if not year:
            year = datetime.now().year

        actions = self._load_jsonl("actions.jsonl")
        projects = self._load_jsonl("projects.jsonl")

        # 年度 Action 统计
        year_actions = [
            a for a in actions
            if a.get("created_at", "").startswith(str(year))
            or a.get("completed_at", "").startswith(str(year))
        ]
        year_done = [a for a in year_actions if a.get("status") == "done"]

        # 月度趋势
        monthly_trend = defaultdict(int)
        for a in year_done:
            completed = a.get("completed_at", "")
            if completed and completed.startswith(str(year)):
                month = completed[5:7]
                monthly_trend[month] += 1

        # 最活跃项目
        project_activity = Counter()
        for a in year_done:
            pid = a.get("project_id", "")
            if pid:
                project_activity[pid] += 1

        # 最高效时段 (按小时统计)
        hourly = Counter()
        for a in year_done:
            completed = a.get("completed_at", "")
            if completed:
                try:
                    dt = datetime.fromisoformat(completed)
                    hourly[dt.hour] += 1
                except ValueError:
                    pass

        peak_hour = hourly.most_common(1)[0] if hourly else (0, 0)

        # 上下文分布
        context_counter = Counter()
        for a in year_done:
            ctx = a.get("contexts", a.get("context", "general"))
            if isinstance(ctx, list):
                context_counter.update(ctx)
            else:
                context_counter[ctx] += 1

        return {
            "year": year,
            "actions": {
                "total": len(year_actions),
                "done": len(year_done),
                "completion_rate": len(year_done) / max(1, len(year_actions)),
            },
            "monthly_trend": dict(sorted(monthly_trend.items())),
            "most_active_projects": [
                {"project_id": pid, "actions": count}
                for pid, count in project_activity.most_common(5)
            ],
            "peak_hour": {"hour": peak_hour[0], "count": peak_hour[1]},
            "top_contexts": dict(context_counter.most_common(5)),
            "generated_at": datetime.now().isoformat(),
        }

    def skill_growth_card(self, skill_id: str = "zenskill-core") -> Dict[str, Any]:
        """与 ZenSkill 技能成长联动的综合评分卡"""
        health = self.compute_health()
        actions = self._load_jsonl("actions.jsonl")
        projects = self._load_jsonl("projects.jsonl")

        # 技能关联的 Action
        skill_actions = [a for a in actions if a.get("skill_id") == skill_id]
        skill_done = [a for a in skill_actions if a.get("status") == "done"]

        # 技能关联的 Project
        skill_projects = [p for p in projects if p.get("skill_id") == skill_id]

        # 计算技能贡献度
        total_actions = len(actions)
        skill_ratio = len(skill_actions) / max(1, total_actions)

        return {
            "skill_id": skill_id,
            "health_score": health["health_score"],
            "health_grade": health["grade"],
            "skill_actions": {
                "total": len(skill_actions),
                "done": len(skill_done),
                "ratio": round(skill_ratio * 100, 1),
            },
            "skill_projects": {
                "total": len(skill_projects),
                "active": len([p for p in skill_projects if p.get("status") == "active"]),
            },
            "recommendation": self._generate_recommendation(health, skill_ratio),
            "generated_at": datetime.now().isoformat(),
        }

    def format_health_markdown(self, data: Dict[str, Any]) -> str:
        """格式化健康度报告为 Markdown"""
        grade_emoji = {"S": "🏆", "A": "⭐", "B": "👍", "C": "⚠️", "D": "❌"}
        emoji = grade_emoji.get(data["grade"], "")

        lines = [
            "# GTD 健康度报告",
            "",
            f"## 综合评分: {emoji} {data['health_score']} ({data['grade']} {data['label']})",
            "",
            "## 分项评分",
            "",
            "| 维度 | 得分 | 权重 |",
            "|------|------|------|",
        ]

        labels = {
            "capture_rate": "捕获率",
            "completion_rate": "完成率",
            "cleanup_rate": "清理率",
            "energy_efficiency": "能量效率",
            "review_frequency": "Review频率",
        }

        for key, weight in HEALTH_WEIGHTS.items():
            score = data["scores"][key]
            label = labels.get(key, key)
            bar = "█" * int(score / 10)
            lines.append(f"| {label} | {bar} {score}% | {int(weight*100)}% |")

        lines.extend([
            "",
            "## 详细数据",
            "",
            f"- 📥 Inbox: {data['details']['inbox_done']}/{data['details']['inbox_total']} 处理",
            f"- ✅ Action: {data['details']['actions_done']}/{data['details']['actions_total']} 完成",
            f"- 📦 Project: {data['details']['projects_done']} 完成, {data['details']['projects_active']} 活跃",
            f"- ⚡ 能量投入: {data['details']['energy_invested']} 单位",
            f"- 🔄 Review: {data['details']['review_count']} 次 ({data['period_days']}天)",
            "",
            f"---",
            f"*生成于 {data['generated_at'][:19]}*",
        ])

        return "\n".join(lines)

    def _generate_recommendation(self, health: Dict, skill_ratio: float) -> str:
        """生成改进建议"""
        suggestions = []

        if health["scores"]["capture_rate"] < 60:
            suggestions.append("提高 Inbox 处理效率，每日清零")
        if health["scores"]["completion_rate"] < 60:
            suggestions.append("提高 Action 完成率，减少拖延")
        if health["scores"]["energy_efficiency"] < 60:
            suggestions.append("优化能量分配，高能量做困难事")
        if health["scores"]["review_frequency"] < 60:
            suggestions.append("增加 Review 频率，每周至少回顾一次")
        if skill_ratio < 0.3:
            suggestions.append("增加技能相关 Action，提升技能成长速度")

        if not suggestions:
            return "GTD 状态良好，继续保持！"

        return "建议: " + "; ".join(suggestions[:3])

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
