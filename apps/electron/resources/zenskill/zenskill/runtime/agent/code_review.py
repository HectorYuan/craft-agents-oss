"""代码审查器：接收 git diff 文本，用 LLM 分析并返回结构化审查结果。

设计（与 compact_session 同层，直接驱动 StreamFn，不经 AgentLoop）：
- CodeReviewer 把 diff 包进 UserMessage 提示词，收集流式 TextDelta 至终态；
  因此天然可被 FauxStreamFn 确定性驱动（单测不打真实 API）。
- 提示词要求 LLM 输出严格 JSON；解析时兼容 ```json 代码块围栏，
  JSON 不可用时降级到行级启发式解析，保证尽力返回结构化结果。
- 返回 CodeReviewResult（可 to_dict/from_dict 序列化），带
  severity（critical/high/medium/low）与 category（bug/security/style/performance）统计。

category 语义（与任务对齐）：
- bug         缺陷风险：空指针、越界、竞态、错误分支、异常未处理……
- security    安全漏洞：注入、路径穿越、硬编码密钥、越权、不安全反序列化……
- style       风格问题：命名、格式、魔法数字、死代码、可读性……
- performance 性能问题：循环内 IO、N+1 查询、大对象拷贝、无缓存……
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .providers import ModelConfig, build_model_config, create_stream, resolve_model
from .types import (
    Context,
    StreamDone,
    StreamError,
    TextDelta,
    UserMessage,
)

SEVERITIES = ("critical", "high", "medium", "low")
CATEGORIES = ("bug", "security", "style", "performance")
CONFIDENCES = ("high", "medium", "low")

_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}
_PASS_SCORE = 60


class CodeReviewError(RuntimeError):
    """LLM 流失败或返回内容无法解析时抛出。"""


# ---------------------------------------------------------------------------
# 结构化审查结果
# ---------------------------------------------------------------------------

@dataclass
class ReviewFinding:
    """单条审查发现。severity/category/confidence 在 __post_init__ 归一化到受控枚举。

    confidence（high/medium/low）表示该发现在第二轮自验证中的置信度，
    用于过滤误报：confidence=low 的发现会被 review() 剔除。
    """
    severity: str = "medium"
    category: str = "style"
    title: str = ""
    description: str = ""
    suggestion: str = ""
    file: str = ""
    line: Optional[int] = None
    confidence: str = "high"

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            self.severity = "medium"
        if self.category not in CATEGORIES:
            self.category = "style"
        if self.confidence not in CONFIDENCES:
            self.confidence = "high"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "suggestion": self.suggestion,
            "file": self.file,
            "line": self.line,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReviewFinding":
        line = d.get("line")
        if isinstance(line, bool):
            line = None
        if line is not None and not isinstance(line, (int, float)):
            line = None
        return cls(
            severity=str(d.get("severity", "medium") or "medium"),
            category=str(d.get("category", "style") or "style"),
            title=str(d.get("title", "") or ""),
            description=str(d.get("description", "") or ""),
            suggestion=str(d.get("suggestion", "") or ""),
            file=str(d.get("file", "") or ""),
            line=int(line) if line is not None else None,
            confidence=str(d.get("confidence", "high") or "high"),
        )


@dataclass
class CodeReviewResult:
    """一次 diff 审查的结构化结果。"""
    summary: str = ""
    score: int = 100
    findings: List[ReviewFinding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """通过标准：分数达标且无 critical 缺陷。"""
        return (
            self.score >= _PASS_SCORE
            and not any(f.severity == "critical" for f in self.findings)
        )

    def count_by_severity(self) -> Dict[str, int]:
        return {s: sum(1 for f in self.findings if f.severity == s) for s in SEVERITIES}

    def count_by_category(self) -> Dict[str, int]:
        return {c: sum(1 for f in self.findings if f.category == c) for c in CATEGORIES}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "score": self.score,
            "passed": self.passed,
            "findings": [f.to_dict() for f in self.findings],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CodeReviewResult":
        score = d.get("score", 100)
        if isinstance(score, str):
            score = re.sub(r"[^\d]", "", score)
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = 100
        return cls(
            summary=str(d.get("summary", "") or ""),
            score=max(0, min(100, score)),
            findings=[
                ReviewFinding.from_dict(f)
                for f in (d.get("findings") or [])
                if isinstance(f, dict)
            ],
        )


# ---------------------------------------------------------------------------
# 提示词与解析辅助
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM_HINT = (
    "You are a senior code reviewer. Analyze the given git diff and report "
    "concrete, actionable issues. Reply with ONLY a JSON object, no prose, "
    "no markdown fences.\n"
)

_JSON_SCHEMA_EXAMPLE = """{
  "summary": "one-paragraph overview of the change and overall quality",
  "score": 85,
  "findings": [
    {
      "severity": "high",
      "category": "bug",
      "title": "short title",
      "description": "why it is a problem",
      "suggestion": "how to fix it",
      "file": "path/to/file.py",
      "line": 12
    }
  ]
}"""

_VERIFY_JSON_EXAMPLE = """[{"index": 0, "confidence": "high"}]

