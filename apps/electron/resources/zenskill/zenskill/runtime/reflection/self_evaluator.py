"""自我评估器"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..mcp_client import ToolResult


class ErrorType(Enum):
    """错误类型分类"""

    NOT_FOUND = "not_found"  # 文件/资源未找到
    PERMISSION_DENIED = "permission_denied"  # 权限不足
    TIMEOUT = "timeout"  # 执行超时
    INVALID_ARGS = "invalid_args"  # 参数错误
    CONNECTION_ERROR = "connection_error"  # 连接错误
    SYNTAX_ERROR = "syntax_error"  # 语法错误
    RUNTIME_ERROR = "runtime_error"  # 运行时错误
    UNKNOWN = "unknown"  # 未知错误


@dataclass
class Evaluation:
    """评估结果"""

    error_type: ErrorType
    retryable: bool
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.8
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type.value,
            "retryable": self.retryable,
            "alternatives": self.alternatives,
            "confidence": self.confidence,
            "suggestion": self.suggestion,
        }


class SelfEvaluator:
    """自我评估器

    分析执行失败原因，判断是否可重试，生成替代方案。

    使用方式：
        evaluator = SelfEvaluator()
        evaluation = await evaluator.evaluate(
            task="read file",
            tool_name="read_file",
            args={"path": "missing.txt"},
            result=ToolResult(success=False, error="File not found"),
        )
        if evaluation.retryable:
            # 重试
            ...
    """

    # 错误模式匹配规则（按优先级排序，先匹配先返回）
    ERROR_PATTERNS: dict[ErrorType, list[str]] = {
        ErrorType.NOT_FOUND: [
            "not found",
            "no such file",
            "does not exist",
            "找不到",
            "不存在",
            "no such directory",
            "not a directory",
        ],
        ErrorType.PERMISSION_DENIED: [
            "permission denied",
            "access denied",
            "权限",
            "不允许",
            "denied by sandbox",
        ],
        ErrorType.TIMEOUT: [
            "timeout",
            "timed out",
            "超时",
        ],
        ErrorType.SYNTAX_ERROR: [
            "syntax error",
            "syntaxerror",
            "indentation",
            "语法",
        ],
        ErrorType.INVALID_ARGS: [
            "invalid argument",
            "required",
            "missing",
            "参数错误",
        ],
        ErrorType.CONNECTION_ERROR: [
            "connection",
            "connect",
            "refused",
            "连接",
        ],
        ErrorType.RUNTIME_ERROR: [
            "runtime error",
            "exception",
            "traceback",
        ],
    }

    # 错误类型 → 是否可重试
    RETRYABLE_ERRORS: dict[ErrorType, bool] = {
        ErrorType.NOT_FOUND: True,  # 可能是路径问题
        ErrorType.PERMISSION_DENIED: False,  # 权限问题不可重试
        ErrorType.TIMEOUT: True,  # 可能是暂时的
        ErrorType.INVALID_ARGS: True,  # 可能是参数格式问题
        ErrorType.CONNECTION_ERROR: True,  # 可能是暂时的
        ErrorType.SYNTAX_ERROR: False,  # 语法错误不可重试
        ErrorType.RUNTIME_ERROR: True,  # 可能是环境问题
        ErrorType.UNKNOWN: False,  # 未知错误不重试
    }

    async def evaluate(
        self,
        task: str,
        tool_name: str,
        args: dict[str, Any],
        result: ToolResult,
        context: dict[str, Any] | None = None,
    ) -> Evaluation:
        """评估执行结果

        Args:
            task: 任务描述
            tool_name: 工具名称
            args: 工具参数
            result: 执行结果
            context: 上下文信息

        Returns:
            评估结果
        """
        error_msg = result.error or ""

        # 分类错误类型
        error_type = self._classify_error(error_msg)

        # 判断是否可重试
        retryable = self.RETRYABLE_ERRORS.get(error_type, False)

        # 生成替代方案
        alternatives = await self._suggest_alternatives(
            task, tool_name, args, error_type, error_msg
        )

        # 生成建议
        suggestion = self._generate_suggestion(error_type, tool_name, args, error_msg)

        return Evaluation(
            error_type=error_type,
            retryable=retryable,
            alternatives=alternatives,
            confidence=0.8,
            suggestion=suggestion,
        )

    def _classify_error(self, error_msg: str) -> ErrorType:
        """分类错误类型"""
        error_lower = error_msg.lower()

        for error_type, patterns in self.ERROR_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in error_lower:
                    return error_type

        return ErrorType.UNKNOWN

    async def _suggest_alternatives(
        self,
        task: str,
        tool_name: str,
        args: dict[str, Any],
        error_type: ErrorType,
        error_msg: str,
    ) -> list[dict[str, Any]]:
        """生成替代方案"""
        alternatives = []

        if error_type == ErrorType.NOT_FOUND:
            # 尝试不同的路径
            path = args.get("path", "")
            if path:
                # 尝试绝对路径
                if not path.startswith("/"):
                    alternatives.append({
                        "action": "try_absolute_path",
                        "args": {"path": f"/{path}"},
                    })
                # 尝试添加扩展名
                if "." not in path.split("/")[-1]:
                    alternatives.append({
                        "action": "try_with_extension",
                        "args": {"path": f"{path}.txt"},
                    })

        elif error_type == ErrorType.INVALID_ARGS:
            # 尝试不同的参数格式
            if tool_name == "run_command":
                command = args.get("command", "")
                if command:
                    alternatives.append({
                        "action": "try_with_shell",
                        "args": {"command": f"sh -c '{command}'"},
                    })

        elif error_type == ErrorType.TIMEOUT:
            # 尝试增加超时时间
            timeout = args.get("timeout", 30)
            alternatives.append({
                "action": "increase_timeout",
                "args": {"timeout": timeout * 2},
            })

        return alternatives

    def _generate_suggestion(
        self,
        error_type: ErrorType,
        tool_name: str,
        args: dict[str, Any],
        error_msg: str,
    ) -> str:
        """生成建议"""
        if error_type == ErrorType.NOT_FOUND:
            path = args.get("path", args.get("directory", ""))
            return f"检查路径是否正确: {path}"
        elif error_type == ErrorType.PERMISSION_DENIED:
            return "需要更高权限或使用 --mode full"
        elif error_type == ErrorType.TIMEOUT:
            return "增加超时时间或简化任务"
        elif error_type == ErrorType.INVALID_ARGS:
            return "检查参数格式和必填字段"
        elif error_type == ErrorType.CONNECTION_ERROR:
            return "检查网络连接或 MCP Server 状态"
        elif error_type == ErrorType.SYNTAX_ERROR:
            return "检查代码语法"
        else:
            return f"错误: {error_msg[:100]}"
