"""ZenSkill Rich TUI -- Rich + prompt_toolkit 实现。

参照 AgentSwarm SwarmTUI 的 while(true) + yield 设计。
"""

from .app import ZenRichTUI, run_tui

__all__ = ["ZenRichTUI", "run_tui"]
