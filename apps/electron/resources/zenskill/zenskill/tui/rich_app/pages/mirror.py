"""用户镜像页面 -- /mirror 命令。

展示用户数据采集、特征向量、隐私设置。
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from ...data import TuiDataAdapter


class MirrorPage:
    """用户镜像页面。"""

    def __init__(self, console: Console, data: TuiDataAdapter):
        self.console = console
        self.data = data

    def render(self, **kwargs) -> None:
        """渲染用户镜像。"""
        # 数据概览
        summary = self.data.get_mirror_data_summary()
        event_count = summary.get("event_count", 0)
        size_bytes = summary.get("total_size_bytes", 0)
        size_str = f"{size_bytes / 1024:.1f} KB" if size_bytes < 1024 * 1024 else f"{size_bytes / 1024 / 1024:.1f} MB"

        self.console.print(Panel(
            f"📊 事件数: [bold]{event_count}[/bold]  │  数据量: [bold]{size_str}[/bold]",
            title="🪞 用户镜像",
            border_style="magenta",
        ))

        # 隐私设置
        prefs = self.data.get_privacy_prefs()
        if prefs:
            collection = getattr(prefs, "data_collection", True)
            self.console.print(Panel(
                f"数据采集: {'🟢 已授权' if collection else '🔴 未授权'}",
                title="🔒 隐私设置",
                border_style="yellow",
            ))

        # 特征摘要
        features = self.data.get_feature_summary()
        if features and features != "特征数据不足":
            self.console.print(Panel(
                features[:500],
                title="📈 特征向量",
                border_style="blue",
            ))

        # 快捷命令
        self.console.print()
        self.console.print("[dim]命令: /mirror status | /mirror features | /mirror privacy | /mirror export[/dim]")
