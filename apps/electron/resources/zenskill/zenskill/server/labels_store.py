"""Labels 持久化（P1：labels:list/create/delete 去 stub）。

格式 SSOT: vendor packages/shared/src/labels/types.ts（WorkspaceLabelConfig/LabelConfig/AutoLabelRule）
存储: {workspace_root}/labels/config.json（原子写）

消费方: AppShell / KanbanBoard / NavigationContext / LabelsSettingsPage
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

_LABEL_ID_RE = re.compile(r"^[\w:-]+$")  # slug 含冒号（id::value 带值标签）


class LabelsStore:
    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)
        self._config_path = self.workspace_root / "labels" / "config.json"

    def _load(self) -> dict:
        if not self._config_path.exists():
            return {"version": 1, "labels": []}
        try:
            cfg = json.loads(self._config_path.read_text(encoding="utf-8"))
            if isinstance(cfg, dict) and "labels" in cfg:
                return cfg
        except Exception:
            pass
        return {"version": 1, "labels": []}

    def _save(self, cfg: dict) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self._config_path.parent),
                                   prefix=".config.json.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._config_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def list(self) -> list[dict]:
        return self._load().get("labels", [])

    def create(self, name: str, color: str | None = None,
               parent_id: str | None = None) -> dict:
        if not name or not name.strip():
            raise ValueError("label name is required")
        label_id = name.strip().lower().replace(" ", "-")
        if not _LABEL_ID_RE.match(label_id):
            raise ValueError(f"invalid label id: {label_id}")
        cfg = self._load()
        if self._find(cfg.get("labels", []), label_id):
            raise ValueError(f"label already exists: {label_id}")
        new_label: dict[str, Any] = {"id": label_id, "name": name.strip()}
        if color:
            new_label["color"] = color
        if parent_id:
            parent = self._find(cfg.get("labels", []), parent_id)
            if not parent:
                raise ValueError(f"parent label not found: {parent_id}")
            parent.setdefault("children", []).append(new_label)
        else:
            cfg.setdefault("labels", []).append(new_label)
        self._save(cfg)
        return new_label

    def delete(self, label_id: str) -> bool:
        cfg = self._load()

        def remove_from(labels: list) -> tuple[list, bool]:
            removed = False
            result = []
            for l in labels:
                if l.get("id") == label_id:
                    removed = True
                    continue
                children = l.get("children") or []
                new_children, child_removed = remove_from(children)
                if child_removed:
                    l["children"] = new_children
                    removed = True
                result.append(l)
            return result, removed

        new_labels, removed = remove_from(cfg.get("labels", []))
        if not removed:
            return False
        cfg["labels"] = new_labels
        self._save(cfg)
        return True

    def _find(self, labels: list, label_id: str) -> dict | None:
        for l in labels:
            if l.get("id") == label_id:
                return l
            found = self._find(l.get("children") or [], label_id)
            if found:
                return found
        return None
