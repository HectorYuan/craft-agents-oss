"""Diff 视图页面 -- /diff 命令。

展示代码变更对比（unified diff）。自包含组件，仅依赖 rich 与标准库。
"""

from __future__ import annotations

import difflib
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

USAGE_HINT = "用法: /diff <file> 或通过 agent 工具调用"

_STYLE_HEADER = "bold grey50"
_STYLE_HUNK = "cyan"
_STYLE_ADD = "green"
_STYLE_DEL = "red"
_STYLE_CONTEXT = "grey50"


def render_diff_text(old: str, new: str, context_lines: int = 3) -> str:
    """用 difflib.unified_diff 生成 unified diff 文本。"""
    diff = difflib.unified_diff(
        old.splitlines(),
        new.splitlines(),
        fromfile="a",
        tofile="b",
        n=context_lines,
        lineterm="",
    )
    return "\n".join(diff)


class DiffPage:
    """Diff 视图页面。"""

    def __init__(self, console: Console, data=None):
        self.console = console
        self.data = data

    def render(self, file_path: str = "", old_text: str = "", new_text: str = "", **kwargs) -> None:
        """渲染 diff，显式参数优先于 data，kwargs 支持 context_lines。"""
        params = self._resolve_params(file_path, old_text, new_text)
        if not (params["file_path"] or params["old_text"] or params["new_text"]):
            self.console.print(Text(USAGE_HINT, style="dim"))
            return
        self._render_diff(params, self._resolve_context_lines(kwargs))

    def _resolve_params(self, file_path: str, old_text: str, new_text: str) -> dict:
        source: dict = {}
        if isinstance(self.data, dict):
            source = self.data
        elif self.data is not None:
            source = {key: getattr(self.data, key, "") for key in ("file_path", "old_text", "new_text")}

        params = {key: str(source.get(key) or "") for key in ("file_path", "old_text", "new_text")}
        for key, value in (("file_path", file_path), ("old_text", old_text), ("new_text", new_text)):
            if value:
                params[key] = value
        return params

    def _resolve_context_lines(self, kwargs: dict) -> int:
        value = kwargs.get("context_lines")
        if value is None and isinstance(self.data, dict):
            value = self.data.get("context_lines")
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 3

    def _render_diff(self, params: dict, context_lines: int) -> None:
        file_path = params["file_path"]
        old_text = params["old_text"]
        new_text = params["new_text"]

        path = Path(file_path).expanduser() if file_path else None
        file_exists = bool(path and path.is_file())

        if path and not file_exists and not old_text and not new_text:
            self._print_error(f"文件不存在: {file_path}")
            return

        if file_exists:
            if not old_text and not new_text:
                self.console.print(Panel(
                    Text(f"缺少对比内容: {file_path}\n{USAGE_HINT}", style="yellow"),
                    title="Diff",
                    border_style="yellow",
                ))
                return
            try:
                if not old_text:
                    old_text = path.read_text(encoding="utf-8", errors="replace")
                elif not new_text:
                    new_text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                self._print_error(f"读取失败: {exc}")
                return

        diff_text = render_diff_text(old_text, new_text, context_lines)
        if not diff_text:
            self.console.print(Text("无变更", style="yellow"))
            return

        added = sum(1 for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++ "))
        removed = sum(1 for line in diff_text.splitlines() if line.startswith("-") and not line.startswith("--- "))

        title = Text(f"Diff: {file_path}") if file_path else Text("Diff")
        self.console.print(Panel(
            self._colorize(diff_text),
            title=title,
            subtitle=f"[green]+{added}[/green] [red]-{removed}[/red]",
            border_style="cyan",
        ))

    def _print_error(self, message: str) -> None:
        self.console.print(Panel(Text(message, style="red"), title="Diff", border_style="red"))

    @staticmethod
    def _line_style(line: str) -> str:
        if line.startswith(("--- ", "+++ ")):
            return _STYLE_HEADER
        if line.startswith("@@"):
            return _STYLE_HUNK
        if line.startswith("+"):
            return _STYLE_ADD
        if line.startswith("-"):
            return _STYLE_DEL
        return _STYLE_CONTEXT

    @staticmethod
    def _colorize(diff_text: str) -> Text:
        text = Text()
        for i, line in enumerate(diff_text.splitlines()):
            if i:
                text.append("\n")
            text.append(line, style=DiffPage._line_style(line))
        return text
