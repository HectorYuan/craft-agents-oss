"""
技能定义 DSL + 自然语言解析器 (Phase 9F + 9G)

允许用户用自然语言描述技能，自动转换为结构化 SkillDefinition。
"""

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════
# 9F: Skill DSL 数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class SkillDefinition:
    """技能定义 DSL"""
    name: str
    description: str = ""
    category: str = "general"            # dev/design/data/ops/writing
    difficulty: str = "beginner"         # beginner/intermediate/advanced/expert

    # 五维能力映射
    proficiency_weight: float = 0.2      # 熟练度权重
    stability_weight: float = 0.2        # 稳定性权重
    satisfaction_weight: float = 0.2     # 满意度权重
    responsiveness_weight: float = 0.2   # 响应力权重
    memory_weight: float = 0.2           # 记忆力权重

    # 前置依赖
    prerequisites: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)

    # 练习模板
    practice_tasks: List[Dict[str, str]] = field(default_factory=list)
    # 评估指标
    success_metrics: List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """导出为可读 Markdown"""
        lines = [
            f"# {self.name}",
            f"",
            f"**分类**: {self.category} | **难度**: {self.difficulty}",
            f"",
            f"## 描述",
            f"{self.description}",
            f"",
            f"## 五维权重",
            f"| 维度 | 权重 |",
            f"|------|------|",
            f"| 熟练度 | {self.proficiency_weight:.0%} |",
            f"| 稳定性 | {self.stability_weight:.0%} |",
            f"| 满意度 | {self.satisfaction_weight:.0%} |",
            f"| 响应力 | {self.responsiveness_weight:.0%} |",
            f"| 记忆力 | {self.memory_weight:.0%} |",
        ]
        if self.prerequisites:
            lines.append("")
            lines.append("## 前置依赖")
            for p in self.prerequisites:
                lines.append(f"- {p}")
        if self.tools:
            lines.append("")
            lines.append("## 推荐工具")
            for t in self.tools:
                lines.append(f"- {t}")
        if self.practice_tasks:
            lines.append("")
            lines.append("## 练习任务")
            for i, task in enumerate(self.practice_tasks, 1):
                lines.append(f"{i}. **{task.get('level', '')}**: {task.get('description', '')}")
        return "\n".join(lines)

    def to_spec(self) -> "SkillSpec":
        """升级到 SkillSpec (Phase S)"""
        from .core.skill_spec import SkillSpec
        return SkillSpec.from_definition(self)


# ═══════════════════════════════════════════════════════════════
# 9G: 自然语言解析器
# ═══════════════════════════════════════════════════════════════

