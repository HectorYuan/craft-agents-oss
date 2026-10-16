"""SKILL.md frontmatter v2 校验（W2 共享抽取）。

从 registry.py `_skill_validate` 内联实现原样抽出，供 MCP skill_validate 工具
与可用性验证器（U-02）复用。校验逻辑逐行保留、行为等价：

- 目录遍历：跳过隐藏目录与无 SKILL.md 的目录，按目录名排序；
- 必填字段：name/description/category/type（空值/空列表视为缺失）；
- category 九域闭集、type 六类型闭集；
- description 以 "Use when" 开头（大小写不敏感）报错；
- 读取/解析异常归为 ``{slug}: {exc}``。

修改校验规则时同步本模块与 tests/runtime_mcp/test_registry_matrix.py 基准。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Union

import yaml

VALID_CATEGORIES = frozenset({
    "lark", "arkcli", "agentswarm", "dev", "data", "ai",
    "design", "ops", "life", "general",
})
VALID_TYPES = frozenset({
    "execution", "analysis", "creation",
    "coordination", "knowledge", "general",
})
REQUIRED_FIELDS = ("name", "description", "category", "type")

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_USE_WHEN_RE = re.compile(r"^\s*Use when", re.IGNORECASE)


def validate_one(skill_md_path: Union[Path, str]) -> List[str]:
    """校验单个 SKILL.md，返回错误列表（不带 slug 前缀）。

    错误顺序与 validate_all 一致：
    no frontmatter → missing 字段 → bad category → bad type → Use when。
    读取/解析失败直接抛出，由调用方决定错误文案。
    """
    path = Path(skill_md_path)
    content = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return ["no frontmatter"]
    raw = yaml.safe_load(m.group(1)) or {}
    errors: List[str] = []
    for field_name in REQUIRED_FIELDS:
        v = raw.get(field_name)
        if not v or (isinstance(v, list) and not v):
            errors.append(f"missing {field_name}")
    if raw.get("category") not in VALID_CATEGORIES:
        errors.append(f"bad category '{raw.get('category')}'")
    if raw.get("type") not in VALID_TYPES:
        errors.append(f"bad type '{raw.get('type')}'")
    if isinstance(raw.get("description"), str) and _USE_WHEN_RE.match(raw["description"]):
        errors.append("description still starts with 'Use when'")
    return errors


def validate_all(skills_dir: Union[Path, str, None] = None) -> Dict[str, Any]:
    """校验技能目录下全部 SKILL.md，返回 {total, errors, pass}。

    skills_dir 缺省 ``~/.agents/skills``；errors 各项格式为 ``{slug}: {原因}``。
    """
    skills_root = Path(skills_dir) if skills_dir is not None else Path.home() / ".agents" / "skills"
    errors: List[str] = []
    total = 0
    for d in sorted(skills_root.iterdir()):
        sf = d / "SKILL.md"
        if not d.is_dir() or d.name.startswith(".") or not sf.exists():
            continue
        total += 1
        slug = d.name
        try:
            file_errors = validate_one(sf)
        except Exception as exc:
            errors.append(f"{slug}: {exc}")
            continue
        errors.extend(f"{slug}: {e}" for e in file_errors)
    return {"total": total, "errors": errors, "pass": len(errors) == 0}
