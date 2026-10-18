"""MultiAgentExecuteTool — MU2 多 Agent 协作栈激活桥（编排执行层）。

把两套半成品拼成完整能力：
- MU2 编排栈（agent/）：TaskDecomposer 分解 + 7 角色视角（协议/协商/共享
  记忆保留在栈内待后续版本接入）
- 执行半边：DelegateTool 隔离子 agent（同 core 工具、新上下文、交回终答）

执行模型：分解 → 角色匹配 → 依赖序逐个委派子 agent（角色视角注入系统
提示）→ 按依赖序聚合。negotiator 协商 v1 不接入（无冲突检测点），文档标注。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .agent_loop import AgentLoop, AgentLoopConfig
from .delegate_tool import DelegateTool
from .tools import DEFAULT_SYSTEM_PROMPT, create_default_tools
from .types import AgentTool, AgentToolResult, Context, TextContent, UserMessage

logger = logging.getLogger(__name__)

# 子任务技能关键词 → MU2 角色（capability_audit：MU2-C 七角色）
_ROLE_KEYWORDS = {
    "architect": ("design", "architecture", "架构", "选型", "设计"),
    "tester": ("test", "qa", "测试", "验证", "边界"),
    "writer": ("document", "doc", "文档", "写作", "说明"),
    "analyst": ("analyz", "data", "分析", "诊断", "数据"),
    "critic": ("review", "critic", "审查", "评审", "批判"),
}


def _match_role(sub) -> str:
    """按子任务技能标签/标题关键词匹配 MU2 角色（默认 developer）。"""
    blob = " ".join(sub.required_skills or []) + " " + (sub.title or "")
    blob = blob.lower()
    for role, keywords in _ROLE_KEYWORDS.items():
        if any(k in blob for k in keywords):
            return role
    return "developer"


_ROLE_PROMPT_PREFIX = {
    "architect": ("You are the ARCHITECT role in a multi-agent team. "
                  "Focus on system design, technology selection and "
                  "structural decisions."),
    "developer": ("You are the DEVELOPER role in a multi-agent team. "
                  "Focus on implementation, refactoring and debugging."),
    "tester": ("You are the TESTER role in a multi-agent team. "
               "Focus on quality assurance, edge cases and test strategy."),
    "writer": ("You are the WRITER role in a multi-agent team. "
               "Focus on documentation quality and clarity."),
    "analyst": ("You are the ANALYST role in a multi-agent team. "
                "Focus on data analysis, diagnosis and decision support."),
    "critic": ("You are the CRITIC role in a multi-agent team. "
               "Focus on critical review and identifying potential problems."),
}


class MultiAgentExecuteTool(AgentTool):
    """把复杂任务分解为子任务树，按 MU2 角色视角以隔离子 agent 依赖序执行。"""

    name = "multi_agent_execute"
    description = (
        "Execute a COMPLEX task via multi-agent orchestration: the task is "
        "decomposed into a dependency-ordered subtask tree, each subtask is "
        "run by an isolated sub-agent with a specialized role perspective "
        "(architect/developer/tester/writer/analyst/critic), and results are "
        "aggregated in dependency order. Use for genuinely multi-part tasks; "
        "do NOT use for simple single-step actions."
    )
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The complex task description (self-contained).",
            },
            "max_subtasks": {
                "type": "integer",
                "description": "Decomposition cap (default 6).",
            },
        },
        "required": ["task"],
    }

    def __init__(
        self,
        stream_fn,
        model,
        cwd: str = ".",
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_subtasks: int = 6,
        sub_max_steps: int = 6,
    ) -> None:
        self._stream_fn = stream_fn
        self._model = model
        self._cwd = cwd
        self._system_prompt = system_prompt
        self._max_subtasks = max_subtasks
        self._sub_max_steps = sub_max_steps

    # ── 工具入口 ────────────────────────────────────────────────

    async def run(self, tool_call_id: str, params: Dict[str, Any],
                  on_update=None) -> AgentToolResult:
        task = (params.get("task") or "").strip()
        if not task:
            return AgentToolResult(
                content=[TextContent("multi_agent_execute requires 'task'.")],
                is_error=True,
            )
        try:
            decomposition = self._decompose(task)
        except Exception as e:
            return AgentToolResult(
                content=[TextContent(f"任务分解失败: {e}")], is_error=True)

        subtasks = self._topological_order(decomposition.subtasks)
        if not subtasks:
            return AgentToolResult(
                content=[TextContent("任务分解结果为空，请直接执行原任务。")],
                is_error=True)

        done: Dict[str, str] = {}
        report: List[Dict[str, str]] = []
        for sub in subtasks[: self._max_subtasks]:
            role = _match_role(sub)
            subtask_text = self._compose_subtask_text(sub, done)
            try:
                summary = await self._run_subtask(
                    role, subtask_text, tool_call_id, on_update)
            except Exception as e:
                # 单子任务失败聚合进报告，不炸整体编排
                summary = f"子任务执行异常: {e}"
            done[sub.id] = summary
            report.append(
                {"role": role, "title": sub.title, "summary": summary})

        return AgentToolResult(
            content=[TextContent(self._aggregate(task, report))])

    # ── 内部 ────────────────────────────────────────────────────

    def _decompose(self, task: str):
        from ...agent.decomposer import TaskDecomposer

        return TaskDecomposer().decompose(
            task_id="multi-agent-execute",
            task_title=task[:80],
            description=task,
            max_subtasks=self._max_subtasks,
        )

    @staticmethod
    def _topological_order(subtasks) -> list:
        """按 depends_on 做稳定拓扑排序（环/缺失依赖按原序追加）。"""
        by_id = {s.id: s for s in subtasks}
        ordered, seen = [], set()

        def visit(s, chain):
            if s.id in seen or s.id in chain:
                return
            chain.add(s.id)
            for dep in s.depends_on or []:
                if dep in by_id:
                    visit(by_id[dep], chain)
            seen.add(s.id)
            ordered.append(s)

        for s in subtasks:
            visit(s, set())
        return ordered

    @staticmethod
    def _compose_subtask_text(sub, done: Dict[str, str]) -> str:
        parts = [f"子任务: {sub.title}"]
        if sub.description:
            parts.append(sub.description)
        if sub.acceptance_criteria:
            parts.append("验收标准: " + "; ".join(sub.acceptance_criteria))
        deps = [done[d] for d in (sub.depends_on or []) if d in done]
        if deps:
            parts.append("前序子任务结论:\n- " + "\n- ".join(deps))
        return "\n".join(parts)

    async def _run_subtask(self, role: str, subtask_text: str,
                           tool_call_id: str, on_update=None) -> str:
        prefix = _ROLE_PROMPT_PREFIX.get(role, _ROLE_PROMPT_PREFIX["developer"])
        system_prompt = f"{prefix}\n\n{self._system_prompt}"
        delegate = DelegateTool(
            self._stream_fn, self._model, cwd=self._cwd,
            system_prompt=system_prompt, max_depth=1,
            default_max_steps=self._sub_max_steps,
        )
        try:
            result = await delegate.run(
                tool_call_id + "-ma", {"task": subtask_text}, on_update)
        except Exception as e:
            return f"子任务执行异常: {e}"
        text = "\n".join(
            getattr(c, "text", str(c)) for c in result.content)
        if getattr(result, "is_error", False):
            return f"子任务失败: {text}"
        return text

    @staticmethod
    def _aggregate(task: str, report: List[Dict[str, str]]) -> str:
        lines = [f"# 多 Agent 协作执行报告\n\n任务: {task}\n"]
        for i, r in enumerate(report, 1):
            lines.append(f"## {i}. [{r['role']}] {r['title']}\n{r['summary']}\n")
        return "\n".join(lines)
