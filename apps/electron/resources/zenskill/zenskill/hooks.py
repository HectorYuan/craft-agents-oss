"""
Claude Code Hook 管理

管理 ZenSkill 在 Claude Code settings.json 中的 hooks 配置。
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class HookManager:
    """Claude Code hooks 配置管理器"""

    PYTHONPATH = "/root/DevSpace/ZenSkill"

    # 预定义 hook 模板
    HOOK_TEMPLATES: Dict[str, Dict[str, Any]] = {
        "PostToolUse": {
            "command": "python -m zenskill collector hook",
            "matcher": "",
            "description": "工具调用后自动采集（轻量 <200ms）",
        },
        "Stop": {
            "command": "python -m zenskill collector run-all --since 10m",
            "matcher": "",
            "description": "会话结束时全量采集 + 智能分析",
        },
        "PreToolUse": {
            "command": "python -m zenskill _internal record-event TOOL_START zenskill-core '{}' --context '{\"tool\":\"{}\"}'",
            "matcher": "Bash|Edit|Write|Read",
            "description": "工具使用前记录意图",
        },
        "UserPromptSubmit": {
            "command": "python -m zenskill _internal record-event USER_PROMPT zenskill-core '{}'",
            "matcher": "",
            "description": "用户提交 prompt 时记录",
        },
        "Notification": {
            "command": "python -m zenskill _internal record-event NOTIFY zenskill-core '{}'",
            "matcher": "",
            "description": "Claude 通知时记录",
        },
    }

    def __init__(self):
        self._settings_path = Path.home() / ".claude" / "settings.json"
        self._backup_path = Path.home() / ".claude" / "settings.json.zenskill.bak"

    def _load_settings(self) -> Dict:
        if not self._settings_path.exists():
            return {}
        with open(self._settings_path, encoding="utf-8") as f:
            return json.load(f)

    def _save_settings(self, settings: Dict) -> None:
        # 备份
        if self._settings_path.exists():
            import shutil
            shutil.copy2(self._settings_path, self._backup_path)
        with open(self._settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

    def _normalize_hooks(self, hooks: Dict) -> Dict[str, str]:
        """兼容两种格式:
        - 简单: {"PostToolUse": {"command": "...", "matcher": ""}}
        - 嵌套: {"PostToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "..."}]}]}
        返回: {"PostToolUse": "command string"}
        """
        result = {}
        for name, cfg in hooks.items():
            if isinstance(cfg, dict) and "command" in cfg:
                result[name] = cfg["command"]
            elif isinstance(cfg, list):
                for item in cfg:
                    inner_hooks = item.get("hooks", [])
                    for h in inner_hooks:
                        if h.get("type") == "command":
                            result[name] = h.get("command", "")
                            break
        return result

    def list_hooks(self) -> List[Dict]:
        """列出所有已配置的 hooks"""
        settings = self._load_settings()
        hooks = settings.get("hooks", {})
        normalized = self._normalize_hooks(hooks)
        result = []
        for name, cmd in normalized.items():
            info = self.HOOK_TEMPLATES.get(name, {})
            result.append({
                "name": name,
                "command": cmd[:80],
                "description": info.get("description", cmd[:60]),
                "active": True,
            })
        for name, info in self.HOOK_TEMPLATES.items():
            if name not in normalized:
                result.append({
                    "name": name,
                    "command": info["command"][:80],
                    "description": info["description"],
                    "active": False,
                })
        return result

    def enable(self, name: str) -> bool:
        """启用一个 hook"""
        if name not in self.HOOK_TEMPLATES:
            return False
        settings = self._load_settings()
        if "hooks" not in settings:
            settings["hooks"] = {}
        template = self.HOOK_TEMPLATES[name]
        settings["hooks"][name] = {
            "command": template["command"],
            "matcher": template.get("matcher", ""),
            "env": {"PYTHONPATH": self.PYTHONPATH},
        }
        self._save_settings(settings)
        return True

    def disable(self, name: str) -> bool:
        """禁用一个 hook"""
        settings = self._load_settings()
        hooks = settings.get("hooks", {})
        if name in hooks:
            del hooks[name]
            settings["hooks"] = hooks
            self._save_settings(settings)
            return True
        return False

    def enable_all(self) -> int:
        """批量启用推荐 hooks (PostToolUse + Stop)"""
        count = 0
        for name in ["PostToolUse", "Stop"]:
            if self.enable(name):
                count += 1
        return count

    def disable_all(self) -> int:
        """禁用所有 ZenSkill hooks"""
        settings = self._load_settings()
        hooks = settings.get("hooks", {})
        zen_hooks = [k for k in hooks if "zenskill" in hooks[k].get("command", "")]
        for k in zen_hooks:
            del hooks[k]
        settings["hooks"] = hooks
        self._save_settings(settings)
        return len(zen_hooks)

    def status(self) -> Dict:
        """获取 hook 状态摘要"""
        settings = self._load_settings()
        hooks = settings.get("hooks", {})
        normalized = self._normalize_hooks(hooks)
        active = [k for k, cmd in normalized.items() if "zenskill" in cmd]
        return {
            "total_available": len(self.HOOK_TEMPLATES),
            "active_zen_hooks": len(active),
            "active_names": active,
            "settings_file": str(self._settings_path),
        }
