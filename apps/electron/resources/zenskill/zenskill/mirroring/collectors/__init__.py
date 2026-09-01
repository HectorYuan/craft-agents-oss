"""
智能体生态采集层

数据源：Claude Code / ZenSkill / OpenClaw / CrewAI / LangGraph
"""

from .base import BaseCollector, CollectorMeta, DataSensitivity
from .registry import CollectorRegistry, collector_registry

__all__ = [
    "BaseCollector",
    "CollectorMeta",
    "DataSensitivity",
    "CollectorRegistry",
    "collector_registry",
]
