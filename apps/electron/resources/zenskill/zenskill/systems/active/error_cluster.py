"""
错误模式聚类 (7R)

从事件流中识别常见错误类型、频率和改进建议。
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

from zenskill.mirroring.event_collector import EventCollector
from zenskill.mirroring.models import EventType, InteractionEvent


@dataclass
class ErrorCluster:
    pattern: str
    count: int
    percentage: float
    latest_at: float
    examples: List[str]
    suggestion: str


class ErrorClusterAnalyzer:
    PATTERNS = [
        ("执行超时", ["timeout", "timed out", "超时", "耗时"], "先拆分任务，缩短单次执行窗口，并为长任务加入阶段性检查点"),
        ("权限/认证", ["permission", "denied", "forbidden", "unauthorized", "认证", "权限", "拒绝"], "执行前检查凭据、权限范围和目标路径，必要时先做只读探测"),
        ("路径/文件不存在", ["not found", "no such file", "不存在", "找不到", "missing"], "先确认文件路径和工作目录，再执行读写或引用操作"),
        ("格式/语法", ["syntax", "parse", "jsondecode", "格式", "语法", "解析"], "对输入输出增加格式校验，复杂结构优先生成最小样例再扩展"),
        ("网络/API", ["connection", "network", "http", "api", "rate limit", "连接", "网络", "限流"], "区分本地错误与外部服务错误，记录状态码并准备降级路径"),
        ("测试/断言", ["assert", "test failed", "pytest", "测试失败", "断言"], "把失败用例归因到输入、状态或预期差异，再补最小回归验证"),
        ("用户意图理解", ["理解", "不清楚", "歧义", "ambiguous", "unclear"], "遇到模糊需求先复述约束和目标，只在关键分歧处提问"),
    ]

    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id
        self.collector = EventCollector()

    def analyze(self, days: int = 30, limit: int = 200) -> Dict[str, Any]:
        since = time.time() - max(days, 1) * 86400
        events = self._load_error_events(since, limit)
        if not events:
            return {"skill_id": self.skill_id, "status": "empty", "days": days, "total": 0, "clusters": []}

        buckets: Dict[str, List[InteractionEvent]] = defaultdict(list)
        for event in events:
            buckets[self._classify(event)].append(event)

        clusters = []
        for pattern, items in buckets.items():
            examples = [self._event_text(e)[:120] for e in items[-3:]]
            clusters.append(ErrorCluster(
                pattern=pattern,
                count=len(items),
                percentage=round(len(items) / len(events) * 100, 1),
                latest_at=max(e.timestamp for e in items),
                examples=examples,
                suggestion=self._suggestion(pattern),
            ))
        clusters.sort(key=lambda item: (item.count, item.latest_at), reverse=True)

        by_day = Counter(datetime.fromtimestamp(e.timestamp).strftime("%m-%d") for e in events)
        return {
            "skill_id": self.skill_id,
            "status": "ok",
            "days": days,
            "total": len(events),
            "clusters": [cluster.__dict__ for cluster in clusters],
            "daily": dict(sorted(by_day.items())),
            "summary": self._summary(clusters),
        }

    def format_report(self, days: int = 30, limit: int = 200) -> str:
        data = self.analyze(days=days, limit=limit)
        lines = ["🧯 错误模式聚类 (7R)", "═" * 50, ""]
        if data["status"] != "ok":
            lines.append(f"   最近 {days} 天暂无错误事件")
            lines.append("   💡 后续错误会通过 mirroring 事件流自动进入聚类分析")
            return "\n".join(lines)

        lines.append(f"   范围: 最近 {days} 天 | 错误事件: {data['total']} 条")
        lines.append(f"   结论: {data['summary']}")
        lines.append("")
        for cluster in data["clusters"][:5]:
            latest = datetime.fromtimestamp(cluster["latest_at"]).strftime("%m-%d %H:%M")
            lines.append(f"   🔸 {cluster['pattern']}: {cluster['count']} 次 ({cluster['percentage']}%)，最近 {latest}")
            lines.append(f"      建议: {cluster['suggestion']}")
            for example in cluster["examples"][:2]:
                if example:
                    lines.append(f"      例: {example}")
        if data.get("daily"):
            trend = " ".join(f"{day}:{count}" for day, count in list(data["daily"].items())[-7:])
            lines.append("")
            lines.append(f"   近期分布: {trend}")
        return "\n".join(lines)

    def _load_error_events(self, since: float, limit: int) -> List[InteractionEvent]:
        explicit = self.collector.query(event_type=EventType.ERROR, skill_id=self.skill_id, since=since, limit=limit)
        failed = [
            event for event in self.collector.query(skill_id=self.skill_id, since=since, limit=limit)
            if not event.success and event.event_type != EventType.ERROR
        ]
        combined = explicit + failed
        combined.sort(key=lambda event: event.timestamp)
        return combined[-limit:]

    def _classify(self, event: InteractionEvent) -> str:
        text = self._event_text(event).lower()
        for pattern, keywords, _ in self.PATTERNS:
            if any(keyword in text for keyword in keywords):
                return pattern
        return "通用执行错误"

    def _event_text(self, event: InteractionEvent) -> str:
        context = event.context if isinstance(event.context, dict) else {}
        parts = [event.action]
        for key in ("error", "error_message", "message", "stderr", "tool", "command"):
            value = context.get(key)
            if value:
                parts.append(str(value))
        return " | ".join(part for part in parts if part)

    def _suggestion(self, pattern: str) -> str:
        for name, _, suggestion in self.PATTERNS:
            if name == pattern:
                return suggestion
        return "记录更完整的错误上下文，优先复现最小失败路径再修复"

    def _summary(self, clusters: List[ErrorCluster]) -> str:
        top = clusters[0]
        return f"主要错误类型是 {top.pattern} ({top.count} 次，占 {top.percentage}%)"
