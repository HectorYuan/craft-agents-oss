"""Server Mode 轻量自动化执行器（W1.2）。

职责: SchedulerTick(每分钟) + ZenSkillChanged(事件) → 规则匹配 → 条件评估 → 动作执行
幂等: ExecutionEntry 去重 + 同规则冷却(默认 24h)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("zenskill.automation_runner")

TICK_INTERVAL = 60  # seconds
COOLDOWN_DEFAULT = 24 * 3600  # 24h
MAX_HISTORY = 500


def _hex6(t: float) -> str:
    """毫秒时间戳取低 24bit 的 6 位十六进制 id（历史条目短 id）。"""
    return format(int(t * 1000) & 0xFFFFFF, "06x")


class AutomationRunner:
    def __init__(self, ws_server: Any) -> None:
        self._ws = ws_server
        self._queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        self._history: list[dict] = []
        self._cooldowns: dict[str, float] = {}  # key → last_success_ts
        self._running = False

    async def start(self) -> None:
        self._running = True
        asyncio.create_task(self._scheduler_loop())
        asyncio.create_task(self._drain_loop())

    async def stop(self) -> None:
        self._running = False

    # ── 事件入口 ─────────────────────────────────────────────────────

    def on_zenskill_changed(self, payload: dict) -> None:
        """写工具后同步调用（入队不阻塞）。"""
        if self._running:
            self._queue.put_nowait(("ZenSkillChanged", payload))

    def on_gtd_event(self, payload) -> None:
        """S2：GTD 实体变更入队（matcher 评估时 payload dict 序列化后供正则匹配）。"""
        if self._running:
            # payload 是 GtdObserverPayload 或 dict；统一 to_dict 化（兼容测试 fixture 传 dict）
            data = payload.to_dict() if hasattr(payload, "to_dict") else dict(payload)
            self._queue.put_nowait(("GtdEntityChanged", data))

    # gtd-action 回流：ActionsPanel 派发文案约定（执行行动: X。完成后用
    # action_done 标记 <id>。）——会话完成时扫首条用户消息自动 done。
    # 双模式（Desktop/Server）通吃：两端会话都经引擎 SessionManager。
    _ACTION_DONE_PAT = re.compile(
        r"action_done\s*(?:标记|mark)?\s*(act_[0-9a-zA-Z_]+)")

    def on_session_completed(self, session_id: str, messages: list[dict],
                             labels: list[str] | None = None) -> None:
        """会话正常结束回流：①内建 gtd-action 自动 done；②投递
        SessionStatusChange 事件（payload 整体 JSON 序列化后供 matcher 正则）。
        入队不阻塞，与既有事件同一条 _drain_loop。"""
        labels = list(labels or [])
        first_user = next(
            (str(m.get("content", "")) for m in messages
             if m.get("role") == "user"), "")
        m = self._ACTION_DONE_PAT.search(first_user)
        action_id = m.group(1) if m else ""
        if action_id:
            try:
                from ..systems.gtd.action import ActionEngine
                ok = ActionEngine().done(action_id)
                logger.info("gtd-action 回流: session=%s action=%s done=%s",
                            session_id, action_id, ok)
            except Exception as exc:
                logger.warning("gtd-action 回流失败 action=%s: %s",
                               action_id, exc)
        if self._running:
            self._queue.put_nowait(("SessionStatusChange", {
                "sessionId": session_id,
                "status": "done",
                "labels": labels,
                "firstMessage": first_user[:200],
                "actionId": action_id,
            }))

    # ── 后台循环 ─────────────────────────────────────────────────────

    async def _scheduler_loop(self) -> None:
        while self._running:
            try:
                await self._scheduler_tick()
            except Exception as exc:
                logger.warning("scheduler_tick error: %s", exc)
            await asyncio.sleep(TICK_INTERVAL)

    async def _drain_loop(self) -> None:
        while self._running:
            try:
                event, payload = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._evaluate(event, payload)
            except asyncio.TimeoutError:
                pass
            except Exception as exc:
                logger.warning("drain error: %s", exc)

    async def _scheduler_tick(self) -> None:
        """每分钟: cron 规则 + progression time 规则。"""
        store = self._ws._automation_store
        if store is None:
            return
        # 1. 用户自定义 cron 规则
        for matcher in store.get_matchers("SchedulerTick"):
            cron = matcher.get("cron")
            if not cron:
                continue
            if self._cron_matches(cron, matcher.get("timezone")):
                if not self._in_cooldown(matcher.get("id", "")):
                    await self._execute_matcher(matcher, "SchedulerTick", {})
        # 2. progression time-based 规则（引擎内）
        try:
            from ..systems.gtd.progression import TaskProgressionEngine
            engine = TaskProgressionEngine()
            raw = engine.generate_progressions()
            for p in raw.get("progressions", []):
                # p is dict (from to_dict())
                if p.get("trigger_type") != "time":
                    continue
                key = f"prog:{p['trigger']}"
                if self._in_cooldown(key):
                    continue
                # 直接执行 prompt
                await self._fire_prompt_action(
                    {"id": key, "name": p["suggestion"][:40], "labels": ["zenskill-trigger::time"]},
                    {"type": "prompt", "prompt": p["prompt"]},
                    f"ZenSkillChanged:{p.entity_type}",
                    {},
                )
                self._cooldowns[key] = time.time()
        except Exception as exc:
            logger.debug("progression time tick: %s", exc)

    # ── 事件评估 ─────────────────────────────────────────────────────

    async def _evaluate(self, event: str, payload: dict) -> None:
        store = self._ws._automation_store
        if store is None:
            return
        for matcher in store.get_matchers(event):
            if self._in_cooldown(matcher.get("id", "")):
                continue
            # 正则匹配（非 SchedulerTick）
            pat = matcher.get("matcher")
            if pat and event != "SchedulerTick":
                data_str = json.dumps(payload, ensure_ascii=False)
                if not re.search(pat, data_str):
                    continue
            # 条件评估
            if not self._evaluate_conditions(matcher.get("conditions", []), payload):
                continue
            await self._execute_matcher(matcher, event, payload)

    def _evaluate_conditions(self, conditions: list[dict], payload: dict) -> bool:
        if not conditions:
            return True
        for c in conditions:
            kind = c.get("condition", "")
            if kind == "time":
                from datetime import datetime
                now = datetime.now()
                if c.get("before") and now.strftime("%H:%M") > c["before"]:
                    return False
                if c.get("after") and now.strftime("%H:%M") < c["after"]:
                    return False
            elif kind == "state":
                # 简化：field 路径取 payload 值 vs value/contains
                val = self._resolve_field(payload, c.get("field", ""))
                if c.get("value") is not None and str(val) != str(c["value"]):
                    return False
                if c.get("contains") and c["contains"] not in str(val):
                    return False
        return True

    @staticmethod
    def _resolve_field(obj: dict, dotpath: str) -> Any:
        cur = obj
        for part in dotpath.split("."):
            if isinstance(cur, dict):
                cur = cur.get(part)
            else:
                return None
        return cur

    @staticmethod
    def _cron_matches(expr: str, tz: str | None) -> bool:
        """极简 5 字段 cron 检查（minute/hour/dom/month/dow）；不支持通配粒度 <1min。"""
        from datetime import datetime
        now = datetime.now()
        parts = expr.strip().split()
        if len(parts) != 5:
            return False
        fields = [now.minute, now.hour, now.day, now.month, now.isoweekday() % 7]
        for p, f in zip(parts, fields):
            if p == "*":
                continue
            if "-" in p:
                lo, hi = p.split("-", 1)
                if not (int(lo) <= f <= int(hi)):
                    return False
            elif "," in p:
                if f not in [int(x) for x in p.split(",")]:
                    return False
            else:
                if f != int(p):
                    return False
        return True

    def _in_cooldown(self, key: str) -> bool:
        last = self._cooldowns.get(key, 0)
        return (time.time() - last) < COOLDOWN_DEFAULT

    # ── 动作执行 ─────────────────────────────────────────────────────

    async def _execute_matcher(self, matcher: dict, event: str, payload: dict) -> None:
        for action in matcher.get("actions", []):
            atype = action.get("type", "")
            if atype == "prompt":
                await self._fire_prompt_action(matcher, action, event, payload)
            elif atype == "script":
                await self._fire_script_action(matcher, action, event, payload)
            elif atype == "webhook":
                await self._fire_webhook_action(matcher, action, event, payload)
        self._cooldowns[matcher.get("id", "")] = time.time()

    async def _fire_prompt_action(self, matcher: dict, action: dict, event: str, payload: dict) -> dict:
        """prompt → create_session（带 model/llmConnection/thinkingLevel）+ 真发送。

        修复记录（C1）：原实现把 options dict 当 workspace_id 传入 create_session，
        会话不可见于任何 workspace 且 prompt 从未发送；action 的 model/
        llmConnection/thinkingLevel 字段也被忽略。
        """
        prompt_text = action.get("prompt", "")
        if not prompt_text:
            self._record(matcher, event, "error", 0, error="prompt 内容为空")
            return {"ok": False, "error": "prompt 内容为空"}
        t0 = time.time()
        try:
            sm = self._ws.session_manager
            workspace_id = sm.default_workspace_id()
            if not workspace_id:
                self._record(matcher, event, "error", 0, error="无可用工作区")
                return {"ok": False, "error": "无可用工作区"}
            session = sm.create_session(
                workspace_id,
                name=matcher.get("name", "Automation"),
                model=action.get("model"),
                default_llm_connection=action.get("llmConnection"),
                thinking_level=action.get("thinkingLevel"),
            )
            session_id = session.get("id", "")

            def _capture_push(channel: str, args) -> None:
                # agent 失败以 error 事件形式经 push_event 冒出（_run_agent
                # 内部 catch 后不重抛），在此补记进自动化历史
                try:
                    events = args if isinstance(args, list) else [args]
                    for ev in events:
                        if isinstance(ev, dict) and ev.get("type") == "error":
                            self._record(matcher, event, "error",
                                         time.time() - t0,
                                         error=str(ev.get("error"))[:200],
                                         session_id=session_id)
                except Exception:
                    pass

            # 真发送：agent loop 由 send_message 起后台任务
            accepted = await sm.send_message(
                session_id, prompt_text, _capture_push, {})
            if not accepted:
                self._record(matcher, event, "error", time.time() - t0,
                             error="消息发送被拒绝", session_id=session_id)
                return {"ok": False, "error": "消息发送被拒绝", "session_id": session_id}
            self._record(matcher, event, "success", time.time() - t0,
                         summary=f"prompt → session {session_id[:8]}",
                         session_id=session_id)
            return {"ok": True, "session_id": session_id}
        except Exception as exc:
            self._record(matcher, event, "error", time.time() - t0, error=str(exc))
            logger.warning("prompt action failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def _fire_script_action(self, matcher: dict, action: dict, event: str, payload: dict) -> None:
        script = action.get("script", "")
        workspace_root = str(self._ws.workspace_manager.get_workspace_path("default") or ".")
        script_path = Path(workspace_root) / script
        # 路径穿越防护
        try:
            resolved = script_path.resolve()
            if not str(resolved).startswith(str(Path(workspace_root).resolve())):
                self._record(matcher, event, "blocked", 0, error="path traversal")
                return
        except Exception:
            pass
        if not script_path.exists():
            self._record(matcher, event, "error", 0, error=f"script not found: {script}")
            return
        runtime = action.get("runtime", "python3")
        if runtime in ("python3", "python"):
            # 脚本需 import zenskill 包——裸 "python3" 落到系统解释器时
            # 包不可见会静默 ImportError（exit 0 空输出），必须跟随宿主解释器
            runtime = sys.executable
        timeout = action.get("timeoutMs", 30000) / 1000
        env = os.environ.copy()
        env["CRAFT_WORKSPACE_ROOT"] = workspace_root
        env["ZENSKILL_EVENT_DATA"] = json.dumps(payload, ensure_ascii=False)
        try:
            t0 = time.time()
            proc = subprocess.run(
                [runtime, str(script_path)] + (action.get("args") or []),
                capture_output=True, text=True, timeout=timeout, env=env,
            )
            duration = time.time() - t0
            status = "success" if proc.returncode == 0 else "error"
            summary = proc.stdout[:500] if proc.stdout else proc.stderr[:200] if proc.stderr else ""
            self._record(matcher, event, status, duration, summary=summary)
        except subprocess.TimeoutExpired:
            self._record(matcher, event, "error", timeout, error="timeout")
        except Exception as exc:
            self._record(matcher, event, "error", 0, error=str(exc))

    async def _fire_webhook_action(self, matcher: dict, action: dict, event: str, payload: dict) -> None:
        url = action.get("url", "")
        if not url:
            return
        method = action.get("method", "POST")
        headers = action.get("headers", {})
        body = action.get("body") or payload
        body_bytes = json.dumps(body, ensure_ascii=False).encode()
        req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
        try:
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_body = resp.read()[:500].decode(errors="replace") if action.get("captureResponse") else ""
            self._record(matcher, event, "success", time.time() - t0, summary=resp_body)
        except Exception as exc:
            self._record(matcher, event, "error", 0, error=str(exc))

    # ── 历史 ─────────────────────────────────────────────────────────

    def _record(self, matcher: dict, event: str, status: str, duration: float,
                error: str = "", summary: str = "", session_id: str = "") -> None:
        entry = {
            "id": _hex6(time.time()),
            "automationId": matcher.get("id", ""),
            "event": event,
            "status": status,
            "duration": duration,
            "timestamp": int(time.time() * 1000),
            "error": error,
            "actionSummary": summary[:500],
            "sessionId": session_id,
        }
        self._history.append(entry)
        if len(self._history) > MAX_HISTORY:
            self._history = self._history[-MAX_HISTORY:]

    def get_history(self, limit: int = 50) -> list[dict]:
        return list(reversed(self._history[-limit:]))


# 模块级 re 导入（_evaluate 用）
import re  # noqa: E402
