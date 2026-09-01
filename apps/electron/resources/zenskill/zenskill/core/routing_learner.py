"""自适应学习路由 (PROP-20260712-092)

引入反馈闭环，路由决策随执行数据持续优化。
使用 ELO 评分算法（简单高效、无需概率假设、适合成对比较）。

用法:
    from zenskill.core.routing_learner import RoutingLearner, ExecutionRecord

    learner = RoutingLearner()

    # 记录执行结果
    learner.record(ExecutionRecord(
        task_hash="abc123",
        skill_id="data-analysis",
        predicted_confidence=0.9,
        actual_success=True,
        execution_time=2.5,
    ))

    # 获取学习调整系数
    factor = learner.get_adjustment("data-analysis")
    adjusted_confidence = base_confidence * factor
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .protocols import RoutingContext


@dataclass
class ExecutionRecord:
    """执行记录"""
    task_hash: str
    skill_id: str
    predicted_confidence: float
    actual_success: bool
    execution_time: float = 0.0
    user_rating: Optional[float] = None  # 0.0-5.0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_hash": self.task_hash,
            "skill_id": self.skill_id,
            "predicted_confidence": self.predicted_confidence,
            "actual_success": self.actual_success,
            "execution_time": self.execution_time,
            "user_rating": self.user_rating,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionRecord":
        return cls(
            task_hash=data["task_hash"],
            skill_id=data["skill_id"],
            predicted_confidence=data["predicted_confidence"],
            actual_success=data["actual_success"],
            execution_time=data.get("execution_time", 0.0),
            user_rating=data.get("user_rating"),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(),
        )

    @classmethod
    def from_task(cls, task: str, skill_id: str, **kwargs) -> "ExecutionRecord":
        """从任务文本创建记录"""
        task_hash = hashlib.sha256(task.encode()).hexdigest()[:16]
        return cls(task_hash=task_hash, skill_id=skill_id, **kwargs)


@dataclass
class SkillStats:
    """技能统计信息"""
    skill_id: str
    elo_rating: float = 1500.0  # ELO 初始分
    total_games: int = 0
    wins: int = 0
    losses: int = 0
    avg_confidence: float = 0.0
    avg_execution_time: float = 0.0
    last_used: Optional[datetime] = None

    @property
    def win_rate(self) -> float:
        if self.total_games == 0:
            return 0.5
        return self.wins / self.total_games

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "elo_rating": round(self.elo_rating, 1),
            "total_games": self.total_games,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 3),
            "avg_confidence": round(self.avg_confidence, 3),
            "avg_execution_time": round(self.avg_execution_time, 2),
        }


class RoutingLearner:
    """自适应学习路由器

    使用 ELO 评分算法:
    - 每次执行记录为一次"比赛"
    - 成功 = 赢，失败 = 输
    - ELO 分数反映技能的相对能力

    特性:
    - 调整系数有上下限（0.5-2.0），防止极端偏移
    - 冷启动机制：新技能使用默认置信度
    - 支持序列化/反序列化（持久化）
    """

    # ELO 常量
    K_FACTOR = 32  # K 因子（调整幅度）
    INITIAL_RATING = 1500.0
    MIN_ADJUSTMENT = 0.5
    MAX_ADJUSTMENT = 2.0
    MIN_RECORDS_FOR_ADJUSTMENT = 10  # 最少记录数才开始调整

    def __init__(self) -> None:
        self._stats: Dict[str, SkillStats] = {}
        self._records: List[ExecutionRecord] = []

    def record(self, record: ExecutionRecord) -> None:
        """记录执行结果"""
        self._records.append(record)

        # 更新统计
        stats = self._get_or_create_stats(record.skill_id)
        stats.total_games += 1
        stats.last_used = record.timestamp

        if record.actual_success:
            stats.wins += 1
        else:
            stats.losses += 1

        # 更新平均值
        n = stats.total_games
        stats.avg_confidence = (
            (stats.avg_confidence * (n - 1) + record.predicted_confidence) / n
        )
        if record.execution_time > 0:
            stats.avg_execution_time = (
                (stats.avg_execution_time * (n - 1) + record.execution_time) / n
            )

        # 更新 ELO
        self._update_elo(record)

    def _get_or_create_stats(self, skill_id: str) -> SkillStats:
        """获取或创建技能统计"""
        if skill_id not in self._stats:
            self._stats[skill_id] = SkillStats(skill_id=skill_id)
        return self._stats[skill_id]

    def _update_elo(self, record: ExecutionRecord) -> None:
        """更新 ELO 评分"""
        stats = self._get_or_create_stats(record.skill_id)

        # 简化 ELO：与"平均技能"（1500 分）比较
        expected = 1.0 / (1.0 + 10 ** ((self.INITIAL_RATING - stats.elo_rating) / 400))
        actual = 1.0 if record.actual_success else 0.0

        stats.elo_rating += self.K_FACTOR * (actual - expected)

    def get_adjustment(self, skill_id: str) -> float:
        """获取学习调整系数

        Returns:
            调整系数 0.5-2.0（1.0 表示无调整）
        """
        stats = self._stats.get(skill_id)
        if not stats or stats.total_games < self.MIN_RECORDS_FOR_ADJUSTMENT:
            return 1.0  # 冷启动：无调整

        # 从 ELO 计算调整系数
        # 1500 → 1.0, 1600 → ~1.3, 1400 → ~0.7
        adjustment = 10 ** ((stats.elo_rating - self.INITIAL_RATING) / 400)

        # 限制范围
        return max(self.MIN_ADJUSTMENT, min(self.MAX_ADJUSTMENT, adjustment))

    def get_adjusted_confidence(
        self, skill_id: str, base_confidence: float
    ) -> float:
        """获取调整后的置信度"""
        factor = self.get_adjustment(skill_id)
        return min(1.0, base_confidence * factor)

    def get_stats(self, skill_id: Optional[str] = None) -> Any:
        """获取统计信息"""
        if skill_id:
            return self._stats.get(skill_id)
        return self._stats

    def get_records(
        self, skill_id: Optional[str] = None, limit: int = 100
    ) -> List[ExecutionRecord]:
        """获取执行记录"""
        records = self._records
        if skill_id:
            records = [r for r in records if r.skill_id == skill_id]
        return records[-limit:]

    def get_ranking(self) -> List[Dict[str, Any]]:
        """获取技能排名（按 ELO 降序）"""
        ranking = []
        for stats in sorted(
            self._stats.values(), key=lambda s: s.elo_rating, reverse=True
        ):
            ranking.append(stats.to_dict())
        return ranking

    def detect_drift(self, threshold: float = 0.6) -> List[str]:
        """检测路由漂移

        Args:
            threshold: 单技能占比阈值

        Returns:
            发生漂移的技能 ID 列表
        """
        if not self._records:
            return []

        # 统计最近 100 条记录的分布
        recent = self._records[-100:]
        skill_counts = defaultdict(int)
        for r in recent:
            skill_counts[r.skill_id] += 1

        total = len(recent)
        drifted = []
        for skill_id, count in skill_counts.items():
            if count / total > threshold:
                drifted.append(skill_id)

        return drifted

    def to_dict(self) -> Dict[str, Any]:
        """序列化"""
        return {
            "stats": {k: v.to_dict() for k, v in self._stats.items()},
            "records": [r.to_dict() for r in self._records[-1000:]],  # 保留最近 1000 条
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoutingLearner":
        """反序列化"""
        learner = cls()

        for skill_id, stats_data in data.get("stats", {}).items():
            stats = SkillStats(
                skill_id=skill_id,
                elo_rating=stats_data.get("elo_rating", 1500.0),
                total_games=stats_data.get("total_games", 0),
                wins=stats_data.get("wins", 0),
                losses=stats_data.get("losses", 0),
                avg_confidence=stats_data.get("avg_confidence", 0.0),
                avg_execution_time=stats_data.get("avg_execution_time", 0.0),
            )
            learner._stats[skill_id] = stats

        for record_data in data.get("records", []):
            learner._records.append(ExecutionRecord.from_dict(record_data))

        return learner


# 全局单例
routing_learner = RoutingLearner()
