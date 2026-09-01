"""链式执行器"""


from __future__ import annotations

import time
from typing import Any, Callable, Optional

from ..memory import ContextManager
from .skill_chain import SkillChain, ChainStep, StepStatus
from .chain_result import ChainResult, StepResult

__stable_api__ = "1.0"  # ChainExecutor 公开方法（execute/构建） 为外部消费方稳定面（docs/agentswarm_integration_plan.md I2）


class ChainExecutor:
    """链式执行器

    执行技能链，处理依赖关系、中间结果传递和失败回滚。

    使用方式：
        executor = ChainExecutor(executor, context_manager)
        result = await executor.execute(chain)
        if result.success:
            print("链执行成功")
        else:
            print(f"链执行失败: {result.error}")
    """

    def __init__(
        self,
        executor,
        context_manager: ContextManager | None = None,
        on_step_complete: Callable[[str, StepResult], None] | None = None,
        on_step_fail: Callable[[str, StepResult], None] | None = None,
    ):
        """初始化链式执行器

        Args:
            executor: 工具执行器（duck-typed，需提供 async execute(tool_name, args)）
            context_manager: 上下文管理器
            on_step_complete: 步骤完成回调
            on_step_fail: 步骤失败回调
        """
        self._executor = executor
        self._context_manager = context_manager
        self._on_step_complete = on_step_complete
        self._on_step_fail = on_step_fail

    async def execute(self, chain: SkillChain) -> ChainResult:
        """执行技能链

        Args:
            chain: 技能链定义

        Returns:
            链执行结果
        """
        start_time = time.time()
        result = ChainResult(chain_id=chain.chain_id)

        # 验证链
        errors = chain.validate()
        if errors:
            result.error = f"Chain validation failed: {'; '.join(errors)}"
            result.end_time = time.time()
            result.total_duration_seconds = result.end_time - start_time
            return result

        # 初始化所有步骤结果
        for step_id in chain.steps:
            result.step_results[step_id] = StepResult(step_id=step_id)

        # 按拓扑顺序执行
        completed_steps = set()

        for step_id in chain.execution_order:
            step = chain.get_step(step_id)
            if not step:
                continue

            # 检查依赖是否完成
            deps_met = all(dep in completed_steps for dep in step.depends_on)
            if not deps_met:
                result.step_results[step_id].status = StepStatus.SKIPPED
                result.step_results[step_id].error = "Dependencies not met"
                continue

            # 检查条件（简单实现）
            if step.condition:
                if not self._evaluate_condition(step.condition, result.outputs):
                    result.step_results[step_id].status = StepStatus.SKIPPED
                    result.step_results[step_id].error = "Condition not met"
                    continue

            # 执行步骤
            step_result = await self._execute_step(step, chain, result.outputs)
            result.step_results[step_id] = step_result

            if step_result.status == StepStatus.COMPLETED:
                completed_steps.add(step_id)
                # 保存输出
                if step_result.output is not None:
                    result.outputs[step_id] = step_result.output
                if self._on_step_complete:
                    self._on_step_complete(step_id, step_result)
            else:
                if self._on_step_fail:
                    self._on_step_fail(step_id, step_result)

                # 失败处理
                if not chain.config.continue_on_error:
                    # 需要回滚
                    if chain.config.rollback_on_failure:
                        await self._rollback(chain, result, completed_steps)
                    break

        # 判断整体是否成功
        result.success = all(
            r.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
            for r in result.step_results.values()
        )

        result.end_time = time.time()
        result.total_duration_seconds = result.end_time - start_time

        # 记录到记忆系统
        if self._context_manager:
            await self._record_to_memory(chain, result)

        return result

    async def _execute_step(
        self,
        step: ChainStep,
        chain: SkillChain,
        previous_outputs: dict[str, Any],
    ) -> StepResult:
        """执行单个步骤

        Args:
            step: 步骤定义
            chain: 技能链
            previous_outputs: 之前的输出

        Returns:
            步骤执行结果
        """
        result = StepResult(step_id=step.step_id)
        result.status = StepStatus.RUNNING
        result.start_time = time.time()
        result.attempts = 0

        # 准备参数（模板替换）
        args = self._resolve_args(step.args, previous_outputs)

        # 重试逻辑
        max_retries = min(step.retries, chain.config.max_retries)

        for attempt in range(1, max_retries + 1):
            result.attempts = attempt

            try:
                # 执行工具
                tool_result = await self._executor.execute(
                    tool_name=step.tool_name,
                    args=args,
                    context={"task": step.name, "step_id": step.step_id}
                )

                if tool_result.success:
                    result.status = StepStatus.COMPLETED
                    result.output = tool_result.content
                    result.end_time = time.time()
                    result.duration_seconds = result.end_time - result.start_time
                    return result
                else:
                    result.error = tool_result.error or "Execution failed"

            except Exception as e:
                result.error = str(e)

            # 如果还有重试机会，等待后重试
            if attempt < max_retries:
                import asyncio
                await asyncio.sleep(0.1 * attempt)

        # 所有重试都失败
        result.status = StepStatus.FAILED
        result.end_time = time.time()
        result.duration_seconds = result.end_time - result.start_time
        return result

    async def _rollback(
        self,
        chain: SkillChain,
        result: ChainResult,
        completed_steps: set[str],
    ) -> None:
        """回滚已完成的步骤

        Args:
            chain: 技能链
            result: 执行结果
            completed_steps: 已完成的步骤
        """
        # 反向遍历已完成的步骤
        rollback_order = list(reversed(list(completed_steps)))

        for step_id in rollback_order:
            step = chain.get_step(step_id)
            if not step or not step.rollback_tool:
                continue

            # 执行回滚
            try:
                rollback_args = step.rollback_args or {}
                rollback_result = await self._executor.execute(
                    tool_name=step.rollback_tool,
                    args=rollback_args,
                    context={"task": f"Rollback {step.name}", "step_id": step_id}
                )

                if rollback_result.success:
                    result.step_results[step_id].status = StepStatus.ROLLED_BACK
                else:
                    # 回滚失败，记录但继续
                    result.step_results[step_id].error += f" Rollback failed: {rollback_result.error}"

            except Exception as e:
                result.step_results[step_id].error += f" Rollback error: {str(e)}"

    def _resolve_args(
        self,
        args: dict[str, Any],
        previous_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        """解析参数模板

        支持 ${step_id.output} 格式的模板变量。

        Args:
            args: 原始参数
            previous_outputs: 之前的输出

        Returns:
            解析后的参数
        """
        resolved = {}

        for key, value in args.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                # 模板变量
                var_path = value[2:-1].split(".")
                if len(var_path) == 2:
                    step_id, field = var_path
                    if step_id in previous_outputs:
                        output = previous_outputs[step_id]
                        if isinstance(output, dict) and field in output:
                            resolved[key] = output[field]
                        else:
                            resolved[key] = output
                    else:
                        resolved[key] = value  # 保持原样
                else:
                    resolved[key] = value
            else:
                resolved[key] = value

        return resolved

    def _evaluate_condition(
        self,
        condition: str,
        outputs: dict[str, Any],
    ) -> bool:
        """评估条件表达式

        简单实现：检查条件字符串中的变量是否存在。

        Args:
            condition: 条件表达式
            outputs: 之前的输出

        Returns:
            条件是否满足
        """
        # 简单实现：检查是否包含 "exists" 或 "not_empty"
        if "exists:" in condition:
            step_id = condition.split("exists:")[1].strip()
            return step_id in outputs
        elif "not_empty:" in condition:
            step_id = condition.split("not_empty:")[1].strip()
            return step_id in outputs and outputs[step_id]
        return True

    async def _record_to_memory(
        self,
        chain: SkillChain,
        result: ChainResult,
    ) -> None:
        """记录执行结果到记忆系统

        Args:
            chain: 技能链
            result: 执行结果
        """
        if result.success:
            await self._context_manager.remember_success(
                task=f"Execute chain {chain.chain_id}",
                tool_name="chain_executor",
                args={"chain_id": chain.chain_id},
                output=result.get_summary()
            )
        else:
            await self._context_manager.remember_error(
                task=f"Execute chain {chain.chain_id}",
                tool_name="chain_executor",
                args={"chain_id": chain.chain_id},
                error=result.error or result.get_summary()
            )