class SkillNLParser:
    """将自然语言描述解析为 SkillDefinition"""

    CATEGORY_KEYWORDS = {
        "dev": ["编程", "开发", "代码", "coding", "programming", "software",
                "python", "javascript", "rust", "go", "java", "后端", "前端",
                "api", "web", "app", "application"],
        "design": ["设计", "design", "ui", "ux", "界面", "layout", "视觉",
                   "graphic", "prototype", "原型", "figma"],
        "data": ["数据", "data", "分析", "analytics", "统计", "statistics",
                 "machine learning", "ml", "ai", "pandas", "sql", "可视化"],
        "ops": ["运维", "部署", "deploy", "docker", "kubernetes", "k8s",
                "ci", "cd", "pipeline", "监控", "monitoring", "云", "cloud"],
        "writing": ["写作", "文档", "documentation", "writing", "blog",
                    "翻译", "translate", "编辑", "edit"],
        "general": [],
    }

    DIFFICULTY_PATTERNS = [
        (r"入门|基础|新手|beginner|basic|简单|入门级", "beginner"),
        (r"中级|进阶|intermediate|熟练|medium", "intermediate"),
        (r"高级|advanced|专家|expert|精通|深入|复杂", "advanced"),
    ]

    TOOL_PATTERNS = {
        "git": [r"\bgit\b", r"版本控制", r"github", r"gitlab"],
        "docker": [r"\bdocker\b", r"容器", r"container"],
        "vscode": [r"\bvscode\b", r"vs code", r"visual studio"],
        "python": [r"\bpython\b", r"pip\b"],
        "fastapi": [r"\bfastapi\b", r"fast api"],
        "pytest": [r"\bpytest\b", r"测试", r"unit test"],
    }

    def parse(self, text: str, name: Optional[str] = None) -> SkillDefinition:
        """解析自然语言 → SkillDefinition"""
        text_lower = text.lower()

        # 名称
        if not name:
            name = self._extract_name(text)

        # 分类
        category = self._classify_category(text_lower)

        # 难度
        difficulty = self._extract_difficulty(text_lower)

        # 工具
        tools = self._extract_tools(text_lower)

        # 生成练习任务
        practice = self._generate_practice_tasks(name, category, difficulty)

        return SkillDefinition(
            name=name,
            description=text[:200],
            category=category,
            difficulty=difficulty,
            tools=tools,
            practice_tasks=practice,
            success_metrics=[f"完成 5 个 {name} 相关任务", f"{name} 熟练度达到 60"],
        )

    def _extract_name(self, text: str) -> str:
        """从描述中提取技能名"""
        # 尝试匹配 "学习 X" / "掌握 X" / "X 技能"
        m = re.search(r"(?:学习|掌握|练习|提升|加强)\s*(.{2,20}?)(?:技能|能力|方面)?$", text)
        if m:
            return m.group(1).strip()
        # 取前 20 个字符
        return text[:20].strip()

    def _classify_category(self, text_lower: str) -> str:
        """分类技能领域"""
        scores: Dict[str, int] = {}
        for cat, keywords in self.CATEGORY_KEYWORDS.items():
            scores[cat] = sum(1 for kw in keywords if kw in text_lower)
        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        return best if scores[best] > 0 else "general"

    def _extract_difficulty(self, text_lower: str) -> str:
        """提取难度等级"""
        for pattern, level in self.DIFFICULTY_PATTERNS:
            if re.search(pattern, text_lower):
                return level
        return "beginner"

    def _extract_tools(self, text_lower: str) -> List[str]:
        """提取涉及的工具"""
        tools = []
        for tool, patterns in self.TOOL_PATTERNS.items():
            if any(re.search(p, text_lower) for p in patterns):
                tools.append(tool)
        return tools

    def _generate_practice_tasks(
        self, name: str, category: str, difficulty: str
    ) -> List[Dict[str, str]]:
        """根据分类和难度生成练习任务模板"""
        templates = {
            "dev": [
                {"level": "入门", "description": f"完成 {name} 的 Hello World 项目"},
                {"level": "进阶", "description": f"用 {name} 实现一个 CRUD 应用"},
                {"level": "高级", "description": f"优化 {name} 项目的性能和架构"},
            ],
            "data": [
                {"level": "入门", "description": f"用 {name} 导入并清洗一份数据集"},
                {"level": "进阶", "description": f"用 {name} 做探索性数据分析和可视化"},
                {"level": "高级", "description": f"用 {name} 构建预测模型并评估"},
            ],
            "ops": [
                {"level": "入门", "description": f"用 {name} 本地启动一个服务"},
                {"level": "进阶", "description": f"用 {name} 配置 CI/CD 流水线"},
                {"level": "高级", "description": f"用 {name} 设计高可用集群方案"},
            ],
            "design": [
                {"level": "入门", "description": f"用 {name} 设计一个登录页面"},
                {"level": "进阶", "description": f"用 {name} 完成完整的产品原型"},
                {"level": "高级", "description": f"用 {name} 构建设计系统组件库"},
            ],
            "writing": [
                {"level": "入门", "description": f"用 {name} 写一篇技术博客"},
                {"level": "进阶", "description": f"用 {name} 撰写完整的项目文档"},
                {"level": "高级", "description": f"用 {name} 编写开源项目贡献指南"},
            ],
            "general": [
                {"level": "入门", "description": f"了解 {name} 的基础概念"},
                {"level": "进阶", "description": f"在项目中实际应用 {name}"},
                {"level": "高级", "description": f"成为 {name} 的专家，可以指导他人"},
            ],
        }
        return templates.get(category, templates["general"])


# ═══════════════════════════════════════════════════════════════
# 9H: 技能模板引擎
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# 9I: 自动测试用例生成 (基于 LLM)
# ═══════════════════════════════════════════════════════════════

class SkillTestGenerator:
    """利用 LLM 为技能定义生成测试用例和评估标准"""

    @staticmethod
    def build_prompt(skill: SkillDefinition) -> str:
        """构建 LLM prompt"""
        tasks_text = "\n".join(
            f"- [{t['level']}] {t['description']}"
            for t in skill.practice_tasks
        )
        return f"""为以下技能生成 5 个具体、可量化的测试用例：

技能名称: {skill.name}
分类: {skill.category}
难度: {skill.difficulty}
描述: {skill.description}
前置依赖: {', '.join(skill.prerequisites) or '无'}
推荐工具: {', '.join(skill.tools) or '无'}

练习任务:
{tasks_text}

请输出 5 个测试用例，每个包含：
1. test_name: 测试名称
2. scenario: 测试场景描述
3. expected: 预期结果
4. difficulty: 难度 (beginner/intermediate/advanced)
5. points: 分值 (1-10)

输出格式为 JSON 数组，不要包含其他文本。"""

    async def generate(self, skill: SkillDefinition) -> list[dict]:
        """调用 LLM 生成测试用例"""
        try:
            from zenskill.core.llm_provider import (
                get_llm_provider, ChatMessage, DeepSeekLLMProvider
            )

            prompt = self.build_prompt(skill)
            # 用 flash 模型（非推理）确保生成完整 JSON，足够 token
            provider = DeepSeekLLMProvider(model="deepseek-v4-flash")
            messages = [ChatMessage(role="user", content=prompt)]

            resp = await provider.chat(messages, max_tokens=2000, temperature=0.2)
            parsed = self._parse_response(resp.content)
            if parsed:
                return parsed
            return self._fallback_generate(skill)

        except Exception:
            return self._fallback_generate(skill)

    def _parse_response(self, content: str) -> list[dict]:
        """解析 LLM JSON 响应"""
        import json
        import re

        # 尝试提取 JSON 数组
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return []

    def _fallback_generate(self, skill: SkillDefinition) -> list[dict]:
        """LLM 不可用时用模板生成"""
        tests = []
        levels = ["beginner", "beginner", "intermediate", "intermediate", "advanced"]

        templates = {
            "dev": [
                ("环境搭建", f"成功配置 {skill.name} 开发环境", "工具链可用", 3),
                ("基础语法", f"完成 {skill.name} 基础语法练习", "通过所有单元测试", 5),
                ("CRUD 实现", f"用 {skill.name} 实现数据增删改查", "API 返回正确状态码", 7),
                ("异常处理", f"处理 {skill.name} 中的异常场景", "异常被正确捕获和记录", 6),
                ("性能测试", f"对 {skill.name} 项目做性能基准测试", "响应时间 < 100ms", 8),
            ],
            "data": [
                ("数据加载", f"用 {skill.name} 加载 CSV 数据集", "数据行数正确", 3),
                ("数据清洗", f"清洗数据集中的缺失值和异常值", "缺失值处理率 100%", 5),
                ("可视化", f"用 {skill.name} 生成图表", "图表正确显示", 6),
                ("统计分析", f"对数据集做描述性统计", "统计指标正确", 7),
                ("模型训练", f"用 {skill.name} 训练简单模型", "模型收敛", 8),
            ],
        }

        template = templates.get(skill.category, templates["dev"])
        for i, (name, scenario, expected, points) in enumerate(template):
            tests.append({
                "test_name": f"{skill.name} - {name}",
                "scenario": scenario,
                "expected": expected,
                "difficulty": levels[i],
                "points": points,
            })

        return tests


