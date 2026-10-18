"""SessionsPage — 会话生命周期页（B3，对齐 GUI session-list）。

列表 / 导出 Markdown / 删除；数据走 runtime SessionManager（与 GUI 同源存储）。
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table


class SessionsPage:
    """会话生命周期：列表 / export / delete。"""

    def __init__(self, console: Console, data) -> None:
        self.console = console
        self.data = data

    def render(self, action: str = "list", session_id: str = "", **kwargs) -> None:
        if action == "export":
            self._export(session_id)
        elif action == "delete":
            self._delete(session_id)
        else:
            self._list()

    # ── list ────────────────────────────────────────────────────

    def _list(self):
        from ....runtime.agent.session import SessionManager
        sessions = SessionManager().list_sessions()
        if not sessions:
            self.console.print("[dim]暂无历史会话[/dim]")
            return

        table = Table(title="🗂 会话列表", show_lines=False)
        table.add_column("Session ID", style="cyan")
        table.add_column("创建时间")
        table.add_column("条目", justify="right")
        table.add_column("分支", justify="right")
        table.add_column("CWD", style="dim")
        for s in sorted(sessions, key=lambda x: x.get("created") or "", reverse=True)[:20]:
            sid = s["id"]
            table.add_row(
                sid[:16] + ("…" if len(sid) > 16 else ""),
                str(s.get("created") or "")[:19],
                str(s.get("entries", 0)),
                str(s.get("branches", 0)),
                s.get("cwd", ""),
            )
        self.console.print(table)
        self.console.print(
            "[dim]export: /sessions export <id> · delete: /sessions delete <id>[/dim]")

    # ── export ──────────────────────────────────────────────────

    def _export(self, session_id: str):
        if not session_id:
            self.console.print("[yellow]用法: /sessions export <session_id>[/yellow]")
            return
        try:
            from ....runtime.agent.session import SessionManager, export_markdown
            manager = SessionManager()
            session = manager.load(session_id)
        except Exception as e:
            self.console.print(f"[red]会话不存在: {e}[/red]")
            return
        try:
            from datetime import datetime
            out_dir = Path.home() / ".zenskill" / "exports"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / (
                f"session_{session_id[:16]}_{datetime.now():%Y%m%d_%H%M%S}.md")
            out_path.write_text(export_markdown(session), encoding="utf-8")
            self.console.print(f"[green]已导出:[/green] {out_path}")
        except Exception as e:
            self.console.print(f"[red]导出失败: {e}[/red]")

    # ── delete ──────────────────────────────────────────────────

    def _delete(self, session_id: str):
        if not session_id:
            self.console.print("[yellow]用法: /sessions delete <session_id>[/yellow]")
            return
        try:
            from ....runtime.agent.session import SessionManager
            removed = SessionManager().delete_session(session_id)
        except Exception as e:
            self.console.print(f"[red]删除失败: {e}[/red]")
            return
        if removed:
            self.console.print(f"[green]已删除会话[/green] {session_id[:16]}…")
        else:
            self.console.print(f"[yellow]会话不存在:[/yellow] {session_id[:16]}…")
