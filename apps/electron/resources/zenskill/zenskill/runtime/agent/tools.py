"""四核心工具：read / write / edit / bash（参照 pi packages/coding-agent/src/core/tools/）。

设计要点：
- content 给模型（含可续读截断提示），details 给 UI/日志
- read 支持 offset/limit 行区间；edit 对原文精确匹配且要求唯一不重叠
- bash 输出尾截断，超时/中止杀整棵进程树（start_new_session + killpg）
"""
from __future__ import annotations

import asyncio
import difflib
import json
import os
import re
import signal
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .types import AgentTool, AgentToolResult, ImageContent, TextContent

DEFAULT_READ_MAX_LINES = 2000
DEFAULT_READ_MAX_BYTES = 200_000
DEFAULT_BASH_TIMEOUT = 120
DEFAULT_IO_TIMEOUT = 30
DEFAULT_BASH_MAX_LINES = 500
DEFAULT_GREP_MAX_HITS = 200
DEFAULT_FIND_MAX_HITS = 200


def _resolve_path(cwd: str, path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = Path(cwd) / p
    return p


def _short(value: Any, limit: int = 80) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB


class ReadTool(AgentTool):
    concurrency_safe = True
    name = "read"
    description = (
        "Read a text file. Returns line-numbered content. Files over 200 lines "
        "are auto-truncated to first50+last50; always pass offset/limit to read a "
        "specific relevant section. For binary files, use bash(cat) instead. "
        "For image files (png/jpg/gif/webp), returns the image for vision-capable "
        "models. Prefer grep to locate content first, then read only the needed range."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path (relative or absolute)"},
            "offset": {"type": "integer", "description": "1-indexed start line"},
            "limit": {"type": "integer", "description": "Max lines to return"},
        },
        "required": ["path"],
    }

    def __init__(self, cwd: str, max_lines: int = DEFAULT_READ_MAX_LINES,
                 max_bytes: int = DEFAULT_READ_MAX_BYTES) -> None:
        self.cwd = cwd
        self.max_lines = max_lines
        self.max_bytes = max_bytes

    async def run(self, tool_call_id: str, params: Dict[str, Any], on_update=None) -> AgentToolResult:
        path = _resolve_path(self.cwd, params["path"])
        if not path.is_file():
            return AgentToolResult(
                content=[TextContent(f"File not found: {path}")], is_error=True
            )
        # 图片文件：返回 ImageContent（供支持视觉的模型使用）
        if path.suffix.lower() in _IMAGE_EXTENSIONS:
            return await self._read_image(path)
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(path.read_bytes), timeout=DEFAULT_IO_TIMEOUT
            )
        except asyncio.TimeoutError:
            return AgentToolResult(
                content=[TextContent(f"Read timed out after {DEFAULT_IO_TIMEOUT}s: {path}")],
                is_error=True,
            )
        except OSError as e:
            return AgentToolResult(
                content=[TextContent(f"Cannot read {path}: {e}")], is_error=True
            )

        text = raw.decode("utf-8", errors="replace")
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]
        total = len(lines)

        offset = max(1, int(params.get("offset") or 1))
        has_explicit_range = "offset" in params or "limit" in params
        limit = int(params.get("limit") or self.max_lines)

        # 智能截断：无显式 range 且文件超过 200 行时，首尾各 50 行
        if not has_explicit_range and total > 200:
            head = lines[:50]
            tail = lines[-50:]
            selected = head + [f"\n... ({total - 100} lines omitted) ...\n"] + tail
            shown = "\n".join(selected)
            shown += f"\n[Showing first 50 + last 50 of {total} lines. Use offset/limit to read specific sections.]"
            return AgentToolResult(
                content=[TextContent(shown)],
                details={"total_lines": total, "truncated": True},
            )

        start = min(offset, total + 1)
        end = min(start - 1 + limit, total)
        selected = lines[start - 1 : end] if start <= total else []

        shown = "\n".join(selected)
        truncated = False
        if len(shown.encode("utf-8", errors="replace")) > self.max_bytes:
            shown_bytes = shown.encode("utf-8", errors="replace")[: self.max_bytes]
            shown = shown_bytes.decode("utf-8", errors="ignore")
            truncated = True
            end = start + shown.count("\n")
        if end < total:
            truncated = True
            shown += f"\n[Showing lines {start}-{end} of {total}. Use offset={end + 1} to continue.]"
        if start > total:
            shown = f"[File has {total} lines; offset {start} is past the end.]"

        details = {
            "path": str(path),
            "total_lines": total,
            "offset": start,
            "end": end,
            "truncated": truncated,
        }
        return AgentToolResult(content=[TextContent(shown)], details=details)

    async def _read_image(self, path: Path) -> AgentToolResult:
        """读取图片文件为 ImageContent（供视觉模型使用）"""
        try:
            size = path.stat().st_size
            if size > _MAX_IMAGE_BYTES:
                return AgentToolResult(
                    content=[TextContent(f"Image too large: {size // 1024}KB > 5MB limit")],
                    is_error=True,
                )
            raw = await asyncio.wait_for(
                asyncio.to_thread(path.read_bytes), timeout=DEFAULT_IO_TIMEOUT
            )
        except asyncio.TimeoutError:
            return AgentToolResult(
                content=[TextContent(f"Read timed out after {DEFAULT_IO_TIMEOUT}s: {path}")],
                is_error=True,
            )
        except OSError as e:
            return AgentToolResult(
                content=[TextContent(f"Cannot read {path}: {e}")], is_error=True
            )
        import base64 as _b64
        data = _b64.b64encode(raw).decode("ascii")
        mime = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp",
        }.get(path.suffix.lower(), "image/png")
        return AgentToolResult(
            content=[ImageContent(data=data, mime_type=mime)],
            details={"path": str(path), "bytes": len(raw), "image": True},
        )