class SkillTemplateEngine:
    """基于 SkillDefinition 生成多种格式的输出"""

    def render_skill_md(self, skill: SkillDefinition) -> str:
        """渲染为 SKILL.md 格式（Claude Code 兼容）"""
        lines = [
            "---",
            f"name: {skill.name.lower().replace(' ', '-')}",
            f"description: {skill.description[:100]}",
            f"category: {skill.category}",
            "metadata:",
            f"  difficulty: {skill.difficulty}",
            f"  version: '0.1.0'",
            "---",
            "",
            f"# {skill.name}",
            "",
            skill.description,
            "",
            "## 前置要求",
        ]
        if skill.prerequisites:
            for p in skill.prerequisites:
                lines.append(f"- {p}")
        else:
            lines.append("- 无")
        lines.append("")
        lines.append("## 练习计划")
        for task in skill.practice_tasks:
            lines.append(
                f"- [{task['level']}] {task['description']}"
            )
        return "\n".join(lines)

    def render_practice_plan(self, skill: SkillDefinition, days: int = 7) -> str:
        """生成 N 天练习计划"""
        import datetime

        lines = [
            f"# {skill.name} — {days} 天练习计划",
            "",
            f"**难度**: {skill.difficulty} | **分类**: {skill.category}",
            "",
        ]

        today = datetime.date.today()
        for day in range(days):
            d = today + datetime.timedelta(days=day)
            task_idx = min(day, len(skill.practice_tasks) - 1)
            task = skill.practice_tasks[task_idx]
            lines.append(f"### Day {day + 1} — {d.strftime('%m/%d')} ({d.strftime('%A')})")
            lines.append(f"- {task['description']}")
            if day % 3 == 0 and day > 0:
                lines.append(f"- 📝 回顾前 3 天的学习收获")
            lines.append("")

        return "\n".join(lines)

    def render_checklist(self, skill: SkillDefinition) -> str:
        """生成技能掌握清单"""
        lines = [
            f"# {skill.name} 掌握清单",
            "",
            "完成以下所有检查项即视为掌握本技能：",
            "",
        ]
        checks = [
            f"- [ ] 理解 {skill.name} 的核心概念",
            f"- [ ] 完成入门级练习任务",
            f"- [ ] 在真实项目中应用 {skill.name}",
            f"- [ ] 能够独立解决 {skill.name} 相关问题",
            f"- [ ] 能向他人解释 {skill.name} 的原理",
        ]
        for c in checks:
            lines.append(c)
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# 8I: 预置技能模板库
# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# 9J: 技能代码生成引擎
# ═══════════════════════════════════════════════════════════════

