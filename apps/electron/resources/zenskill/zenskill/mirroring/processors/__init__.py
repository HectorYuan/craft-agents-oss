"""
信号处理器

去重 / 聚合 / NLP 提取。
"""

from .deduplicator import EventDeduplicator
from .aggregator import SignalAggregator
from .nlp import NLPSignalExtractor

__all__ = ["EventDeduplicator", "SignalAggregator", "NLPSignalExtractor"]

