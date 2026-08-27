"""
ZenSkill — LLM 个性化任务生成器 (7G)

基于活跃目标 + 用户画像 → DeepSeek 生成定制练习任务
失败时降级到 TaskRecommendationEngine 模板推荐
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from zenskill.core.paths import get_user_data_dir


class TaskGenerator:
    """LLM 驱动的个性化任务生成器"""

    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id
        self._cache_dir = get_user_data_dir() / "tasks"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = self._cache_dir / "generated_tasks.json"

    def generate_for_goal(self, goal, user_context: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """为单个活跃目标生成 3 个定制任务

        Args:
            goal: GrowthGoal 对象
            user_context: 可选的用户上下文（工具偏好、项目等）

        Returns:
            任务 dict 列表 [{title, description, difficulty, ...}]
        """
        # 尝试 LLM 生成
        try:
            tasks = self._generate_with_llm(goal, user_context)
            if tasks:
                self._cache(goal.goal_id, tasks)
                return tasks
        except Exception:
            pass

        # 降级: 模板匹配
        return self._generate_from_templates(goal)

    def generate_for_goals(self, goals: List, user_context: Optional[Dict] = None) -> Dict[str, List[Dict]]:
        """为多个目标批量生成任务

        Returns:
            {goal_id: [tasks]}
        """
        results = {}
        for goal in goals:
            try:
                results[goal.goal_id] = self.generate_for_goal(goal, user_context)
            except Exception:
                results[goal.goal_id] = []
        return results

    def get_cached_tasks(self, goal_id: str) -> List[Dict]:
        """读取缓存的任务"""
        if self._cache_file.exists():
            try:
                cache = json.loads(self._cache_file.read_text())
                return cache.get(goal_id, [])
            except Exception:
                pass
        return []

    # ═══════════════════════════════════════════════════════════════
    # Internal
    # ═══════════════════════════════════════════════════════════════

    def _generate_with_llm(self, goal, user_context: Optional[Dict]) -> List[Dict[str, Any]]:
        """使用 DeepSeek 生成个性化任务"""
        import asyncio
        from zenskill.core.llm_provider import get_llm_provider, ChatMessage

        provider = get_llm_provider()

        dim_name_map = {
            "proficiency": "熟练度", "stability": "稳定性",
            "satisfaction": "满意度", "responsiveness": "响应力",
            "memory": "记忆力", "composite": "综合能力",
        }
        dim_name = dim_name_map.get(goal.dimension, goal.dimension)

        ctx_str = ""
        if user_context:
            tools = user_context.get("top_tools", [])
            if tools:
                ctx_str += f"\n常用工具: {', '.join(tools[:5])}"
            projects = user_context.get("projects", [])
            if projects:
                ctx_str += f"\n活跃项目: {', '.join(projects[:3])}"

        prompt = f"""你是 ZenSkill 的个性化任务教练。根据以下用户信息，生成 3 个具体的练习任务。

## 目标
- 维度: {dim_name} ({goal.dimension})
- 当前分数: {goal.current_score}
- 目标分数: {goal.target_score}
- 推荐策略: {goal.strategy}{ctx_str}

## 要求
- 每个任务必须具体、可执行、有明确的完成标准
- 难度应与当前分数匹配（分数越低越简单）
- 任务应可直接在 Claude Code 环境中完成
- 输出严格的 JSON 数组格式

输出格式:
```json
[
  {{"title": "...", "description": "...", "difficulty": "easy|medium|hard", "estimated_minutes": 15, "target_dimensions": ["{goal.dimension}"]}},
  ...
]
```"""

        messages = [
            ChatMessage(role="system", content="你是 ZenSkill 个性化任务教练。只输出 JSON，不要有其他文字。"),
            ChatMessage(role="user", content=prompt),
        ]

        try:
            response = asyncio.run(provider.simple_chat(messages, temperature=0.7, max_tokens=1500))
            content = response.get("content", "")
            tasks = self._parse_json_response(content)
            if tasks and len(tasks) >= 1:
                return tasks[:3]
        except Exception:
            pass

        return []

    def _parse_json_response(self, content: str) -> List[Dict]:
        """从 LLM 回复中提取 JSON"""
        # 尝试多种解析策略
        strategies = [
            lambda c: json.loads(c),
            lambda c: json.loads(c.split("```json")[1].split("```")[0] if "```json" in c else "[]"),
            lambda c: json.loads(c.split("```")[1].split("```")[0] if "```" in c else "[]"),
            lambda c: json.loads("[" + c.split("[", 1)[1].rsplit("]", 1)[0] + "]" if "[" in c and "]" in c else "[]"),
        ]
        for strategy in strategies:
            try:
                result = strategy(content)
                if isinstance(result, list):
                    return result
                if isinstance(result, dict):
                    return [result]
            except Exception:
                continue
        return []

    def _generate_from_templates(self, goal) -> List[Dict[str, Any]]:
        """模板降级: 为特定维度生成任务"""
        from zenskill.systems.active.task_recommender import TASK_TEMPLATES

        # 筛选匹配该维度的模板
        matching = [t for t in TASK_TEMPLATES
                    if goal.dimension in t.get("target_dimensions", [])]
        if not matching:
            matching = TASK_TEMPLATES[:3]

        tasks = []
        for t in matching[:3]:
            tasks.append({
                "title": t["title"],
                "description": t["description"],
                "difficulty": t["difficulty"],
                "estimated_minutes": t["estimated_interactions"] * 3,
                "target_dimensions": t["target_dimensions"],
                "expected_gain": t["expected_gain"],
                "source": "template",
            })
        return tasks

    def _cache(self, goal_id: str, tasks: List[Dict]) -> None:
        """缓存生成结果"""
        cache = {}
        if self._cache_file.exists():
            try:
                cache = json.loads(self._cache_file.read_text())
            except Exception:
                pass
        cache[goal_id] = tasks
        # 只保留最近 10 个 goal 的缓存
        keys = list(cache.keys())
        if len(keys) > 10:
            for old_key in keys[:-10]:
                del cache[old_key]
        self._cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=2))

    def to_spawn_format(self, task: Dict, goal_context: Optional[Dict] = None) -> str:
        """使用 SpawnHelper 格式输出任务描述 (兼容 sessions_spawn)

        Args:
            task: 任务 dict (来自 generate_for_goal)
            goal_context: 可选的目标上下文

        Returns:
            sessions_spawn 兼容的任务描述字符串
        """
        try:
            from zenthink.templates.spawn_helper import SpawnHelper  # type: ignore
            helper = SpawnHelper()
            dim = goal_context.get("dimension", "") if goal_context else ""
            bg = f"ZenSkill 个性化练习: {task.get('title', '任务')}"
            obj = task.get("description", "完成此练习以提升技能水平")
            reqs = [f"维度: {dim}",
                    f"难度: {task.get('difficulty', 'medium')}",
                    f"预计: {task.get('estimated_minutes', 15)} 分钟"]
            return helper.create_task(
                background=bg,
                objective=obj,
                requirements=reqs,
            )
        except ImportError:
            # Fallback: 简易 Markdown 格式
            return f"""## {task.get('title', 'Task')}
- 描述: {task.get('description', '')}
- 难度: {task.get('difficulty', '?')}
- 预计: {task.get('estimated_minutes', '?')} 分钟
- 维度: {', '.join(task.get('target_dimensions', []))}
"""
