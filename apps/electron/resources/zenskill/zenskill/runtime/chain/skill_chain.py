"""技能链定义"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class StepStatus(Enum):
    """步骤状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


@dataclass
class ChainConfig:
    """链配置"""
    max_retries: int = 3
    timeout_seconds: int = 300
    rollback_on_failure: bool = True
    continue_on_error: bool = False


@dataclass
class ChainStep:
    """链步骤定义

    表示技能链中的一个执行步骤。

    Attributes:
        step_id: 步骤唯一标识
        name: 步骤名称
        tool_name: 要执行的工具名称
        args: 工具参数（支持模板变量）
        depends_on: 依赖的步骤ID列表
        description: 步骤描述
        timeout: 超时时间（秒）
        retries: 最大重试次数
        rollback_tool: 回滚工具名称
        rollback_args: 回滚参数
        condition: 条件表达式（可选）
    """
    step_id: str
    name: str
    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    description: str = ""
    timeout: int = 30
    retries: int = 3
    rollback_tool: str | None = None
    rollback_args: dict[str, Any] | None = None
    condition: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "step_id": self.step_id,
            "name": self.name,
            "tool_name": self.tool_name,
            "args": self.args,
            "depends_on": self.depends_on,
            "description": self.description,
            "timeout": self.timeout,
            "retries": self.retries,
            "rollback_tool": self.rollback_tool,
            "rollback_args": self.rollback_args,
            "condition": self.condition,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainStep:
        """从字典创建"""
        return cls(
            step_id=data["step_id"],
            name=data["name"],
            tool_name=data["tool_name"],
            args=data.get("args", {}),
            depends_on=data.get("depends_on", []),
            description=data.get("description", ""),
            timeout=data.get("timeout", 30),
            retries=data.get("retries", 3),
            rollback_tool=data.get("rollback_tool"),
            rollback_args=data.get("rollback_args"),
            condition=data.get("condition"),
        )


