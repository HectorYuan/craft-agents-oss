"""反思循环引擎"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..mcp_client import ToolResult
from ..memory.memory_store import MemoryEntry, MemoryType
from ..memory.context_manager import ContextManager
from .self_evaluator import SelfEvaluator, Evaluation, ErrorType
from .retry_strategy import RetryStrategy, Strategy, StrategyResult


@dataclass
class ReflectionResult:
    """反思结果"""

    success: bool
    attempts: int
    final_output: Any = None
    error: str = ""
    evaluations: list[dict[str, Any]] = field(default_factory=list)
    strategies: list[dict[str, Any]] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "attempts": self.attempts,
            "final_output": self.final_output,
            "error": self.error,
            "evaluations": self.evaluations,
            "strategies": self.strategies,
            "duration_seconds": self.duration_seconds,
        }


class ReflectionLoop:
    """反思循环引擎

    执行工具调用，失败后自动评估、重试、记录。

    流程：
    1. 执行工具
    2. 如果失败 → 自我评估
    3. 如果可重试 → 获取重试策略 → 调整参数 → 重新执行
    4. 记录到记忆系统
    5. 重复直到成功或达到最大重试次数

    使用方式：
        loop = ReflectionLoop(
            executor=executor,
            context_manager=context_manager,
        )
        result = await loop.run("读取配置文件", {"path": "config.yaml"})
    """

    def __init__(
        self,
        executor: Any,  # ExecutorBase
        context_manager: ContextManager | None = None,
        max_attempts: int = 3,
        evaluator: SelfEvaluator | None = None,
        retry_strategy: RetryStrategy | None = None,
    ):
        """初始化反思循环

        Args:
            executor: 执行器
            context_manager: 上下文管理器
            max_attempts: 最大尝试次数
            evaluator: 自我评估器
            retry_strategy: 重试策略
        """
        self._executor = executor
        self._context_manager = context_manager
        self._max_attempts = max_attempts
        self._evaluator = evaluator or SelfEvaluator()
        self._retry_strategy = retry_strategy or RetryStrategy()

    async def run(
        self,
        task: str,
        args: dict[str, Any] | None = None,
        tool_name: str | None = None,
    ) -> ReflectionResult:
        """执行任务（带反思）

        Args:
            task: 任务描述
            args: 工具参数
            tool_name: 指定工具名称（可选）

        Returns:
            反思结果
        """
        start_time = time.time()
        args = args or {}
        evaluations = []
        strategies = []
        current_args = dict(args)

        # 加载上下文记忆
        if self._context_manager:
            context = await self._context_manager.get_context(task)
            # 将记忆注入到参数中
            if context.get("avoid_errors"):
                current_args["_avoid_errors"] = context["avoid_errors"]

        # 获取可用工具
        if tool_name:
            # 使用指定工具
            tools_to_try = [tool_name]
        else:
            # 从执行器获取所有可用工具
            tools = await self._executor.list_tools()
            tools_to_try = [t.name for t in tools]

        last_error = ""

        for attempt in range(1, self._max_attempts + 1):
            # 选择要尝试的工具
            if attempt <= len(tools_to_try):
                current_tool = tools_to_try[attempt - 1]
            else:
                # 所有工具都试过了，使用最后一个
                current_tool = tools_to_try[-1] if tools_to_try else None

            if not current_tool:
                return ReflectionResult(
                    success=False,
                    attempts=attempt,
                    error="No tools available",
                    evaluations=evaluations,
                    strategies=strategies,
                    duration_seconds=time.time() - start_time,
                )

            # 执行工具
            result = await self._executor.execute(
                current_tool, current_args, {"task": task}
            )

            # 记录执行步骤
            evaluations.append({
                "attempt": attempt,
                "tool": current_tool,
                "args": current_args,
                "success": result.success,
                "error": result.error,
            })

            if result.success:
                # 成功，记录到记忆系统
                if self._context_manager:
                    await self._context_manager.remember_success(
                        task=task,
                        tool_name=current_tool,
                        args=current_args,
                        output=str(result.content)[:200],
                    )

                return ReflectionResult(
                    success=True,
                    attempts=attempt,
                    final_output=result.content,
                    evaluations=evaluations,
                    strategies=strategies,
                    duration_seconds=time.time() - start_time,
                )

            # 失败，进行评估
            last_error = result.error or "Unknown error"

            evaluation = await self._evaluator.evaluate(
                task=task,
                tool_name=current_tool,
                args=current_args,
                result=result,
            )

            evaluations[-1]["evaluation"] = evaluation.to_dict()

            # 记录错误到记忆系统
            if self._context_manager:
                await self._context_manager.remember_error(
                    task=task,
                    tool_name=current_tool,
                    args=current_args,
                    error=last_error,
                )

            # 如果不可重试，停止
            if not evaluation.retryable:
                return ReflectionResult(
                    success=False,
                    attempts=attempt,
                    error=last_error,
                    evaluations=evaluations,
                    strategies=strategies,
                    duration_seconds=time.time() - start_time,
                )

            # 获取重试策略
            history = evaluations[:-1]  # 排除当前尝试
            strategy_result = await self._retry_strategy.get_next_strategy(
                attempt=attempt,
                evaluation=evaluation,
                history=history,
            )

            strategies.append(strategy_result.to_dict())

            # 根据策略调整
            if strategy_result.strategy == Strategy.ABORT:
                return ReflectionResult(
                    success=False,
                    attempts=attempt,
                    error=last_error,
                    evaluations=evaluations,
                    strategies=strategies,
                    duration_seconds=time.time() - start_time,
                )
            elif strategy_result.strategy == Strategy.ASK_USER:
                return ReflectionResult(
                    success=False,
                    attempts=attempt,
                    error=f"Need user help: {strategy_result.reason}",
                    evaluations=evaluations,
                    strategies=strategies,
                    duration_seconds=time.time() - start_time,
                )
            elif strategy_result.modified_args:
                current_args.update(strategy_result.modified_args)

        # 达到最大重试次数
        return ReflectionResult(
            success=False,
            attempts=self._max_attempts,
            error=f"Max attempts ({self._max_attempts}) exceeded. Last error: {last_error}",
            evaluations=evaluations,
            strategies=strategies,
            duration_seconds=time.time() - start_time,
        )
