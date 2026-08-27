"""知识库页面 -- /knowledge 命令。

展示记忆库、反思历史、技能图谱。
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...data import TuiDataAdapter


class KnowledgePage:
    """知识库页面。"""

    def __init__(self, console: Console, data: TuiDataAdapter):
        self.console = console
        self.data = data

    def render(self, **kwargs) -> None:
        """渲染知识库。"""
        # 记忆统计
        entries = []
        total = 0
        by_type = {}
        try:
            from zenskill.core.memory.memory_store import MemoryStore
            store = MemoryStore()
            entries = store.list_all(limit=100)
            total = len(entries)
            for e in entries:
                t = e.memory_type.value if hasattr(e.memory_type, 'value') else str(e.memory_type)
                by_type[t] = by_type.get(t, 0) + 1
        except Exception:
            pass

        self.console.print(Panel(
            f"📚 记忆总数: [bold]{total}[/bold]",
            title="📚 知识库",
            border_style="blue",
        ))

        # 记忆分类
        if by_type:
            table = Table(title="记忆分类", show_lines=False)
            table.add_column("类型", style="cyan")
            table.add_column("数量", width=8)

            for t, count in sorted(by_type.items(), key=lambda x: -x[1]):
                table.add_row(t, str(count))
            self.console.print(table)

        # 最近记忆
        if entries:
            self.console.print()
            self.console.print("[bold]📝 最近记忆[/bold]")
            for e in entries[:5]:
                content = e.content[:80] + ("..." if len(e.content) > 80 else "")
                tags = ", ".join(e.tags[:3]) if e.tags else ""
                self.console.print(f"  · {content}" + (f" [{tags}]" if tags else ""))

        # 快捷命令
        self.console.print()
        self.console.print("[dim]命令: /memory list | /memory search <词> | /memory add <内容> | /reflect trigger[/dim]")
