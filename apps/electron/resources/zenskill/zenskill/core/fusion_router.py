"""多信号融合路由器 (PROP-20260712-089)

将多个异构信号源的评分加权聚合，输出统一的路由决策。

用法:
    from zenskill.core.fusion_router import FusionRouter
    from zenskill.core.routing_signal import KeywordRoutingSignal, SemanticRoutingSignal

    router = FusionRouter()
    router.register_signal(KeywordRoutingSignal(weight=0.3))
    router.register_signal(SemanticRoutingSignal(weight=0.3))

    result = router.route("分析数据", context)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .protocols import RoutingCandidate, RoutingContext, RoutingDecision
from .routing_signal import RoutingSignalProvider, SignalScore


@dataclass
class FusionResult:
    """融合路由结果"""
    task: str
    context: Optional[RoutingContext]
    total_score: float
    signal_scores: List[SignalScore]
    candidates: List[RoutingCandidate]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "total_score": round(self.total_score, 4),
            "signal_scores": [s.to_dict() for s in self.signal_scores],
            "candidates": [c.to_dict() for c in self.candidates],
        }


class FusionRouter:
    """多信号融合路由器

    支持:
    - 注册多个 RoutingSignalProvider
    - 可配置权重聚合
    - 信号源可热插拔
    - 与 RuleEngine + SkillHandler Protocol 集成
    """

    def __init__(self) -> None:
        self._signals: List[RoutingSignalProvider] = []
        self._candidates: List[RoutingCandidate] = []

    def register_signal(self, signal: RoutingSignalProvider) -> None:
        """注册信号源"""
        self._signals.append(signal)

    def unregister_signal(self, name: str) -> bool:
        """注销信号源"""
        for i, s in enumerate(self._signals):
            if s.signal_name == name:
                self._signals.pop(i)
                return True
        return False

    def register_candidate(self, candidate: RoutingCandidate) -> None:
        """注册路由候选"""
        self._candidates.append(candidate)

    def clear_candidates(self) -> None:
        """清空候选列表"""
        self._candidates.clear()

    def compute_signals(
        self, task: str, context: Optional[RoutingContext] = None
    ) -> List[SignalScore]:
        """计算所有信号源的评分"""
        scores = []
        for signal in self._signals:
            raw = signal.score(task, context)
            weighted = raw * signal.weight
            scores.append(SignalScore(
                signal_name=signal.signal_name,
                raw_score=raw,
                weighted_score=weighted,
                weight=signal.weight,
            ))
        return scores

    def fuse_scores(
        self, signal_scores: List[SignalScore]
    ) -> float:
        """融合信号评分（加权平均）"""
        if not signal_scores:
            return 0.0

        total_weight = sum(s.weight for s in signal_scores)
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(s.weighted_score for s in signal_scores)
        return weighted_sum / total_weight

    def route(
        self, task: str, context: Optional[RoutingContext] = None
    ) -> FusionResult:
        """融合路由：计算信号评分 + 匹配候选"""
        # 1. 计算信号评分
        signal_scores = self.compute_signals(task, context)
        total_score = self.fuse_scores(signal_scores)

        # 2. 匹配候选（基于信号评分调整置信度）
        matched_candidates = []
        for cand in self._candidates:
            adjusted_confidence = cand.confidence * total_score
            if adjusted_confidence > 0.1:  # 最低阈值
                matched_candidates.append(RoutingCandidate(
                    skill_id=cand.skill_id,
                    confidence=adjusted_confidence,
                    role=cand.role,
                ))

        # 3. 按置信度排序
        matched_candidates.sort(key=lambda c: c.confidence, reverse=True)

        return FusionResult(
            task=task,
            context=context,
            total_score=total_score,
            signal_scores=signal_scores,
            candidates=matched_candidates,
        )

    def route_with_decision(
        self, task: str, context: Optional[RoutingContext] = None
    ) -> Optional[RoutingDecision]:
        """融合路由并返回完整决策记录"""
        result = self.route(task, context)

        if not result.candidates:
            return None

        best = result.candidates[0]
        return RoutingDecision(
            task=task,
            context=context,
            skill_id=best.skill_id,
            confidence=best.confidence,
            signal_scores={s.signal_name: s.raw_score for s in result.signal_scores},
        )

    def list_signals(self) -> List[Dict[str, Any]]:
        """列出已注册的信号源"""
        return [
            {
                "name": s.signal_name,
                "weight": s.weight,
                "type": type(s).__name__,
            }
            for s in self._signals
        ]


# 全局单例
fusion_router = FusionRouter()
