"""运行时执行配置（旧引擎退役后的兼容落点，M4-8）。

历史上 execution_loop.ExecutionConfig 与 controller.ExecutionConfig 字段
不同（max_steps/timeout_seconds vs permission_mode/timeout...），此处合并
为单一 dataclass 供 cmd_test_skill / cmd_deploy_skill / SkillDeployer 使用。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExecutionConfig:
    max_steps: int = 10
    timeout_seconds: float = 300.0
    timeout: float = 300.0
    max_retries: int = 3
    permission_mode: str = "restricted"
    enable_memory: bool = True
    enable_reflection: bool = True
    rollback_on_failure: bool = True
