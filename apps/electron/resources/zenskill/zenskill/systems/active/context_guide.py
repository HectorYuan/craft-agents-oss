"""Context-aware guidance engine (7W)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any


class ContextGuideEngine:
    """基于当前会话上下文生成智能引导建议"""

    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id

    def analyze(self, lookback_hours: int = 24) -> dict[str, Any]:
        events = self._recent_events(lookback_hours)
        if not events:
            return {"suggestions": [], "context": {"total_events": 0, "error_count": 0}}

        tools = Counter(e.get("tool", "?") for e in events if isinstance(e, dict))
        files = Counter(
            e.get("file_type", "?").split("/")[0] if "file_type" in e else "?"
            for e in events if isinstance(e, dict)
        )
        languages = Counter(
            e.get("extension", "?") for e in events if isinstance(e, dict) and e.get("extension")
        )
        errors = [e for e in events if isinstance(e, dict) and not e.get("success", True)]
        tool_use = dict(tools.most_common(5))
        top_lang = [l for l, _ in languages.most_common(2)]
        suggestions = self._build_suggestions(tool_use, top_lang, len(errors), len(events))

        return {
            "suggestions": suggestions,
            "context": {
                "total_events": len(events),
                "error_count": len(errors),
                "top_tools": dict(tools.most_common(5)),
                "top_languages": dict(languages.most_common(3)),
                "lookback_hours": lookback_hours,
            },
        }

    def format_guide(self, lookback_hours: int = 24) -> str:
        result = self.analyze(lookback_hours)
        ctx = result["context"]

        lines = ["🧭 上下文感知引导", "═" * 50, ""]

        if ctx["total_events"] == 0:
            lines.append("  数据不足以生成引导建议")
            return "\n".join(lines)

        lines.append(f"  最近 {ctx['lookback_hours']}h: {ctx['total_events']} 次操作")

        if ctx["error_count"] > 0:
            lines.append(f"  ⚠️  错误率: {ctx['error_count']}/{ctx['total_events']} ({ctx['error_count']/max(ctx['total_events'],1)*100:.0f}%)")

        top_tools = ctx.get("top_tools", {})
        if top_tools:
            tools_str = ", ".join(f"{t}({c})" for t, c in list(top_tools.items())[:3])
            lines.append(f"  🔧 常用工具: {tools_str}")

        top_langs = ctx.get("top_languages", {})
        if top_langs:
            langs_str = ", ".join(f"{l}({c})" for l, c in list(top_langs.items())[:3])
            lines.append(f"  📁 常用语言: {langs_str}")

        lines.append("")

        if result["suggestions"]:
            lines.append("💡 建议:")
            for s in result["suggestions"]:
                lines.append(f"  • {s}")
        else:
            lines.append("💡 一切正常，继续保持！")

        return "\n".join(lines)

    # ---- internal ----

    def _recent_events(self, lookback_hours: int) -> list[dict]:
        try:
            from zenskill.mirroring.event_collector import EventCollector
            collector = EventCollector()
            events = collector.query(limit=200)
            return [e.to_dict() if hasattr(e, "to_dict") else e for e in events]
        except Exception:
            return []

    def _build_suggestions(self, tools: dict, langs: list[str], error_count: int,
                           total: int) -> list[str]:
        suggestions = []
        # 词汇对齐：事件里的工具名大小写/来源不一（MCP 小写、宿主可能驼峰），
        # 统一小写计数；Claude Code 名（Edit/Glob/Agent）映射到 MCP 等价词
        alias = {"glob": "find", "agent": "delegate", "task": "delegate"}
        low = dict(tools or {})
        tools = {}
        for k, v in low.items():
            key = str(k).lower()
            key = alias.get(key, key)
            tools[key] = tools.get(key, 0) + (v or 0)

        def tsum(*names: str) -> int:
            return sum(tools.get(n, 0) for n in names)

        # 高错误率
        if total > 10 and error_count / total > 0.15:
            suggestions.append("错误率偏高，建议运行测试: `pytest -v`")

        # 大量写操作但很少测试（edit/write/edit_multi 都算写）
        edit_count = tsum("edit", "write")
        test_count = tsum("bash")
        if edit_count > 10 and test_count < 3:
            suggestions.append("代码修改频繁但测试较少，建议增加测试覆盖")

        # 特定语言建议
        if "py" in langs:
            from zenskill.core.paths import SkillStateManager
            state = SkillStateManager(self.skill_id).load()
            lvl = state.get("level", "NOVICE")
            if lvl in ("NOVICE", "APPRENTICE"):
                suggestions.append("Python 练习建议：尝试 `zenskill task recommend` 获取任务")

        # 搜索频繁
        if tsum("grep", "find") > 20:
            suggestions.append("搜索操作频繁，考虑优化项目结构或更新 .gitignore")

        # 子代理使用
        if tsum("delegate") > 5:
            suggestions.append("大量使用子代理，检查是否有重复或可合并的任务")

        # 默认建议
        if not suggestions:
            suggestions.append("工作流看起来不错，运行 `zenskill doctor state` 检查数据健康")

        return suggestions
