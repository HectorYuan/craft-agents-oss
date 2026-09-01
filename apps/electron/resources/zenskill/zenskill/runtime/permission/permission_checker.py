"""权限检查器"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .permission_mode import (
    PERMISSION_MATRIX,
    PermissionMode,
    ToolCategory,
    classify_tool,
)


@dataclass
class PermissionResult:
    """权限检查结果"""

    allowed: bool
    reason: str = ""
    requires_confirm: bool = False
    category: ToolCategory = ToolCategory.READ

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "requires_confirm": self.requires_confirm,
            "category": self.category.value,
        }


class PermissionChecker:
    """权限检查器

    根据权限模式和工具分类判断操作是否允许。

    使用方式：
        checker = PermissionChecker(PermissionMode.RESTRICTED)
        result = await checker.check("write_file", {"path": "test.txt"})
        if result.requires_confirm:
            # 请求用户确认
            ...
    """

    def __init__(
        self,
        mode: PermissionMode = PermissionMode.RESTRICTED,
        confirm_callback: Optional[Callable[[str, dict], Any]] = None,
    ):
        """初始化权限检查器

        Args:
            mode: 权限模式
            confirm_callback: 确认回调函数，接收 (tool_name, args) 返回用户确认结果
        """
        self._mode = mode
        self._confirm_callback = confirm_callback
        self._custom_rules: list[Callable[[str, dict, PermissionMode], PermissionResult | None]] = []

    @property
    def mode(self) -> PermissionMode:
        return self._mode

    @mode.setter
    def mode(self, value: PermissionMode) -> None:
        self._mode = value

    def add_rule(
        self,
        rule: Callable[[str, dict, PermissionMode], PermissionResult | None],
    ) -> None:
        """添加自定义权限规则

        Args:
            rule: 规则函数，接收 (tool_name, args, mode) 返回 PermissionResult 或 None（跳过）
        """
        self._custom_rules.append(rule)

    async def check(
        self,
        tool_name: str,
        args: dict[str, Any],
        category: ToolCategory | None = None,
    ) -> PermissionResult:
        """检查工具调用权限

        Args:
            tool_name: 工具名称
            args: 工具参数
            category: 工具分类（可选，自动推断）

        Returns:
            权限检查结果
        """
        # 应用自定义规则
        for rule in self._custom_rules:
            result = rule(tool_name, args, self._mode)
            if result is not None:
                return result

        # 分类工具
        if category is None:
            category = classify_tool(tool_name)

        # FULL 模式：全部允许
        if self._mode == PermissionMode.FULL:
            return PermissionResult(
                allowed=True,
                category=category,
            )

        # PLAN 模式：只允许读操作
        if self._mode == PermissionMode.PLAN:
            if category == ToolCategory.READ:
                return PermissionResult(
                    allowed=True,
                    category=category,
                )
            return PermissionResult(
                allowed=False,
                reason=f"PLAN mode: {category.value} operation not allowed",
                requires_confirm=False,
                category=category,
            )

        # 获取矩阵权限
        requires_confirm = PERMISSION_MATRIX.get(
            (self._mode, category), True
        )

        # RESTRICTED 模式：需要确认
        if requires_confirm and self._confirm_callback:
            try:
                confirmed = await self._confirm_callback(tool_name, args)
                if not confirmed:
                    return PermissionResult(
                        allowed=False,
                        reason="User denied the operation",
                        requires_confirm=True,
                        category=category,
                    )
            except Exception as e:
                return PermissionResult(
                    allowed=False,
                    reason=f"Confirm callback error: {e}",
                    requires_confirm=True,
                    category=category,
                )

        return PermissionResult(
            allowed=True,
            requires_confirm=requires_confirm,
            category=category,
        )

    def check_sync(
        self,
        tool_name: str,
        args: dict[str, Any],
        category: ToolCategory | None = None,
    ) -> PermissionResult:
        """同步版本的权限检查（用于测试）

        注意：不会调用 confirm_callback
        """
        # 应用自定义规则
        for rule in self._custom_rules:
            result = rule(tool_name, args, self._mode)
            if result is not None:
                return result

        # 分类工具
        if category is None:
            category = classify_tool(tool_name)

        # FULL 模式：全部允许
        if self._mode == PermissionMode.FULL:
            return PermissionResult(allowed=True, category=category)

        # PLAN 模式：只允许读操作
        if self._mode == PermissionMode.PLAN:
            if category == ToolCategory.READ:
                return PermissionResult(allowed=True, category=category)
            return PermissionResult(
                allowed=False,
                reason=f"PLAN mode: {category.value} operation not allowed",
                category=category,
            )

        # 获取矩阵权限
        requires_confirm = PERMISSION_MATRIX.get((self._mode, category), True)

        return PermissionResult(
            allowed=True,
            requires_confirm=requires_confirm,
            category=category,
        )