class SkillCodeGenerator:
    """
    从 SkillDefinition 生成可执行的 Python 代码

    生成内容：
    - 技能状态管理类（继承 SkillManifest）
    - 练习任务生成函数
    - 评估函数
    - 多 Agent 提示词模板
    - 记忆索引配置
    """

    def generate(self, skill: SkillDefinition, skill_id: str = None) -> str:
        """
        生成完整的可执行 Python 技能模块

        Args:
            skill: 技能定义
            skill_id: 技能标识符（默认从 name 推导）

        Returns:
            完整的 Python 模块源代码
        """
        sid = skill_id or self._to_skill_id(skill.name)

        sections = [
            self._generate_header(skill, sid),
            self._generate_skill_manifest(skill, sid),
            self._generate_task_generator(skill, sid),
            self._generate_evaluator(skill, sid),
            self._generate_prompt_templates(skill, sid),
            self._generate_memory_config(skill, sid),
            self._generate_main_block(skill, sid),
        ]

        return "\n\n".join(sections)

    def _to_skill_id(self, name: str) -> str:
        """将技能名转换为 skill_id"""
        import re
        return re.sub(r"[^a-z0-9]+", "-", name.lower().strip()).strip("-")

    # ── 模块头部 ──

    def _generate_header(self, skill: SkillDefinition, sid: str) -> str:
        safe_name = skill.name.replace("'", "").replace('"', '')
        safe_desc = skill.description[:100].replace("'", "").replace('"', "").replace("\\", "")
        return '''"""
ZenSkill 技能模块: ''' + safe_name + '''

自动生成于 ZenSkill SkillCodeGenerator (Phase 9J)

分类: ''' + skill.category + ''' | 难度: ''' + skill.difficulty + '''
描述: ''' + safe_desc + '''

运行时自动注册到 zenskill 技能管理器中。
"""

from zenskill.systems.cultivating.skill_manifest import (
    SkillManifest, SkillLevel, SkillStat, SkillMilestone,
)
from zenskill.core.paths import SkillStateManager
from typing import Any, Dict, List, Optional
from datetime import datetime
import random


__skill_id__ = "''' + sid + '''"
__skill_name__ = "''' + skill.name + '''"'''

    # ── SkillManifest 子类 ──

    def _generate_skill_manifest(self, skill: SkillDefinition, sid: str) -> str:
        """生成技能 Manifest 类"""
        class_name = self._to_class_name(sid)
        p_w = skill.proficiency_weight
        s_w = skill.stability_weight
        sa_w = skill.satisfaction_weight
        r_w = skill.responsiveness_weight
        m_w = skill.memory_weight

        return '''\
class ''' + class_name + '''Manifest(SkillManifest):
    """
    ''' + skill.name + ''' 技能修炼档案
    """

    SKILL_ID = "''' + sid + '''"
    SKILL_NAME = "''' + skill.name + '''"
    CATEGORY = "''' + skill.category + '''"
    DIFFICULTY = "''' + skill.difficulty + '''"

    DIMENSION_WEIGHTS = {
        "proficiency": ''' + str(p_w) + ''',
        "stability": ''' + str(s_w) + ''',
        "satisfaction": ''' + str(sa_w) + ''',
        "responsiveness": ''' + str(r_w) + ''',
        "memory": ''' + str(m_w) + ''',
    }

    TOOLS = ''' + repr(skill.tools) + '''
    PREREQUISITES = ''' + repr(skill.prerequisites) + '''

    def __init__(self):
        super().__init__(
            skill_id=self.SKILL_ID,
            skill_name=self.SKILL_NAME,
        )

    def should_level_up(self):
        stats = self.stats
        level = self.current_level

        next_level = SkillLevel(min(level.value + 1, 5))
        thresholds = {
            SkillLevel.APPRENTICE: stats.total_interactions >= 10,
            SkillLevel.ADEPT: (stats.total_interactions >= 50 and
                              stats.successful_executions / max(stats.total_interactions, 1) >= 0.7),
            SkillLevel.EXPERT: (stats.total_interactions >= 200 and
                               stats.user_feedback_score >= 0.8),
            SkillLevel.MASTER: (stats.total_interactions >= 500 and
                               stats.user_feedback_score >= 0.9 and
                               stats.memory_usage_count >= 100),
        }

        if next_level in thresholds:
            return thresholds[next_level]
        return False

    def get_practice_tasks(self, count=3):
        return TaskGenerator.generate_tasks(count=count)'''

    # ── 任务生成器 ──

    def _generate_task_generator(self, skill: SkillDefinition, sid: str) -> str:
        """生成练习任务生成器"""
        tasks_str = ""
        for i, task in enumerate(skill.practice_tasks):
            tasks_str += (
                f'        {{"id": "task-{i+1:02d}", '
                f'"level": "{task.get("level", "beginner")}", '
                f'"description": """{task.get("description", "")}""", '
                f'"category": "{skill.category}"}},\n'
            )

        return f'''
class TaskGenerator:
    """{skill.name} 练习任务生成器"""

    TASKS = [
{tasks_str}    ]

    @classmethod
    def generate_tasks(cls, count: int = 3, difficulty: str = None) -> List[Dict]:
        """生成练习任务

        Args:
            count: 任务数量
            difficulty: 难度筛选（beginner/intermediate/advanced），None 则不筛选

        Returns:
            任务列表
        """
        candidates = cls.TASKS
        if difficulty:
            candidates = [t for t in candidates if t["level"] == difficulty]
        if not candidates:
            candidates = cls.TASKS

        selected = random.sample(candidates, min(count, len(candidates)))
        for t in selected:
            t["assigned_at"] = datetime.now().isoformat()
        return selected

    @classmethod
    def get_daily_task(cls) -> Dict:
        """获取每日推荐任务"""
        tasks = cls.generate_tasks(count=1)
        return tasks[0] if tasks else {{}}

    @classmethod
    def list_by_level(cls, level: str) -> List[Dict]:
        """按难度列出所有任务"""
        return [t for t in cls.TASKS if t["level"] == level]'''

    # ── 评估函数 ──

    def _generate_evaluator(self, skill: SkillDefinition, sid: str) -> str:
        """生成评估函数"""
        success_lines = ""
        for i, metric in enumerate(skill.success_metrics):
            success_lines += f'        "{metric}",\n'

        return f'''
class SkillEvaluator:
    """{skill.name} 技能评估器"""

    SUCCESS_METRICS = [
{success_lines}    ]

    @classmethod
    def evaluate_task(cls, task_result: Dict) -> Dict[str, Any]:
        """评估用户完成的任务

        Args:
            task_result: {{
                "task_id": str,
                "completed": bool,
                "duration_min": float,
                "self_score": float (0-1),
                "output_quality": str (good/medium/poor),
            }}

        Returns:
            {{"score", "feedback", "suggestions"}}
        """
        score = 0.0
        feedback = []
        suggestions = []

        # 完成度
        if task_result.get("completed"):
            score += 0.3
        else:
            suggestions.append("建议完成任务后再提交评估")

        # 自我评估
        self_score = task_result.get("self_score", 0.5)
        score += self_score * 0.3

        # 产出质量
        quality = task_result.get("output_quality", "medium")
        quality_scores = {{"good": 0.3, "medium": 0.15, "poor": 0.05}}
        score += quality_scores.get(quality, 0.1)

        # 效率
        duration = task_result.get("duration_min", 60)
        if duration < 30:
            score += 0.1
            feedback.append("⚡ 高效完成任务")

        if score >= 0.8:
            feedback.append("🌟 表现优秀，继续保持")
        elif score >= 0.6:
            feedback.append("👍 完成任务，还有提升空间")
            suggestions.append("尝试挑战更高难度的任务")
        else:
            feedback.append("💪 需要更多练习")
            suggestions.append("建议先完成入门级任务打好基础")

        return {{
            "score": round(min(1.0, score), 2),
            "feedback": feedback,
            "suggestions": suggestions,
            "metrics_checked": cls.SUCCESS_METRICS,
        }}

    @classmethod
    def get_dimension_weights(cls) -> Dict[str, float]:
        """返回五维权重用于 AbilityCalculator"""
        return ''' + self._to_class_name(sid) + '''Manifest.DIMENSION_WEIGHTS'''

    # ── 多 Agent 提示词 ──

    def _generate_prompt_templates(self, skill: SkillDefinition, sid: str) -> str:
        """生成多角色提示词模板"""
        name = skill.name
        desc = skill.description[:150]
        cat = skill.category
        tools = skill.tools

        return """\
class PromptTemplates:
    \"""""" + name + """ 多 Agent 提示词模板\"

    SKILL_NAME = \"""" + name + """\"
    SKILL_DESCRIPTION = \"""" + desc + """\"
    CATEGORY = \"""" + cat + """\"
    TOOLS = """ + repr(tools) + """

    @classmethod
    def architect_prompt(cls, task: str) -> str:
        return f\"\"\"你是一位经验丰富的架构师，专注于 {cls.SKILL_NAME}。

当前任务: {task}

请从架构角度提供：
1. 整体设计方案和架构图
2. 关键技术选型建议
3. 潜在风险和缓解措施
4. 扩展性考虑

涉及的技能: {cls.SKILL_DESCRIPTION}
推荐工具: """ + repr(", ".join(tools)) + """\"\"\".format(task=task)

    @classmethod
    def developer_prompt(cls, task: str) -> str:
        return f\"\"\"你是一位熟练的 {cls.SKILL_NAME} 开发者。

当前任务: {task}

请提供：
1. 分步实现方案
2. 关键代码示例
3. 注意事项和常见陷阱
4. 测试建议

推荐工具: """ + repr(", ".join(tools)) + """\"\"\".format(task=task)

    @classmethod
    def reviewer_prompt(cls, code: str) -> str:
        return f\"\"\"你是一位严格但公正的代码评审者，专精于 {cls.SKILL_NAME}。

请审查以下代码：
```
{code}
```

从以下维度评审：
1. 正确性: 逻辑是否无 bug
2. 可维护性: 代码是否清晰易读
3. 性能: 是否有明显性能问题
4. 安全性: 是否存在安全隐患
5. 最佳实践: 是否符合 {cls.SKILL_NAME} 社区规范\"\"\".format(code=code)

    @classmethod
    def coach_prompt(cls, level: str) -> str:
        return f\"\"\"你是一位耐心的 {cls.SKILL_NAME} 教练。

学习者当前水平: {level}

请提供：
1. 适合当前水平的练习建议
2. 需要重点关注的知识点
3. 推荐学习资源

技能描述: {cls.SKILL_DESCRIPTION}

保持鼓励和积极的语气，帮助学习者建立信心。\"\"\".format(level=level)

    @classmethod
    def get_all_prompts(cls):
        return {
            \"architect\": {
                \"role\": \"架构师\",
                \"description\": \"从系统设计角度提供建议\",
                \"template\": cls.architect_prompt(\"{task}\"),
            },
            \"developer\": {
                \"role\": \"开发者\",
                \"description\": \"从实现角度提供指导\",
                \"template\": cls.developer_prompt(\"{task}\"),
            },
            \"reviewer\": {
                \"role\": \"评审者\",
                \"description\": \"从代码审查角度提供反馈\",
                \"template\": cls.reviewer_prompt(\"{code}\"),
            },
            \"coach\": {
                \"role\": \"教练\",
                \"description\": \"从学习成长角度提供引导\",
                \"template\": cls.coach_prompt(\"{level}\"),
            },
        }"""

    # ── 记忆配置 ──

    def _generate_memory_config(self, skill: SkillDefinition, sid: str) -> str:
        """生成记忆索引配置"""
        tools_str = repr(skill.tools + [skill.category])
        # 转义 docstring 中的特殊字符
        safe_name = skill.name.replace("'", "\\'").replace("\\", "\\\\")
        return """\
class MemoryConfig:
    \"\"\"""" + safe_name + """ 记忆索引配置\"\"\"

    SKILL_ID = \"""" + sid + """\"

    KEYWORD_PATTERNS = """ + tools_str + """

    EXTRACTION_RULES = {
        \"code_snippets\": True,
        \"error_patterns\": True,
        \"design_decisions\": True,
        \"tool_usage\": True,
        \"learning_moments\": True,
    }

    PRIORITY_WEIGHTS = {
        \"error_fix\": 0.9,
        \"design_decision\": 0.7,
        \"code_snippet\": 0.5,
        \"exploration\": 0.3,
    }

    @classmethod
    def get_keywords(cls):
        return cls.KEYWORD_PATTERNS

    @classmethod
    def get_index_pattern(cls):
        return (
            \"当用户提到以下概念时，自动关联 \" + cls.SKILL_ID + \" 相关记忆：\\\\n\"
            \"- 关键词: \" + \", \".join(cls.KEYWORD_PATTERNS) + \"\\\\n\"
            \"- 工具: \" + \", \".join(""" + repr(skill.tools) + """)
        )"""

    # ── 主入口 ──

    def _generate_main_block(self, skill: SkillDefinition, sid: str) -> str:
        """生成注册和主入口"""
        class_name = self._to_class_name(sid)
        return '''\
# ============================================================
# 自动注册到 ZenSkill
# ============================================================

def register():
    return {
        "skill_id": __skill_id__,
        "skill_name": __skill_name__,
        "manifest_class": ''' + class_name + '''Manifest,
        "task_generator": TaskGenerator,
        "evaluator": SkillEvaluator,
        "prompts": PromptTemplates,
        "memory_config": MemoryConfig,
        "metadata": {
            "category": "''' + skill.category + '''",
            "difficulty": "''' + skill.difficulty + '''",
            "version": "0.1.0",
            "generated_by": "ZenSkill SkillCodeGenerator (9J)",
        },
    }


if __name__ == "__main__":
    reg = register()
    print("Skill ID:", reg["skill_id"])
    print("Skill Name:", reg["skill_name"])
    print("Category:", reg["metadata"]["category"])
    print("Tasks:", len(TaskGenerator.TASKS))
    print()

    task = TaskGenerator.get_daily_task()
    if task:
        print("Today:", task.get("description", ""))'''

    def _to_class_name(self, sid: str) -> str:
        """将 skill-id 转换为类名"""
        return "".join(
            word.capitalize() for word in sid.replace("-", " ").split()
        )


