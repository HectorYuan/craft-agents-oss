"""
ServerToolRegistry — MCP server 端工具注册与分发

桥接 ZenSkill 现有系统（技能生态 / GTD / 记忆 / 成长报告）为 MCP tools。
handler 统一同步签名 dict -> Any；返回 str/结构化值由 server 层包装为
MCP content。系统 import 延迟到 handler 内部，保持 server 启动轻量。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ServerToolSpec:
    """server 端工具定义"""
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    handler: Callable[[dict[str, Any]], Any] = None
    _custom: bool = False  # 自定义工具标记（reload_custom_tools 用）


# 内部来源标记键：由 agent 执行层（AgentLoop/callMcpTool）注入到写工具
# arguments，跨进程经 JSON 透传；不入 inputSchema（对外接口不变）。
SOURCE_SESSION_KEY = "_source_session_id"
CREATED_BY_KEY = "_created_by"


def _pop_source_context(a: dict[str, Any]) -> tuple[str, str]:
    """弹出内部来源标记，返回 (source_session_id, created_by)。

    弹出而非读取——避免内部键被 catch-all 型 handler（如 action_update 的
    字段透传）当成业务字段写回引擎。"""
    return (
        str(a.pop(SOURCE_SESSION_KEY, "") or ""),
        str(a.pop(CREATED_BY_KEY, "user") or "user"),
    )


# priority 值域：引擎侧 P0-P3（ActionEngine.PRIORITY_ORDER）。
# 旧前端/旧数据可能传 high/medium/low，读取与写入时归一化。
_PRIORITY_ALIASES = {"high": "P1", "medium": "P2", "low": "P3"}
_VALID_PRIORITIES = ("P0", "P1", "P2", "P3")

# energy_required 值域：引擎侧数字（ActionEngine.ENERGY_MAP: easy=3/medium=5/hard=8/extreme=10）。
_ENERGY_ALIASES = {"easy": 3, "medium": 5, "hard": 8, "extreme": 10,
                   "low": 3, "high": 8, "1": 1, "3": 3, "5": 5, "8": 8, "10": 10}
_VALID_ENERGY = (1, 3, 5, 8, 10)


def _normalize_priority(value: Any) -> Any:
    """priority 归一化：high/medium/low → P1/P2/P3；P0-P3 直传；未知值原样返回"""
    if not isinstance(value, str):
        return value
    v = value.strip()
    upper = v.upper()
    if upper in _VALID_PRIORITIES:
        return upper
    return _PRIORITY_ALIASES.get(v.lower(), value)


def _normalize_energy(value: Any) -> Any:
    """energy_required 归一化：easy/medium/hard/extreme 等别名 → 数字；有效数字直传"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) if int(value) in _VALID_ENERGY else value
    if isinstance(value, str):
        return _ENERGY_ALIASES.get(value.strip().lower(), value)
    return value


def _display_priority(value: Any) -> Any:
    """读取侧显示归一化：历史数据 medium → P2（不回写文件）"""
    return _normalize_priority(value)


class ServerToolRegistry:
    """工具注册表：list_specs 供 tools/list，call 供 tools/call"""

    # 只读重工具的 TTL 缓存（秒）。这些工具每次全量扫描事件/文件，
    # GUI 刷新频繁，缓存后重复刷新 ~0ms。写工具执行后全清。
    CACHE_TTL = {
        "daily_review": 45.0,
        "achievement_list": 45.0,
        "habit_analyze": 45.0,
        "skill_browse": 120.0,
    }
    # 写工具：调用即清缓存（保证后续读拿到新数据）。
    # 前缀规则对齐 TS 侧 sources.ts——新增同族写工具自动覆盖。
    # READ 前缀族下的读工具（list/review/analyze 等）显式排除——
    # 否则 gtd_inbox_list 等命中前缀被误判为写，TTL 缓存永不命中。
    _WRITE_TOOL_PREFIXES = ("gtd_", "inbox_", "action_", "project_", "incubating_")
    _WRITE_TOOLS_EXACT = frozenset({
        "memory_remember", "memory_forget", "goal_set",
        "goal_update", "goal_delete",
        "habit_set", "habit_check", "habit_delete",
        "skill_install", "skill_uninstall",
        "calendar_add", "calendar_update", "calendar_delete",
        "project_add", "project_update",
        "progression_feedback",
    })
    _READ_TOOLS = frozenset({
        "gtd_inbox_list", "gtd_review",
        "action_list", "project_list",
        "incubating_list",
        "calendar_list", "calendar_month",
        "inbox_suggest",
        "share_card",
        "task_progressions",
        "progression_mode",
        "collaboration_insights", "collaboration_transfer",
        "collaboration_dashboard",
    })

    @classmethod
    def is_write_tool(cls, name: str) -> bool:
        if name in cls._READ_TOOLS:
            return False
        return name in cls._WRITE_TOOLS_EXACT or name.startswith(cls._WRITE_TOOL_PREFIXES)

    def __init__(self):
        self._tools: dict[str, ServerToolSpec] = {}
        self._cache: dict[str, tuple[float, str]] = {}

    def register(
        self,
        name: str,
        description: str,
        handler: Callable[[dict[str, Any]], Any],
        input_schema: dict[str, Any] | None = None,
    ) -> None:
        self._tools[name] = ServerToolSpec(
            name=name,
            description=description,
            input_schema=input_schema or {"type": "object", "properties": {}},
            handler=handler,
        )

    def list_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.input_schema,
            }
            for t in self._tools.values()
        ]

    def has(self, name: str) -> bool:
        return name in self._tools

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    def reload_custom_tools(self) -> int:
        """重新加载 ~/.zenskill/tools/*.py 自定义工具（覆盖同名旧注册）。"""
        # 移除旧的自定义工具（通过 _custom 标记识别）
        self._tools = {
            k: v for k, v in self._tools.items()
            if not getattr(v, "_custom", False)
        }
        before = self.tool_count
        _register_custom_tools(self)
        return self.tool_count - before

    def filter_by_prefixes(self, prefixes: list[str]) -> "ServerToolRegistry":
        """返回只含名称匹配任一前缀工具的新注册表"""
        filtered = ServerToolRegistry()
        for tool in self._tools.values():
            if any(tool.name.startswith(p) for p in prefixes):
                filtered._tools[tool.name] = tool
        return filtered

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        """调用工具；异常向上抛（由 server 层转 isError 响应）

        每次调用自动记录到 ZenSkill event collector（双向桥接）。
        只读重工具走 TTL 缓存；写工具调用前清缓存。
        """
        spec = self._tools.get(name)
        if spec is None:
            raise KeyError(f"Unknown tool: {name}")
        arguments = arguments or {}

        if self.is_write_tool(name):
            self._cache.clear()

        cache_key = None
        if name in self.CACHE_TTL:
            try:
                cache_key = f"{name}:{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"
            except (TypeError, ValueError):
                cache_key = None
            if cache_key:
                hit = self._cache.get(cache_key)
                if hit and time.time() - hit[0] < self.CACHE_TTL[name]:
                    return hit[1]

        result = spec.handler(arguments)
        # 写工具成功后标记 guide.md 脏（下次会话启动时自动刷新）
        if self.is_write_tool(name):
            try:
                from ...core.guide_dirty import mark_guide_dirty
                mark_guide_dirty()
            except Exception:
                pass
        # 事件流桥接：每次 MCP 工具调用自动记录到 ZenSkill event collector
        self._record_event(name, arguments, result)
        # 陪伴事件埋点：companion_summary / instant_feedback / proactive_insight
        if name in ("companion_summary", "instant_feedback", "proactive_insight"):
            self._record_companion_event(name, result)
        if not isinstance(result, str):
            result = json.dumps(result, ensure_ascii=False, default=str)

        if cache_key:
            self._cache[cache_key] = (time.time(), result)
        return result

    def _record_event(self, name: str, arguments: dict, result: Any) -> None:
        """记录 MCP 工具调用事件到 ZenSkill event collector"""
        try:
            from ...mirroring.event_collector import EventCollector
            ec = EventCollector()
            # 记录工具执行
            args_summary = json.dumps(arguments, ensure_ascii=False)[:200] if arguments else ""
            ec.record_skill_execution(
                skill_id="mcp",
                task=f"{name}: {args_summary}",
                success=True,
                duration_ms=0,
                context={"mcp_tool": name, "source": "craft-gui"},
            )
        except Exception:
            pass

    _COMPANION_TOOLS = frozenset({
        "companion_summary", "instant_feedback", "proactive_insight",
    })

    def _record_companion_event(self, name: str, result: Any) -> None:
        """陪伴事件埋点：companion_summary / instant_feedback / proactive_insight"""
        try:
            from ...systems.active.companion_events import CompanionEventRecorder
            recorder = CompanionEventRecorder(
                getattr(self, '_event_collector', None))
            if name == "companion_summary":
                if isinstance(result, dict):
                    recorder.record_displayed(
                        mood=result.get("mood", ""),
                        energy_level=result.get("energy", {}).get("level", ""),
                        has_insight=result.get("top_insight") is not None,
                    )
            elif name == "instant_feedback":
                if isinstance(result, dict):
                    recorder.record_feedback(
                        feedback_type=result.get("one_line", "")[:50],
                    )
            elif name == "proactive_insight":
                if isinstance(result, dict) and result.get("count", 0) > 0:
                    first = result["items"][0] if result.get("items") else {}
                    recorder.record_insight_clicked(
                        insight_type=first.get("type", ""),
                        source="auto",
                    )
        except Exception:
            pass


