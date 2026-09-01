"""ZenSkill 技能导出器 — 导出已安装技能清单供 AgentSwarm 同步。

Usage:
    from zenskill.skills.exporter import export_installed_skills
    skills = export_installed_skills()
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Schema 版本（与 specs/skill-schema.yaml 对齐）──────────────
SCHEMA_VERSION = "1.2.0"


def _content_hash(data: Dict[str, Any]) -> str:
    """计算内容哈希，用于增量同步比对。"""
    content = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def export_installed_skills(skills_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """导出已安装技能的清单。

    Args:
        skills_dir: 技能目录，默认 ~/.zenskill/skills/

    Returns:
        技能清单列表，兼容 AgentSwarm skill-schema.yaml 格式
    """
    if skills_dir is None:
        skills_dir = Path.home() / ".zenskill" / "skills"

    if not skills_dir.exists():
        return []

    skills = []
    for skill_path in skills_dir.iterdir():
        if not skill_path.is_dir():
            continue

        manifest = _load_manifest(skill_path)
        if manifest is None:
            continue

        skill_data = _build_export_entry(skill_path, manifest)
        skills.append(skill_data)

    return skills


def _load_manifest(skill_path: Path) -> Optional[Dict[str, Any]]:
    """加载技能 manifest.json。"""
    manifest_path = skill_path / "manifest.json"
    if not manifest_path.exists():
        # 尝试兼容其他格式
        for alt_name in ["skill.json", "package.json", "pyproject.toml"]:
            alt_path = skill_path / alt_name
            if alt_path.exists():
                return _parse_alternative_manifest(alt_path)
        # SKILL.md 目录（P1-2: 第五种来源）
        skill_md = skill_path / "SKILL.md"
        if skill_md.exists():
            from .frontmatter import parse_skill_md

            meta, _body = parse_skill_md(skill_md)
            if meta.name:
                return {
                    "name": meta.name,
                    "version": meta.version or "0.1.0",
                    "description": meta.description,
                    "tags": meta.tags,
                }
        return None

    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _parse_alternative_manifest(path: Path) -> Optional[Dict[str, Any]]:
    """解析非标准 manifest 格式。"""
    if path.name == "pyproject.toml":
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                return None
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
            project = data.get("project", {})
            return {
                "name": project.get("name", path.parent.name),
                "version": project.get("version", "0.0.0"),
                "description": project.get("description", ""),
            }
        except Exception:
            return None

    if path.name == "package.json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "name": data.get("name", path.parent.name),
                "version": data.get("version", "0.0.0"),
                "description": data.get("description", ""),
            }
        except (json.JSONDecodeError, OSError):
            return None

    return None


def _build_export_entry(skill_path: Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """构建导出条目。"""
    name = manifest.get("name", skill_path.name)
    version = manifest.get("version", "0.0.0")
    description = manifest.get("description", "")

    # 检测来源
    source = _detect_source(skill_path, manifest)

    # 构建 content_hash
    content_data = {"name": name, "version": version, "description": description}
    hash_val = _content_hash(content_data)

    entry = {
        "name": name,
        "description": description,
        "metadata": manifest.get("metadata", {
            "type": "executor",
            "role": "general",
            "level": "L2",
        }),
        "source": {
            "market": source.get("market", "builtin"),
            "url": source.get("url", ""),
            "format": source.get("format", ""),
            "license": manifest.get("license", ""),
            "schema_version": SCHEMA_VERSION,
            "content_hash": hash_val,
            "installed_at": datetime.now().isoformat(),
            "install_method": source.get("install_method", "auto"),
        },
    }

    return entry


def _detect_source(skill_path: Path, manifest: Dict[str, Any]) -> Dict[str, str]:
    """检测技能来源。"""
    source_info = manifest.get("source", {})

    if source_info.get("market"):
        return source_info

    # 从路径推断
    path_str = str(skill_path)
    if ".zenskill/cache/github" in path_str:
        return {"market": "github", "install_method": "auto"}
    if ".zenskill/cache/npm" in path_str:
        return {"market": "npm", "install_method": "auto"}
    if ".zenskill/cache/pypi" in path_str:
        return {"market": "pypi", "install_method": "auto"}

    return {"market": "builtin", "install_method": "manual"}


def export_as_json(skills_dir: Optional[Path] = None) -> str:
    """导出为 JSON 字符串。"""
    skills = export_installed_skills(skills_dir)
    return json.dumps(skills, ensure_ascii=False, indent=2)
