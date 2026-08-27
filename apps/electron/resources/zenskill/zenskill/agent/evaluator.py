"""
MU2-H: 代理性能评估与进化 (Agent Evaluation & Evolution)

多 Agent 性能评估体系：
1. 质量 — 产出质量评分
2. 效率 — 完成时间、资源消耗
3. 可靠性 — 成功率、故障率
4. 协作性 — 协作顺畅度
5. 进化 — A/B 测试、优胜劣汰
"""

from __future__ import annotations

import json
import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class EvaluationMetric(str, Enum):
    """评估指标"""
    QUALITY = "quality"               # 产出质量
    EFFICIENCY = "efficiency"         # 效率（速度）
    RELIABILITY = "reliability"       # 可靠性（成功率）
    COLLABORATION = "collaboration"   # 协作性
    INNOVATION = "innovation"         # 创新性
    LEARNING = "learning"             # 学习速度


@dataclass
class PerformanceRecord:
    """单次执行记录"""
    agent_id: str
    task_id: str
    task_type: str
    success: bool
    duration_ms: float = 0
    quality_score: float = 0.0       # 0-1
    collaboration_score: float = 0.0 # 0-1
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "quality": self.quality_score,
            "collaboration": self.collaboration_score,
            "timestamp": datetime.fromtimestamp(self.timestamp).isoformat(),
        }


@dataclass
class AgentScore:
    """Agent 综合评分"""
    agent_id: str
    role: str
    total_tasks: int = 0
    success_count: int = 0
    total_duration_ms: float = 0
    avg_quality: float = 0.0
    avg_collaboration: float = 0.0
    recent_tasks: list[str] = field(default_factory=list)
    trend: str = "stable"            # improving / stable / declining
    last_active: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.success_count / max(self.total_tasks, 1)

    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / max(self.total_tasks, 1)

    def composite_score(self) -> float:
        """综合评分 0-100"""
        s = (
            self.success_rate * 40 +           # 可靠性 40%
            self.avg_quality * 30 +            # 质量 30%
            self.avg_collaboration * 20 +      # 协作 20%
            min(1.0, 1000 / max(self.avg_duration_ms, 1)) * 10  # 效率 10%
        )
        return round(s * 100, 1)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "total_tasks": self.total_tasks,
            "success_rate": round(self.success_rate, 2),
            "avg_duration_ms": round(self.avg_duration_ms, 1),
            "avg_quality": round(self.avg_quality, 2),
            "avg_collaboration": round(self.avg_collaboration, 2),
            "composite_score": self.composite_score(),
            "trend": self.trend,
        }


