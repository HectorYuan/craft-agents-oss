"""重试策略"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .self_evaluator import ErrorType, Evaluation


class Strategy(Enum):
    """重试策略"""

    ADJUST_ARGUMENTS = "adjust_arguments"  # 调整参数
    SWITCH_TOOL = "switch_tool"  # 切换同类工具
    REPLAN_PATH = "replan_path"  # 重新规划路径
    EXPAND_QUERY = "expand_query"  # 扩展查询关键词
    ASK_USER = "ask_user"  # 请求用户帮助
    ABORT = "abort"  # 放弃执行


@dataclass
class StrategyResult:
    """策略执行结果"""

    strategy: Strategy
    next_action: str
    modified_args: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "next_action": self.next_action,
            "modified_args": self.modified_args,
            "reason": self.reason,
        }


class RetryStrategy:
    """重试策略

    根据错误类型和历史记录选择最优重试策略。

    策略优先级：
    1. ADJUST_ARGUMENTS — 调整参数（如路径格式）
    2. SWITCH_TOOL — 切换同类工具
    3. REPLAN_PATH — 重新规划执行路径
    4. EXPAND_QUERY — 扩展查询关键词
    5. ASK_USER — 请求用户帮助
    6. ABORT — 放弃执行

    使用方式：
        strategy = RetryStrategy()
        result = await strategy.get_next_strategy(
            attempt=1,
            evaluation=evaluation,
            history=[...],
        )
    """

    # 错误类型 → 推荐策略序列
    ERROR_STRATEGIES: dict[ErrorType, list[Strategy]] = {
        ErrorType.NOT_FOUND: [
            Strategy.ADJUST_ARGUMENTS,
            Strategy.SWITCH_TOOL,
            Strategy.ASK_USER,
        ],
        ErrorType.PERMISSION_DENIED: [
            Strategy.ASK_USER,
        ],
        ErrorType.TIMEOUT: [
            Strategy.ADJUST_ARGUMENTS,
            Strategy.SWITCH_TOOL,
            Strategy.ABORT,
        ],
        ErrorType.INVALID_ARGS: [
            Strategy.ADJUST_ARGUMENTS,
            Strategy.SWITCH_TOOL,
            Strategy.ASK_USER,
        ],
        ErrorType.CONNECTION_ERROR: [
            Strategy.ADJUST_ARGUMENTS,
            Strategy.ABORT,
        ],
        ErrorType.SYNTAX_ERROR: [
            Strategy.ABORT,
        ],
        ErrorType.RUNTIME_ERROR: [
            Strategy.ADJUST_ARGUMENTS,
            Strategy.SWITCH_TOOL,
            Strategy.REPLAN_PATH,
        ],
        ErrorType.UNKNOWN: [
            Strategy.ASK_USER,
        ],
    }

    # 最大重试次数
    MAX_RETRY_ATTEMPTS = 3

    async def get_next_strategy(
        self,
        attempt: int,
        evaluation: Evaluation,
        history: list[dict[str, Any]],
    ) -> StrategyResult:
        """获取下一个重试策略

        Args:
            attempt: 当前尝试次数（从 1 开始）
            evaluation: 评估结果
            history: 历史执行记录

        Returns:
            策略执行结果
        """
        # 超过最大重试次数，放弃
        if attempt >= self.MAX_RETRY_ATTEMPTS:
            return StrategyResult(
                strategy=Strategy.ABORT,
                next_action="abort",
                reason=f"Max retry attempts ({self.MAX_RETRY_ATTEMPTS}) exceeded",
            )

        # 不可重试，放弃
        if not evaluation.retryable:
            return StrategyResult(
                strategy=Strategy.ABORT,
                next_action="abort",
                reason=f"Error type {evaluation.error_type.value} is not retryable",
            )

        # 根据错误类型选择策略序列
        strategies = self.ERROR_STRATEGIES.get(
            evaluation.error_type,
            [Strategy.ASK_USER],
        )

        # 根据尝试次数选择策略
        strategy_index = min(attempt - 1, len(strategies) - 1)
        strategy = strategies[strategy_index]

        # 生成具体行动
        return await self._execute_strategy(strategy, evaluation, history)

    async def _execute_strategy(
        self,
        strategy: Strategy,
        evaluation: Evaluation,
        history: list[dict[str, Any]],
    ) -> StrategyResult:
        """执行策略"""
        if strategy == Strategy.ADJUST_ARGUMENTS:
            return await self._adjust_arguments(evaluation, history)
        elif strategy == Strategy.SWITCH_TOOL:
            return await self._switch_tool(evaluation, history)
        elif strategy == Strategy.REPLAN_PATH:
            return await self._replan_path(evaluation, history)
        elif strategy == Strategy.EXPAND_QUERY:
            return await self._expand_query(evaluation, history)
        elif strategy == Strategy.ASK_USER:
            return await self._ask_user(evaluation)
        else:
            return StrategyResult(
                strategy=Strategy.ABORT,
                next_action="abort",
                reason="Unknown strategy",
            )

    async def _adjust_arguments(
        self,
        evaluation: Evaluation,
        history: list[dict[str, Any]],
    ) -> StrategyResult:
        """调整参数"""
        # 从替代方案中获取调整建议
        if evaluation.alternatives:
            alt = evaluation.alternatives[0]
            return StrategyResult(
                strategy=Strategy.ADJUST_ARGUMENTS,
                next_action=alt.get("action", "retry"),
                modified_args=alt.get("args", {}),
                reason=f"Adjusted arguments based on: {alt.get('action', '')}",
            )

        return StrategyResult(
            strategy=Strategy.ADJUST_ARGUMENTS,
            next_action="retry",
            reason="Retry with same arguments",
        )

    async def _switch_tool(
        self,
        evaluation: Evaluation,
        history: list[dict[str, Any]],
    ) -> StrategyResult:
        """切换同类工具"""
        # 分析历史记录，找出未尝试过的工具
        tried_tools = set()
        for step in history:
            if "tool" in step:
                tried_tools.add(step["tool"])

        return StrategyResult(
            strategy=Strategy.SWITCH_TOOL,
            next_action="select_alternative_tool",
            reason=f"Tried tools: {tried_tools}. Select a different tool.",
        )

    async def _replan_path(
        self,
        evaluation: Evaluation,
        history: list[dict[str, Any]],
    ) -> StrategyResult:
        """重新规划路径"""
        return StrategyResult(
            strategy=Strategy.REPLAN_PATH,
            next_action="replan",
            reason="Replan execution path with different approach",
        )

    async def _expand_query(
        self,
        evaluation: Evaluation,
        history: list[dict[str, Any]],
    ) -> StrategyResult:
        """扩展查询关键词"""
        return StrategyResult(
            strategy=Strategy.EXPAND_QUERY,
            next_action="expand_keywords",
            reason="Expand search keywords for better matching",
        )

    async def _ask_user(
        self,
        evaluation: Evaluation,
    ) -> StrategyResult:
        """请求用户帮助"""
        return StrategyResult(
            strategy=Strategy.ASK_USER,
            next_action="prompt_user",
            reason=evaluation.suggestion or "Need user assistance",
        )
