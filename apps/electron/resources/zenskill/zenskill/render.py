"""
统一渲染引擎 (Phase R1)

三段一致，渐进增强: Plain ANSI → Rich → Textual

用法:
    from zenskill.render import RenderEngine, CardSpec, TableSpec, BarChartSpec

    r = RenderEngine()
    r.card(CardSpec(title="技能", icon="📦", fields=[("名称", "tsx")]))
    r.table(TableSpec(headers=["名称", "评分"], rows=[["tsx", "4.5"]]))
    r.bar_chart(BarChartSpec(data=[("熟练度", 42, 100)]))
    r.status(ok=True, message="完成")

CLI 集成:
    from zenskill.render import render_to_string, render_to_cli
    print(render_to_string(...))  # 返回字符串
    render_to_cli(...)             # 直接输出到终端
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════
# Design Tokens
# ═══════════════════════════════════════════════════════════════

# ── 语义色 ──
COLORS: Dict[str, str] = {
    "primary":         "#00D2A0",
    "secondary":       "#4A90D9",
    "accent":          "#9B59B6",
    "background":      "#0D1117",
    "surface":         "#161B22",
    "text":            "#E6EDF3",
    "text_muted":      "#6E7681",
    "success":         "#00D2A0",
    "warning":         "#F9CA24",
    "error":           "#FF6B6B",
    "info":            "#4A90D9",
    "muted":           "#6E7681",
    # 等级
    "level_novice":       "#6E7681",
    "level_apprentice":   "#4A90D9",
    "level_journeyman":   "#9B59B6",
    "level_expert":       "#F9CA24",
    "level_master":       "#00D2A0",
    # 五维
    "dim_proficiency":    "#00D2A0",
    "dim_stability":      "#4A90D9",
    "dim_satisfaction":   "#F9CA24",
    "dim_responsiveness": "#9B59B6",
    "dim_memory":         "#FF6B6B",
    # 分类
    "category_dev":       "#4A90D9",
    "category_design":    "#9B59B6",
    "category_data":      "#00D2A0",
    "category_ops":       "#F9CA24",
    "category_writing":   "#FF6B6B",
}

# ── 图标 ──
ICONS: Dict[str, str] = {
    "skill": "📦", "github_skill": "🐙", "npx_skill": "📦",
    "content_skill": "📖", "builtin_skill": "⚙️",
    "level_novice": "🌱", "level_apprentice": "🌿",
    "level_journeyman": "🌳", "level_expert": "⭐", "level_master": "👑",
    "search": "🔍", "install": "📥", "save": "💾", "delete": "🗑️",
    "refresh": "🔄", "settings": "⚙️", "help": "❓", "info": "ℹ️",
    "success": "✅", "warning": "⚠️", "error": "❌",
    "pending": "⏳", "empty": "📭",
    "dashboard": "📊", "growth": "📈", "memory": "🧠",
    "reflect": "🧘", "gtd": "✅", "graph": "🕸️",
    "category_dev": "💻", "category_design": "🎨",
    "category_data": "📊", "category_ops": "🚀", "category_writing": "✍️",
}

# ── Plain 模式降级图标 ──
PLAIN_ICONS: Dict[str, str] = {
    "success": "[OK]", "error": "[ERR]", "warning": "[WARN]",
    "info": "[INFO]", "pending": "[...]", "empty": "[-]",
}

# ── ANSI 256 降级映射 ──
ANSI256: Dict[str, int] = {
    "#00D2A0": 43, "#4A90D9": 33, "#9B59B6": 129,
    "#F9CA24": 220, "#FF6B6B": 203, "#6E7681": 249,
    "#0D1117": 233, "#161B22": 235, "#E6EDF3": 255,
}


# ═══════════════════════════════════════════════════════════════
# 后端检测
# ═══════════════════════════════════════════════════════════════

_TEXTUAL_AVAILABLE = False
_RICH_AVAILABLE = False
_RICH_CONSOLE = None

try:
    import rich
    from rich.console import Console as RichConsole
    from rich.panel import Panel
    from rich.table import Table as RichTable
    from rich.text import Text as RichText
    from rich.box import Box, HEAVY, ROUNDED, SIMPLE
    _RICH_AVAILABLE = True
    _RICH_CONSOLE = RichConsole(highlight=False)
except ImportError:
    pass

try:
    import textual
    _TEXTUAL_AVAILABLE = True
except ImportError:
    pass


def detect_backend() -> str:
    """自动检测可用后端: textual > rich > plain"""
    if _TEXTUAL_AVAILABLE:
        return "textual"
    if _RICH_AVAILABLE:
        return "rich"
    return "plain"


def _terminal_width() -> int:
    """检测终端宽度，默认 80"""
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return 80


def _supports_emoji() -> bool:
    """检测终端是否支持 emoji"""
    term = os.environ.get("TERM", "")
    if term in ("dumb", "vt52"):
        return False
    if os.environ.get("NO_EMOJI"):
        return False
    return True


# ═══════════════════════════════════════════════════════════════
# 组件规格 (Specs)
# ═══════════════════════════════════════════════════════════════

@dataclass
class CardSpec:
    """Card 组件规格"""
    title: str
    icon: str = ""
    fields: List[Tuple[str, Any]] = field(default_factory=list)
    footer: str = ""
    color: str = "primary"

@dataclass
class TableSpec:
    """Table 组件规格"""
    headers: List[str] = field(default_factory=list)
    rows: List[List[Any]] = field(default_factory=list)
    title: str = ""
    color: str = "primary"

@dataclass
class BarChartSpec:
    """BarChart 组件规格"""
    data: List[Tuple[str, float, float]] = field(default_factory=list)  # (label, value, max)
    width: int = 20
    colors: List[str] = field(default_factory=list)  # color key names

@dataclass
class StatusSpec:
    """Status 组件规格"""
    ok: bool
    message: str
    detail: str = ""

@dataclass
class SectionSpec:
    """Section 组件规格"""
    title: str
    icon: str = ""
    subtitle: str = ""

@dataclass
class ListSpec:
    """List 组件规格"""
    items: List[str] = field(default_factory=list)
    icon: str = "info"
    numbered: bool = False


# ═══════════════════════════════════════════════════════════════
# Plain 后端
# ═══════════════════════════════════════════════════════════════

class PlainRenderer:
    """纯 ANSI 渲染器 — 零依赖"""

    @staticmethod
    def _ansi(code: int, text: str) -> str:
        return f"\033[{code}m{text}\033[0m"

    @staticmethod
    def _color_ansi(hex_color: str, text: str) -> str:
        ansi = ANSI256.get(hex_color, 249)
        return f"\033[38;5;{ansi}m{text}\033[0m"

    @staticmethod
    def _icon(key: str) -> str:
        if _supports_emoji():
            return ICONS.get(key, "")
        return PLAIN_ICONS.get(key, key.upper())

    def _box_width(self) -> int:
        w = _terminal_width()
        return min(w - 4, 74)

    def card(self, spec: CardSpec) -> str:
        width = self._box_width()
        icon = self._icon(spec.icon or "info")
        title = f"{icon} {spec.title}" if icon else spec.title
        # 截断标题
        max_title = width - 4
        if len(title) > max_title:
            title = title[:max_title - 1] + "…"

        lines = []
        # 顶边
        top = f"  ┌─ {title} " + "─" * max(0, width - len(title) - 3)
        lines.append(self._color_ansi(COLORS.get(spec.color, "#00D2A0"), top))

        # 字段
        for key, value in spec.fields:
            val_str = str(value)
            if len(val_str) > width - 24:
                val_str = val_str[:width - 27] + "…"
            lines.append(f"  │  {key:20s}  {val_str}")

        # 底边
        if spec.footer:
            footer_text = spec.footer[:width - 4]
            lines.append(f"  │  {self._color_ansi(COLORS['muted'], footer_text)}")

        bottom = f"  └" + "─" * (width + 1)
        lines.append(self._color_ansi(COLORS.get(spec.color, "#00D2A0"), bottom))
        return "\n".join(lines)

    def table(self, spec: TableSpec) -> str:
        if not spec.rows:
            return self._color_ansi(COLORS["muted"], "  (无数据)")

        width = self._box_width()
        ncols = len(spec.headers) if spec.headers else len(spec.rows[0])
        col_width = max(8, (width - ncols * 3) // ncols)

        lines = []
        # 标题
        if spec.title:
            lines.append(f"  {spec.title}")
            lines.append(f"  {'─' * width}")

        # 表头
        header_parts = []
        for h in spec.headers[:ncols]:
            hdr = h[:col_width].ljust(col_width)
            header_parts.append(self._color_ansi(COLORS.get(spec.color, "#4A90D9"),
                                                  f"\033[1m{hdr}\033[0m"))
        if header_parts:
            lines.append("  " + " │ ".join(header_parts))
            lines.append("  " + "─" * (col_width) + "─┼─" + "─" * (col_width) if ncols == 2
                         else "  " + "─" * (col_width * ncols + (ncols - 1) * 3))

        # 数据行
        for row in spec.rows:
            parts = []
            for cell in row[:ncols]:
                cell_str = str(cell)[:col_width].ljust(col_width)
                parts.append(cell_str)
            lines.append("  " + " │ ".join(parts))

        return "\n".join(lines)

    def bar_chart(self, spec: BarChartSpec) -> str:
        lines = []
        colors = spec.colors if spec.colors else ["primary"] * len(spec.data)

        for i, (label, value, max_val) in enumerate(spec.data):
            ratio = value / max(max_val, 1)
            filled = int(ratio * spec.width)
            bar = "█" * filled + "·" * (spec.width - filled)
            color_key = colors[i % len(colors)]
            hex_color = COLORS.get(color_key, COLORS["primary"])
            bar_colored = self._color_ansi(hex_color, bar)
            pct = f"{ratio:.0%}"
            lines.append(f"  {label:12s}  {bar_colored}  {pct:>4s}")

        return "\n".join(lines)

    def status(self, spec: StatusSpec) -> str:
        icon = self._icon("success" if spec.ok else "error")
        msg = f"{icon} {spec.message}"
        if spec.detail:
            msg += f"  {self._color_ansi(COLORS['muted'], spec.detail)}"
        if spec.ok:
            return self._color_ansi(COLORS["success"], msg)
        return self._color_ansi(COLORS["error"], msg)

    def section(self, spec: SectionSpec) -> str:
        icon = self._icon(spec.icon or "info")
        title = f"{icon} {spec.title}" if icon else spec.title
        if spec.subtitle:
            title += f"  —  {spec.subtitle}"
        width = self._box_width()
        lines = [
            "",
            self._color_ansi(COLORS["primary"], f"  {title}"),
            self._color_ansi(COLORS["primary"], f"  {'═' * min(len(title) + 2, width)}"),
            "",
        ]
        return "\n".join(lines)

    def list(self, spec: ListSpec) -> str:
        if not spec.items:
            return f"  {self._icon('empty')} (无内容)"

        lines = []
        for i, item in enumerate(spec.items):
            if spec.numbered:
                prefix = f"  {i+1:2d}."
            else:
                prefix = f"  {self._icon(spec.icon)}"
            lines.append(f"{prefix} {item}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Rich 后端
# ═══════════════════════════════════════════════════════════════

class RichRenderer:
    """Rich 渲染器"""

    def __init__(self):
        self._console = _RICH_CONSOLE or RichConsole(highlight=False)

    def card(self, spec: CardSpec) -> str:
        icon = ICONS.get(spec.icon or "info", "")
        title = f"{icon} {spec.title}" if icon else spec.title

        text = RichText()
        for key, value in spec.fields:
            text.append(f"{key}: ", style="bold")
            text.append(f"{value}\n")

        if spec.footer:
            text.append(spec.footer, style="dim")

        color = COLORS.get(spec.color, "green")
        panel = Panel(text, title=title, border_style=color, box=ROUNDED,
                      padding=(0, 2))
        return self._capture(panel)

    def table(self, spec: TableSpec) -> str:
        color = COLORS.get(spec.color, "blue")
        table = RichTable(title=spec.title or None, border_style=color,
                          box=SIMPLE, show_header=True, header_style="bold")

        for h in spec.headers:
            table.add_column(h)
        for row in spec.rows:
            table.add_row(*[str(c) for c in row])

        return self._capture(table)

    def bar_chart(self, spec: BarChartSpec) -> str:
        lines = []
        colors = spec.colors if spec.colors else ["primary"] * len(spec.data)

        for i, (label, value, max_val) in enumerate(spec.data):
            ratio = value / max(max_val, 1)
            filled = int(ratio * spec.width)
            bar = "█" * filled + "░" * (spec.width - filled)
            color_key = colors[i % len(colors)]
            hex_color = COLORS.get(color_key, COLORS["primary"])
            pct = f"{ratio:.0%}"
            lines.append(f"  {label:12s}  [{hex_color}]{bar}[/{hex_color}]  {pct:>4s}")

        return "\n".join(lines)

    def status(self, spec: StatusSpec) -> str:
        icon = ICONS.get("success" if spec.ok else "error", "")
        color = COLORS["success"] if spec.ok else COLORS["error"]
        msg = f"[{color}]{icon} {spec.message}[/{color}]"
        if spec.detail:
            msg += f"  [dim]{spec.detail}[/dim]"
        return msg

    def section(self, spec: SectionSpec) -> str:
        icon = ICONS.get(spec.icon or "info", "")
        title = f"{icon} {spec.title}" if icon else spec.title
        if spec.subtitle:
            title += f"  —  {spec.subtitle}"
        return f"\n[bold {COLORS['primary']}]{title}[/bold {COLORS['primary']}]\n"

    def list(self, spec: ListSpec) -> str:
        if not spec.items:
            return f"  [dim](无内容)[/dim]"

        lines = []
        icon = ICONS.get(spec.icon, "")
        for i, item in enumerate(spec.items):
            prefix = f"  {i+1:2d}." if spec.numbered else f"  {icon}"
            lines.append(f"{prefix} {item}")
        return "\n".join(lines)

    def _capture(self, renderable) -> str:
        """将 Rich renderable 捕获为字符串"""
        with self._console.capture() as capture:
            self._console.print(renderable)
        return capture.get().rstrip()


# ═══════════════════════════════════════════════════════════════
# RenderEngine — 统一入口
# ═══════════════════════════════════════════════════════════════

class RenderEngine:
    """统一渲染引擎 — 自动选择最佳后端

    用法:
        r = RenderEngine()
        print(r.card(CardSpec(...)))   # 返回字符串
        r.render(CardSpec(...))        # 直接输出到终端
    """

    def __init__(self, backend: Optional[str] = None, force_plain: bool = False):
        """
        Args:
            backend: "textual" | "rich" | "plain" | None (自动检测)
            force_plain: 强制使用 Plain (用于测试/管道)
        """
        if force_plain:
            self._backend = "plain"
        else:
            self._backend = backend or detect_backend()
        self._plain = PlainRenderer()
        self._rich: Any = None
        if self._backend == "rich" and _RICH_AVAILABLE:
            self._rich = RichRenderer()

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def is_rich(self) -> bool:
        return self._backend == "rich"

    @property
    def is_plain(self) -> bool:
        return self._backend == "plain"

    # ── 组件 ──

    def card(self, spec: CardSpec) -> str:
        if self._rich:
            return self._rich.card(spec)
        return self._plain.card(spec)

    def table(self, spec: TableSpec) -> str:
        if self._rich:
            return self._rich.table(spec)
        return self._plain.table(spec)

    def bar_chart(self, spec: BarChartSpec) -> str:
        if self._rich:
            return self._rich.bar_chart(spec)
        return self._plain.bar_chart(spec)

    def status(self, spec: StatusSpec) -> str:
        if self._rich:
            return self._rich.status(spec)
        return self._plain.status(spec)

    def section(self, spec: SectionSpec) -> str:
        if self._rich:
            return self._rich.section(spec)
        return self._plain.section(spec)

    def list(self, spec: ListSpec) -> str:
        if self._rich:
            return self._rich.list(spec)
        return self._plain.list(spec)

    # ── 复合渲染 ──

    def render(self, *specs) -> None:
        """渲染多个 spec 到终端 (自动打印)"""
        output = "\n".join(self._render_spec(s) for s in specs if s is not None)
        if output.strip():
            print(output)

    def _render_spec(self, spec) -> str:
        if isinstance(spec, CardSpec):
            return self.card(spec)
        elif isinstance(spec, TableSpec):
            return self.table(spec)
        elif isinstance(spec, BarChartSpec):
            return self.bar_chart(spec)
        elif isinstance(spec, StatusSpec):
            return self.status(spec)
        elif isinstance(spec, SectionSpec):
            return self.section(spec)
        elif isinstance(spec, ListSpec):
            return self.list(spec)
        elif isinstance(spec, str):
            return spec
        return str(spec)


# ═══════════════════════════════════════════════════════════════
# 简洁 API — 直接打印，无需 Spec 对象
# ═══════════════════════════════════════════════════════════════

# 全局渲染器 (单例，自动检测后端)
_r: Optional[RenderEngine] = None

def _eng() -> RenderEngine:
    global _r
    if _r is None:
        _r = RenderEngine()
    return _r


# ── 直接打印 (返回 None，副作用是输出到终端) ──

def card(title: str, fields=None, icon: str = "info", footer: str = "",
         color: str = "primary") -> None:
    """打印 Card
    
    card("技能详情", [("名称", "tsx"), ("版本", "4.22.4")])
    card("安装完成", icon="success", color="success")
    """
    print(_eng().card(CardSpec(title=title, icon=icon, fields=fields or [],
                                footer=footer, color=color)))


def table(headers: list, rows: list, title: str = "", color: str = "primary") -> None:
    """打印表格
    
    table(["技能", "等级"], [["tsx", "JOURNEYMAN"], ["vite", "NOVICE"]])
    """
    print(_eng().table(TableSpec(headers=headers, rows=rows,
                                  title=title, color=color)))


def bar(data: list, width: int = 20, colors: list = None) -> None:
    """打印条形图
    
    bar([("熟练度", 42, 100), ("稳定性", 65, 100)])
    """
    colors = colors or ["primary"] * len(data)
    print(_eng().bar_chart(BarChartSpec(data=data, width=width, colors=colors)))


def ok(message: str, detail: str = "") -> None:
    """打印成功状态
    
    ok("技能已安装", "npx-tsx v4.22.4")
    """
    print(_eng().status(StatusSpec(ok=True, message=message, detail=detail)))


def fail(message: str, detail: str = "") -> None:
    """打印失败状态"""
    print(_eng().status(StatusSpec(ok=False, message=message, detail=detail)))


def section(title: str, icon: str = "", subtitle: str = "") -> None:
    """打印区块标题
    
    section("技能管理", icon="dashboard", subtitle="Phase E")
    """
    print(_eng().section(SectionSpec(title=title, icon=icon, subtitle=subtitle)))


def li(items: list, icon: str = "info", numbered: bool = False) -> None:
    """打印列表
    
    li(["记忆管理", "禅思反思", "GTD 任务"], icon="memory")
    """
    print(_eng().list(ListSpec(items=items, icon=icon, numbered=numbered)))


# ── 链式打印: p.card(...).table(...).ok(...) ──

class _Printer:
    """链式渲染器 — 支持连续调用
    
    from zenskill.render import p
    p.card("技能", fields).table(headers, rows).ok("完成")
    """
    def card(self, *a, **kw) -> "_Printer": card(*a, **kw); return self
    def table(self, *a, **kw) -> "_Printer": table(*a, **kw); return self
    def bar(self, *a, **kw) -> "_Printer": bar(*a, **kw); return self
    def ok(self, *a, **kw) -> "_Printer": ok(*a, **kw); return self
    def fail(self, *a, **kw) -> "_Printer": fail(*a, **kw); return self
    def section(self, *a, **kw) -> "_Printer": section(*a, **kw); return self
    def li(self, *a, **kw) -> "_Printer": li(*a, **kw); return self

p = _Printer()
"""链式渲染器

用法:
    from zenskill.render import p
    p.section("技能管理", icon="📦")
     .card("技能", fields)
     .ok("完成")
"""


# ── Toast 通知 (U1A) ──

def toast(message: str, ok: bool = True, duration: float = 3.0) -> None:
    """显示自动消失的 Toast 通知

    toast("安装完成", ok=True)
    toast("连接失败", ok=False, duration=5)
    """
    import time
    import threading

    msg = _eng().status(StatusSpec(ok=ok, message=message, detail=""))
    print(f"\n  {msg}")

    def _clear():
        time.sleep(duration)
        sys.stdout.write("\r\033[K\033[F\033[K")
        sys.stdout.flush()

    threading.Thread(target=_clear, daemon=True).start()


# ── 字符串版本 (返回字符串，用于 --json 降级等场景) ──

def get_renderer(force_plain: bool = False) -> RenderEngine:
    """获取全局 RenderEngine 实例 (返回字符串的场景使用)"""
    return _eng()
