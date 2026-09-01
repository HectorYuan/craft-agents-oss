"""
ZenSkill - 主动目标设定系统

根据当前五维能力短板和成长趋势，自动设定下一阶段成长目标：
- 短板识别算法
- 目标可达性预测
- 动态目标调整
- 目标进度追踪
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Tuple

from zenskill.core.paths import get_user_data_dir
from zenskill.systems.visualization.metrics_store import MetricsStore, MetricSnapshot
from zenskill.systems.visualization.ability_calculator import AbilityCalculator, AbilityScores


@dataclass
class GrowthGoal:
    """成长目标"""
    goal_id: str
    dimension: str  # proficiency / stability / satisfaction / responsiveness / memory
    target_score: int  # 目标分数 (0-100)
    current_score: int  # 创建目标时的分数
    deadline_interactions: int  # 预计需要的交互次数
    created_at: str
    status: str  # active / completed / failed
    strategy: str  # 推荐策略

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GrowthGoal":
        """从字典创建目标"""
        return cls(
            goal_id=data.get("goal_id", ""),
            dimension=data.get("dimension", "composite"),
            target_score=data.get("target_score", 0),
            current_score=data.get("current_score", 0),
            deadline_interactions=data.get("deadline_interactions", 0),
            created_at=data.get("created_at", ""),
            status=data.get("status", "active"),
            strategy=data.get("strategy", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


@dataclass
class GoalProgress:
    """目标进度"""
    goal_id: str
    start_score: int
    current_score: int
    target_score: int
    milestones: List[Dict[str, Any]]
    predictions: Dict[str, Any]

    @property
    def progress_pct(self) -> float:
        """完成百分比"""
        if self.target_score <= self.start_score:
            return 100.0
        progress = (self.current_score - self.start_score) / (self.target_score - self.start_score)
        return max(0.0, min(100.0, progress * 100))


class ActiveGoalEngine:
    """主动目标设定引擎

    功能：
    1. 识别当前成长短板
    2. 设定合理的目标
    3. 追踪目标进度
    4. 动态调整目标
    """

    # 维度名称映射
    DIMENSION_NAMES = {
        "proficiency": "熟练度",
        "stability": "稳定性",
        "satisfaction": "满意度",
        "responsiveness": "响应力",
        "memory": "记忆力",
        "composite": "综合能力",
    }

    # 维度权重（用于优先级计算）
    DIMENSION_WEIGHTS = {
        "proficiency": 1.2,
        "stability": 1.0,
        "satisfaction": 0.9,
        "responsiveness": 0.8,
        "memory": 1.1,
    }

    # 推荐策略
    STRATEGIES = {
        "proficiency": "增加使用频次，每天固定时间练习",
        "stability": "将复杂任务拆分为小步骤，提高成功率",
        "satisfaction": "每次交互后反思输出质量，持续优化",
        "responsiveness": "使用更简洁明确的指令，减少歧义",
        "memory": "定期记录重要信息，多使用记忆功能",
    }

    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id
        self.metrics_store = MetricsStore(skill_id)
        self.ability_calculator = AbilityCalculator()
        self.goals_dir = self._get_goals_dir()
        self.goals_file = self.goals_dir / f"{skill_id}_goals.jsonl"

    def _get_goals_dir(self) -> Path:
        """获取目标存储目录"""
        user_dir = get_user_data_dir()
        goals_dir = user_dir / "goals"
        goals_dir.mkdir(parents=True, exist_ok=True)
        return goals_dir

    def _generate_goal_id(self) -> str:
        """生成唯一的目标ID"""
        timestamp = int(time.time())
        return f"goal_{timestamp}_{self.skill_id}"

    def identify_weakest_dimensions(self, n: int = 2) -> List[Tuple[str, int, float]]:
        """
        识别最需要提升的维度（短板）

        Args:
            n: 返回前 N 个维度

        Returns:
            (维度名称, 当前分数, 优先级) 列表
        """
        snapshots = self.metrics_store.get_all_snapshots()
        if not snapshots:
            return [("proficiency", 0, 1.0)]

        latest = snapshots[-1]
        scores = latest.ability_scores

        # 计算历史增长速度
        growth_rates = self._calculate_growth_rates(snapshots)

        # 计算每个维度的优先级
        priorities = []
        for dim in ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]:
            current = scores.get(dim, 0)
            weight = self.DIMENSION_WEIGHTS.get(dim, 1.0)
            growth_rate = growth_rates.get(dim, 0.5)

            # 优先级 = (提升空间) × 权重 × 增长难度系数
            # 增长慢的维度优先级更高（需要更多关注）
            room_for_improvement = max(0, 100 - current)
            difficulty_factor = max(0.5, 2.0 - growth_rate)
            priority = room_for_improvement * weight * difficulty_factor / 100

            priorities.append((dim, current, priority))

        # 按优先级降序排序
        priorities.sort(key=lambda x: x[2], reverse=True)
        return priorities[:n]

    def _calculate_growth_rates(self, snapshots: List[MetricSnapshot]) -> Dict[str, float]:
        """计算各维度的历史增长速度"""
        if len(snapshots) < 2:
            return {dim: 0.5 for dim in self.DIMENSION_NAMES}

        # 取最近 5 个采样点
        recent = snapshots[-min(5, len(snapshots)):]
        first = recent[0]
        last = recent[-1]

        growth_rates = {}
        for dim in ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]:
            start = first.ability_scores.get(dim, 0)
            end = last.ability_scores.get(dim, 0)
            # 每个采样点 5 次交互，计算每次交互的平均增长
            n_samples = len(recent)
            total_interactions = last.interaction_count - first.interaction_count + 1
            growth_per_interaction = (end - start) / total_interactions if total_interactions > 0 else 0
            # 归一化到 0-1 范围
            growth_rates[dim] = min(1.0, growth_per_interaction * 10)

        return growth_rates

    def suggest_goals(self, n_goals: int = 2) -> List[GrowthGoal]:
        """
        建议成长目标

        Args:
            n_goals: 建议的目标数量

        Returns:
            推荐的目标列表
        """
        # 边界检查
        if not isinstance(n_goals, int) or n_goals < 1:
            n_goals = 2
        if n_goals > 3:
            n_goals = 3

        weakest = self.identify_weakest_dimensions(n_goals)
        snapshots = self.metrics_store.get_all_snapshots()
        latest = snapshots[-1] if snapshots else None

        if not latest:
            # 数据不足时返回默认目标
            return [GrowthGoal(
                goal_id=self._generate_goal_id(),
                dimension="composite",
                target_score=30,
                current_score=0,
                deadline_interactions=50,
                created_at=datetime.now().isoformat(),
                status="active",
                strategy="继续使用，积累基础数据",
            )]

        goals = []
        for dim, current_score, priority in weakest:
            # 基于历史增长速度预测合理的目标
            growth_rates = self._calculate_growth_rates(snapshots)
            growth_rate = growth_rates.get(dim, 0.3)

            # 目标设定：每次交互增长 0.2-0.8 分，预计 20 次采样（100 次交互）
            # 但不超过满分
            target_increase = max(10, int(20 * growth_rate * 5))  # 至少提升 10 分
            target_score = min(100, current_score + target_increase)

            # 如果已经接近满分，不建议目标
            if current_score >= 95:
                continue

            # 计算预计需要的交互次数
            expected_growth_per_5 = target_increase / 20
            deadline_interactions = int(target_increase / max(0.1, expected_growth_per_5) * 5)

            goals.append(GrowthGoal(
                goal_id=self._generate_goal_id(),
                dimension=dim,
                target_score=target_score,
                current_score=current_score,
                deadline_interactions=deadline_interactions,
                created_at=datetime.now().isoformat(),
                status="active",
                strategy=self.STRATEGIES.get(dim, "坚持使用，保持练习"),
            ))

        return goals

    def create_goal(
        self,
        dimension: str,
        target_score: int,
        deadline_interactions: Optional[int] = None,
    ) -> GrowthGoal:
        """
        手动创建成长目标

        Args:
            dimension: 维度名称
            target_score: 目标分数
            deadline_interactions: 预计交互次数（可选，自动估算）

        Returns:
            创建的目标对象
        """
        # 边界检查
        if dimension not in self.DIMENSION_NAMES:
            raise ValueError(f"无效的维度名称: {dimension}，可选: {list(self.DIMENSION_NAMES.keys())}")

        if not isinstance(target_score, int) or target_score < 0 or target_score > 100:
            raise ValueError("目标分数必须在 0-100 之间")

        # 获取当前分数
        snapshots = self.metrics_store.get_all_snapshots()
        if snapshots:
            latest = snapshots[-1]
            current_score = latest.ability_scores.get(dimension, 0)
            current_interactions = latest.interaction_count
        else:
            current_score = 0
            current_interactions = 0

        if target_score <= current_score:
            raise ValueError(f"目标分数 ({target_score}) 必须高于当前分数 ({current_score})")

        # 自动估算截止时间
        if deadline_interactions is None:
            target_increase = target_score - current_score
            # 假设每次采样（5次交互）提升 1-5 分
            deadline_interactions = max(25, int(target_increase / 3 * 5))

        # 检查同一维度是否已有活跃目标
        active_goals = self.get_active_goals()
        for goal in active_goals:
            if goal.dimension == dimension:
                raise ValueError(f"维度 [{dimension}] 已有活跃目标，请先完成或取消它")

        goal = GrowthGoal(
            goal_id=self._generate_goal_id(),
            dimension=dimension,
            target_score=target_score,
            current_score=current_score,
            deadline_interactions=deadline_interactions,
            created_at=datetime.now().isoformat(),
            status="active",
            strategy=self.STRATEGIES.get(dimension, "坚持使用，保持练习"),
        )

        # 保存目标
        self._save_goal(goal)

        return goal

    def _save_goal(self, goal: GrowthGoal) -> None:
        """保存目标到文件"""
        with open(self.goals_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(goal.to_dict(), ensure_ascii=False) + "\n")

    def get_all_goals(self) -> List[GrowthGoal]:
        """获取所有历史目标"""
        if not self.goals_file.exists():
            return []

        goals = []
        with open(self.goals_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        goals.append(GrowthGoal.from_dict(data))
                    except (json.JSONDecodeError, ValueError, TypeError):
                        continue

        return goals

    def get_active_goals(self) -> List[GrowthGoal]:
        """获取所有活跃的目标"""
        return [g for g in self.get_all_goals() if g.status == "active"]

    def get_goal_progress(self, goal: GrowthGoal) -> GoalProgress:
        """获取目标的当前进度"""
        snapshots = self.metrics_store.get_all_snapshots()
        if snapshots:
            current_score = snapshots[-1].ability_scores.get(goal.dimension, goal.current_score)
        else:
            current_score = goal.current_score

        return GoalProgress(
            goal_id=goal.goal_id,
            start_score=goal.current_score,
            current_score=current_score,
            target_score=goal.target_score,
            milestones=[],
            predictions={},
        )

    def update_goal_status(self) -> List[GrowthGoal]:
        """更新所有活跃目标的状态"""
        goals = self.get_all_goals()
        snapshots = self.metrics_store.get_all_snapshots()
        if not snapshots:
            return goals

        latest = snapshots[-1]
        updated_goals = []

        # 重新写入所有目标（更新状态）
        temp_file = self.goals_file.with_suffix(".tmp")

        with open(temp_file, "w", encoding="utf-8") as f:
            for goal in goals:
                if goal.status == "active":
                    current_score = latest.ability_scores.get(goal.dimension, goal.current_score)

                    # 检查是否完成
                    if current_score >= goal.target_score:
                        goal.status = "completed"

                    # 检查是否超时（需要检查交互次数）
                    # 这里简化：如果超过目标设定的交互次数仍未完成，标记为需要调整
                    interactions_passed = latest.interaction_count - goal.current_score
                    # 注意：这里需要更复杂的逻辑，暂时不自动标记为 failed

                f.write(json.dumps(goal.to_dict(), ensure_ascii=False) + "\n")
                updated_goals.append(goal)

        temp_file.rename(self.goals_file)
        return updated_goals

    def complete_goal(self, goal_id: str) -> bool:
        """手动标记目标为完成"""
        goals = self.get_all_goals()
        found = False

        temp_file = self.goals_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            for goal in goals:
                if goal.goal_id == goal_id:
                    goal.status = "completed"
                    found = True
                f.write(json.dumps(goal.to_dict(), ensure_ascii=False) + "\n")

        if found:
            temp_file.rename(self.goals_file)
        else:
            temp_file.unlink(missing_ok=True)

        return found

    def cancel_goal(self, goal_id: str) -> bool:
        """取消目标"""
        goals = self.get_all_goals()
        found = False

        temp_file = self.goals_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            for goal in goals:
                if goal.goal_id == goal_id:
                    goal.status = "cancelled"
                    found = True
                f.write(json.dumps(goal.to_dict(), ensure_ascii=False) + "\n")

        if found:
            temp_file.rename(self.goals_file)
        else:
            temp_file.unlink(missing_ok=True)

        return found

    def generate_status_report(self) -> str:
        """生成目标状态报告"""
        self.update_goal_status()
        active_goals = self.get_active_goals()
        all_goals = self.get_all_goals()
        completed = [g for g in all_goals if g.status == "completed"]

        lines = []
        lines.append("🎯 成长目标状态")
        lines.append("═" * 60)
        lines.append("")

        if not active_goals:
            lines.append("   暂无活跃目标，建议使用 'zenskill goal suggest' 获取推荐")
            lines.append("")
            lines.append("   或手动创建目标:")
            lines.append("   python -m zenskill goal set --dimension proficiency --target 50")
            lines.append("")
        else:
            for goal in active_goals:
                dim_name = self.DIMENSION_NAMES.get(goal.dimension, goal.dimension)
                progress = self.get_goal_progress(goal)
                pct = progress.progress_pct

                lines.append(f"   📍 [{dim_name}] 目标: {goal.target_score} 分")
                lines.append(f"      当前: {progress.current_score} 分 / 开始: {goal.current_score} 分")
                lines.append(f"      进度: [{int(pct):3d}%] {'█' * int(pct / 5)}{'░' * (20 - int(pct / 5))}")
                lines.append(f"      策略: {goal.strategy}")
                lines.append("")

        lines.append(f"📊 统计: 活跃 {len(active_goals)} 个，已完成 {len(completed)} 个")
        lines.append("")

        # 显示下一个推荐目标
        if len(active_goals) < 2:
            suggestions = self.suggest_goals(1)
            if suggestions:
                suggestion = suggestions[0]
                dim_name = self.DIMENSION_NAMES.get(suggestion.dimension, suggestion.dimension)
                lines.append(f"💡 建议关注: [{dim_name}] 从 {suggestion.current_score} → {suggestion.target_score}")

        return "\n".join(lines)
