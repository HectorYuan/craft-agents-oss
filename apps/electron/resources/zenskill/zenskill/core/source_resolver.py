"""ZenSkill source 解析器 — canonical slug 指纹发现与旧 slug 迁移

命名规范：
  canonical slug = "zenskill"（无后缀、全平台一致、永不变）
  display name   = config.json 的 name 字段（用户可改，不影响路由）
  旧 slug        = zenskill-2/3/4...（开发期碰撞计数器残留，启动时自动迁移）

判定方式不依赖 slug 字符串本身，而是依赖 config 指纹：
  type == "mcp" and "zenskill" in mcp.command

用法：
  from zenskill.core.source_resolver import resolve_zenskill_source
  slug = resolve_zenskill_source(workspace_root)   # → "zenskill"（迁移后）
  guide_path = resolve_zenskill_guide_path(workspace_root)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

CANONICAL_SLUG = "zenskill"
_FALLBACK_SLUG = "zenskill-official"
_SOURCE_FINGERPRINT_COMMAND = "zenskill"
_MARKER_FILE = ".zenskill_source"


def _is_zenskill_source(config: dict) -> bool:
    """config 指纹：type=mcp 且 command 含 zenskill"""
    if not isinstance(config, dict):
        return False
    if config.get("type") != "mcp":
        return False
    mcp = config.get("mcp", {})
    command = mcp.get("command", "")
    return _SOURCE_FINGERPRINT_COMMAND in command


def _read_source_config(source_dir: Path) -> dict | None:
    config_path = source_dir / "config.json"
    if not config_path.exists():
        return None
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _list_source_dirs(workspace_root: Path) -> list[Path]:
    sources_dir = workspace_root / "sources"
    if not sources_dir.exists():
        return []
    return sorted(d for d in sources_dir.iterdir() if d.is_dir())


def _write_marker(source_dir: Path, slug: str) -> None:
    """在 source 目录内写标记文件，加速后续指纹发现"""
    marker = source_dir / _MARKER_FILE
    if not marker.exists():
        try:
            marker.write_text(slug, encoding="utf-8")
        except Exception:
            pass


def _has_marker(source_dir: Path) -> bool:
    return (source_dir / _MARKER_FILE).exists()


def migrate_legacy_slugs(workspace_root: Path) -> list[str]:
    """把旧 zenskill-N 目录重命名为 canonical slug（幂等，启动时调用一次）。

    返回迁移的旧 slug 列表（空 = 无需迁移或已迁移）。
    """
    migrated = []
    canonical_dir = workspace_root / "sources" / CANONICAL_SLUG

    # canonical 已存在 → 无需迁移
    if canonical_dir.exists() and _has_marker(canonical_dir):
        return migrated

    for source_dir in _list_source_dirs(workspace_root):
        config = _read_source_config(source_dir)
        if config is None or not _is_zenskill_source(config):
            continue
        if source_dir.name == CANONICAL_SLUG:
            _write_marker(source_dir, CANONICAL_SLUG)
            continue
        # 旧 slug → 重命名
        if canonical_dir.exists():
            # canonical 目录被占用但无标记（可能是空壳）→ 跳过
            logger.warning(
                "canonical dir %s exists without marker, skip migration of %s",
                canonical_dir, source_dir.name,
            )
            continue
        try:
            shutil.move(str(source_dir), str(canonical_dir))
            # 更新 config.json 的 slug/id
            migrated_config = _read_source_config(canonical_dir)
            if migrated_config:
                migrated_config["slug"] = CANONICAL_SLUG
                if migrated_config.get("id", "").startswith(source_dir.name):
                    migrated_config["id"] = CANONICAL_SLUG
                config_path = canonical_dir / "config.json"
                config_path.write_text(
                    json.dumps(migrated_config, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            _write_marker(canonical_dir, CANONICAL_SLUG)
            migrated.append(source_dir.name)
            logger.info("migrated source %s → %s", source_dir.name, CANONICAL_SLUG)
        except Exception:
            logger.exception("failed to migrate %s", source_dir.name)

    return migrated


def resolve_zenskill_source(workspace_root: Path | str) -> str | None:
    """指纹发现 ZenSkill source 的 slug（不触发迁移）。

    优先级：标记文件 > config 指纹 > None
    """
    root = Path(workspace_root)
    for source_dir in _list_source_dirs(root):
        # 快速路径：标记文件
        if _has_marker(source_dir) and source_dir.name in (CANONICAL_SLUG,):
            return source_dir.name
        config = _read_source_config(source_dir)
        if config is not None and _is_zenskill_source(config):
            _write_marker(source_dir, source_dir.name)
            return source_dir.name
    return None


def resolve_or_migrate(workspace_root: Path | str) -> str:
    """入口函数：迁移旧 slug + 指纹发现 + canonical fallback。永不返回 None。"""
    root = Path(workspace_root)
    migrate_legacy_slugs(root)
    slug = resolve_zenskill_source(root)
    if slug:
        return slug

    # 无 source → 返回 canonical（后续 createSource 会用这个名字）
    logger.warning(
        "no zenskill source found in %s, returning canonical slug %s",
        root, CANONICAL_SLUG,
    )
    return CANONICAL_SLUG


def resolve_zenskill_source_dir(workspace_root: Path | str) -> Path | None:
    """返回 ZenSkill source 的目录路径（含 config.json + guide.md）"""
    root = Path(workspace_root)
    slug = resolve_zenskill_source(root)
    if slug is None:
        return None
    source_dir = root / "sources" / slug
    return source_dir if source_dir.exists() else None


def resolve_zenskill_guide_path(workspace_root: Path | str) -> Path | None:
    """返回 guide.md 的完整路径"""
    source_dir = resolve_zenskill_source_dir(workspace_root)
    if source_dir is None:
        return None
    guide = source_dir / "guide.md"
    return guide if guide.exists() else None
