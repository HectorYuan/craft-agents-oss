"""AutomationsPage — 自动化规则页（对齐 GUI automations 面板 / ws automations:* 通道）。

列表 / toggle / run（单次触发一个周期）/ delete；
数据走 AutomationsStore（与 GUI 同源 {workspace_root}/automations.json）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console
from rich.table import Table


class AutomationsPage:
    """自动化规则：列表 / toggle / run / delete。"""

    def __init__(self, console: Console, data) -> None:
        self.console = console
        self.data = data

    def render(self, action: str = "list", automation_id: str = "", **kwargs) -> None:
        if action == "toggle":
            self._toggle(automation_id)
        elif action == "run":
            self._run(automation_id)
        elif action == "delete":
            self._delete(automation_id)
        else:
            self._list()

    # ── store / runner ──────────────────────────────────────────

    def _workspace_root(self) -> Path:
        try:
            from ....core.update_pages import resolve_active_workspace_root
            root = resolve_active_workspace_root()
            if root:
                return Path(root)
        except Exception:
            pass
        return Path.home() / ".zenskill" / "workspace"

    def _store(self):
        from ....server.automations_store import AutomationsStore
        return AutomationsStore(self._workspace_root())

    def _find(self, store, automation_id: str):
        for event, matchers in (store.load().get("automations") or {}).items():
            for m in matchers or []:
                if m.get("id") == automation_id:
                    return event, m
        return "", None

    def _drive(self, coro) -> None:
        try:
            asyncio.run(coro)
        except RuntimeError:
            try:
                asyncio.get_running_loop().create_task(coro)
            except RuntimeError:
                coro.close()

    def _missing(self, automation_id: str) -> None:
        self.console.print(f"[yellow]规则不存在:[/yellow] {automation_id}")

    # ── list ────────────────────────────────────────────────────

    def _list(self):
        try:
            cfg = self._store().load()
        except Exception as e:
            self.console.print(f"[red]automations 读取失败: {e}[/red]")
            return
        automations = cfg.get("automations") or {}
        rows = []
        for event, matchers in automations.items():
            for m in matchers or []:
                rows.append((m, event))
        if not rows:
            self.console.print(
                "[dim]暂无自动化规则 — automations.json 为空（GUI 自动化面板可创建）[/dim]")
            return
        rows.sort(key=lambda r: (r[1], str(r[0].get("id", ""))))
        table = Table(title=f"自动化规则 ({len(rows)})", show_lines=False)
        table.add_column("ID", style="cyan")
        table.add_column("名称")
        table.add_column("事件", style="magenta")
        table.add_column("触发")
        table.add_column("动作")
        table.add_column("启用", justify="center")
        for m, event in rows:
            trigger = m.get("cron") or m.get("matcher") or "-"
            actions = ", ".join(a.get("type", "?") for a in m.get("actions") or []) or "-"
            enabled = "[green]on[/green]" if m.get("enabled", True) else "[dim]off[/dim]"
            table.add_row(
                str(m.get("id", "")),
                str(m.get("name", ""))[:24],
                event,
                str(trigger)[:20],
                actions,
                enabled,
            )
        self.console.print(table)
        self.console.print(
            "[dim]toggle: /automations toggle <id> · run: /automations run <id> · "
            "delete: /automations delete <id>[/dim]")

    # ── toggle ──────────────────────────────────────────────────

    def _toggle(self, automation_id: str):
        if not automation_id:
            self.console.print("[yellow]用法: /automations toggle <id>[/yellow]")
            return
        try:
            store = self._store()
            event, matcher = self._find(store, automation_id)
            if matcher is None:
                self._missing(automation_id)
                return
            enabled = not matcher.get("enabled", True)
            ok = store.set_enabled(event, automation_id, enabled)
        except Exception as e:
            self.console.print(f"[red]toggle 失败: {e}[/red]")
            return
        if ok:
            state = "已启用" if enabled else "已禁用"
            name = matcher.get("name") or automation_id
            self.console.print(f"[green]{state}[/green] {name} ({automation_id})")
        else:
            self._missing(automation_id)

    # ── run ─────────────────────────────────────────────────────

    def _run(self, automation_id: str):
        if not automation_id:
            self.console.print("[yellow]用法: /automations run <id>[/yellow]")
            return
        try:
            store = self._store()
            event, matcher = self._find(store, automation_id)
        except Exception as e:
            self.console.print(f"[red]automations 读取失败: {e}[/red]")
            return
        if matcher is None:
            self._missing(automation_id)
            return
        try:
            from ....server import automation_runner as runner_mod
            # 源码 _record 引用的 _hex6 未定义（见 tests/test_infra_matrix.py），
            # 缺失时补一个等价实现，保证单次触发可完整记录历史
            if not hasattr(runner_mod, "_hex6"):
                runner_mod._hex6 = lambda t: format(int(t) % 0xFFFFFF, "06x")  # noqa: E731
            runner = runner_mod.AutomationRunner(SimpleNamespace(
                _automation_store=store,
                session_manager=None,
                workspace_manager=SimpleNamespace(
                    get_workspace_path=lambda name: self._workspace_root()),
            ))
            self._drive(runner._execute_matcher(matcher, event, {}))
            last = runner.get_history(limit=1)
            if not last:
                self.console.print("[green]已触发[/green] (无可执行动作)")
                return
            entry = last[0]
            status = entry.get("status", "?")
            style = "green" if status == "success" else "red"
            detail = (entry.get("error") or entry.get("actionSummary")
                      or entry.get("sessionId") or "")
            line = f"[{style}]run {status}[/{style}]"
            if detail:
                line += f" — {str(detail)[:80]}"
            self.console.print(line)
        except Exception as e:
            self.console.print(f"[red]run 失败: {e}[/red]")

    # ── delete ──────────────────────────────────────────────────

    def _delete(self, automation_id: str):
        if not automation_id:
            self.console.print("[yellow]用法: /automations delete <id>[/yellow]")
            return
        try:
            store = self._store()
            event, matcher = self._find(store, automation_id)
            if matcher is None:
                self._missing(automation_id)
                return
            removed = store.delete(event, automation_id)
        except Exception as e:
            self.console.print(f"[red]删除失败: {e}[/red]")
            return
        if removed:
            name = matcher.get("name") or automation_id
            self.console.print(f"[green]已删除规则[/green] {name} ({automation_id})")
        else:
            self._missing(automation_id)
