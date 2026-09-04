"""TUI 主题系统 -- 轻量版 (Rich 样式，无 Textual 依赖)。

提供 5 个主题: clean (简洁) / rich (华丽) / zen (禅意) / mono (单色) / light (亮色)。
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

# 禅意主题 -- 主色 Zen Green (docs/UI_DESIGN_SYSTEM.md)，暗绿底低刺激
ZEN_THEME = ZenTheme(
    name="zen",
    display_name="禅意",
    rich_styles={
        "primary": "#00D2A0",
        "accent": "#5EEAD4",
        "success": "#00D2A0",
        "warning": "#F5C542",
        "error": "#E5484D",
        "muted": "#5F7A70",
        "background": "#0A1612",
    },
    show_decorations=False,
    chart_style="minimal",
)

# 单色主题 -- 全灰阶，适合低色域终端
MONO_THEME = ZenTheme(
    name="mono",
    display_name="单色",
    rich_styles={
        "primary": "#CCCCCC",
        "accent": "#E6E6E6",
        "success": "#B8B8B8",
        "warning": "#A0A0A0",
        "error": "#8C8C8C",
        "muted": "#666666",
    },
    show_decorations=False,
    chart_style="minimal",
)

# 亮色主题 -- 适配亮色终端背景
LIGHT_THEME = ZenTheme(
    name="light",
    display_name="亮色",
    rich_styles={
        "primary": "#2563EB",
        "accent": "#3B82F6",
        "success": "#16A34A",
        "warning": "#D97706",
        "error": "#DC2626",
        "muted": "#6B7280",
        "background": "#FFFFFF",
    },
    show_decorations=False,
    chart_style="minimal",
)

_THEMES: Dict[str, ZenTheme] = {
    "clean": CLEAN_THEME,
    "rich": RICH_THEME,
    "zen": ZEN_THEME,
    "mono": MONO_THEME,
    "light": LIGHT_THEME,
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
