"""安全扫描器（W2，解 G3）— 纯静态规则引擎，绝不执行被扫描代码。

规则集见 docs/skill_market_integration_plan.md 第四章（含 S3 补强 SEC-011）。
SEC-001 域名白名单可用环境变量 ZENSKILL_NETWORK_WHITELIST 追加（逗号分隔），
命中白名单的 URL 不计 findings（降 info）。
每规则每文件至多产出一条 finding，取首个命中行，evidence 截断 80 字符。
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import List, Optional, Tuple, Union

SEVERITY = {
    "SEC-001": "critical",
    "SEC-002": "critical",
    "SEC-003": "high",
    "SEC-004": "high",
    "SEC-005": "high",
    "SEC-006": "medium",
    "SEC-007": "medium",
    "SEC-008": "medium",
    "SEC-009": "low",
    "SEC-010": "low",
    "SEC-011": "medium",
}

_MESSAGES = {
    "SEC-001": "网络外发：向非白名单域发送数据",
    "SEC-002": "执行注入：动态执行/解码后执行/shell 拼接",
    "SEC-003": "破坏命令：rm -rf / dd / mkfs / chmod -R 777 等",
    "SEC-004": "持久化/提权：写 shell rc / crontab / systemd / PATH 前置",
    "SEC-005": "zip slip：路径穿越条目或 symlink 指向技能根外",
    "SEC-006": "prompt injection：覆盖指令/伪造系统标记/指示外传密钥",
    "SEC-007": "隐藏内容：零宽字符或超长 base64 块",
    "SEC-008": "资源炸弹：单文件/总量/文件数超限",
    "SEC-009": "声明不一致：frontmatter 未声明 scripts 但存在 scripts/ 目录",
    "SEC-010": "硬编码凭证：token/API key 模式",
    "SEC-011": "多阶段载荷：指示下载/拉取远程内容并执行",
}

DEFAULT_NETWORK_WHITELIST = frozenset({
    "github.com",
    "raw.githubusercontent.com",
    "api.skillhub.cn",
    "pypi.org",
    "npmjs.org",
})

MAX_SINGLE_FILE = 10 * 1024 * 1024      # 10MB
MAX_MD_FILE = 1024 * 1024               # .md 限 1MB
MAX_TOTAL_SIZE = 50 * 1024 * 1024       # 总量 50MB
MAX_FILE_COUNT = 500
EVIDENCE_MAX = 80

_SCRIPT_SUFFIXES = {".py", ".sh", ".js"}
_TEXT_SUFFIXES = _SCRIPT_SUFFIXES | {
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".cfg",
    ".ini", ".html", ".css", ".xml", ".csv", ".rst",
}

# ── SEC-001 网络外发 ──
_URL_RE = re.compile(r"https?://[^\"'\s\)\]<>]+")
_CURL_EGRESS_RE = re.compile(r"\bcurl\b")
_CURL_SEND_RE = re.compile(
    r"--data|(?<![\w-])-d\b|-F\b|--form|--upload-file|(?<![\w-])-T\b"
    r"|-X\s*POST|--request\s*POST|--json")
_WGET_RE = re.compile(r"\bwget\b")
_WGET_SEND_RE = re.compile(r"--post-data|--post-file")
_PY_POST_RE = re.compile(r"\b(?:requests|httpx|aiohttp)\b[\w.]*\.post\s*\(")
_INLINE_POST_RE = re.compile(r"\.(?:post|put)\s*\(\s*['\"]https?://")
_NET_CMD_RE = re.compile(r"\b(?:curl|wget|requests|httpx|aiohttp|urllib)\b")
# "泛读敏感文件"（窃取面）：遍历性读取密钥/凭据存储。显式命名服务方 env
# 凭据（GITHUB_TOKEN/OPENAI_API_KEY 等用户主动配置项）不在此列——技能引用
# 自家服务凭据是正常配置模式（生产实测 9 个 dangerous 误报源：github 系
# scripts 读 token 调 API 是功能本质，静态层无法与窃取区分的边界）。
_SENSITIVE_PATH_RE = re.compile(
    r"\.ssh\b|id_rsa|id_ed25519|\.aws\b|\.gnupg|\.netrc|\.git-credentials"
    r"|\bcredentials\.json\b|/root/\.|~/\.*(ssh|aws|gnupg)",
    re.IGNORECASE)

# ── SEC-002 执行注入 ──
_EVAL_EXEC_RE = re.compile(r"\b(?:eval|exec)\s*\(")
_B64_PIPE_RE = re.compile(r"base64\s+(?:-\w*\s*)*(-d|--decode)\b")
_SHELL_TRUE_RE = re.compile(r"shell\s*=\s*True")
_PY_DECODE_RE = re.compile(r"b64decode|fromhex|unhexlify|a85decode|b32decode")

# ── SEC-003 破坏命令 ──
_RM_TOKEN_RE = re.compile(r"\brm\b")
_FLAG_RE_TMPL = r"(?:^|\s)-{{1,2}}[a-zA-Z-]*{}"
_DD_OF_RE = re.compile(r"\bdd\b[^\n#]*\bof=")
_MKFS_RE = re.compile(r"\bmkfs(?:\.\w+)?\b")
_CHMOD_777_RE = re.compile(r"chmod\s+(?:-R|--recursive)[^\n#]*\s777\b")
_DEV_REDIRECT_RE = re.compile(r">\s*/dev/(?:sd|hd|nvme|vd)")


def _is_rm_rf(line: str) -> bool:
    m = _RM_TOKEN_RE.search(line)
    if not m:
        return False
    rest = line[m.end():]
    has_r = re.search(_FLAG_RE_TMPL.format("r"), rest) is not None
    has_f = re.search(_FLAG_RE_TMPL.format("f"), rest) is not None
    return has_r and has_f

# ── SEC-004 持久化/提权 ──
_RC_WRITE_RE = re.compile(r"(?:>>?|\btee\b[^\n]*)[^\n#]*(?:bashrc|zshrc|bash_profile|zprofile)")
_CRONTAB_RE = re.compile(r"\|\s*crontab\b|crontab\s+\S+\.(?:sh|txt|cron)\b|crontab\s+-\s*$")
_SYSTEMD_RE = re.compile(
    r"\.config/systemd/user|/etc/systemd/system|>\s*[^\n]*\.service\b"
    r"|systemctl\s+(?:--user\s+)?(?:enable|start)\s+\S+\.service")
_PATH_PREPEND_RE = re.compile(r"PATH\s*=\s*[\"']?[^\"'\n]*\$PATH", re.IGNORECASE)
_PATH_SAFE_PREFIX_RE = re.compile(r"PATH\s*=\s*[\"']?/(?:usr|bin|sbin|opt|etc|local)")
_PATH_HIJACK_RE = re.compile(r"[.~]|\$HOME|/tmp")

# ── SEC-006 prompt injection ──
_INJECTION_RES = (
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions?|rules?|prompts?)", re.I),
    re.compile(r"disregard\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above)?\s*instructions", re.I),
    re.compile(r"</?(?:system|im_start|im_end|endoftext)>", re.I),
    re.compile(r"(?:~/.ssh|id_rsa|\.env\b|credentials)[^\n]{0,80}(?:send|upload|post|exfiltrate|发送|上传)", re.I),
    re.compile(r"(?:send|upload|post|exfiltrate|发送|上传)[^\n]{0,80}(?:~/.ssh|id_rsa|\.env\b|credentials)", re.I),
)

# ── SEC-007 隐藏内容 ──
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff\u202e]")
_LONG_B64_RE = re.compile(r"[A-Za-z0-9+/]{1025,}={0,2}")

# ── SEC-010 硬编码凭证 ──
_CRED_RES = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"\bsk-[A-Za-z0-9]{20}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"\bxox[bp]-"),
)

# ── SEC-011 多阶段载荷 ──
_REMOTE_PAYLOAD_RES = (
    re.compile(r"\b(?:curl|wget)\b[^\n|]*\|[^\n]*\b(?:ba)?sh\b"),
    re.compile(r"拉取最新(?:指令|命令|规则|载荷|payload)"),
    re.compile(r"(?:去|请|先)[^\n]{0,30}拉取[^\n]{0,30}(?:执行|运行)"),
    re.compile(r"raw\.githubusercontent\.com[^\n]{0,120}(?:执行|运行|\bbash\b|\bsh\b)"),
    re.compile(r"(?:下载|执行|运行)[^\n]{0,40}远程(?:指令|脚本|载荷)"),
)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_SCRIPTS_DECLARED_RE = re.compile(r"^scripts\s*:", re.MULTILINE)
_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:")


@dataclass
class SecurityFinding:
    rule_id: str
    severity: str
    file: str
    line: int
    message: str
    evidence: str


@dataclass
class SecurityReport:
    skill_id: str
    risk_level: str                 # safe / warn / dangerous
    findings: List[SecurityFinding] = field(default_factory=list)
    scanned_files: int = 0
    skipped: List[str] = field(default_factory=list)
    duration_ms: int = 0


def network_whitelist() -> frozenset:
    """SEC-001 域名白名单：默认集 + 环境变量 ZENSKILL_NETWORK_WHITELIST（逗号分隔）。"""
    extra = os.environ.get("ZENSKILL_NETWORK_WHITELIST", "")
    domains = set(DEFAULT_NETWORK_WHITELIST)
    for d in extra.split(","):
        d = d.strip().lower()
        if d:
            domains.add(d)
    return frozenset(domains)


def _rel_posix(p: Path, root: Path) -> str:
    """相对路径统一 POSIX 分隔符输出（Windows 上 relative_to 得到反斜杠）。"""
    return "/".join(p.relative_to(root).parts)


def check_entry_name(name: str) -> bool:
    """条目名安全性：True=安全。拒绝 .. 段、绝对路径（含 Windows 盘符）。"""
    norm = name.replace("\\", "/")
    if norm.startswith("/") or _WINDOWS_ABS_RE.match(norm):
        return False
    return all(part != ".." for part in PurePosixPath(norm).parts)


def _domain_allowed(url: str, whitelist: frozenset) -> bool:
    m = re.match(r"https?://([^/:]+)", url)
    if not m:
        return True
    host = m.group(1).lower()
    return any(host == d or host.endswith("." + d) for d in whitelist)


def _is_egress_line(line: str) -> bool:
    if _CURL_EGRESS_RE.search(line) and _CURL_SEND_RE.search(line):
        return True
    if _WGET_RE.search(line) and _WGET_SEND_RE.search(line):
        return True
    if _PY_POST_RE.search(line) or _INLINE_POST_RE.search(line):
        return True
    return False


def _ev(line: str) -> str:
    s = line.strip()
    return s[:EVIDENCE_MAX] + ("…" if len(s) > EVIDENCE_MAX else "")


def _emit(findings: List[SecurityFinding], rule_id: str, rel: str,
          hits: List[Tuple[int, str]], message: Optional[str] = None,
          severity: Optional[str] = None) -> None:
    if not hits:
        return
    line, raw = hits[0]
    base = message or _MESSAGES[rule_id]
    sev = severity or SEVERITY[rule_id]
    findings.append(SecurityFinding(
        rule_id=rule_id,
        severity=sev,
        file=rel,
        line=line,
        message=base,
        evidence=_ev(raw),
    ))


def _extract_code_blocks(content: str) -> List[Tuple[int, List[str]]]:
    """提取 SKILL.md fenced 代码块，返回 [(起始行号, [块内各行]), ...]。"""
    blocks: List[Tuple[int, List[str]]] = []
    lines = content.split("\n")
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("```"):
            i += 1
            start = i + 1  # 1-based 行号
            block: List[str] = []
            while i < len(lines) and not lines[i].lstrip().startswith("```"):
                block.append(lines[i])
                i += 1
            blocks.append((start, block))
        i += 1
    return blocks


def _scan_egress(rel: str, numbered: List[Tuple[int, str]],
                 whitelist: frozenset,
                 md_context: bool = False) -> List[SecurityFinding]:
    """SEC-001：行级外发到非白名单域；敏感路径读取+网络发送组合判 critical。"""
    egress_hits: List[Tuple[int, str]] = []
    sensitive_hit: Optional[Tuple[int, str]] = None
    net_seen = False
    for ln, line in numbered:
        if _is_egress_line(line):
            urls = _URL_RE.findall(line)
            if urls and any(not _domain_allowed(u, whitelist) for u in urls):
                egress_hits.append((ln, line))
        if _SENSITIVE_PATH_RE.search(line) and sensitive_hit is None:
            sensitive_hit = (ln, line)
        if _NET_CMD_RE.search(line):
            net_seen = True
    findings: List[SecurityFinding] = []
    if egress_hits:
        if md_context:
            _emit(findings, "SEC-001", rel, egress_hits,
                  severity="medium",
                  message="网络外发（文档示例级）：代码块向非白名单域发送——"
                          "功能 API 示例常见，warn 确认流人工审")
        else:
            _emit(findings, "SEC-001", rel, egress_hits)
    elif sensitive_hit is not None and net_seen:
        _emit(findings, "SEC-001", rel, [sensitive_hit],
              message="网络外发：读取敏感路径与网络发送组合（数据外传）")
    return findings


def _emit_or(hits: List[Tuple[int, str]], rel: str) -> List[SecurityFinding]:
    findings: List[SecurityFinding] = []
    _emit(findings, "SEC-002", rel, hits)
    return findings


def _scan_destructive(rel: str, numbered: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    hits: List[Tuple[int, str]] = []
    for ln, line in numbered:
        if (_is_rm_rf(line) or _DD_OF_RE.search(line) or _MKFS_RE.search(line)
                or _CHMOD_777_RE.search(line) or _DEV_REDIRECT_RE.search(line)):
            hits.append((ln, line))
    return hits


def _scan_persistence(rel: str, numbered: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    hits: List[Tuple[int, str]] = []
    for ln, line in numbered:
        if (_RC_WRITE_RE.search(line) or _CRONTAB_RE.search(line)
                or _SYSTEMD_RE.search(line)):
            hits.append((ln, line))
            continue
        if _PATH_PREPEND_RE.search(line) and not _PATH_SAFE_PREFIX_RE.search(line):
            if _PATH_HIJACK_RE.search(line.split("$PATH")[0]):
                hits.append((ln, line))
    return hits


def _scan_credentials(rel: str, numbered: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    hits: List[Tuple[int, str]] = []
    for ln, line in numbered:
        if any(p.search(line) for p in _CRED_RES):
            hits.append((ln, line))
    return hits


def _scan_injection(rel: str, numbered: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    hits: List[Tuple[int, str]] = []
    for ln, line in numbered:
        if any(p.search(line) for p in _INJECTION_RES):
            hits.append((ln, line))
    return hits


def _scan_hidden(rel: str, numbered: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    hits: List[Tuple[int, str]] = []
    for ln, line in numbered:
        if _ZERO_WIDTH_RE.search(line):
            hits.append((ln, line))
        for m in _LONG_B64_RE.finditer(line):
            hits.append((ln, m.group(0)[:EVIDENCE_MAX]))
            break
    return hits


def _scan_remote_payload(rel: str, numbered: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    hits: List[Tuple[int, str]] = []
    for ln, line in numbered:
        if any(p.search(line) for p in _REMOTE_PAYLOAD_RES):
            hits.append((ln, line))
    return hits


def _numbered(text: str) -> List[Tuple[int, str]]:
    return [(i + 1, line) for i, line in enumerate(text.split("\n"))]


def _scan_skill_md(rel: str, content: str, whitelist: frozenset,
                   has_scripts_dir: bool) -> List[SecurityFinding]:
    findings: List[SecurityFinding] = []
    code_lines: List[Tuple[int, str]] = []
    for start, block in _extract_code_blocks(content):
        code_lines.extend((start + i, line) for i, line in enumerate(block))
    # 文档示例级统一降档（medium）：SKILL.md 代码块是"教 agent 怎么做"的示例，
    # 不是可执行载荷——linux 管理技能教 rm -rf、python 技能演示 exec 均属功能
    # 说明；scripts/ 下的真实代码仍按原 severity（实锤）。生产 338 技能实测：
    # 该原则消除 github/linux 系合法技能的 dangerous 误报（评审#5 的推广）。
    findings.extend(_scan_egress(rel, code_lines, whitelist, md_context=True))
    for _rid, _hits in (("SEC-002", _scan_exec_injection_lines(code_lines)),
                        ("SEC-003", _scan_destructive(rel, code_lines)),
                        ("SEC-004", _scan_persistence(rel, code_lines))):
        _emit(findings, _rid, rel, _hits, severity="medium",
              message=f"{_MESSAGES[_rid]}（文档示例级：SKILL.md 代码块演示，"
                      f"非 scripts 可执行载荷）")

    all_lines = _numbered(content)
    _emit(findings, "SEC-006", rel, _scan_injection(rel, all_lines))
    _emit(findings, "SEC-007", rel, _scan_hidden(rel, all_lines))
    _emit(findings, "SEC-010", rel, _scan_credentials(rel, all_lines))
    _emit(findings, "SEC-011", rel, _scan_remote_payload(rel, all_lines))

    m = _FRONTMATTER_RE.match(content)
    if m and has_scripts_dir and not _SCRIPTS_DECLARED_RE.search(m.group(1)):
        findings.append(SecurityFinding(
            "SEC-009", SEVERITY["SEC-009"], rel, 1, _MESSAGES["SEC-009"],
            "scripts/ 目录存在但 frontmatter 未声明 scripts 字段"))
    return findings


def _scan_exec_injection_lines(numbered: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    hits: List[Tuple[int, str]] = []
    decode_hit: Optional[Tuple[int, str]] = None
    exec_seen = False
    for ln, line in numbered:
        if _EVAL_EXEC_RE.search(line) or _SHELL_TRUE_RE.search(line):
            hits.append((ln, line))
            exec_seen = True
        if _B64_PIPE_RE.search(line) and re.search(r"\||\b(?:ba)?sh\b|\bpython", line):
            hits.append((ln, line))
            exec_seen = True
        if _PY_DECODE_RE.search(line) and decode_hit is None:
            decode_hit = (ln, line)
        if exec_seen and decode_hit is not None:
            hits.append(decode_hit)
            decode_hit = None
    return hits


def _scan_script(rel: str, content: str, whitelist: frozenset) -> List[SecurityFinding]:
    findings: List[SecurityFinding] = []
    numbered = _numbered(content)
    findings.extend(_scan_egress(rel, numbered, whitelist))
    _emit(findings, "SEC-002", rel, _scan_exec_injection_lines(numbered))
    _emit(findings, "SEC-003", rel, _scan_destructive(rel, numbered))
    _emit(findings, "SEC-004", rel, _scan_persistence(rel, numbered))
    _emit(findings, "SEC-010", rel, _scan_credentials(rel, numbered))
    return findings


def _risk_level(findings: List[SecurityFinding]) -> str:
    severities = {f.severity for f in findings}
    if severities & {"critical", "high"}:
        return "dangerous"
    if "medium" in severities:
        return "warn"
    return "safe"


def scan_directory(path: Union[Path, str]) -> SecurityReport:
    """对已解压技能目录做全量静态扫描（不执行任何被扫描代码）。"""
    start = time.perf_counter()
    root = Path(path)
    findings: List[SecurityFinding] = []
    skipped: List[str] = []
    scanned = 0
    whitelist = network_whitelist()

    entries = sorted(root.rglob("*"))
    file_entries = [p for p in entries if p.is_file() or p.is_symlink()]

    # SEC-005：条目名路径审查 + symlink 出逃（方案：fetch 已硬拒，此为双保险）
    for p in file_entries:
        rel = _rel_posix(p, root)
        if not check_entry_name(rel):
            findings.append(SecurityFinding(
                "SEC-005", SEVERITY["SEC-005"], rel, 0, _MESSAGES["SEC-005"],
                _ev(rel)))
        elif p.is_symlink():
            try:
                target = p.resolve()
                inside = target.is_relative_to(root.resolve())
            except OSError:
                inside = False
            if not inside:
                findings.append(SecurityFinding(
                    "SEC-005", SEVERITY["SEC-005"], rel, 0,
                    "zip slip：symlink 指向技能根外", _ev(f"{rel} -> {os.readlink(p)}")))

    # SEC-008：文件数超限直接短路（方案：>500 拒绝短路，仅保留路径审查）
    if len(file_entries) > MAX_FILE_COUNT:
        findings.append(SecurityFinding(
            "SEC-008", SEVERITY["SEC-008"], "SKILL.md", 1,
            f"资源炸弹：文件数 {len(file_entries)} 超过 {MAX_FILE_COUNT}",
            f"{len(file_entries)} files"))
        skipped.extend(_rel_posix(p, root) for p in file_entries)
        file_entries = []

    # SEC-008：单文件/总量限额
    total_size = 0
    total_overflow = False
    content_files: List[Path] = []
    for p in file_entries:
        rel = _rel_posix(p, root)
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        total_size += size
        if size > MAX_SINGLE_FILE or (p.suffix.lower() == ".md" and size > MAX_MD_FILE):
            findings.append(SecurityFinding(
                "SEC-008", SEVERITY["SEC-008"], rel, 0,
                f"资源炸弹：单文件 {size} 字节超限"
                f"（{'md 限 1MB' if p.suffix.lower() == '.md' else '限 10MB'}）",
                f"{size} bytes"))
            skipped.append(rel)
            continue
        if not total_overflow and total_size > MAX_TOTAL_SIZE:
            findings.append(SecurityFinding(
                "SEC-008", SEVERITY["SEC-008"], rel, 0,
                f"资源炸弹：总大小 {total_size} 字节超过 {MAX_TOTAL_SIZE}",
                f"{total_size} bytes"))
            total_overflow = True
        if total_overflow:
            skipped.append(rel)
            continue
        content_files.append(p)

    has_scripts_dir = (root / "scripts").is_dir()

    for p in content_files:
        rel = _rel_posix(p, root)
        suffix = p.suffix.lower()
        try:
            content = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            skipped.append(rel)
            continue
        scanned += 1
        if p.name == "SKILL.md":
            findings.extend(_scan_skill_md(rel, content, whitelist, has_scripts_dir))
        elif suffix in _SCRIPT_SUFFIXES and Path(*p.relative_to(root).parts[:1]) == Path("scripts"):
            findings.extend(_scan_script(rel, content, whitelist))
        elif suffix in _TEXT_SUFFIXES:
            _emit(findings, "SEC-010", rel, _scan_credentials(rel, _numbered(content)))

    return SecurityReport(
        skill_id=root.name,
        risk_level=_risk_level(findings),
        findings=findings,
        scanned_files=scanned,
        skipped=skipped,
        duration_ms=int((time.perf_counter() - start) * 1000),
    )