def build_default_registry() -> ServerToolRegistry:
    """首批 MCP 工具接线（全量只读优先，写操作限 inbox/memory）"""
    registry = ServerToolRegistry()

    def _skill_search(a: dict[str, Any]) -> Any:
        from ...skills.search_engine import SkillSearchEngine

        engine = SkillSearchEngine()
        results = engine.search(
            a["query"],
            category=a.get("category"),
            difficulty=a.get("difficulty"),
            top_k=int(a.get("top_k", 10)),
        )
        return {
            "count": len(results),
            "results": [
                {
                    "skill_id": r.skill.skill_id,
                    "name": getattr(r.skill, "name", r.skill.skill_id),
                    "description": getattr(r.skill, "description", ""),
                    "score": round(r.score, 3),
                    "category": getattr(r.skill, "category", ""),
                }
                for r in results
            ],
        }

    def _skill_browse(a: dict[str, Any]) -> Any:
        """按分类浏览已安装技能（分组统计 + 每组 top N）"""
        from ...skills.search_engine import SkillSearchEngine
        from collections import defaultdict

        engine = SkillSearchEngine()
        engine.build_index()
        limit = int(a.get("limit", 3))
        groups: dict[str, list] = defaultdict(list)
        for entry in engine._index.values():
            cat = entry.category or "general"
            groups[cat].append({
                "skill_id": entry.skill_id,
                "name": entry.name,
                "description": (entry.description or "")[:100],
                "category": cat,
                "usage_count": entry.usage_count,
                "level": entry.level,
            })
        categories = []
        for cat, skills in sorted(groups.items(), key=lambda x: -len(x[1])):
            skills.sort(key=lambda s: (-s["usage_count"], s["name"]))
            categories.append({
                "name": cat,
                "count": len(skills),
                "skills": skills[:limit],
            })
        return {"total": len(engine._index), "categories": categories}

    def _skill_trending(a: dict[str, Any]) -> Any:
        from ...skills.search_engine import SkillSearchEngine

        results = SkillSearchEngine().trending(top_k=int(a.get("top_k", 10)))
        return {
            "count": len(results),
            "results": [
                {
                    "skill_id": r.skill.skill_id,
                    "name": getattr(r.skill, "name", r.skill.skill_id),
                    "score": round(r.score, 3),
                }
                for r in results
            ],
        }

    def _skill_install(a: dict[str, Any]) -> Any:
        from ...skills.universal_installer import install_skill

        return install_skill(a["uri"])

    def _skill_uninstall(a: dict[str, Any]) -> Any:
        from ...skills.universal_installer import uninstall_skill

        return uninstall_skill(a["skill_id"])

    def _gtd_capture(a: dict[str, Any]) -> Any:
        from ...systems.gtd.inbox import InboxEngine

        source_session_id, created_by = _pop_source_context(a)
        item = InboxEngine().add(a["text"], source="mcp",
                                 source_session_id=source_session_id,
                                 created_by=created_by)
        return {"ok": True, "item": item.to_dict()}

    def _gtd_inbox_list(a: dict[str, Any]) -> Any:
        from ...systems.gtd.inbox import InboxEngine

        items = InboxEngine().list(
            status=a.get("status", "unprocessed"),
            limit=int(a.get("limit", 20)),
        )
        return {"count": len(items), "items": [i.to_dict() for i in items]}

    def _inbox_clarify(a: dict[str, Any]) -> Any:
        """澄清 inbox 条目 — 自动意图分类，标记目标类型并落下游对象。

        result_type=action/project/calendar 时自动创建对应下游对象并回填
        target_id（显式传 target_id 时视为已关联，不重复创建）；
        reference 只打标。"""
        from ...systems.gtd.inbox import InboxEngine

        valid_types = ("action", "project", "calendar", "reference")
        engine = InboxEngine()
        item_id = a["item_id"]
        item = engine.get(item_id)
        if not item:
            return {"ok": False, "item_id": item_id,
                    "message": f"未找到条目 {item_id}"}
        result_type = str(a.get("result_type", "")
                          or engine.auto_classify(item.raw_text)).strip().lower()
        if result_type not in valid_types:
            return {
                "ok": False,
                "item_id": item_id,
                "result_type": str(a.get("result_type", "")),
                "message": (f"非法 result_type「{a.get('result_type')}」，"
                            f"可选值: {'/'.join(valid_types)}"),
            }

        target_id = a.get("target_id", "")
        created: Any = None
        if not target_id:
            text = item.raw_text
            try:
                if result_type == "action":
                    from ...systems.gtd.action import ActionEngine
                    created = ActionEngine().add(title=text)
                elif result_type == "calendar":
                    from ...systems.gtd.calendar import CalendarEngine
                    created = CalendarEngine().add(
                        date=time.strftime("%Y-%m-%d"), title=text)
                elif result_type == "project":
                    from ...systems.gtd.project import ProjectEngine
                    created = ProjectEngine().create(name=text)
            except Exception as e:
                return {"ok": False, "item_id": item_id,
                        "result_type": result_type,
                        "message": f"下游对象创建失败: {e}"}
            if created is not None:
                target_id = getattr(created, "id", "")

        ok = engine.clarify(item_id, result_type, target_id)
        result: dict[str, Any] = {
            "ok": ok,
            "item_id": item_id,
            "result_type": result_type,
            "target_id": target_id,
            "message": (f"Inbox 条目 {item_id} 已澄清为 {result_type}"
                        + (f"（已创建 target_id={target_id}）" if created is not None else ""))
                        if ok else f"未找到条目 {item_id}",
        }
        if created is not None:
            to_dict = getattr(created, "to_dict", None)
            result["created"] = to_dict() if callable(to_dict) else str(created)
        return result

    def _inbox_archive(a: dict[str, Any]) -> Any:
        """归档 inbox 条目"""
        from ...systems.gtd.inbox import InboxEngine

        ok = InboxEngine().archive(a["item_id"])
        return {
            "ok": ok,
            "item_id": a["item_id"],
            "message": f"Inbox 条目 {a['item_id']} 已归档" if ok
                       else f"未找到条目 {a['item_id']}",
        }

    def _inbox_suggest(a: dict[str, Any]) -> Any:
        """批量获取 inbox 条目的 AI 分类建议（只读，不写入）。

        B09/B10 支撑：AutoClassifyBadge 展示建议 + 批量整理按建议一键澄清。
        """
        from ...systems.gtd.inbox import InboxEngine

        engine = InboxEngine()
        items = engine.list(status="unprocessed", limit=int(a.get("limit", 50)))
        suggestions = []
        for item in items:
            suggestions.append({
                "item_id": item.id,
                "text": item.raw_text[:80],
                "suggested_type": engine.auto_classify(item.raw_text),
            })
        return {
            "count": len(suggestions),
            "items": suggestions,
            "message": f"待处理 {len(suggestions)} 条，已附分类建议",
        }

    def _memory_remember(a: dict[str, Any]) -> Any:
        from ...core.paths import SkillStateManager

        skill_id = a.get("skill_id", "zenskill")
        action = a.get("action", "memory_add")
        content = a["content"]
        SkillStateManager(skill_id).record_episode(action, content)
        return {
            "ok": True,
            "skill_id": skill_id,
            "action": action,
            "content": content,
            "message": f"已为 {skill_id} 记住: {content[:100]}",
        }

    def _memory_list(a: dict[str, Any]) -> Any:
        from ...core.paths import SkillStateManager

        skill_id = a.get("skill_id", "zenskill")
        n = int(a.get("n", 10))
        # skill_id 为空或 "all" 时聚合全部 skill（与 guide.md 口径一致）
        if skill_id in ("", "all"):
            skill_ids = ["zenskill", "zenskill-core", "mcp-test", "craft-gui"]
        else:
            skill_ids = [skill_id]
        all_episodes = []
        for sid in skill_ids:
            try:
                state = SkillStateManager(sid).load()
                for ep in state.get("episodes", []):
                    all_episodes.append({**ep, "skill_id": sid})
            except Exception:
                pass
        all_episodes.sort(key=lambda e: e.get("date", ""), reverse=True)
        return {
            "skill_id": skill_id,
            "count": len(all_episodes),
            "showing": min(n, len(all_episodes)),
            "items": [
                {
                    "action": ep.get("action", "general"),
                    "content": ep.get("content", ""),
                    "date": ep.get("date", ""),
                    "skill_id": ep.get("skill_id", ""),
                }
                for ep in all_episodes[:n]
            ],
            "message": f"找到 {len(all_episodes)} 条记忆，显示最近 {min(n, len(all_episodes))} 条",
        }

    def _dashboard_summary(a: dict[str, Any]) -> Any:
        from ...tui.data import TuiDataAdapter

        result = TuiDataAdapter().get_dashboard_summary()
        # 补充 GUI 侧需要的计数（与 guide.md 口径一致）
        try:
            from pathlib import Path
            skills_dir = Path.home() / ".agents" / "skills"
            result["installed_skills"] = len([
                d for d in skills_dir.iterdir()
                if d.is_dir() and (d / "SKILL.md").exists()
            ]) if skills_dir.exists() else 0
        except Exception:
            result["installed_skills"] = 0
        try:
            import json, time
            idx = json.loads(
                (Path.home() / ".zenskill" / "memory" / "sessions" / "sessions_index.json")
                .read_text(encoding="utf-8"))
            today = time.strftime("%Y-%m-%d")
            result["today_sessions"] = sum(
                1 for s in idx.values()
                if time.strftime("%Y-%m-%d", time.localtime(s.get("started_at", 0) / 1000)) == today
            )
        except Exception:
            result["today_sessions"] = 0
        return result

    def _growth_report(a: dict[str, Any]) -> Any:
        from ...tui.data import TuiDataAdapter

        return TuiDataAdapter().get_growth_report(a["skill_id"])

    def _skill_context(a: dict[str, Any]) -> Any:
        """获取技能详细文档（SKILL.md 内容 + 索引元数据）"""
        from ...skills.search_engine import SkillSearchEngine
        from pathlib import Path

        skill_id = a["skill_id"]
        engine = SkillSearchEngine()
        engine.build_index()
        entry = engine.get_entry(skill_id)

        result = {"skill_id": skill_id, "found": False}
        if entry:
            result.update({
                "found": True,
                "name": getattr(entry, "name", skill_id),
                "description": getattr(entry, "description", ""),
                "category": getattr(entry, "category", "general"),
                "difficulty": getattr(entry, "difficulty", "beginner"),
                "usage_count": getattr(entry, "usage_count", 0),
                "level": getattr(entry, "level", "NOVICE"),
                "source": getattr(entry, "source", "unknown"),
            })

        # 尝试读取 SKILL.md 内容
        skill_dir = Path.home() / ".agents" / "skills" / skill_id
        md_file = skill_dir / "SKILL.md"
        if md_file.exists():
            try:
                content = md_file.read_text()[:5000]
                result["skill_md"] = content
                result["skill_md_path"] = str(md_file)
            except Exception:
                pass

        return result

    def _gtd_review(a: dict[str, Any]) -> Any:
        """每周回顾：本周完成/未完成/能量统计"""
        from datetime import datetime, timedelta

        days = int(a.get("days", 7))
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        def _inbox_stats_jsonl() -> dict[str, Any]:
            """降级路径：JSONL 全量扫描（SQLite 不可用时）。"""
            from ...systems.gtd.inbox import InboxEngine

            # inbox 统计（已处理 = clarified + archived 两态合计；
            # 引擎无 "processed" 状态，旧代码查它恒为 0）
            inbox = InboxEngine()
            pending = inbox.list(status="unprocessed", limit=500)
            processed = (inbox.list(status="clarified", limit=500)
                         + inbox.list(status="archived", limit=500))

            # 已处理时间：优先 clarify/archive 时间戳，旧数据回退 created_at
            def _processed_day(i: Any) -> str:
                cr = i.clarify_result if isinstance(i.clarify_result, dict) else {}
                return str(cr.get("clarified_at") or cr.get("archived_at")
                           or i.created_at or "")

            # 按日期过滤最近 N 天
            recent_pending = [i for i in pending if i.created_at >= cutoff]
            recent_processed = [i for i in processed if _processed_day(i) >= cutoff]

            return {
                "pending_total": len(pending),
                "pending_recent": len(recent_pending),
                "processed_recent": len(recent_processed),
                "recent_items": [
                    {"text": i.raw_text[:80], "status": i.status, "created": i.created_at}
                    for i in recent_pending[:5]
                ],
            }

        try:
            from ...core.database import db
            with db.connect() as conn:
                pending_total = conn.execute(
                    "SELECT COUNT(*) FROM gtd_inbox WHERE status='unprocessed'"
                ).fetchone()[0]
                pending_recent = conn.execute(
                    "SELECT COUNT(*) FROM gtd_inbox WHERE status='unprocessed' "
                    "AND created_at >= ?", (cutoff,)
                ).fetchone()[0]
                # 已处理按日分布：clarified_at 为空串/NULL（直接归档）时回退 created_at
                processed_by_day = conn.execute(
                    "SELECT date(COALESCE(NULLIF(clarified_at, ''), created_at)) AS day, "
                    "COUNT(*) AS cnt FROM gtd_inbox "
                    "WHERE status IN ('clarified','archived') "
                    "GROUP BY day ORDER BY day"
                ).fetchall()
                recent_rows = conn.execute(
                    "SELECT content, status, created_at FROM gtd_inbox "
                    "WHERE status='unprocessed' ORDER BY created_at DESC LIMIT 5"
                ).fetchall()
            processed_recent = sum(int(cnt) for day, cnt in processed_by_day
                                   if day and day >= cutoff[:10])
            inbox_stats: dict[str, Any] = {
                "pending_total": pending_total,
                "pending_recent": pending_recent,
                "processed_recent": processed_recent,
                "recent_items": [
                    {"text": (r["content"] or "")[:80], "status": r["status"],
                     "created": r["created_at"] or ""}
                    for r in recent_rows
                ],
            }
        except Exception:
            inbox_stats = _inbox_stats_jsonl()

        return {
            "period_days": days,
            "inbox": inbox_stats,
            "message": (
                f"过去 {days} 天：新增 {inbox_stats['pending_recent']} 项，"
                f"处理 {inbox_stats['processed_recent']} 项，"
                f"剩余 {inbox_stats['pending_total']} 项待办"
            ),
        }

    def _growth_milestone(a: dict[str, Any]) -> Any:
        """检查技能境界突破，报告成就"""
        from ...tui.data import TuiDataAdapter
        from ...core.paths import SkillStateManager

        skill_id = a.get("skill_id", "zenskill-core")
        adapter = TuiDataAdapter()

        # 获取当前状态
        state = adapter.get_skill_state(skill_id)
        abilities = adapter.get_ability_scores(skill_id)
        achievements = adapter.get_achievements(skill_id)

        return {
            "skill_id": skill_id,
            "state": state,
            "abilities": str(abilities)[:500] if abilities else None,
            "achievements": str(achievements)[:500] if achievements else None,
            "message": f"{skill_id} 当前境界：{state.get('level', 'NOVICE')}，使用 {state.get('usage_count', 0)} 次",
        }

    def _growth_dashboard(a: dict[str, Any]) -> Any:
        """技能成长仪表盘：境界/使用统计/五维能力分数"""
        from ...tui.data import TuiDataAdapter
        from dataclasses import asdict

        adapter = TuiDataAdapter()
        skills = adapter.list_skills()
        results = []
        for s in skills:
            skill_id = s["skill_id"]
            try:
                scores = adapter.get_ability_scores(skill_id)
                scores_dict = asdict(scores) if scores else None
            except Exception:
                scores_dict = None
            results.append({
                "skill_id": skill_id,
                "level": s.get("level", "NOVICE"),
                "usage_count": s.get("usage_count", 0),
                "success_rate": round(s.get("success_rate", 0.0), 2),
                "last_used": s.get("last_used", ""),
                "scores": scores_dict,
            })
        return {"count": len(results), "skills": results}

    def _memory_search(a: dict[str, Any]) -> Any:
        """按关键词搜索记忆（遍历多个 skill_id 的 episodes）"""
        from ...core.paths import SkillStateManager

        query = a["query"].lower()
        n = int(a.get("n", 10))

        all_episodes = []
        for skill_id in ["zenskill", "zenskill-core", "mcp-test", "craft-gui"]:
            try:
                state = SkillStateManager(skill_id).load()
                for ep in state.get("episodes", []):
                    content = ep.get("content", "").lower()
                    action = ep.get("action", "").lower()
                    if query in content or query in action:
                        all_episodes.append({
                            "skill_id": skill_id,
                            "action": ep.get("action", ""),
                            "content": ep.get("content", ""),
                            "date": ep.get("date", ""),
                            "relevance": content.count(query) + action.count(query),
                        })
            except Exception:
                pass

        # 按相关性排序
        all_episodes.sort(key=lambda x: x["relevance"], reverse=True)
        return {
            "query": a["query"],
            "count": len(all_episodes),
            "showing": min(n, len(all_episodes)),
            "items": all_episodes[:n],
            "message": f"搜索 '{a['query']}'：找到 {len(all_episodes)} 条相关记忆",
        }

    def _memory_forget(a: dict[str, Any]) -> Any:
        """按内容模糊匹配删除第一条记忆（episode）。

        skill_id 缺省 all：与 memory_list 同口径聚合遍历，命中即删即返回；
        读写走 SkillStateManager state JSON（memory_list/memory_search 同源）。
        """
        from ...core.paths import SkillStateManager

        query = str(a.get("query") or "").strip()
        if not query:
            return {"ok": False, "deleted": False,
                    "message": "需要 query（按内容模糊匹配，删除第一条匹配项）"}
        needle = query.lower()
        skill_id = str(a.get("skill_id") or "all").strip()
        skill_ids = (["zenskill", "zenskill-core", "mcp-test", "craft-gui"]
                     if skill_id in ("", "all") else [skill_id])

        for sid in skill_ids:
            try:
                mgr = SkillStateManager(sid)
                state = mgr.load()
                episodes = state.get("episodes", [])
            except Exception:
                continue
            for idx, ep in enumerate(episodes):
                content = str(ep.get("content", ""))
                action = str(ep.get("action", ""))
                if needle not in content.lower() and needle not in action.lower():
                    continue
                episodes.pop(idx)
                try:
                    mgr.save(state, action="memory_forget")
                except Exception as e:
                    return {"ok": False, "deleted": False, "skill_id": sid,
                            "message": f"记忆删除失败: {e}"}
                return {
                    "ok": True,
                    "deleted": True,
                    "skill_id": sid,
                    "action": action,
                    "content": content,
                    "message": f"已删除 {sid} 的记忆: {content[:80]}",
                }
        return {"ok": True, "deleted": False, "query": query,
                "message": f"未找到内容包含「{query}」的记忆"}

    registry.register(
        "skill_search",
        "搜索 ZenSkill 技能生态（本地索引 + 使用统计排序）",
        _skill_search,
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "自然语言关键词（中英文均可）"},
                "category": {"type": "string", "description": "分类过滤: dev/design/data/ops/writing/general/system"},
                "difficulty": {"type": "string", "description": "难度过滤: beginner/intermediate/advanced/expert"},
                "top_k": {"type": "integer", "description": "返回数量，默认 10"},
            },
            "required": ["query"],
        },
    )
    registry.register(
        "skill_browse",
        "按分类浏览已安装技能（分组统计 + 每组 top N）",
        _skill_browse,
        {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "每分类显示数量，默认 3"}},
        },
    )
    registry.register(
        "skill_trending",
        "列出热门技能",
        _skill_trending,
        {
            "type": "object",
            "properties": {"top_k": {"type": "integer", "description": "返回数量，默认 10"}},
        },
    )
    registry.register(
        "skill_install",
        "安装技能（支持 github:// clawhub:// npm:// pypi:// https:// file:// builtin 等来源）",
        _skill_install,
        {
            "type": "object",
            "properties": {"uri": {"type": "string", "description": "技能 URI 或 GitHub URL"}},
            "required": ["uri"],
        },
    )
    registry.register(
        "skill_uninstall",
        "卸载技能",
        _skill_uninstall,
        {
            "type": "object",
            "properties": {"skill_id": {"type": "string"}},
            "required": ["skill_id"],
        },
    )
    registry.register(
        "gtd_capture",
        "收集一条想法/任务到 ZenSkill GTD inbox",
        _gtd_capture,
        {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "原始想法文本"}},
            "required": ["text"],
        },
    )
    registry.register(
        "gtd_inbox_list",
        "列出 GTD inbox 条目",
        _gtd_inbox_list,
        {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "unprocessed/processed，默认 unprocessed"},
                "limit": {"type": "integer", "description": "默认 20"},
            },
        },
    )
    registry.register(
        "inbox_clarify",
        "澄清 inbox 条目（自动意图分类 action/project/calendar/reference，"
        "action/project/calendar 会自动创建下游对象并回填 target_id）",
        _inbox_clarify,
        {
            "type": "object",
            "properties": {
                "item_id": {"type": "string", "description": "inbox 条目 ID"},
                "result_type": {"type": "string",
                                "enum": ["action", "project", "calendar", "reference"],
                                "description": "可选，不传则自动分类；action/project/calendar 自动落下游对象"},
                "target_id": {"type": "string", "description": "可选，已存在的澄清目标 ID（传了则不重复创建）"},
            },
            "required": ["item_id"],
        },
    )
    registry.register(
        "inbox_archive",
        "归档 inbox 条目",
        _inbox_archive,
        {
            "type": "object",
            "properties": {"item_id": {"type": "string", "description": "inbox 条目 ID"}},
            "required": ["item_id"],
        },
    )
    registry.register(
        "inbox_suggest",
        "批量获取 inbox 条目的 AI 分类建议（只读，不写入）",
        _inbox_suggest,
        {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "扫描条数，默认 50"}},
        },
    )
    registry.register(
        "memory_remember",
        "为技能写入一条记忆（episode）",
        _memory_remember,
        {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string", "description": "默认 zenskill"},
                "content": {"type": "string"},
                "action": {"type": "string", "description": "记忆类型标签，默认 memory_add"},
            },
            "required": ["content"],
        },
    )
    registry.register(
        "memory_list",
        "列出技能记忆（最近的 episode）",
        _memory_list,
        {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string", "description": "技能 ID，传 all 聚合全部技能"},
                "n": {"type": "integer", "description": "返回条数，默认 10"},
            },
        },
    )
    registry.register(
        "dashboard_summary",
        "ZenSkill 仪表盘摘要（技能数/境界/待办/洞察）",
        _dashboard_summary,
    )
    registry.register(
        "growth_report",
        "技能成长报告",
        _growth_report,
        {
            "type": "object",
            "properties": {"skill_id": {"type": "string"}},
            "required": ["skill_id"],
        },
    )
    registry.register(
        "skill_context",
        "获取技能详细文档（SKILL.md 内容 + 索引元数据）",
        _skill_context,
        {
            "type": "object",
            "properties": {"skill_id": {"type": "string", "description": "技能 ID"}},
            "required": ["skill_id"],
        },
    )
    registry.register(
        "gtd_review",
        "每周回顾：本周完成/未完成/能量统计",
        _gtd_review,
        {
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "回顾天数，默认 7"}},
        },
    )
    registry.register(
        "growth_milestone",
        "检查技能境界突破，报告成就",
        _growth_milestone,
        {
            "type": "object",
            "properties": {"skill_id": {"type": "string", "description": "默认 zenskill"}},
        },
    )
    registry.register(
        "growth_dashboard",
        "技能成长仪表盘：境界/使用统计/五维能力分数",
        _growth_dashboard,
    )
    registry.register(
        "memory_search",
        "按关键词搜索记忆（语义匹配）",
        _memory_search,
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "n": {"type": "integer", "description": "返回条数，默认 10"},
            },
            "required": ["query"],
        },
    )
    registry.register(
        "memory_forget",
        "按内容模糊匹配删除第一条记忆（episode）",
        _memory_forget,
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "匹配关键词（content/action 子串，删除第一条命中项）"},
                "skill_id": {"type": "string", "description": "技能 ID，缺省 all 聚合遍历（与 memory_list 同口径）"},
            },
            "required": ["query"],
        },
    )

    # ============================================================
    # 第一梯队：高价值 + 低成本（直接桥接现有 API）
    # ============================================================

    def _energy_level(a: dict[str, Any]) -> Any:
        """获取当前能量状态（含建议）"""
        from ...systems.gtd.energy import EnergyEngine
        engine = EnergyEngine()
        status = engine.status()
        advise = engine.advise()
        return {
            "status": status,
            "advice": {
                "suggestions": advise.get("suggestions", []),
                "total_burned_7d": advise.get("total_burned_7d", 0),
                "peak_hour": advise.get("peak_hour"),
            },
            "message": f"当前能量：{status.get('level', '?')}（{int(status.get('pct', 0)*100)}%）",
        }

    def _zenloop_run(a: dict[str, Any]) -> Any:
        """触发 ZenLoop 循环（WP-B：automation/无人值守场景的工具入口）"""
        import asyncio
        import concurrent.futures
        from ...systems.zenloop.zenloop_system import ZenLoopSystem
        from ...systems.zenloop.loop_base import LoopType

        name = (a.get("loop_type") or "reflection").upper()
        try:
            loop_type = LoopType[name]
        except KeyError:
            valid = [t.name.lower() for t in LoopType]
            return {"ok": False,
                    "message": f"未知循环类型 {name}，可选: {', '.join(valid)}"}

        zl = ZenLoopSystem()
        # handler 可能跑在 serve 的 asyncio loop 内——独立线程开新 loop 执行
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(asyncio.run, zl.trigger_loop(
                loop_type, {"source": "mcp"}))
            try:
                results = future.result(timeout=90.0)
            except concurrent.futures.TimeoutError:
                return {"ok": False,
                        "message": f"ZenLoop {name} 执行超时（90s）"}

        summaries = []
        for r in results:
            summaries.append({
                "loop": getattr(r, "loop_type", name),
                "summary": getattr(r, "summary", "")[:200],
                "success": getattr(r, "success", True),
            })
        if not results:
            return {"ok": True, "executed": 0, "results": [],
                    "message": f"ZenLoop {name} 未触发（插件触发条件未满足，如交互数/间隔/错误数）"}
        return {"ok": True, "executed": len(results), "results": summaries,
                "message": f"ZenLoop {name} 执行 {len(results)} 个插件"}

    def _calendar_list(a: dict[str, Any]) -> Any:
        """日程列表：今日或本周（GTD CalendarEngine）"""
        from ...systems.gtd.calendar import CalendarEngine

        cal = CalendarEngine()
        scope = a.get("scope", "today")
        if scope == "week":
            weeks = cal.week()
            events = []
            for i, day_events in enumerate(weeks):
                for e in day_events:
                    events.append(e)
            label = "本周"
        else:
            events = cal.today()
            label = "今日"

        shown = events[:20]
        return {
            "scope": scope,
            "count": len(shown),
            "events": [
                {"id": getattr(e, "id", "") or "",
                 "date": e.date, "time": getattr(e, "time_str", "") or "",
                 "end_time": getattr(e, "end_time", "") or "",
                 "title": e.title, "action_id": getattr(e, "action_id", "") or ""}
                for e in shown
            ],
            "message": f"{label}日程 {len(shown)} 条",
        }

    def _calendar_add(a: dict[str, Any]) -> Any:
        """添加日程事件（CalendarEngine.add；action_id 走 add 后关联，
        标题缺省时按 schedule_action 语义从行动解析）"""
        from ...systems.gtd.calendar import CalendarEngine

        action_id = a.get("action_id", "")
        title = (a.get("title") or "").strip()
        if not title and action_id:
            from ...systems.gtd.action import ActionEngine
            action = ActionEngine().get(action_id)
            title = action.title if action else action_id
        if not title:
            return {"ok": False, "message": "需要 title（或可解析标题的 action_id）"}

        kwargs: dict[str, Any] = {}
        if a.get("time_str"):
            kwargs["time_str"] = a["time_str"]
        if a.get("end_time"):
            kwargs["end_time"] = a["end_time"]
        if a.get("period"):
            kwargs["period"] = a["period"]
        if a.get("repeat_rule"):
            kwargs["repeat_rule"] = a["repeat_rule"]
        if action_id:
            kwargs["action_id"] = action_id
        event = CalendarEngine().add(a["date"], title, **kwargs)
        when = f"{event.date} {event.time_str}".strip() if event.time_str else event.date
        return {
            "ok": True,
            "event": event.to_dict(),
            "message": f"已添加日程：{when} {event.title}",
        }

    def _calendar_delete(a: dict[str, Any]) -> Any:
        """删除日程事件"""
        from ...systems.gtd.calendar import CalendarEngine

        event_id = a["event_id"]
        ok = CalendarEngine().delete(event_id)
        return {
            "ok": ok,
            "event_id": event_id,
            "message": f"日程 {event_id} 已删除" if ok
                       else f"未找到日程 {event_id}",
        }

    def _calendar_update(a: dict[str, Any]) -> Any:
        """更新日程事件字段（date/time_str/title/end_time/repeat_rule/period）"""
        from ...systems.gtd.calendar import CalendarEngine

        event_id = a["event_id"]
        fields = {k: v for k, v in a.items()
                  if k != "event_id" and v is not None
                  and not k.startswith("_")}
        if not fields:
            return {"ok": False, "event_id": event_id,
                    "message": ("未提供要更新的字段"
                                "（可选 date/time_str/title/end_time/repeat_rule/period）")}
        updated = CalendarEngine().update(event_id, **fields)
        return {
            "ok": updated is not None,
            "event_id": event_id,
            "event": updated.to_dict() if updated else None,
            "message": f"日程 {event_id} 已更新" if updated
                       else f"未找到日程 {event_id}",
        }

    def _calendar_month(a: dict[str, Any]) -> Any:
        """月视图：原样返回 engine.month_view()
        形状：{year, month, month_name, days, events}，
        days 为 {完整日期 "YYYY-MM-DD": 事件数} 映射，
        events 为按日分组的完整事件列表（每项含 id/time_str/title 等），
        仅包含本月有事件的日期；year/month 缺省为当月"""
        from ...systems.gtd.calendar import CalendarEngine

        return CalendarEngine().month_view(
            int(a.get("year") or 0), int(a.get("month") or 0))

    def _calendar_suggest(a: dict[str, Any]) -> Any:
        """智能排期建议：今日空闲槽位（每项 {date, time, period}，
        按历史活跃时段推荐，避开今日已占用时间）"""
        from ...systems.gtd.calendar import CalendarEngine

        suggestions = CalendarEngine().suggest()
        return {
            "count": len(suggestions),
            "suggestions": suggestions,
            "message": (f"建议 {len(suggestions)} 个今日排期槽位"
                        if suggestions else "今日槽位已满，暂无建议"),
        }

    def _session_summary(a: dict[str, Any]) -> Any:
        """会话摘要回流（WP-C：SessionManager complete 钩子经 MCP 写入）。

        detail_level:
        - "summary"（默认）: 一条 episode 摘要
        - "full": 逐条消息写入 episodes（每条截断 500 字符），跨会话记忆搜索可命中
        """
        from ...core.paths import SkillStateManager

        skill_id = a.get("skill_id", "zenskill-core")
        detail_level = a.get("detail_level", "summary")
        mgr = SkillStateManager(skill_id)
        from pathlib import Path

        message_count = int(a.get("message_count") or 0)
        tool_count = int(a.get("tool_count") or 0)
        first_message = (a.get("first_message") or "")[:80]
        content = (f"会话摘要: {message_count} 条消息 / {tool_count} 次工具调用"
                   + (f" | {first_message}" if first_message else ""))

        if detail_level == "full" and a.get("session_path"):
            session_file = Path(a["session_path"])
            if session_file.exists():
                import json as _json
                for line in session_file.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        msg = _json.loads(line)
                    except Exception:
                        continue
                    role = msg.get("type", "")
                    if role not in ("user", "assistant"):
                        continue
                    text = str(msg.get("content", ""))[:500]
                    if not text.strip():
                        continue
                    mgr.record_episode(f"session_{role}", text)
            else:
                SkillStateManager(skill_id).record_episode("session_summary", content)
        else:
            mgr.record_episode("session_summary", content)

        return {"ok": True,
                "detail_level": detail_level,
                "message": f"会话摘要已记录（{message_count} 条消息 / {tool_count} 次工具调用，detail={detail_level}）"}

    def _daily_review(a: dict[str, Any]) -> Any:
        """每日复盘：今日 inbox 处理、action 完成、能量变化、成就、习惯"""
        import time
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")

        # Inbox — SQLite 精确统计（无 limit 截断）；异常降级回 JSONL 全量扫描
        def _inbox_stats_jsonl() -> tuple[int, int]:
            from ...systems.gtd.inbox import InboxEngine
            inbox = InboxEngine()
            all_inbox = inbox.list(status="all", limit=10 ** 6)

            def _done_today(i: Any) -> bool:
                if i.status not in ("clarified", "archived"):
                    return False
                cr = i.clarify_result if isinstance(i.clarify_result, dict) else {}
                clarified_at = str(cr.get("clarified_at") or "")
                archived_at = str(cr.get("archived_at") or "")
                if clarified_at[:10] == today or archived_at[:10] == today:
                    return True
                # 旧数据无处理时间戳：回退 created_at 近似
                return not (clarified_at or archived_at) and i.created_at[:10] == today

            processed = sum(1 for i in all_inbox if _done_today(i))
            return processed, inbox.count()

        try:
            from ...core.database import db
            with db.connect() as conn:
                pending = conn.execute(
                    "SELECT COUNT(*) FROM gtd_inbox WHERE status='unprocessed'"
                ).fetchone()[0]
                # 已处理时间：clarified_at 为空串/NULL（直接归档）时回退 created_at；
                # 截前 10 位与 JSONL 版 created_at[:10] 语义一致
                processed_today = conn.execute(
                    "SELECT COUNT(*) FROM gtd_inbox WHERE status IN ('clarified','archived') "
                    "AND substr(COALESCE(NULLIF(clarified_at, ''), created_at), 1, 10) = ?",
                    (today,),
                ).fetchone()[0]
        except Exception:
            processed_today, pending = _inbox_stats_jsonl()

        # Actions
        from ...systems.gtd.action import ActionEngine
        ae = ActionEngine()
        all_actions = ae.list(status="all", limit=500)
        completed_today = [
            a for a in all_actions
            if a.status == "done" and a.completed_at[:10] == today
        ]
        added_today = [
            a for a in all_actions
            if a.created_at[:10] == today
        ]

        # Energy
        from ...systems.gtd.energy import EnergyEngine
        energy = EnergyEngine()
        e_status = energy.status()
        e_advise = energy.advise()

        # Achievements
        from ...systems.active.achievement_system import AchievementSystem
        ach = AchievementSystem("zenskill-core").evaluate()

        # Habits
        from ...systems.active.habit_tracker import HabitTracker
        habits = HabitTracker().analyze(days=1)
        habits_today = [
            r for r in habits.get("habits", [])
            if any(ok for ok in r.get("completed", {}).values())
        ]

        return {
            "date": today,
            "inbox": {"processed": processed_today, "pending": pending},
            "actions": {
                "completed": len(completed_today),
                "added": len(added_today),
                "completed_titles": [a.title for a in completed_today[:5]],
            },
            "energy": {
                "level": e_status.get("level", "?"),
                "pct": e_status.get("pct", 0),
                "peak_hour": e_advise.get("peak_hour"),
            },
            "achievements": {
                "unlocked": ach["unlocked_count"],
                "total": ach["total"],
            },
            "habits_today": len(habits_today),
            "message": (
                f"📊 {today} 复盘：完成 {len(completed_today)} 个行动，"
                f"处理 {processed_today} 条 inbox，"
                f"能量 {e_status.get('level', '?')}，"
                f"成就 {ach['unlocked_count']}/{ach['total']}"
            ),
        }

    registry.register(
        "daily_review",
        "每日复盘：今日 inbox/action/energy/成就/习惯汇总",
        _daily_review,
    )
    registry.register(
        "session_summary",
        "会话摘要回流：消息数/工具调用数/首条消息 → episodes",
        _session_summary,
        {
            "type": "object",
            "properties": {
                "detail_level": {"type": "string",
                                 "enum": ["summary", "full"],
                                 "description": "summary=一条摘要（默认）；full=逐条消息写入 episodes"},
                "session_path": {"type": "string",
                                 "description": "session.jsonl 路径（full 模式必填）"},
            },
        },
    )
    registry.register(
        "calendar_list",
        "日程列表：今日/本周的 GTD 日程（CalendarEngine）",
        _calendar_list,
        {
            "type": "object",
            "properties": {"scope": {
                "type": "string",
                "enum": ["today", "week"],
                "description": "范围，默认 today"}},
        },
    )
    registry.register(
        "calendar_add",
        "添加日程事件（GTD CalendarEngine）：带 action_id 时关联行动"
        "（标题缺省自动取行动标题）；period 缺省按 time_str 推断时段",
        _calendar_add,
        {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "日期 YYYY-MM-DD"},
                "title": {"type": "string", "description": "事件标题"},
                "time_str": {"type": "string", "description": "开始时间 HH:MM（可选）"},
                "end_time": {"type": "string", "description": "结束时间 HH:MM（可选）"},
                "repeat_rule": {"type": "string",
                                "enum": ["daily", "weekly", "monthly"],
                                "description": "重复规则（可选）"},
                "period": {"type": "string",
                           "enum": ["morning", "afternoon", "evening"],
                           "description": "时段（可选，缺省按 time_str 推断）"},
                "action_id": {"type": "string",
                              "description": "关联 GTD 行动 ID（可选）"},
            },
            "required": ["date", "title"],
        },
    )
    registry.register(
        "calendar_delete",
        "删除日程事件",
        _calendar_delete,
        {
            "type": "object",
            "properties": {"event_id": {"type": "string", "description": "日程事件 ID"}},
            "required": ["event_id"],
        },
    )
    registry.register(
        "calendar_update",
        "更新日程事件字段（date/time_str/title/end_time/repeat_rule/period；"
        "time_str 变更时自动重算时段）",
        _calendar_update,
        {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "日程事件 ID"},
                "date": {"type": "string", "description": "日期 YYYY-MM-DD"},
                "time_str": {"type": "string", "description": "开始时间 HH:MM"},
                "title": {"type": "string", "description": "事件标题"},
                "end_time": {"type": "string", "description": "结束时间 HH:MM（可选）"},
                "repeat_rule": {"type": "string",
                                "enum": ["daily", "weekly", "monthly"],
                                "description": "重复规则（可选）"},
                "period": {"type": "string",
                           "enum": ["morning", "afternoon", "evening"],
                           "description": "时段（可选，缺省按 time_str 重算）"},
            },
            "required": ["event_id"],
        },
    )
    registry.register(
        "calendar_month",
        "月视图：返回 {year, month, month_name, days, events}，"
        "days 为 {完整日期 YYYY-MM-DD: 事件数} 映射，events 为按日分组的完整事件列表"
        "（仅含本月有事件的日期；year/month 缺省当月）",
        _calendar_month,
        {
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "年份，缺省当年"},
                "month": {"type": "integer", "description": "月份 1-12，缺省当月"},
            },
        },
    )
    registry.register(
        "calendar_suggest",
        "智能排期建议：今日空闲槽位列表（每项含 date/time/period，"
        "按历史活跃时段推荐并避开已占用时间）",
        _calendar_suggest,
    )
    registry.register(
        "zenloop_run",
        "触发 ZenLoop 循环（reflection/consolidation/insight/purification）——"
        "定时自动化/无人值守反思入口",
        _zenloop_run,
        {
            "type": "object",
            "properties": {"loop_type": {
                "type": "string",
                "description": "循环类型，默认 reflection"}},
        },
    )

    def _action_list_item(i: Any) -> dict[str, Any]:
        """action_list 条目：基础字段 + GTD 视图所需字段 + 来源标记（如有值）"""
        d: dict[str, Any] = {"id": i.id, "title": i.title,
                             "priority": _display_priority(i.priority),
                             "status": i.status, "due_date": i.due_date}
        for f in ("project_id", "energy_required", "contexts", "repeat_rule"):
            v = getattr(i, f, None)
            if v is None:
                v = [] if f == "contexts" else (0 if f == "energy_required" else "")
            d[f] = v
        if getattr(i, "source_session_id", ""):
            d["source_session_id"] = i.source_session_id
        if getattr(i, "created_by", ""):
            d["created_by"] = i.created_by
        return d

    def _action_row_item(r: Any) -> dict[str, Any]:
        """SQLite 行 → action_list 条目（与 _action_list_item 同构）"""
        try:
            contexts = json.loads(r["contexts"]) if r["contexts"] not in (None, "") else []
        except Exception:
            contexts = r["contexts"] or []
        d: dict[str, Any] = {"id": r["action_id"], "title": r["title"],
                             "priority": _display_priority(r["priority"]),
                             "status": r["status"], "due_date": r["due_date"] or ""}
        d["project_id"] = r["project_id"] or ""
        d["energy_required"] = r["energy_required"] if r["energy_required"] is not None else 0
        d["contexts"] = contexts
        d["repeat_rule"] = r["repeat_rule"] or ""
        if r["source_session_id"]:
            d["source_session_id"] = r["source_session_id"]
        if r["created_by"]:
            d["created_by"] = r["created_by"]
        return d

    def _action_list_sql(a: dict[str, Any]) -> list[dict[str, Any]]:
        """action_list 的 SQLite 查询路径（索引过滤 + 排序 + 截断下推）。

        前置 reconcile_sqlite 对账：直写 JSONL 的历史数据 / 旧版删除残留
        以 JSONL 为准幂等重建。任一步失败抛出，由 _action_list 降级 JSONL。
        """
        from ...core.database import db
        from ...systems.gtd.action import ActionEngine
        ActionEngine().reconcile_sqlite()

        sql = ("SELECT action_id, title, status, priority, energy_required, contexts, "
               "due_date, project_id, repeat_rule, source_session_id, created_by "
               "FROM gtd_actions WHERE 1=1")
        params: list[Any] = []
        status = a.get("status", "pending")
        if status and status != "all":
            sql += " AND status = ?"
            params.append(status)
        if a.get("project_id"):
            sql += " AND project_id = ?"
            params.append(a["project_id"])
        if a.get("priority"):
            sql += " AND priority = ?"
            params.append(a["priority"])
        if a.get("context"):
            # JSONL 语义：contexts 为 str 时子串匹配、list 时成员匹配；
            # JSON 编码后标量与列表元素都带双引号，引号包裹等值匹配覆盖两种形态
            sql += " AND contexts LIKE ?"
            params.append(f'%"{a["context"]}"%')
        if a.get("due_today"):
            from datetime import datetime
            sql += " AND substr(due_date, 1, 10) = ?"
            params.append(datetime.now().strftime("%Y-%m-%d"))
        sql += (" ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 "
                "WHEN 'P2' THEN 2 ELSE 3 END, created_at DESC LIMIT ?")
        params.append(int(a.get("limit", 20)))
        with db.connect() as conn:
            return [_action_row_item(r) for r in conn.execute(sql, params).fetchall()]

    def _action_add(a: dict[str, Any]) -> Any:
        """添加 GTD 下一步行动"""
        from ...systems.gtd.action import ActionEngine
        source_session_id, created_by = _pop_source_context(a)
        engine = ActionEngine()
        kwargs = {}
        if a.get("priority"): kwargs["priority"] = _normalize_priority(a["priority"])
        if a.get("energy_required"): kwargs["energy_required"] = _normalize_energy(a["energy_required"])
        if a.get("project_id"): kwargs["project_id"] = a["project_id"]
        if a.get("contexts"): kwargs["contexts"] = a["contexts"]
        if a.get("due_date"): kwargs["due_date"] = a["due_date"]
        if a.get("skill_id"): kwargs["skill_id"] = a["skill_id"]
        if a.get("repeat_rule"): kwargs["repeat_rule"] = a["repeat_rule"]
        action = engine.add(a["title"], source_session_id=source_session_id,
                            created_by=created_by, **kwargs)
        return {
            "ok": True,
            "id": action.id,
            "title": action.title,
            "priority": action.priority,
            "message": f"已添加行动：{action.title}（优先级：{action.priority}）",
        }

    def _action_list(a: dict[str, Any]) -> Any:
        """列出待办行动（SQLite 索引查询优先；异常降级 JSONL 内存过滤）"""
        from ...systems.gtd.action import ActionEngine
        try:
            items = _action_list_sql(a)
        except Exception:
            engine = ActionEngine()
            fallback = engine.list(
                status=a.get("status", "pending"),
                project_id=a.get("project_id", ""),
                context=a.get("context", ""),
                priority=a.get("priority", ""),
                due_today=a.get("due_today", False),
                limit=int(a.get("limit", 20)),
            )
            items = [_action_list_item(i) for i in fallback]
        return {
            "count": len(items),
            "items": items,
            "message": f"找到 {len(items)} 个待办行动",
        }

    def _diff_achievements(skill_id: str = "zenskill-core"):
        """返回 (system, before_set) 供执行后 diff"""
        from ...systems.active.achievement_system import AchievementSystem
        system = AchievementSystem(skill_id)
        before = {b.badge_id for b in system.evaluate()["unlocked"]}
        return system, before

    def _new_badge_titles(system, before: set) -> list[str]:
        """返回新解锁徽章的 [{icon} title] 列表"""
        after = system.evaluate()
        return [f"{b.icon} {b.title}" for b in after["unlocked"] if b.badge_id not in before]

    def _action_done(a: dict[str, Any]) -> Any:
        """完成行动 — 触发成长记录、重复任务再生、成就解锁检测"""
        from ...systems.gtd.action import ActionEngine
        engine = ActionEngine()
        action_id = a["action_id"]
        action = engine.get(action_id)
        if not action:
            return {"ok": False, "action_id": action_id,
                    "message": f"未找到行动 {action_id}"}
        skill_id = action.skill_id or "zenskill-core"
        system, before = _diff_achievements(skill_id)
        energy = int(a.get("energy_invested", action.energy_required or 0))
        ok = engine.done(action_id, energy_invested=energy)
        effects = []
        if action.skill_id:
            effects.append("成长已记录")
        if action.repeat_rule:
            effects.append(f"重复任务已生成下一实例（{action.repeat_rule}）")
        new_badges = _new_badge_titles(system, before)
        if new_badges:
            effects.extend([f"解锁成就 {b}" for b in new_badges])
        result = {
            "ok": ok,
            "action_id": action_id,
            "title": action.title,
            "energy_invested": energy,
            "effects": effects,
            "new_achievements": new_badges,
            "message": f"行动「{action.title}」已完成" + (f"，{'、'.join(effects)}" if effects else ""),
        }
        if ok and energy > 0:
            try:
                from ...systems.gtd.energy import EnergyEngine
                pool = EnergyEngine().status()
                result["energy_pool"] = {
                    "level": pool.get("level"),
                    "remaining": pool.get("current_energy"),
                    "max": pool.get("max_energy"),
                }
                if pool.get("current_energy", 0) < 10:
                    result["message"] += "（能量不足 10，建议休息）"
            except Exception:
                pass
        return result

    def _action_mark_next(a: dict[str, Any]) -> Any:
        """标记行动为 next（准备执行）"""
        from ...systems.gtd.action import ActionEngine
        engine = ActionEngine()
        action_id = a["action_id"]
        action = engine.get(action_id)
        if not action:
            return {"ok": False, "action_id": action_id,
                    "message": f"未找到行动 {action_id}"}
        ok = engine.mark_next(action_id)
        return {"ok": ok, "action_id": action_id, "title": action.title,
                "message": f"行动「{action.title}」已标记为 next" if ok else "更新失败"}

    def _action_update(a: dict[str, Any]) -> Any:
        """更新行动字段（title/priority/due_date/contexts/skill_id/repeat_rule 等）"""
        from ...systems.gtd.action import ActionEngine
        engine = ActionEngine()
        action_id = a["action_id"]
        action = engine.get(action_id)
        if not action:
            return {"ok": False, "action_id": action_id,
                    "message": f"未找到行动 {action_id}"}
        fields = {k: v for k, v in a.items()
                  if k != "action_id" and v is not None
                  and not k.startswith("_")}
        # 入参归一化：high/medium/low → P1/P2/P3；能量别名 → 数字
        if "priority" in fields:
            fields["priority"] = _normalize_priority(fields["priority"])
        if "energy_required" in fields:
            fields["energy_required"] = _normalize_energy(fields["energy_required"])
        updated = engine.edit(action_id, **fields)
        return {
            "ok": updated is not None,
            "action_id": action_id,
            "title": updated.title if updated else "",
            "message": f"行动「{action.title}」已更新" if updated else "更新失败",
        }

    def _action_delete(a: dict[str, Any]) -> Any:
        """删除行动"""
        from ...systems.gtd.action import ActionEngine
        engine = ActionEngine()
        action = engine.get(a["action_id"])
        if not action:
            return {"ok": False, "action_id": a["action_id"],
                    "message": f"未找到行动 {a['action_id']}"}
        ok = engine.delete(a["action_id"])
        return {"ok": ok, "action_id": a["action_id"], "title": action.title,
                "message": f"行动「{action.title}」已删除" if ok else "删除失败"}

    def _project_add(a: dict[str, Any]) -> Any:
        """创建项目（ProjectEngine.create）"""
        from ...systems.gtd.project import ProjectEngine
        engine = ProjectEngine()
        kwargs: dict[str, Any] = {}
        if a.get("outcome"):
            kwargs["outcome"] = a["outcome"]
        if a.get("skill_id"):
            kwargs["skill_id"] = a["skill_id"]
        proj = engine.create(a["name"], **kwargs)
        return {
            "ok": True,
            "id": proj.id,
            "name": proj.name,
            "outcome": proj.outcome,
            "message": f"已创建项目「{proj.name}」"
                       + (f"（id: {proj.id}）" if proj.id else ""),
        }

    def _project_update(a: dict[str, Any]) -> Any:
        """更新项目字段（name/outcome/notes/status）"""
        from ...systems.gtd.project import ProjectEngine

        engine = ProjectEngine()
        project_id = a["project_id"]
        project = engine.get(project_id)
        if not project:
            return {"ok": False, "project_id": project_id,
                    "message": f"未找到项目 {project_id}"}
        fields = {k: v for k, v in a.items()
                  if k != "project_id" and v is not None
                  and not k.startswith("_")}
        if not fields:
            return {"ok": False, "project_id": project_id,
                    "message": "未提供要更新的字段（可选 name/outcome/notes/status）"}
        updated = engine.update(project_id, **fields)
        return {
            "ok": updated is not None,
            "project_id": project_id,
            "name": updated.name if updated else "",
            "message": f"项目「{project.name}」已更新" if updated else "更新失败",
        }

    def _project_list(a: dict[str, Any]) -> Any:
        """列出项目及其进度"""
        from ...systems.gtd.project import ProjectEngine
        engine = ProjectEngine()
        items = engine.list(
            status=a.get("status", "active"),
            parent_id=a.get("parent_id", ""),
        )
        return {
            "count": len(items),
            "items": [
                {"id": i.id, "name": i.name, "status": i.status,
                 "progress": getattr(i, "progress", 0)}
                for i in items[:20]
            ],
            "message": f"找到 {len(items)} 个项目",
        }

    def _project_done(a: dict[str, Any]) -> Any:
        """完成项目"""
        from ...systems.gtd.project import ProjectEngine
        engine = ProjectEngine()
        project_id = a["project_id"]
        project = engine.get(project_id)
        if not project:
            return {"ok": False, "project_id": project_id,
                    "message": f"未找到项目 {project_id}"}
        ok = engine.done(project_id)
        return {"ok": ok, "project_id": project_id, "name": project.name,
                "message": f"项目「{project.name}」已完成" if ok else "更新失败"}

    def _incubating_list(a: dict[str, Any]) -> Any:
        """列出孵化池条目（未成熟想法）"""
        from ...systems.gtd.incubating import IncubatingEngine
        items = IncubatingEngine().list(
            status=a.get("status", "active"),
            channel=a.get("channel", ""),
            limit=int(a.get("limit", 20)),
        )
        return {
            "count": len(items),
            "items": [
                {"id": i.id, "raw_concept": i.raw_concept[:80],
                 "channel": i.channel, "maturity": round(i.maturity, 2),
                 "status": i.status, "check_after": i.check_after}
                for i in items
            ],
            "message": f"孵化池有 {len(items)} 个活跃条目",
        }

    def _incubating_promote(a: dict[str, Any]) -> Any:
        """孵化成熟条目 → 提升为 Action"""
        from ...systems.gtd.incubating import IncubatingEngine
        engine = IncubatingEngine()
        item_id = a["item_id"]
        item = engine.get(item_id)
        if not item:
            return {"ok": False, "item_id": item_id,
                    "message": f"未找到孵化条目 {item_id}"}
        if item.maturity < 0.8:
            return {"ok": False, "item_id": item_id,
                    "message": f"孵化条目成熟度 {round(item.maturity, 2)} < 0.8，暂不可提升"}
        ok = engine.promote(item_id)
        return {
            "ok": ok,
            "item_id": item_id,
            "concept": item.raw_concept[:60],
            "message": f"孵化条目已提升为行动" if ok else "提升失败",
        }

    def _habit_check(a: dict[str, Any]) -> Any:
        """记录习惯打卡 + 成就解锁检测"""
        from ...systems.active.habit_tracker import HabitTracker
        tracker = HabitTracker()
        habit_id = a["habit_id"]
        # 打卡前 snapshot 成就
        system, before = _diff_achievements("zenskill-core")
        try:
            result = tracker.check_in(habit_id)
        except ValueError as e:
            return {"ok": False, "habit_id": habit_id, "message": str(e)}
        new_badges = _new_badge_titles(system, before)
        effects = [f"连续 {result.get('streak', 0)} 天，"
                   f"7 天完成率 {round(result.get('completion_rate', 0) * 100)}%"]
        if new_badges:
            effects.extend([f"解锁成就 {b}" for b in new_badges])
        result["new_achievements"] = new_badges
        result["effects"] = effects
        result["message"] = f"习惯「{result['title']}」已打卡：" + "，".join(effects)
        return result

    def _habit_analyze(a: dict[str, Any]) -> Any:
        """习惯分析：每日打卡日历 + streak/完成率/风险"""
        from ...systems.active.habit_tracker import HabitTracker
        tracker = HabitTracker()
        days = int(a.get("days", 7))
        analysis = tracker.analyze(days=days)
        return {
            "days": days,
            "habits": [
                {
                    "id": r["habit"]["habit_id"],
                    "title": r["habit"]["title"],
                    "target": r["habit"]["target_count"],
                    "daily": r["daily"],
                    "completed": r["completed"],
                    "streak": r["streak"],
                    "best_streak": r["best_streak"],
                    "completion_rate": round(r["completion_rate"], 2),
                    "risk": r["risk"],
                }
                for r in analysis["habits"]
            ],
        }

    def _habit_list(a: dict[str, Any]) -> Any:
        """列出习惯及其完成率"""
        from ...systems.active.habit_tracker import HabitTracker
        tracker = HabitTracker()
        habits = tracker.list_habits()
        return {
            "count": len(habits),
            "items": [
                {"id": h.habit_id, "title": h.title, "target": h.target_count}
                for h in habits
            ],
            "message": f"找到 {len(habits)} 个习惯",
        }

    def _habit_set(a: dict[str, Any]) -> Any:
        """创建/更新习惯定义（HabitTracker.add_habit；habit_id 缺省由 title 归一化派生）"""
        from ...systems.active.habit_tracker import HabitTracker

        title = str(a.get("title") or "").strip()
        if not title:
            return {"ok": False, "message": "需要 title（习惯名称）"}
        try:
            habit_id = HabitTracker._normalize_id(a.get("habit_id") or title)
        except ValueError:
            habit_id = f"habit_{int(time.time())}"
        habit = HabitTracker().add_habit(
            habit_id,
            title,
            target_count=int(a.get("target_count") or 1),
            skill_id=a.get("skill_id"),
            action_contains=str(a.get("action_contains") or ""),
        )
        return {
            "ok": True,
            "habit": {
                "habit_id": habit.habit_id,
                "title": habit.title,
                "skill_id": habit.skill_id,
                "target_count": habit.target_count,
                "action_contains": habit.action_contains,
            },
            "message": (f"已保存习惯「{habit.title}」"
                        f"（id: {habit.habit_id}，每日 {habit.target_count} 次）"),
        }

    def _habit_delete(a: dict[str, Any]) -> Any:
        """删除习惯定义"""
        from ...systems.active.habit_tracker import HabitTracker

        habit_id = a["habit_id"]
        ok = HabitTracker().remove_habit(habit_id)
        return {
            "ok": ok,
            "habit_id": habit_id,
            "message": f"习惯 {habit_id} 已删除" if ok
                       else f"未找到习惯 {habit_id}",
        }

    def _achievement_list(a: dict[str, Any]) -> Any:
        """列出已解锁成就与进度中的徽章"""
        from ...systems.active.achievement_system import AchievementSystem
        skill_id = a.get("skill_id", "zenskill-core")
        system = AchievementSystem(skill_id)
        result = system.evaluate()
        return {
            "skill_id": skill_id,
            "count": result["unlocked_count"],
            "total": result["total"],
            "completion_rate": round(result["completion_rate"], 2),
            "badges": [
                {
                    "id": b.badge_id, "title": b.title, "tier": b.tier,
                    "icon": b.icon, "description": b.description,
                    "unlocked": b.unlocked, "progress": round(b.progress, 2),
                    "detail": b.detail,
                }
                for b in result["unlocked"]
            ],
            "locked": [
                {
                    "id": b.badge_id, "title": b.title, "tier": b.tier,
                    "icon": b.icon, "description": b.description,
                    "progress": round(b.progress, 2), "detail": b.detail,
                }
                for b in result["locked"]
            ],
            "message": f"{skill_id} 已解锁 {result['unlocked_count']}/{result['total']} 个成就",
        }

    def _goal_set(a: dict[str, Any]) -> Any:
        """设置技能成长目标（真引擎：ActiveGoalEngine.create_goal / suggest_goals）"""
        from ...systems.active.goal_engine import ActiveGoalEngine
        skill_id = a.get("skill_id", "zenskill-core")
        engine = ActiveGoalEngine(skill_id)

        # suggest 模式：引擎按短板自动推荐
        if a.get("suggest"):
            suggestions = engine.suggest_goals(n_goals=int(a.get("n", 2)))
            return {
                "skill_id": skill_id,
                "suggestions": [g.to_dict() for g in suggestions],
                "message": "推荐目标（按当前短板生成），确认后用 goal_set 带 dimension+target_score 落设",
            }

        dimension = a.get("dimension", "proficiency")
        target = int(a.get("target_score") or 0)
        if not target:
            return {"success": False,
                    "error": "需要 target_score（0-100），或传 suggest=true 让引擎推荐"}
        try:
            goal = engine.create_goal(
                dimension, target,
                deadline_interactions=a.get("deadline_interactions"),
            )
        except ValueError as e:
            return {"success": False, "error": str(e),
                    "hint": "维度可选: proficiency/stability/satisfaction/responsiveness/memory/composite"}
        prog = engine.get_goal_progress(goal)
        return {
            "success": True,
            "skill_id": skill_id,
            "goal": goal.to_dict(),
            "progress_pct": round(prog.progress_pct, 1),
            "message": (f"已设置目标：{skill_id} 的 {goal.dimension} "
                        f"{prog.current_score} → {goal.target_score} 分"
                        f"（预计约 {goal.deadline_interactions} 次交互）"),
        }

    def _goal_progress(a: dict[str, Any]) -> Any:
        """检查目标进度（真引擎：update_goal_status + get_goal_progress）"""
        from ...systems.active.goal_engine import ActiveGoalEngine
        skill_id = a.get("skill_id", "zenskill-core")
        engine = ActiveGoalEngine(skill_id)
        engine.update_goal_status()

        active = engine.get_active_goals()
        items = []
        for g in active:
            prog = engine.get_goal_progress(g)
            items.append({
                "goal_id": g.goal_id,
                "dimension": g.dimension,
                "start_score": prog.start_score,
                "current_score": prog.current_score,
                "target_score": prog.target_score,
                "progress_pct": round(prog.progress_pct, 1),
                "deadline_interactions": g.deadline_interactions,
            })
        completed = [g.to_dict() for g in engine.get_all_goals() if g.status == "completed"]
        if items:
            top = items[0]
            msg = (f"活跃目标 {len(items)} 个：{top['dimension']} "
                   f"{top['current_score']}/{top['target_score']}（{top['progress_pct']}%）")
        elif completed:
            msg = f"暂无活跃目标，已完成 {len(completed)} 个（可用 goal_set suggest=true 推荐新目标）"
        else:
            msg = "尚无目标（goal_set suggest=true 可按短板自动推荐）"
        return {"skill_id": skill_id, "active": items,
                "completed_count": len(completed), "message": msg}

    def _goal_update(a: dict[str, Any]) -> Any:
        """更新目标字段（target_score/status）"""
        from ...systems.active.goal_engine import ActiveGoalEngine

        skill_id = a.get("skill_id", "zenskill-core")
        engine = ActiveGoalEngine(skill_id)
        goal_id = a["goal_id"]
        if a.get("target_score") is None and a.get("status") is None:
            return {"ok": False, "goal_id": goal_id,
                    "message": "未提供要更新的字段（可选 target_score/status）"}
        try:
            goal = engine.update_goal(
                goal_id,
                target_score=(int(a["target_score"])
                              if a.get("target_score") is not None else None),
                status=a.get("status"),
            )
        except ValueError as e:
            return {"ok": False, "goal_id": goal_id, "message": str(e)}
        if goal is None:
            return {"ok": False, "goal_id": goal_id,
                    "message": f"未找到目标 {goal_id}"}
        return {
            "ok": True,
            "goal_id": goal_id,
            "goal": goal.to_dict(),
            "message": (f"目标 {goal_id} 已更新"
                        f"（{goal.dimension} → {goal.target_score} 分，状态 {goal.status}）"),
        }

    def _goal_delete(a: dict[str, Any]) -> Any:
        """删除目标（JSONL 物理删除）"""
        from ...systems.active.goal_engine import ActiveGoalEngine

        skill_id = a.get("skill_id", "zenskill-core")
        engine = ActiveGoalEngine(skill_id)
        goal_id = a["goal_id"]
        ok = engine.delete_goal(goal_id)
        return {
            "ok": ok,
            "goal_id": goal_id,
            "message": f"目标 {goal_id} 已删除" if ok
                       else f"未找到目标 {goal_id}",
        }

    def _task_progressions(a: dict[str, Any]) -> Any:
        """任务推进建议（层 3：TaskProgressionEngine 规则扫描 + 缓存）"""
        from ...core.progression_governor import ProgressionGovernor
        from ...systems.gtd.progression import TaskProgressionEngine
        try:
            limit = int(a.get("limit") or 5)
        except (TypeError, ValueError):
            limit = 5
        if limit <= 0:
            limit = 5
        result = TaskProgressionEngine().generate_progressions(limit=limit)
        # 层 4 治理: 本次返回视为一次推送，按 trigger_type 记入频控计数
        # （下次调用经 can_push 过滤: 每日上限 / 同类 24h 冷却 / quiet 静默）
        try:
            governor = ProgressionGovernor()
            for p in result.get("progressions") or []:
                governor.record_push(str(p.get("trigger_type") or "state"))
        except Exception:
            pass
        return result

    def _progression_feedback(a: dict[str, Any]) -> Any:
        """推进建议反馈（层 4：三态 accepted/rejected/dismissed 落 JSONL）"""
        from ...core.progression_governor import ProgressionGovernor
        trigger = str(a.get("trigger") or "").strip()
        action = str(a.get("action") or "").strip()
        if not trigger or not action:
            raise ValueError("progression_feedback 需要 trigger 与 action 参数")
        ProgressionGovernor().record_feedback(trigger, action)
        return {"ok": True, "trigger": trigger, "action": action,
                "message": "反馈已记录"}

    def _progression_mode(a: dict[str, Any]) -> Any:
        """主动度分级（层 4）：无 mode 查询，有 mode 设置（active/quiet/ritual_only）"""
        from ...core.progression_governor import ProgressionGovernor
        governor = ProgressionGovernor()
        mode = str(a.get("mode") or "").strip()
        if mode:
            governor.set_mode(mode)
            return {"ok": True, "mode": governor.get_mode(),
                    "message": f"主动度已切换为 {mode}"}
        mode = governor.get_mode()
        return {"mode": mode, "message": f"当前主动度: {mode}"}

    def _proactive_insight(a: dict[str, Any]) -> Any:
        """获取主动洞察（先检测生成，再按类型筛选）"""
        from ...systems.active.proactive_insight import ProactiveInsightEngine
        engine = ProactiveInsightEngine()
        # 洞察是懒生成：先跑检测（幂等，去重由引擎内部保证），再读取
        try:
            engine.check_and_generate_insights()
        except Exception:
            pass
        wanted = a.get("type", "all")
        insights = engine.get_insights_by_type(wanted) if wanted != "all" else engine.get_all_insights(limit=10)
        return {
            "count": len(insights),
            "items": [
                {"type": getattr(i, "insight_type", getattr(i, "type", "info")),
                 "title": getattr(i, "title", ""),
                 "content": i.content[:200],
                 "level": getattr(i, "level", "low")}
                for i in insights[:10]
            ],
            "message": f"找到 {len(insights)} 条洞察",
        }

    def _context_guide(a: dict[str, Any]) -> Any:
        """获取当前上下文指南（时间感知问候 + 能量/任务建议）"""
        import time as _time
        from ...systems.active.context_guide import ContextGuideEngine
        from ...systems.gtd.energy import EnergyEngine
        from ...systems.gtd.inbox import InboxEngine

        hour = _time.localtime().tm_hour
        if 5 <= hour < 12:
            greeting, period = "早上好", "morning"
        elif 12 <= hour < 14:
            greeting, period = "中午好", "noon"
        elif 14 <= hour < 18:
            greeting, period = "下午好", "afternoon"
        elif 18 <= hour < 23:
            greeting, period = "晚上好", "evening"
        else:
            greeting, period = "夜深了", "night"

        engine = ContextGuideEngine()
        analysis = engine.analyze(lookback_hours=24)
        energy = EnergyEngine().status()
        inbox_count = InboxEngine().count()

        return {
            "greeting": greeting,
            "period": period,
            "hour": hour,
            "energy": {"level": energy.get("level"), "pct": energy.get("pct")},
            "inbox_pending": inbox_count,
            "suggestions": analysis.get("suggestions", []),
            "context": analysis.get("context", {}),
        }

    def _companion_summary(a: dict[str, Any]) -> Any:
        """陪伴感摘要：一句话状态 + 能量 + 待办 + 建议（供 GUI 顶部展示）"""
        import time as _time
        from ...systems.gtd.energy import EnergyEngine
        from ...systems.gtd.action import ActionEngine
        from ...systems.gtd.inbox import InboxEngine

        hour = _time.localtime().tm_hour
        energy = EnergyEngine().status()
        inbox = InboxEngine().count()
        actions = ActionEngine().list(status="pending", limit=100)
        due_today = [a for a in actions if a.due_date and a.due_date[:10] == _time.strftime("%Y-%m-%d")]
        overdue = [a for a in actions if a.due_date and a.due_date[:10] < _time.strftime("%Y-%m-%d")]

        level = energy.get("level", "medium")
        if level == "critical":
            mood = "需要休息一下"
        elif level == "low":
            mood = "适合做些轻松的事"
        elif level == "medium":
            mood = "状态不错"
        else:
            mood = "精力充沛，适合挑战高难度"

        parts = [mood]
        if overdue:
            parts.append(f"{len(overdue)} 个行动已逾期")
        elif due_today:
            parts.append(f"今天有 {len(due_today)} 个待办到期")
        elif inbox > 0:
            parts.append(f"收件箱有 {inbox} 条待处理")

        # P4.2 多源化：时间感知问候 + proactive_insight 顶级洞察 + 微反馈
        if 5 <= hour < 12:
            greeting = "早上好"
        elif 12 <= hour < 14:
            greeting = "中午好"
        elif 14 <= hour < 18:
            greeting = "下午好"
        elif 18 <= hour < 23:
            greeting = "晚上好"
        else:
            greeting = "夜深了"

        top_insight = None
        try:
            from ...systems.active.proactive_insight import ProactiveInsightEngine
            engine = ProactiveInsightEngine(skill_id="zenskill-core")
            # WP-A：先懒生成（幂等，同类型 unread 去重由引擎保证）——
            # 否则无人调过 proactive_insight 时 companion 永远拿不到洞察
            try:
                engine.check_and_generate_insights()
            except Exception:
                pass
            insights = engine.get_unread_insights()
            top_insights = [
                {
                    "type": getattr(i, "insight_type", getattr(i, "type", "info")),
                    "title": getattr(i, "title", ""),
                    "content": str(getattr(i, "content", ""))[:160],
                }
                for i in insights[:3]
            ]
            if top_insights:
                parts.append(f"洞察：{top_insights[0]['title']}")
        except Exception:
            pass

        one_line = ""
        try:
            from ...systems.active.instant_feedback import InstantFeedbackEngine
            one_line = InstantFeedbackEngine("zenskill-core").generate_one_line()
            if one_line:
                parts.append(one_line)
        except Exception:
            pass

        # #5 Companion 深度：会话主题感知
        recent_topics = []
        try:
            from ...core.session_context import get_session_topic_context
            topic_ctx = get_session_topic_context("zenskill-core")
            recent_topics = topic_ctx.get("recent_topics", [])
            if recent_topics:
                topic = recent_topics[0]
                parts.append(f"刚才在聊：{topic[:40]}")
        except Exception:
            pass

        # #5 Companion 深度：用户画像差异化
        try:
            from ...core.session_context import get_user_profile_context
            profile = get_user_profile_context()
            user_level = profile.get("level", "NOVICE")
            usage = profile.get("usage_count", 0)
            if user_level == "NOVICE" and usage < 10 and len(actions) > 0:
                parts.append("今天试试用 action_add 添加一个今日目标")
            elif user_level in ("EXPERT", "MASTER") and len(actions) == 0:
                parts.append("可以用 learning_path 查看进阶路线")
        except Exception:
            pass

        # #5 Companion 深度：时段差异化建议
        if 22 <= hour or hour < 6:
            if level in ("low", "critical"):
                parts.append("建议休息——明日能量会自动恢复")
            else:
                parts.append("夜深了，还有精力的话可以处理 inbox")
        elif 12 <= hour < 14 and len(actions) > 5:
            parts.append("午休前花 5 分钟清一下收件箱")
        elif 18 <= hour < 20 and overdue == 0 and pending == 0:
            parts.append("今天全部完成，做得很棒")

        return {
            "mood": f"{greeting}——" + "；".join(parts) + "。",
            "greeting": greeting,
            "recent_topics": recent_topics,
            "top_insight": top_insights[0] if top_insights else None,
            "top_insights": top_insights,
            "micro_feedback": one_line,
            "energy": {"level": level, "pct": energy.get("pct"),
                       "current": energy.get("current_energy"), "max": energy.get("max_energy")},
            "inbox_pending": inbox,
            "pending_actions": len(actions),
            "due_today": len(due_today),
            "overdue": len(overdue),
        }

    def _level_ceremony(a: dict[str, Any]) -> Any:
        """境界突破仪式（latest=最近一次 / list=历史 / celebrate=即时祝贺）"""
        from ...systems.visualization.level_up_ceremony import LevelUpCeremony
        skill_id = a.get("skill_id", "zenskill-core")
        cer = LevelUpCeremony(skill_id)
        action = a.get("action", "latest")

        if action == "list":
            items = cer.list_ceremonies(limit=int(a.get("limit") or 10))
            return {"action": "list", "ceremonies": items,
                    "message": f"共 {len(items)} 次境界突破记录"}

        if action == "celebrate":
            frm = (a.get("from_level") or "").upper()
            to = (a.get("to_level") or "").upper()
            if not frm or not to:
                return {"success": False,
                        "error": "celebrate 需要 from_level/to_level（如 NOVICE→APPRENTICE）"}
            class _Lvl:
                def __init__(self, name: str):
                    self.name = name
            text = cer.generate_quick_celebration(_Lvl(frm), _Lvl(to))
            return {"action": "celebrate", "text": text, "message": text}

        latest = cer.get_latest_ceremony()
        if not latest:
            return {"action": "latest", "text": "",
                    "message": "尚无境界突破仪式记录（升级时自动生成）"}
        return {"action": "latest", "text": latest, "message": "最近一次境界突破仪式"}

    def _instant_feedback(a: dict[str, Any]) -> Any:
        """微反馈/连击（本会话节奏感知，适合 Hook 或间隙提醒）"""
        from ...systems.active.instant_feedback import InstantFeedbackEngine
        skill_id = a.get("skill_id", "zenskill-core")
        eng = InstantFeedbackEngine(skill_id)
        items = eng.generate()
        one_line = eng.generate_one_line()
        return {"feedback": items, "one_line": one_line,
                "message": one_line or "节奏平稳，继续保持"}

    def _learning_path(a: dict[str, Any]) -> Any:
        """生成学习路径（真引擎：SkillSearchEngine.path，按难度排序 + 已有技能前置）"""
        from ...skills.search_engine import SkillSearchEngine
        engine = SkillSearchEngine()
        target = a.get("target_skill") or a.get("target_goal") or ""
        if not target.strip():
            return {"success": False, "error": "需要 target_skill（目标描述）"}

        owned = a.get("owned_skills")
        if owned is None:
            owned = []
            try:
                from ...core.paths import get_user_data_dir
                states = get_user_data_dir() / "states"
                if states.is_dir():
                    owned = [f.stem for f in sorted(states.glob("*.json"))
                             if not f.name.endswith(".history.jsonl")]
            except Exception:
                pass

        result = engine.path(
            target_goal=target,
            owned_skills=list(owned),
            top_k=int(a.get("top_k") or 5),
        )
        steps = result.get("steps", [])
        if not steps:
            msg = f"未找到与「{target}」相关技能（索引可能为空，检查 installed_skills）"
        else:
            head = steps[0]
            msg = (f"路径共 {len(steps)} 步、约 {result.get('estimated_total_interactions', 0)} 次交互，"
                   f"首步：{head['name']}（{head['difficulty']}）")
        return {"target": target, "owned_skills": list(owned),
                "steps": steps,
                "estimated_total_interactions": result.get("estimated_total_interactions", 0),
                "message": msg}

    # 注册第一梯队工具
    registry.register("energy_level", "获取当前能量等级", _energy_level)
    registry.register(
        "action_add", "添加 GTD 下一步行动", _action_add,
        {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "行动标题"},
                "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"],
                             "description": "优先级 P0-P3（兼容 high/medium/low，自动归一化）"},
                "energy_required": {"type": "integer", "enum": [1, 3, 5, 8, 10],
                                    "description": "所需能量（兼容 easy/medium/hard/extreme，自动映射数字）"},
                "project_id": {"type": "string", "description": "关联项目 ID"},
                "contexts": {"type": "string", "description": "上下文标签"},
                "due_date": {"type": "string", "description": "截止日期 YYYY-MM-DD"},
                "skill_id": {"type": "string", "description": "关联技能 ID（完成时记录成长）"},
                "repeat_rule": {"type": "string", "description": "重复规则：daily/weekly/monthly（完成时自动生成下一实例）"},
            },
            "required": ["title"],
        },
    )
    registry.register("action_list", "列出待办行动", _action_list,
        {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "状态过滤：pending/completed/all"},
                "project_id": {"type": "string", "description": "按项目过滤"},
                "priority": {"type": "string", "description": "按优先级过滤"},
                "due_today": {"type": "boolean", "description": "只显示今天到期"},
                "limit": {"type": "integer", "description": "返回数量，默认 20"},
            },
        },
    )
    registry.register("action_done", "完成 GTD 行动（触发成长记录与重复任务再生）", _action_done,
        {
            "type": "object",
            "properties": {
                "action_id": {"type": "string", "description": "行动 ID"},
                "energy_invested": {"type": "integer", "description": "实际投入能量，默认取行动所需能量"},
            },
            "required": ["action_id"],
        },
    )
    registry.register("action_mark_next", "标记行动为 next（准备执行）", _action_mark_next,
        {
            "type": "object",
            "properties": {"action_id": {"type": "string", "description": "行动 ID"}},
            "required": ["action_id"],
        },
    )
    registry.register("action_update", "更新行动字段", _action_update,
        {
            "type": "object",
            "properties": {
                "action_id": {"type": "string", "description": "行动 ID"},
                "title": {"type": "string", "description": "新标题"},
                "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"],
                             "description": "优先级 P0-P3（兼容 high/medium/low，自动归一化）"},
                "due_date": {"type": "string", "description": "截止日期 YYYY-MM-DD"},
                "contexts": {"type": "string", "description": "上下文标签"},
                "skill_id": {"type": "string", "description": "关联技能 ID"},
                "repeat_rule": {"type": "string", "description": "重复规则 daily/weekly/monthly"},
            },
            "required": ["action_id"],
        },
    )
    registry.register("action_delete", "删除行动", _action_delete,
        {
            "type": "object",
            "properties": {"action_id": {"type": "string", "description": "行动 ID"}},
            "required": ["action_id"],
        },
    )
    registry.register(
        "project_add", "创建 GTD 项目（多步目标）", _project_add,
        {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "项目名称"},
                "outcome": {"type": "string", "description": "预期成果描述（可选）"},
                "skill_id": {"type": "string", "description": "关联技能 ID（完成时记录成长，可选）"},
            },
            "required": ["name"],
        },
    )
    registry.register("project_list", "列出项目及其进度", _project_list,
        {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "状态过滤：active/completed/all"},
            },
        },
    )
    registry.register("project_done", "完成项目", _project_done,
        {
            "type": "object",
            "properties": {"project_id": {"type": "string", "description": "项目 ID"}},
            "required": ["project_id"],
        },
    )
    registry.register("project_update", "更新项目字段（name/outcome/notes/status）", _project_update,
        {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目 ID"},
                "name": {"type": "string", "description": "项目名称"},
                "outcome": {"type": "string", "description": "预期成果描述"},
                "notes": {"type": "string", "description": "备注"},
                "status": {"type": "string",
                           "enum": ["active", "someday", "done", "archived"],
                           "description": "项目状态"},
            },
            "required": ["project_id"],
        },
    )
    registry.register("incubating_list", "列出孵化池条目（未成熟想法）", _incubating_list,
        {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "状态过滤：active/mature/all，默认 active"},
                "channel": {"type": "string", "description": "通道过滤：reflect/consolidate/insight/purify"},
                "limit": {"type": "integer", "description": "返回数量，默认 20"},
            },
        },
    )
    registry.register("incubating_promote", "孵化成熟条目 → 提升为 Action", _incubating_promote,
        {
            "type": "object",
            "properties": {"item_id": {"type": "string", "description": "孵化条目 ID"}},
            "required": ["item_id"],
        },
    )
    registry.register("habit_check", "记录习惯打卡", _habit_check,
        {
            "type": "object",
            "properties": {"habit_id": {"type": "string", "description": "习惯 ID"}},
            "required": ["habit_id"],
        },
    )
    registry.register("habit_list", "列出习惯及其完成率", _habit_list)
    registry.register("habit_analyze", "习惯分析：每日打卡日历 + streak/完成率/风险", _habit_analyze,
        {
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "分析天数，默认 7"}},
        },
    )
    registry.register("habit_set", "创建/更新习惯定义（habit_id 缺省由 title 归一化派生，重复保存即更新）", _habit_set,
        {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "习惯名称"},
                "habit_id": {"type": "string", "description": "习惯 ID（可选，缺省由 title 派生）"},
                "skill_id": {"type": "string", "description": "关联技能 ID（可选）"},
                "target_count": {"type": "integer", "description": "每日目标次数，默认 1"},
                "action_contains": {"type": "string", "description": "事件 action 匹配子串（可选）"},
            },
            "required": ["title"],
        },
    )
    registry.register("habit_delete", "删除习惯定义", _habit_delete,
        {
            "type": "object",
            "properties": {"habit_id": {"type": "string", "description": "习惯 ID"}},
            "required": ["habit_id"],
        },
    )
    registry.register("achievement_list", "列出已解锁成就", _achievement_list,
        {
            "type": "object",
            "properties": {"skill_id": {"type": "string", "description": "默认 zenskill-core"}},
        },
    )
    registry.register("goal_set", "设置技能成长目标（suggest=true 自动推荐短板目标）", _goal_set,
        {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string", "description": "技能 ID，默认 zenskill-core"},
                "dimension": {"type": "string", "description": "维度：proficiency/stability/satisfaction/responsiveness/memory/composite"},
                "target_score": {"type": "integer", "description": "目标分数 0-100（须高于当前分）"},
                "suggest": {"type": "boolean", "description": "true=引擎按短板自动推荐，不落设"},
                "n": {"type": "integer", "description": "suggest 模式推荐数量，默认 2"},
                "deadline_interactions": {"type": "integer", "description": "预计交互次数（可选，默认自动估算）"},
            },
        },
    )
    registry.register("goal_progress", "检查目标进度", _goal_progress,
        {
            "type": "object",
            "properties": {"skill_id": {"type": "string", "description": "技能 ID"}},
        },
    )
    registry.register("goal_update", "更新成长目标字段（target_score/status）", _goal_update,
        {
            "type": "object",
            "properties": {
                "goal_id": {"type": "string", "description": "目标 ID"},
                "target_score": {"type": "integer", "description": "新目标分数 0-100"},
                "status": {"type": "string",
                           "enum": ["active", "completed", "failed", "cancelled"],
                           "description": "目标状态"},
                "skill_id": {"type": "string", "description": "技能 ID，默认 zenskill-core"},
            },
            "required": ["goal_id"],
        },
    )
    registry.register("goal_delete", "删除成长目标（JSONL 物理删除）", _goal_delete,
        {
            "type": "object",
            "properties": {
                "goal_id": {"type": "string", "description": "目标 ID"},
                "skill_id": {"type": "string", "description": "技能 ID，默认 zenskill-core"},
            },
            "required": ["goal_id"],
        },
    )
    registry.register(
        "task_progressions",
        "任务推进建议：基于状态/阶段自动生成 top-N 推进提示词",
        _task_progressions,
        {"type": "object", "properties": {"limit": {"type": "integer", "description": "返回数量，默认 5"}}},
    )
    registry.register(
        "progression_feedback",
        "记录推进建议反馈：accepted（采纳）/ rejected（拒绝）/ dismissed（忽略）",
        _progression_feedback,
        {
            "type": "object",
            "properties": {
                "trigger": {"type": "string", "description": "触发器，如 overdue_action:act_xxx / morning_ritual"},
                "action": {"type": "string", "enum": ["accepted", "rejected", "dismissed"],
                           "description": "反馈动作"},
            },
            "required": ["trigger", "action"],
        },
    )
    registry.register(
        "progression_mode",
        "推进建议主动度：无 mode 查询当前档位，有 mode 设置（active/quiet/ritual_only）",
        _progression_mode,
        {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["active", "quiet", "ritual_only"],
                         "description": "省略时仅查询当前档位"},
            },
        },
    )
    registry.register("proactive_insight", "获取主动洞察", _proactive_insight,
        {
            "type": "object",
            "properties": {"type": {"type": "string", "description": "洞察类型过滤"}},
        },
    )
    registry.register("context_guide", "获取当前上下文指南", _context_guide)
    def _zenloop_bridge_run(a: dict[str, Any]) -> Any:
        """运行 GTD × ZenLoop 联动周期（reflect/consolidate/insight/purify）"""
        from ...systems.gtd.zenloop_bridge import GTDZenLoopBridge
        result = GTDZenLoopBridge().run_all_cycles()
        return {"ok": True, "cycles": result,
                "message": "ZenLoop 周期完成: " + "；".join(
                    f"{k}={json.dumps(v, ensure_ascii=False, default=str)[:60]}"
                    for k, v in result.items() if isinstance(v, dict) and v.get("message"))}

    def _zenloop_status(a: dict[str, Any]) -> Any:
        """孵化池概览（按通道分组）"""
        from ...systems.gtd.incubating import IncubatingEngine
        engine = IncubatingEngine()
        items = engine.list(status="active", limit=50)
        by_channel: dict[str, int] = {}
        for i in items:
            by_channel[i.channel] = by_channel.get(i.channel, 0) + 1
        return {"active": len(items), "by_channel": by_channel,
                "top": [{"id": i.id, "channel": i.channel,
                         "maturity": round(i.maturity, 2),
                         "concept": i.raw_concept[:60]} for i in items[:5]],
                "message": f"孵化池: {len(items)} 活跃"}

    registry.register("companion_summary", "陪伴感摘要：一句话状态 + 能量 + 待办 + 建议", _companion_summary)
    registry.register("zenloop_bridge_run", "运行 GTD × ZenLoop 联动周期（reflect/consolidate/insight/purify）", _zenloop_bridge_run)
    registry.register("zenloop_status", "孵化池概览（按通道分组）", _zenloop_status)
    registry.register("level_ceremony", "境界突破仪式：latest 最近仪式 / list 历史 / celebrate 即时祝贺", _level_ceremony,
        {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["latest", "list", "celebrate"],
                           "description": "默认 latest"},
                "skill_id": {"type": "string"},
                "from_level": {"type": "string", "description": "celebrate 模式：旧境界"},
                "to_level": {"type": "string", "description": "celebrate 模式：新境界"},
                "limit": {"type": "integer", "description": "list 模式条数，默认 10"},
            },
        },)
    registry.register("instant_feedback", "微反馈：会话连击/节奏/每日小成就（一句话）", _instant_feedback,
        {
            "type": "object",
            "properties": {"skill_id": {"type": "string"}},
        },)
    registry.register("learning_path", "生成学习路径（技能索引真检索，已有技能前置、按难度递增）", _learning_path,
        {
            "type": "object",
            "properties": {
                "owned_skills": {"type": "array", "items": {"type": "string"}, "description": "已有技能 ID（缺省自动扫描 states）"},
                "top_k": {"type": "integer", "description": "路径步骤上限，默认 5"},
                "target_skill": {"type": "string", "description": "目标技能"},
                "current_level": {"type": "string", "description": "当前水平，默认 NOVICE"},
            },
        },
    )

    def _share_card(a: dict[str, Any]) -> Any:
        """生成成长分享卡片（PNG 渲染降级 SVG；public=true 附免登录公开页）"""
        import base64 as _b64
        from pathlib import Path as _Path

        from ...share.card_data import GrowthCardData
        from ...share.public_page import make_card_id, render_card_svg, save_public_page
        from ...share.renderer import render_card_html, render_card_png

        card_data = GrowthCardData().get_card_data()
        card_id = make_card_id(card_data)
        result: dict[str, Any] = {"card_id": card_id, "format": a.get("format", "png")}

        image_base64 = ""
        shares_dir = _Path.home() / ".zenskill" / "shares"
        try:
            shares_dir.mkdir(parents=True, exist_ok=True)
            png_path = render_card_png(
                render_card_html(card_data), str(shares_dir / f"{card_id}.png"))
            if png_path:
                image_base64 = _b64.b64encode(_Path(png_path).read_bytes()).decode("ascii")
                result["png_path"] = png_path
                result["mime"] = "image/png"
        except Exception:
            pass
        if not image_base64:
            svg = render_card_svg(card_data)
            image_base64 = _b64.b64encode(svg.encode("utf-8")).decode("ascii")
            html_path = shares_dir / f"{card_id}.html"
            try:
                html_path.write_text(render_card_html(card_data), encoding="utf-8")
                result["html_path"] = str(html_path)
            except Exception:
                pass
            result["mime"] = "image/svg+xml"
        result["image_base64"] = image_base64
        result["level_name"] = card_data.get("level_name", "")
        result["date"] = card_data.get("date", "")

        if a.get("public"):
            try:
                result["public_page"] = save_public_page(card_id)
            except Exception as e:
                result["public_page_error"] = str(e)

        result["message"] = (
            f"成长卡片已生成（{result['mime']}，境界 {result['level_name']}）"
            + (f"，公开页: {result['public_page']}" if result.get("public_page") else ""))
        return result

    registry.register("share_card", "生成成长分享卡片（1080×1080 PNG，渲染降级 SVG），public=true 额外生成免登录公开页", _share_card,
        {
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": ["png", "html"],
                           "description": "卡片格式，默认 png（渲染失败自动降级 SVG/HTML）"},
                "public": {"type": "boolean",
                           "description": "true=同时生成免登录公开页 HTML 并返回路径"},
            },
        },
    )

    # ── skill_validate：校验所有技能 frontmatter v2 ──
    def _skill_validate(a: dict[str, Any]) -> Any:
        import re as _re
        from pathlib import Path
        skills_dir = Path.home() / ".agents" / "skills"
        domains = {"lark", "arkcli", "agentswarm", "dev", "data", "ai", "design", "ops", "life", "general"}
        types = {"execution", "analysis", "creation", "coordination", "knowledge", "general"}
        errors: list[str] = []
        total = 0
        for d in sorted(skills_dir.iterdir()):
            sf = d / "SKILL.md"
            if not d.is_dir() or d.name.startswith(".") or not sf.exists():
                continue
            total += 1
            slug = d.name
            try:
                content = sf.read_text(encoding="utf-8")
                m = _re.match(r"^---\s*\n(.*?)\n---", content, _re.DOTALL)
                if not m:
                    errors.append(f"{slug}: no frontmatter")
                    continue
                import yaml as _yaml
                raw = _yaml.safe_load(m.group(1)) or {}
                for field in ("name", "description", "category", "type"):
                    v = raw.get(field)
                    if not v or (isinstance(v, list) and not v):
                        errors.append(f"{slug}: missing {field}")
                if raw.get("category") not in domains:
                    errors.append(f"{slug}: bad category '{raw.get('category')}'")
                if raw.get("type") not in types:
                    errors.append(f"{slug}: bad type '{raw.get('type')}'")
                if isinstance(raw.get("description"), str) and _re.match(r"^\s*Use when", raw["description"], _re.I):
                    errors.append(f"{slug}: description still starts with 'Use when'")
            except Exception as exc:
                errors.append(f"{slug}: {exc}")
        return {"total": total, "errors": errors, "pass": len(errors) == 0}

    registry.register(
        "skill_validate",
        "校验所有技能 SKILL.md frontmatter v2（name/description/category/type 必填，闭集校验）",
        _skill_validate,
        {"type": "object", "properties": {}},
    )

    # ============================================================
    # Collaboration 子系统：跨技能洞察 / 迁移模式 / 仪表盘
    # ============================================================

    def _collaboration_insights(a: dict[str, Any]) -> Any:
        """跨技能洞察：全量扫描技能图谱，发现瓶颈/模式/协同/不均衡"""
        from ...systems.collaboration.cross_insight import CrossSkillInsightEngine
        from dataclasses import asdict

        engine = CrossSkillInsightEngine()
        insights = engine.generate_cross_insights()
        return {
            "count": len(insights),
            "insights": [
                {
                    "insight_id": i.insight_id,
                    "type": i.type,
                    "severity": i.severity,
                    "title": i.title,
                    "description": i.content,
                    "affected_skills": i.affected_skills,
                    "importance": i.severity,
                }
                for i in insights
            ],
            "message": f"发现 {len(insights)} 条跨技能洞察" if insights else "暂无跨技能洞察",
        }

    def _collaboration_transfer(a: dict[str, Any]) -> Any:
        """跨技能迁移模式：从高表现技能中提取成功模式推荐给低表现技能"""
        from ...systems.collaboration.skill_transfer import SkillTransferEngine

        engine = SkillTransferEngine()
        patterns = engine.find_transferable_patterns()
        return {
            "count": len(patterns),
            "patterns": patterns,
            "message": f"发现 {len(patterns)} 个可迁移模式" if patterns else "暂无可迁移模式",
        }

    def _collaboration_dashboard(a: dict[str, Any]) -> Any:
        """协作仪表盘：技能生态系统全景（健康度/热力图/网络/协同/洞察）"""
        import re as _re
        from ...systems.collaboration.dashboard import SkillEcosystemDashboard

        dashboard = SkillEcosystemDashboard()
        text = dashboard.generate_dashboard()

        # 尝试解析 Markdown 为结构化数据
        try:
            sections: dict[str, Any] = {}
            # 按 ═══ 分割主要区块
            blocks = _re.split(r"═{2,}", text)
            for block in blocks:
                block = block.strip()
                if not block:
                    continue
                # 提取每行内容
                lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
                if lines:
                    title = lines[0]
                    sections[title] = lines[1:]
            if sections:
                return {"sections": sections, "raw_text": text,
                        "message": "协作仪表盘已生成"}
        except Exception:
            pass

        # 解析失败降级：返回原始文本
        return {"message": text}

    registry.register(
        "collaboration_insights",
        "跨技能洞察：全量扫描技能图谱，发现瓶颈/模式/协同/不均衡",
        _collaboration_insights,
        {"type": "object", "properties": {}},
    )
    registry.register(
        "collaboration_transfer",
        "跨技能迁移模式：从高表现技能中提取成功模式推荐给低表现技能",
        _collaboration_transfer,
        {"type": "object", "properties": {}},
    )
    registry.register(
        "collaboration_dashboard",
        "协作仪表盘：技能生态系统全景（健康度/热力图/网络/协同/洞察）",
        _collaboration_dashboard,
        {"type": "object", "properties": {}},
    )

    # 自定义工具桥接（~/.zenskill/tools/*.py → MCP registry）
    _register_custom_tools(registry)

    return registry


