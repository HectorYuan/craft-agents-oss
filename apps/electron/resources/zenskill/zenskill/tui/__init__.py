"""
ZenSkill TUI - 终端图形界面

提供四种模式 (自动降级):
- Rich App (Rich + prompt_toolkit): 推荐，流式对话 + 命令补全
- 交互模式 (Textual): 全功能终端UI，命令面板、鼠标支持 (需额外安装)
- 命令模式 (Rich): 轻量即时渲染，单字符快捷键
- Plain 模式: 零依赖，数字菜单

用法:
    from zenskill.tui import get_available_modes, get_best_tui
    TUIClass = get_best_tui()
"""

__all__ = [
    "ZenRichTUI", "CommandMode", "PlainTUI",
    "get_available_modes", "get_best_tui",
]

# 惰性导入 -- 不在此处 import textual/rich
# 各子模块独立处理自己的依赖

def get_available_modes() -> dict:
    """返回可用的 TUI 模式"""
    modes = {}
    try:
        from .plain_mode import PlainTUI
        modes["plain"] = PlainTUI
    except ImportError:
        pass
    try:
        from .command_mode import CommandMode
        modes["rich_fallback"] = CommandMode
    except ImportError:
        pass
    try:
        from .rich_app import ZenRichTUI
        modes["rich"] = ZenRichTUI
    except ImportError:
        pass
    return modes


def get_best_tui():
    """返回最佳可用 TUI 类。

    优先级: rich (Rich+prompt_toolkit) > rich_fallback (CommandMode) > plain
    """
    modes = get_available_modes()
    for key in ("rich", "rich_fallback", "plain"):
        if key in modes:
            return modes[key]
    raise ImportError("No TUI backend available")


# 兼容旧代码的惰性导入
def __getattr__(name):
    if name == "ZenRichTUI":
        from .rich_app import ZenRichTUI
        return ZenRichTUI
    if name == "CommandMode":
        from .command_mode import CommandMode
        return CommandMode
    if name == "PlainTUI":
        from .plain_mode import PlainTUI
        return PlainTUI
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
