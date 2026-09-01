"""
SettingsVM — 设置视图 (Phase T+)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
from pathlib import Path

from . import ViewModel, register_viewmodel


@register_viewmodel("settings")
@dataclass
class SettingsVM(ViewModel):
    """系统设置"""

    title: str = "设置"
    icon: str = "⚙️"

    config: Dict[str, Any] = field(default_factory=dict)
    db_stats: Dict[str, Any] = field(default_factory=dict)
    version: str = ""

    @classmethod
    def load(cls) -> "SettingsVM":
        vm = cls()
        try:
            from zenskill import __version__
            vm.version = __version__

            # 数据库统计
            try:
                from zenskill.core.database import db
                vm.db_stats = db.get_stats()
            except Exception:
                vm.db_stats = {"tables": "N/A"}

            # 配置
            config_path = Path.home() / ".zenskill" / "config.json"
            if config_path.exists():
                import json
                vm.config = json.loads(config_path.read_text())
            else:
                vm.config = {}

            vm.data_level = 2
        except Exception as e:
            vm.error = str(e)
        return vm

    def render_l1(self) -> str:
        if self.error:
            return f"  ⚠️ {self.error}"

        from zenskill.render import PlainRenderer
        r = PlainRenderer()

        fields = [
            ("版本", self.version),
            ("主题", self.config.get("tui_theme", "默认")),
            ("数据库表数", str(len(self.db_stats.get("tables", [])))),
            ("数据库大小", f"{self.db_stats.get('size_mb', 0)} MB"),
        ]

        # 显示可用 TUI 模式
        try:
            from zenskill.render import detect_backend
            fields.append(("渲染后端", detect_backend()))
        except Exception:
            pass

        return r.card(
            type('s', (), {'title': '系统设置', 'icon': 'settings',
                           'fields': fields, 'footer': '', 'color': 'primary'})()
        )

    def render_l2(self) -> str:
        if self.error:
            return f"[red]⚠️ {self.error}[/red]"

        from zenskill.render import RichRenderer
        r = RichRenderer()

        fields = [
            ("版本", self.version),
            ("主题", self.config.get("tui_theme", "默认")),
            ("数据库表数", str(len(self.db_stats.get("tables", [])))),
            ("数据库大小", f"{self.db_stats.get('size_mb', 0)} MB"),
        ]
        try:
            from zenskill.render import detect_backend
            fields.append(("渲染后端", detect_backend()))
        except Exception:
            pass

        return r.card(
            type('s', (), {'title': '系统设置', 'icon': 'settings',
                           'fields': fields, 'footer': '', 'color': 'primary'})()
        )
