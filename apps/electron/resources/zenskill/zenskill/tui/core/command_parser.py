"""统一命令解析器 -- TUI/CLI 两入口一致。

命令格式: /resource action [args...]
示例:
    /dashboard          -> resource=dashboard, action=show
    /skills list        -> resource=skills, action=list
    /growth report      -> resource=growth, action=report
    /d                  -> resource=dashboard, action=show  (别名)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


# ── 别名映射 ──────────────────────────────────────────────────

ALIASES = {
    "d": ("dashboard", "show"),
    "c": ("chat", "show"),
    "g": ("growth", "show"),
    "s": ("skills", "list"),
    "m": ("mirror", "show"),
    "k": ("knowledge", "show"),
    "h": ("help", "show"),
    "q": ("quit", ""),
    "?": ("help", "show"),
}

DEFAULT_ACTIONS = {
    "dashboard": "show",
    "chat": "show",
    "growth": "show",
    "skills": "list",
    "mirror": "show",
    "knowledge": "show",
    "system": "show",
    "doctor": "run",
    "llm": "list",
    "help": "show",
    "quit": "",
    "clear": "",
    "version": "show",
}

ACTION_ALIASES = {
    "ls": "list",
    "info": "show",
    "detail": "show",
    "rm": "delete",
    "del": "delete",
    "?": "help",
}


@dataclass
class ParsedCommand:
    """解析后的命令。"""

    resource: str
    action: str
    args: List[str] = field(default_factory=list)
    raw: str = ""

    @property
    def is_valid(self) -> bool:
        return bool(self.resource)

    @property
    def is_nav(self) -> bool:
        """是否为页面导航命令。"""
        return self.resource in (
            "dashboard", "chat", "growth", "mirror",
            "knowledge", "system", "doctor", "llm",
        ) and self.action in ("show", "run")

    def __str__(self) -> str:
        parts = [self.resource, self.action]
        parts.extend(self.args)
        return " ".join(p for p in parts if p)


def parse_command(input: str) -> ParsedCommand:
    """统一命令解析。

    >>> parse_command("/dashboard")
    ParsedCommand(resource='dashboard', action='show', args=[])
    >>> parse_command("/skills list")
    ParsedCommand(resource='skills', action='list', args=[])
    >>> parse_command("/d")
    ParsedCommand(resource='dashboard', action='show', args=[])
    """
    raw = input.strip()
    if raw.startswith("/"):
        raw = raw[1:]
    if not raw:
        return ParsedCommand(resource="", action="", raw=input)

    parts = raw.split()
    if not parts:
        return ParsedCommand(resource="", action="", raw=input)

    # 单词别名: /d -> dashboard show
    if len(parts) == 1 and parts[0] in ALIASES:
        resource, action = ALIASES[parts[0]]
        return ParsedCommand(resource=resource, action=action, raw=input)

    resource = parts[0]

    # 单词无 action: /dashboard -> dashboard show
    if len(parts) == 1:
        action = DEFAULT_ACTIONS.get(resource, "show")
        return ParsedCommand(resource=resource, action=action, raw=input)

    # 有 action
    action = parts[1]
    action = ACTION_ALIASES.get(action, action)
    args = parts[2:]

    return ParsedCommand(resource=resource, action=action, args=args, raw=input)


def is_command(input: str) -> bool:
    """判断输入是否为斜杠命令。"""
    return input.strip().startswith("/")


def classify_input(input: str) -> str:
    """分类用户输入。

    Returns:
        "command"   -- / 开头的斜杠命令
        "file_ref"  -- @ 开头的文件引用
        "chat"      -- 普通对话
    """
    stripped = input.strip()
    if stripped.startswith("/"):
        return "command"
    if stripped.startswith("@"):
        return "file_ref"
    return "chat"


def extract_at_references(input: str) -> tuple[str, List[str]]:
    """提取 @ 文件引用。

    Returns:
        (清理后的文本, 文件路径列表)
    """
    refs = re.findall(r"@(\S+)", input)
    cleaned = re.sub(r"@\S+", "", input).strip()
    return cleaned, refs