class AgentEvaluator:
    """
    Agent 性能评估器

    追踪、评分、进化多 Agent 的性能。
    """

    def __init__(self, window_size: int = 100):
        self._records: list[PerformanceRecord] = []
        self._window_size = window_size
        self._scores: dict[str, AgentScore] = {}

    # ── 记录 ──

    def record(self, record: PerformanceRecord) -> None:
        """记录一次执行"""
        self._records.append(record)
        if len(self._records) > self._window_size * 10:
            self._records = self._records[-self._window_size * 10:]
        self._update_score(record)

    def _update_score(self, record: PerformanceRecord) -> None:
        """更新 Agent 评分"""
        if record.agent_id not in self._scores:
            self._scores[record.agent_id] = AgentScore(
                agent_id=record.agent_id,
                role=record.metadata.get("role", "unknown"),
            )

        score = self._scores[record.agent_id]
        score.total_tasks += 1
        if record.success:
            score.success_count += 1
        score.total_duration_ms += record.duration_ms
        score.avg_quality = (
            score.avg_quality * (score.total_tasks - 1) + record.quality_score
        ) / score.total_tasks
        score.avg_collaboration = (
            score.avg_collaboration * (score.total_tasks - 1) + record.collaboration_score
        ) / score.total_tasks
        score.recent_tasks.append(record.task_id)
        if len(score.recent_tasks) > 20:
            score.recent_tasks = score.recent_tasks[-20:]
        score.last_active = record.timestamp
        score.trend = self._calculate_trend(record.agent_id)

    # ── 查询 ──

    def get_score(self, agent_id: str) -> Optional[AgentScore]:
        return self._scores.get(agent_id)

    def get_all_scores(self) -> list[AgentScore]:
        return list(self._scores.values())

    def get_leaderboard(self, metric: str = "composite", top_n: int = 10) -> list[dict]:
        """获取排行榜"""
        scores = self.get_all_scores()
        if metric == "composite":
            scores.sort(key=lambda s: s.composite_score(), reverse=True)
        elif metric == "success_rate":
            scores.sort(key=lambda s: s.success_rate, reverse=True)
        elif metric == "quality":
            scores.sort(key=lambda s: s.avg_quality, reverse=True)
        return [s.to_dict() for s in scores[:top_n]]

    def get_agent_history(self, agent_id: str, limit: int = 50) -> list[dict]:
        """获取 Agent 历史记录"""
        records = [r for r in self._records if r.agent_id == agent_id]
        return [r.to_dict() for r in records[-limit:]]

    def _calculate_trend(self, agent_id: str) -> str:
        """计算趋势"""
        records = [r for r in self._records if r.agent_id == agent_id]
        if len(records) < 10:
            return "stable"

        # 比较最近 5 条和前 5 条的成功率
        recent = records[-5:]
        earlier = records[-10:-5]

        if not earlier:
            return "stable"

        recent_rate = sum(1 for r in recent if r.success) / max(len(recent), 1)
        earlier_rate = sum(1 for r in earlier if r.success) / max(len(earlier), 1)

        if recent_rate > earlier_rate + 0.1:
            return "improving"
        elif recent_rate < earlier_rate - 0.1:
            return "declining"
        return "stable"

    # ── 统计 ──

    def summary(self) -> dict:
        """评估摘要"""
        scores = self.get_all_scores()
        return {
            "total_agents": len(scores),
            "total_records": len(self._records),
            "avg_composite": round(
                sum(s.composite_score() for s in scores) / max(len(scores), 1), 1
            ),
            "avg_success_rate": round(
                sum(s.success_rate for s in scores) / max(len(scores), 1), 2
            ),
            "avg_quality": round(
                sum(s.avg_quality for s in scores) / max(len(scores), 1), 2
            ),
            "by_trend": {
                "improving": len([s for s in scores if s.trend == "improving"]),
                "stable": len([s for s in scores if s.trend == "stable"]),
                "declining": len([s for s in scores if s.trend == "declining"]),
            },
        }


# ============================================================
# A/B 测试框架
# ============================================================

@dataclass
class ABTestConfig:
    """A/B 测试配置"""
    experiment_id: str
    description: str
    variants: list[str]              # variant names
    traffic_split: list[float]       # 流量分配比例
    metric: EvaluationMetric = EvaluationMetric.QUALITY
    min_samples: int = 10            # 最小样本量
    start_time: float = field(default_factory=time.time)


@dataclass
class ABTestResult:
    """A/B 测试结果"""
    experiment_id: str
    winner: str                      # 获胜 variant
    variant_stats: dict[str, dict]   # variant → stats
    confidence: float                 # 置信度
    significant: bool                 # 是否显著


class ABTestManager:
    """A/B 测试管理器"""

    def __init__(self):
        self._experiments: dict[str, ABTestConfig] = {}
        self._results: dict[str, list[PerformanceRecord]] = {}

    def create_experiment(self, config: ABTestConfig) -> str:
        self._experiments[config.experiment_id] = config
        self._results[config.experiment_id] = []
        return config.experiment_id

    def record_result(self, experiment_id: str, variant: str,
                      success: bool, quality: float = 0.0) -> None:
        if experiment_id not in self._results:
            return
        self._results[experiment_id].append(PerformanceRecord(
            agent_id=variant,
            task_id=f"exp_{experiment_id}",
            task_type=experiment_id,
            success=success,
            quality_score=quality,
        ))

    def get_result(self, experiment_id: str) -> Optional[ABTestResult]:
        config = self._experiments.get(experiment_id)
        if not config:
            return None

        records = self._results.get(experiment_id, [])
        variant_stats: dict[str, dict] = {}
        for variant in config.variants:
            vr = [r for r in records if r.agent_id == variant]
            variant_stats[variant] = {
                "samples": len(vr),
                "success_rate": round(
                    sum(1 for r in vr if r.success) / max(len(vr), 1), 2
                ),
                "avg_quality": round(
                    sum(r.quality_score for r in vr) / max(len(vr), 1), 2
                ),
            }

        # 找胜者
        best_variant = max(config.variants,
                          key=lambda v: variant_stats[v]["avg_quality"])

        return ABTestResult(
            experiment_id=experiment_id,
            winner=best_variant,
            variant_stats=variant_stats,
            confidence=0.8 if all(
                variant_stats[v]["samples"] >= config.min_samples
                for v in config.variants
            ) else 0.0,
            significant=all(
                variant_stats[v]["samples"] >= config.min_samples
                for v in config.variants
            ),
        )
