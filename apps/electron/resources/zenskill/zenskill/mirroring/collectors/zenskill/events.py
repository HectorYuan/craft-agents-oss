"""
ZenSkill 内部事件采集器

读取已有 events.jsonl，提取事件统计模式。
"""

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from ..base import BaseCollector, CollectorMeta, DataSensitivity


class ZenskillEventCollector(BaseCollector):
    """ZenSkill 内部事件采集器"""

    meta = CollectorMeta(
        name="zenskill-events",
        version="0.1.0",
        description="分析 ZenSkill 已有事件记录，提取工具使用模式",
        sensitivity=DataSensitivity.LOW,
        data_source="~/.zenskill/mirroring/events.jsonl",
    )

    def __init__(self):
        self._events_path = Path.home() / ".zenskill" / "mirroring" / "events.jsonl"

    def is_available(self) -> bool:
        return self._events_path.exists()

    def collect_full(self) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []

        now = time.time()
        events = self._load_events()
        if not events:
            return []

        event_type_counts: Counter = Counter()
        hour_counts: Counter = Counter()
        session_counts: Counter = Counter()
        total = len(events)

        for e in events:
            event_type_counts[e.get("event_type", "unknown")] += 1
            ts = e.get("timestamp", 0)
            if ts:
                try:
                    from datetime import datetime
                    hour = datetime.fromtimestamp(ts).hour
                    hour_counts[hour] += 1
                except Exception:
                    pass
            sid = e.get("session_id", "")
            if sid:
                session_counts[sid] += 1

        peak_hour = max(hour_counts, key=hour_counts.get) if hour_counts else -1

        return [{
            "source": "zenskill_events",
            "timestamp": now,
            "signal": {
                "total_events": total,
                "event_type_distribution": dict(event_type_counts),
                "sessions": len(session_counts),
                "peak_hour": peak_hour,
                "hour_distribution": dict(hour_counts),
            },
            "sensitivity": "low",
        }]

    def _load_events(self) -> List[Dict]:
        events = []
        try:
            for line in open(self._events_path, encoding="utf-8"):
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        except Exception:
            pass
        return events