# index 对应 findings 数组下标（从 0 开始）；confidence 取值 high/medium/low。
# 只输出 JSON 数组，不要输出解释或 markdown 围栏。"""


def _strip_fences(text: str) -> str:
    """去掉 ```json ... ``` 之类的 markdown 代码块围栏。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json_object(text: str) -> Optional[str]:
    """提取文本中第一个 { 或 [ 到最后一个 } 或 ] 的合法 JSON 片段。"""
    start_obj = text.find("{")
    start_arr = text.find("[")
    if start_obj == -1 and start_arr == -1:
        return None
    if start_obj == -1:
        start = start_arr
    elif start_arr == -1:
        start = start_obj
    else:
        start = min(start_obj, start_arr)
    end_obj = text.rfind("}")
    end_arr = text.rfind("]")
    end = max(end_obj, end_arr)
    if end == -1 or end <= start:
        return None
    candidate = text[start:end + 1]
    try:
        json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return candidate


_FINDING_LINE = re.compile(
    r"^\s*(?:[-*]|\d+[.)])\s*"           # 列表前缀：- * 1.
    r"(?:\[(?P<sev>[^\]]+)\]\s*)?"        # [high] / [critical]
    r"(?:(?P<cat>[a-zA-Z]+)\s*:\s*)?"     # bug: / security:
    r"(?P<body>.+)$"
)
_LOCATION_RE = re.compile(r"^([^\s:]+(?::\d+)?)[:：]\s*(.*)$")

# 编译器/CI 常见输出：src/app.py:13: SQL injection risk
_FILE_LINE_RE = re.compile(r"^\s*([^:\s]+\.[\w./\\-]+)[:：](\d+)[:：]\s*(.+)$")
# 自然语言位置：In file src/app.py, line 13: SQL injection risk
_IN_FILE_LINE_RE = re.compile(
    r"^\s*In\s+file\s+([^,;]+?)\s*,\s*line\s+(\d+)\s*[:：]\s*(.+)$",
    re.IGNORECASE,
)


# 依据信息关键词自动推断严重级别（未显式标注时启用）
_SEVERITY_RULES = (
    # critical：安全/溢出类高危关键词
    ("critical", ("vulnerability", "injection", "overflow", "sql", "xss",
                   "command execution", "rce", "buffer overflow", "remote", "traversal")),
    # high：与 critical 同族但仅作安全提示，或重大缺陷
    ("high", ("deadlock", "race condition", "crash", "corruption", "leak")),
    # medium：告警、弃用、潜在隐患
    ("medium", ("warning", "deprecated", "deprecation", "unsafe", "risk")),
    # low：风格/格式/命名等非功能性
    ("low", ("style", "format", "formatting", "naming", "spelling", "typo")),
)


def _infer_severity(text: str) -> str:
    """根据信息关键词推断缺陷严重级别，未命中时取 medium。"""
    low = text.lower()
    for sev, keywords in _SEVERITY_RULES:
        for kw in keywords:
            if kw in low:
                return sev
    return "medium"


def _looks_like_location(part: str) -> bool:
    return bool(part) and (
        "." in part or "/" in part or "\\" in part or ":" in part
    )


def _parse_heuristic(text: str) -> CodeReviewResult:
    """JSON 不可用时的降级解析。

    逐行识别三类发现格式：
      1) '- [sev] category: title'                      原列表格式
      2) 'file.py:12: message'                          编译器/CI 输出格式
      3) 'In file x, line 12: message'                 自然语言位置格式
    未显式标注严重级别时，依据 message 关键词自动推断。
    """
    findings: List[ReviewFinding] = []
    summary_lines: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        # --- 格式 3：In file X, line Y: message ---
        in_file = _IN_FILE_LINE_RE.match(line)
        if in_file:
            file_path = in_file.group(1).strip()
            try:
                line_no = int(in_file.group(2))
            except ValueError:
                line_no = None
            body = in_file.group(3).strip()
            title = _extract_compiler_title(body)
            findings.append(ReviewFinding(
                severity=_infer_severity(body),
                category=_infer_category(body),
                title=title,
                description=body,
                file=file_path,
                line=line_no,
            ))
            continue

        # --- 格式 2：file:line: message ---
        file_line = _FILE_LINE_RE.match(line)
        if file_line:
            file_path = file_line.group(1).strip()
            try:
                line_no = int(file_line.group(2))
            except ValueError:
                line_no = None
            body = file_line.group(3).strip()
            findings.append(ReviewFinding(
                severity=_infer_severity(body),
                category=_infer_category(body),
                title=_extract_compiler_title(body),
                description=body,
                file=file_path,
                line=line_no,
            ))
            continue

        # --- 格式 1：列表格式 '- [sev] category: title' ---
        m = _FINDING_LINE.match(line)
        if m and not m.group("body").lower().startswith(("summary", "score")):
            sev_raw = (m.group("sev") or "").lower()
            body = m.group("body").strip()
            sev = sev_raw if sev_raw in SEVERITIES else _infer_severity(body)
            cat_raw = (m.group("cat") or "").lower()
            cat = cat_raw if cat_raw in CATEGORIES else _infer_category(body)
            file_path, title = "", body
            loc = _LOCATION_RE.match(body)
            if loc and _looks_like_location(loc.group(1)):
                file_path, title = loc.group(1).strip(), loc.group(2).strip()
            findings.append(ReviewFinding(
                severity=sev, category=cat, title=title,
                description=body, file=file_path,
            ))
        else:
            summary_lines.append(line)
    # 启发式分数：100 - 各缺陷权重和（critical=40, high=20, medium=10, low=5），下限 0
    penalty = sum({
        "critical": 40, "high": 20, "medium": 10, "low": 5,
    }.get(f.severity, 5) for f in findings)
    score = max(0, 100 - penalty)
    return CodeReviewResult(
        summary="\n".join(summary_lines)[:500],
        score=score,
        findings=findings,
    )


def _extract_compiler_title(body: str) -> str:
    """从编译器风格 message 中截取简洁标题（首句，去尾标点）。"""
    body = body.strip()
    # 去掉可能的错误代号前缀，如 'E713' / 'SQL22531N'
    body = re.sub(r"^[A-Z]{1,5}\d{1,5}\s*[:：-]?\s*", "", body)
    title = body.split(";")[0].split(".")[0].strip().rstrip(".:：")
    return title[:120] or body[:120]


def _infer_category(body: str) -> str:
    """依据 message 关键词推断所属 category，未命中时默认 style。"""
    low = body.lower()
    if any(kw in low for kw in ("injection", "vulnerab", "security", "auth",
                                "password", "sql", "xss", "csrf", "unsafe")):
        return "security"
    if any(kw in low for kw in ("performance", "slow", "n+1", "leak", "io",
                                "cache", "complexity")):
        return "performance"
    if any(kw in low for kw in ("style", "format", "naming", "spelling", "typo")):
        return "style"
    return "bug"  # 默认视为缺陷风险


# ---------------------------------------------------------------------------
# git 集成
# ---------------------------------------------------------------------------

async def run_bash(command: str, cwd: Optional[str] = None) -> str:
    """执行一条 shell 命令并返回 stdout+stderr 文本；非零退出抛 CodeReviewError。

    cwd 指定命令的工作目录（如 git 仓库路径）；命令失败或无法启动时抛
    CodeReviewError，便于上层区分「git 环境问题」与「LLM 审查问题」。
    """
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as e:
        raise CodeReviewError(f"Failed to run command: {e}") from e
    output, _ = await proc.communicate()
    text = output.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise CodeReviewError(
            f"Command failed (exit {proc.returncode}): {command}\n{text.strip()}"
        )
    return text


# ---------------------------------------------------------------------------
# CodeReviewer
# ---------------------------------------------------------------------------

class CodeReviewer:
    """接收 git diff 文本，驱动 LLM 流式分析并返回结构化 CodeReviewResult。

    stream/model 可显式注入（测试传 FauxStreamFn + 假 ModelConfig）；
    缺省时按 resolve_model()/create_stream() 走真实凭据解析。

    git 集成：review_staged()/review_branch(base)/review_working() 通过
    run_bash 执行对应 git diff 命令拿到 diff 文本，再走同一 review 管线。
    """

    def __init__(
        self,
        stream: Optional[Callable[..., Any]] = None,
        model: Optional[ModelConfig] = None,
        categories: Optional[List[str]] = None,
        max_findings: int = 20,
        max_diff_chars: int = 30_000,
        abort_event: Any = None,
        context_files: bool = True,
    ) -> None:
        self._stream = stream
        self._model = model
        self.categories = [c for c in (categories or list(CATEGORIES)) if c in CATEGORIES]
        self.max_findings = max_findings
        self.max_diff_chars = max_diff_chars
        self.abort_event = abort_event
        self.context_files = context_files

    # ------------------------------------------------------------------
    # 内部装配
    # ------------------------------------------------------------------

    def _ensure_model(self) -> ModelConfig:
        if self._model is None:
            self._model = resolve_model()
        return self._model

    def _ensure_stream(self) -> Callable[..., Any]:
        if self._stream is None:
            self._stream = create_stream(self._ensure_model())
        return self._stream

    @staticmethod
    def _extract_files_from_diff(diff: str) -> List[str]:
        """从 git diff 文本中提取被修改的文件路径（解析 +++ b/path 行）。

        只识别带 b/ 前缀的 +++ 头（git 默认 a/b 前缀格式）；删除文件（+++ /dev/null）
        与重命名等无 b/ 前缀的行会被跳过。路径按出现顺序去重返回。
        """
        files: List[str] = []
        seen = set()
        for line in diff.splitlines():
            m = re.match(r"^\+\+\+\s+b/(.+)$", line.strip())
            if not m:
                continue
            path = m.group(1).strip()
            if path.startswith('"') and path.endswith('"'):  # git 引号转义的特殊路径
                path = path[1:-1]
            if path and path != "/dev/null" and path not in seen:
                seen.add(path)
                files.append(path)
        return files

    def _read_file_context(
        self,
        files: List[str],
        cwd: Optional[str] = None,
        max_lines_per_file: int = 200,
    ) -> str:
        """读取每个文件的内容（截断到 max_lines_per_file），拼成上下文文本块。

        读取失败（文件不存在/不可读/编码问题）的文件静默跳过；返回空串表示
        无可用上下文。每个文件块的格式：
            --- File: path ---\n内容
        """
        blocks: List[str] = []
        for path in files:
            full = path if os.path.isabs(path) else os.path.join(cwd or "", path)
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as fh:
                    lines = fh.readlines()
            except OSError:
                continue
            if len(lines) > max_lines_per_file:
                content = "".join(lines[:max_lines_per_file])
                content += f"\n... [truncated: {len(lines)} lines total]"
            else:
                content = "".join(lines)
            blocks.append(f"--- File: {path} ---\n{content.rstrip()}")
        return "\n\n".join(blocks)

    def build_prompt(self, diff: str, cwd: Optional[str] = None) -> str:
        """构造审查提示词：分类定义 + 严格 JSON 格式要求 + diff 正文 + 文件上下文。

        cwd 提供 git 仓库根目录，用于定位 diff 中引用文件的实际内容；
        context_files 开启时，在 diff 后追加被修改文件的截断内容。
        """
        if len(diff) > self.max_diff_chars:
            diff = (
                diff[: self.max_diff_chars]
                + f"\n... [diff truncated: {len(diff)} chars total]"
            )
        categories_desc = ", ".join(self.categories)
        prompt = (
            _DEFAULT_SYSTEM_HINT
            + f"Categories to check: {categories_desc}.\n"
            + "Severity levels: critical, high, medium, low.\n"
            + "Return JSON exactly like this (do not wrap in markdown):\n"
            + _JSON_SCHEMA_EXAMPLE
            + "\n\nHere is the git diff to review:\n"
            + "```diff\n" + diff + "\n```"
        )
        if self.context_files:
            files = self._extract_files_from_diff(diff)
            if files:
                ctx = self._read_file_context(files, cwd)
                if ctx:
                    prompt += "\n\nRelevant file context:\n" + ctx
        return prompt

    def _build_context(self, diff: str, cwd: Optional[str] = None) -> Context:
        return Context(messages=[UserMessage(content=self.build_prompt(diff, cwd))])

    # ------------------------------------------------------------------
    # 流式收集
    # ------------------------------------------------------------------

    async def _collect(self, context: Context) -> str:
        """驱动 StreamFn 收集文本直到终态；StreamError 抛 CodeReviewError。"""
        model = self._ensure_model()
        stream = self._ensure_stream()
        parts: List[str] = []
        terminal_error: Optional[str] = None
        async for ev in stream(model, context, self.abort_event):
            if isinstance(ev, TextDelta):
                parts.append(ev.text)
            elif isinstance(ev, StreamError):
                terminal_error = ev.error.error_message or "LLM stream error"
                break
            elif isinstance(ev, StreamDone):
                break
        if terminal_error:
            raise CodeReviewError(terminal_error)
        return "".join(parts)

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    async def review(self, diff: str, cwd: Optional[str] = None) -> CodeReviewResult:
        """审查一段 git diff 文本，返回结构化 CodeReviewResult。

        cwd 指定 git 仓库路径；传入后，diff 中引用文件的上下文会（在
        context_files 开启时）被读取并注入提示词。
        """
        if not diff or not diff.strip():
            return CodeReviewResult(
                summary="No diff to review (empty input).",
                score=100,
            )
        context = self._build_context(diff, cwd)
        text = (await self._collect(context)).strip()
        if not text:
            raise CodeReviewError("LLM returned an empty review.")
        result = self._parse(text)
        if self.max_findings > 0:
            result.findings = result.findings[: self.max_findings]
        # 多轮自验证：把第一轮 findings 与原始 diff 交给 LLM 过滤误报
        result.findings = await self._verify_findings(result.findings, diff, cwd)
        return result

    async def review_staged(self, cwd: Optional[str] = None) -> CodeReviewResult:
        """审查暂存区（index）改动：git diff --cached。

        cwd 指定 git 仓库路径；无暂存改动时返回干净的 CodeReviewResult（不触发 LLM）。
        """
        diff = await run_bash("git diff --cached", cwd=cwd)
        return await self.review(diff, cwd=cwd)

    async def review_branch(self, base: str, cwd: Optional[str] = None) -> CodeReviewResult:
        """审查 base...HEAD 分支差异：git diff {base}...HEAD。

        cwd 指定 git 仓库路径；base 为对比基线分支名（如 "main"）。
        """
        diff = await run_bash(f"git diff {shlex.quote(base)}...HEAD", cwd=cwd)
        return await self.review(diff, cwd=cwd)

    async def review_working(self, cwd: Optional[str] = None) -> CodeReviewResult:
        """审查工作区未暂存改动：git diff。

        cwd 指定 git 仓库路径；无改动时返回干净的 CodeReviewResult（不触发 LLM）。
        """
        diff = await run_bash("git diff", cwd=cwd)
        return await self.review(diff, cwd=cwd)

    def build_verify_prompt(self, findings: List[ReviewFinding], diff: str) -> str:
        """构造自验证提示词：把第一轮 findings 与原始 diff 交给 LLM，要求其评估每个
        finding 的置信度（high/medium/low），输出 JSON 数组 [{index, confidence}, ...]，
        index 对应 findings 数组下标（从 0 开始）。"""
        findings_json = json.dumps(
            [f.to_dict() for f in findings], ensure_ascii=False, indent=2
        )
        return (
            "You are a senior code reviewer performing a second-pass self-verification.\n"
            "Below is the original git diff and a list of findings from a first-pass review.\n"
            "For EACH finding, decide its confidence (how likely it is a true, actionable issue\n"
            "and not a false positive) by cross-checking it against the diff.\n"
            "Confidence levels: high (definitely a real issue), medium (likely but uncertain),\n"
            "low (suspected false positive / too speculative).\n"
            "\n"
            "Reply with ONLY a JSON array, no prose, no markdown fences, exactly like:\n"
            + _VERIFY_JSON_EXAMPLE
            + "\n\nHere is the original git diff:\n```diff\n"
            + diff
            + "\n```\n\nHere are the findings (index = array position, from 0):\n```json\n"
            + findings_json
            + "\n```\n"
        )

    async def _verify_findings(
        self,
        findings: List[ReviewFinding],
        diff: str,
        cwd: Optional[str] = None,
    ) -> List[ReviewFinding]:
        """第二轮自验证：把第一轮 findings 与原始 diff 一起发给 LLM，评估每个 finding 的
        置信度并据此过滤误报。返回仅保留 confidence != low 的 findings。"""
        if not findings:
            return findings
        context = Context(messages=[UserMessage(content=self.build_verify_prompt(findings, diff))])
        text = (await self._collect(context)).strip()
        if not text:
            # 验证阶段无响应时不做过滤，保守保留全部 findings
            return findings

        cleaned = _strip_fences(text)
        payload = _extract_json_object(cleaned)
        confidence_map: Dict[int, str] = {}
        if payload is not None:
            try:
                data = json.loads(payload)
                if isinstance(data, list):
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        idx = item.get("index")
                        conf = item.get("confidence")
                        if isinstance(idx, int) and isinstance(conf, str):
                            confidence_map[int(idx)] = conf
            except (TypeError, ValueError):
                confidence_map = {}

        keep: List[ReviewFinding] = []
        for i, finding in enumerate(findings):
            conf = confidence_map.get(i, "high")  # 未覆盖的 index 默认置信
            if conf in ("low",):
                continue  # 过滤置信度=low 的发现
            f = finding
            if conf in CONFIDENCES and conf != f.confidence:
                f = ReviewFinding(
                    severity=f.severity,
                    category=f.category,
                    title=f.title,
                    description=f.description,
                    suggestion=f.suggestion,
                    file=f.file,
                    line=f.line,
                    confidence=conf,
                )
            keep.append(f)
        return keep

    def _parse(self, text: str) -> CodeReviewResult:
        cleaned = _strip_fences(text)
        payload = _extract_json_object(cleaned)
        if payload is not None:
            try:
                return self._parse_json(payload)
            except (TypeError, ValueError, KeyError):
                pass  # 结构不合法时降级启发式
        return _parse_heuristic(cleaned)

    def _parse_json(self, payload: str) -> CodeReviewResult:
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON must be an object")
        return CodeReviewResult.from_dict(data)
