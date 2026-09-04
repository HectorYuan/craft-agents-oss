"""代码审查页面 -- /review 命令。

对接 runtime/agent/code_review.py 的 CodeReviewer（LLM 结构化审查），
支持 working/staged/branch 三种 diff 范围。
"""

from __future__ import annotations

import asyncio

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...data import TuiDataAdapter

_SEVERITY_STYLE = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "dim",
}
_CATEGORY_ICON = {
    "bug": "🐞",
    "security": "🔒",
    "style": "🎨",
    "performance": "⚡",
}


class ReviewPage:
    """代码审查页面。"""

    def __init__(self, console: Console, data: TuiDataAdapter):
        self.console = console
        self.data = data
        self.last_result = None

    def render(self, scope: str = "", base: str = "", **kwargs) -> None:
        """渲染审查结果；无参数时显示用法。"""
        if not scope:
            self.console.print(Panel(
                "用法: /review working   审查未提交改动\n"
                "      /review staged    审查已暂存改动\n"
                "      /review branch <base>   审查分支差异",
                title="🔍 代码审查",
                border_style="cyan",
            ))
            return

        result = self._run_review(scope, base)
        if result is None:
            return
        self._render_result(result)

    def _run_review(self, scope: str, base: str):
        """执行审查（同步包装异步引擎调用）。"""
        try:
            from zenskill.runtime.agent.code_review import (
                CodeReviewError,
                CodeReviewer,
            )
        except ImportError as e:
            self.console.print(f"[red]code_review 模块不可用: {e}[/red]")
            return None

        reviewer = CodeReviewer()
        self.console.print("[dim]▸ LLM 审查中（diff → 结构化 findings）...[/dim]")
        try:
            if scope == "staged":
                result = asyncio.run(reviewer.review_staged(cwd=cwd))
            elif scope == "branch":
                if not base:
                    self.console.print("[yellow]/review branch 需要 base 分支名[/yellow]")
                    return None
                result = asyncio.run(reviewer.review_branch(base, cwd=cwd))
            else:
                result = asyncio.run(reviewer.review_working(cwd=cwd))
        except CodeReviewError as e:
            self.console.print(f"[red]审查失败: {e}[/red]")
            return None
        except Exception as e:
            self.console.print(f"[red]审查异常: {e}[/red]")
            return None

        self.last_result = result
        return result

    def _render_result(self, result) -> None:
        """渲染审查结果。"""
        verdict = "[green]✅ 通过[/green]" if result.passed else "[red]❌ 未通过[/red]"
        self.console.print(Panel(
            f"{verdict}  │  评分: [bold]{result.score}[/bold]  │  "
            f"findings: {len(result.findings)}",
            title="🔍 审查结论",
            border_style="green" if result.passed else "red",
        ))

        if result.summary:
            self.console.print(f"[dim]{result.summary[:300]}[/dim]")

        if not result.findings:
            self.console.print("[dim]无发现[/dim]")
            return

        table = Table(title="Findings", show_lines=False)
        table.add_column("级别", width=9)
        table.add_column("类别", width=5)
        table.add_column("位置", width=28)
        table.add_column("描述", width=48)

        for f in result.findings:
            style = _SEVERITY_STYLE.get(f.severity, "")
            icon = _CATEGORY_ICON.get(f.category, "·")
            location = f"{f.file}:{f.line}" if getattr(f, "file", "") else "-"
            table.add_row(
                f"[{style}]{f.severity}[/{style}]" if style else f.severity,
                icon,
                location[:28],
                (f.title or f.description or "")[:48],
            )
        self.console.print(table)
