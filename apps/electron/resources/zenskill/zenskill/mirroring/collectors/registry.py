"""
采集器注册表

管理所有采集器的注册、发现和批量执行。
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class CollectorRegistry:
    """采集器注册表 — 单例"""

    _instance: "CollectorRegistry | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._collectors: Dict[str, Any] = {}
            cls._instance._initialized = False
        return cls._instance

    def register(self, collector) -> None:
        """注册采集器"""
        self._collectors[collector.meta.name] = collector
        logger.info(f"注册采集器: {collector.meta.name}")

    def list_all(self) -> List[Dict[str, Any]]:
        """列出所有已注册采集器及状态"""
        result = []
        for name, c in self._collectors.items():
            available = c.is_available()
            result.append({
                "name": name,
                "description": c.meta.description,
                "available": available,
                "sensitivity": c.meta.sensitivity.value,
                "data_source": c.meta.data_source,
            })
        return result

    def get(self, name: str):
        """按名称获取采集器"""
        return self._collectors.get(name)

    def run(self, name: str, incremental: bool = False, since: float = 0) -> List[Dict[str, Any]]:
        """运行指定采集器"""
        collector = self._collectors.get(name)
        if collector is None:
            raise ValueError(f"采集器不存在: {name}")

        if incremental and hasattr(collector, "collect_incremental"):
            return collector.collect_incremental(since)
        return collector.collect_full()

    def run_all(self, incremental: bool = False, since: float = 0,
                process: bool = True) -> Dict[str, List[Dict[str, Any]]]:
        """运行所有已注册的采集器，可选后处理管道"""
        results = {}
        total_events = 0
        all_events: List[Dict] = []

        for name, collector in self._collectors.items():
            try:
                if not collector.is_available():
                    results[name] = {"available": False, "events": []}
                    continue

                if incremental:
                    events = collector.collect_incremental(since)
                else:
                    events = collector.collect_full()

                results[name] = {"available": True, "count": len(events)}
                total_events += len(events)
                all_events.extend(events)

                # 写入事件到 mirroring 的 events.jsonl
                self._write_events(events, collector)

            except Exception as e:
                logger.error(f"采集器 {name} 失败: {e}")
                results[name] = {"available": False, "error": str(e)}

        results["_total"] = {"collectors": len(self._collectors), "total_events": total_events}

        # 后处理管道：去重 → NLP → 聚合
        if process and all_events:
            pipeline = self._run_pipeline(all_events)
            results["_pipeline"] = pipeline

        return results

    def _run_pipeline(self, events: List[Dict]) -> Dict[str, Any]:
        """运行处理管道：去重 → NLP → 聚合"""
        try:
            from ..processors import EventDeduplicator, SignalAggregator, NLPSignalExtractor
        except ImportError:
            return {}

        dedup = EventDeduplicator()
        unique = dedup.deduplicate(events)

        nlp = NLPSignalExtractor()
        nlp_signals = nlp.extract(unique)

        agg = SignalAggregator()
        aggregation = agg.aggregate(unique)

        return {
            "dedup_removed": len(events) - len(unique),
            "nlp": nlp_signals,
            "insights": aggregation.get("insights", []),
        }

    def _write_events(self, events: List[Dict], collector) -> None:
        """将采集事件写入 mirroring 事件文件"""
        from pathlib import Path
        import time

        from zenskill.core.paths import append_jsonl_unlocked, file_lock

        try:
            from zenskill.core.paths import get_mirroring_dir
            mirror_dir = get_mirroring_dir()
        except Exception:
            mirror_dir = Path.home() / ".zenskill" / "mirroring"

        mirror_dir.mkdir(parents=True, exist_ok=True)
        events_file = mirror_dir / "events.jsonl"

        with file_lock(events_file, timeout=1.0):
            for event in events:
                record = {
                    "source": collector.meta.name,
                    "timestamp": event.get("timestamp", time.time()),
                    "signal": event.get("signal", {}),
                    "sensitivity": collector.meta.sensitivity.value,
                }
                append_jsonl_unlocked(events_file, record)

    @property
    def count(self) -> int:
        return len(self._collectors)


# 全局单例
collector_registry = CollectorRegistry()
