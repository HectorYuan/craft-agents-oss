"""TUI 主题系统 -- 轻量版 (Rich 样式，无 Textual 依赖)。

提供两个主题: clean (简洁) 和 rich (华丽)。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass
class ZenTheme:
    """主题数据类。"""

    name: str
    display_name: str
    rich_styles: Dict[str, str] = field(default_factory=dict)
    show_decorations: bool = True
    chart_style: str = "decorated"


# ── 内置主题 ──────────────────────────────────────────────────

CLEAN_THEME = ZenTheme(
    name="clean",
    display_name="简洁",
    rich_styles={
        "primary": "#4A90D9",
        "accent": "#67B8DE",
        "success": "#27AE60",
        "warning": "#F39C12",
        "error": "#E74C3C",
        "muted": "#7F8C8D",
    },
    show_decorations=False,
    chart_style="minimal",
)

RICH_THEME = ZenTheme(
    name="rich",
    display_name="华丽",
    rich_styles={
        "primary": "#FFD700",
        "accent": "#9B59B6",
        "success": "#2ECC71",
        "warning": "#E67E22",
        "error": "#E74C3C",
        "muted": "#95A5A6",
    },
    show_decorations=True,
    chart_style="decorated",
)

_THEMES: Dict[str, ZenTheme] = {
    "clean": CLEAN_THEME,
    "rich": RICH_THEME,
}


def get_theme(name: str) -> ZenTheme:
    """获取主题，不存在时返回 rich 主题。"""
    return _THEMES.get(name, RICH_THEME)


def list_themes() -> list:
    """列出所有主题名。"""
    return list(_THEMES.keys())


def register_theme(theme: ZenTheme) -> None:
    """注册自定义主题。"""
    _THEMES[theme.name] = theme


def load_saved_theme() -> str:
    """从配置文件加载保存的主题名。"""
    config_path = Path.home() / ".zenskill" / "config.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            return config.get("tui_theme", "rich")
        except Exception:
            pass
    return "rich"


def save_theme(name: str) -> None:
    """保存主题选择到配置文件。"""
    config_path = Path.home() / ".zenskill" / "config.json"
    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    config["tui_theme"] = name
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
