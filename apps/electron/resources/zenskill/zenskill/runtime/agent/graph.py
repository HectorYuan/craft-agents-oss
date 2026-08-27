"""任务分解 + DAG 执行（E5 Graph 工程）。

PlannerAgent：用 LLM 将复杂任务分解为子任务 DAG（依赖拓扑排序 + 并行执行）。
AgentGraph：DAG 执行器——无依赖子任务并行，有依赖串行，结果聚合。

子任务格式：
    SubTask(id, description, dependencies[], tools_hint[], result)

用法：
    graph = AgentGraph(stream_fn, model, tools_factory)
    plan = await graph.plan("给 stats.py 写测试并修复发现的 bug")
    results = await graph.execute(plan)
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .agent_loop import AgentLoop, AgentLoopConfig
from .types import (
    AgentTool,
    AssistantMessage,
    Context,
    Message,
    StopReason,
    TextContent,
    UserMessage,
    message_to_dict,
)


@dataclass
class SubTask:
    id: str
    description: str
    dependencies: List[str] = field(default_factory=list)
    tools_hint: List[str] = field(default_factory=list)
    result: Optional[str] = None
    status: str = "pending"  # pending / running / done / failed


@dataclass
class ExecutionPlan:
    task: str
    subtasks: List[SubTask]
    raw_plan: str = ""

    def topo_sort(self) -> List[List[SubTask]]:
        """拓扑排序：返回可并行执行的层级列表"""
        by_id = {s.id: s for s in self.subtasks}
        in_degree = {s.id: len(s.dependencies) for s in self.subtasks}
        levels: List[List[SubTask]] = []
        remaining = set(by_id.keys())

        while remaining:
            # 当前层：入度为 0 的节点
            level = [by_id[sid] for sid in remaining if in_degree[sid] == 0]
            if not level:
                # 环依赖——退化为串行
                level = [by_id[next(iter(remaining))]]
            levels.append(level)
            for s in level:
                remaining.discard(s.id)
                for dep in by_id:
                    if s.id in by_id[dep].dependencies:
                        in_degree[dep] -= 1
        return levels

    def summary(self) -> str:
        lines = [f"Plan for: {self.task}", f"Subtasks ({len(self.subtasks)}):"]
        for s in self.subtasks:
            deps = f" (depends on: {', '.join(s.dependencies)})" if s.dependencies else ""
            lines.append(f"  [{s.id}] {s.description}{deps}")
        return "\n".join(lines)


PLANNER_PROMPT = """You are a task planner. Given a complex task, decompose it into smaller subtasks that can be executed independently or in sequence.

Output a JSON array of subtasks. Each subtask has:
- "id": short identifier (e.g., "t1", "t2")
- "description": what to do
- "dependencies": list of subtask ids that must complete first (empty if independent)
- "tools_hint": tools likely needed (e.g., ["read", "edit", "bash"])

Rules:
- Each subtask should be self-contained and completable in 1-3 tool calls
- Independent subtasks can run in parallel
- Keep it simple: 2-5 subtasks for most tasks
- Output ONLY the JSON array, no other text