class WriteTool(AgentTool):
    name = "write"
    description = (
        "Create or overwrite a file. Creates parent directories as needed. "
        "Use for new files or full rewrites; prefer edit for targeted changes."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    }

    def __init__(self, cwd: str) -> None:
        self.cwd = cwd

    async def run(self, tool_call_id: str, params: Dict[str, Any], on_update=None) -> AgentToolResult:
        path = _resolve_path(self.cwd, params["path"])
        content = params["content"]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except (UnicodeEncodeError, TypeError) as e:
            return AgentToolResult(
                content=[TextContent(f"Cannot write {path}: content is not valid text ({e})")], is_error=True
            )
        except OSError as e:
            return AgentToolResult(
                content=[TextContent(f"Cannot write {path}: {e}")], is_error=True
            )
        size = len(content.encode("utf-8"))
        return AgentToolResult(
            content=[TextContent(f"Wrote {size} bytes to {path}")],
            details={"path": str(path), "bytes": size},
        )


class EditTool(AgentTool):
    name = "edit"
    description = (
        "Apply exact-match text replacements to a file. Each oldText must "
        "appear exactly once and edits must not overlap; matches are validated "
        "against the original file before any change is applied."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Single-file mode: file path"},
            "edits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "oldText": {"type": "string"},
                        "newText": {"type": "string"},
                    },
                    "required": ["oldText", "newText"],
                },
            },
            "files": {
                "type": "array",
                "description": "Multi-file mode: [{path, edits: [{oldText, newText}]}]",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "edits": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "oldText": {"type": "string"},
                                    "newText": {"type": "string"},
                                },
                                "required": ["oldText", "newText"],
                            },
                        },
                    },
                    "required": ["path", "edits"],
                },
            },
        },
        "oneOf": [
            {"required": ["path", "edits"]},
            {"required": ["files"]},
        ],
    }

    def __init__(self, cwd: str) -> None:
        self.cwd = cwd

    async def run(self, tool_call_id: str, params: Dict[str, Any], on_update=None) -> AgentToolResult:
        # 多文件模式：files=[{path, edits}]
        if params.get("files"):
            results = []
            total_applied = 0
            for entry in params["files"]:
                result = self._apply_one(_resolve_path(self.cwd, entry["path"]),
                                         entry.get("edits") or [])
                if result.is_error:
                    return result  # 任一文件失败则整体失败（原子语义）
                total_applied += result.details.get("edits_applied", 0)
                results.append(result.details.get("diff", ""))
            return AgentToolResult(
                content=[TextContent(f"Applied edits to {len(params['files'])} file(s)")],
                details={"files": len(params["files"]), "edits_applied": total_applied,
                         "diffs": results},
            )

        # 单文件模式
        return self._apply_one(
            _resolve_path(self.cwd, params["path"]), params.get("edits") or []
        )

    def _apply_one(self, path: Path, edits: List[Dict[str, Any]]) -> AgentToolResult:
        if not edits:
            return AgentToolResult(
                content=[TextContent("No edits provided")], is_error=True
            )
        if not path.is_file():
            return AgentToolResult(
                content=[TextContent(f"File not found: {path}")], is_error=True
            )
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return AgentToolResult(
                content=[TextContent(
                    f"Cannot edit {path}: file is not valid UTF-8 text "
                    f"(binary or other encoding). Use bash for binary files."
                )],
                is_error=True,
            )
        except OSError as e:
            return AgentToolResult(
                content=[TextContent(f"Cannot read {path}: {e}")], is_error=True
            )

        # 对原文校验：每个 oldText 唯一，且各匹配区间不重叠
        spans = []
        for i, edit in enumerate(edits):
            old = edit["oldText"]
            count = original.count(old)
            if count == 0:
                return AgentToolResult(
                    content=[TextContent(
                        f"Edit {i}: oldText not found in {path}: {_short(old)!r}"
                    )],
                    is_error=True,
                )
            if count > 1:
                return AgentToolResult(
                    content=[TextContent(
                        f"Edit {i}: oldText found {count} times in {path}; "
                        "it must be unique. Add surrounding context to disambiguate."
                    )],
                    is_error=True,
                )
            spans.append((original.index(old), original.index(old) + len(old)))

        spans_sorted = sorted(spans)
        for (s1, e1), (s2, _) in zip(spans_sorted, spans_sorted[1:]):
            if s2 < e1:
                return AgentToolResult(
                    content=[TextContent(f"Overlapping edits in {path}; refusing to apply")],
                    is_error=True,
                )

        updated = original
        for edit in edits:
            updated = updated.replace(edit["oldText"], edit["newText"], 1)
        try:
            path.write_text(updated, encoding="utf-8")
        except OSError as e:
            return AgentToolResult(
                content=[TextContent(f"Cannot write {path}: {e}")], is_error=True
            )

        diff = "\n".join(difflib.unified_diff(
            original.split("\n"), updated.split("\n"),
            fromfile=f"a/{path.name}", tofile=f"b/{path.name}", lineterm="",
        ))
        return AgentToolResult(
            content=[TextContent(f"Applied {len(edits)} edit(s) to {path}")],
            details={"path": str(path), "diff": diff, "edits_applied": len(edits)},
        )