def _register_custom_tools(registry: "ServerToolRegistry") -> None:
    """加载 ~/.zenskill/tools/*.py 自定义工具并注册进 MCP registry。

    每个工具 spec 额外标记 _custom: True，便于 reload_custom_tools 识别。
    """
    try:
        from ...runtime.agent.custom_tools import load_custom_tools
        custom = load_custom_tools()
    except Exception:
        return

    for tool in custom:
        def _make_handler(t):
            def handler(a: dict[str, Any]) -> Any:
                """同步 handler — MCP server 是同步的，在独立线程中运行异步 run()。"""
                import asyncio as _aio
                import concurrent.futures

                def _runner():
                    new_loop = _aio.new_event_loop()
                    _aio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(t.run("mcp-custom", a))
                    finally:
                        new_loop.close()

                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        result = pool.submit(_runner).result(timeout=30)
                except Exception as e:
                    return {"success": False, "error": f"{type(e).__name__}: {e}"}
                if getattr(result, "is_error", False):
                    text = result.content[0].text if result.content else "error"
                    return {"success": False, "error": text}
                text = result.content[0].text if result.content else ""
                try:
                    return json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    return {"success": True, "result": text}
            return handler

        spec = {
            "name": tool.name,
            "description": (tool.description or "")[:200],
            "inputSchema": tool.parameters or {"type": "object", "properties": {}},
            "_custom": True,
        }
        registry.register(
            tool.name,
            spec["description"],
            _make_handler(tool),
            spec["inputSchema"],
        )
        # 标记为自定义工具（reload_custom_tools 识别用）
        if tool.name in registry._tools:
            registry._tools[tool.name]._custom = True
