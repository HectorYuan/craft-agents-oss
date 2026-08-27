"""
用户镜像系统

Phase 9A: 用户画像数据层 - 行为事件采集、特征工程、隐私保护
Phase 9B: 偏好学习引擎 - 置信度加权学习、跨项目合并
Phase 9C: 智能体生态采集层 - Claude Code + ZenSkill 多 Agent 统一数据层

快速使用:
    from zenskill.mirroring import EventCollector, PreferenceEngine

    collector = EventCollector()
    collector.record_tool_call("Bash", "git status")

    engine = PreferenceEngine()
    engine.learn_from_history()
    profile = engine.get_profile()
"""

__version__ = "0.1.0"

from .environment_indexer import EnvironmentIndexer
from .event_collector import EventCollector
from .feature_store import FeatureStore
from .models import EventType, FeatureVector, InteractionEvent, UserPrivacyPrefs
from .preference_engine import PreferenceEngine
from .privacy_layer import PrivacyLayer
from .workflow import WorkflowAnalyzer, BottleneckDetector, WorkflowOptimizer, HabitTracker
from .pattern_miner import StatisticalPatternMiner, PatternProfile
from .context_predictor import ContextPredictor, AnomalyDetector, ContextVector
from .gap_detector import GapDetector

# collectors
from .collectors import BaseCollector, CollectorRegistry, collector_registry
from .collectors.claude_code import (
    ClaudeHistoryCollector,
    ClaudeMemoryCollector,
    ClaudePlansCollector,
    ClaudeTasksCollector,
    CoreSettingsCollector,
    ClaudeSessionCollector,
    ClaudeFileHistoryCollector,
    ClaudeShellSnapshotCollector,
)
from .collectors.zenskill import (
    ZenskillEventCollector,
    ZenskillMemoryCollector,
    ZenskillZenloopCollector,
)
from .processors import EventDeduplicator, SignalAggregator, NLPSignalExtractor

__all__ = [
    "EventType",
    "InteractionEvent",
    "FeatureVector",
    "UserPrivacyPrefs",
    "EventCollector",
    "FeatureStore",
    "PreferenceEngine",
    "PrivacyLayer",
    "EnvironmentIndexer",
    "WorkflowAnalyzer",
    "BottleneckDetector",
    "WorkflowOptimizer",
    "HabitTracker",
    "__version__",
    # collectors
    "BaseCollector",
    "CollectorRegistry",
    "collector_registry",
    "ClaudeHistoryCollector",
    "ClaudeMemoryCollector",
    "ClaudePlansCollector",
    "ClaudeTasksCollector",
    "CoreSettingsCollector",
    "ClaudeSessionCollector",
    "ClaudeFileHistoryCollector",
    "ClaudeShellSnapshotCollector",
    "ZenskillEventCollector",
    "ZenskillMemoryCollector",
    "ZenskillZenloopCollector",
    "EventDeduplicator",
    "SignalAggregator",
    "NLPSignalExtractor",
    "WorkflowAnalyzer",
    "StatisticalPatternMiner",
    "PatternProfile",
    "ContextPredictor",
    "AnomalyDetector",
    "ContextVector",
    "GapDetector",
]
