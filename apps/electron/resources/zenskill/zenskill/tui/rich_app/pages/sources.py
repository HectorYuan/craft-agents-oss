"""SourcesPage — 来源注册页（C 阶段，对齐 GUI SourceInfoPage / ws sources:* 通道）。

列表 / toggle / delete；数据与 GUI 同源存储
{config_dir}/workspaces/{ws_id}/sources/{slug}/config.json
（ws_server.SourceManager 同款布局）。credentials:healthCheck 是全局探针、
非 per-source 健康源，故状态列只呈现 enabled。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from rich.console import Console
from rich.table import Table


class SourcesPage:
    """来源注册：列表 / toggle / delete。"""

    def __init__(self, console: Console, data) -> None:
        self.console = console
        self.data = data

    def render(self, action: str = "list", source_id: str = "", **kwargs) -> None:
        if action == "toggle":
            self._toggle(source_id)
        elif action == "delete":
            self._delete(source_id)
        else:
            self._list()

    # ── store（与 ws_server.SourceManager 同源）─────────────────

    def _registry_root(self) -> Path:
        try:
            from ....core.paths import get_config_dir
            return get_config_dir() / "workspaces"
        except Exception:
            return Path.home() / ".zenskill" / "workspaces"

    def _iter_sources(self):
        root = self._registry_root()
        if not root.exists():
            return []
        sources = []
        for cfg_path in sorted(root.glob("*/sources/*/config.json")):
            try:
                config = json.loads(cfg_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            sources.append({
                "config": config if isinstance(config, dict) else {},
                "config_path": cfg_path,
                "dir": cfg_path.parent,
            })
        return sources

    def _find(self, sources, source_id: str):
        for source in sources:
            cfg = source["config"]
            if str(cfg.get("slug", "")) == source_id or str(cfg.get("id", "")) == source_id:
                return source
        return None

    def _missing(self, source_id: str) -> None:
        self.console.print(f"[yellow]来源不存在:[/yellow] {source_id}")

    # ── list ────────────────────────────────────────────────────

    def _list(self):
        try:
            sources = self._iter_sources()
        except Exception as e:
            self.console.print(f"[red]sources 读取失败: {e}[/red]")
            return
        if not sources:
            self.console.print(
                "[dim]暂无已注册来源 — sources/*/config.json 为空（GUI 来源面板可注册）[/dim]")
            return
        table = Table(title=f"已注册来源 ({len(sources)})", show_lines=False)
        table.add_column("Slug", style="cyan")
        table.add_column("名称")
        table.add_column("类型", style="magenta")
        table.add_column("Provider")
        table.add_column("启用", justify="center")
        table.add_column("目录", style="dim")
        for source in sources:
            cfg = source["config"]
            enabled = "[green]on[/green]" if cfg.get("enabled", True) else "[dim]off[/dim]"
            table.add_row(
                str(cfg.get("slug", "")),
                str(cfg.get("name", ""))[:24],
                str(cfg.get("type", "mcp")),
                str(cfg.get("provider", "-")),
                enabled,
                source["dir"].name[:20],
            )
        self.console.print(table)
        self.console.print(
            "[dim]toggle: /sources toggle <slug> · delete: /sources delete <slug>[/dim]")

    # ── toggle ──────────────────────────────────────────────────

    def _toggle(self, source_id: str):
        if not source_id:
            self.console.print("[yellow]用法: /sources toggle <slug>[/yellow]")
            return
        try:
            sources = self._iter_sources()
            source = self._find(sources, source_id)
            if source is None:
                self._missing(source_id)
                return
            enabled = not source["config"].get("enabled", True)
            source["config"]["enabled"] = enabled
            source["config_path"].write_text(
                json.dumps(source["config"], ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception as e:
            self.console.print(f"[red]toggle 失败: {e}[/red]")
            return
        state = "已启用" if enabled else "已禁用"
        name = source["config"].get("name") or source_id
        self.console.print(f"[green]{state}[/green] {name} ({source_id})")

    # ── delete ──────────────────────────────────────────────────

    def _delete(self, source_id: str):
        if not source_id:
            self.console.print("[yellow]用法: /sources delete <slug>[/yellow]")
            return
        try:
            sources = self._iter_sources()
            source = self._find(sources, source_id)
            if source is None:
                self._missing(source_id)
                return
            shutil.rmtree(source["dir"])
        except Exception as e:
            self.console.print(f"[red]删除失败: {e}[/red]")
            return
        name = source["config"].get("name") or source_id
        self.console.print(f"[green]已删除来源[/green] {name} ({source_id})")
