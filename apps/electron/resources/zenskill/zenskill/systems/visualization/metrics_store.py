"""
ZenSkill - 指标历史持久化系统

负责记录和查询成长指标历史，支持：
- 自动采样（每 N 次交互记录一次）
- 最多保留 100 个采样点
- 查询历史趋势
- 计算变化量和增长率
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict

from zenskill.core.paths import append_jsonl_unlocked, atomic_write_text, file_lock, get_metrics_dir


@dataclass
class MetricSnapshot:
    """指标快照 - 一个采样点的数据"""
    timestamp: float
    date: str
    interaction_count: int
    success_rate: float
    user_satisfaction: float
    avg_response_time_ms: float
    memory_usage_count: int
    level: str
    ability_scores: Dict[str, int]

    @classmethod
    def from_state(
        cls,
        state: Dict[str, Any],
        ability_scores: Optional[Dict[str, int]] = None,
    ) -> "MetricSnapshot":
        """
        从技能状态创建快照

        Args:
            state: 技能状态字典
            ability_scores: 五维能力得分（如果为 None 则从数据计算）

        Raises:
            ValueError: 如果 state 不是字典类型
        """
        if not isinstance(state, dict):
            raise ValueError(f"state 必须是字典类型，实际是 {type(state)}")

        usage_count = state.get("usage_count", 0)
        # 确保是有效数字
        if not isinstance(usage_count, (int, float)) or usage_count < 0:
            usage_count = 0

        metrics = state.get("metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}

        success_count = metrics.get("successful_executions", 0)
        if not isinstance(success_count, (int, float)) or success_count < 0:
            success_count = 0

        success_rate = success_count / max(1, usage_count)
        success_rate = max(0.0, min(1.0, success_rate))  # 限制在 0-1 范围

        avg_response = metrics.get("avg_duration_ms", 500)
        if not isinstance(avg_response, (int, float)) or avg_response < 0:
            avg_response = 500

        user_satisfaction = metrics.get("user_satisfaction", 0.8)
        if not isinstance(user_satisfaction, (int, float)):
            user_satisfaction = 0.8
        user_satisfaction = max(0.0, min(1.0, user_satisfaction))

        # 计算能力得分
        if ability_scores is None:
            proficiency = min(100, usage_count // 5)
            stability = round(success_rate * 100)
            satisfaction = round(user_satisfaction * 100)
            responsiveness = max(0, round(100 - avg_response / 50))

            episodes = state.get("episodes", [])
            memory_score = min(100, len(episodes) // 2) if isinstance(episodes, list) else 0

            composite = round(
                proficiency * 0.3
                + stability * 0.25
                + satisfaction * 0.2
                + responsiveness * 0.15
                + memory_score * 0.1
            )

            ability_scores = {
                "proficiency": proficiency,
                "stability": stability,
                "satisfaction": satisfaction,
                "responsiveness": responsiveness,
                "memory": memory_score,
                "composite": composite,
            }

        level = state.get("level", "NOVICE")
        if not isinstance(level, str):
            level = "NOVICE"

        return cls(
            timestamp=time.time(),
            date=datetime.now().strftime("%Y-%m-%d"),
            interaction_count=int(usage_count),
            success_rate=success_rate,
            user_satisfaction=user_satisfaction,
            avg_response_time_ms=float(avg_response),
            memory_usage_count=len(episodes) if isinstance(episodes, list) else 0,
            level=level,
            ability_scores=ability_scores,
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetricSnapshot":
        """从字典创建"""
        return cls(**data)


class MetricsStore:
    """指标历史存储"""

    # 采样频率：每 5 次交互记录一次
    SAMPLE_INTERVAL = 5

    # 最多保留 100 个采样点
    MAX_POINTS = 100

    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id
        self.metrics_dir = get_metrics_dir()
        self.history_file = self.metrics_dir / f"{skill_id}_history.jsonl"

    def should_sample(self, current_usage: int) -> bool:
        """
        判断是否应该进行采样

        Args:
            current_usage: 当前使用次数

        Returns:
            是否需要采样
        """
        # 边界检查：确保是有效数字
        if not isinstance(current_usage, int) or current_usage < 0:
            return False

        # 每 SAMPLE_INTERVAL 次采样一次
        if current_usage % self.SAMPLE_INTERVAL == 0:
            # 确保不是重复采样
            last_snapshot = self.get_latest_snapshot()
            if last_snapshot and last_snapshot.interaction_count == current_usage:
                return False
            return True
        return False

    def record_snapshot(self, state: Dict[str, Any]) -> MetricSnapshot:
        """
        记录一个指标快照

        Args:
            state: 技能状态字典

        Returns:
            保存的快照

        Raises:
            ValueError: 如果状态数据无效
            IOError: 如果文件写入失败
        """
        if not isinstance(state, dict):
            raise ValueError(f"state 必须是字典类型，实际是 {type(state)}")

        try:
            snapshot = MetricSnapshot.from_state(state)
        except Exception as e:
            raise ValueError(f"无法从状态创建快照: {e}") from e

        # 确保目录存在
        try:
            self.metrics_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise IOError(f"无法创建指标目录: {e}") from e

        try:
            with file_lock(self.history_file, timeout=1.0):
                append_jsonl_unlocked(self.history_file, snapshot.to_dict())
                self._trim_history_unlocked()
        except OSError as e:
            raise IOError(f"无法写入历史文件: {e}") from e

        return snapshot

    def _trim_history(self) -> None:
        """清理过期数据，保留最多 MAX_POINTS 个采样点"""
        with file_lock(self.history_file):
            self._trim_history_unlocked()

    def _trim_history_unlocked(self) -> None:
        if not self.history_file.exists():
            return

        try:
            lines = []
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        lines.append(line)

            if len(lines) > self.MAX_POINTS:
                lines = lines[-self.MAX_POINTS:]
                atomic_write_text(self.history_file, "\n".join(lines) + "\n")
        except OSError:
            pass

    def get_all_snapshots(self) -> List[MetricSnapshot]:
        """获取所有历史快照"""
        snapshots = []
        if not self.history_file.exists():
            return snapshots

        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            snapshots.append(MetricSnapshot.from_dict(data))
                        except (json.JSONDecodeError, TypeError, ValueError):
                            # 跳过损坏的行
                            continue
        except OSError:
            # 文件读取失败，返回空列表
            return []

        return snapshots

    def get_latest_snapshot(self) -> Optional[MetricSnapshot]:
        """获取最新的快照"""
        snapshots = self.get_all_snapshots()
        return snapshots[-1] if snapshots else None

    def get_previous_snapshot(self) -> Optional[MetricSnapshot]:
        """获取上一个快照（用于对比变化）"""
        snapshots = self.get_all_snapshots()
        return snapshots[-2] if len(snapshots) >= 2 else None

    def get_snapshots_since(self, days: int = 7) -> List[MetricSnapshot]:
        """
        获取最近 N 天的快照

        Args:
            days: 天数

        Returns:
            快照列表
        """
        cutoff = time.time() - days * 86400
        return [
            s for s in self.get_all_snapshots()
            if s.timestamp >= cutoff
        ]

    def calculate_change(self, dimension: str = "composite", n_points: int = 10) -> Dict[str, Any]:
        """
        计算某个维度的变化情况

        Args:
            dimension: 维度名称
            n_points: 对比最近 N 个点

        Returns:
            变化信息字典
        """
        # 边界检查
        if not isinstance(dimension, str):
            dimension = "composite"
        if not isinstance(n_points, int) or n_points < 2:
            n_points = 10

        snapshots = self.get_all_snapshots()
        if len(snapshots) < 2:
            return {"change": 0, "change_pct": 0, "trend": "flat"}

        # 取前 N 个点对比
        current = snapshots[-1].ability_scores.get(dimension, 0)
        if len(snapshots) >= n_points:
            prev = snapshots[-n_points].ability_scores.get(dimension, 0)
        else:
            prev = snapshots[0].ability_scores.get(dimension, 0)

        # 确保是数字
        if not isinstance(current, (int, float)):
            current = 0
        if not isinstance(prev, (int, float)):
            prev = 0

        change = current - prev
        change_pct = round(change / max(1, prev) * 100, 1) if prev > 0 else 0

        trend = "up" if change > 0 else "down" if change < 0 else "flat"

        return {
            "change": change,
            "change_pct": change_pct,
            "trend": trend,
            "current": current,
            "previous": prev,
        }

    def get_fastest_growing_dimension(self, n_points: int = 5) -> Dict[str, Any]:
        """
        获取增长最快的维度

        Args:
            n_points: 对比点数

        Returns:
            增长最快维度信息
        """
        dimensions = ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]
        changes = []

        for dim in dimensions:
            change_info = self.calculate_change(dim, n_points)
            changes.append((dim, change_info["change"]))

        # 按变化量排序
        changes.sort(key=lambda x: x[1], reverse=True)
        best_dim, best_change = changes[0]

        return {
            "dimension": best_dim,
            "change": best_change,
            "is_positive": best_change > 0,
        }

    def get_snapshot_count(self) -> int:
        """获取快照数量"""
        return len(self.get_all_snapshots())
