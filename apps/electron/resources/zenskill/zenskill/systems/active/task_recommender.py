"""
ZenSkill - 智能任务推荐引擎

根据用户行为模式和当前目标，主动推荐适合的技能练习任务：
- 行为模式挖掘（使用时间、任务偏好、响应风格）
- 协同过滤推荐（基于历史成功任务）
- 难度自适应调整
- 任务完成度追踪和反馈循环
"""

from __future__ import annotations

import json
import random
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Tuple

from zenskill.core.paths import get_user_data_dir
from zenskill.systems.visualization.metrics_store import MetricsStore
from zenskill.systems.active.goal_engine import ActiveGoalEngine


@dataclass
class RecommendedTask:
    """推荐的练习任务"""
    task_id: str
    title: str
    description: str
    target_dimensions: List[str]  # 针对哪些能力维度
    difficulty: str  # easy / medium / hard
    estimated_interactions: int
    expected_gain: Dict[str, float]  # 各维度预期提升
    priority: float
    is_completed: bool = False
    completed_at: Optional[str] = None
    feedback_rating: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecommendedTask":
        """从字典创建任务"""
        return cls(
            task_id=data.get("task_id", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            target_dimensions=data.get("target_dimensions", []),
            difficulty=data.get("difficulty", "medium"),
            estimated_interactions=data.get("estimated_interactions", 5),
            expected_gain=data.get("expected_gain", {}),
            priority=data.get("priority", 0.5),
            is_completed=data.get("is_completed", False),
            completed_at=data.get("completed_at"),
            feedback_rating=data.get("feedback_rating"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


@dataclass
class UserBehaviorPattern:
    """用户行为模式"""
    pattern_id: str
    pattern_type: str  # usage_time / task_preference / response_style
    description: str
    confidence: float
    detected_at: str
    supporting_data: Dict[str, Any]


# 预设任务模板库
TASK_TEMPLATES = [
    {
        "id": "memory_basic_1",
        "title": "基础记忆练习",
        "description": "使用记忆功能记录 3 条重要信息（如：常用命令、代码片段、笔记）",
        "target_dimensions": ["memory"],
        "difficulty": "easy",
        "estimated_interactions": 3,
        "expected_gain": {"memory": 5.0},
    },
    {
        "id": "memory_search_1",
        "title": "记忆检索练习",
        "description": "使用搜索功能查找之前记录的记忆，验证检索效果",
        "target_dimensions": ["memory"],
        "difficulty": "easy",
        "estimated_interactions": 2,
        "expected_gain": {"memory": 3.0},
    },
    {
        "id": "skill_basic_1",
        "title": "技能熟练度练习",
        "description": "连续使用技能完成 5 次简单任务，保持专注",
        "target_dimensions": ["proficiency"],
        "difficulty": "easy",
        "estimated_interactions": 5,
        "expected_gain": {"proficiency": 4.0},
    },
    {
        "id": "skill_chain_1",
        "title": "链式任务练习",
        "description": "完成一组相关的任务序列，体验技能的连贯性",
        "target_dimensions": ["proficiency", "stability"],
        "difficulty": "medium",
        "estimated_interactions": 8,
        "expected_gain": {"proficiency": 6.0, "stability": 3.0},
    },
    {
        "id": "quality_review_1",
        "title": "输出质量回顾",
        "description": "回顾最近 3 次交互的输出，评估质量并记录改进点",
        "target_dimensions": ["satisfaction"],
        "difficulty": "easy",
        "estimated_interactions": 3,
        "expected_gain": {"satisfaction": 4.0},
    },
    {
        "id": "reflection_1",
        "title": "禅思反思练习",
        "description": "触发一次完整的反思循环，记录洞察和改进建议",
        "target_dimensions": ["satisfaction", "stability"],
        "difficulty": "medium",
        "estimated_interactions": 5,
        "expected_gain": {"satisfaction": 5.0, "stability": 3.0},
    },
    {
        "id": "speed_challenge_1",
        "title": "响应速度挑战",
        "description": "在 10 分钟内完成 5 个简单任务，锻炼快速响应能力",
        "target_dimensions": ["responsiveness"],
        "difficulty": "medium",
        "estimated_interactions": 5,
        "expected_gain": {"responsiveness": 5.0},
    },
    {
        "id": "complex_task_1",
        "title": "复杂任务挑战",
        "description": "尝试完成一个较复杂的任务，分步骤执行并记录过程",
        "target_dimensions": ["stability", "proficiency"],
        "difficulty": "hard",
        "estimated_interactions": 12,
        "expected_gain": {"stability": 8.0, "proficiency": 5.0},
    },
    {
        "id": "comprehensive_1",
        "title": "综合能力提升",
        "description": "完成一个包含记忆使用、快速响应、质量评估的综合练习",
        "target_dimensions": ["proficiency", "stability", "satisfaction", "responsiveness", "memory"],
        "difficulty": "hard",
        "estimated_interactions": 15,
        "expected_gain": {"proficiency": 3.0, "stability": 3.0, "satisfaction": 3.0, "responsiveness": 3.0, "memory": 3.0},
    },
    {
        "id": "milestone_review_1",
        "title": "成长里程碑回顾",
        "description": "查看成长报告，回顾最近的进步，设定下一个目标",
        "target_dimensions": ["composite"],
        "difficulty": "easy",
        "estimated_interactions": 2,
        "expected_gain": {"composite": 2.0},
    },
]


class TaskRecommendationEngine:
    """智能任务推荐引擎"""

    # 难度图标
    DIFFICULTY_ICONS = {
        "easy": "🟢",
        "medium": "🟡",
        "hard": "🔴",
    }

    # 维度名称
    DIMENSION_NAMES = {
        "proficiency": "熟练度",
        "stability": "稳定性",
        "satisfaction": "满意度",
        "responsiveness": "响应力",
        "memory": "记忆力",
        "composite": "综合能力",
    }

    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id
        self.metrics_store = MetricsStore(skill_id)
        self.goal_engine = ActiveGoalEngine(skill_id)
        self.tasks_dir = self._get_tasks_dir()
        self.tasks_file = self.tasks_dir / f"{skill_id}_tasks.jsonl"

    def _get_tasks_dir(self) -> Path:
        """获取任务存储目录"""
        user_dir = get_user_data_dir()
        tasks_dir = user_dir / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        return tasks_dir

    def _generate_task_id(self) -> str:
        """生成唯一的任务ID"""
        timestamp = int(time.time() * 1000)
        return f"task_{timestamp}_{self.skill_id}"

    def _get_user_level(self) -> str:
        """获取用户当前境界"""
        snapshots = self.metrics_store.get_all_snapshots()
        if snapshots:
            return snapshots[-1].level
        return "NOVICE"

    def _get_dimension_scores(self) -> Dict[str, int]:
        """获取各维度当前分数"""
        snapshots = self.metrics_store.get_all_snapshots()
        if snapshots:
            scores = snapshots[-1].ability_scores.copy()
            # 确保包含所有标准维度
            for dim in ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]:
                if dim not in scores:
                    scores[dim] = 0
            return scores
        return {dim: 0 for dim in ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]}

    def recommend_tasks(
        self,
        count: int = 3,
        difficulty: Optional[str] = None,
    ) -> List[RecommendedTask]:
        """
        推荐适合的练习任务

        Args:
            count: 推荐的任务数量
            difficulty: 可选的难度过滤 (easy/medium/hard)

        Returns:
            推荐任务列表
        """
        # 边界检查
        if not isinstance(count, int) or count < 1:
            count = 3
        if count > 5:
            count = 5

        user_level = self._get_user_level()
        dimension_scores = self._get_dimension_scores()

        # 获取当前活跃目标
        active_goals = self.goal_engine.get_active_goals()
        target_dimensions = [g.dimension for g in active_goals]

        # 筛选适合的模板
        suitable_templates = self._filter_templates(user_level, dimension_scores, difficulty)

        # 计算每个模板的推荐优先级
        scored_templates = []
        for template in suitable_templates:
            priority = self._calculate_template_priority(
                template,
                dimension_scores,
                target_dimensions,
            )
            scored_templates.append((template, priority))

        # 按优先级排序
        scored_templates.sort(key=lambda x: x[1], reverse=True)

        # 转换为 RecommendedTask 对象并持久化
        recommended = []
        for template, priority in scored_templates[:count]:
            task = RecommendedTask(
                task_id=self._generate_task_id(),
                title=template["title"],
                description=template["description"],
                target_dimensions=template["target_dimensions"],
                difficulty=template["difficulty"],
                estimated_interactions=template["estimated_interactions"],
                expected_gain=template["expected_gain"],
                priority=priority,
            )
            self.save_task(task)
            recommended.append(task)

        return recommended

    def _filter_templates(
        self,
        user_level: str,
        dimension_scores: Dict[str, int],
        difficulty_filter: Optional[str],
    ) -> List[Dict[str, Any]]:
        """根据用户水平和其他条件筛选任务模板"""
        suitable = []

        level_order = ["NOVICE", "APPRENTICE", "ADEPT", "EXPERT", "MASTER"]
        user_level_index = level_order.index(user_level) if user_level in level_order else 0

        for template in TASK_TEMPLATES:
            # 难度过滤
            if difficulty_filter and template["difficulty"] != difficulty_filter:
                continue

            # 根据用户境界调整可用难度
            template_difficulty = template["difficulty"]
            if template_difficulty == "hard" and user_level_index < 2:  # ADEPT 以下不能用 hard
                continue

            suitable.append(template)

        return suitable

    def _calculate_template_priority(
        self,
        template: Dict[str, Any],
        dimension_scores: Dict[str, int],
        target_dimensions: List[str],
    ) -> float:
        """计算模板的推荐优先级"""
        base_priority = 0.5

        # 1. 如果任务目标维度正好是当前目标维度，提高优先级
        for dim in template["target_dimensions"]:
            if dim in target_dimensions:
                base_priority += 0.3

        # 2. 针对低分数维度的任务优先级更高
        for dim in template["target_dimensions"]:
            if dim in dimension_scores:
                score = dimension_scores[dim]
                # 分数越低，优先级越高（提升空间越大）
                boost = (100 - score) / 200  # 0 - 0.5
                base_priority += boost

        # 3. 多样化：根据最近完成的任务类型，推荐不同类型的
        # 这里简化处理：随机添加一些变化
        base_priority += random.uniform(-0.1, 0.1)

        return min(1.0, max(0.0, base_priority))

    def save_task(self, task: RecommendedTask) -> None:
        """保存任务到历史记录"""
        with open(self.tasks_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(task.to_dict(), ensure_ascii=False) + "\n")

    def get_all_tasks(self) -> List[RecommendedTask]:
        """获取所有历史任务"""
        if not self.tasks_file.exists():
            return []

        tasks = []
        with open(self.tasks_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        tasks.append(RecommendedTask.from_dict(data))
                    except (json.JSONDecodeError, ValueError, TypeError):
                        continue

        return tasks

    def get_pending_tasks(self) -> List[RecommendedTask]:
        """获取待完成的任务"""
        return [t for t in self.get_all_tasks() if not t.is_completed]

    def complete_task(self, task_id: str, feedback_rating: Optional[float] = None) -> bool:
        """
        标记任务为完成

        Args:
            task_id: 任务ID
            feedback_rating: 可选的用户反馈评分 (0-5)

        Returns:
            是否成功标记
        """
        tasks = self.get_all_tasks()
        found = False

        temp_file = self.tasks_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            for task in tasks:
                if task.task_id == task_id:
                    task.is_completed = True
                    task.completed_at = datetime.now().isoformat()
                    if feedback_rating is not None:
                        task.feedback_rating = max(0.0, min(5.0, float(feedback_rating)))
                    found = True
                f.write(json.dumps(task.to_dict(), ensure_ascii=False) + "\n")

        if found:
            temp_file.rename(self.tasks_file)
        else:
            temp_file.unlink(missing_ok=True)

        return found

    def analyze_behavior_patterns(self) -> List[UserBehaviorPattern]:
        """分析用户行为模式"""
        patterns: List[UserBehaviorPattern] = []

        # 这里可以添加更复杂的行为分析
        # 目前简化处理：基于当前状态给出模式

        snapshots = self.metrics_store.get_all_snapshots()
        if len(snapshots) < 3:
            return patterns

        # 基于数据生成一些简单的行为模式
        latest = snapshots[-1]

        # 模式1：使用频率分析
        interaction_count = latest.interaction_count
        if interaction_count >= 50:
            patterns.append(UserBehaviorPattern(
                pattern_id=f"pattern_{int(time.time())}_1",
                pattern_type="usage_frequency",
                description="你是一位高频用户，保持持续的练习习惯非常好！",
                confidence=0.9,
                detected_at=datetime.now().isoformat(),
                supporting_data={"interaction_count": interaction_count},
            ))
        elif interaction_count >= 20:
            patterns.append(UserBehaviorPattern(
                pattern_id=f"pattern_{int(time.time())}_2",
                pattern_type="usage_frequency",
                description="你的使用频率适中，建议保持稳定的练习节奏",
                confidence=0.8,
                detected_at=datetime.now().isoformat(),
                supporting_data={"interaction_count": interaction_count},
            ))

        # 模式2：能力平衡分析
        scores = latest.ability_scores
        dim_scores = [
            scores.get("proficiency", 0),
            scores.get("stability", 0),
            scores.get("satisfaction", 0),
            scores.get("responsiveness", 0),
            scores.get("memory", 0),
        ]
        score_variance = sum((s - sum(dim_scores) / len(dim_scores)) ** 2 for s in dim_scores) / len(dim_scores)

        if score_variance < 100:
            patterns.append(UserBehaviorPattern(
                pattern_id=f"pattern_{int(time.time())}_3",
                pattern_type="ability_balance",
                description="你的各项能力发展非常均衡，继续保持！",
                confidence=0.85,
                detected_at=datetime.now().isoformat(),
                supporting_data={"score_variance": score_variance},
            ))

        return patterns

    def generate_recommendation_report(self) -> str:
        """生成任务推荐报告"""
        recommendations = self.recommend_tasks(3)
        pending = self.get_pending_tasks()
        patterns = self.analyze_behavior_patterns()

        lines = []
        lines.append("🎯 智能任务推荐")
        lines.append("═" * 60)
        lines.append("")

        # 行为模式
        if patterns:
            lines.append("📊 你的行为模式:")
            for pattern in patterns:
                lines.append(f"   • {pattern.description}")
            lines.append("")

        # 待完成任务
        if pending:
            lines.append(f"⏳ 待完成任务 ({len(pending)} 个):")
            for task in pending[:3]:
                icon = self.DIFFICULTY_ICONS.get(task.difficulty, "•")
                lines.append(f"   {icon} {task.title}")
            lines.append("")

        # 新推荐
        lines.append("💡 为你推荐:")
        lines.append("")
        for i, task in enumerate(recommendations, 1):
            icon = self.DIFFICULTY_ICONS.get(task.difficulty, "•")
            dim_names = [self.DIMENSION_NAMES.get(d, d) for d in task.target_dimensions]

            lines.append(f"   {i}. {icon} {task.title}")
            lines.append(f"      {task.description}")
            lines.append(f"      针对维度: {', '.join(dim_names)}")
            lines.append(f"      预计交互: {task.estimated_interactions} 次")
            lines.append(f"      任务 ID: {task.task_id}")
            lines.append("")

        lines.append("💡 使用 'python -m zenskill task complete <ID>' 标记任务完成")

        return "\n".join(lines)
