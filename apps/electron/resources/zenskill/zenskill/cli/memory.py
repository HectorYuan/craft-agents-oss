"""memory 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

from ..cli_utils import output as cli_output
from ..core.paths import SkillStateManager

def cmd_memory_add(args: argparse.Namespace) -> None:
    """添加记忆"""
    mgr = SkillStateManager(args.skill_id)
    mgr.record_episode('memory_add', args.content)

    result = {"ok": True, "content": args.content, "tags": args.tags or ""}
    cli_output(result, args, text=lambda: (
        f"✅ 记忆已添加\n"
        f"   内容: {args.content}"
        + (f"\n   标签: {args.tags}" if args.tags else "")
    ))


def cmd_memory_list(args: argparse.Namespace) -> None:
    """列出记忆"""
    mgr = SkillStateManager(args.skill_id)
    state = mgr.load()

    episodes = state.get('episodes', [])

    items = []
    for ep in reversed(episodes[-args.n:]):
        items.append({
            "content": ep.get('content', ''),
            "type": ep.get('action', 'general'),
            "created_at": ep.get('date', ''),
            "tags": ep.get('tags', ''),
        })
    result = {"count": len(episodes), "items": items}

    def _text():
        lines = []
        lines.append(f"  📋 记忆列表 — 共 {len(episodes)} 条")
        lines.append(f"  ══════════════════════════════════════════════════════════════")
        lines.append("")

        if not episodes:
            lines.append(f"  [dim]暂无记忆数据[/dim]")
            lines.append("")
            return "\n".join(lines)

        for i, ep in enumerate(reversed(episodes[-args.n:]), 1):
            date = str(ep.get('date', 'N/A'))[:16]
            content = str(ep.get('content', 'N/A'))[:80]
            lines.append(f"  {i:3d}.  [{date}]  {content}")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_memory_search(args: argparse.Namespace) -> None:
    """搜索记忆"""
    mgr = SkillStateManager(args.skill_id)
    state = mgr.load()

    episodes = state.get('episodes', [])
    keyword = args.keyword.lower()

    # 搜索匹配的记忆
    matches = []
    for ep in episodes:
        content = ep.get('content', '').lower()
        action = ep.get('action', '').lower()
        raw_tags = ep.get('tags', '')
        tags = normalize_tags(raw_tags).lower() if raw_tags else ''

        if keyword in content or keyword in action or keyword in tags:
            matches.append(ep)

    items = []
    for ep in reversed(matches):
        items.append({
            "content": ep.get('content', ''),
            "type": ep.get('action', 'general'),
            "created_at": ep.get('date', ''),
            "tags": ep.get('tags', ''),
        })
    result = {"keyword": args.keyword, "match_count": len(matches), "matches": items}

    def _text():
        lines = [f"🔍 记忆搜索: '{args.keyword}'", "=" * 60, f"   共找到 {len(matches)} 条匹配记忆"]
        if matches:
            lines.append("")
            for i, ep in enumerate(reversed(matches), 1):
                date = ep.get('date', 'N/A')
                action = ep.get('action', 'N/A')
                content = ep.get('content', 'N/A')
                lines.append(f"{i:2d}. [{date}] **{action}**")
                lines.append(f"     {content}")
                if ep.get('tags'):
                    lines.append(f"     标签: {ep['tags']}")
                lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_memory_export(args: argparse.Namespace) -> None:
    """导出记忆到文件"""
    import json
    from pathlib import Path

    mgr = SkillStateManager(args.skill_id)
    state = mgr.load()

    export_data = {
        "version": "1.0",
        "exported_at": datetime.now().isoformat(),
        "skill_id": args.skill_id,
        "level": state.get('level'),
        "usage_count": state.get('usage_count'),
        "episodes": state.get('episodes', []),
        "milestones": state.get('milestones', []),
        "metrics": state.get('metrics', {}),
    }

    # 确定输出文件
    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path.cwd() / f"zenskill_{args.skill_id}_backup_{timestamp}.json"

    # 确保目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)

    result = {
        "ok": True,
        "output_path": str(output_path),
        "episode_count": len(export_data['episodes']),
        "usage_count": export_data['usage_count'],
        "level": export_data['level'],
    }
    cli_output(result, args, text=lambda: (
        f"✅ 记忆导出成功！\n"
        f"   导出文件: {output_path}\n"
        f"   记忆条数: {len(export_data['episodes'])}\n"
        f"   使用次数: {export_data['usage_count']}\n"
        f"   当前境界: {export_data['level']}"
    ))


def cmd_memory_import(args: argparse.Namespace) -> None:
    """从文件导入记忆"""
    import json
    from pathlib import Path

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 文件不存在: {input_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        import_data = json.load(f)

    mgr = SkillStateManager(args.skill_id)
    state = mgr.load()

    # 合并记忆（避免重复）
    existing_contents = {ep.get('content', '') for ep in state.get('episodes', [])}
    new_episodes = [
        ep for ep in import_data.get('episodes', [])
        if ep.get('content', '') not in existing_contents
    ]

    if not new_episodes:
        cli_output({"ok": True, "new_count": 0, "total_count": len(state.get('episodes', []))},
                   args, text=lambda: "ℹ️  没有新记忆需要导入")
        return

    if args.dry_run:
        cli_output({
            "ok": True, "dry_run": True,
            "new_count": len(new_episodes),
            "source_skill_id": import_data.get('skill_id', 'unknown'),
            "exported_at": import_data.get('exported_at', 'unknown'),
        }, args, text=lambda: (
            f"📋 预览导入:\n"
            f"   将导入 {len(new_episodes)} 条新记忆\n"
            f"   技能ID: {import_data.get('skill_id', 'unknown')}\n"
            f"   导出时间: {import_data.get('exported_at', 'unknown')}\n\n"
            f"   使用 '--dry-run' 参数预览，去掉该参数执行实际导入"
        ))
        return

    # 实际导入
    if 'episodes' not in state:
        state['episodes'] = []
    state['episodes'].extend(new_episodes)

    # 合并里程碑
    new_milestones_count = 0
    if 'milestones' in import_data:
        existing_milestones = {m.get('achievement', '') for m in state.get('milestones', [])}
        new_milestones = [
            m for m in import_data['milestones']
            if m.get('achievement', '') not in existing_milestones
        ]
        if new_milestones:
            if 'milestones' not in state:
                state['milestones'] = []
            state['milestones'].extend(new_milestones)
            new_milestones_count = len(new_milestones)

    mgr.save(state, action="memory_import")

    total_episodes = len(state.get('episodes', []))
    cli_output({
        "ok": True,
        "import_file": str(input_path),
        "new_episodes": len(new_episodes),
        "total_episodes": total_episodes,
        "new_milestones": new_milestones_count,
    }, args, text=lambda: (
        f"✅ 记忆导入成功！\n"
        f"   导入文件: {input_path}\n"
        f"   新增记忆: {len(new_episodes)} 条\n"
        f"   当前总记忆: {total_episodes} 条"
    ))


def cmd_memory_stats(args: argparse.Namespace) -> None:
    """记忆统计 — 查看情景记忆总量/去重/高频操作/净化建议"""
    from collections import Counter
    from ..core.paths import SkillStateManager

    sm = SkillStateManager(args.skill_id)
    ss = sm.load()
    episodes = ss.get("episodes", [])

    # 预计算所有统计数据
    date_metrics = {}
    if episodes:
        dates = [str(e.get("date", ""))[:10] for e in episodes if e.get("date")]
        if dates:
            date_counts = Counter(dates)
            recent_days = sorted(date_counts.keys())[-7:]
            date_metrics = {
                "active_days": len(date_counts),
                "recent_7day_count": sum(date_counts[d] for d in recent_days),
            }

    action_counts = Counter(e.get("action", "unknown") for e in episodes)
    top_actions = [{"action": a, "count": c, "pct": round(c / len(episodes) * 100, 1)}
                   for a, c in action_counts.most_common(5)] if episodes else []

    seen = set()
    dupes = 0
    for ep in episodes:
        key = (ep.get("action", ""), str(ep.get("content", ""))[:40])
        if key in seen:
            dupes += 1
        else:
            seen.add(key)

    import time
    cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400))
    old_count = sum(1 for e in episodes if str(e.get("date", ""))[:10] < cutoff)

    result = {
        "total_episodes": len(episodes),
        "date_metrics": date_metrics,
        "action_types": len(action_counts),
        "top_actions": top_actions,
        "unique_count": len(episodes) - dupes,
        "duplicate_count": dupes,
        "old_count": old_count,
    }

    def _text():
        lines = ["", "🧠 记忆统计", "═" * 50, f"   情景记忆总数: {len(episodes)} 条"]
        if not episodes:
            lines.append("   暂无记忆数据")
            return "\n".join(lines)

        if date_metrics:
            lines.append(f"   活跃天数: {date_metrics['active_days']} 天 (最近7天: {date_metrics['recent_7day_count']} 条)")

        lines.append(f"   操作类型: {len(action_counts)} 种")
        for act, cnt in action_counts.most_common(5):
            pct = cnt / len(episodes) * 100
            lines.append(f"     {act}: {cnt} 次 ({pct:.1f}%)")

        lines.append(f"   去重后: {len(episodes) - dupes} 条 (重复: {dupes})")
        if old_count > 0:
            lines.append(f"   ⚠️ 超过30天旧记忆: {old_count} 条 (建议运行 zenskill collector hook 自动清理)")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_memory_cross_index(args: argparse.Namespace) -> None:
    """建立跨会话记忆索引 (10J)"""
    from ..systems.memory.cross_session import CrossSessionMemory
    from ..cli_utils import section_blank, box_header, box_footer

    csm = CrossSessionMemory()
    result = csm.build_index(force=getattr(args, 'force', False))

    def _text():
        lines = []
        section_blank("跨会话记忆索引", "🧠", phase="10J")
        if result["sessions"] == 0:
            lines.append("  [dim]暂无会话数据，继续使用后自动生成[/dim]")
            lines.append("")
            return "\n".join(lines)
        box_header("索引结果")
        lines.append(f"  │  会话数:   {result['sessions']}")
        lines.append(f"  │  话题簇:   {result['clusters']}")
        lines.append(f"  │  跨会话链接: {result['links']}")
        lines.append(f"  │  项目数:   {len(result['projects'])}")
        box_footer()
        if result.get("projects"):
            lines.append("")
            box_header("检测到的项目")
            for p in result["projects"]:
                lines.append(f"  │  • {p}")
            box_footer()
        lines.append("")
        lines.append("  💡 memory cross search <query>    搜索全部会话")
        lines.append("  💡 memory cross related <sid>    查看关联会话")
        lines.append("  💡 memory cross remind           查看智能提醒")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_memory_cross_search(args: argparse.Namespace) -> None:
    """跨会话搜索 (10J)"""
    from ..systems.memory.cross_session import CrossSessionMemory
    from ..cli_utils import section_blank, box_header, box_footer

    query = args.query
    top_k = getattr(args, "top_k", 5)
    csm = CrossSessionMemory()
    results = csm.search_sessions(query, top_k=top_k)

    def _text():
        lines = []
        section_blank(f"跨会话搜索: {query}", "🔍", phase="10J")
        if not results:
            lines.append(f"  [dim]未找到匹配结果[/dim]")
            lines.append("")
            return "\n".join(lines)
        box_header(f"找到 {len(results)} 条匹配")
        for r in results:
            lines.append(f"  │  [{r['score']:.0%}] {r['date']} | {r['project']}")
            lines.append(f"  │     {r['summary'][:80]}")
        box_footer()
        lines.append("")
        lines.append("  💡 查看更多: memory cross related <session_id>")
        lines.append("")
        return "\n".join(lines)

    cli_output({"query": query, "results": results}, args, text=_text)


def cmd_memory_cross_related(args: argparse.Namespace) -> None:
    """查看关联会话 (10J)"""
    from ..systems.memory.cross_session import CrossSessionMemory
    from ..cli_utils import section_blank, box_header, box_footer

    sid = args.session_id
    csm = CrossSessionMemory()
    related = csm.get_related_sessions(sid)

    def _text():
        lines = []
        section_blank(f"会话关联: {sid[:12]}...", "🔗", phase="10J")
        if not related:
            lines.append("  [dim]无关联会话[/dim]")
            lines.append("")
            return "\n".join(lines)
        box_header(f"找到 {len(related)} 个关联会话")
        for r in related:
            type_icon = {"topic_recurrence": "🔁", "project_continuation": "📂", "tool_pattern": "🔧"}
            lines.append(f"  │  {type_icon.get(r['link_type'], '🔗')} [{r['similarity']:.0%}] {r['date']}")
            lines.append(f"  │     {r['summary'][:80]}")
        box_footer()
        lines.append("")
        return "\n".join(lines)

    cli_output({"session_id": sid, "related": related}, args, text=_text)


def cmd_memory_cross_remind(args: argparse.Namespace) -> None:
    """跨会话智能提醒 (10J)"""
    from ..systems.memory.cross_session import CrossSessionMemory
    from ..cli_utils import section_blank, box_header, box_footer

    days = getattr(args, "days", 7)
    csm = CrossSessionMemory()
    reminders = csm.get_reminders(window_days=days)

    def _text():
        lines = []
        section_blank(f"跨会话提醒 (最近 {days} 天)", "⏰", phase="10J")
        if not reminders:
            lines.append("  [dim]暂无提醒[/dim]")
            lines.append("")
            return "\n".join(lines)
        box_header(f"{len(reminders)} 条提醒")
        for r in reminders:
            icon = {"topic_recurrence": "🔁", "past_topic": "📅"}.get(r["type"], "💡")
            lines.append(f"  │  {icon} {r['message']}")
        box_footer()
        lines.append("")
        lines.append("  💡 memory cross network    查看知识网络")
        lines.append("")
        return "\n".join(lines)

    cli_output({"reminders": reminders}, args, text=_text)


def cmd_memory_cross_network(args: argparse.Namespace) -> None:
    """知识网络可视化 (10J)"""
    from ..systems.memory.cross_session import CrossSessionMemory
    from ..cli_utils import section_blank, box_header, box_footer

    csm = CrossSessionMemory()
    network = csm.get_knowledge_network()

    nodes = network.get("nodes", [])
    edges = network.get("edges", [])

    session_nodes = [n for n in nodes if n.get("type") == "session"]
    topic_nodes = [n for n in nodes if n.get("type") == "topic"]

    def _text():
        lines = []
        section_blank("知识网络", "🌐", phase="10J")
        box_header(f"网络概览")
        lines.append(f"  │  会话节点: {len(session_nodes)}")
        lines.append(f"  │  话题节点: {len(topic_nodes)}")
        lines.append(f"  │  关系边:   {len(edges)}")
        box_footer()
        if topic_nodes:
            lines.append("")
            box_header("话题簇")
            for n in sorted(topic_nodes, key=lambda x: x["size"], reverse=True)[:10]:
                domain_icon = {"frontend": "🎨", "backend": "⚙️", "devops": "🐳",
                               "data": "📊", "ai_ml": "🤖", "cli_tui": "🖥️"}
                icon = domain_icon.get(n.get("domain", ""), "💬")
                lines.append(f"  │  {icon} {n['label']} ({n['size']} 条)")
            box_footer()
        if session_nodes:
            lines.append("")
            box_header("最近会话")
            recent = sorted(session_nodes, key=lambda n: n.get("label", ""), reverse=True)[:5]
            for n in recent:
                lines.append(f"  │  📅 {n['label']} | {n.get('project', '?')} | {n.get('top_intent', '?')}")
            box_footer()
        lines.append("")
        return "\n".join(lines)

    result = {"nodes": len(nodes), "edges": len(edges)}
    cli_output(result, args, text=_text)



def register_memory_parser(subparsers) -> None:
    """注册 memory 子命令组。"""
    memory_parser = subparsers.add_parser("memory", help="记忆管理")
    memory_subparsers = memory_parser.add_subparsers(dest="subcommand", help="记忆操作")

    # memory add
    add_parser = memory_subparsers.add_parser("add", help="添加记忆")
    add_parser.add_argument("content", help="记忆内容")
    add_parser.add_argument("--tags", default="", help="标签，逗号分隔")
    add_parser.set_defaults(func=cmd_memory_add)

    # memory list
    list_parser = memory_subparsers.add_parser("list", help="列出记忆")
    list_parser.add_argument("--n", type=int, default=20, help="显示最近 N 条")
    list_parser.set_defaults(func=cmd_memory_list)

    # memory search
    search_parser = memory_subparsers.add_parser("search", help="搜索记忆")
    search_parser.add_argument("keyword", help="搜索关键词")
    search_parser.set_defaults(func=cmd_memory_search)

    # memory export
    export_parser = memory_subparsers.add_parser("export", help="导出记忆到文件")
    export_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    export_parser.add_argument("--output", help="输出文件路径")
    export_parser.set_defaults(func=cmd_memory_export)

    # memory import
    import_parser = memory_subparsers.add_parser("import", help="从文件导入记忆")
    import_parser.add_argument("input", help="导入文件路径")
    import_parser.add_argument("--skill-id", default="zenskill-core", help="目标技能ID")
    import_parser.add_argument("--dry-run", action="store_true", help="预览导入效果")
    import_parser.set_defaults(func=cmd_memory_import)

    # memory stats
    memory_stats_parser = memory_subparsers.add_parser("stats", help="记忆统计 — 容量/去重/高频操作")
    memory_stats_parser.set_defaults(func=cmd_memory_stats)

    # 10J: 跨会话记忆关联
    memory_cross_p = memory_subparsers.add_parser("cross", help="跨会话记忆关联 (Phase 10J)")
    cross_sub = memory_cross_p.add_subparsers(dest="cross_action", help="跨会话操作")
    cross_index_p = cross_sub.add_parser("index", help="建立跨会话记忆索引")
    cross_index_p.set_defaults(func=cmd_memory_cross_index)
    cross_search_p = cross_sub.add_parser("search", help="跨会话搜索")
    cross_search_p.add_argument("query", help="搜索关键词")
    cross_search_p.add_argument("--top-k", type=int, default=5, help="返回数量")
    cross_search_p.set_defaults(func=cmd_memory_cross_search)
    cross_related_p = cross_sub.add_parser("related", help="查看关联会话")
    cross_related_p.add_argument("session_id", help="会话 ID")
    cross_related_p.set_defaults(func=cmd_memory_cross_related)
    cross_remind_p = cross_sub.add_parser("remind", help="跨会话智能提醒")
    cross_remind_p.add_argument("--days", type=int, default=7, help="回顾窗口天数")
    cross_remind_p.set_defaults(func=cmd_memory_cross_remind)
    cross_network_p = cross_sub.add_parser("network", help="知识网络可视化")
    cross_network_p.set_defaults(func=cmd_memory_cross_network)

    # ── Runtime v2.0: chain / version / upgrade (Phase 12.5 + 13.0) ──
