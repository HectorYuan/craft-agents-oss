"""链执行结果"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .skill_chain import StepStatus


@dataclass
class StepResult:
    """步骤执行结果

    Attributes:
        step_id: 步骤ID
        status: 执行状态
        output: 执行输出
        error: 错误信息
        attempts: 尝试次数
        duration_seconds: 执行耗时
        start_time: 开始时间
        end_time: 结束时间
    """
    step_id: str
    status: StepStatus = StepStatus.PENDING
    output: Any = None
    error: str = ""
    attempts: int = 0
    duration_seconds: float = 0.0
    start_time: float = 0.0
    end_time: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "step_id": self.step_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "attempts": self.attempts,
            "duration_seconds": self.duration_seconds,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


@dataclass
class ChainResult:
    """链执行结果

    Attributes:
        chain_id: 链ID
        success: 是否成功
        step_results: 各步骤结果
        outputs: 所有步骤输出的聚合
        error: 错误信息
        total_duration_seconds: 总耗时
        start_time: 开始时间
        end_time: 结束时间
    """
    chain_id: str
    success: bool = False
    step_results: dict[str, StepResult] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    total_duration_seconds: float = 0.0
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def completed_steps(self) -> list[str]:
        """已完成的步骤"""
        return [
            step_id for step_id, result in self.step_results.items()
            if result.status == StepStatus.COMPLETED
        ]

    @property
    def failed_steps(self) -> list[str]:
        """失败的步骤"""
        return [
            step_id for step_id, result in self.step_results.items()
            if result.status == StepStatus.FAILED
        ]

    @property
    def rolled_back_steps(self) -> list[str]:
        """已回滚的步骤"""
        return [
            step_id for step_id, result in self.step_results.items()
            if result.status == StepStatus.ROLLED_BACK
        ]

    def get_step_output(self, step_id: str) -> Any:
        """获取步骤输出"""
        return self.outputs.get(step_id)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "chain_id": self.chain_id,
            "success": self.success,
            "step_results": {
                step_id: result.to_dict()
                for step_id, result in self.step_results.items()
            },
            "outputs": self.outputs,
            "error": self.error,
            "total_duration_seconds": self.total_duration_seconds,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "rolled_back_steps": self.rolled_back_steps,
        }

    def get_summary(self) -> str:
        """获取执行摘要"""
        total = len(self.step_results)
        completed = len(self.completed_steps)
        failed = len(self.failed_steps)
        rolled_back = len(self.rolled_back_steps)

        status = "成功" if self.success else "失败"
        return (
            f"链 {self.chain_id} 执行{status}: "
            f"{completed}/{total} 步骤完成, "
            f"{failed} 失败, "
            f"{rolled_back} 回滚, "
            f"耗时 {self.total_duration_seconds:.1f}s"
        )
