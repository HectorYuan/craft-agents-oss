"""项目指令加载（对标 Codex AGENTS.md / Claude CLAUDE.md）。

按优先级扫描工作区指令文件：AGENTS.md → ZENSKILL.md → CLAUDE.md。
存在则格式化为 <project-instructions> 块注入系统提示词。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

INSTRUCTION_FILES = ("AGENTS.md", "ZENSKILL.md", "CLAUDE.md")
MAX_INSTRUCTION_CHARS = 4000


def find_instruction_file(cwd: Optional[str] = None) -> Optional[Path]:
    """按优先级查找工作区的指令文件。"""
    root = Path(cwd or os.getcwd())
    for name in INSTRUCTION_FILES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def load_project_instructions(cwd: Optional[str] = None) -> Optional[str]:
    """加载项目指令，返回格式化文本块；无指令文件返回 None。"""
    path = find_instruction_file(cwd)
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text:
        return None
    if len(text) > MAX_INSTRUCTION_CHARS:
        text = text[:MAX_INSTRUCTION_CHARS] + "\n... (truncated)"
    return (
        "<project-instructions>\n"
        f"Project instructions from {path.name}:\n"
        f"{text}\n"
        "</project-instructions>"
    )
