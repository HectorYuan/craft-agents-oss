"""
成长分析器 (7T/7U)

提供多维对比分析与成长路径回放。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from zenskill.core.paths import SkillStateManager
from zenskill.systems.visualization.metrics_store import MetricsStore, MetricSnapshot


DIMENSIONS = ["proficiency", "stability", "satisfaction", "responsiveness", "memory", "composite"]
DIM_NAMES = {
    "proficiency": "熟练度",
    "stability": "稳定性",
    "satisfaction": "满意度",
    "responsiveness": "响应力",
    "memory": "记忆度",
    "composite": "综合",
}


class GrowthAnalyzer:
    """多维成长对比与路径回放"""

    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id
        self.store = MetricsStore(skill_id)

    def compare(self, window: int = 10) -> Dict[str, Any]:
        snapshots = self.store.get_all_snapshots()
        if len(snapshots) < 2:
            return {"skill_id": self.skill_id, "status": "insufficient", "snapshot_count": len(snapshots), "dimensions": []}

        current = snapshots[-1]
        baseline = snapshots[-min(max(window, 2), len(snapshots))]
        dimensions = [self._compare_dimension(dim, baseline, current) for dim in DIMENSIONS]
        dimensions.sort(key=lambda item: item["change"], reverse=True)

        positive = [d for d in dimensions if d["change"] > 0]
        negative = [d for d in dimensions if d["change"] < 0]
        fastest = positive[0] if positive else dimensions[0]
        weakest = min(dimensions, key=lambda item: item["current"])

        return {
            "skill_id": self.skill_id,
            "status": "ok",
            "snapshot_count": len(snapshots),
            "window": min(window, len(snapshots)),
            "baseline_date": baseline.date,
            "current_date": current.date,
            "dimensions": dimensions,
            "fastest": fastest,
            "weakest": weakest,
            "declining": negative,
            "summary": self._build_compare_summary(fastest, weakest, negative),
        }

    def replay(self, limit: int = 12) -> Dict[str, Any]:
        snapshots = self.store.get_all_snapshots()
        state = SkillStateManager(self.skill_id).load()
        if not snapshots:
            return {"skill_id": self.skill_id, "status": "insufficient", "events": [], "summary": "暂无成长快照"}

        events = [self._snapshot_event("起点", snapshots[0])]
        events.extend(self._level_change_events(snapshots))
        events.extend(self._growth_spurt_events(snapshots))
        events.extend(self._milestone_events(state))
        if len(snapshots) > 1:
            events.append(self._snapshot_event("当前", snapshots[-1]))

        events.sort(key=lambda item: item.get("timestamp", 0))
        events = self._dedupe_events(events)[-limit:]

        first = snapshots[0].ability_scores.get("composite", 0)
        last = snapshots[-1].ability_scores.get("composite", 0)
        return {
            "skill_id": self.skill_id,
            "status": "ok",
            "snapshot_count": len(snapshots),
            "events": events,
            "summary": f"综合能力 {first} → {last}，累计变化 {last - first:+.0f}，当前境界 {state.get('level', snapshots[-1].level)}",
        }

    def format_compare(self, window: int = 10) -> str:
        data = self.compare(window)
        lines = ["📊 多维对比分析 (7T)", "═" * 50, ""]
        if data["status"] != "ok":
            lines.append(f"   数据积累中：当前 {data['snapshot_count']} 个采样点，至少需要 2 个")
            return "\n".join(lines)

        lines.append(f"   范围: {data['baseline_date']} → {data['current_date']} ({data['window']} 个采样点)")
        lines.append(f"   结论: {data['summary']}")
        lines.append("")
        for item in data["dimensions"]:
            arrow = "↗" if item["change"] > 0 else "↘" if item["change"] < 0 else "→"
            lines.append(
                f"   {arrow} {item['name']:6s} {item['previous']:>3.0f} → {item['current']:>3.0f} "
                f"({item['change']:+.0f}, {item['change_pct']:+.1f}%)"
            )
        if data["declining"]:
            lines.append("")
            lines.append("   ⚠️ 需关注: " + "、".join(item["name"] for item in data["declining"][:3]))
        return "\n".join(lines)

    def format_replay(self, limit: int = 12) -> str:
        data = self.replay(limit)
        lines = ["🕰️ 成长路径回放 (7U)", "═" * 50, ""]
        if data["status"] != "ok":
            lines.append("   暂无成长快照，继续使用后将自动生成路径")
            return "\n".join(lines)

        lines.append(f"   {data['summary']}")
        lines.append("")
        for event in data["events"]:
            date = event.get("date", "????-??-??")
            title = event.get("title", "事件")
            detail = event.get("detail", "")
            lines.append(f"   [{date}] {title}: {detail}")
        return "\n".join(lines)

    def _compare_dimension(self, dim: str, baseline: MetricSnapshot, current: MetricSnapshot) -> Dict[str, Any]:
        prev = self._score(baseline, dim)
        cur = self._score(current, dim)
        change = cur - prev
        return {
            "dimension": dim,
            "name": DIM_NAMES.get(dim, dim),
            "previous": prev,
            "current": cur,
            "change": change,
            "change_pct": round(change / max(prev, 1) * 100, 1) if prev > 0 else 0,
        }

    def _score(self, snapshot: MetricSnapshot, dim: str) -> float:
        value = snapshot.ability_scores.get(dim, 0)
        return float(value) if isinstance(value, (int, float)) else 0.0

    def _build_compare_summary(self, fastest: Dict[str, Any], weakest: Dict[str, Any], declining: List[Dict[str, Any]]) -> str:
        parts = [f"增长最快是 {fastest['name']} ({fastest['change']:+.0f})", f"当前短板是 {weakest['name']} ({weakest['current']:.0f})"]
        if declining:
            parts.append(f"下降维度 {len(declining)} 个")
        return "；".join(parts)

    def _snapshot_event(self, title: str, snapshot: MetricSnapshot) -> Dict[str, Any]:
        return {
            "timestamp": snapshot.timestamp,
            "date": snapshot.date,
            "title": title,
            "detail": f"{snapshot.level}，综合 {snapshot.ability_scores.get('composite', 0)}，交互 {snapshot.interaction_count} 次",
        }

    def _level_change_events(self, snapshots: List[MetricSnapshot]) -> List[Dict[str, Any]]:
        events = []
        prev = snapshots[0].level
        for snap in snapshots[1:]:
            if snap.level != prev:
                events.append({
                    "timestamp": snap.timestamp,
                    "date": snap.date,
                    "title": "境界变化",
                    "detail": f"{prev} → {snap.level}",
                })
                prev = snap.level
        return events

    def _growth_spurt_events(self, snapshots: List[MetricSnapshot]) -> List[Dict[str, Any]]:
        events = []
        for prev, cur in zip(snapshots, snapshots[1:]):
            change = self._score(cur, "composite") - self._score(prev, "composite")
            if change >= 3:
                events.append({
                    "timestamp": cur.timestamp,
                    "date": cur.date,
                    "title": "成长跃迁",
                    "detail": f"综合能力单段提升 {change:+.0f}",
                })
        return events

    def _milestone_events(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        events = []
        for item in state.get("milestones", []) if isinstance(state.get("milestones", []), list) else []:
            timestamp = item.get("timestamp") or item.get("achieved_at") or ""
            events.append({
                "timestamp": self._parse_time(timestamp),
                "date": str(timestamp)[:10] if timestamp else "????-??-??",
                "title": "里程碑",
                "detail": f"{item.get('level', '')} {item.get('achievement', '')}".strip(),
            })
        return events

    def _parse_time(self, value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return 0.0
        return 0.0

    def _dedupe_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        result = []
        for event in events:
            key = (event.get("date"), event.get("title"), event.get("detail"))
            if key in seen:
                continue
            seen.add(key)
            result.append(event)
        return result