class BashTool(AgentTool):
    name = "bash"
    description = (
        "Run a shell command; stderr is merged into the same output and a trailing "
        "[exit code] marker is appended. Output is tail-truncated at 500 lines. "
        "Default timeout 120s; override with timeout. Process tree is killed on "
        "timeout. Always check the [exit code] marker and stderr: a command can print "
        "output yet fail, or fail silently. If exit code is non-zero or stderr shows an "
        "error, analyze the cause before retrying — do not blindly re-run the same command."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer", "description": "Seconds, default 120"},
        },
        "required": ["command"],
    }

    def __init__(self, cwd: str, timeout: int = DEFAULT_BASH_TIMEOUT,
                 max_lines: int = DEFAULT_BASH_MAX_LINES) -> None:
        self.cwd = cwd
        self.timeout = timeout
        self.max_lines = max_lines

    async def run(self, tool_call_id: str, params: Dict[str, Any], on_update=None) -> AgentToolResult:
        command = params["command"]
        timeout = int(params.get("timeout") or self.timeout)
        started = time.monotonic()

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=self.cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as e:
            return AgentToolResult(
                content=[TextContent(f"Failed to start command: {e}")], is_error=True
            )

        chunks: List[bytes] = []
        total_len = 0
        timed_out = False

        async def _pump() -> None:
            nonlocal total_len
            assert proc.stdout is not None
            while True:
                piece = await proc.stdout.read(4096)
                if not piece:
                    break
                chunks.append(piece)
                total_len += len(piece)
                if on_update is not None:
                    on_update(piece.decode("utf-8", errors="replace"))

        pump = asyncio.ensure_future(_pump())
        try:
            await asyncio.wait_for(asyncio.shield(proc.wait()), timeout=timeout)
        except asyncio.TimeoutError:
            timed_out = True
            _kill_process_tree(proc)
        finally:
            try:
                await asyncio.wait_for(pump, timeout=5)
            except asyncio.TimeoutError:
                pump.cancel()

        duration_ms = int((time.monotonic() - started) * 1000)
        output = b"".join(chunks).decode("utf-8", errors="replace")
        out_lines = output.split("\n")
        truncated = False
        if len(out_lines) > self.max_lines:
            out_lines = out_lines[-self.max_lines :]
            truncated = True
            output = (
                f"[Output truncated: showing last {self.max_lines} lines]\n" + "\n".join(out_lines)
            )

        exit_code = proc.returncode
        if timed_out:
            text_out = (
                f"{output}\n[Command timed out after {timeout}s and was killed]"
                if output
                else f"[Command timed out after {timeout}s and was killed]"
            )
            return AgentToolResult(
                content=[TextContent(text_out)],
                is_error=True,
                details={"command": command, "exit_code": exit_code,
                         "duration_ms": duration_ms, "timed_out": True,
                         "truncated": truncated},
            )

        text_out = output
        if exit_code != 0:
            suffix = f"\n[exit code: {exit_code}]"
            text_out = (text_out + suffix) if text_out else suffix.lstrip("\n")
        return AgentToolResult(
            content=[TextContent(text_out)] if text_out else [TextContent("[no output]")],
            is_error=(exit_code != 0),
            details={"command": command, "exit_code": exit_code,
                     "duration_ms": duration_ms, "timed_out": False,
                     "truncated": truncated},
        )


