"""
统一键盘输入处理 (Phase T4)

支持方向键导航 + 快捷键，跨 Rich/Plain 两种模式共用。

用法:
    from zenskill.tui.keyboard import read_key, Key

    key = read_key()  # 阻塞等待按键
    if key == Key.UP:
        ...
"""

from __future__ import annotations

import sys
import os
from enum import Enum


class Key(Enum):
    """统一按键定义"""
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    ENTER = "enter"
    ESC = "esc"
    TAB = "tab"
    BACKSPACE = "backspace"
    SPACE = "space"
    HOME = "home"
    END = "end"
    PAGE_UP = "page_up"
    PAGE_DOWN = "page_down"

    # 数字
    N1 = "1"; N2 = "2"; N3 = "3"; N4 = "4"
    N5 = "5"; N6 = "6"; N7 = "7"; N8 = "8"

    # 字母
    Q = "q"; R = "r"; B = "b"; J = "j"; K = "k"
    H = "h"; L = "l"; C = "c"; S = "s"
    D = "d"; G = "g"; M = "m"; T = "t"
    I = "i"; F = "f"; X = "x"
    SLASH = "/"; QUESTION = "?"
    SPACE_CHAR = " "


# ── ANSI 转义序列 → Key 映射 ──
_ANSI_MAP = {
    "\x1b[A": Key.UP,
    "\x1b[B": Key.DOWN,
    "\x1b[C": Key.RIGHT,
    "\x1b[D": Key.LEFT,
    "\x1b[H": Key.HOME,
    "\x1b[F": Key.END,
    "\x1b[5~": Key.PAGE_UP,
    "\x1b[6~": Key.PAGE_DOWN,
    "\x1b[1~": Key.HOME,
    "\x1b[4~": Key.END,
    "\x1b[3~": Key.BACKSPACE,  # Delete key
    "\x1b": Key.ESC,
    "\t": Key.TAB,
    "\n": Key.ENTER,
    "\r": Key.ENTER,
    " ": Key.SPACE,
}

# ── 单字符 → Key 映射 ──
_CHAR_MAP = {
    "1": Key.N1, "2": Key.N2, "3": Key.N3, "4": Key.N4,
    "5": Key.N5, "6": Key.N6, "7": Key.N7, "8": Key.N8,
    "q": Key.Q, "Q": Key.Q,
    "r": Key.R, "R": Key.R,
    "b": Key.B, "B": Key.B,
    "j": Key.J, "J": Key.J,
    "k": Key.K, "K": Key.K,
    "h": Key.H, "H": Key.H,
    "l": Key.L, "L": Key.L,
    "c": Key.C, "C": Key.C,
    "s": Key.S, "S": Key.S,
    "d": Key.D, "D": Key.D,
    "g": Key.G, "G": Key.G,
    "m": Key.M, "M": Key.M,
    "t": Key.T, "T": Key.T,
    "i": Key.I, "I": Key.I,
    "f": Key.F, "F": Key.F,
    "x": Key.X, "X": Key.X,
    "/": Key.SLASH,
    "?": Key.QUESTION,
    " ": Key.SPACE_CHAR,
}


def read_key() -> Key:
    """读取单个按键（阻塞）

    自动识别:
    - 方向键 (ANSI escape 序列)
    - 单字符 (1-8, q, r, j, k, /, ?)
    - 回车

    跨平台兼容 (Linux/macOS/Windows)
    """
    ch = _getch()
    if not ch:
        return Key.ESC

    # ANSI 转义序列 (方向键等): ESC [ ...
    if ch == "\x1b":
        seq = ch
        # 读取后续字符 (非阻塞, 较长的超时确保方向键序列完整)
        while True:
            nxt = _getch(timeout=0.15)
            if nxt:
                seq += nxt
                if seq in _ANSI_MAP:
                    return _ANSI_MAP[seq]
                if len(seq) >= 8:
                    return Key.ESC
            else:
                return _ANSI_MAP.get(seq, Key.ESC)

    # 单字符
    if ch in _CHAR_MAP:
        return _CHAR_MAP[ch]

    if ch in ("\n", "\r"):
        return Key.ENTER

    return Key.ESC


def _getch(timeout: float = None) -> str:
    """读取单个字符（跨平台）"""
    try:
        if os.name == "nt":
            import msvcrt
            if timeout:
                import time
                start = time.time()
                while time.time() - start < timeout:
                    if msvcrt.kbhit():
                        return msvcrt.getch().decode("utf-8", errors="replace")
                    time.sleep(0.01)
                return ""
            return msvcrt.getch().decode("utf-8", errors="replace")
        else:
            import termios
            import tty
            import select

            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                if timeout:
                    r, _, _ = select.select([sys.stdin], [], [], timeout)
                    if not r:
                        return ""
                return sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        return ""


# ── Rich 集成 ──

def read_key_rich() -> Key:
    """Rich 环境下读取按键"""
    try:
        from rich import get_key as rich_get_key

        key_event = rich_get_key()
        key_name = key_event.key if hasattr(key_event, 'key') else str(key_event)

        # map Rich key names to our Key enum
        mapping = {
            "up": Key.UP, "down": Key.DOWN, "left": Key.LEFT, "right": Key.RIGHT,
            "enter": Key.ENTER, "escape": Key.ESC, "tab": Key.TAB,
            "backspace": Key.BACKSPACE, "space": Key.SPACE,
            "1": Key.N1, "2": Key.N2, "3": Key.N3, "4": Key.N4,
            "5": Key.N5, "6": Key.N6, "7": Key.N7, "8": Key.N8,
            "q": Key.Q, "Q": Key.Q, "r": Key.R, "R": Key.R,
            "j": Key.J, "k": Key.K, "h": Key.H, "l": Key.L,
            "/": Key.SLASH, "?": Key.QUESTION,
        }
        return mapping.get(key_name.lower(), Key.ENTER)
    except ImportError:
        return read_key()
