"""
MU2-B: 任务分解代理 (Task Decomposer)

将复杂任务分解为可执行的子任务树：
1. 复杂度评估 → 是否需要分解？
2. 依赖分析 → 子任务之间的前置/并行关系
3. 分解策略 → 按技能/按阶段/按输出类型
4. 验收标准 → 每个子任务明确的完成定义
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ComplexityLevel(Enum):
    """任务复杂度等级"""
    TRIVIAL = "trivial"         # 无需分解，直接执行
    SIMPLE = "simple"           # 可分解为 2-3 个子任务
    MODERATE = "moderate"       # 需要 3-6 个子任务，有依赖关系
    COMPLEX = "complex"         # 需要 6-12 个子任务，分多个阶段
    VERY_COMPLEX = "very_complex"  # 12+ 子任务，多阶段+并行


class DecompositionStrategy(Enum):
    """分解策略"""
    BY_SKILL = "by_skill"           # 按技能领域分解
    BY_PHASE = "by_phase"           # 按阶段分解（设计→实现→测试）
    BY_OUTPUT = "by_output"         # 按输出类型分解
    BY_MODULE = "by_module"         # 按模块/组件分解
    HYBRID = "hybrid"               # 混合策略


@dataclass
class SubTask:
    """分解后的子任务"""
    id: str
    title: str
    description: str = ""
    required_skills: list[str] = field(default_factory=list)
    estimated_hours: float = 1.0
    depends_on: list[str] = field(default_factory=list)   # 前置子任务 ID
    parallel_with: list[str] = field(default_factory=list)  # 可并行的子任务 ID
    acceptance_criteria: list[str] = field(default_factory=list)
    assigned_role: str = ""          # 后续由路由系统填充
    status: str = "pending"          # pending → ready → running → done
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title,
            "description": self.description,
            "required_skills": self.required_skills,
            "estimated_hours": self.estimated_hours,
            "depends_on": self.depends_on,
            "parallel_with": self.parallel_with,
            "acceptance_criteria": self.acceptance_criteria,
            "assigned_role": self.assigned_role,
            "status": self.status,
        }


@dataclass
class DecompositionResult:
    """分解结果"""
    task_title: str
    complexity: ComplexityLevel
    strategy: DecompositionStrategy
    subtasks: list[SubTask] = field(default_factory=list)
    total_estimated_hours: float = 0.0
    parallel_groups: list[list[str]] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "task_title": self.task_title,
            "complexity": self.complexity.value,
            "strategy": self.strategy.value,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "total_estimated_hours": self.total_estimated_hours,
            "parallel_groups": self.parallel_groups,
            "subtask_count": len(self.subtasks),
        }


class TaskDecomposer:
    """
    任务分解器

    基于规则的任务分解引擎，支持多种分解策略。
    后续可接入 LLM 实现智能分解。
    """

    # 复杂度阈值
    COMPLEXITY_THRESHOLDS = {
        ComplexityLevel.TRIVIAL: {"max_words": 10, "max_skills": 1},
        ComplexityLevel.SIMPLE: {"max_words": 30, "max_skills": 2},
        ComplexityLevel.MODERATE: {"max_words": 80, "max_skills": 3},
        ComplexityLevel.COMPLEX: {"max_words": 200, "max_skills": 5},
    }

    # 预置分解模板
    DECOMPOSITION_TEMPLATES = {
        "code_implementation": {
            "strategy": DecompositionStrategy.BY_PHASE,
            "phases": [
                ("需求分析", ["分析", "需求", "理解"], ["analysis"]),
                ("方案设计", ["设计", "架构", "方案"], ["design", "architecture"]),
                ("编码实现", ["编码", "实现", "开发"], ["coding"]),
                ("测试验证", ["测试", "验证", "调试"], ["testing"]),
                ("文档与提交", ["文档", "提交", "PR"], ["writing"]),
            ],
        },
        "research": {
            "strategy": DecompositionStrategy.BY_OUTPUT,
            "phases": [
                ("信息收集", ["搜索", "收集", "调研"], ["research"]),
                ("分析整理", ["分析", "整理", "归纳"], ["analysis"]),
                ("方案产出", ["报告", "方案", "输出"], ["writing"]),
                ("评审修订", ["评审", "修订", "反馈"], ["critique"]),
            ],
        },
        "bug_fix": {
            "strategy": DecompositionStrategy.BY_PHASE,
            "phases": [
                ("问题复现", ["复现", "诊断", "定位", "修复"], ["testing", "debugging"]),
                ("根因分析", ["根因", "分析", "原因"], ["analysis"]),
                ("修复方案", ["修复", "方案", "修改"], ["design"]),
                ("修复实施", ["实施", "修改", "编码"], ["coding"]),
                ("回归验证", ["回归", "验证", "确认"], ["testing"]),
            ],
        },
    }

    _id_counter: int = 0

    @classmethod
    def _next_id(cls) -> str:
        cls._id_counter += 1
        return f"sub_{int(time.time() * 1000)}_{cls._id_counter}"

    def assess_complexity(self, task_title: str, description: str = "",
                          required_skills: Optional[list[str]] = None) -> ComplexityLevel:
        """
        评估任务复杂度

        Args:
            task_title: 任务标题
            description: 任务描述
            required_skills: 所需技能列表

        Returns:
            复杂度等级
        """
        full_text = f"{task_title} {description}".strip() if description else task_title
        word_count = len(full_text)
        skill_count = len(required_skills or [])

        # 极短任务且无多技能 → TRIVIAL（关键词在短标题中不生效）
        if word_count <= 4 and skill_count <= 1:
            return ComplexityLevel.TRIVIAL

        # 复杂度关键词检测
        complexity_keywords = {
            ComplexityLevel.COMPLEX: ["完整", "系统", "平台", "框架", "集成",
                                       "多个", "分布式", "高并发",
                                       "full", "complete", "system", "platform",
                                       "integrated", "distributed", "multi-"],
            ComplexityLevel.MODERATE: ["模块", "功能", "组件", "接口", "服务",
                                        "方案", "设计",
                                        "module", "feature", "component",
                                        "service", "api", "design", "schema"],
            ComplexityLevel.SIMPLE: ["更新", "修改", "添加", "修复", "优化",
                                      "重构", "升级",
                                      "update", "modify", "add", "fix",
                                      "refactor"],
        }
        for level, keywords in complexity_keywords.items():
            if any(kw in full_text for kw in keywords):
                return level

        # 极短任务且无关键词 → TRIVIAL
        if word_count <= 10 and skill_count <= 1:
            return ComplexityLevel.TRIVIAL

        # 按词数评估
        if word_count > 80:
            return ComplexityLevel.COMPLEX
        if word_count > 30:
            return ComplexityLevel.MODERATE

        # 按技能数评估
        if skill_count >= 5:
            return ComplexityLevel.VERY_COMPLEX
        if skill_count >= 3:
            return ComplexityLevel.MODERATE
        if skill_count >= 2:
            return ComplexityLevel.SIMPLE

        return ComplexityLevel.TRIVIAL

    def find_best_strategy(self, task_title: str, description: str = "",
                           required_skills: Optional[list[str]] = None) -> DecompositionStrategy:
        """
        自动选择最佳分解策略

        Args:
            task_title: 任务标题
            description: 任务描述
            required_skills: 所需技能列表

        Returns:
            最佳分解策略
        """
        text = (task_title + " " + (description or "")).lower()
        skills = [s.lower() for s in (required_skills or [])]

        # 按阶段：包含开发类关键词
        if any(kw in text for kw in ["实现", "开发", "编码", "implement", "develop", "code"]):
            return DecompositionStrategy.BY_PHASE

        # 按模块：包含组件/模块类关键词
        if any(kw in text for kw in ["模块", "组件", "功能", "module", "component", "feature"]):
            return DecompositionStrategy.BY_MODULE

        # 按技能：多个不同技能领域
        if len(skills) >= 3:
            return DecompositionStrategy.BY_SKILL

        # 按输出：包含产出类关键词
        if any(kw in text for kw in ["报告", "文档", "方案", "report", "doc", "plan"]):
            return DecompositionStrategy.BY_OUTPUT

        return DecompositionStrategy.BY_PHASE

    def find_template(self, task_title: str, description: str = "") -> Optional[str]:
        """
        查找匹配的预置分解模板

        Returns:
            模板名称，未匹配返回 None
        """
        text = (task_title + " " + (description or "")).lower()

        for template_name, template in self.DECOMPOSITION_TEMPLATES.items():
            for phase_name, keywords, _ in template["phases"]:
                if any(kw in text for kw in keywords):
                    return template_name

        return None

    def decompose(self, task_id: str, task_title: str, description: str = "",
                  required_skills: Optional[list[str]] = None,
                  force_strategy: Optional[DecompositionStrategy] = None,
                  max_subtasks: int = 15) -> DecompositionResult:
        """
        分解任务为子任务

        Args:
            task_id: 原始任务 ID
            task_title: 任务标题
            description: 任务描述
            required_skills: 所需技能列表
            force_strategy: 强制使用指定策略
            max_subtasks: 最大子任务数

        Returns:
            分解结果
        """
        complexity = self.assess_complexity(task_title, description, required_skills)

        # 简单任务无需分解
        if complexity == ComplexityLevel.TRIVIAL:
            return DecompositionResult(
                task_title=task_title,
                complexity=complexity,
                strategy=DecompositionStrategy.BY_PHASE,
                subtasks=[
                    SubTask(id=task_id, title=task_title,
                            description=description,
                            required_skills=required_skills or [])
                ],
                total_estimated_hours=1.0,
            )

        strategy = force_strategy or self.find_best_strategy(task_title, description, required_skills)
        template_name = self.find_template(task_title, description)

        subtasks: list[SubTask] = []
        parallel_groups: list[list[str]] = []

        if template_name and template_name in self.DECOMPOSITION_TEMPLATES:
            # 基于模板分解
            template = self.DECOMPOSITION_TEMPLATES[template_name]
            prev_id = ""
            for i, (phase_name, keywords, skills) in enumerate(template["phases"]):
                sub = SubTask(
                    id=self._next_id(),
                    title=phase_name,
                    description=f"{task_title} - {phase_name}",
                    required_skills=skills,
                    estimated_hours=max(0.5, 4.0 - i * 0.5),
                    depends_on=[prev_id] if prev_id else [],
                    acceptance_criteria=[f"{phase_name} 完成"],
                )
                subtasks.append(sub)
                prev_id = sub.id
        elif strategy == DecompositionStrategy.BY_SKILL:
            # 按技能分解
            skills = required_skills or ["general"]
            for i, skill in enumerate(skills):
                sub = SubTask(
                    id=self._next_id(),
                    title=f"{skill.upper()} 部分",
                    description=f"使用 {skill} 技能完成 {task_title} 的 {skill} 相关部分",
                    required_skills=[skill],
                    estimated_hours=2.0,
                    depends_on=[],
                    acceptance_criteria=[f"{skill} 部分完成并验证"],
                )
                subtasks.append(sub)
        elif strategy == DecompositionStrategy.BY_MODULE:
            # 按模块分解 — 识别关键词后拆解
            words = (task_title + " " + description).split()
            modules = self._extract_modules(words, max_subtasks)
            prev_id = ""
            for i, (mod_name, mod_desc) in enumerate(modules):
                sub = SubTask(
                    id=self._next_id(),
                    title=mod_name,
                    description=mod_desc,
                    estimated_hours=2.0,
                    depends_on=[prev_id] if prev_id and i < len(modules) // 2 else [],
                    acceptance_criteria=[f"{mod_name} 完成"],
                )
                subtasks.append(sub)
                prev_id = sub.id if i < len(modules) // 2 else prev_id
        else:
            # BY_PHASE / BY_OUTPUT — 通用阶段分解
            phases = [
                ("分析与设计", ["analysis", "design", "architecture"], 2.0),
                ("核心实现", ["coding", "development"], 3.0),
                ("测试与验证", ["testing", "qa"], 1.5),
                ("文档与交付", ["writing", "documentation"], 1.0),
            ]
            prev_id = ""
            for i, (phase_name, skills, hours) in enumerate(phases):
                sub = SubTask(
                    id=self._next_id(),
                    title=phase_name,
                    description=f"{task_title} - {phase_name}",
                    required_skills=skills,
                    estimated_hours=hours,
                    depends_on=[prev_id] if prev_id else [],
                    acceptance_criteria=[f"{phase_name} 完成"],
                )
                subtasks.append(sub)
                prev_id = sub.id

        # 计算并行组
        parallel_groups = self._compute_parallel_groups(subtasks)

        total_hours = sum(s.estimated_hours for s in subtasks)

        return DecompositionResult(
            task_title=task_title,
            complexity=complexity,
            strategy=strategy,
            subtasks=subtasks[:max_subtasks],
            total_estimated_hours=total_hours,
            parallel_groups=parallel_groups,
            metadata={
                "task_id": task_id,
                "template_used": template_name,
                "original_skills": required_skills,
            },
        )

    def _extract_modules(self, words: list[str], max_modules: int) -> list[tuple[str, str]]:
        """从文本中提取模块信息（基于规则的简单实现）"""
        module_keywords = ["模块", "组件", "功能", "页面", "服务", "接口",
                           "module", "component", "service", "api", "page"]
        modules = []
        seen = set()
        for w in words:
            if any(kw in w.lower() for kw in module_keywords):
                if w not in seen:
                    seen.add(w)
                    modules.append((f"实现 {w}", f"完成 {w} 的开发"))
        if not modules:
            modules = [("核心功能", "完成核心功能开发")]
        if len(modules) > max_modules:
            modules = modules[:max_modules]
        return modules

    def _compute_parallel_groups(self, subtasks: list[SubTask]) -> list[list[str]]:
        """
        计算可并行的子任务分组

        依赖链上同一深度的无依赖关系的子任务可以被并行执行
        """
        # 构建依赖图深度
        depths: dict[str, int] = {}
        for sub in subtasks:
            if not sub.depends_on:
                depths[sub.id] = 0
            else:
                max_dep = max(depths.get(d, 0) for d in sub.depends_on)
                depths[sub.id] = max_dep + 1

        # 按深度分组
        groups: dict[int, list[str]] = {}
        for sub_id, depth in depths.items():
            groups.setdefault(depth, []).append(sub_id)

        return list(groups.values())

    def visualize(self, result: DecompositionResult) -> str:
        """
        可视化分解结果（文本形式）

        Args:
            result: 分解结果

        Returns:
            ASCII 树形可视化
        """
        lines = [""]
        lines.append(f"  📋 任务分解: {result.task_title}")
        lines.append(f"  ═══════════════════════════════════════")
        lines.append(f"  复杂度: {result.complexity.value} | 策略: {result.strategy.value}")
        lines.append(f"  子任务: {len(result.subtasks)} | 预估: {result.total_estimated_hours}h")
        lines.append("")

        if result.parallel_groups:
            lines.append("  ┌─ 并行分组 ───────────────────────────")
            for i, group in enumerate(result.parallel_groups):
                group_subs = [s for s in result.subtasks if s.id in group]
                names = " + ".join(s.title for s in group_subs)
                lines.append(f"  │ 组{i+1}: {names}")
            lines.append("  └──────────────────────────────────────")
            lines.append("")

        for i, sub in enumerate(result.subtasks):
            deps = f" [依赖: {', '.join(sub.depends_on[:3])}]" if sub.depends_on else ""
            lines.append(f"  {i+1}. {sub.title} ({sub.estimated_hours}h){deps}")
            if sub.acceptance_criteria:
                for ac in sub.acceptance_criteria:
                    lines.append(f"     ✅ {ac}")
            if sub.required_skills:
                lines.append(f"     🛠️ {', '.join(sub.required_skills)}")

        return "\n".join(lines)
