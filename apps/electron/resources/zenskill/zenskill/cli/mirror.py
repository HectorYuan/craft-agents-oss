"""mirror 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

from ..cli_utils import output as cli_output

def cmd_mirror_status(args: argparse.Namespace) -> None:
    """显示用户镜像数据采集概览"""
    from ..mirroring.event_collector import EventCollector
    from ..mirroring.feature_store import FeatureStore
    from ..mirroring.privacy_layer import PrivacyLayer

    collector = EventCollector()
    store = FeatureStore()
    privacy = PrivacyLayer()

    summary = privacy.get_data_summary()
    event_count = collector.get_event_count()
    features = store.get_latest_features()

    def _text():
        lines = []
        lines.append("")
        lines.append("  🪞 用户镜像系统 — Phase 9A + 9B")
        lines.append("  ══════════════════════════════════════════════════════════════")
        lines.append("")
        lines.append("  ┌─ 📊 数据采集 ────────────────────────────────────────────")
        lines.append(f"  │  总事件数:   {event_count}")
        lines.append(f"  │  数据目录:   {summary['mirroring_dir']}")
        lines.append(f"  │  数据大小:   {summary['total_size_bytes'] / 1024:.1f} KB")
        lines.append("  └───────────────────────────────────────────────────────────")
        lines.append("")
        lines.append("  ┌─ 🔒 隐私保护 ────────────────────────────────────────────")
        consent_ok = summary['consent_given']
        encrypt_ok = summary['encryption_enabled']
        lines.append(f"  │  {'🟢' if consent_ok else '🔴'} 采集授权: {'已授权' if consent_ok else '未授权'}")
        lines.append(f"  │  {'🟢' if encrypt_ok else '🔴'} 数据加密: {'已启用' if encrypt_ok else '未启用'}")
        lines.append("  └───────────────────────────────────────────────────────────")
        lines.append("")
        lines.append("  ┌─ 📈 特征向量 ────────────────────────────────────────────")
        if features:
            lines.append(f"  │  计算时间: {datetime.fromtimestamp(features.computed_at).strftime('%Y-%m-%d %H:%M')}")
            lines.append(f"  │  会话数:   {features.session_count}")
            lines.append(f"  │  成功率:   {features.success_rate:.1%}")
            lines.append(f"  │  趋势:     {features.engagement_trend}")
        else:
            lines.append(f"  │  [dim]暂无特征数据，继续使用将自动生成[/dim]")
        lines.append("  └───────────────────────────────────────────────────────────")
        lines.append("")
        return "\n".join(lines)

    result = {"event_count": event_count, "summary": summary}
    cli_output(result, args, text=_text)


def cmd_mirror_events(args: argparse.Namespace) -> None:
    """查看最近的事件记录"""
    from ..mirroring.event_collector import EventCollector
    from ..mirroring.models import EventType

    collector = EventCollector()
    event_type = None
    if args.type:
        try:
            event_type = EventType(args.type)
        except ValueError:
            print(f"❌ 未知事件类型: {args.type}")
            print(f"   支持的类型: {', '.join(e.value for e in EventType)}")
            return

    events = collector.query(event_type=event_type, limit=args.n)

    def _text():
        lines = [f"📋 最近事件记录 (共 {len(events)} 条)", "=" * 80]
        if not events:
            lines.append("   暂无事件记录")
        else:
            for e in events:
                ts = datetime.fromtimestamp(e.timestamp).strftime("%m-%d %H:%M")
                status = "✅" if e.success else "❌"
                lines.append(f"  [{ts}] {status} {e.event_type.value:15s} | {e.skill_id:20s} | {e.action[:30]}")
        return "\n".join(lines)

    result = {"event_count": len(events), "events": [e.__dict__ if hasattr(e, '__dict__') else str(e) for e in events]}
    cli_output(result, args, text=_text)


def cmd_mirror_features(args: argparse.Namespace) -> None:
    """查看或计算用户行为特征"""
    from ..mirroring.feature_store import FeatureStore

    store = FeatureStore()

    recomputed = False
    if args.recompute:
        recomputed = True
        vector = store.compute_features()

    def _text():
        parts = []
        if recomputed:
            parts.append("🔄 正在计算特征向量...")
            parts.append("✅ 计算完成")
            parts.append("")
        parts.append(store.get_feature_summary())
        return "\n".join(parts)

    result = {"recomputed": recomputed}
    cli_output(result, args, text=_text)


def cmd_mirror_privacy(args: argparse.Namespace) -> None:
    """查看隐私设置"""
    from ..mirroring.privacy_layer import PrivacyLayer

    privacy = PrivacyLayer()
    prefs = privacy.get_prefs()

    def _text():
        lines = [
            "🔒 隐私设置",
            "=" * 60,
            f"   采集授权:     {'✅ 是' if prefs.consent_given else '❌ 否'}",
            f"   数据加密:     {'✅ 启用' if prefs.encryption_enabled else '❌ 禁用'}",
            f"   保留天数:     {prefs.retention_days} 天",
            f"   匿名化天数:   {prefs.anonymize_after_days} 天",
            f"   排除事件类型: {', '.join(prefs.excluded_event_types) if prefs.excluded_event_types else '无'}",
            f"   最后修改:     {prefs.last_modified}",
        ]
        return "\n".join(lines)

    result = {
        "consent_given": prefs.consent_given,
        "encryption_enabled": prefs.encryption_enabled,
        "retention_days": prefs.retention_days,
        "anonymize_after_days": prefs.anonymize_after_days,
        "excluded_event_types": prefs.excluded_event_types,
        "last_modified": str(prefs.last_modified),
    }
    cli_output(result, args, text=_text)


def cmd_mirror_privacy_set(args: argparse.Namespace) -> None:
    """更新隐私设置"""
    from ..mirroring.privacy_layer import PrivacyLayer

    privacy = PrivacyLayer()
    try:
        privacy.update_prefs(**{args.key: args.value})
        result = {"key": args.key, "value": args.value, "success": True}
        cli_output(result, args, text=lambda: f"✅ 已更新 {args.key} = {args.value}")
    except Exception as e:
        result = {"key": args.key, "value": args.value, "success": False, "error": str(e)}
        cli_output(result, args, text=lambda: f"❌ 更新失败: {e}")


def cmd_mirror_export(args: argparse.Namespace) -> None:
    """导出所有镜像数据 (GDPR)"""
    from pathlib import Path
    from ..mirroring.privacy_layer import PrivacyLayer

    privacy = PrivacyLayer()
    output = Path(args.output)
    count = privacy.export_all_data(output)
    result = {"exported_count": count, "output": str(output)}
    cli_output(result, args, text=lambda: f"✅ 已导出 {count} 个文件到 {output}")


def cmd_mirror_delete_all(args: argparse.Namespace) -> None:
    """删除所有镜像数据 (GDPR)"""
    from ..mirroring.privacy_layer import PrivacyLayer

    confirm = input("⚠️  确认删除所有镜像数据？(输入 yes 确认): ")
    if confirm.strip().lower() != "yes":
        print("已取消")
        return

    privacy = PrivacyLayer()
    count = privacy.delete_all_data()
    result = {"deleted_count": count}
    cli_output(result, args, text=lambda: f"✅ 已删除 {count} 个文件")


def cmd_mirror_purge(args: argparse.Namespace) -> None:
    """清理过期事件并匿名化旧数据"""
    from ..mirroring.event_collector import EventCollector
    from ..mirroring.privacy_layer import PrivacyLayer

    collector = EventCollector()
    privacy = PrivacyLayer()

    purged = collector.purge_old_events()
    anonymized = privacy.anonymize_old_data()

    result = {"purged": purged, "anonymized": anonymized}
    cli_output(result, args, text=lambda: f"🧹 清理完成\n   清理事件: {purged} 条\n   匿名化:   {anonymized} 条")


def cmd_mirror_scan(args: argparse.Namespace) -> None:
    """扫描并索引当前环境 (Claude Code + 项目)"""
    from pathlib import Path

    from ..mirroring.environment_indexer import EnvironmentIndexer

    indexer = EnvironmentIndexer()
    result = indexer.scan_all()
    stack = result["project_stack"]
    git = result["git_profile"]
    skills = result["skills"]

    def _text():
        lines = []
        lines.append("")
        lines.append(f"  🔍 环境扫描: {Path.cwd().name}")
        lines.append(f"  ══════════════════════════════════════════════════════════════")
        lines.append("")
        lines.append("  ┌─ 📦 项目技术栈 ──────────────────────────────────────────")
        lines.append(f"  │  语言:      {', '.join(stack['languages']) or '未检测到'}")
        lines.append(f"  │  包管理器:  {', '.join(stack['package_managers']) or '-'}")
        lines.append(f"  │  框架:      {', '.join(stack['frameworks']) or '-'}")
        lines.append(f"  │  工具:      {', '.join(stack['tools']) or '-'}")
        lines.append("  └───────────────────────────────────────────────────────────")
        lines.append("")
        lines.append("  ┌─ 🌿 Git 画像 ────────────────────────────────────────────")
        if git["has_git"]:
            lines.append(f"  │  用户:      {git['user_name'] or '未设置'} <{git['user_email'] or ''}>")
            lines.append(f"  │  最近提交:  {len(git['recent_commits'])} 条")
            if git["commit_pattern"]:
                cp = git["commit_pattern"]
                active = cp.get("most_active_hour", "-")
                lines.append(f"  │  活跃峰值:  {active}:00 左右")
        else:
            lines.append(f"  │  [dim]非 Git 仓库[/dim]")
        lines.append("  └───────────────────────────────────────────────────────────")
        lines.append("")
        lines.append("  ┌─ 🧠 Claude Code ──────────────────────────────────────────")
        lines.append(f"  │  已装技能:  {len(skills['installed'])} 个")
        for s in skills["installed"][:5]:
            lines.append(f"  │    • {s['name']}")
        lines.append("  └───────────────────────────────────────────────────────────")
        lines.append("")
        lines.append(f"  🟢 扫描完成 — 数据已自动记录到镜像系统")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_mirror_profile(args: argparse.Namespace) -> None:
    """查看用户画像 (Phase 9B)"""
    from pathlib import Path

    from ..mirroring.environment_indexer import EnvironmentIndexer
    from ..mirroring.feature_store import FeatureStore
    from ..mirroring.preference_engine import PreferenceEngine

    # 环境画像
    indexer = EnvironmentIndexer()
    summary = indexer.get_work_pattern_summary()

    # 行为特征
    store = FeatureStore()
    features = store.get_latest_features()

    # 学习到的偏好
    engine = PreferenceEngine()
    profile = engine.get_profile_summary()
    prefs = profile["all_preferences"]
    high_conf = profile["high_confidence_preferences"]

    def _text():
        lines = []
        lines.append("")
        lines.append(f"  👤 用户画像 — Phase 9B")
        lines.append(f"  ══════════════════════════════════════════════════════════════")
        lines.append("")
        lines.append("  ┌─ 📦 工作环境 ────────────────────────────────────────────")
        lines.append(f"  │  主要语言:  {', '.join(summary['primary_languages']) or '-'}")
        lines.append(f"  │  使用工具:  {', '.join(summary['tools']) or '-'}")
        lines.append(f"  │  已装技能:  {', '.join(summary['installed_skills']) or '-'}")
        lines.append("  └───────────────────────────────────────────────────────────")
        lines.append("")
        lines.append("  ┌─ 📊 行为特征 ────────────────────────────────────────────")
        if features and features.skill_usage:
            usage = features.skill_usage
            most_used = max(usage.items(), key=lambda x: x[1]) if usage else ("-", 0)
            lines.append(f"  │  最常用技能:  {most_used[0]} ({most_used[1]} 次)")
            lines.append(f"  │  总交互次数:  {sum(usage.values())}")
        else:
            lines.append(f"  │  [dim]数据积累中...[/dim]")
        lines.append("  └───────────────────────────────────────────────────────────")
        # 活跃时段
        hours = summary["active_hours"]
        if hours:
            lines.append("")
            lines.append("  ┌─ ⏰ 工作模式 ────────────────────────────────────────────")
            total = sum(hours.values())
            if total:
                periods = [
                    ("上午 (6-12)", hours.get("morning_commits", 0)),
                    ("下午 (12-18)", hours.get("afternoon_commits", 0)),
                    ("晚上 (18-24)", hours.get("evening_commits", 0)),
                    ("深夜 (0-6)", hours.get("night_commits", 0)),
                ]
                max_n = max(c for _, c in periods) or 1
                for label, count in periods:
                    bar_len = int(count / max_n * 16) if max_n else 0
                    bar = "█" * bar_len + "·" * (16 - bar_len)
                    lines.append(f"  │  {label:14s} {bar} {count}")
            lines.append("  └───────────────────────────────────────────────────────────")
        # 学习到的偏好
        lines.append("")
        strength_icon = {"strong": "🟢", "developing": "🟡", "initial": "🔵"}
        strength = profile["profile_strength"]
        lines.append(f"  ┌─ 🎯 学习偏好 (强度: {strength_icon.get(strength, '⚪')} {strength}) ──────")
        STYLE_NAMES = {
            "work_pace": "工作节奏", "tool_preference": "工具偏好",
            "code_style": "代码风格", "learning_style": "学习风格",
            "communication_style": "沟通风格", "explanation_depth": "解释深度",
            "decision_style": "决策风格", "risk_tolerance": "风险偏好",
        }
        VALUE_NAMES = {
            "fast": "快速", "steady": "稳健", "thorough": "严谨",
            "automation": "自动化优先", "careful": "谨慎操作", "pragmatic": "实用主义",
            "learning_by_doing": "实践驱动", "theory_first": "理论优先",
            "detailed": "注重细节", "moderate": "适中", "systematic": "系统性",
            "conservative": "保守",
        }
        for key, data in prefs.items():
            name = STYLE_NAMES.get(key, key)
            value_raw = data.get("value", "?")
            value = VALUE_NAMES.get(value_raw, value_raw)
            conf = data.get("confidence", 0)
            count = data.get("evidence_count", 0)
            bar = "█" * int(conf * 10) + "░" * int((1 - conf) * 10)
            conf_icon = "🟢" if conf > 0.7 else "🟡" if conf > 0.4 else "🔵"
            info = f"({count}证据)" if count > 0 else "(校准中)"
            lines.append(f"  │  {conf_icon} {name:8s} {value:10s}  {bar}  {conf:.0%} {info}")
        lines.append("  └───────────────────────────────────────────────────────────")
        if high_conf:
            lines.append("")
            lines.append("  ┌─ ✅ 高置信度洞察 ────────────────────────────────────────")
            icons = ["🔹", "🔸", "🔹", "🔸"]
            for i, (key, value) in enumerate(high_conf.items()):
                name = STYLE_NAMES.get(key, key)
                value_named = VALUE_NAMES.get(value, value)
                lines.append(f"  │  {icons[i % len(icons)]} {name}: {value_named}")
            lines.append("  └───────────────────────────────────────────────────────────")
        # 采集管道分析（自动缓存，每 5 分钟刷新）
        lines.append("")
        lines.append(f"  ┌─ 🧠 智能分析 ────────────────────────────────────────────")
        try:
            import json, time
            from datetime import datetime
            cache_file = Path.home() / ".zenskill" / "mirroring" / "pipeline.json"
            pipeline = None
            if cache_file.exists():
                try:
                    pipeline = json.loads(cache_file.read_text())
                except Exception:
                    pass
            if pipeline and pipeline.get("nlp"):
                nlp_result = pipeline["nlp"]
                insights = pipeline.get("insights", [])
                domains = nlp_result.get("domains", {})
                if domains:
                    top = sorted(domains.items(), key=lambda x: x[1], reverse=True)[:4]
                    d_str = "  ".join(f"{d} {'█' * int(s / 10)}{int(s)}%" for d, s in top)
                    lines.append(f"  │  🏷  {d_str}")
                intents = nlp_result.get("intents", {})
                if intents:
                    i_str = "  ".join(f"{k} {'█' * v}{v}" for k, v in
                                     sorted(intents.items(), key=lambda x: x[1], reverse=True))
                    lines.append(f"  │  🎯 {i_str}")
                keywords = nlp_result.get("top_keywords", [])
                if keywords:
                    lines.append(f"  │  🔑 {'  '.join(f'`{k}`' for k in keywords[:8])}")
                if insights:
                    icons = ["🔹", "🔸"]
                    for i, ins in enumerate(insights[:4]):
                        lines.append(f"  │  {icons[i % 2]} {ins}")
                ts = pipeline.get("timestamp", 0)
                if ts:
                    ago = int(time.time() - ts)
                    ago_str = f"{ago}s" if ago < 60 else f"{ago // 60}m" if ago < 3600 else f"{ago // 3600}h"
                    lines.append(f"  │  [dim]缓存: {ago_str}前 | 共 {pipeline.get('event_count', 0)} 条事件[/dim]")
            else:
                lines.append(f"  │  [dim]智能分析数据收集中... (Hook 自动刷新, 5 分钟冷却)[/dim]")
        except Exception:
            lines.append(f"  │  [dim]智能分析模块不可用[/dim]")
        lines.append(f"  └───────────────────────────────────────────────────────────")
        lines.append("")
        lines.append(f"  💡 平均置信度 {profile['average_confidence']:.0%} — "
                      f"继续使用画像会越来越准确")
        lines.append("")
        # ZenThink Profile 集成
        try:
            from ..profile_reader import ProfileReader
            pr = ProfileReader()
            if pr.available:
                lines.append("🧘 ZenThink 知识库")
                lines.append("━" * 40)
                pr_summary = pr.get_summary()
                lines.append(f"   {pr_summary}")
                soul = pr.read_soul()
                if soul.get("cultivation"):
                    lines.append("   修炼体系:")
                    for s in soul["cultivation"][:3]:
                        lines.append(f"     {s['rank']}·{s['name']} ({s['title']}) — {s['threshold']}次")
                lines.append("")
        except Exception:
            pass
        return "\n".join(lines)

    result = {"profile": profile}
    cli_output(result, args, text=_text)


def cmd_mirror_sync_skills(args: argparse.Namespace) -> None:
    """同步 Claude Code 已安装的技能到 ZenSkill"""
    from ..mirroring.environment_indexer import EnvironmentIndexer

    indexer = EnvironmentIndexer()
    result = indexer.sync_claude_skills_to_zenskill()

    def _text():
        lines = []
        lines.append(f"🔄 正在同步 Claude Code 技能到 ZenSkill...")
        lines.append("")
        lines.append(f"✅ 同步完成！")
        lines.append(f"   已同步技能: {len(result['synchronized'])} 个")
        lines.append(f"   累计事件: {result['total_usage_events']} 条")
        lines.append("")
        if result["synchronized"]:
            lines.append(f"📋 已安装技能:")
            for s in result["synchronized"]:
                caps = ", ".join(s["capabilities"])
                lines.append(f"   - {s['name']} ({s['usage_count']} 次使用) [{caps}]")
        lines.append("")
        if result["tool_breakdown"]:
            lines.append(f"🔧 工具使用分布:")
            for tool, count in result["tool_breakdown"].items():
                lines.append(f"   - {tool}: {count} 次")
        lines.append("")
        lines.append(f"💡 提示: 数据已同步到用户镜像系统")
        lines.append(f"   可使用 'zenskill mirror profile' 查看完整画像")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_mirror_learn(args: argparse.Namespace) -> None:
    """从行为数据学习用户偏好 (Phase 9B)"""
    from ..mirroring.preference_engine import PreferenceEngine

    engine = PreferenceEngine()
    result = engine.learn_from_behavior()
    prefs = result["preferences"]
    signals = result["signals"]
    tp = signals["tool_patterns"]

    def _text():
        lines = []
        lines.append("")
        lines.append(f"  🧠 偏好学习引擎 — Phase 9B")
        lines.append(f"  ══════════════════════════════════════════════════════════════")
        lines.append("")
        lines.append(f"  ┌─ 📊 行为信号 ────────────────────────────────────────────")
        lines.append(f"  │  事件总数:    {tp['total_events']}")
        lines.append(f"  │  工作节奏:    {tp['work_pace']}")
        lines.append(f"  │  工具风格:    {tp['tool_style']}")
        lines.append(f"  │  编辑/阅读:   {tp['edit_ratio']:.0%} / {tp['read_ratio']:.0%}")
        lines.append(f"  └───────────────────────────────────────────────────────────")
        lines.append("")
        lines.append(f"  ┌─ 🎯 学习偏好 ────────────────────────────────────────────")
        STYLE_NAMES = {
            "work_pace": "工作节奏", "tool_preference": "工具偏好",
            "code_style": "代码风格", "learning_style": "学习风格",
            "communication_style": "沟通风格", "explanation_depth": "解释深度",
            "decision_style": "决策风格", "risk_tolerance": "风险偏好",
        }
        for key, data in prefs.items():
            name = STYLE_NAMES.get(key, key)
            value = data.get("value", "?")
            conf = data.get("confidence", 0)
            count = data.get("evidence_count", 0)
            bar = "█" * int(conf * 10) + "░" * int((1 - conf) * 10)
            conf_icon = "🟢" if conf > 0.7 else "🟡" if conf > 0.4 else "🔵"
            lines.append(f"  │  {conf_icon} {name:8s} {value:12s}  {bar}  {conf:.0%} ({count}证据)")
        lines.append(f"  └───────────────────────────────────────────────────────────")
        lines.append("")
        lines.append(f"  💡 每个工具使用事件都将强化你的偏好画像")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_mirror_workflow(args: argparse.Namespace) -> None:
    """工作流模式分析 (Phase 9D)"""
    from ..cli_utils import section_blank, box_header, box_footer, bar_chart
    from ..mirroring.workflow import WorkflowAnalyzer

    analyzer = WorkflowAnalyzer()
    result = analyzer.analyze()

    def _text():
        lines = []
        section_blank("工作流模式分析", "🔄", phase="9D")
        # 工具链
        chains = result.get("tool_chains", {})
        box_header("工具序列链", "🔗")
        top = chains.get("top_chain", "none")
        trans = chains.get("top_transitions", [])
        if trans:
            lines.append(f"  │  主导链: {top}")
            lines.append(f"  │  常见转换:")
            for t in trans[:5]:
                lines.append(f"  │    {t['from']:8s} → {t['to']:8s}  ({t['count']} 次)")
        else:
            lines.append(f"  │  [dim]数据积累中...[/dim]")
        box_footer()
        # 工作时段分布
        segments = result.get("work_segments", {})
        if segments:
            lines.append("")
            box_header("工作时段", "⏰")
            max_n = max(s.get("count", 1) for s in segments.values()) or 1
            for seg, info in segments.items():
                b = bar_chart(info["count"], max_n, 20)
                lines.append(f"  │  {seg:10s} {b} {info['pct']:.0f}%  ({info['top_project']})")
            box_footer()
        # 深度工作
        deep = result.get("deep_work", {})
        if deep.get("total_sessions", 0) > 0:
            lines.append("")
            box_header("深度工作", "🧘")
            lines.append(f"  │  深度时段: {deep.get('deep_sessions', 0)} 个")
            lines.append(f"  │  深度时长: {deep.get('total_deep_minutes', 0):.0f} 分钟")
            lines.append(f"  │  深度占比: {deep.get('deep_work_ratio', 0)}% ({deep.get('total_sessions', 0)} 总会话)")
            box_footer()
        # 项目节奏
        rhythm = result.get("project_rhythm", {})
        if rhythm.get("unique_projects", 0) > 0:
            lines.append("")
            box_header("项目切换", "📂")
            style = rhythm.get("style", "balanced")
            style_label = {"focus": "🟢 专注型", "balanced": "🟡 均衡型", "multitask": "🔴 多任务型"}
            lines.append(f"  │  风格:     {style_label.get(style, style)}")
            lines.append(f"  │  切换次数: {rhythm.get('total_switches', 0)}")
            lines.append(f"  │  项目数:   {rhythm.get('unique_projects', 0)}")
            top_proj = rhythm.get("top_projects", {})
            if top_proj:
                lines.append(f"  │  主要项目:")
                for proj, count in top_proj.items():
                    lines.append(f"  │    • {proj}: {count}")
            box_footer()
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


# ================================================================
# 9D: 工作流模式识别 — 独立命令组
# ================================================================

def cmd_mirror_predict(args: argparse.Namespace) -> None:
    """预测性辅助引擎 — 基于模式数据预判下一步行动 (9E)"""
    from ..cli_utils import section_blank, box_header, box_footer, bar_chart
    from ..mirroring.pattern_miner import StatisticalPatternMiner
    from ..mirroring.context_predictor import (
        ContextPredictor, AnomalyDetector, _read_session_cache,
        _detect_project_from_cwd,
    )
    from ..mirroring.gap_detector import GapDetector

    miner = StatisticalPatternMiner()
    profile = miner.mine()
    predictor = ContextPredictor(profile)
    detector = AnomalyDetector(profile)
    gap = GapDetector()

    # 使用改进后的实时上下文（自动从会话缓存 + cwd 填充数据）
    predictions = predictor.predict()  # 自动调用 _current_context()
    ctx = predictor._current_context()
    anomalies = detector.detect(ctx)
    gaps = gap.detect_all()

    def _text():
        lines = []
        section_blank("预测性辅助引擎", "🔮", phase="9E")
        # 下一步行动预测
        box_header("下一步行动预测", "🎯")
        if predictions:
            for i, p in enumerate(predictions[:3]):
                icons = ["🥇", "🥈", "🥉"]
                conf_bar = bar_chart(p["confidence"] * 100, 100, 10)
                lines.append(f"  │  {icons[i]} {p['action']:10s} {conf_bar} {p['confidence']:.0%}")
                lines.append(f"  │      {p['explanation']}")
        else:
            lines.append(f"  │  [dim]数据积累中，还需要更多交互来学习你的模式[/dim]")
        box_footer()
        # 转移矩阵预览
        matrix = profile.transition_matrix
        if matrix:
            lines.append("")
            box_header("行为转移矩阵", "🔗")
            for tool, row in sorted(matrix.items()):
                top = sorted(row.items(), key=lambda x: x[1], reverse=True)[:2]
                parts = [f"{t}({p:.0%})" for t, p in top]
                lines.append(f"  │  {tool:10s} → {'  '.join(parts)}")
            box_footer()
        # 异常检测
        if anomalies:
            lines.append("")
            box_header("异常检测", "⚠️")
            for a in anomalies:
                sev = {"high": "🔴", "medium": "🟡", "low": "🔵"}.get(a["severity"], "⚪")
                lines.append(f"  │  {sev} {a['message']}")
            box_footer()
        # 7E: 目标建议 (从 pipeline 自动生成)
        from ..integration import suggest_goals_from_pipeline
        goal_suggestions = suggest_goals_from_pipeline()
        if goal_suggestions:
            lines.append("")
            box_header("智能目标建议", "🎯")
            for g in goal_suggestions:
                lines.append(f"  │  🎯 {g['title']}")
                lines.append(f"  │     {g['description']}")
                lines.append(f"  │     [dim]{g['reason']}[/dim]")
            box_footer()
        # 需求缺口
        all_gaps = (
            gaps.get("skill_gaps", []) +
            gaps.get("knowledge_gaps", []) +
            gaps.get("tool_gaps", [])
        )
        if all_gaps:
            lines.append("")
            box_header("需求缺口", "🕳️")
            for g in all_gaps[:5]:
                label = g.get("message") or g.get("tool") or g.get("suggestion", "")
                lines.append(f"  │  🔹 {label}")
            box_footer()
        lines.append("")
        return "\n".join(lines)

    result = {"predictions": predictions, "anomalies": anomalies}
    cli_output(result, args, text=_text)


def cmd_mirror_tips(args: argparse.Namespace) -> None:
    """轻量建议 + 会话摘要 — 适合 Stop hook 输出 (9E)"""
    from ..mirroring.pattern_miner import StatisticalPatternMiner
    from ..mirroring.context_predictor import (
        ContextPredictor, _read_session_cache,
    )
    from ..mirroring.gap_detector import GapDetector
    import json, time
    from datetime import datetime
    from pathlib import Path

    # ── 会话摘要（使用改进的缓存读取函数） ──
    session_state = _read_session_cache()
    session_info = ""
    if session_state:
        tc = session_state.get("tool_count", 0)
        started = session_state.get("started", 0)
        elapsed = (time.time() - started) / 60 if started else 0
        tools = session_state.get("recent_tools", [])
        session_info = f"🛑 会话结束 | {tc} tools in {elapsed:.0f} min"
        if tools:
            from collections import Counter
            tc_count = Counter(tools)
            top_tools = ", ".join(f"{t}({c})" for t, c in tc_count.most_common(3))
            session_info += f" | 主要: {top_tools}"

    # ── 预测 + 缺口（使用改进的自动上下文构建） ──
    miner = StatisticalPatternMiner()
    profile = miner.mine()
    predictor = ContextPredictor(profile)
    gap = GapDetector()
    ctx = predictor._current_context()
    predictions = predictor.predict(ctx)
    peak_hours = profile.peak_hours
    gaps = gap.detect_all()

    def _text():
        lines = []
        lines.append("")
        if session_info:
            lines.append(f"  {session_info}")
        for p in predictions[:1]:
            lines.append(f"  💡 建议: {p['action']} ({p['confidence']:.0%})")
        active = datetime.now().hour in peak_hours
        if active:
            lines.append(f"  ⏰ 活跃时段, 通常 {profile.session_rhythm.get('avg_duration_min', 0):.0f}min/会话")
        else:
            lines.append(f"  🌙 非常规时段, 峰值 {', '.join(f'{h}:00' for h in peak_hours[:2])}")
        for g in gaps.get("skill_gaps", [])[:1]:
            lines.append(f"  📈 缺口: {g.get('domain', '')} ({g.get('score', 0):.0f}%) — {g.get('suggestion', '')[:60]}")
        lines.append("")
        return "\n".join(lines)

    result = {"session_info": session_info, "predictions": predictions[:1]}
    cli_output(result, args, text=_text)


def cmd_mirror_sync_global(args: argparse.Namespace) -> None:
    """与全局偏好同步 (9B-3)"""
    from ..mirroring.preference_engine import PreferenceEngine

    engine = PreferenceEngine()
    stats = engine.sync_with_global()
    profile = engine.get_profile_summary()

    def _text():
        lines = []
        lines.append(f"🔄 正在与全局偏好同步...")
        lines.append("")
        lines.append(f"✅ 同步完成！")
        lines.append(f"   合并更新: {len(stats['merged'])} 项")
        lines.append(f"   本地胜出: {len(stats['local_kept'])} 项")
        lines.append(f"   全局胜出: {len(stats['global_kept'])} 项")
        lines.append("")
        lines.append(f"📊 同步后画像强度: {profile['profile_strength']}")
        lines.append(f"   平均置信度: {profile['average_confidence']:.0%}")
        lines.append("")
        lines.append(f"💡 提示: 偏好已在所有项目间共享")
        lines.append(f"   运行 'zenskill mirror profile' 查看完整偏好")
        return "\n".join(lines)

    cli_output(stats, args, text=_text)


def cmd_mirror_export(args: argparse.Namespace) -> None:
    """导出偏好文件"""
    from ..mirroring.preference_engine import PreferenceEngine

    engine = PreferenceEngine()
    success = engine.export_preferences(args.output)

    result = {"success": success, "output": args.output}
    if success:
        cli_output(result, args, text=lambda: f"✅ 偏好已导出到: {args.output}")
    else:
        cli_output(result, args, text=lambda: f"❌ 导出失败")


def cmd_mirror_import(args: argparse.Namespace) -> None:
    """导入偏好文件"""
    from ..mirroring.preference_engine import PreferenceEngine

    engine = PreferenceEngine()
    merge = not args.no_merge
    success = engine.import_preferences(args.input, merge=merge)

    result = {"success": success, "input": args.input, "merge": merge}
    if success:
        mode = "合并" if merge else "覆盖"
        cli_output(result, args, text=lambda: f"✅ 偏好已{mode}导入")
    else:
        cli_output(result, args, text=lambda: f"❌ 导入失败")



def register_mirror_parser(subparsers) -> None:
    """注册 mirror 子命令组。"""
    mirror_parser = subparsers.add_parser("mirror", help="用户镜像系统（Phase 9A）")
    mirror_subparsers = mirror_parser.add_subparsers(dest="subcommand", help="镜像操作")

    # mirror status
    mirror_status_parser = mirror_subparsers.add_parser("status", help="数据采集概览")
    mirror_status_parser.set_defaults(func=cmd_mirror_status)

    # mirror events
    mirror_events_parser = mirror_subparsers.add_parser("events", help="查看最近事件")
    mirror_events_parser.add_argument("--n", type=int, default=20, help="显示条数")
    mirror_events_parser.add_argument("--type", help="事件类型过滤")
    mirror_events_parser.set_defaults(func=cmd_mirror_events)

    # mirror features
    mirror_features_parser = mirror_subparsers.add_parser("features", help="查看特征向量")
    mirror_features_parser.add_argument("--recompute", action="store_true", help="重新计算特征")
    mirror_features_parser.set_defaults(func=cmd_mirror_features)

    # mirror privacy
    mirror_privacy_parser = mirror_subparsers.add_parser("privacy", help="查看隐私设置")
    mirror_privacy_parser.set_defaults(func=cmd_mirror_privacy)

    # mirror privacy set
    mirror_privacy_set_parser = mirror_subparsers.add_parser("privacy-set", help="更新隐私设置")
    mirror_privacy_set_parser.add_argument("key", help="设置项名称")
    mirror_privacy_set_parser.add_argument("value", help="设置值")
    mirror_privacy_set_parser.set_defaults(func=cmd_mirror_privacy_set)

    # mirror export
    mirror_export_parser = mirror_subparsers.add_parser("export", help="导出所有镜像数据")
    mirror_export_parser.add_argument("output", help="输出文件路径")
    mirror_export_parser.set_defaults(func=cmd_mirror_export)

    # mirror delete-all
    mirror_delete_parser = mirror_subparsers.add_parser("delete-all", help="删除所有镜像数据")
    mirror_delete_parser.set_defaults(func=cmd_mirror_delete_all)

    # mirror purge
    mirror_purge_parser = mirror_subparsers.add_parser("purge", help="清理过期事件")
    mirror_purge_parser.set_defaults(func=cmd_mirror_purge)

    # mirror scan
    mirror_scan_parser = mirror_subparsers.add_parser("scan", help="扫描并索引当前环境")
    mirror_scan_parser.set_defaults(func=cmd_mirror_scan)

    # mirror profile (9B: 用户画像)
    mirror_profile_parser = mirror_subparsers.add_parser("profile", help="查看用户画像")
    mirror_profile_parser.set_defaults(func=cmd_mirror_profile)

    # mirror sync-skills
    mirror_sync_parser = mirror_subparsers.add_parser("sync-skills", help="同步 Claude Code 技能到 ZenSkill")
    mirror_sync_parser.set_defaults(func=cmd_mirror_sync_skills)

    # mirror learn (9B: 偏好学习)
    mirror_learn_parser = mirror_subparsers.add_parser("learn", help="从行为数据学习用户偏好")
    mirror_learn_parser.set_defaults(func=cmd_mirror_learn)

    # mirror workflow (9D: 工作流模式识别)
    mirror_workflow_parser = mirror_subparsers.add_parser("workflow", help="工作流模式分析（Phase 9D）")
    mirror_workflow_parser.set_defaults(func=cmd_mirror_workflow)

    # mirror predict (9E: 预测性辅助引擎)
    mirror_predict_parser = mirror_subparsers.add_parser("predict", help="预测下一步行动（Phase 9E）")
    mirror_predict_parser.set_defaults(func=cmd_mirror_predict)

    # mirror tips (9E: 轻量建议)
    mirror_tips_parser = mirror_subparsers.add_parser("tips", help="轻量智能建议（适合 Hook）")
    mirror_tips_parser.set_defaults(func=cmd_mirror_tips)

    # mirror sync-global (9B-3: 跨项目同步)
    mirror_sync_global_parser = mirror_subparsers.add_parser("sync-global", help="与全局偏好同步")
    mirror_sync_global_parser.set_defaults(func=cmd_mirror_sync_global)

    # mirror export-prefs / import-prefs
    mirror_export_prefs_parser = mirror_subparsers.add_parser("export-prefs", help="导出偏好文件")
    mirror_export_prefs_parser.add_argument("output", help="输出文件路径")
    mirror_export_prefs_parser.set_defaults(func=cmd_mirror_export)

    mirror_import_prefs_parser = mirror_subparsers.add_parser("import-prefs", help="导入偏好文件")
    mirror_import_prefs_parser.add_argument("input", help="输入文件路径")
    mirror_import_prefs_parser.add_argument("--no-merge", action="store_true", help="不合并，直接覆盖")
    mirror_import_prefs_parser.set_defaults(func=cmd_mirror_import)

    # ── 9D: 工作流模式识别命令组 ──
    from .workflow import register_workflow_parser
    register_workflow_parser(subparsers)
