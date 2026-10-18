"""automations.json 读写 + TaskProgression 规则映射（W1.1）。

格式 SSOT: vendor packages/shared/src/automations/types.ts
路径: {workspace_root}/automations.json（与 Mode B 同文件——双模式兼容）
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

# ── vendor SSOT 字段白名单 ────────────────────────────────────────────────
_MATCHER_KEYS = frozenset({
    "id", "name", "matcher", "cron", "timezone", "permissionMode",
    "labels", "enabled", "conditions", "telegramTopic", "actions",
})
_ACTION_TYPE_KEYS = {
    "prompt":  frozenset({"type", "prompt", "llmConnection", "model", "thinkingLevel"}),
    "script":  frozenset({"type", "script", "args", "runtime", "timeoutMs", "page"}),
    "webhook": frozenset({"type", "url", "method", "headers", "bodyFormat",
                           "body", "captureResponse", "auth"}),
}
_VALID_ACTION_TYPES = frozenset(_ACTION_TYPE_KEYS.keys())

APP_EVENTS = frozenset({
    "LabelAdd", "LabelRemove", "LabelConfigChange",
    "PermissionModeChange", "FlagChange", "SessionStatusChange",
    "SchedulerTick", "ZenSkillChanged",
})
AGENT_EVENTS = frozenset({
    "PreToolUse", "PostToolUse", "PostToolUseFailure", "Notification",
    "UserPromptSubmit", "SessionStart", "SessionEnd", "Stop",
    "SubagentStart", "SubagentStop", "PreCompact", "PermissionRequest", "Setup",
})
ALL_EVENTS = APP_EVENTS | AGENT_EVENTS


def _hex6(obj: object) -> str:
    h = hashlib.md5(str(obj).encode()).hexdigest()[:6]
    return h


class AutomationsStore:
    """读写 {workspace_root}/automations.json + TaskProgression 投影。"""

    def __init__(self, workspace_root: str | Path) -> None:
        self._root = Path(workspace_root)
        self._path = self._root / "automations.json"

    # ── 核心 CRUD ──────────────────────────────────────────────────────

    def load(self) -> dict:
        if not self._path.exists():
            return {"automations": {}}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {"automations": {}}

    def save(self, cfg: dict) -> None:
        errors = _validate(cfg)
        if errors:
            raise ValueError(f"automations.json 校验失败: {'; '.join(errors)}")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent),
                                    prefix=".automations.", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            os.unlink(tmp)
            raise
        os.replace(tmp, self._path)

    def get_matchers(self, event: str, enabled_only: bool = True) -> list[dict]:
        cfg = self.load()
        matchers = cfg.get("automations", {}).get(event, [])
        if enabled_only:
            matchers = [m for m in matchers if m.get("enabled", True)]
        return matchers

    def upsert(self, event: str, matcher: dict) -> str:
        """插入或更新 matcher；返回 id。"""
        cfg = self.load()
        automations = cfg.setdefault("automations", {})
        matchers = automations.setdefault(event, [])

        mid = matcher.get("id") or _hex6(time.time())
        matcher["id"] = mid
        existing_idx = next((i for i, m in enumerate(matchers) if m.get("id") == mid), None)
        if existing_idx is not None:
            matchers[existing_idx] = matcher
        else:
            matchers.append(matcher)
        self.save(cfg)
        return mid

    def delete(self, event: str, matcher_id: str) -> bool:
        cfg = self.load()
        matchers = cfg.get("automations", {}).get(event, [])
        before = len(matchers)
        automations = cfg.setdefault("automations", {})
        automations[event] = [m for m in matchers if m.get("id") != matcher_id]
        if len(automations[event]) < before:
            self.save(cfg)
            return True
        return False

    def set_enabled(self, event: str, matcher_id: str, enabled: bool) -> bool:
        cfg = self.load()
        for m in cfg.get("automations", {}).get(event, []):
            if m.get("id") == matcher_id:
                m["enabled"] = enabled
                self.save(cfg)
                return True
        return False

    def duplicate(self, event: str, matcher_id: str) -> dict | None:
        cfg = self.load()
        for m in cfg.get("automations", {}).get(event, []):
            if m.get("id") == matcher_id:
                dup = dict(m)
                dup["id"] = _hex6(time.time())
                dup["name"] = (dup.get("name") or "Copy") + " (copy)"
                self.upsert(event, dup)
                return dup
        return None

    # ── TaskProgression → AutomationMatcher 映射 ───────────────────────

    def list_progression_matchers(self) -> list[dict]:
        """引擎 TaskProgression 规则映射为 AutomationMatcher 视图。"""
        try:
            from ..systems.gtd.progression import TaskProgressionEngine
            engine = TaskProgressionEngine()
            progressions_data = engine.generate_progressions()
            progressions = progressions_data.get("progressions", [])
            result = []
            for p in progressions:
                result.append({
                    "id": _hex6(p["trigger"]),
                    "name": p["suggestion"][:40],
                    "enabled": True,
                    "labels": [f"zenskill-trigger::{p['trigger_type']}"],
                    "conditions": [],
                    "actions": [{"type": "prompt", "prompt": p["prompt"]}],
                    "x-enskill": {
                        "entity_type": p["entity_type"],
                        "entity_id": p["entity_id"],
                        "priority": p["priority"],
                        "trigger": p["trigger"],
                        "trigger_type": p.trigger_type,
                    },
                })
            return result
        except Exception:
            return []

    def progression_enabled(self) -> str:
        """当前 progression 主动度。"""
        try:
            from ..core.progression_governor import ProgressionGovernor
            g = ProgressionGovernor()
            return g.mode
        except Exception:
            return "active"

    def set_progression_mode(self, mode: str) -> None:
        if mode not in ("active", "quiet", "ritual_only"):
            raise ValueError(f"invalid mode: {mode}")
        try:
            from ..core.progression_governor import ProgressionGovernor
            g = ProgressionGovernor()
            g.set_mode(mode)
        except Exception:
            pass


def _validate(cfg: dict) -> list[str]:
    """格式校验：event 白名单、action 三型必填字段、hex6 id、cron 格式。"""
    errors: list[str] = []
    automations = cfg.get("automations")
    if not isinstance(automations, dict):
        return ["automations 字段缺失或非对象"]

    for event, matchers in automations.items():
        if event not in ALL_EVENTS:
            errors.append(f"未知 event: {event}")
        if not isinstance(matchers, list):
            errors.append(f"{event}: matchers 非列表")
            continue
        for i, m in enumerate(matchers):
            prefix = f"{event}[{i}]"
            mid = m.get("id", "")
            if mid and (not re.match(r"^[0-9a-f]{6}$", mid)):
                errors.append(f"{prefix}: id 非 hex6: {mid}")
            for action in m.get("actions", []):
                at = action.get("type", "")
                if at not in _VALID_ACTION_TYPES:
                    errors.append(f"{prefix}: 未知 action type: {at}")
                else:
                    required = _ACTION_TYPE_KEYS[at] - {"type"}
                    for k in required:
                        if k == "prompt" and at == "prompt":
                            if not action.get(k):
                                errors.append(f"{prefix}: prompt 动作缺 prompt")
                        elif k == "url" and at == "webhook":
                            if not action.get(k):
                                errors.append(f"{prefix}: webhook 缺 url")
                        elif k == "script" and at == "script":
                            if not action.get(k):
                                errors.append(f"{prefix}: script 缺 script")
            cron = m.get("cron")
            if cron:
                parts = cron.strip().split()
                if len(parts) != 5:
                    errors.append(f"{prefix}: cron 非 5 字段: {cron}")
    return errors