class GrepTool(AgentTool):
    concurrency_safe = True
    name = "grep"
    description = (
        "Search file contents with regex; returns matching lines with "
        "file:line:prefix. Use this to LOCATE code/symbols before reading — it is "
        "more token-efficient than reading whole files. Use glob to filter by file "
        "type (e.g., '*.py') and path to limit the tree searched. Capped at 200 hits "
        "and skips binary/dependency dirs (.git, node_modules, .venv, __pycache__). "
        "For file NAMES rather than contents, use find instead."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regular expression"},
            "path": {"type": "string", "description": "Directory or file to search"},
            "glob": {"type": "string", "description": "Filename filter, e.g. *.py"},
            "ignore_case": {"type": "boolean"},
        },
        "required": ["pattern"],
    }

    _SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache", ".pytest_cache"}

    def __init__(self, cwd: str, max_hits: int = DEFAULT_GREP_MAX_HITS) -> None:
        self.cwd = cwd
        self.max_hits = max_hits

    async def run(self, tool_call_id: str, params: Dict[str, Any], on_update=None) -> AgentToolResult:
        pattern = params["pattern"]
        try:
            regex = re.compile(pattern, re.IGNORECASE if params.get("ignore_case") else 0)
        except re.error as e:
            return AgentToolResult(
                content=[TextContent(f"Invalid regex: {e}")], is_error=True
            )

        root = _resolve_path(self.cwd, params.get("path") or ".")
        glob_filter = params.get("glob")
        if glob_filter:
            try:
                glob_re = re.compile(_glob_to_regex(glob_filter), re.IGNORECASE)
            except re.error:
                glob_re = None
        else:
            glob_re = None

        targets: List[Path] = []
        if root.is_file():
            targets = [root]
        elif root.is_dir():
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in self._SKIP_DIRS]
                for fn in filenames:
                    if glob_re is None or glob_re.match(fn):
                        targets.append(Path(dirpath) / fn)
                if len(targets) > 5000:
                    break
        else:
            return AgentToolResult(
                content=[TextContent(f"Path not found: {root}")], is_error=True
            )

        hits: List[str] = []
        scanned = 0
        truncated = False

        def _scan():
            nonlocal hits, scanned, truncated
            for target in sorted(targets):
                try:
                    if target.stat().st_size > 2_000_000:
                        continue
                    text = target.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                scanned += 1
                rel = target.relative_to(Path(self.cwd)) if target.is_relative_to(Path(self.cwd)) else target
                for lineno, line in enumerate(text.split("\n"), start=1):
                    if regex.search(line):
                        hits.append(f"{rel}:{lineno}:{line.strip()[:300]}")
                        if len(hits) >= self.max_hits:
                            truncated = True
                            break
                if truncated:
                    break

        try:
            await asyncio.wait_for(asyncio.to_thread(_scan), timeout=DEFAULT_IO_TIMEOUT)
        except asyncio.TimeoutError:
            return AgentToolResult(
                content=[TextContent(
                    f"Grep timed out after {DEFAULT_IO_TIMEOUT}s. "
                    f"Partial results: {len(hits)} hits in {scanned} files. "
                    f"Refine pattern or path to narrow the search."
                )],
                is_error=True,
            )

        output = "\n".join(hits) if hits else "[no matches]"
        if truncated:
            output += f"\n[Truncated at {self.max_hits} matches. Refine pattern or path to narrow.]"
        return AgentToolResult(
            content=[TextContent(output)],
            details={"pattern": pattern, "files_scanned": scanned, "hits": len(hits), "truncated": truncated},
        )


