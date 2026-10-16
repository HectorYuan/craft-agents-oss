"""GTD observer 容器（S2 反向桥接）。

所有 GTD 状态变更通过 emit_gtd_event() 派发；observer 列表在模块级
共享（ActionEngine/InboxEngine/ProjectEngine 临时构造的实例也共享）。
仅 server mode 路径（`ws_server._on_startup`）注册，CLI 模式不注册。

防递归：emit 栈深度 > 1 直接 return（防御 GTD 内部 _create_next_repeat
等自身再次 fire）。
"""
import threading
from dataclasses import dataclass, asdict
from typing import Callable, Optional


@dataclass
class GtdObserverPayload:
    """GTD 状态变更事件 payload（独立命名空间，与 vendor SESSION_PERSISTENT_FIELDS 无关）。"""
    eventType: str          # 固定 "GtdEntityChanged"
    entityType: str         # "action" / "inbox" / "project"
    entityId: str
    previousStatus: str     # 变化前状态（"pending"/"done"/"archived" 等）
    newStatus: str          # 变化后状态
    sourceSessionId: str    # GTDAction.source_session_id（可能为空字符串）
    completedAt: Optional[str]  # 仅 done 时非空
    title: str              # 实体标题（human-readable）

    def to_dict(self) -> dict:
        return asdict(self)


# 模块级 observer list：所有 GTD 引擎实例（临时 + 持久）共享
_observers: list[Callable[[GtdObserverPayload], None]] = []
_emit_lock = threading.local()


def register_gtd_observer(cb: Callable[[GtdObserverPayload], None]) -> None:
    """注册 GTD 事件 observer（重复注册自动去重）。"""
    if cb not in _observers:
        _observers.append(cb)


def unregister_gtd_observer(cb: Callable) -> None:
    """取消注册 observer。"""
    if cb in _observers:
        _observers.remove(cb)


def clear_gtd_observers() -> None:
    """测试用：清空所有 observer（仅测试 fixture 调用，生产代码不应使用）。"""
    _observers.clear()


def emit_gtd_event(payload: GtdObserverPayload) -> None:
    """派发 GTD 事件到所有 observer。

    防递归：同线程内嵌套 emit（深度 > 0）直接吞。
    单 observer 异常不阻断其他 observer 执行。
    """
    depth = getattr(_emit_lock, "depth", 0)
    if depth > 0:
        return
    _emit_lock.depth = depth + 1
    try:
        # 拷贝防回调内 unregister 触发 mod-during-iter
        for cb in list(_observers):
            try:
                cb(payload)
            except Exception:
                # 单 observer 失败不阻断其他 observer，也不污染 GTD 写路径
                pass
    finally:
        _emit_lock.depth = 0
