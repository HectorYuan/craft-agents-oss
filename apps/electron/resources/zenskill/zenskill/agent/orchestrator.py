"""
MU2-E/G: 能力路由与工作流编排引擎

将任务分解、角色代理、消息总线、协商、共享记忆
串联为完整的多 Agent 协作文工作流。

工作流原语：
- 顺序执行 → → →
- 并行执行 {并行}
- 分支选择 If → A Else B
- 汇聚集结 →
- 人工审批 需要用户确认
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from .protocol import (
    AgentRole, AgentMessage, MessageType, MessagePriority,
    MessageBus, TaskContract,
)
from .decomposer import TaskDecomposer, SubTask, DecompositionResult
from .negotiator import (
    NegotiationCoordinator, NegotiationSession,
    StructuredOpinion, VotingMethod,
)
from .shared_memory import SharedMemory

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class StepType(str, Enum):
    SEQUENTIAL = "sequential"      # 顺序执行
    PARALLEL = "parallel"          # 并行执行
    CONDITIONAL = "conditional"    # 分支选择
    NEGOTIATION = "negotiation"    # 协商
    APPROVAL = "approval"          # 人工审批
    SUB_WORKFLOW = "sub_workflow"  # 子工作流


@dataclass
class WorkflowStep:
    """工作流步骤"""
    id: str
    title: str
    step_type: StepType = StepType.SEQUENTIAL
    assigned_role: str = ""        # 指定角色处理
    subtask_id: str = ""           # 关联的子任务
    depends_on: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    status: WorkflowStatus = WorkflowStatus.PENDING
    result: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title,
            "type": self.step_type.value,
            "role": self.assigned_role,
            "depends_on": self.depends_on,
            "status": self.status.value,
        }


@dataclass
class WorkflowResult:
    """工作流执行结果"""
    workflow_id: str
    title: str
    status: WorkflowStatus
    steps: list[dict]
    outputs: dict
    duration_seconds: float
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "title": self.title,
            "status": self.status.value,
            "steps": self.steps,
            "duration": f"{self.duration_seconds:.1f}s",
            "errors": self.errors,
        }


@dataclass
class WorkflowDefinition:
    """工作流定义"""
    workflow_id: str
    title: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def add_step(self, title: str, step_type: StepType = StepType.SEQUENTIAL,
                 assigned_role: str = "", depends_on: Optional[list[str]] = None,
                 **kwargs) -> WorkflowStep:
        step = WorkflowStep(
            id=f"step_{uuid.uuid4().hex[:8]}",
            title=title,
            step_type=step_type,
            assigned_role=assigned_role,
            depends_on=depends_on or [],
            config=kwargs,
        )
        self.steps.append(step)
        return step


class WorkflowOrchestrator:
    """
    工作流编排引擎

    支持的工作流原语：
    - 顺序执行: step → step → step
    - 并行执行: {step, step, step}
    - 分支选择: If 条件 → A Else B
    - 协商: 多 Agent 协商决策
    - 人工审批: 关键节点等待确认
    """

    def __init__(self, bus: MessageBus,
                 decomposer: Optional[TaskDecomposer] = None,
                 negotiator: Optional[NegotiationCoordinator] = None,
                 shared_memory: Optional[SharedMemory] = None):
        self._bus = bus
        self._decomposer = decomposer or TaskDecomposer()
        self._negotiator = negotiator or NegotiationCoordinator(bus)
        self._memory = shared_memory or SharedMemory()
        self._workflows: dict[str, WorkflowDefinition] = {}
        self._results: dict[str, WorkflowResult] = {}

    # ── 工作流管理 ──

    def create_workflow(self, title: str, description: str = "") -> WorkflowDefinition:
        wf = WorkflowDefinition(
            workflow_id=f"wf_{uuid.uuid4().hex[:8]}",
            title=title,
            description=description,
        )
        self._workflows[wf.workflow_id] = wf
        return wf

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        return self._workflows.get(workflow_id)

    def get_result(self, workflow_id: str) -> Optional[WorkflowResult]:
        return self._results.get(workflow_id)

    def list_workflows(self, status: str = "") -> list[dict]:
        results = []
        for wf_id, wf in self._workflows.items():
            result = self._results.get(wf_id)
            results.append({
                "id": wf_id,
                "title": wf.title,
                "steps": len(wf.steps),
                "status": result.status.value if result else "pending",
            })
        if status:
            results = [r for r in results if r["status"] == status]
        return results

    # ── 自动编排（从任务开始） ──

    async def run_task(self, task_title: str, description: str = "",
                       required_skills: Optional[list[str]] = None) -> WorkflowResult:
        """
        从自然语言任务自动编排完整工作流

        流程：
        1. 任务分解 → 2. 查找 Agent → 3. 分配任务 → 4. 执行 → 5. 汇总
        """
        start_time = time.time()
        wf = self.create_workflow(task_title, description)

        # 1. 分解任务
        decomposition = self._decomposer.decompose(
            task_id=wf.workflow_id,
            task_title=task_title,
            description=description,
            required_skills=required_skills,
        )
        self._memory.update_task_context(
            wf.workflow_id, "decomposition", decomposition.to_dict()
        )

        # 2. 为每个子任务创建步骤
        for sub in decomposition.subtasks:
            # 查找可用 Agent
            agents = self._bus.find_agents_for_task(
                task_type=sub.required_skills[0] if sub.required_skills else "",
                domain="",
            )
            assigned_role = agents[0][1].role.value if agents else ""

            wf.add_step(
                title=sub.title,
                assigned_role=assigned_role,
                subtask_id=sub.id,
                depends_on=sub.depends_on,
                description=sub.description,
                criteria=sub.acceptance_criteria,
            )

        # 3. 执行工作流
        result = await self._execute_workflow(wf)
        self._results[wf.workflow_id] = result
        return result

    async def from_decomposition(self, decomposition: DecompositionResult) -> WorkflowResult:
        """从分解结果创建工作流并执行"""
        wf = self.create_workflow(decomposition.task_title)
        for sub in decomposition.subtasks:
            agents = self._bus.find_agents_for_task(
                task_type=sub.required_skills[0] if sub.required_skills else "",
            )
            assigned_role = agents[0][1].role.value if agents else ""
            wf.add_step(title=sub.title, assigned_role=assigned_role,
                        subtask_id=sub.id, depends_on=sub.depends_on)
        result = await self._execute_workflow(wf)
        self._results[wf.workflow_id] = result
        return result

    # ── 工作流执行引擎 ──

    async def _execute_workflow(self, wf: WorkflowDefinition) -> WorkflowResult:
        """执行工作流（核心引擎）"""
        start_time = time.time()
        errors: list[str] = []
        step_results: dict[str, Any] = {}
        outputs: dict[str, Any] = {}
        all_steps_completed = True

        # 按依赖拓扑排序
        ready = [s for s in wf.steps if not s.depends_on]
        blocked = [s for s in wf.steps if s.depends_on]
        completed: set[str] = set()

        while ready:
            # 并行执行就绪步骤
            batch_tasks = []
            for step in ready:
                step.status = WorkflowStatus.RUNNING
                batch_tasks.append(self._execute_step(step, wf, step_results))

            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            for step, result in zip(ready, batch_results):
                if isinstance(result, Exception):
                    step.status = WorkflowStatus.FAILED
                    errors.append(f"[{step.title}] {str(result)}")
                    all_steps_completed = False
                else:
                    step.status = WorkflowStatus.COMPLETED
                    step.result = result
                    step_results[step.id] = result
                    outputs[step.title] = result
                completed.add(step.id)

            # 更新就绪列表
            ready = []
            still_blocked = []
            for s in blocked:
                deps_complete = all(d in completed for d in s.depends_on)
                if deps_complete:
                    ready.append(s)
                else:
                    still_blocked.append(s)
            blocked = still_blocked

        # 检查是否有未完成的步骤
        if blocked:
            errors.append(f"阻塞步骤: {[s.title for s in blocked]}")
            all_steps_completed = False

        duration = time.time() - start_time

        status = WorkflowStatus.COMPLETED if all_steps_completed else WorkflowStatus.FAILED

        result = WorkflowResult(
            workflow_id=wf.workflow_id,
            title=wf.title,
            status=status,
            steps=[s.to_dict() for s in wf.steps],
            outputs=outputs,
            duration_seconds=duration,
            errors=errors,
        )

        # 记录到共享记忆
        self._memory.store(
            content=f"工作流完成: {wf.title}, {status.value}, {duration:.1f}s",
            source="orchestrator",
            entry_type="collaboration",
            task_id=wf.workflow_id,
            importance=0.8,
        )

        return result

    async def _execute_step(self, step: WorkflowStep, wf: WorkflowDefinition,
                            context: dict) -> Optional[dict]:
        """执行单个步骤"""
        logger.info(f"⚡ 步骤: {step.title} ({step.step_type.value})")

        if step.step_type == StepType.PARALLEL:
            return await self._run_parallel(step, wf, context)
        elif step.step_type == StepType.CONDITIONAL:
            return self._run_conditional(step, context)
        elif step.step_type == StepType.NEGOTIATION:
            return await self._run_negotiation_step(step)
        elif step.step_type == StepType.APPROVAL:
            return self._run_approval(step)
        else:
            return await self._run_sequential(step)

    async def _run_sequential(self, step: WorkflowStep) -> Optional[dict]:
        """顺序步骤：分配给合适的 Agent 执行"""
        if not step.assigned_role:
            return {"status": "skipped", "reason": "no_role_assigned"}

        # 查找该角色的 Agent
        agents = self._bus.find_agents_for_task(step.assigned_role)
        if not agents:
            return {"status": "skipped", "reason": f"no_agent_for_{step.assigned_role}"}

        target = agents[0][0]

        # 发送任务
        msg = AgentMessage.new(
            sender="orchestrator",
            msg_type=MessageType.TASK_ASSIGNMENT,
            receiver=target,
            payload={
                "task": {
                    "task_id": step.id,
                    "title": step.title,
                    "config": step.config,
                }
            },
        )

        # 等待接受
        accept = await self._bus.send_and_wait(msg, timeout=30.0)
        if accept and accept.msg_type == MessageType.TASK_ACCEPTANCE:
            # 记录协作
            self._memory.record_collaboration("orchestrator", target)
            self._memory.store(
                content=f"任务已分配: {step.title} → {target}",
                source="orchestrator",
                entry_type="collaboration",
                task_id=step.subtask_id or "",
                importance=0.6,
            )
            return {"assigned_to": target, "status": "accepted"}
        else:
            return {"status": "rejected", "agent": target}

    async def _run_parallel(self, step: WorkflowStep, wf: WorkflowDefinition,
                            context: dict) -> dict:
        """并行步骤：同时执行多个子步骤"""
        sub_steps = step.config.get("sub_steps", [])
        if not sub_steps:
            return {"status": "no_sub_steps"}

        tasks = []
        for sub in sub_steps:
            sub_step = WorkflowStep(
                id=f"{step.id}_{sub.get('id', 'sub')}",
                title=sub.get("title", ""),
                assigned_role=sub.get("role", ""),
                config=sub,
            )
            tasks.append(self._run_sequential(sub_step))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {"parallel_results": [str(r)[:100] for r in results]}

    def _run_conditional(self, step: WorkflowStep, context: dict) -> dict:
        """条件步骤：根据条件选择分支"""
        condition = step.config.get("condition", "")
        branches = step.config.get("branches", {})

        # 简单条件匹配
        if condition in context:
            chosen = branches.get("true", branches.get("default", "unknown"))
        else:
            chosen = branches.get("false", branches.get("default", "unknown"))

        return {"condition": condition, "chosen_branch": chosen}

    async def _run_negotiation_step(self, step: WorkflowStep) -> dict:
        """协商步骤：多 Agent 协商决策"""
        topic = step.config.get("topic", step.title)
        session = self._negotiator.start_negotiation(topic)

        # 自动提交各角色提案
        for role_info in step.config.get("participants", []):
            session.submit_proposal(StructuredOpinion(
                agent_id=role_info.get("agent", role_info.get("role", "unknown")),
                role=AgentRole(role_info.get("role", "developer")),
                conclusion=role_info.get("conclusion", ""),
                confidence=role_info.get("confidence", 0.5),
                domain=role_info.get("domain", ""),
            ))

        if len(session.proposals) >= 2:
            result = await session.run_negotiation()
            return {
                "consensus": result.consensus_reached,
                "decision": result.final_decision,
                "winner": result.winning_proposal,
                "summary": result.summary,
            }
        return {"status": "insufficient_proposals"}

    def _run_approval(self, step: WorkflowStep) -> dict:
        """审批步骤：标记需要人工确认"""
        return {
            "status": "awaiting_approval",
            "message": step.config.get("message", "需要人工确认"),
            "step_id": step.id,
        }

    # ── 标准工作流模板 ──

    def create_code_review_workflow(self, feature_name: str) -> WorkflowDefinition:
        """创建代码审查标准工作流"""
        wf = self.create_workflow(
            f"代码审查: {feature_name}",
            f"对 {feature_name} 进行完整代码审查",
        )
        wf.add_step(f"开发者实现 {feature_name}", assigned_role="developer")
        wf.add_step("测试覆盖检查", step_type=StepType.PARALLEL,
                     assigned_role="tester",
                     depends_on=[wf.steps[-1].id])
        wf.add_step("代码质量评审", step_type=StepType.PARALLEL,
                     assigned_role="critic",
                     depends_on=[wf.steps[-2].id])
        wf.add_step("安全审查", step_type=StepType.PARALLEL,
                     assigned_role="architect",
                     depends_on=[wf.steps[-3].id])
        wf.add_step("汇总审查意见", assigned_role="coordinator",
                     depends_on=[wf.steps[-1].id, wf.steps[-2].id, wf.steps[-3].id])
        wf.add_step("最终审批", step_type=StepType.APPROVAL,
                     depends_on=[wf.steps[-1].id],
                     message=f"请确认 {feature_name} 的审查结果")
        return wf

    def create_negotiation_workflow(self, topic: str,
                                     participants: list[dict]) -> WorkflowDefinition:
        """创建协商标准工作流"""
        wf = self.create_workflow(f"协商: {topic}", topic)
        wf.add_step(f"关于 {topic} 的协商", step_type=StepType.NEGOTIATION,
                     participants=participants, topic=topic)
        wf.add_step("执行协商结果", assigned_role="developer",
                     depends_on=[wf.steps[-1].id])
        return wf
