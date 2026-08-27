"""
事件去重引擎

基于信号相似度检测重复事件，避免偏好学习被重复数据污染。
"""

import hashlib
import json
import time
from typing import Any, Dict, List


class EventDeduplicator:
    """事件去重器 — 基于信号指纹"""

    def __init__(self, window_seconds: float = 3600.0):
        self._window = window_seconds
        self._fingerprints: Dict[str, float] = {}

    def deduplicate(self, events: List[Dict]) -> List[Dict]:
        """去重，保留每个时间窗口内的首个事件"""
        now = time.time()
        # 清理过期指纹
        expired = [fp for fp, ts in self._fingerprints.items() if now - ts > self._window]
        for fp in expired:
            del self._fingerprints[fp]

        result = []
        dup_count = 0
        for e in events:
            fp = self._make_fingerprint(e)
            if fp in self._fingerprints:
                dup_count += 1
                continue
            self._fingerprints[fp] = now
            result.append(e)

        return result

    @staticmethod
    def _make_fingerprint(event: Dict) -> str:
        """生成事件指纹（source + signal hash）"""
        source = event.get("source", "")
        signal = event.get("signal", {})
        raw = json.dumps({"s": source, "d": signal}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
