"""
ViewModel 基类 — TUI 三端统一数据层 (Phase T1)

用法:
    from zenskill.tui.views import ViewModel
    from zenskill.tui.views.dashboard import DashboardVM

    vm = DashboardVM.load()
    print(vm.render_l1())  # Plain ANSI
    print(vm.render_l2())  # Rich
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ViewModel:
    """TUI 页面 ViewModel 基类

    每个页面一个 ViewModel 子类，负责:
    1. load() — 从 DB/DAO 拉取数据
    2. render_l1() — Plain ANSI 渲染 (返回字符串)
    3. render_l2() — Rich 渲染 (返回 Rich-text 字符串)
    4. render_l3() — Textual 渲染 (返回 Widget 数据，供 screens 使用)

    子类必须实现:
    - load()
    - render_l1()
    - render_l2()
    """

    title: str = ""
    icon: str = "📊"
    level: int = 1           # 数据丰富度: 1=基础 2=完整 3=全量
    error: str = ""           # 非空表示加载失败

    @classmethod
    def load(cls) -> "ViewModel":
        """从数据源加载 ViewModel"""
        raise NotImplementedError

    def render_l1(self) -> str:
        """Plain ANSI 渲染"""
        raise NotImplementedError

    def render_l2(self) -> str:
        """Rich 渲染"""
        # 默认回退到 L1
        return self.render_l1()

    def render(self, backend: str = "plain") -> str:
        """根据后端自动选择渲染方法"""
        if backend == "rich":
            return self.render_l2()
        return self.render_l1()

    @property
    def is_empty(self) -> bool:
        return bool(self.error)


# Registry
_REGISTRY: Dict[str, type] = {}

def register_viewmodel(name: str):
    """装饰器: 注册 ViewModel"""
    def dec(cls):
        _REGISTRY[name] = cls
        return cls
    return dec

def get_viewmodel(name: str) -> Optional[type]:
    return _REGISTRY.get(name)

def list_viewmodels() -> List[str]:
    return list(_REGISTRY.keys())

# 自动注册所有 ViewModel
from . import dashboard  # noqa
from . import growth     # noqa
from . import skills     # noqa
from . import memory     # noqa
from . import gtd        # noqa
from . import chat       # noqa
from . import insights   # noqa
from . import search     # noqa
from . import settings   # noqa