Example:
Task: "Fix the bug in add() and write tests for it"
[
  {"id": "t1", "description": "Read the code and locate the bug in the add function", "dependencies": [], "tools_hint": ["read", "grep"]},
  {"id": "t2", "description": "Fix the bug in the add function", "dependencies": ["t1"], "tools_hint": ["edit"]},
  {"id": "t3", "description": "Write tests for the add function", "dependencies": ["t1"], "tools_hint": ["write", "bash"]},
  {"id": "t4", "description": "Run all tests and verify everything passes", "dependencies": ["t2", "t3"], "tools_hint": ["bash"]}
]
"""


class PlannerAgent:
    """用 LLM 将复杂任务分解为子任务 DAG"""

    def __init__(self, stream_fn, model) -> None:
        self._stream = stream_fn
        self._model = model

    async def plan(self, task: str) -> ExecutionPlan:
        context = Context(
            messages=[
                UserMessage(content=PLANNER_PROMPT),
                UserMessage(content=f"Task: {task}"),
            ],
        )
        config = AgentLoopConfig(stream=self._stream, model=self._model, max_steps=1)
        loop = AgentLoop(config)
        final_text = ""
        async for ev in loop.run(context):
            if type(ev).__name__ == "MessageEnd" and isinstance(ev.message, AssistantMessage):
                final_text = ev.message.text()

        # 解析 JSON
        subtasks = self._parse_plan(final_text)
        return ExecutionPlan(task=task, subtasks=subtasks, raw_plan=final_text)

    def _parse_plan(self, text: str) -> List[SubTask]:
        # 提取 JSON 数组
        start = text.find("[")
        end = text.rfind("]") + 1
        if start < 0 or end <= start:
            return [SubTask(id="t1", description=text.strip())]
        try:
            raw = json.loads(text[start:end])
        except json.JSONDecodeError:
            return [SubTask(id="t1", description=text.strip())]

        subtasks = []
        for item in raw:
            subtasks.append(SubTask(
                id=item.get("id", f"t{len(subtasks)+1}"),
                description=item.get("description", ""),
                dependencies=item.get("dependencies", []),
                tools_hint=item.get("tools_hint", []),
            ))
        return subtasks


class AgentGraph:
    """DAG 执行器——无依赖子任务并行，有依赖串行"""

    def __init__(self, stream_fn, model, tools_factory: Callable[[], List[AgentTool]],
                 system_prompt: str = "") -> None:
        self._stream = stream_fn
        self._model = model
        self._tools_factory = tools_factory
        self._system_prompt = system_prompt

    async def execute(self, plan: ExecutionPlan) -> Dict[str, str]:
        """执行计划，返回 {subtask_id: result_text}"""
        results: Dict[str, str] = {}
        levels = plan.topo_sort()

        for level in levels:
            if len(level) == 1:
                # 单任务——串行
                s = level[0]
                s.status = "running"
                s.result = await self._run_subtask(s, plan.task, results)
                s.status = "done" if s.result is not None else "failed"
                results[s.id] = s.result or ""
            else:
                # 多任务——并行
                async def _run_one(st: SubTask):
                    st.status = "running"
                    st.result = await self._run_subtask(st, plan.task, results)
                    st.status = "done" if st.result is not None else "failed"
                    results[st.id] = st.result or ""

                await asyncio.gather(*[_run_one(s) for s in level])

        return results

    async def _run_subtask(self, subtask: SubTask, main_task: str,
                           prev_results: Dict[str, str]) -> Optional[str]:
        """执行单个子任务"""
        # 构建上下文：主任务 + 依赖结果 + 子任务描述
        dep_context = ""
        if subtask.dependencies:
            dep_lines = []
            for dep_id in subtask.dependencies:
                if dep_id in prev_results:
                    dep_lines.append(f"[{dep_id}] {prev_results[dep_id][:500]}")
            if dep_lines:
                dep_context = "\n\nResults from dependent subtasks:\n" + "\n".join(dep_lines)

        user_msg = (
            f"Main task: {main_task}\n"
            f"Your subtask [{subtask.id}]: {subtask.description}{dep_context}\n\n"
            f"Complete this subtask. Use tools as needed. "
            f"When done, give a brief summary of what you did."
        )

        context = Context(
            messages=[UserMessage(content=user_msg)],
            system_prompt=self._system_prompt,
            tools=self._tools_factory(),
        )
        config = AgentLoopConfig(stream=self._stream, model=self._model, max_steps=8)
        loop = AgentLoop(config)
        final_text = ""
        async for ev in loop.run(context):
            if type(ev).__name__ == "MessageEnd" and isinstance(ev.message, AssistantMessage):
                final_text = ev.message.text()
        return final_text or None