class FindTool(AgentTool):
    concurrency_safe = True
    name = "find"
    description = "Find files by name glob pattern (e.g., '*.py', '**/test_*'); returns relative paths. Use when you know the name/regex but not the location. Searches only file/dir names, not contents — for content search use grep. Capped at 200 results."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob, e.g. *.py or *test*"},
            "path": {"type": "string"},
        },
        "required": ["pattern"],
    }

    def __init__(self, cwd: str, max_hits: int = DEFAULT_FIND_MAX_HITS) -> None:
        self.cwd = cwd
        self.max_hits = max_hits

    async def run(self, tool_call_id: str, params: Dict[str, Any], on_update=None) -> AgentToolResult:
        root = _resolve_path(self.cwd, params.get("path") or ".")
        if not root.exists():
            return AgentToolResult(
                content=[TextContent(f"Path not found: {root}")], is_error=True
            )
        regex = re.compile(_glob_to_regex(params["pattern"]))
        matches: List[str] = []
        truncated = False

        def _scan():
            nonlocal matches, truncated
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in GrepTool._SKIP_DIRS]
                for name in sorted(filenames + dirnames):
                    if regex.match(name):
                        p = Path(dirpath) / name
                        rel = p.relative_to(Path(self.cwd)) if p.is_relative_to(Path(self.cwd)) else p
                        matches.append(str(rel))
                        if len(matches) >= self.max_hits:
                            truncated = True
                            break
                if truncated:
                    break

        try:
            await asyncio.wait_for(asyncio.to_thread(_scan), timeout=DEFAULT_IO_TIMEOUT)
        except asyncio.TimeoutError:
            return AgentToolResult(
                content=[TextContent(
                    f"Find timed out after {DEFAULT_IO_TIMEOUT}s. "
                    f"Partial results: {len(matches)} matches. "
                    f"Refine pattern to narrow the search."
                )],
                is_error=True,
            )
        output = "\n".join(matches) if matches else "[no matches]"
        if truncated:
            output += f"\n[Truncated at {self.max_hits} results.]"
        return AgentToolResult(
            content=[TextContent(output)],
            details={"pattern": params["pattern"], "matches": len(matches), "truncated": truncated},
        )


class ListTool(AgentTool):
    concurrency_safe = True
    name = "ls"
    description = "List a directory's entries with type markers (d=dir, -=file), sorted dirs-first then by name. Use to survey a directory's top-level structure before descending in with read/grep/find."
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def __init__(self, cwd: str) -> None:
        self.cwd = cwd

    async def run(self, tool_call_id: str, params: Dict[str, Any], on_update=None) -> AgentToolResult:
        root = _resolve_path(self.cwd, params["path"])
        if not root.is_dir():
            return AgentToolResult(
                content=[TextContent(f"Directory not found: {root}")], is_error=True
            )
        try:
            entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError as e:
            return AgentToolResult(
                content=[TextContent(f"Cannot list {root}: {e}")], is_error=True
            )
        lines = [
            f"{'d' if e.is_dir() else '-'} {e.name}" for e in entries
        ]
        return AgentToolResult(
            content=[TextContent("\n".join(lines) if lines else "[empty]")],
            details={"path": str(root), "entries": len(lines)},
        )


