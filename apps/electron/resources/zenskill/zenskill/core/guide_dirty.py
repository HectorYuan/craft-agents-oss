"""guide.md 脏标记 — GTD 写操作后置脏，下次会话启动时才刷新。

替代"每次 create_session 无条件 spawn update_guide.py（1-3s CPU）"：
写工具执行后 touch 脏标记文件，会话创建链路检测到标记才执行刷新。

跨进程安全：创建用 os.open(O_CREAT|O_EXCL)——并发置脏时只有第一个
进程真正创建成功，其余静默跳过（存在即脏，语义等价）。

标记文件位置：~/.zenskill/guide_dirty（空文件，存在=脏）。
"""

from __future__ import annotations

import os
from pathlib import Path

GUIDE_DIRTY_FILENAME = "guide_dirty"


def guide_dirty_path() -> Path:
    """脏标记文件路径（~/.zenskill/guide_dirty）"""
    return Path.home() / ".zenskill" / GUIDE_DIRTY_FILENAME


def is_guide_dirty() -> bool:
    """guide.md 是否有未应用的变更"""
    return guide_dirty_path().exists()


def mark_guide_dirty() -> bool:
    """置脏。O_CREAT|O_EXCL 防竞态：已存在则跳过并返回 False。"""
    path = guide_dirty_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return False


def clear_guide_dirty() -> bool:
    """清除脏标记（刷新完成后调用）。不存在时返回 False。"""
    try:
        guide_dirty_path().unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False
