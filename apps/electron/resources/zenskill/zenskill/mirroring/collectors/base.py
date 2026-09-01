"""
采集器基类

所有数据源采集器都必须实现此接口。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class DataSensitivity(Enum):
    LOW = "low"              # 统计数据，无个人信息
    MEDIUM = "medium"        # 普通交互内容
    HIGH = "high"            # 可能含敏感内容
    CRITICAL = "critical"    # 必须本地处理


@dataclass
class CollectorMeta:
    """采集器元数据"""
    name: str
    version: str = "0.1.0"
    description: str = ""
    sensitivity: DataSensitivity = DataSensitivity.MEDIUM
    data_source: str = ""


class BaseCollector(ABC):
    """采集器基类"""

    meta: CollectorMeta

    @abstractmethod
    def is_available(self) -> bool:
        """检测此数据源是否可用"""

    @abstractmethod
    def collect_full(self) -> List[Dict[str, Any]]:
        """全量采集

        返回统一格式的事件列表：
        {
            "source": str,       # 数据来源
            "event_type": str,   # 事件类型
            "timestamp": float,  # Unix 时间戳
            "signal": dict,      # 提取的信号
            "sensitivity": str,  # 敏感级别
        }
        """

    def collect_incremental(self, since: float) -> List[Dict[str, Any]]:
        """增量采集 — 默认回退到全量"""
        all_events = self.collect_full()
        return [e for e in all_events if e.get("timestamp", 0) > since]

    def get_privacy_rules(self) -> Dict[str, List[str]]:
        """返回需要过滤的敏感字段"""
        return {
            "hash_fields": ["user_id", "project", "sessionId"],
            "remove_fields": ["api_key", "password", "token", "secret"],
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取采集器统计信息"""
        try:
            events = self.collect_full()
            return {
                "total_events": len(events),
                "available": self.is_available(),
                "sensitivity": self.meta.sensitivity.value,
            }
        except Exception:
            return {"total_events": 0, "available": False, "error": "采集失败"}
