"""
ZenSkill TUI - 终端图形界面

提供两种模式 (自动降级):
- Rich App (Rich + prompt_toolkit): 推荐主模式，16 页面 + 192 命令 +
  流式对话 + 命令补全。完整体验以本模式为准。
- Plain 模式: 零依赖兜底（rich 不可用时自动落入），仅 6 个基础页面的
  查览 + 对话入口，不含 rich 模式的页面与命令面，功能不再对等扩展。

用法:
    from zenskill.tui import get_available_modes, get_best_tui
    TUIClass = get_best_tui()
"""

__all__ = [
    "ZenRichTUI", "PlainTUI",
    "get_available_modes", "get_best_tui",
]


def get_available_modes() -> dict:
    """返回可用的 TUI 模式"""
    modes = {}
    try:
        from .rich_app import ZenRichTUI
        modes["rich"] = ZenRichTUI
    except ImportError:
        pass
    try:
        from .plain_mode import PlainTUI
        modes["plain"] = PlainTUI
    except ImportError:
        pass
    return modes


def get_best_tui():
    """返回最佳可用 TUI 类。

    优先级: rich (Rich+prompt_toolkit) > plain
    """
    modes = get_available_modes()
    for key in ("rich", "plain"):
        if key in modes:
            return modes[key]
    raise ImportError("No TUI backend available")


# 兼容旧代码的惰性导入
def __getattr__(name):
    if name == "ZenRichTUI":
        from .rich_app import ZenRichTUI
        return ZenRichTUI
    if name == "PlainTUI":
        from .plain_mode import PlainTUI
        return PlainTUI
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
