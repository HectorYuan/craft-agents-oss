"""workspace 级六 Store 合一（Batch 1：13 通道去 stub）。

格式 SSOT 对齐 vendor:
- StatusesStore: packages/shared/src/statuses/types.ts (StatusConfig)
- ViewsStore:    packages/shared/src/views/types.ts (ViewConfig)
- SettingsStore: packages/shared/src/protocol/dto.ts (WorkspaceSettings)
- PreferencesStore: vendor types.ts read/writePreferences + config/validators.ts PREFERENCES_FILE
- DraftsStore:   packages/shared/src/config/storage.ts (SessionDraft/DraftsData)
- NotesStore:    per-session 文本（right-sidebar 会话笔记）

全部原子写（tmp + os.replace），slug 防穿越。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

_SLUG_RE = re.compile(r"^[\w-]+$")
_ID_RE = re.compile(r"^[\w:.-]+$")  # label id 允许冒号/点（状态 id 变体）


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# ────────────────────────────────────────────────────────────────
# Statuses（{ws}/statuses/config.json — 内置 5 条不可删）
# ────────────────────────────────────────────────────────────────

BUILTIN_STATUSES: list[dict] = [
    {"id": "todo", "label": "Todo", "category": "open",
     "isFixed": True, "isDefault": True, "order": 0},
    {"id": "in-progress", "label": "In Progress", "category": "open",
     "isFixed": True, "isDefault": False, "order": 1},
    {"id": "needs-review", "label": "Needs Review", "category": "open",
     "isFixed": False, "isDefault": True, "order": 2},
    {"id": "done", "label": "Done", "category": "closed",
     "isFixed": True, "isDefault": False, "order": 3},
    {"id": "cancelled", "label": "Cancelled", "category": "closed",
     "isFixed": True, "isDefault": False, "order": 4},
]


class StatusesStore:
    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)
        self._path = self.workspace_root / "statuses" / "config.json"

    def list(self) -> list[dict]:
        custom: list[dict] = []
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    custom = data
                elif isinstance(data, dict):
                    custom = data.get("statuses", [])
            except Exception:
                custom = []
        builtin_ids = {s["id"] for s in BUILTIN_STATUSES}
        # 内置在前，自定义追加（剔除重复 id 的自定义条目）
        merged = list(BUILTIN_STATUSES) + [
            s for s in custom
            if isinstance(s, dict) and s.get("id") not in builtin_ids
        ]
        merged.sort(key=lambda s: s.get("order", 99))
        return merged

    def create(self, entry: dict) -> dict:
        if not entry.get("id") or not _SLUG_RE.match(str(entry["id"])):
            raise ValueError(f"invalid status id: {entry.get('id')}")
        existing = {s["id"] for s in self.list()}
        if entry["id"] in existing:
            raise ValueError(f"status already exists: {entry['id']}")
        if entry.get("category") not in ("open", "closed"):
            entry["category"] = "open"
        entry.setdefault("isFixed", False)
        entry.setdefault("isDefault", False)
        entry.setdefault("order", len(existing))
        # 只持久化非内置条目
        builtin_ids = {b["id"] for b in BUILTIN_STATUSES}
        custom = [s for s in self.list() if s["id"] not in builtin_ids]
        custom.append(entry)
        self._save_custom(custom)
        return entry

    def _save_custom(self, entries: list[dict]) -> None:
        _atomic_write_json(self._path, entries)


# ────────────────────────────────────────────────────────────────
# Views（{ws}/views.json）
# ────────────────────────────────────────────────────────────────


class ViewsStore:
    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)
        self._path = self.workspace_root / "views.json"

    def list(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data.get("views", [])
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def save(self, views: list[dict]) -> None:
        _atomic_write_json(self._path, {"version": 1, "views": views})


# ────────────────────────────────────────────────────────────────
# WorkspaceSettings（{ws}/workspace-settings.json）
# ────────────────────────────────────────────────────────────────


class SettingsStore:
    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)
        self._path = self.workspace_root / "workspace-settings.json"

    def get(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def update(self, patch: dict) -> dict:
        current = self.get()
        # 只允许 WorkspaceSettings 白名单字段（对齐 dto.ts）
        allowed = {"name", "model", "permissionMode", "cyclablePermissionModes",
                   "thinkingLevel", "workingDirectory", "localMcpEnabled",
                   "defaultLlmConnection", "enabledSourceSlugs"}
        for k, v in patch.items():
            if k in allowed:
                current[k] = v
        _atomic_write_json(self._path, current)
        return current


# ────────────────────────────────────────────────────────────────
# Preferences（<config_dir>/preferences.json — 对齐 vendor PREFERENCES_FILE）
# ────────────────────────────────────────────────────────────────


class PreferencesStore:
    def __init__(self, config_dir: Path):
        from ..core.paths import get_config_dir
        self._path = (config_dir or get_config_dir()) / "preferences.json"

    @property
    def path(self) -> str:
        return str(self._path)

    def read(self) -> dict:
        """readPreferences: {content, exists, path}（content 为 JSON 文本化）。"""
        exists = self._path.exists()
        content = ""
        if exists:
            try:
                content = self._path.read_text(encoding="utf-8")
            except Exception:
                content = ""
        return {"content": content, "exists": exists, "path": self.path}

    def write(self, content: str) -> dict:
        """writePreferences: {success, error}（content 可为 JSON 字符串或对象）。"""
        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False, indent=2)
        try:
            # 若是 JSON 字符串则校验合法性（preferences.json 按 JSON 存）
            if content.strip():
                json.loads(content)
            _atomic_write_text(self._path, content if content.strip().endswith("\n")
                               else content + "\n")
            return {"success": True, "error": None}
        except json.JSONDecodeError as exc:
            return {"success": False, "error": f"invalid JSON: {exc}"}


# ────────────────────────────────────────────────────────────────
# Drafts（<config_dir>/drafts.json — 对齐 vendor DraftsData）
# ────────────────────────────────────────────────────────────────


class DraftsStore:
    def __init__(self, config_dir: Path | None = None):
        from ..core.paths import get_config_dir
        self._path = (config_dir or get_config_dir()) / "drafts.json"

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data.get("drafts", {}) if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save(self, drafts: dict) -> None:
        _atomic_write_json(self._path, {"drafts": drafts, "updatedAt": int(time.time() * 1000)})

    def get_all(self) -> dict:
        return self._load()

    def get(self, session_id: str) -> dict | None:
        return self._load().get(session_id)

    def set(self, session_id: str, draft: dict) -> None:
        if not isinstance(draft, dict):
            raise ValueError("draft must be an object")
        drafts = self._load()
        drafts[session_id] = draft
        self._save(drafts)

    def delete(self, session_id: str) -> bool:
        drafts = self._load()
        if session_id not in drafts:
            return False
        drafts.pop(session_id)
        self._save(drafts)
        return True


# ────────────────────────────────────────────────────────────────
# Session Notes（{ws}/sessions/{id}/notes.md — 纯文本）
# ────────────────────────────────────────────────────────────────


class NotesStore:
    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)

    def _notes_path(self, session_id: str) -> Path:
        if not _SLUG_RE.match(session_id) and not _ID_RE.match(session_id):
            # session id 形如 sess_xxx / uuid — 允许字母数字横线下划线点
            if not re.match(r"^[\w.-]+$", session_id):
                raise ValueError(f"invalid session id: {session_id}")
        return self.workspace_root / "sessions" / session_id / "notes.md"

    def get(self, session_id: str) -> dict:
        p = self._notes_path(session_id)
        content = p.read_text(encoding="utf-8") if p.exists() else ""
        return {"content": content, "exists": p.exists(), "path": str(p)}

    def set(self, session_id: str, content: str) -> dict:
        p = self._notes_path(session_id)
        _atomic_write_text(p, str(content))
        return {"success": True, "path": str(p)}
