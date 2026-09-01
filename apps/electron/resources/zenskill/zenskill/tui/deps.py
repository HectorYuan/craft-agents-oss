"""
TUI 依赖检测 + 一键安装 (Phase T6, 迁移更新)

用法:
    from zenskill.tui.deps import check_deps, prompt_install

    deps = check_deps()
    # {"rich_app": True, "rich": True, "textual": False, "plain": True}

    if not deps["rich"]:
        prompt_install()
"""

from __future__ import annotations

import subprocess
import sys
from typing import Dict, Optional


def check_deps() -> Dict[str, bool]:
    """检测 TUI 依赖可用性"""
    deps = {"plain": True}  # Plain 永远可用

    try:
        import rich
        deps["rich"] = True
    except ImportError:
        deps["rich"] = False

    try:
        import prompt_toolkit
        deps["prompt_toolkit"] = True
    except ImportError:
        deps["prompt_toolkit"] = False

    # Rich App 需要 rich + prompt_toolkit
    deps["rich_app"] = deps["rich"] and deps.get("prompt_toolkit", False)

    try:
        import textual
        deps["textual"] = True
    except ImportError:
        deps["textual"] = False

    return deps


def get_best_mode(deps: Dict[str, bool]) -> str:
    """根据可用依赖返回最佳模式

    优先级: rich_app > textual > rich > plain
    """
    if deps.get("rich_app"):
        return "rich"
    if deps.get("textual"):
        return "textual"
    if deps.get("rich"):
        return "rich"
    return "plain"


def get_missing(deps: Dict[str, bool]) -> list:
    """返回缺失的推荐依赖列表"""
    missing = []
    if not deps.get("rich"):
        missing.append("rich")
    if not deps.get("prompt_toolkit"):
        missing.append("prompt_toolkit")
    return missing


def install_dep(package: str) -> bool:
    """pip install 一个包

    Returns:
        True 如果安装成功
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package],
            capture_output=True, text=True, timeout=60,
        )
        return result.returncode == 0
    except Exception:
        return False


def install_all_deps() -> Dict[str, bool]:
    """一键安装推荐的 TUI 依赖 (rich + prompt_toolkit)"""
    results = {}
    for pkg in ["rich", "prompt_toolkit"]:
        results[pkg] = install_dep(pkg)
    return results


def render_dep_status(deps: Dict[str, bool], rich_available: bool = False) -> str:
    """渲染依赖状态面板

    Args:
        deps: check_deps() 返回值
        rich_available: 当前是否能用 Rich 渲染

    Returns:
        格式化的依赖状态字符串
    """
    if rich_available:
        return _render_rich(deps)
    return _render_plain(deps)


def _render_plain(deps: Dict[str, bool]) -> str:
    """Plain ANSI 渲染"""
    from zenskill.render import PlainRenderer as R

    lines = []
    for name, label in [
        ("rich_app", "Rich App (推荐)"),
        ("textual", "Textual (全功能)"),
        ("rich", "Rich (命令)"),
        ("plain", "Plain (基础)"),
    ]:
        ok = deps.get(name, False)
        icon = R._icon("success" if ok else "error")
        lines.append(f"  {icon} {label:22s} {'✅ 已安装' if ok else '❌ 未安装'}")

    lines.append("")

    if not deps.get("rich_app"):
        cmd = "pip install rich prompt_toolkit"
        lines.append(f"  💡 推荐: {cmd}")

    lines.append("")
    return "\n".join(lines)


def _render_rich(deps: Dict[str, bool]) -> str:
    """Rich 渲染"""
    lines = []
    for name, label in [
        ("rich_app", "Rich App (推荐)"),
        ("textual", "Textual (全功能)"),
        ("rich", "Rich (命令)"),
        ("plain", "Plain (基础)"),
    ]:
        ok = deps.get(name, False)
        icon = "✅" if ok else "❌"
        status = "[green]已安装[/green]" if ok else "[red]未安装[/red]"
        lines.append(f"  {icon} {label:22s} {status}")

    lines.append("")

    if not deps.get("rich_app"):
        lines.append("  [yellow]💡 推荐: pip install rich prompt_toolkit[/yellow]")

    lines.append("")
    return "\n".join(lines)


def prompt_install_interactive() -> Optional[str]:
    """交互式依赖安装提示

    Returns:
        用户选择的模式: "rich" | "textual" | "plain" | None(退出)
    """
    deps = check_deps()

    # 如果 Rich App 可用，直接返回
    if deps["rich_app"]:
        return "rich"

    print()
    print(render_dep_status(deps, rich_available=deps["rich"]))
    print("  选择:")
    if not deps["rich_app"]:
        print("  [r] 安装 Rich + prompt_toolkit (推荐)")
    if not deps["textual"]:
        print("  [t] 安装 Textual (旧模式)")
    print("  [p] 使用 Plain 模式 (无需安装)")
    print("  [q] 退出")

    try:
        choice = input("\n  选择 > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None

    if choice == "r":
        print("  ⏳ 安装 Rich + prompt_toolkit...")
        ok_rich = install_dep("rich") if not deps["rich"] else True
        ok_pt = install_dep("prompt_toolkit") if not deps.get("prompt_toolkit") else True
        if ok_rich and ok_pt:
            print("  ✅ 安装成功!")
            return "rich"
        else:
            print("  ❌ 部分安装失败，请手动: pip install rich prompt_toolkit")
            return "plain"

    if choice == "t" and not deps["textual"]:
        print("  ⏳ 安装 Textual...")
        if install_dep("textual"):
            print("  ✅ Textual 安装成功!")
            return "textual"
        else:
            print("  ❌ 安装失败，请手动: pip install textual")
            return "plain"

    if choice == "p":
        return "plain"

    return None
