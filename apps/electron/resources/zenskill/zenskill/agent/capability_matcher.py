"""
MU2-9P: 代理能力动态发现与智能路由 (Capability Discovery & Routing)

基于五维匹配度将任务智能路由到最合适的 Agent：
1. 技能相关性 (25%) — 擅长的领域 vs 任务类型
2. 能力水平 (20%) — 五维能力 vs 任务难度
3. 历史表现 (25%) — 历史成功率和质量评分
4. 可用性 (15%) — 当前负载 vs 最大容量
5. 协作契合度 (15%) — 历史协作效果

集成现有基础设施：
- AgentCapability → 技能/领域匹配
- AgentEvaluator → 历史表现评分
- SharedMemory → 协作关系分析
- MessageBus → 注册与发现
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .protocol import AgentCapability, AgentRole, MessageBus
from .evaluator import AgentEvaluator, AgentScore
from .shared_memory import SharedMemory

logger = logging.getLogger(__name__)


# ── 五维匹配度权重 ──
WEIGHT_SKILL_RELEVANCE = 0.25
WEIGHT_ABILITY_LEVEL = 0.20
WEIGHT_HISTORICAL_PERFORMANCE = 0.25
WEIGHT_AVAILABILITY = 0.15
WEIGHT_COLLABORATION_FIT = 0.15

# ── 默认任务难度映射 ──
DIFFICULTY_LEVELS = {
    "trivial": 0.2,
    "easy": 0.4,
    "medium": 0.6,
    "hard": 0.8,
    "expert": 1.0,
}


@dataclass
class TaskSpecification:
    """
    任务规格说明 — 用于匹配决策的完整任务描述

    Attributes:
        task_type: 任务类型（如 "coding", "testing", "architecture"）
        domain: 领域（如 "python", "backend", "security"）
        difficulty: 难度等级 ("trivial"/"easy"/"medium"/"hard"/"expert")
        priority: 优先级 (1-5, 5=最高)
        required_skills: 所需的技能列表
        context: 额外上下文信息
    """
    task_type: str
    domain: str = ""
    difficulty: str = "medium"
    priority: int = 3
    required_skills: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)

    @property
    def difficulty_score(self) -> float:
        """难度数值 0-1"""
        return DIFFICULTY_LEVELS.get(self.difficulty, 0.6)


@dataclass
class AgentMatchResult:
    """
    Agent 匹配结果

    Attributes:
        agent_id: Agent ID
        role: 角色
        overall_score: 综合匹配度 0-100
        dimensions: 各维度得分明细
    """
    agent_id: str
    role: str
    overall_score: float
    dimensions: Dict[str, float]
    breakdown: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "overall_score": self.overall_score,
            "dimensions": self.dimensions,
            "breakdown": self.breakdown,
        }


class CapabilityMatcher:
    """
    能力匹配器 — 五维智能路由引擎

    将 TaskSpecification 与注册的 Agent 进行多维度匹配，
    返回按综合得分排序的匹配结果。
    """

    def __init__(self, bus: Optional[MessageBus] = None,
                 evaluator: Optional[AgentEvaluator] = None,
                 shared_memory: Optional[SharedMemory] = None):
        self._bus = bus or MessageBus()
        self._evaluator = evaluator or AgentEvaluator()
        self._shared_memory = shared_memory or SharedMemory()

    # ── 五维匹配 ──

    def find_best_agents(
        self, task: TaskSpecification,
        min_score: float = 30.0,
        top_k: int = 3,
    ) -> List[AgentMatchResult]:
        """
        查找最适合任务的 Agent

        Args:
            task: 任务规格
            min_score: 最低综合得分
            top_k: 返回 Top-K

        Returns:
            按综合得分降序排列的匹配结果
        """
        # 获取所有已注册 Agent 的能力
        capabilities = self._bus.list_capabilities()
        if not capabilities:
            return []

        results: List[AgentMatchResult] = []

        for agent_id, cap in capabilities.items():
            score = self._score_agent(agent_id, cap, task)
            if score.overall_score >= min_score:
                results.append(score)

        results.sort(key=lambda r: -r.overall_score)
        return results[:top_k]

    def _score_agent(
        self, agent_id: str, cap: AgentCapability,
        task: TaskSpecification,
    ) -> AgentMatchResult:
        """
        计算 Agent 的五维综合得分

        Returns:
            AgentMatchResult
        """
        # 1. 技能相关性 (0-100)
        skill_score = self._score_skill_relevance(cap, task)

        # 2. 能力水平 (0-100)
        ability_score = self._score_ability_level(agent_id, cap, task)

        # 3. 历史表现 (0-100)
        perf_score = self._score_historical_performance(agent_id, task)

        # 4. 可用性 (0-100)
        avail_score = self._score_availability(agent_id, cap)

        # 5. 协作契合度 (0-100)
        collab_score = self._score_collaboration_fit(agent_id, task)

        # 综合得分
        overall = (
            skill_score * WEIGHT_SKILL_RELEVANCE +
            ability_score * WEIGHT_ABILITY_LEVEL +
            perf_score * WEIGHT_HISTORICAL_PERFORMANCE +
            avail_score * WEIGHT_AVAILABILITY +
            collab_score * WEIGHT_COLLABORATION_FIT
        )

        dimensions = {
            "skill_relevance": round(skill_score, 1),
            "ability_level": round(ability_score, 1),
            "historical_performance": round(perf_score, 1),
            "availability": round(avail_score, 1),
            "collaboration_fit": round(collab_score, 1),
        }

        breakdown = {
            "skill_relevance": self._explain_skill(cap, task),
            "historical_performance": self._explain_performance(agent_id),
            "availability": self._explain_availability(agent_id, cap),
        }

        return AgentMatchResult(
            agent_id=agent_id,
            role=cap.role.value,
            overall_score=round(overall, 1),
            dimensions=dimensions,
            breakdown=breakdown,
        )

    # ── 维度 1: 技能相关性 ──

    def _score_skill_relevance(self, cap: AgentCapability,
                                task: TaskSpecification) -> float:
        """
        技能相关性评分 (0-100)

        匹配要素：
        - task_type 是否在 skills 中 (50%)
        - domain 是否在 domains/confidence_factors 中 (30%)
        - required_skills 匹配度 (20%)
        """
        score = 0.0

        # task_type 匹配
        if task.task_type in cap.skills:
            score += 50.0
        elif any(task.task_type in s for s in cap.skills):
            score += 25.0

        # domain 匹配
        if task.domain:
            if task.domain in cap.domains:
                score += 30.0
                # confidence 加成
                conf = cap.confidence_factors.get(task.domain, 1.0)
                score *= conf
            elif any(d in task.domain for d in cap.domains):
                score += 15.0

        # required_skills 匹配
        if task.required_skills:
            matches = sum(1 for rs in task.required_skills if rs in cap.skills)
            ratio = matches / len(task.required_skills)
            score += ratio * 20.0

        return min(score, 100.0)

    # ── 维度 2: 能力水平 ──

    def _score_ability_level(self, agent_id: str, cap: AgentCapability,
                              task: TaskSpecification) -> float:
        """
        能力水平评分 (0-100)

        评估 Agent 的能力是否满足任务难度要求。
        使用 AgentScore.composite_score() 的标准化值。
        """
        score = self._evaluator.get_score(agent_id)
        composite = score.composite_score() if score else 50.0

        # 根据难度调整期望
        difficulty = task.difficulty_score  # 0-1
        # 能力超过难度越多越好，但能力不足会扣分
        ability_ratio = composite / max(difficulty * 100, 1)

        if ability_ratio >= 1.5:
            return 100.0  # 能力远超需求
        elif ability_ratio >= 1.0:
            return 70.0 + (ability_ratio - 1.0) * 60  # 70-100
        elif ability_ratio >= 0.5:
            return ability_ratio * 100  # 50-70
        else:
            return max(10.0, ability_ratio * 100)

    # ── 维度 3: 历史表现 ──

    def _score_historical_performance(self, agent_id: str,
                                       task: TaskSpecification) -> float:
        """
        历史表现评分 (0-100)

        综合：
        - 成功率 (40%)
        - 平均质量 (30%)
        - 协作评分 (20%)
        - 趋势 (10%)
        """
        score = self._evaluator.get_score(agent_id)
        if not score or score.total_tasks == 0:
            return 50.0  # 无数据时给中等分

        perf = (
            score.success_rate * 40 +
            score.avg_quality * 30 +
            score.avg_collaboration * 20 +
            self._trend_score(score.trend) * 10
        )
        return min(perf * 100, 100.0)

    def _trend_score(self, trend: str) -> float:
        return {"improving": 1.0, "stable": 0.7, "declining": 0.3}.get(trend, 0.5)

    # ── 维度 4: 可用性 ──

    def _score_availability(self, agent_id: str,
                             cap: AgentCapability) -> float:
        """
        可用性评分 (0-100)

        基于当前活跃任务数与最大并发数的比率。
        """
        # 从 evaluator 获取当前活跃任务数
        score = self._evaluator.get_score(agent_id)
        active_tasks = len(score.recent_tasks) if score else 0
        max_tasks = cap.max_concurrent_tasks

        if active_tasks >= max_tasks:
            return 10.0  # 满载
        elif active_tasks == 0:
            return 100.0  # 空闲
        else:
            ratio = active_tasks / max_tasks
            return 100.0 - (ratio * 80)  # 50%-100% 区间

    # ── 维度 5: 协作契合度 ──

    def _score_collaboration_fit(self, agent_id: str,
                                  task: TaskSpecification) -> float:
        """
        协作契合度评分 (0-100)

        分析该 Agent 与任务上下文中其他 Agent 的历史协作效果。
        """
        # 检查是否有协作伙伴在任务上下文中
        partners = task.context.get("partner_agents", [])
        if not partners:
            return 70.0  # 无协作上下文时给中等偏上分

        # 检查共享记忆中的协作关系
        collab_network = getattr(self._shared_memory,
                                 "_collaboration_graph", {})
        agent_partners = collab_network.get(agent_id, set())

        if not agent_partners:
            return 40.0  # 无协作历史

        match_count = sum(1 for p in partners if p in agent_partners)
        ratio = match_count / max(len(partners), 1)

        # 检查 evaluator 中的协作评分
        score = self._evaluator.get_score(agent_id)
        collab_score = score.avg_collaboration if score else 0.5

        return min(
            40.0 + ratio * 40.0 + collab_score * 20.0,
            100.0,
        )

    # ── 解释器（用于 CLI/UI 展示） ──

    def _explain_skill(self, cap: AgentCapability,
                        task: TaskSpecification) -> str:
        """技能匹配解释"""
        matched_skills = [s for s in cap.skills if s == task.task_type
                          or task.task_type in s]
        matched_domains = [d for d in cap.domains if d == task.domain
                           or task.domain in d]
        parts = []
        if matched_skills:
            parts.append(f"技能匹配: {', '.join(matched_skills)}")
        if matched_domains:
            parts.append(f"领域匹配: {', '.join(matched_domains)}")
        return "; ".join(parts) if parts else "基础匹配"

    def _explain_performance(self, agent_id: str) -> str:
        """历史表现解释"""
        score = self._evaluator.get_score(agent_id)
        if not score or score.total_tasks == 0:
            return "暂无历史数据"
        return (f"{score.total_tasks} 次任务, "
                f"成功率 {score.success_rate:.0%}, "
                f"趋势 {score.trend}")

    def _explain_availability(self, agent_id: str,
                               cap: AgentCapability) -> str:
        """可用性解释"""
        score = self._evaluator.get_score(agent_id)
        active = len(score.recent_tasks) if score else 0
        return f"活跃 {active}/{cap.max_concurrent_tasks} 任务"


# ── 便捷函数 ──

def format_match_result(result: AgentMatchResult) -> str:
    """格式化匹配结果为可读文本"""
    dims = result.dimensions
    parts = [
        f"  🏆 {result.role:12s} 综合 {result.overall_score:.0f}/100",
        f"     技能 {dims['skill_relevance']:.0f} · "
        f"能力 {dims['ability_level']:.0f} · "
        f"表现 {dims['historical_performance']:.0f} · "
        f"可用 {dims['availability']:.0f} · "
        f"协作 {dims['collaboration_fit']:.0f}",
    ]
    for key, explanation in result.breakdown.items():
        if explanation:
            parts.append(f"     ├─ {explanation}")
    return "\n".join(parts)


def find_agents_for_task(
    task_type: str,
    domain: str = "",
    difficulty: str = "medium",
    top_k: int = 3,
    bus: Optional[MessageBus] = None,
    evaluator: Optional[AgentEvaluator] = None,
    shared_memory: Optional[SharedMemory] = None,
) -> List[AgentMatchResult]:
    """
    便捷函数：一步完成 Agent 查找

    用法:
        results = find_agents_for_task("coding", "python")
        for r in results:
            print(format_match_result(r))
    """
    matcher = CapabilityMatcher(
        bus=bus or MessageBus(),
        evaluator=evaluator or AgentEvaluator(),
        shared_memory=shared_memory or SharedMemory(),
    )
    task = TaskSpecification(
        task_type=task_type,
        domain=domain,
        difficulty=difficulty,
    )
    return matcher.find_best_agents(task, top_k=top_k)
