"""可用性验证器（W2，解 G4）— 与安全扫描器同跑于 staging。

检查项 U-01~U-06 见 docs/skill_market_integration_plan.md 第五章：
broken → gate 拒绝；degraded → 确认流 + fix_hint 补全提示。
U-02 复用 frontmatter_check 的闭集常量，但为六字段校验（含 when/tags），
且只校验单个技能，不做全表扫描。
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

import yaml

from .frontmatter_check import VALID_CATEGORIES, VALID_TYPES

_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_V2_FIELDS = ("name", "description", "category", "type", "when", "tags")
_REF_RE = re.compile(r"(?:scripts|resources)/[\w][\w./-]*", re.IGNORECASE)
_DESC_MIN_LEN = 20
_TEXT_SUFFIXES = {".md", ".py", ".sh", ".js", ".txt", ".json",
                  ".yaml", ".yml", ".toml", ".cfg", ".ini", ".rst"}
_SYNTAX_TIMEOUT = 10


@dataclass
class UsabilityIssue:
    level: str          # broken / degraded
    check: str          # U-01 .. U-06
    message: str
    fix_hint: str


@dataclass
class UsabilityReport:
    skill_id: str
    status: str         # usable / degraded / broken
    issues: List[UsabilityIssue] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)


def _parse_frontmatter(content: str) -> Optional[dict]:
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return None
    raw = yaml.safe_load(m.group(1))
    return raw if isinstance(raw, dict) else None


def _check_structure(root: Path, meta: Optional[dict]) -> List[UsabilityIssue]:
    issues: List[UsabilityIssue] = []
    skill_md = root / "SKILL.md"
    if not skill_md.exists():
        issues.append(UsabilityIssue(
            "broken", "U-01", "SKILL.md 不存在",
            "技能根目录必须包含 SKILL.md（frontmatter + 使用说明）"))
    if meta is None:
        issues.append(UsabilityIssue(
            "broken", "U-01", "frontmatter 缺失或不可解析（YAML 非法/非映射）",
            "SKILL.md 需以 --- 包裹的合法 YAML frontmatter 开头"))
    if not _SLUG_RE.match(root.name):
        issues.append(UsabilityIssue(
            "broken", "U-01", f"目录 slug 非法: {root.name!r}（须匹配 ^[a-z0-9-]+$）",
            "重命名目录为小写字母/数字/连字符组合"))
    return issues


def _check_v2_fields(meta: dict) -> List[UsabilityIssue]:
    issues: List[UsabilityIssue] = []
    for f in _V2_FIELDS:
        v = meta.get(f)
        if not v or (isinstance(v, list) and not v):
            hint = {
                "when": "补充 when: 触发场景描述",
                "tags": "补充 tags: [标签] 列表",
            }.get(f, f"补充必填字段 {f}")
            issues.append(UsabilityIssue(
                "degraded", "U-02", f"frontmatter v2 缺少必填字段 {f}", hint))
    if meta.get("category") not in VALID_CATEGORIES:
        issues.append(UsabilityIssue(
            "degraded", "U-02",
            f"category 非法: {meta.get('category')!r}（须为九域闭集之一）",
            f"category 取值: {', '.join(sorted(VALID_CATEGORIES))}"))
    if meta.get("type") not in VALID_TYPES:
        issues.append(UsabilityIssue(
            "degraded", "U-02",
            f"type 非法: {meta.get('type')!r}（须为六类型闭集之一）",
            f"type 取值: {', '.join(sorted(VALID_TYPES))}"))
    return issues


def _check_references(root: Path, body: str) -> List[UsabilityIssue]:
    issues: List[UsabilityIssue] = []
    for ref in sorted(set(_REF_RE.findall(body))):
        ref = ref.rstrip(".")
        if not (root / ref).exists():
            issues.append(UsabilityIssue(
                "degraded", "U-03", f"SKILL.md 引用的文件不存在: {ref}",
                f"创建 {ref} 或修正引用路径"))
    return issues


def _run_syntax_check(cmd: List[str]) -> Optional[int]:
    """返回退出码；命令不可用返回 None。"""
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=_SYNTAX_TIMEOUT)
        return proc.returncode
    except (subprocess.TimeoutExpired, OSError):
        return None


def _check_scripts(root: Path, skipped: List[str]) -> List[UsabilityIssue]:
    issues: List[UsabilityIssue] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        rel = str(p.relative_to(root))
        suffix = p.suffix.lower()
        if suffix == ".py":
            try:
                ast.parse(p.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError, ValueError) as e:
                issues.append(UsabilityIssue(
                    "broken", "U-04", f"Python 脚本语法错误: {rel} ({e})",
                    f"修复 {rel} 语法后再安装"))
        elif suffix == ".js":
            if shutil.which("node") is None:
                skipped.append(rel)
                continue
            rc = _run_syntax_check(["node", "--check", str(p)])
            if rc is None:
                skipped.append(rel)
            elif rc != 0:
                issues.append(UsabilityIssue(
                    "degraded", "U-04", f"JS 脚本语法检查失败: {rel}",
                    f"node --check {rel} 未通过，修复语法"))
        elif suffix == ".sh":
            rc = _run_syntax_check(["bash", "-n", str(p)])
            if rc is not None and rc != 0:
                issues.append(UsabilityIssue(
                    "degraded", "U-04", f"Shell 脚本语法检查失败: {rel}",
                    f"bash -n {rel} 未通过，修复语法"))
    return issues


def _check_encoding(root: Path) -> List[UsabilityIssue]:
    issues: List[UsabilityIssue] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.is_symlink() or p.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        rel = str(p.relative_to(root))
        data = p.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            issues.append(UsabilityIssue(
                "degraded", "U-05", f"文件含 UTF-8 BOM: {rel}",
                f"重存 {rel} 为无 BOM UTF-8"))
            continue
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            issues.append(UsabilityIssue(
                "degraded", "U-05", f"文件非 UTF-8 编码: {rel}",
                f"将 {rel} 转存为 UTF-8"))
    return issues


def _check_discoverability(root: Path, meta: dict) -> List[UsabilityIssue]:
    issues: List[UsabilityIssue] = []
    name = meta.get("name")
    if not isinstance(name, str) or name != root.name:
        issues.append(UsabilityIssue(
            "degraded", "U-06", f"name 与 slug 不一致: name={name!r} slug={root.name!r}",
            f"frontmatter name 改为 {root.name!r}，保证 skill_retrieve 可命中"))
    desc = meta.get("description")
    if not isinstance(desc, str) or len(desc) < _DESC_MIN_LEN:
        issues.append(UsabilityIssue(
            "degraded", "U-06",
            f"description 过短（<{_DESC_MIN_LEN} 字符），影响检索召回",
            "description 扩写到 20 字符以上，说明技能用途"))
    return issues


def validate_usability(skill_dir: Union[Path, str]) -> UsabilityReport:
    """对单个技能目录做 U-01~U-06 可用性验证。"""
    root = Path(skill_dir)
    skipped: List[str] = []
    issues: List[UsabilityIssue] = []

    skill_md = root / "SKILL.md"
    meta: Optional[dict] = None
    body = ""
    if skill_md.exists():
        try:
            content = skill_md.read_text(encoding="utf-8")
            meta = _parse_frontmatter(content)
            m = _FRONTMATTER_RE.match(content)
            body = content[m.end():] if m else content
        except (UnicodeDecodeError, yaml.YAMLError, OSError):
            meta = None

    issues.extend(_check_structure(root, meta))
    if meta is not None:
        issues.extend(_check_v2_fields(meta))
        issues.extend(_check_discoverability(root, meta))
    if body:
        issues.extend(_check_references(root, body))
    issues.extend(_check_scripts(root, skipped))
    issues.extend(_check_encoding(root))

    if any(i.level == "broken" for i in issues):
        status = "broken"
    elif any(i.level == "degraded" for i in issues):
        status = "degraded"
    else:
        status = "usable"
    return UsabilityReport(
        skill_id=root.name, status=status, issues=issues, skipped=skipped)
