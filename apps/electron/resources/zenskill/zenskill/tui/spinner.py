"""
进度指示器 (Phase U0C)

对标 Claude Code spinner — Rich 模式用 Spinner，Plain 用 ASCII 旋转字符。

用法:
    from zenskill.tui.spinner import Spinner

    with Spinner("安装中..."):
        install_skill(...)

    # 或手动
    spinner = Spinner("加载中...", rich=True)
    spinner.start()
    do_work()
    spinner.stop("✅ 完成")
"""

from __future__ import annotations

import sys
import time
import threading
from typing import Optional


class Spinner:
    """终端旋转指示器

    Rich 模式:
        使用 rich.spinner.Spinner 或 rich.status
    Plain 模式:
        ASCII 旋转字符 + 手动刷新
    """

    FRAMES = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]

    def __init__(self, message: str = "", rich: bool = False):
        self.message = message
        self.rich = rich
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_idx = 0

    def start(self):
        """开始旋转"""
        self._running = True
        if self.rich:
            self._rich_start()
        else:
            self._plain_start()

    def stop(self, final_message: str = ""):
        """停止旋转，可选显示最终消息"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)

        # 清除当前行
        sys.stdout.write("\r\033[K")
        if final_message:
            sys.stdout.write(f"{final_message}\n")
        sys.stdout.flush()

    def _rich_start(self):
        """Rich 模式 — 使用 rich.status"""
        try:
            from rich.console import Console
            console = Console()
            self._rich_status = console.status(self.message, spinner="dots")
            self._rich_status.start()
        except Exception:
            self._plain_start()

    def _rich_stop(self):
        if hasattr(self, '_rich_status'):
            self._rich_status.stop()

    def _plain_start(self):
        """Plain 模式 — 后台线程旋转"""
        def spin():
            while self._running:
                frame = self.FRAMES[self._frame_idx % len(self.FRAMES)]
                self._frame_idx += 1
                sys.stdout.write(f"\r  {frame} {self.message}")
                sys.stdout.flush()
                time.sleep(0.1)
            # 清除行
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
        self._thread = threading.Thread(target=spin, daemon=True)
        self._thread.start()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


def with_spinner(message: str, rich: bool = False):
    """装饰器: 为函数添加旋转指示器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with Spinner(message, rich=rich):
                return func(*args, **kwargs)
        return wrapper
    return decorator
