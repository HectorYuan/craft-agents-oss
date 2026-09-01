"""collector 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

from ..cli_utils import output as cli_output
from ..cli_helpers import _register_collectors, _str_box_footer, _str_box_header, _str_section

def cmd_collector_list(args: argparse.Namespace) -> None:
    """列出所有采集器及状态"""
    from ..mirroring.collectors import collector_registry

    _register_collectors()
    collectors = collector_registry.list_all()
    cc = [c for c in collectors if c["name"].startswith("claude-")]
    zs = [c for c in collectors if c["name"].startswith("zenskill-")]
    ok_n = sum(1 for c in collectors if c["available"])
    fail_n = sum(1 for c in collectors if not c["available"])

    result = {
        "total_collectors": len(collectors),
        "available_count": ok_n,
        "unavailable_count": fail_n,
        "claude_collectors": [{"name": c["name"], "available": c["available"],
                               "description": c["description"]} for c in cc],
        "zenskill_collectors": [{"name": c["name"], "available": c["available"],
                                 "description": c["description"]} for c in zs],
    }

    def _text():
        lines = [_str_section("智能体生态采集层", "🕸️", phase="9C"),
                 _str_box_header("Claude Code 生态", "📦")]
        for c in cc:
            icon = "🟢" if c["available"] else "🔴"
            name = c["name"].replace("claude-", "")
            lines.append(f"  │  {icon} {name:20s} {c['description']}")
        lines.append(_str_box_footer())
        if zs:
            lines.append("")
            lines.append(_str_box_header("ZenSkill 内部", "🧘"))
            for c in zs:
                icon = "🟢" if c["available"] else "🔴"
                name = c["name"].replace("zenskill-", "")
                lines.append(f"  │  {icon} {name:20s} {c['description']}")
            lines.append(_str_box_footer())
        lines.append("")
        lines.append(f"  📊 共 {len(collectors)} 个采集器  |  🟢 {ok_n} 可用  |  🔴 {fail_n} 不可用")
        lines.append("  💡 zenskill collector run-all       # 一键全量采集 + 分析")
        lines.append("       zenskill collector run <name>    # 运行指定采集器")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_collector_run(args: argparse.Namespace) -> None:
    """运行指定采集器"""
    from ..cli_utils import parse_since
    from ..mirroring.collectors import collector_registry

    _register_collectors()
    name = args.name
    since = parse_since(getattr(args, 'since', None))
    incremental = since > 0
    label = f" (自 {args.since})" if incremental else ""

    try:
        results = collector_registry.run(name, incremental=incremental, since=since)
        if not results:
            cli_output({"ok": True, "collector_name": name, "event_count": 0}, args,
                       text=lambda: (
                           f"\n  🔍 采集结果: {name}{label}\n"
                           f"  {'═' * 62}\n\n"
                           f"  ⚠️  无数据或数据源不可用"
                       ))
            return

        result_data = {"ok": True, "collector_name": name, "event_count": len(results),
                       "events": results}

        def _text():
            lines = ["", f"  🔍 采集结果: {name}{label}",
                     f"  {'═' * 62}", ""]
            for event in results:
                signal = event.get("signal", {})
                lines.append(f"  ┌─ 信号详情 ──────────────────────────────────────────────")
                for k, v in signal.items():
                    if isinstance(v, dict):
                        lines.append(f"  │  {k}:")
                        items = list(v.items())
                        for sk, sv in (items[:8] if len(items) > 8 else items):
                            if isinstance(sv, float):
                                lines.append(f"  │    {sk:25s}  {sv:.1f}")
                            else:
                                lines.append(f"  │    {sk:25s}  {sv}")
                        if len(items) > 8:
                            lines.append(f"  │    ... 共 {len(items)} 项")
                    elif isinstance(v, list):
                        lines.append(f"  │  {k}: [{len(v)} 项]")
                        for item in v[:5]:
                            lines.append(f"  │    • {item}")
                        if len(v) > 5:
                            lines.append(f"  │    ... 共 {len(v)} 项")
                    else:
                        lines.append(f"  │  {k}: {v}")
                lines.append(f"  └───────────────────────────────────────────────────────────")
            lines.append("")
            return "\n".join(lines)

        cli_output(result_data, args, text=_text)
    except ValueError as e:
        print(f"  ❌ {e}")
        names = [c["name"] for c in collector_registry.list_all()]
        print(f"  可用: {', '.join(names)}")


def cmd_collector_run_all(args: argparse.Namespace) -> None:
    """运行所有采集器"""
    from ..cli_utils import bar_chart, parse_since
    from ..mirroring.collectors import collector_registry

    _register_collectors()
    since = parse_since(getattr(args, 'since', None))
    incremental = since > 0
    title = f"Phase 9C {'增量' if incremental else '全量'}采集 + 智能分析"
    if incremental:
        title += f" (自 {args.since})"
    results = collector_registry.run_all(incremental=incremental, since=since)

    # 分组显示
    cc_ok, zs_ok = [], []
    for name, info in results.items():
        if name.startswith("_"):
            continue
        if info.get("available"):
            target = cc_ok if name.startswith("claude-") else zs_ok
            target.append((name, info.get("count", 0)))

    total = results.get("_total", {})
    ok_n = sum(len(x) for x in [cc_ok, zs_ok])
    pipeline = results.get("_pipeline", {})

    result_data = {
        "incremental": incremental,
        "total_collectors": total.get("collectors", 0),
        "total_events": total.get("total_events", 0),
        "ok_count": ok_n,
        "has_pipeline": bool(pipeline),
        "pipeline": pipeline,
    }

    def _text():
        lines = [_str_section(title, "🚀")]
        for group_title, group_data, emoji, prefix in [
            ("Claude Code", cc_ok, "📦", "claude-"),
            ("ZenSkill", zs_ok, "🧘", "zenskill-"),
        ]:
            if group_data:
                lines.append(_str_box_header(group_title, emoji))
                for name, count in group_data:
                    short = name.replace(prefix, "")
                    b = bar_chart(count, 3, 10, "▓", "░")
                    lines.append(f"  │  🟢 {short:18s} {b} {count}")
                lines.append(_str_box_footer())
                if group_title == "Claude Code":
                    lines.append("")

        lines.append(f"  📊 采集完成: {total.get('collectors', 0)} 个源  |  "
                     f"{total.get('total_events', 0)} 条信号  |  🟢 {ok_n} 成功")

        # 处理管道
        if pipeline:
            dedup = pipeline.get("dedup_removed", 0)
            nlp = pipeline.get("nlp", {})
            insights = pipeline.get("insights", [])

            lines.append("")
            lines.append(_str_box_header("智能分析", "🧠"))
            if dedup > 0:
                lines.append(f"  │  🧹 去重: 移除 {dedup} 条重复")

            domains = nlp.get("domains", {})
            if domains:
                lines.append("  │")
                lines.append("  │  🏷  技术领域")
                for d, s in sorted(domains.items(), key=lambda x: x[1], reverse=True)[:5]:
                    b = bar_chart(s, 100, 16)
                    lines.append(f"  │     {d:10s}  {b}  {s:.0f}%")

            intents = nlp.get("intents", {})
            if intents:
                lines.append("  │")
                lines.append("  │  🎯 意图分布")
                parts = [f"{k} {'█' * v}{v}" for k, v in
                         sorted(intents.items(), key=lambda x: x[1], reverse=True)]
                lines.append("  │     " + "  ".join(parts))

            keywords = nlp.get("top_keywords", [])
            if keywords:
                lines.append("  │")
                kw_line = "  ".join(f"`{kw}`" for kw in keywords[:10])
                lines.append(f"  │  🔑 高频信号词: {kw_line}")

            maturity = nlp.get("tech_maturity", "")
            if maturity:
                levels = {"advanced": "🟢 高级", "intermediate": "🟡 中级", "beginner": "🔵 初级"}
                lines.append(f"  │  📈 技术成熟度: {levels.get(maturity, maturity)}")

            if insights:
                lines.append(f"  │  💡 洞察 ({len(insights)} 条)")
                for ins in insights:
                    lines.append(f"  │     • {ins}")

            lines.append(_str_box_footer())

        lines.append("  💡 数据已写入 ~/.zenskill/mirroring/events.jsonl")
        lines.append("")
        return "\n".join(lines)

    cli_output(result_data, args, text=_text)


def cmd_collector_hook(args: argparse.Namespace) -> None:
    """轻量级实时采集 + 会话感知 — 供 Claude Code PostToolUse Hook 调用

    stdout: 人类可读状态行 + 预警
    stderr: 结构化 JSON (供日志/监控)
    """
    import json, os, time, sys
    from pathlib import Path
    from ..mirroring.collectors import collector_registry

    _register_collectors()
    fast_sources = ["claude-history", "claude-sessions", "zenskill-events"]
    total = 0
    _hook_lines: list[str] = []  # 收集 stdout 输出行
    all_collected_events: list[dict] = []
    for name in fast_sources:
        try:
            c = collector_registry.get(name)
            if c and c.is_available():
                events = c.collect_full()
                collector_registry._write_events(events, c)
                total += len(events)
                all_collected_events.extend(events)
        except Exception:
            pass

    # ── 自动创建缺失的技能状态（Issue #3 修复）──
    try:
        skill_ids = set()
        for ev in all_collected_events:
            sid = ev.get("skill_id") or ev.get("data", {}).get("skill_id")
            if sid:
                skill_ids.add(sid)
        from ..core.paths import SkillStateManager
        for sid in skill_ids:
            mgr = SkillStateManager(sid)
            if not mgr.state_path.exists():
                mgr.save(mgr._default_state(), action="auto_create")
                _hook_lines.append(f"[zenskill] 自动创建技能状态: {sid}")
    except Exception:
        pass

    # ── 自动归档: events.jsonl > 1000 行 → 归档旧数据 (10R) ──
    events_file = Path.home() / ".zenskill" / "mirroring" / "events.jsonl"
    try:
        if events_file.exists():
            lines = events_file.read_text().count('\n')
            if lines > 1000:
                archive_dir = Path.home() / ".zenskill" / "mirroring" / "archive"
                archive_dir.mkdir(parents=True, exist_ok=True)
                ts = time.strftime("%Y%m%d_%H%M")
                archive_file = archive_dir / f"events_{ts}.jsonl"
                # 保留最近 500 行，其余归档
                all_lines = events_file.read_text().strip().split('\n')
                kept = all_lines[-500:]
                archived = all_lines[:-500]
                if archived:
                    with file_lock(events_file):
                        atomic_write_text(archive_file, '\n'.join(archived) + '\n')
                        atomic_write_text(events_file, '\n'.join(kept) + '\n')
    except Exception:
        pass

    # ── 会话状态感知 (自动重置) ──
    session_dir = Path.home() / ".zenskill" / "session"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_file = session_dir / "current.json"

    now = time.time()
    state = {"started": now, "tool_count": 0, "recent_tools": [], "last_active": now}
    reset_reason = ""

    # 尝试从 stdin 读取 Claude Code Hook 传入的 JSON (含 tool_name)
    tool_name = getattr(args, 'tool_name', '') or ''
    if not tool_name:
        try:
            import select
            if select.select([sys.stdin], [], [], 0)[0]:
                hook_data = json.loads(sys.stdin.read())
                tool_name = hook_data.get("tool_name", "") or hook_data.get("tool", "") or ""
        except Exception:
            pass

    with file_lock(session_file):
        if session_file.exists():
            try:
                loaded = json.loads(session_file.read_text())
                last_active = loaded.get("last_active", loaded.get("started", 0))
                current_ppid = os.getppid()
                stored_ppid = loaded.get("_claude_pid", 0)
                if stored_ppid and stored_ppid != current_ppid:
                    reset_reason = "(新 Claude Code 会话)"
                elif now - last_active > 1800:
                    reset_reason = f"(上次会话 {int((now - last_active) / 60)} 分钟前已结束)"
                else:
                    state = loaded
            except Exception:
                pass

        state["_claude_pid"] = os.getppid()
        state["tool_count"] += 1
        state["last_active"] = now
        if tool_name:
            state["recent_tools"].append(tool_name)
            state["recent_tools"] = state["recent_tools"][-5:]

        atomic_write_json(session_file, state, indent=None)

    # ── 阈值预警 ──
    alerts = []
    elapsed_min = (now - state["started"]) / 60
    tc = state["tool_count"]

    if elapsed_min > 60 and tc > 30:
        alerts.append(f"⏰ 已持续 {elapsed_min:.0f} 分钟/{tc} 次操作，建议 commit 或休息")
    elif tc > 0 and tc % 15 == 0 and tc > 5:
        alerts.append(f"📊 本次会话已 {tc} 次操作 (已 {elapsed_min:.0f} 分钟)")

    if state["recent_tools"] and all(
        t in ("Read", "Bash") for t in state["recent_tools"][-3:]
    ) and len(state["recent_tools"]) >= 3:
        alerts.append("💡 最近 3 次都是 Read/Bash，考虑用 Edit 直接修改")

    # ── 管道分析（每 5 分钟） ──
    cache_file = Path.home() / ".zenskill" / "mirroring" / "pipeline.json"
    last_run = 0
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text())
            last_run = cached.get("timestamp", 0)
        except Exception:
            pass

    pipeline_ran = False
    if time.time() - last_run > 300:
        result = _run_light_pipeline()
        if result:
            atomic_write_json(cache_file, result, indent=None)
            pipeline_ran = True

    # ── 主动洞察定期生成 (7F): 每 50 次操作 → ProactiveInsightEngine.check_and_generate ──
    if tc > 0 and tc % 50 == 0:
        try:
            from ..systems.active.proactive_insight import ProactiveInsightEngine
            pie = ProactiveInsightEngine()
            new_insights = pie.check_and_generate_insights()
            if new_insights:
                _hook_lines.append(f"💡 {len(new_insights)} 条新洞察已生成")
                for ins in new_insights[:2]:
                    _hook_lines.append(f"  - {ins.title}")
        except Exception:
            pass

    # ── MetricsStore 实时趋势检测 (每 30 次操作) ──
    if tc > 0 and tc % 30 == 0:
        try:
            from ..systems.visualization.metrics_store import MetricsStore
            ms = MetricsStore(args.skill_id)
            snaps = ms.get_all_snapshots()
            if len(snaps) >= 3:
                recent = snaps[-3:]
                trends = {}
                for dim in ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]:
                    vals = [s.ability_scores.get(dim, 0) for s in recent]
                    if vals[0] > 0 and vals[-1] < vals[0] - 5:
                        trends[dim] = f"↓{vals[0]-vals[-1]:.0f}"
                if trends:
                    dim_names = {"proficiency":"熟练度","stability":"稳定性","satisfaction":"满意度","responsiveness":"响应力","memory":"记忆力"}
                    trend_alerts = [f"{dim_names.get(d,d)}({v})" for d, v in trends.items()]
                    _hook_lines.append(f"📊 趋势预警: 维度下降 — {', '.join(trend_alerts)}")
        except Exception:
            pass

    # ── 跨模块集成 (7E + 8D): 每 30 分钟运行一次 ──
    integration = {}
    integration_cache = Path.home() / ".zenskill" / "session" / ".last_integration"
    last_integration = 0
    if integration_cache.exists():
        try:
            last_integration = float(integration_cache.read_text().strip())
        except Exception:
            pass

    if time.time() - last_integration > 1800:
        try:
            from ..integration import integrated_hook_output
            integration = integrated_hook_output()
            atomic_write_text(integration_cache, str(time.time()))
        except Exception:
            pass

    # ── 输出: stdout 人类可读 ──
    if reset_reason:
        _hook_lines.append(f"🔄 新会话 {reset_reason}")
    _hook_lines.append(f"✅ ZenSkill 已采集 {total} events | Session #{tc} ({elapsed_min:.0f}min)")

    for alert in alerts:
        _hook_lines.append(alert)

    # 7E: 目标建议
    for g in integration.get("goal_suggestions", [])[:2]:
        _hook_lines.append(f"🎯 建议目标: {g['title']} — {g['reason']}")

    # 8D: 图谱更新
    graph = integration.get("graph_update", {})
    if graph and "new_relationships" in graph:
        _hook_lines.append(f"🕸️ 图谱更新: +{graph['new_relationships']} 关系, {graph.get('total_nodes', 0)} 节点")

    # 7P: 即时反馈 (每 5 次工具调用输出一次微正向反馈)
    if tc > 0 and tc % 5 == 0:
        try:
            from ..systems.active.instant_feedback import InstantFeedbackEngine
            feedback = InstantFeedbackEngine(args.skill_id).generate_one_line(state)
            if feedback:
                _hook_lines.append(feedback)
        except Exception:
            pass

    # Layer 2: 智能提醒(每 10 次工具调用输出一次)
    if tc > 0 and tc % 10 == 0:
        try:
            from ..context_card import generate_smart_alert
            alert = generate_smart_alert()
            if alert:
                _hook_lines.append(alert)
        except Exception:
            pass

    # Stage A: 感知引擎评估 (每次工具调用后)
    try:
        from ..perception_engine import PerceptionEngine
        engine = PerceptionEngine()
        lt = time.localtime(now)
        ctx = {
            "tool_count": tc, "elapsed_min": elapsed_min,
            "recent_tools": state.get("recent_tools", []),
            "current_hour": lt.tm_hour,
            "current_minute": lt.tm_min,
            "last_command": "",
            "error_rate": 0.0,
        }
        perception = engine.evaluate(ctx)
        # 输出感知结果（仅当有告警或建议时）
        for alert in perception.get("alerts", []):
            sev = {"critical": "🚨", "high": "🔴", "medium": "🟡", "low": "🔵"}
            _hook_lines.append(f"{sev.get(alert['severity'], '⚪')} [{alert['source']}] {alert['message']}")
        for sug in perception.get("suggestions", []):
            _hook_lines.append(f"💡 [{sug['source']}] {sug['suggestion']}")
    except Exception:
        pass

    # Phase 3: PDCA Check — 禅思反思触发 (L3+L4)
    try:
        from ..zen_reflection import ZenReflectionEngine
        zr = ZenReflectionEngine()
        trigger = zr.should_trigger(tc, elapsed_min)
        if trigger:
            _hook_lines.append(f"🧘 [ZenLoop {trigger}]")
            if trigger == "check":
                _hook_lines.append(f"  PDCA Check: {tc} 次操作 — 检查是否偏离计划")
            elif trigger == "reflect":
                # 生成轻量反思
                reflection = zr.generate_reflection({
                    "tool_count": tc, "elapsed_min": elapsed_min,
                    "recent_tools": state.get("recent_tools", []),
                    "pipeline_insights": [],
                    "anomalies": alerts,
                })
                _hook_lines.append(f"  💾 反思报告已保存到 ~/.zenskill/zenloop/")
            elif trigger == "improve":
                imps = zr.generate_improvements({
                    "tool_count": tc, "elapsed_min": elapsed_min,
                    "anomalies": alerts, "skill_gaps": [],
                    "recent_tools": state.get("recent_tools", []),
                })
                for imp in imps[:2]:
                    _hook_lines.append(f"  📈 [{imp['area']}] {imp['suggestion'][:60]}")
    except Exception:
        pass

    # 通知引擎: 里程碑/疲劳/洞察/升级 → 推送通知
    try:
        from ..notifier import notifier as zn
        from ..core.paths import SkillStateManager
        mgr = SkillStateManager(args.skill_id)
        zs = mgr.load()
        notifs = zn.check({
            "tool_count": tc, "elapsed_min": elapsed_min,
            "level": zs.get("level", ""),
            "old_level": zs.get("_old_level", ""),
        })
        if notifs:
            _hook_lines.append(zn.format_for_hook(notifs))
        # LevelUpCeremony: 境界提升时触发庆典
        old_lv = zs.get("_old_level", "")
        new_lv = zs.get("level", "")
        if old_lv and new_lv and old_lv != new_lv:
            try:
                from ..systems.visualization.level_up_ceremony import LevelUpCeremony
                from ..core.schemas import SkillLevel
                old_enum = SkillLevel(old_lv)
                new_enum = SkillLevel(new_lv)
                ceremony = LevelUpCeremony()
                msg = ceremony.generate_quick_celebration(old_enum, new_enum)
                _hook_lines.append(msg)
                ceremony.save_ceremony(msg, old_lv, new_lv)
            except Exception:
                pass
    except Exception:
        pass

    # Step 4: 记忆自动沉淀 — 写入 state episodes (持久化, 跨进程)
    try:
        from ..core.paths import SkillStateManager
        skill_mgr = SkillStateManager(args.skill_id)
        skill_state = skill_mgr.load()
        episodes = skill_state.get("episodes", [])
        tool_str = state.get("recent_tools", [])[-1] if state.get("recent_tools") else "unknown"
        episodes.append({
            "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "action": f"hook_{tool_str}",
            "content": f"工具调用: {tool_str}, 会话 #{tc}",
            "tags": ["hook", tool_str],
        })
        # 只保留最近 200 条
        skill_state["episodes"] = episodes[-200:]
        skill_mgr.save(skill_state, action="memory_add", write_history=True)
        # 每 20 次: 记忆巩固 — 统计 + 去重
        if tc > 0 and tc % 20 == 0:
            _hook_lines.append(f"🧠 记忆积累: {len(episodes)} 条情景记忆")
            # 简单 Consolidation: 合并重复 tags 的连续记忆
            deduped = 0
            seen = set()
            for ep in reversed(episodes):
                key = (ep.get("action", ""), ep.get("content", "")[:40])
                if key in seen:
                    deduped += 1
                else:
                    seen.add(key)
            if deduped > 0:
                _hook_lines.append(f"  ↳ Consolidation: {deduped} 条重复记忆已合并")
        # 每 50 次: 记忆洞察 + 净化
        if tc > 0 and tc % 50 == 0:
            action_counts = {}
            for ep in episodes:
                act = ep.get("action", "unknown")
                action_counts[act] = action_counts.get(act, 0) + 1
            top_actions = sorted(action_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            _hook_lines.append(f"💡 记忆洞察: 高频操作 {', '.join(f'{a}({c}次)' for a, c in top_actions)}")
            # Purification: 清理超过 30 天的旧记忆
            cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - 30*86400))
            kept = [e for e in episodes if str(e.get("date", ""))[:10] >= cutoff]
            purged = len(episodes) - len(kept)
            if purged > 0:
                skill_state["episodes"] = kept[-200:]
                skill_mgr.save(skill_state, action="purification", write_history=True)
                _hook_lines.append(f"🧹 Purification: {purged} 条旧记忆已清理")
    except Exception:
        pass

    # Step 1+2: 每 30 次操作 → 自动创建目标 + 生成任务
    if tc > 0 and tc % 30 == 0:
        try:
            from ..systems.active.goal_engine import ActiveGoalEngine
            from ..systems.active.task_recommender import TaskRecommendationEngine
            engine = ActiveGoalEngine()
            recommender = TaskRecommendationEngine()

            # Step 1: 自动创建目标 (7E) — 检测弱维度 → 建议目标 → 自动创建
            active = engine.get_active_goals()
            if len(active) < 2:
                suggested = engine.suggest_goals(n_goals=2)
                for sg in suggested:
                    try:
                        goal = engine.create_goal(
                            dimension=sg.dimension,
                            target_score=sg.target_score,
                        )
                        dim_name = engine.DIMENSION_NAMES.get(sg.dimension, sg.dimension)
                        _hook_lines.append(f"🎯 新目标: {dim_name} {sg.current_score}→{sg.target_score}")
                    except Exception:
                        pass

            # Step 2: 为活跃目标生成推荐任务 (7G LLM 个性化)
            active = engine.get_active_goals()
            if active:
                try:
                    from ..task_generator import TaskGenerator
                    gen = TaskGenerator()
                    for goal in active[:2]:
                        tasks = gen.generate_for_goal(goal)
                        source = "LLM" if tasks and tasks[0].get("source") != "template" else "模板"
                        if tasks:
                            dim_name = engine.DIMENSION_NAMES.get(goal.dimension, goal.dimension)
                            _hook_lines.append(f"📋 [{dim_name}] {len(tasks)} 个{source}任务")
                except Exception:
                    # 降级: TaskRecommendationEngine 模板推荐
                    for goal in active[:2]:
                        try:
                            tasks = recommender.recommend_tasks(count=3)
                            if tasks:
                                _hook_lines.append(f"📋 {len(tasks)} 个推荐任务可用")
                        except Exception:
                            pass
        except Exception:
            pass

    # Stage D: 主动干预 — 阈值触发行动建议
    if tc > 0 and tc % 50 == 0 or (elapsed_min > 90 and tc > 50):
        try:
            pipeline_file = Path.home() / ".zenskill" / "mirroring" / "pipeline.json"
            pipeline_data = json.loads(pipeline_file.read_text()) if pipeline_file.exists() else {}
            patterns_file = Path.home() / ".zenskill" / "mirroring" / "patterns.json"
            patterns_data = json.loads(patterns_file.read_text()) if patterns_file.exists() else {}
            from ..context_card import generate_active_interventions
            interventions = generate_active_interventions(state, pipeline_data, patterns_data)
            for iv in interventions[:2]:
                icon = {"recommended": "⭐", "suggested": "💡", "info": "ℹ️"}.get(iv["priority"], "💡")
                _hook_lines.append(f"{icon} ACT: {iv['message']}")
        except Exception:
            pass

    # ── stdout: 通过 cli_output 输出 (支持 --json) ──
    hook_result = {
        "ok": True, "events": total,
        "pipeline": pipeline_ran,
        "session": {"tool_count": tc, "elapsed_min": round(elapsed_min, 1)},
        "alerts": alerts,
        "integration": integration,
    }
    cli_output(hook_result, args, text=lambda: "\n".join(_hook_lines))

    # ── stderr: 结构化 JSON (供程序解析) ──
    sys.stderr.write(json.dumps(hook_result, ensure_ascii=False) + "\n")


def cmd_collector_pipeline(args: argparse.Namespace) -> None:
    """手动触发管道分析"""
    from ..cli_utils import bar_chart

    result = _run_light_pipeline()

    if not result:
        cli_output({"ok": False, "error": "no_data"}, args,
                   text=lambda: "  [dim]无采集数据，请先运行 zenskill collector run-all[/dim]\n")
        return

    nlp = result.get("nlp", {})
    insights = result.get("insights", [])

    def _text():
        lines = [_str_section("管道分析", "🧠"),
                 _str_box_header("分析结果")]
        lines.append(f"  │  🧹 去重: 移除 {result['dedup_removed']} 条")
        lines.append(f"  │  📊 事件: {result['event_count']} 条")

        domains = nlp.get("domains", {})
        if domains:
            lines.append("  │  🏷  技术领域")
            for d, s in sorted(domains.items(), key=lambda x: x[1], reverse=True)[:5]:
                b = bar_chart(s, 100, 16)
                lines.append(f"  │     {d:10s}  {b}  {s:.0f}%")

        intents = nlp.get("intents", {})
        if intents:
            parts = [f"{k} {'█' * v}{v}" for k, v in sorted(intents.items(), key=lambda x: x[1], reverse=True)]
            lines.append("  │  🎯 意图: " + "  ".join(parts))

        keywords = nlp.get("top_keywords", [])
        if keywords:
            lines.append(f"  │  🔑 高频词: {'  '.join(f'`{k}`' for k in keywords[:10])}")

        maturity = nlp.get("tech_maturity", "")
        if maturity:
            levels = {"advanced": "🟢 高级", "intermediate": "🟡 中级", "beginner": "🔵 初级"}
            lines.append(f"  │  📈 技术成熟度: {levels.get(maturity, maturity)}")

        if insights:
            lines.append(f"  │  💡 洞察 ({len(insights)} 条)")
            for ins in insights:
                lines.append(f"  │     • {ins}")

        lines.append(_str_box_footer())
        lines.append("")
        return "\n".join(lines)

    cli_output({"ok": True, "pipeline": result}, args, text=_text)



def register_collector_parser(subparsers) -> None:
    """注册 collector 子命令组。"""
    collector_parser = subparsers.add_parser("collector", help="智能体生态采集器（Phase 9C）")
    collector_parser.set_defaults(func=cmd_collector_list)  # 默认为 list
    collector_subparsers = collector_parser.add_subparsers(dest="subcommand", help="采集操作")

    # collector list
    collector_list_parser = collector_subparsers.add_parser("list", help="列出所有采集器")
    collector_list_parser.set_defaults(func=cmd_collector_list)

    # collector run
    collector_run_parser = collector_subparsers.add_parser("run", help="运行指定采集器")
    collector_run_parser.add_argument("name", help="采集器名称")
    collector_run_parser.add_argument("--since", help="增量采集起始时间 (ISO格式或相对时间: 1h/30m/1d)")
    collector_run_parser.set_defaults(func=cmd_collector_run)

    # collector run-all
    collector_run_all_parser = collector_subparsers.add_parser("run-all", help="运行全部采集器")
    collector_run_all_parser.add_argument("--since", help="增量采集起始时间 (ISO格式或相对时间: 1h/30m/1d)")
    collector_run_all_parser.set_defaults(func=cmd_collector_run_all)

    # collector hook (给 Claude Code PostToolUse hook 用)
    collector_hook_parser = collector_subparsers.add_parser("hook", help="轻量级实时采集（供 Claude Code Hook 使用）")
    collector_hook_parser.set_defaults(func=cmd_collector_hook)

    # collector pipeline (手动触发管道分析)
    collector_pipeline_parser = collector_subparsers.add_parser("pipeline", help="手动触发管道分析（去重→NLP→聚合）")
    collector_pipeline_parser.set_defaults(func=cmd_collector_pipeline)

