"""
ZenSkill - ZenLoop 禅思循环系统
"""

from .loop_base import (
    LoopType,
    LoopResult,
    ZenLoopPlugin,
)

from .loops import (
    ReflectionLoop,
    ConsolidationLoop,
    InsightLoop,
    PurificationLoop,
)

from .zenloop_system import (
    ZenLoopSystem,
)

__all__ = [
    # loop_base
    "LoopType",
    "LoopResult",
    "ZenLoopPlugin",
    
    # loops
    "ReflectionLoop",
    "ConsolidationLoop",
    "InsightLoop",
    "PurificationLoop",
    
    # zenloop_system
    "ZenLoopSystem",
]
