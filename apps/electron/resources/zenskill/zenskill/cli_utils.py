"""
ZenSkill CLI 统一输出工具

提供框线、标题、条形图、状态指示等格式化函数，
所有 CLI 命令共享同一套视觉语言。

用法:
    from zenskill.cli_utils import section, box, bar_chart

    section("用户画像", "👤", phase="9B")
    with box("📊 数据采集"):
        print("│  事件总数: 514")
    print(bar_chart(42, 100, width=16))
"""

from typing import List, Optional, Callable, Any
import json
import sys
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════
# 区块标题
# ═══════════════════════════════════════════════════════════════════

def section(title: str, emoji: str = "", phase: str = "") -> None:
    """打印双线标题区块

    输出:
      🏷 标题行 — Phase X
      ══════════════════════════════════════
    """
    tag = f" — Phase {phase}" if phase else ""
    print()
    print(f"  {emoji} {title}{tag}")
    print(f"  {'═' * 62}")


def section_blank(title: str, emoji: str = "", phase: str = "") -> None:
    """打印标题 + 额外空行"""
    section(title, emoji, phase)
    print()


# ═══════════════════════════════════════════════════════════════════
# 框线卡片
# ═══════════════════════════════════════════════════════════════════

def box_header(title: str, emoji: str = "") -> str:
    """打印框线卡片头，返回 indent 前缀

    用法:
        indent = box_header("数据采集", "📊")
        # 手动打印内容行...
        box_footer()
    """
    print()
    line = f"  ┌─ {emoji} {title} " if emoji else f"  ┌─ {title} "
    line += "─" * max(0, 58 - len(line) + 1)
    print(line)
    return "  │  "


def box_footer() -> None:
    """打印框线卡片尾"""
    print(f"  └{'─' * 60}")


def box_item(text: str, indent: str = "  │  ") -> None:
    """打印框线内单行"""
    print(f"{indent}{text}")


def box_kv(key: str, value, indent: str = "  │  ") -> None:
    """打印框线内键值对"""
    print(f"{indent}{key}: {value}")


# ═══════════════════════════════════════════════════════════════════
# 条形图
# ═══════════════════════════════════════════════════════════════════

def bar_chart(value: float, max_value: float, width: int = 16,
              fill: str = "█", empty: str = "·") -> str:
    """生成 ASCII 条形图

    >>> bar_chart(75, 100)
    '████████████····'
    """
    ratio = value / max(max_value, 1)
    n = min(int(ratio * width), width)
    return fill * n + empty * (width - n)


def bar_line(label: str, value: float, max_value: float,
             width: int = 16, indent: str = "  │  ") -> None:
    """打印带标签的条形图行

    输出:   上午 (6-12)     ████████········  42
    """
    bar = bar_chart(value, max_value, width)
    print(f"{indent}{label:16s} {bar} {value}")


# ═══════════════════════════════════════════════════════════════════
# 状态指示器
# ═══════════════════════════════════════════════════════════════════

def status_icon(ok: bool) -> str:
    """布尔 → 🟢/🔴"""
    return "🟢" if ok else "🔴"


def confidence_icon(conf: float) -> str:
    """置信度 → 颜色指示器"""
    if conf > 0.7:
        return "🟢"
    elif conf > 0.4:
        return "🟡"
    return "🔵"


def health_icon(ok_count: int, total: int) -> str:
    """健康度 → 🟢🟡🔴 + 文字"""
    if total == 0:
        return "⚪ 未知"
    ratio = ok_count / total
    if ratio >= 0.95:
        return "🟢 优秀"
    elif ratio >= 0.7:
        return "🟡 良好"
    return "🔴 需修复"


# ═══════════════════════════════════════════════════════════════════
# 紧凑列表
# ═══════════════════════════════════════════════════════════════════

def icon_list(items: List[str], indent: str = "  │  ",
              icons: Optional[List[str]] = None) -> None:
    """打印 emoji 图标链列表"""
    if icons is None:
        icons = ["🔹", "🔸", "🔹", "🔸", "🔹", "🔸"]
    for i, item in enumerate(items[:8]):
        icon = icons[i % len(icons)]
        print(f"{indent}{icon} {item}")
    if len(items) > 8:
        print(f"{indent}... 共 {len(items)} 项")


def truncated_dict(d: dict, top_n: int = 8, indent: str = "  │  ") -> None:
    """紧凑打印 dict（超过 top_n 截断）"""
    items = list(d.items())
    for k, v in items[:top_n]:
        if isinstance(v, float):
            print(f"{indent}  {k:25s}  {v:.1f}")
        else:
            print(f"{indent}  {k:25s}  {v}")
    if len(items) > top_n:
        print(f"{indent}  ... 共 {len(items)} 项")


# ═══════════════════════════════════════════════════════════════════
# 空状态 / 提示
# ═══════════════════════════════════════════════════════════════════

def empty_hint(text: str = "暂无数据，继续使用将自动生成") -> None:
    """空状态提示"""
    print(f"  │  [dim]{text}[/dim]")


def tip(text: str) -> None:
    """使用提示行"""
    print()
    print(f"  💡 {text}")


# ═══════════════════════════════════════════════════════════════════
# 时间解析
# ═══════════════════════════════════════════════════════════════════

def parse_since(since_str: Optional[str]) -> float:
    """解析 --since 参数为 Unix 时间戳

    支持格式:
        "2026-05-22T10:00:00"  ISO 格式
        "1h"  1 小时前
        "30m" 30 分钟前
        "1d"  1 天前
        "7d"  7 天前
    """
    if not since_str:
        return 0

    import re
    import time

    # 相对时间: 1h / 30m / 1d
    m = re.match(r"^(\d+)\s*(h|m|d|s)$", since_str.strip())
    if m:
        num = int(m.group(1))
        unit = m.group(2)
        seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
        return time.time() - num * seconds

    # ISO 时间
    try:
        from datetime import datetime
        return datetime.fromisoformat(since_str).timestamp()
    except Exception:
        pass

    # 默认：全量
    return 0


# ═══════════════════════════════════════════════════════════════════
# 输出分流（--json / --output）
# ═══════════════════════════════════════════════════════════════════

def output(result: dict, args: Any, *, text: Callable[[], str] | None = None) -> None:
    """标准化输出：--json 时打印 JSON，否则调用 text() 回调

    用法:
        output({"skill_id": sid, "status": st}, args,
               text=lambda: f"技能: {sid}\n状态: {st}")
    """
    if getattr(args, 'json_output', False):
        print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
    elif text:
        print(text())


def write_output(content: str, args: Any) -> None:
    """--output/-o 时写文件，否则打印到 stdout

    用法:
        write_output(report_text, args)
    """
    path = getattr(args, 'output', None)
    if path:
        Path(path).write_text(content, encoding='utf-8')
        print(f"已写入: {path}")
    else:
        print(content)


def watch_loop(fn: Callable[[], Any], interval: float = 5.0,
               header: str = "") -> None:
    """实时轮询刷新（--watch 模式）

    用法:
        watch_loop(lambda: print_status(), interval=5)
    """
    import time
    try:
        if header:
            print(header)
        while True:
            fn()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n已停止监控")