def _glob_to_regex(glob: str) -> str:
    parts = []
    for ch in glob:
        if ch == "*":
            parts.append(".*")
        elif ch == "?":
            parts.append(".")
        else:
            parts.append(re.escape(ch))
    return "^" + "".join(parts) + "$"



def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        if hasattr(os, "killpg"):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        else:  # pragma: no cover - 非 POSIX 平台退化
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


DEFAULT_WEB_FETCH_MAX_CHARS = 15000
DEFAULT_WEB_SEARCH_MAX_CHARS = 8000


class WebFetchTool(AgentTool):
    concurrency_safe = True
    name = "web_fetch"
    description = (
        "Fetch a URL and return its text content (up to 15000 characters). Useful for "
        "reading documentation, library source, or reference pages when you need "
        "external info, e.g. to understand an API contract or diagnose an error not "
        "explainable from local code. Has a 15s timeout; sends a ZenSkill User-Agent."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to fetch"},
        },
        "required": ["url"],
    }

    def __init__(self, max_chars: int = DEFAULT_WEB_FETCH_MAX_CHARS):
        self._max_chars = max_chars

    async def run(self, tool_call_id: str, params: Dict[str, Any], on_update=None) -> AgentToolResult:
        import aiohttp

        url = params.get("url", "")
        if not url:
            return AgentToolResult(content=[TextContent("Error: url is required")], is_error=True)

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    url,
                    headers={"User-Agent": "ZenSkill/2.6 (agent web_fetch)"},
                    allow_redirects=True,
                ) as resp:
                    if resp.status != 200:
                        return AgentToolResult(content=[TextContent(f"Error: HTTP {resp.status}")], is_error=True)
                    text = await resp.text()
                    if len(text) > self._max_chars:
                        text = text[: self._max_chars] + f"\n\n... (truncated from {len(text)} chars)"
                    return AgentToolResult(content=[TextContent(text)])
        except asyncio.TimeoutError:
            return AgentToolResult(content=[TextContent(f"Error: request timed out after 15s: {url}")], is_error=True)
        except Exception as e:
            return AgentToolResult(content=[TextContent(f"Error fetching {url}: {type(e).__name__}: {e}")], is_error=True)


class SearchTool(AgentTool):
    concurrency_safe = True
    name = "web_search"
    description = (
        "Search the web using DuckDuckGo; returns titles, URLs, and snippets (default "
        "5 results, max 10). Useful for finding documentation, error solutions, or "
        "reference material not in the local codebase, such as framework deprecations, "
        "API signatures, or third-party library usage. For deep reading of one page, "
        "follow up with web_fetch on the most promising URL."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Max results to return (default 5)"},
        },
        "required": ["query"],
    }

    def __init__(self, max_chars: int = DEFAULT_WEB_SEARCH_MAX_CHARS):
        self._max_chars = max_chars

    async def run(self, tool_call_id: str, params: Dict[str, Any], on_update=None) -> AgentToolResult:
        import aiohttp

        query = params.get("query", "")
        if not query:
            return AgentToolResult(content=[TextContent("Error: query is required")], is_error=True)

        max_results = min(int(params.get("max_results", 5)), 10)

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": query},
                    headers={"User-Agent": "Mozilla/5.0 (ZenSkill/2.6)"},
                ) as resp:
                    if resp.status != 200:
                        return AgentToolResult(content=[TextContent(f"Error: HTTP {resp.status}")], is_error=True)
                    html = await resp.text()
                    results = _parse_ddg_html(html, max_results)
                    if len(results) > self._max_chars:
                        results = results[: self._max_chars] + "\n... (truncated)"
                    if not results.strip():
                        results = "No results found. The search service may be unavailable."
                    return AgentToolResult(content=[TextContent(results)])
        except asyncio.TimeoutError:
            return AgentToolResult(content=[TextContent("Error: search timed out after 10s")], is_error=True)
        except Exception as e:
            return AgentToolResult(content=[TextContent(f"Search error: {type(e).__name__}: {e}")], is_error=True)


