"""Craft Projects CRUD（W3.4）— 对齐 vendor ProjectConfig 格式。

路径: {workspace_root}/projects/{slug}/config.json + assets/
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Optional


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "-", name.lower().strip())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or f"project-{int(time.time())}"


class ProjectsStore:
    def __init__(self, workspace_root: str | Path):
        self._root = Path(workspace_root) / "projects"

    def _project_dir(self, slug: str) -> Path:
        return self._root / slug

    def _config_path(self, slug: str) -> Path:
        return self._project_dir(slug) / "config.json"

    def list(self) -> list[dict]:
        if not self._root.is_dir():
            return []
        result = []
        for d in sorted(self._root.iterdir()):
            cfg_path = d / "config.json"
            if d.is_dir() and cfg_path.exists():
                try:
                    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                    result.append(cfg)
                except Exception:
                    pass
        return result

    def get_one(self, slug: str) -> Optional[dict]:
        p = self._config_path(slug)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def create(self, opts: dict) -> dict:
        name = opts.get("name", "Untitled")
        slug = _slugify(name)
        # 冲突处理
        base_slug = slug
        counter = 1
        while self._config_path(slug).exists():
            counter += 1
            slug = f"{base_slug}-{counter}"
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        config = {
            "id": f"proj_{slug}",
            "slug": slug,
            "name": name,
            "description": opts.get("description", ""),
            "workingDirectory": opts.get("workingDirectory", ""),
            "details": opts.get("details", ""),
            "colorTheme": opts.get("colorTheme", ""),
            "color": opts.get("color", ""),
            "createdAt": now,
            "updatedAt": now,
        }
        cfg_dir = self._project_dir(slug)
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        (cfg_dir / "assets").mkdir(exist_ok=True)
        (cfg_dir / "MEMORY.md").write_text(f"# {name}\n", encoding="utf-8")
        return config

    def update(self, slug: str, patch: dict) -> Optional[dict]:
        config = self.get_one(slug)
        if not config:
            return None
        for k in ("name", "description", "workingDirectory", "details", "colorTheme", "color"):
            if k in patch:
                config[k] = patch[k]
        if "kanbanColumns" in patch:
            config["kanbanColumns"] = patch["kanbanColumns"]
        config["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._config_path(slug).write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        return config

    def delete(self, slug: str) -> bool:
        import shutil
        d = self._project_dir(slug)
        if d.is_dir():
            shutil.rmtree(d)
            return True
        return False

    def list_assets(self, slug: str) -> list[dict]:
        assets_dir = self._project_dir(slug) / "assets"
        if not assets_dir.is_dir():
            return []
        result = []
        for f in sorted(assets_dir.iterdir()):
            if f.is_file():
                stat = f.stat()
                import mimetypes
                result.append({
                    "filename": f.name,
                    "sizeBytes": stat.st_size,
                    "mimeType": mimetypes.guess_type(str(f))[0] or "application/octet-stream",
                    "uploadedAt": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime)),
                    "absolutePath": str(f),
                })
        return result
