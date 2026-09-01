"""
Claude Code 核心设定采集器

采集 CLAUDE.md 项目设定 + settings.json 用户配置。
提取语言偏好、项目技术栈、开发习惯、工具偏好等核心信号。
"""

import json
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from ..base import BaseCollector, CollectorMeta, DataSensitivity


class CoreSettingsCollector(BaseCollector):
    """Claude Code 核心设定采集器

    采集范围：
    - 各项目 CLAUDE.md（项目设定、语言偏好、技术栈）
    - ~/.claude/settings.json（用户配置、hooks、插件）
    """

    meta = CollectorMeta(
        name="claude-core-settings",
        version="0.1.0",
        description="采集各项目 CLAUDE.md 核心设定 + settings.json 用户配置",
        sensitivity=DataSensitivity.HIGH,
        data_source="CLAUDE.md + ~/.claude/settings.json",
    )

    # 搜索路径
    SEARCH_ROOTS = [
        Path.home() / ".claude" / "projects",
    ]
    PROJECT_ROOTS = [
        Path("/root/DevSpace"),
        Path("/root/DevSpace/ZenSkill"),
        Path("/root/DevSpace/ZenAgent"),
        Path("/root/DevSpace/modelnexus"),
        Path("/root/DevSpace/docs"),
    ]

    def __init__(self):
        self._settings_path = Path.home() / ".claude" / "settings.json"
        self._stats = {}

    def is_available(self) -> bool:
        return any(r.exists() for r in self.PROJECT_ROOTS) or self._settings_path.exists()

    def collect_full(self) -> List[Dict[str, Any]]:
        now = time.time()
        results = []

        # 1. 采集项目 CLAUDE.md
        claude_md_signals = self._collect_claude_md()
        if claude_md_signals:
            results.append({
                "source": "claude_code_claude_md",
                "timestamp": now,
                "signal": claude_md_signals,
                "sensitivity": "high",
            })

        # 2. 采集 settings.json
        settings_signals = self._collect_settings()
        if settings_signals:
            results.append({
                "source": "claude_code_settings",
                "timestamp": now,
                "signal": settings_signals,
                "sensitivity": "high",
            })

        return results

    def _collect_claude_md(self) -> Dict[str, Any]:
        """采集所有项目 CLAUDE.md"""
        projects_info: List[Dict] = []
        lang_prefs: Counter = Counter()
        tech_keywords: Counter = Counter()

        tech_terms = [
            "python", "fastapi", "react", "typescript", "vue", "rust", "go",
            "docker", "kubernetes", "redis", "postgresql", "mongodb",
            "textual", "pydantic", "pytest", "asyncio", "aiohttp",
            "openai", "anthropic", "claude", "deepseek",
        ]

        for root in self.PROJECT_ROOTS:
            claude_md = root / "CLAUDE.md"
            if not claude_md.exists():
                continue

            try:
                content = claude_md.read_text(encoding="utf-8")
                proj_name = root.name

                info: Dict[str, Any] = {
                    "project": proj_name,
                    "path": str(root),
                    "size": len(content),
                }

                # 语言偏好检测
                if "中文" in content or "chinese" in content.lower():
                    lang_prefs["chinese"] += 1
                    info["language"] = "zh"
                else:
                    lang_prefs["english"] += 1
                    info["language"] = "en"

                # 提取文档节数
                sections = len(re.findall(r"^#{1,3}\s", content, re.MULTILINE))
                info["sections"] = sections

                # 技术栈关键词
                content_lower = content.lower()
                for term in tech_terms:
                    if term in content_lower:
                        tech_keywords[term] += 1

                # 提取项目描述（第一段）
                lines = content.strip().split("\n")
                desc = ""
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("```"):
                        desc = line[:200]
                        break
                info["description"] = desc

                projects_info.append(info)

            except Exception:
                pass

        if not projects_info:
            return {}

        return {
            "total_projects": len(projects_info),
            "projects": projects_info,
            "dominant_language": lang_prefs.most_common(1)[0][0] if lang_prefs else "unknown",
            "language_distribution": dict(lang_prefs),
            "tech_stack": dict(tech_keywords.most_common(10)),
            "avg_sections": round(sum(p.get("sections", 0) for p in projects_info) / len(projects_info), 1),
        }

    def _collect_settings(self) -> Dict[str, Any]:
        """采集 settings.json"""
        if not self._settings_path.exists():
            return {}

        try:
            with open(self._settings_path, encoding="utf-8") as f:
                settings = json.load(f)
        except Exception:
            return {}

        signals: Dict[str, Any] = {}

        # 模型配置
        if "model" in settings:
            signals["model"] = settings["model"]

        # 努力等级
        if "effortLevel" in settings:
            signals["effort_level"] = settings["effortLevel"]

        # Hooks 配置
        hooks = settings.get("hooks", {})
        if hooks:
            hook_types = list(hooks.keys())
            signals["hooks_count"] = len(hooks)
            signals["hook_types"] = hook_types

            # 检测 hook 使用的命令模式
            cmd_counter: Counter = Counter()
            for hook_name, hook_cfg in hooks.items():
                if isinstance(hook_cfg, dict):
                    cmd = hook_cfg.get("command", "") or hook_cfg.get("matcher", "") or ""
                    # 提取命令关键词
                    for kw in ["zenskill", "python", "bash", "hook_record",
                               "git", "env", "source"]:
                        if kw in str(cmd):
                            cmd_counter[kw] += 1
            if cmd_counter:
                signals["hook_commands"] = dict(cmd_counter)

        # 权限配置
        perms = settings.get("permissions", {})
        if perms:
            perm_count = 0
            for perm_key, perm_val in perms.items():
                if isinstance(perm_val, dict):
                    perm_count += len(perm_val)
                elif isinstance(perm_val, list):
                    perm_count += len(perm_val)
            signals["permissions_count"] = perm_count
            # 权限类型
            perm_types = list(perms.keys())
            if perm_types:
                signals["permission_types"] = perm_types

        # 环境变量
        env_vars = settings.get("env", {})
        if env_vars:
            signals["env_vars_count"] = len(env_vars)
            # 只记录 key，不记录 value
            signals["env_keys"] = list(env_vars.keys())[:10]

        return signals