def _parse_ddg_html(html: str, max_results: int) -> str:
    """Parse DuckDuckGo HTML search results page into readable text."""
    results: list[str] = []

    # DDG HTML results are in <a class="result__a"> (title+link) and
    # <a class="result__snippet"> (snippet). Use regex for robustness.
    title_pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    titles = title_pattern.findall(html)
    snippets = snippet_pattern.findall(html)

    for i, (href, title) in enumerate(titles[:max_results]):
        # Clean HTML tags from title
        clean_title = re.sub(r"<[^>]+>", "", title).strip()
        # DDG wraps href in //duckduckgo.com/l/?uddg=...&rut=...
        if "uddg=" in href:
            import urllib.parse
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            href = parsed.get("uddg", [href])[0]
        snippet = ""
        if i < len(snippets):
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
        results.append(f"{i + 1}. {clean_title}\n   URL: {href}\n   {snippet}")

    return "\n\n".join(results)


def create_default_tools(cwd: str) -> List[AgentTool]:
    return [
        ReadTool(cwd), WriteTool(cwd), EditTool(cwd), BashTool(cwd),
        GrepTool(cwd), FindTool(cwd), ListTool(cwd),
        WebFetchTool(), SearchTool(),
    ]


DEFAULT_SYSTEM_PROMPT = """You are ZenSkill Agent, a coding agent working in the user's workspace.

## Tools
- read(path, offset?, limit?): Read file content. For files over 200 lines, read() auto-truncates to first50+last50 — always pass offset/limit to read a specific relevant section instead of the whole file.
- write(path, content): Create or overwrite a file. Use for new files or full rewrites; prefer edit for targeted changes.
- edit(path, edits): Targeted edits with exact oldText→newText replacement. oldText must match the file exactly and be unique; include surrounding context to disambiguate.
- bash(command): Run a shell command. Pipes stderr into the output. Use the [exit code] marker and stderr lines to judge whether a command truly succeeded — never assume success from missing output.
- grep(pattern, glob?, ignoreCase?): Search file contents with regex, returns file:line:prefix. Always use this to LOCATE code/symbols before reading; do not read whole files to search.
- find(pattern): Search file names with glob patterns (e.g., "*.py"). Use when you know the name but not the location.
- ls(path): List a directory's entries with type markers (d=dir, -=file). Use to survey a directory before descending.

## Workflow
1. **Locate first, then read**: Before reading any file, use grep/find/ls to pinpoint the relevant lines. Only then read those sections with read(path, offset, limit). Never read an entire large file to search for a symbol — that wastes context.
2. **Plan then act**: For complex tasks, outline your approach before executing.
3. **Verify after changes**: Run tests or validation after editing code.
4. **One step at a time**: Make one change, verify it works, then proceed to the next.

## Reading files efficiently
- Use grep to find where a name/pattern appears, then read only the surrounding lines via offset/limit.
- If read() truncated the output, continue with offset = next unread line rather than re-reading from the top.
- Choose the smallest offset/limit range that answers your question — context is a limited resource.

## Error Recovery
- If a file path is wrong, use find to locate it.
- If edit fails because oldText was not found, re-read the file to get the current content — then craft oldText with enough context to be unique.
- If bash returns a non-zero exit code, read stderr and the error output carefully to diagnose the root cause, then fix it.
- **Do not blindly re-run a failed command.** First analyze the error, form a hypothesis about the cause, adjust the command or approach, and only then retry. If a command fails twice for the same reason, stop and rethink the approach entirely rather than repeating it.
- Always check the [exit code] and stderr — a command may print output yet still fail, or succeed silently.

## Safety
- Never run destructive commands (rm -rf, git reset --hard) without explicit user request.
- Prefer reading and understanding before modifying.
- When unsure, ask the user rather than guessing.

## Output
- Reply in the language of the user's task.
- When the task is done, give a concise summary of what was changed and why.
"""
