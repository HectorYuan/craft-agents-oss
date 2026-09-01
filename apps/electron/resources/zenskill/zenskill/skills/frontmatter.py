"""
SKILL.md frontmatter 统一解析模块 (P0-2)

全仓唯一的 frontmatter 读写入口，支持:
- 标准 YAML 语法（多行值 description: >、列表、嵌套字段）
- 行首 --- 分隔符状态机识别（正文含 --- 不误判）
- 非法 YAML 容错（返回空 meta + 错误列表，不抛异常）
- 必填字段校验（lint 用）

取代 __main__.py 与 platforms/coze.py 中的朴素正则/split 解析。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

_DELIMITER_RE = re.compile(r"^---\s*$")

_KNOWN_KEYS = {
    "name", "description", "version", "author", "tags",
    "dependencies", "license", "allowed-tools", "allowed_tools",
}


@dataclass
class SkillFrontmatter:
    """SKILL.md frontmatter 规范化视图

    未知字段原样保留在 extra 中，读写不丢失。
    """

    name: str = ""
    description: str = ""
    version: Optional[str] = None
    author: Optional[str] = None
    license: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    allowed_tools: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors and bool(self.name) and bool(self.description)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = dict(self.extra)
        d.update({
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "license": self.license,
            "tags": self.tags,
            "dependencies": self.dependencies,
            "allowed-tools": self.allowed_tools,
        })
        return {k: v for k, v in d.items() if v not in (None, [], "")}


def _split_frontmatter(content: str) -> Tuple[Optional[str], str]:
    """行首 --- 状态机分离 frontmatter 与正文

    返回 (frontmatter 文本或 None, 正文)。允许首行前有空白行；
    未找到闭合 --- 时视为无 frontmatter。
    """
    lines = content.split("\n")
    fm_lines: Optional[List[str]] = None
    body_start = 0

    for i, line in enumerate(lines):
        if fm_lines is None:
            if _DELIMITER_RE.match(line.rstrip("\r")):
                fm_lines = []
            elif line.strip():
                return None, content
        else:
            if _DELIMITER_RE.match(line.rstrip("\r")):
                return "\n".join(fm_lines), "\n".join(lines[i + 1:])
            fm_lines.append(line)

    return None, content


def _normalize_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        return str(value.get("key") or value)
    return str(value)


def _normalize_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    if isinstance(value, (list, tuple)):
        return [str(t).strip() for t in value if str(t).strip()]
    return [str(value)]


def _from_raw_dict(raw: Dict[str, Any]) -> SkillFrontmatter:
    allowed = raw.get("allowed-tools") or raw.get("allowed_tools")
    known = {
        "name", "description", "version", "author", "tags",
        "dependencies", "license", "allowed-tools", "allowed_tools",
    }
    return SkillFrontmatter(
        name=_normalize_str(raw.get("name")) or "",
        description=_normalize_str(raw.get("description")) or "",
        version=_normalize_str(raw.get("version")),
        author=_normalize_str(raw.get("author")),
        license=_normalize_str(raw.get("license")),
        tags=_normalize_str_list(raw.get("tags")),
        dependencies=_normalize_str_list(raw.get("dependencies")),
        allowed_tools=_normalize_str_list(allowed),
        extra={k: v for k, v in raw.items() if k not in known},
    )


def parse_skill_md(path: Path | str) -> Tuple[SkillFrontmatter, str]:
    """解析 SKILL.md，返回 (规范化 meta, 正文)

    非法 YAML / 非 mapping 结构时不抛异常，errors 中给出原因。
    """
    content = Path(path).read_text(encoding="utf-8")
    return parse_frontmatter_text(content)


def parse_frontmatter_text(content: str) -> Tuple[SkillFrontmatter, str]:
    fm_text, body = _split_frontmatter(content)
    if fm_text is None:
        return SkillFrontmatter(), body

    try:
        raw = yaml.safe_load(fm_text)
    except yaml.YAMLError as e:
        meta = SkillFrontmatter()
        meta.errors.append(f"frontmatter YAML 解析失败: {e}")
        return meta, body

    if raw is None:
        return SkillFrontmatter(), body
    if not isinstance(raw, dict):
        meta = SkillFrontmatter()
        meta.errors.append(f"frontmatter 不是映射结构: {type(raw).__name__}")
        return meta, body

    return _from_raw_dict(raw), body


def dump_skill_md(path: Path | str, meta: SkillFrontmatter, body: str) -> None:
    """写回 SKILL.md：规范化字段 + extra 合并序列化"""
    raw = dict(meta.extra)
    raw.update({
        "name": meta.name,
        "description": meta.description,
        "version": meta.version,
        "author": meta.author,
        "license": meta.license,
        "tags": meta.tags,
        "dependencies": meta.dependencies,
        "allowed-tools": meta.allowed_tools,
    })
    raw = {k: v for k, v in raw.items() if v not in (None, [], "")}

    fm_yaml = yaml.dump(
        raw, default_flow_style=False, allow_unicode=True, sort_keys=False
    )
    Path(path).write_text(f"---\n{fm_yaml}---\n{body}", encoding="utf-8")


def validate_frontmatter(meta: SkillFrontmatter) -> List[str]:
    """lint 校验：返回错误列表（空列表 = 通过）"""
    errors = list(meta.errors)

    if not meta.name:
        errors.append("缺少必填字段 name")
    if not meta.description:
        errors.append("缺少必填字段 description")
    if meta.version is not None and not re.match(
        r"^\d+(\.\d+){0,3}([-+][\w.]+)?$", meta.version
    ):
        errors.append(f"version 格式非语义化版本: {meta.version!r}")

    return errors
