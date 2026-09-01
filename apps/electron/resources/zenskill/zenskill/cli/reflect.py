"""reflect 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

from ..cli_utils import output as cli_output
from ..core.paths import SkillStateManager, get_zenloop_dir

def cmd_reflect_store(args: argparse.Namespace) -> None:
    """存储宿主 Claude 完成的反思结果"""
    import json
    import sys

    # 从 stdin 读取 JSON
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("❌ 输入格式错误，需要有效的 JSON")
        sys.exit(1)

    # 提取反思内容
    reflection_content = input_data.get("reflection_content", "")
    if not reflection_content:
        print("❌ 缺少 reflection_content 字段")
        sys.exit(1)

    # 写入最新反思文件
    zenloop_dir = get_zenloop_dir()
    latest_file = zenloop_dir / "latest_reflection.md"
    with open(latest_file, "w", encoding="utf-8") as f:
        f.write(reflection_content)

    # 写入历史文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_file = zenloop_dir / f"reflection_{timestamp}.md"
    with open(history_file, "w", encoding="utf-8") as f:
        f.write(reflection_content)

    # 更新状态和记忆
    mgr = SkillStateManager(args.skill_id)
    mgr.record_episode('reflection', f'宿主 Claude 完成禅思反思 - 长度: {len(reflection_content)} 字符')

    result = {
        "latest_file": str(latest_file),
        "history_file": str(history_file),
        "content_length": len(reflection_content),
    }
    cli_output(result, args, text=lambda: (
        f"✅ 反思结果已存储\n"
        f"   最新报告: {latest_file}\n"
        f"   历史报告: {history_file}\n"
        f"   内容长度: {len(reflection_content)} 字符"
    ))


def cmd_reflect_trigger(args: argparse.Namespace) -> None:
    """触发禅思反思"""
    import json

    mgr = SkillStateManager(args.skill_id)
    state = mgr.load()

    # 宿主协作模式：输出 JSON，让宿主 Claude 完成实际思考
    if getattr(args, 'hosted', False):
        from ..core.llm_provider import ClaudeCodeHostedProvider

        provider = ClaudeCodeHostedProvider()

        # 使用专用方法生成禅思反思的高质量 prompt
        llm_prompt = provider.format_reflection_prompt(
            interaction_history=state.get('episodes', []),
            memories=state.get('episodes', []),
            skill_state=state,
        )

        result = {
            "llm_task": True,
            "task_type": "reflection",
            "prompt": llm_prompt,
            "expected_format": "markdown",
            "result_callback": {
                "command": "python -m zenskill reflect store",
                "stdin_json": True,
                "result_key": "reflection_content",
            },
            "skill_state": {
                "skill_id": args.skill_id,
                "level": state.get('level', 'NOVICE'),
                "usage_count": state.get('usage_count', 0),
                "episode_count": len(state.get('episodes', [])),
            },
        }

        # 以 JSON 格式输出，方便宿主解析
        if getattr(args, 'output', None) == 'json':
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            # 友好格式提示
            print(f"🧘 宿主协作模式 - 已生成 LLM 任务")
            print(f"=" * 60)
            print(f"\n📋 任务信息:")
            print(f"   - 任务类型: 禅思反思")
            print(f"   - Prompt 长度: {len(llm_prompt)} 字符")
            print(f"   - 期望格式: Markdown")
            print(f"\n💡 使用方式:")
            print(f"   1. 将 prompt 传给宿主 Claude 完成思考")
            print(f"   2. 通过写回命令存储结果:")
            print(f"      echo '{{\"reflection_content\": \"...\"}}' | python -m zenskill reflect store")
        return

    # 普通模式：使用规则引擎生成报告
    # 生成详细反思报告
    report = generate_reflection_report(state)

    # 保存到文件
    zenloop_dir = get_zenloop_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 保存带时间戳的历史报告
    history_file = zenloop_dir / f"reflection_{timestamp}.md"
    with open(history_file, "w", encoding="utf-8") as f:
        f.write(report)

    # 保存最新报告（方便快速查看）
    latest_file = zenloop_dir / "latest_reflection.md"
    with open(latest_file, "w", encoding="utf-8") as f:
        f.write(report)

    # 记录反思
    usage_count = state.get('usage_count', 0)
    episodes = state.get('episodes', [])
    mgr.record_episode('reflection', f'禅思反思 - 使用{usage_count}次，境界{state.get("level", "NOVICE")}')

    result = {
        "ok": True,
        "usage_count": usage_count,
        "episode_count": len(episodes),
        "level": state.get('level', 'NOVICE'),
        "latest_file": str(latest_file),
        "history_file": str(history_file),
    }
    cli_output(result, args, text=lambda: (
        f"🧘 触发禅思反思...\n"
        f"{"=" * 60}\n\n"
        f"📊 本次周期统计:\n"
        f"   - 使用次数: {usage_count} 次\n"
        f"   - 成长事件: {len(episodes)} 条\n"
        f"   - 当前境界: {state.get('level', 'NOVICE')}\n\n"
        f"📄 报告已保存:\n"
        f"   最新报告: {latest_file}\n"
        f"   历史报告: {history_file}\n\n"
        f"✅ 反思完成！成长记录已更新"
    ))


def cmd_reflect_issues(args: argparse.Namespace) -> None:
    """自我诊断：扫描系统优化点"""
    mgr = SkillStateManager(args.skill_id)
    state = mgr.load()
    zenloop_dir = get_zenloop_dir()

    issues = []
    warnings = []
    suggestions = []

    # 检查 1: 记忆数量
    episode_count = len(state.get('episodes', []))
    if episode_count < 5:
        issues.append(f"记忆库较小 ({episode_count}/5)，建议多记录使用经验")
    elif episode_count < 20:
        suggestions.append(f"记忆库正在增长 ({episode_count}/20)，继续保持")

    # 检查 2: 洞见阈值
    from ..systems.zenloop.loops.insight_loop import InsightLoop
    insight = InsightLoop()
    if hasattr(insight, '_threshold') and insight._threshold > episode_count:
        warnings.append(f"洞见循环阈值 ({insight._threshold}) 高于当前记忆数 ({episode_count})，需要更多记忆才能触发")

    # 检查 3: 反思历史文件
    reflection_files = list(zenloop_dir.glob("reflection_*.md"))
    if not reflection_files:
        issues.append("尚未生成任何反思报告，建议执行 'reflect trigger'")
    else:
        suggestions.append(f"已有 {len(reflection_files)} 份反思报告存档")

    # 检查 4: latest_reflection.md
    latest_file = zenloop_dir / "latest_reflection.md"
    if not latest_file.exists():
        warnings.append("latest_reflection.md 不存在，将在下次反思时生成")

    # 检查 5: 成功率
    success_rate = state.get('metrics', {}).get('success_rate', 0)
    if success_rate < 0.5 and state.get('usage_count', 0) > 5:
        issues.append(f"近期成功率偏低 ({success_rate:.1%})，建议简化任务或检查参数")
    elif success_rate < 0.7 and state.get('usage_count', 0) > 3:
        warnings.append(f"成功率有改进空间 ({success_rate:.1%})")

    # 检查 6: 境界进度
    level = state.get('level', 'NOVICE')
    usage = state.get('usage_count', 0)
    level_thresholds = {
        "NOVICE": 5,
        "APPRENTICE": 20,
        "ADEPT": 50,
        "EXPERT": 100,
    }
    next_level = None
    for lvl, threshold in sorted(level_thresholds.items(), key=lambda x: x[1]):
        if usage < threshold:
            next_level = lvl
            remaining = threshold - usage
            break

    if next_level:
        suggestions.append(f"距离下一境界 [{next_level}] 还需 {remaining} 次使用")

    total_issues = len(issues) + len(warnings)
    result = {
        "skill_id": args.skill_id,
        "issues": issues,
        "warnings": warnings,
        "suggestions": suggestions,
        "total_issues": total_issues,
        "episode_count": episode_count,
    }

    def _text():
        lines = ["🔍 ZenSkill 自我诊断报告", "=" * 60,
                 f"\n{'='*60}",
                 f"🔴 问题 ({len(issues)} 个):"]
        if issues:
            for issue in issues:
                lines.append(f"   - {issue}")
        else:
            lines.append(f"   ✓ 无严重问题")

        lines.append(f"\n🟡 警告 ({len(warnings)} 个):")
        if warnings:
            for warning in warnings:
                lines.append(f"   - {warning}")
        else:
            lines.append(f"   ✓ 无警告")

        lines.append(f"\n🟢 建议 ({len(suggestions)} 条):")
        if suggestions:
            for suggestion in suggestions:
                lines.append(f"   - {suggestion}")
        else:
            lines.append(f"   ✓ 系统运行良好")

        lines.append(f"\n{'='*60}")
        if total_issues == 0:
            lines.append(f"✅ 系统健康度：优秀！继续保持！")
        elif total_issues <= 2:
            lines.append(f"✅ 系统健康度：良好，可继续优化")
        else:
            lines.append(f"⚠️  系统健康度：一般，建议优先解决问题")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_reflect_consolidate(args: argparse.Namespace) -> None:
    """手动触发记忆巩固 (ConsolidationLoop)"""
    from ..core.paths import SkillStateManager
    sm = SkillStateManager(args.skill_id)
    ss = sm.load()
    episodes = ss.get("episodes", [])
    if not episodes:
        cli_output({"ok": True, "total": 0}, args, text=lambda: "📭 无记忆数据，无需巩固")
        return

    # 去重统计
    seen = set()
    dupes = 0
    for ep in episodes:
        key = (ep.get("action", ""), str(ep.get("content", ""))[:40])
        if key in seen:
            dupes += 1
        else:
            seen.add(key)

    # 高频模式提取
    from collections import Counter
    actions = Counter(e.get("action", "unknown") for e in episodes)
    top_actions = [f"{a}({c}次)" for a, c in actions.most_common(3)]

    cli_output({
        "ok": True,
        "total": len(episodes),
        "unique": len(episodes) - dupes,
        "duplicates": dupes,
        "top_actions": top_actions,
    }, args, text=lambda: (
        f"🧠 记忆巩固完成\n"
        f"   总记忆: {len(episodes)} 条\n"
        f"   去重后: {len(episodes) - dupes} 条 (重复: {dupes})\n"
        f"   高频操作: {', '.join(top_actions)}\n"
        f"   💡 建议: zenskill memory stats 查看详情"
    ))


def cmd_reflect_insight(args: argparse.Namespace) -> None:
    """手动触发洞见生成 (InsightLoop) — 基于记忆数据发现模式"""
    from ..core.paths import SkillStateManager
    sm = SkillStateManager(args.skill_id)
    ss = sm.load()
    episodes = ss.get("episodes", [])

    if len(episodes) < 5:
        cli_output({"ok": True, "episode_count": len(episodes), "threshold": 5},
                   args, text=lambda: f"📭 记忆不足 ({len(episodes)}/5)，至少需要 5 条记忆才能生成洞见")
        return

    from collections import Counter

    # 操作频率趋势（最近50条 vs 全部）
    recent = episodes[-50:]
    recent_actions = Counter(e.get("action", "unknown") for e in recent)
    all_actions = Counter(e.get("action", "unknown") for e in episodes)
    trend_data = []
    for act, cnt in recent_actions.most_common(3):
        pct = cnt / len(recent) * 100
        all_pct = all_actions.get(act, 0) / len(episodes) * 100
        trend = "↑" if pct > all_pct else "↓" if pct < all_pct else "→"
        trend_data.append({"action": act, "count": cnt, "pct": round(pct, 1),
                           "historical_pct": round(all_pct, 1), "trend": trend})

    # 标签多样性
    all_tags = []
    for e in episodes:
        tags = e.get("tags", [])
        if isinstance(tags, list):
            all_tags.extend(tags)
        elif isinstance(tags, str):
            all_tags.extend(tags.split(","))
    tag_counts = Counter(all_tags)
    top_tags = [f"{t}({c})" for t, c in tag_counts.most_common(5)]

    result = {
        "skill_id": args.skill_id,
        "episode_count": len(episodes),
        "trends": trend_data,
        "tag_diversity": len(tag_counts),
        "top_tags": top_tags,
    }

    def _text():
        lines = ["💡 记忆洞见分析", "═" * 50]
        lines.append(f"   最近50条高频操作:")
        for td in trend_data:
            lines.append(f"     {td['trend']} {td['action']}: {td['count']}次 ({td['pct']:.1f}%, 历史{td['historical_pct']:.1f}%)")
        lines.append(f"   标签多样性: {len(tag_counts)} 种")
        if tag_counts:
            lines.append(f"   Top标签: {', '.join(top_tags)}")
        lines.append(f"   💡 建议: zenskill insight generate 生成结构化洞察")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_reflect_purify(args: argparse.Namespace) -> None:
    """手动触发记忆净化 (PurificationLoop) — 清理过期/冗余记忆"""
    from ..core.paths import SkillStateManager
    import time
    sm = SkillStateManager(args.skill_id)
    ss = sm.load()
    episodes = ss.get("episodes", [])
    if not episodes:
        cli_output({"ok": True, "total": 0}, args, text=lambda: "📭 无记忆数据")
        return

    original = len(episodes)

    # 清理超过30天的旧记忆
    cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400))
    kept = [e for e in episodes if str(e.get("date", ""))[:10] >= cutoff]
    aged = original - len(kept)

    # 清理重复记忆
    seen = set()
    deduped = []
    for e in kept:
        key = (e.get("action", ""), str(e.get("content", ""))[:40])
        if key not in seen:
            seen.add(key)
            deduped.append(e)
    dupe_count = len(kept) - len(deduped)

    # 保存
    ss["episodes"] = deduped[-200:]
    sm.save(ss, action="purification", write_history=True)

    kept_count = len(deduped)
    cli_output({
        "ok": True,
        "original": original, "aged_removed": aged,
        "duplicates_removed": dupe_count, "kept": kept_count,
    }, args, text=lambda: (
        f"🧹 记忆净化完成\n"
        f"   原始: {original} 条\n"
        f"   过期清理: {aged} 条 (>30天)\n"
        f"   去重: {dupe_count} 条\n"
        f"   保留: {kept_count} 条"
    ))



def register_reflect_parser(subparsers) -> None:
    """注册 reflect 子命令组。"""
    reflect_parser = subparsers.add_parser("reflect", help="禅思反思")
    reflect_subparsers = reflect_parser.add_subparsers(dest="subcommand", help="反思操作")

    # reflect trigger
    trigger_parser = reflect_subparsers.add_parser("trigger", help="触发禅思反思")
    trigger_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    trigger_parser.add_argument("--hosted", action="store_true", help="宿主协作模式：输出 LLM 任务描述，由宿主 Claude 完成思考")
    trigger_parser.add_argument("--output", choices=["json", "text"], default="text", help="输出格式（宿主模式下）")
    trigger_parser.set_defaults(func=cmd_reflect_trigger)

    # reflect store
    store_parser = reflect_subparsers.add_parser("store", help="存储宿主完成的反思结果（从 stdin 读取 JSON）")
    store_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    store_parser.set_defaults(func=cmd_reflect_store)

    # reflect issues
    issues_parser = reflect_subparsers.add_parser("issues", help="自我诊断：扫描系统优化点")
    issues_parser.set_defaults(func=cmd_reflect_issues)

    # reflect consolidate / insight / purify (ZenLoop 手动触发)
    reflect_consolidate_parser = reflect_subparsers.add_parser("consolidate", help="手动触发记忆巩固 (ConsolidationLoop)")
    reflect_consolidate_parser.set_defaults(func=cmd_reflect_consolidate)

    reflect_insight_parser = reflect_subparsers.add_parser("insight", help="手动触发洞见生成 (InsightLoop)")
    reflect_insight_parser.set_defaults(func=cmd_reflect_insight)

    reflect_purify_parser = reflect_subparsers.add_parser("purify", help="手动触发记忆净化 (PurificationLoop)")
    reflect_purify_parser.set_defaults(func=cmd_reflect_purify)

    # perceive 命令
