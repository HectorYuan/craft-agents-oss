"""系统设置页面 -- /system 命令。"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...data import TuiDataAdapter


class SettingsPage:
    """系统设置页面。"""

    def __init__(self, console: Console, data: TuiDataAdapter):
        self.console = console
        self.data = data

    def render(self, **kwargs) -> None:
        """渲染系统设置。"""
        # LLM 信息
        self._render_llm_info()

        # 隐私设置
        self._render_privacy()

        # 数据概览
        self._render_data_summary()

    def _render_llm_info(self):
        """显示 LLM 配置。"""
        try:
            from zenskill.core.llm_provider import get_llm_provider
            from zenskill.core.providers import get_providers

            provider = get_llm_provider()
            providers = get_providers()

            table = Table(title="🤖 LLM Provider", show_lines=False)
            table.add_column("Provider", style="cyan")
            table.add_column("模型")
            table.add_column("状态")

            current_name = type(provider).__name__.replace("LLMProvider", "") if provider else "none"

            for p in providers:
                is_active = p.name == current_name
                status = "[green]● 活跃[/green]" if is_active else "[dim]○[/dim]"
                models = ", ".join(p.models[:3]) if p.models else "-"
                table.add_row(p.name, models, status)

            self.console.print(table)

        except Exception as e:
            self.console.print(f"[dim]LLM 信息不可用: {e}[/dim]")

    def _render_privacy(self):
        """显示隐私设置。"""
        prefs = self.data.get_privacy_prefs()
        if prefs:
            self.console.print(Panel(
                f"数据收集: {'开启' if getattr(prefs, 'data_collection', True) else '关闭'}",
                title="🔒 隐私设置",
                border_style="yellow",
            ))

    def _render_data_summary(self):
        """显示数据概览。"""
        summary = self.data.get_mirror_data_summary()
        event_count = summary.get("event_count", 0)
        size_bytes = summary.get("total_size_bytes", 0)
        size_str = f"{size_bytes / 1024:.1f} KB" if size_bytes < 1024 * 1024 else f"{size_bytes / 1024 / 1024:.1f} MB"

        self.console.print(Panel(
            f"事件数: {event_count}  │  数据量: {size_str}",
            title="📦 数据概览",
            border_style="blue",
        ))
