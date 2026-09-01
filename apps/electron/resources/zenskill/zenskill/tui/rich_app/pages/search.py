"""搜索结果页面 -- /search 命令。

展示技能搜索结果。
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...data import TuiDataAdapter


class SearchPage:
    """搜索结果页面。"""

    def __init__(self, console: Console, data: TuiDataAdapter):
        self.console = console
        self.data = data

    def render(self, query: str = "", **kwargs) -> None:
        """渲染搜索结果。"""
        if not query:
            self.console.print("[dim]用法: /search <关键词>[/dim]")
            return

        self.console.print(Panel(
            f"搜索: [bold]{query}[/bold]",
            title="🔍 技能搜索",
            border_style="cyan",
        ))

        # 搜索已安装技能
        skills = self.data.list_skills()
        matched = []
        query_lower = query.lower()

        for s in skills:
            skill_id = s.get("skill_id", "").lower()
            if query_lower in skill_id:
                matched.append(s)

        if matched:
            table = Table(title=f"匹配结果 ({len(matched)})", show_lines=False)
            table.add_column("技能", style="cyan", width=20)
            table.add_column("等级", width=10)
            table.add_column("使用次数", width=10)
            table.add_column("成功率", width=10)

            for s in matched:
                level = s.get("level", "NOVICE")
                icon = {"NOVICE": "🌱", "APPRENTICE": "🌿", "JOURNEYMAN": "🌳",
                        "EXPERT": "⭐", "MASTER": "👑"}.get(level, "")
                rate = s.get("success_rate", 0)
                table.add_row(
                    s.get("skill_id", ""),
                    f"{icon} {level}",
                    str(s.get("usage_count", 0)),
                    f"{rate:.0%}" if rate else "-",
                )
            self.console.print(table)
        else:
            self.console.print("[dim]未找到匹配的已安装技能[/dim]")

        # 搜索记忆
        try:
            from zenskill.core.memory.memory_store import MemoryStore
            store = MemoryStore()
            memories = store.search(query, limit=5)
            if memories:
                self.console.print()
                self.console.print(f"[bold]📚 相关记忆 ({len(memories)})[/bold]")
                for m in memories:
                    content = m.content[:80] + ("..." if len(m.content) > 80 else "")
                    self.console.print(f"  · {content}")
        except Exception:
            pass

        self.console.print()
        self.console.print("[dim]CLI: zenskill search \"{query}\" | zenskill discover[/dim]")