# ═══════════════════════════════════════════════════════════════════
# 9K: 技能迭代优化引擎
# ═══════════════════════════════════════════════════════════════════

class SkillOptimizer:
    """
    基于使用反馈自动优化技能定义

    优化维度：
    - 难度自适应：根据用户表现调整任务难度分布
    - 练习多样性：确保任务不重复
    - 权重重校准：根据实际使用数据调整五维权重
    """

    @staticmethod
    def analyze_feedback(feedback_log: List[Dict]) -> Dict[str, Any]:
        """
        分析用户反馈数据

        Args:
            feedback_log: [{"task_id", "score", "completed", "duration_min"}, ...]

        Returns:
            分析结果和建议
        """
        if not feedback_log:
            return {"suggestions": ["数据不足，继续使用中..."], "adjustment_needed": False}

        completed = sum(1 for f in feedback_log if f.get("completed"))
        avg_score = sum(f.get("score", 0) for f in feedback_log) / len(feedback_log)
        avg_duration = sum(f.get("duration_min", 0) for f in feedback_log) / len(feedback_log)
        completion_rate = completed / len(feedback_log)

        suggestions = []
        adjustment_needed = False

        # 太难了 → 降低难度
        if completion_rate < 0.5 and avg_score < 0.4:
            suggestions.append("任务完成率偏低，建议降低初始难度或增加引导")
            adjustment_needed = True

        # 太简单了 → 提升难度
        if completion_rate > 0.9 and avg_score > 0.85 and len(feedback_log) >= 5:
            suggestions.append("任务过于简单，建议增加高级挑战")
            adjustment_needed = True

        # 耗时过长
        if avg_duration > 60:
            suggestions.append(f"平均耗时 {avg_duration:.0f} 分钟，建议拆分复杂任务")

        return {
            "completion_rate": round(completion_rate, 2),
            "avg_score": round(avg_score, 2),
            "avg_duration_min": round(avg_duration, 0),
            "suggestions": suggestions,
            "adjustment_needed": adjustment_needed,
        }

    @staticmethod
    def suggest_difficulty_adjustment(
        skill: SkillDefinition, feedback_log: List[Dict]
    ) -> str:
        """建议难度调整方向"""
        analysis = SkillOptimizer.analyze_feedback(feedback_log)
        current = skill.difficulty

        if not analysis["adjustment_needed"]:
            return f"当前难度 {current} 适合，无需调整"

        if analysis["completion_rate"] < 0.5:
            difficulty_order = ["beginner", "intermediate", "advanced", "expert"]
            idx = difficulty_order.index(current) if current in difficulty_order else 0
            suggested = difficulty_order[max(0, idx - 1)]
            return f"建议从 {current} 降低到 {suggested}"
        else:
            difficulty_order = ["beginner", "intermediate", "advanced", "expert"]
            idx = difficulty_order.index(current) if current in difficulty_order else 1
            suggested = difficulty_order[min(len(difficulty_order) - 1, idx + 1)]
            return f"建议从 {current} 提升到 {suggested}"

    @staticmethod
    def recalibrate_weights(
        skill: SkillDefinition, usage_stats: Dict[str, float]
    ) -> Dict[str, float]:
        """
        根据实际使用数据重校准五维权重

        Args:
            skill: 当前技能定义
            usage_stats: {{"read_heavy", "edit_heavy", "error_spike", "feedback_high"}}

        Returns:
            调整后的权重字典
        """
        weights = {
            "proficiency_weight": skill.proficiency_weight,
            "stability_weight": skill.stability_weight,
            "satisfaction_weight": skill.satisfaction_weight,
            "responsiveness_weight": skill.responsiveness_weight,
            "memory_weight": skill.memory_weight,
        }

        # 错误率偏高 → 增加稳定性权重
        if usage_stats.get("error_spike"):
            weights["stability_weight"] = min(0.5, weights["stability_weight"] + 0.1)
            weights["proficiency_weight"] = max(0.1, weights["proficiency_weight"] - 0.05)

        # 反馈评分高 → 增加满意度权重
        if usage_stats.get("feedback_high"):
            weights["satisfaction_weight"] = min(0.4, weights["satisfaction_weight"] + 0.05)

        # 读取为主 → 增加记忆权重
        if usage_stats.get("read_heavy"):
            weights["memory_weight"] = min(0.4, weights["memory_weight"] + 0.1)
            weights["responsiveness_weight"] = max(0.1, weights["responsiveness_weight"] - 0.05)

        # 归一化
        total = sum(weights.values())
        return {k: round(v / total, 2) for k, v in weights.items()}


