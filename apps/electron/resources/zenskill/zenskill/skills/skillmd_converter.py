"""SKILL.md ↔ SkillSpec 双向转换器 (P1-2)

单一字段映射表 FIELD_MAPS 双向共用:
- frontmatter ↔ SkillSpec（from_skill_md / to_skill_md）
- SkillSpec/manifest → 各平台 manifest（generate_platform_manifest，
  取代 deploy 手写字段改名代码）

平台差异规则（模板拼接，不引入 LLM）:
- allowed-tools 仅 Claude 系平台输出
- description 按触发机制改写: Claude 侧重「何时使用」，Coze 侧重「用户意图触发词」

v1 限制: references/ 目录内容不进 SSOT（留在源目录），
examples/ 文件路径映射到 spec.examples。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .frontmatter import dump_skill_md, parse_skill_md
from ..core.skill_spec import SkillSpec

CLAUDE_FAMILY = {"claude"}

FRONTMATTER_TO_SPEC = {
    "name": "name",
    "description": "description",
    "version": "version",
    "author": "author",
    "license": "license",
    "tags": "tags",
    "dependencies": "prerequisites",
    "allowed-tools": "tools",
}

PLATFORM_MANIFEST_MAPS: Dict[str, Dict[str, str]] = {
    "local": {
        "id": "@skill_id",
        "name": "name|@skill_id",
        "description": "description|",
        "version": "version|1.0.0",
        "platform": "local",
        "installed_at": "@now",
    },
    "codex": {
        "schema_version": "1.0",
        "name": "@skill_id",
        "description": "description|",
        "tools": "tools|[]",
        "entry_point": "entry_point|main.py",
        "version": "version|1.0.0",
    },
    "cursor": {
        "name": "@skill_id",
        "description": "description|",
        "version": "version|1.0.0",
        "type": "skill",
        "entry": "entry_point|main.py",
    },
    "opencode": {
        "skill_id": "@skill_id",
        "display_name": "name|@skill_id",
        "description": "description|",
        "version": "version|1.0.0",
        "entry": "entry_point|main.py",
    },
}


def _slugify(text: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9-]", "", text.lower().replace(" ", "-").replace("_", "-"))
    return slug[:40] or "skill"


def _first_paragraph(body: str, limit: int = 200) -> str:
    for block in body.split("\n\n"):
        text = block.strip()
        if text and not text.startswith("#"):
            return text[:limit].replace("\n", " ")
    return ""


def from_skill_md(path: Path | str) -> Optional[SkillSpec]:
    """SKILL.md 目录 → SkillSpec（解析失败/缺 name 返回 None）"""
    path = Path(path)

    if path.is_file():
        meta, body = parse_skill_md(path)
    else:
        skill_md = path / "SKILL.md"
        if not skill_md.exists():
            return None
        meta, body = parse_skill_md(skill_md)

    if not meta.name:
        return None

    skill_dir = path if path.is_dir() else path.parent
    examples: List[str] = []
    examples_dir = skill_dir / "examples"
    if examples_dir.is_dir():
        examples = sorted(p.name for p in examples_dir.iterdir() if p.is_file())

    return SkillSpec(
        id=skill_dir.name if skill_dir.name not in ("", ".") else _slugify(meta.name),
        name=meta.name,
        description=meta.description or _first_paragraph(body),
        version=meta.version or "0.1.0",
        author=meta.author or "",
        license=meta.license or "",
        tags=list(meta.tags),
        prerequisites=list(meta.dependencies),
        tools=list(meta.allowed_tools),
        keywords=list(meta.tags)[:10],
        examples=examples,
        source="skillmd",
        source_format="skill-md",
    )


def _platform_description(spec: SkillSpec, platform: str) -> str:
    keywords = "/".join(spec.keywords[:5])
    if platform == "coze":
        return f"触发：当用户提到 {keywords} 时使用。{spec.description}" if keywords else spec.description
    if platform in CLAUDE_FAMILY:
        return f"{spec.description}（适用场景：{keywords}）" if keywords else spec.description
    return spec.description


def _frontmatter_for_platform(spec: SkillSpec, platform: str) -> Dict[str, Any]:
    fm: Dict[str, Any] = {
        "name": spec.name,
        "description": _platform_description(spec, platform),
        "version": spec.version,
    }
    if spec.author:
        fm["author"] = spec.author
    if spec.license:
        fm["license"] = spec.license
    if spec.tags:
        fm["tags"] = list(spec.tags)
    if spec.prerequisites:
        fm["dependencies"] = list(spec.prerequisites)
    if platform in CLAUDE_FAMILY and spec.tools:
        fm["allowed-tools"] = list(spec.tools)
    return fm


def _render_body(spec: SkillSpec) -> str:
    lines = [f"# {spec.name}", "", spec.description, ""]

    if spec.keywords:
        lines += ["## 关键概念", ""]
        lines += [f"- {kw}" for kw in spec.keywords]
        lines.append("")

    if spec.practice_tasks:
        lines += ["## 练习任务", ""]
        for i, task in enumerate(spec.practice_tasks, 1):
            desc = task.get("description", "")
            level = task.get("level", "")
            suffix = f"（{level}）" if level else ""
            lines.append(f"{i}. {desc}{suffix}")
        lines.append("")

    if spec.prerequisites:
        lines += ["## 前置依赖", ""]
        lines += [f"- {dep}" for dep in spec.prerequisites]
        lines.append("")

    return "\n".join(lines) + "\n"


def to_skill_md(
    spec: SkillSpec,
    platform: str = "claude",
    output_dir: Path | str | None = None,
) -> Path:
    """SkillSpec → 目标平台技能目录（SKILL.md；output_dir 时同时写 manifest.json）

    返回技能目录路径；未指定 output_dir 时写到临时目录。
    """
    import tempfile

    from .frontmatter import SkillFrontmatter

    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix=f"zenskill-{platform}-")) / spec.id
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fm = _frontmatter_for_platform(spec, platform)
    meta = SkillFrontmatter(
        name=fm["name"],
        description=fm["description"],
        version=fm.get("version"),
        author=fm.get("author"),
        license=fm.get("license"),
        tags=fm.get("tags", []),
        dependencies=fm.get("dependencies", []),
        allowed_tools=fm.get("allowed-tools", []),
    )
    dump_skill_md(output_dir / "SKILL.md", meta, _render_body(spec))

    if platform in PLATFORM_MANIFEST_MAPS:
        manifest = generate_platform_manifest(
            platform, spec.id, _spec_as_manifest(spec)
        )
        import json

        (output_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    if spec.examples:
        examples_dir = output_dir / "examples"
        examples_dir.mkdir(exist_ok=True)
        for name in spec.examples:
            target = examples_dir / name
            if not target.exists():
                target.write_text("", encoding="utf-8")

    return output_dir


def _spec_as_manifest(spec: SkillSpec) -> Dict[str, Any]:
    return {
        "name": spec.name,
        "description": spec.description,
        "version": spec.version,
        "tools": spec.tools,
        "entry_point": spec.entry_point or "main.py",
    }


def generate_platform_manifest(
    platform: str, skill_id: str, manifest: Dict[str, Any]
) -> Dict[str, Any]:
    """按 FIELD_MAPS 生成平台 manifest（部署管线的唯一字段投影源）"""
    field_map = PLATFORM_MANIFEST_MAPS.get(platform)
    if field_map is None:
        raise KeyError(
            f"Unsupported platform: {platform}. "
            f"Supported: {sorted(PLATFORM_MANIFEST_MAPS.keys())}"
        )

    out: Dict[str, Any] = {}
    for target_key, source in field_map.items():
        if source == "@skill_id":
            out[target_key] = skill_id
        elif source == "@now":
            out[target_key] = time.time()
        elif "|" in source:
            field, default = source.split("|", 1)
            value = manifest.get(field)
            if value in (None, ""):
                value = _resolve_default(default, skill_id)
            out[target_key] = value
        else:
            out[target_key] = source
    return out


def _resolve_default(default: str, skill_id: str) -> Any:
    if default == "@skill_id":
        return skill_id
    if default == "[]":
        return []
    return default