class SkillChain:
    """技能链

    定义一组有序的技能执行步骤，支持依赖关系、条件执行和回滚。

    使用方式：
        chain = SkillChain("deploy", ChainConfig(rollback_on_failure=True))
        chain.add_step(ChainStep(
            step_id="build",
            name="构建项目",
            tool_name="run_command",
            args={"command": "npm run build"},
        ))
        chain.add_step(ChainStep(
            step_id="test",
            name="运行测试",
            tool_name="run_command",
            args={"command": "npm test"},
            depends_on=["build"],
        ))
        chain.add_step(ChainStep(
            step_id="deploy",
            name="部署",
            tool_name="run_command",
            args={"command": "npm run deploy"},
            depends_on=["test"],
            rollback_tool="run_command",
            rollback_args={"command": "npm run rollback"},
        ))

        executor = ChainExecutor(executor)
        result = await executor.execute(chain)
    """

    def __init__(
        self,
        chain_id: str,
        config: ChainConfig | None = None,
        description: str = "",
    ):
        """初始化技能链

        Args:
            chain_id: 链唯一标识
            config: 链配置
            description: 链描述
        """
        self._chain_id = chain_id
        self._config = config or ChainConfig()
        self._description = description
        self._steps: dict[str, ChainStep] = {}
        self._execution_order: list[str] = []

    @property
    def chain_id(self) -> str:
        return self._chain_id

    @property
    def config(self) -> ChainConfig:
        return self._config

    @property
    def description(self) -> str:
        return self._description

    @property
    def steps(self) -> dict[str, ChainStep]:
        return self._steps.copy()

    @property
    def execution_order(self) -> list[str]:
        return self._execution_order.copy()

    def add_step(self, step: ChainStep) -> None:
        """添加步骤

        Args:
            step: 步骤定义

        Raises:
            ValueError: 步骤ID已存在
        """
        if step.step_id in self._steps:
            raise ValueError(f"Step {step.step_id} already exists")

        self._steps[step.step_id] = step
        self._update_execution_order()

    def remove_step(self, step_id: str) -> None:
        """移除步骤

        Args:
            step_id: 步骤ID

        Raises:
            ValueError: 步骤不存在或被其他步骤依赖
        """
        if step_id not in self._steps:
            raise ValueError(f"Step {step_id} not found")

        # 检查是否有其他步骤依赖此步骤
        for step in self._steps.values():
            if step_id in step.depends_on:
                raise ValueError(f"Step {step_id} is depended by {step.step_id}")

        del self._steps[step_id]
        self._update_execution_order()

    def get_step(self, step_id: str) -> ChainStep | None:
        """获取步骤"""
        return self._steps.get(step_id)

    def get_dependencies(self, step_id: str) -> list[str]:
        """获取步骤的所有依赖（递归）"""
        if step_id not in self._steps:
            return []

        deps = set()
        queue = list(self._steps[step_id].depends_on)

        while queue:
            dep = queue.pop(0)
            if dep in self._steps and dep not in deps:
                deps.add(dep)
                queue.extend(self._steps[dep].depends_on)

        return list(deps)

    def get_dependents(self, step_id: str) -> list[str]:
        """获取依赖此步骤的所有步骤"""
        dependents = []
        for step in self._steps.values():
            if step_id in step.depends_on:
                dependents.append(step.step_id)
        return dependents

    def validate(self) -> list[str]:
        """验证链的有效性

        Returns:
            错误列表，空列表表示有效
        """
        errors = []

        # 检查循环依赖 (DFS)
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {step_id: WHITE for step_id in self._steps}

        def has_cycle(node: str) -> bool:
            color[node] = GRAY
            for dep in self._steps[node].depends_on:
                if dep in self._steps:
                    if color[dep] == GRAY:
                        return True
                    if color[dep] == WHITE and has_cycle(dep):
                        return True
            color[node] = BLACK
            return False

        for step_id in self._steps:
            if color[step_id] == WHITE:
                if has_cycle(step_id):
                    errors.append(f"Circular dependency detected involving {step_id}")

        # 检查所有依赖存在
        for step in self._steps.values():
            for dep in step.depends_on:
                if dep not in self._steps:
                    errors.append(f"Step {step.step_id} depends on non-existent step {dep}")

        return errors

    def _update_execution_order(self) -> None:
        """更新执行顺序（拓扑排序）"""
        in_degree = {step_id: 0 for step_id in self._steps}
        adjacency = {step_id: [] for step_id in self._steps}

        for step in self._steps.values():
            for dep in step.depends_on:
                if dep in self._steps:
                    adjacency[dep].append(step.step_id)
                    in_degree[step.step_id] += 1

        queue = [step_id for step_id, degree in in_degree.items() if degree == 0]
        order = []

        while queue:
            queue.sort()  # 保持稳定顺序
            node = queue.pop(0)
            order.append(node)

            for neighbor in adjacency[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        self._execution_order = order

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "chain_id": self._chain_id,
            "description": self._description,
            "config": {
                "max_retries": self._config.max_retries,
                "timeout_seconds": self._config.timeout_seconds,
                "rollback_on_failure": self._config.rollback_on_failure,
                "continue_on_error": self._config.continue_on_error,
            },
            "steps": {step_id: step.to_dict() for step_id, step in self._steps.items()},
            "execution_order": self._execution_order,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillChain:
        """从字典创建"""
        config_data = data.get("config", {})
        config = ChainConfig(
            max_retries=config_data.get("max_retries", 3),
            timeout_seconds=config_data.get("timeout_seconds", 300),
            rollback_on_failure=config_data.get("rollback_on_failure", True),
            continue_on_error=config_data.get("continue_on_error", False),
        )

        chain = cls(
            chain_id=data["chain_id"],
            config=config,
            description=data.get("description", ""),
        )

        for step_data in data.get("steps", {}).values():
            chain.add_step(ChainStep.from_dict(step_data))

        return chain