# ═══════════════════════════════════════════════════════════════════
# 8I: 预置技能模板库
# ═══════════════════════════════════════════════════════════════════

PREDEFINED_SKILL_TEMPLATES = {
    "python-dev": {
        "name": "Python Developer",
        "category": "coding",
        "description": "Python 应用开发技能，涵盖 Web 后端、数据处理、自动化脚本",
        "difficulty": "intermediate",
        "tags": ["python", "backend", "api"],
        "prerequisites": ["basic programming"],
        "proficiency_weight": 0.35, "stability_weight": 0.15,
        "satisfaction_weight": 0.15, "responsiveness_weight": 0.15, "memory_weight": 0.20,
        "practice_tasks": [
            {"level": "beginner", "description": "编写一个 Flask/FastAPI Hello World"},
            {"level": "beginner", "description": "实现 RESTful CRUD 接口"},
            {"level": "intermediate", "description": "添加数据库 ORM (SQLAlchemy/Peewee)"},
            {"level": "intermediate", "description": "编写单元测试 (pytest)"},
            {"level": "advanced", "description": "实现异步任务队列 (Celery/RQ)"},
            {"level": "advanced", "description": "容器化部署 (Docker)"},
        ],
    },
    "frontend-react": {
        "name": "React Frontend",
        "category": "coding",
        "description": "React 前端开发，组件化 UI、状态管理、性能优化",
        "difficulty": "intermediate",
        "tags": ["react", "javascript", "frontend"],
        "prerequisites": ["html", "css", "javascript basics"],
        "proficiency_weight": 0.30, "stability_weight": 0.10,
        "satisfaction_weight": 0.20, "responsiveness_weight": 0.25, "memory_weight": 0.15,
        "practice_tasks": [
            {"level": "beginner", "description": "创建函数式组件并传递 props"},
            {"level": "beginner", "description": "使用 useState/useEffect 管理状态"},
            {"level": "intermediate", "description": "实现 Context 或 Redux 状态管理"},
            {"level": "intermediate", "description": "编写组件测试 (React Testing Library)"},
            {"level": "advanced", "description": "性能优化 (memo/useMemo/lazy loading)"},
            {"level": "advanced", "description": "SSR 集成 (Next.js)"},
        ],
    },
    "devops-docker": {
        "name": "DevOps with Docker",
        "category": "devops",
        "description": "容器化运维：Docker 镜像构建、编排、CI/CD 管道",
        "difficulty": "intermediate",
        "tags": ["docker", "devops", "ci-cd"],
        "prerequisites": ["linux basics", "command line"],
        "proficiency_weight": 0.25, "stability_weight": 0.20,
        "satisfaction_weight": 0.15, "responsiveness_weight": 0.20, "memory_weight": 0.20,
        "practice_tasks": [
            {"level": "beginner", "description": "编写 Dockerfile 构建应用镜像"},
            {"level": "beginner", "description": "使用 docker-compose 编排多服务"},
            {"level": "intermediate", "description": "多阶段构建优化镜像大小"},
            {"level": "intermediate", "description": "配置 GitHub Actions CI 管道"},
            {"level": "advanced", "description": "Kubernetes 基础部署"},
            {"level": "advanced", "description": "监控和日志收集 (Prometheus/Grafana)"},
        ],
    },
    "data-science": {
        "name": "Data Science",
        "category": "analysis",
        "description": "数据科学：Pandas 数据处理、可视化、机器学习基础",
        "difficulty": "intermediate",
        "tags": ["python", "pandas", "ml"],
        "prerequisites": ["python basics", "statistics basics"],
        "proficiency_weight": 0.30, "stability_weight": 0.10,
        "satisfaction_weight": 0.15, "responsiveness_weight": 0.15, "memory_weight": 0.30,
        "practice_tasks": [
            {"level": "beginner", "description": "用 Pandas 加载并清洗一个 CSV 数据集"},
            {"level": "beginner", "description": "用 Matplotlib/Seaborn 创建 3 个图表"},
            {"level": "intermediate", "description": "特征工程：处理缺失值和标准化"},
            {"level": "intermediate", "description": "训练一个 Scikit-learn 分类模型"},
            {"level": "advanced", "description": "交叉验证和超参数调优"},
            {"level": "advanced", "description": "编写数据分析报告 (Jupyter Notebook)"},
        ],
    },
    "api-design": {
        "name": "API Design",
        "category": "coding",
        "description": "RESTful/GraphQL API 设计，包括认证、限流、文档",
        "difficulty": "intermediate",
        "tags": ["api", "rest", "backend"],
        "prerequisites": ["http basics", "json"],
        "proficiency_weight": 0.30, "stability_weight": 0.15,
        "satisfaction_weight": 0.20, "responsiveness_weight": 0.20, "memory_weight": 0.15,
        "practice_tasks": [
            {"level": "beginner", "description": "设计一个 RESTful 资源 URL 结构"},
            {"level": "beginner", "description": "实现 JWT 认证中间件"},
            {"level": "intermediate", "description": "添加请求限流 (rate limiting)"},
            {"level": "intermediate", "description": "编写 OpenAPI/Swagger 文档"},
            {"level": "advanced", "description": "实现 GraphQL schema 和 resolver"},
            {"level": "advanced", "description": "API 版本管理策略"},
        ],
    },
    "technical-writing": {
        "name": "Technical Writing",
        "category": "writing",
        "description": "技术文档写作：API 文档、架构设计文��、技术博客",
        "difficulty": "beginner",
        "tags": ["writing", "documentation", "communication"],
        "prerequisites": [],
        "proficiency_weight": 0.15, "stability_weight": 0.10,
        "satisfaction_weight": 0.35, "responsiveness_weight": 0.20, "memory_weight": 0.20,
        "practice_tasks": [
            {"level": "beginner", "description": "为一个函数/类编写 docstring"},
            {"level": "beginner", "description": "编写 README（项目说明+快速开始+API 参考）"},
            {"level": "intermediate", "description": "写一篇技术博客介绍最近解决的 bug"},
            {"level": "intermediate", "description": "绘制系统架构图（Mermaid/Excalidraw）"},
            {"level": "advanced", "description": "编写 ADR (Architecture Decision Record)"},
            {"level": "advanced", "description": "为开源项目贡献文档 PR"},
        ],
    },
    "llm-prompting": {
        "name": "LLM Prompt Engineering",
        "category": "learning",
        "description": "大语言模型提示工程：结构化 prompt、链式推理、工具调用",
        "difficulty": "beginner",
        "tags": ["llm", "ai", "prompting"],
        "prerequisites": [],
        "proficiency_weight": 0.20, "stability_weight": 0.10,
        "satisfaction_weight": 0.25, "responsiveness_weight": 0.25, "memory_weight": 0.20,
        "practice_tasks": [
            {"level": "beginner", "description": "写出一个清晰的 zero-shot prompt"},
            {"level": "beginner", "description": "使用 few-shot 示例改进输出质量"},
            {"level": "intermediate", "description": "设计一个 Chain-of-Thought prompt"},
            {"level": "intermediate", "description": "实现结构化输出 (JSON schema)"},
            {"level": "advanced", "description": "设计一个多步 Agent 工作流 prompt"},
            {"level": "advanced", "description": "评估并优化 prompt 的性能指标"},
        ],
    },
    "git-workflow": {
        "name": "Git Workflow",
        "category": "productivity",
        "description": "Git 版本控制：分支策略、代码审查、冲突解决",
        "difficulty": "intermediate",
        "tags": ["git", "version-control"],
        "prerequisites": ["command line basics"],
        "proficiency_weight": 0.25, "stability_weight": 0.20,
        "satisfaction_weight": 0.15, "responsiveness_weight": 0.15, "memory_weight": 0.25,
        "practice_tasks": [
            {"level": "beginner", "description": "创建 feature 分支并提交 3 个 commit"},
            {"level": "beginner", "description": "使用 git rebase -i 合并提交"},
            {"level": "intermediate", "description": "解决 merge conflict"},
            {"level": "intermediate", "description": "使用 git bisect 定位 bug 引入点"},
            {"level": "advanced", "description": "配置 Git hooks (pre-commit)"},
            {"level": "advanced", "description": "设计团队分支策略 (Git Flow/Trunk-based)"},
        ],
    },
}

# 类别汇总（供 CLI 显示）
SKILL_TEMPLATE_CATEGORIES = sorted(set(
    t["category"] for t in PREDEFINED_SKILL_TEMPLATES.values()
))

# 难度分布
SKILL_TEMPLATE_STATS = {
    "total": len(PREDEFINED_SKILL_TEMPLATES),
    "by_category": {
        cat: len([t for t in PREDEFINED_SKILL_TEMPLATES.values() if t["category"] == cat])
        for cat in SKILL_TEMPLATE_CATEGORIES
    },
    "by_difficulty": {
        diff: len([t for t in PREDEFINED_SKILL_TEMPLATES.values() if t["difficulty"] == diff])
        for diff in sorted(set(t["difficulty"] for t in PREDEFINED_SKILL_TEMPLATES.values()))
    },
}

