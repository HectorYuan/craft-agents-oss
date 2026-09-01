"""growth 命令组（从 __main__.py 提取）。

包含：growth status/trend/milestones/abilities/accelerate/predict/ceremony/
      insight/export/report/compare/replay/errors/feedback/dimensions/habits/
      achievements
"""
from __future__ import annotations

import argparse

from ..cli_utils import output as cli_output

from ..core.paths import SkillStateManager

def cmd_growth_status(args: argparse.Namespace) -> None:
    """显示成长状态 - 五维能力雷达图（growth 默认命令"""
    # 从状态重建 SkillManifest
    mgr = SkillStateManager(args.skill_id)
    state = mgr.load()

    from zenskill.systems.cultivating.skill_manifest import (
        SkillManifest,
        SkillLevel,
        SkillStat,
    )

    # 重建 manifest
    manifest = SkillManifest(
        skill_id=args.skill_id,
        skill_name=state.get('skill_name', 'ZenSkill 核心引擎'),
    )
    manifest.current_level = SkillLevel[state.get('level', 'NOVICE')]
    manifest.stats.total_interactions = state.get('usage_count', 0)
    manifest.stats.successful_executions = state.get('metrics', {}).get('successful_executions', 0)
    manifest.stats.user_feedback_score = state.get('metrics', {}).get('user_feedback_score', 0.8)
    manifest.stats.memory_usage_count = len(state.get('episodes', []))
    manifest.stats.average_response_time_ms = state.get('metrics', {}).get('avg_duration_ms', 500)

    # 计算境界进度（state 中不保存，动态计算）
    manifest._update_level_progress()

    scores = manifest.get_ability_scores()
    result = {
        "skill_id": args.skill_id,
        "level": state.get('level', 'NOVICE'),
        "usage_count": state.get('usage_count', 0),
        "ability_scores": {
            "proficiency": scores.proficiency,
            "stability": scores.stability,
            "satisfaction": scores.satisfaction,
            "responsiveness": scores.responsiveness,
            "memory": scores.memory,
        },
        "composite": scores.composite,
        "level_progress": manifest.level_progress,
    }

    # --watch 轮询模式
    if getattr(args, 'watch', False):
        from ..cli_utils import watch_loop
        print(f"🔍 监控 {args.skill_id} (每 5s 刷新，Ctrl+C 停止)")

        def _poll():
            # ANSI 清屏替代 os.system("clear")，无子进程无注入面
            print("\033[2J\033[H", end="")
            _mgr = SkillStateManager(args.skill_id)
            _state = _mgr.load()
            _manifest = SkillManifest(
                skill_id=args.skill_id,
                skill_name=_state.get('skill_name', 'ZenSkill 核心引擎'),
            )
            _manifest.current_level = SkillLevel[_state.get('level', 'NOVICE')]
            _manifest.stats.total_interactions = _state.get('usage_count', 0)
            _manifest.stats.successful_executions = _state.get('metrics', {}).get('successful_executions', 0)
            _manifest._update_level_progress()
            print(_manifest.get_full_status_summary())

        watch_loop(_poll, interval=5.0)
        return

    # --dimension 指定时聚焦单维度
    dimension = getattr(args, 'dimension', None)
    if dimension and dimension != "composite":
        dim_names = {"proficiency": "熟练度", "stability": "稳定性",
                     "satisfaction": "满意度", "responsiveness": "响应力", "memory": "记忆度"}
        dim_val = getattr(scores, dimension, 0)
        dim_name = dim_names.get(dimension, dimension)

        def _dim_text():
            base = manifest.get_full_status_summary()
            bar_len = int(dim_val / 100 * 30)
            bar = "█" * bar_len + "░" * (30 - bar_len)
            return (
                f"{base}\n"
                f"  ┌─ 🎯 聚焦维度: {dim_name} ───────────────────────────\n"
                f"  │  [{bar}] {dim_val}/100\n"
                f"  └───────────────────────────────────────────────────────────"
            )

        cli_output(result, args, text=_dim_text)
    else:
        cli_output(result, args, text=manifest.get_full_status_summary)


def cmd_default_overview(args: argparse.Namespace) -> None:
    """默认概览命令 - 显示成长状态 + 洞察摘要"""
    # 先显示五维能力雷达
    cmd_growth_status(args)

    # 如果有数据，追加洞察摘要
    from zenskill.systems.visualization.insight_engine import GrowthInsightEngine

    engine = GrowthInsightEngine(args.skill_id)
    snapshots = engine.metrics_store.get_all_snapshots()

    if len(snapshots) >= 2:
        latest = snapshots[-1]
        composite = latest.ability_scores.get('composite', 0)
        result = {
            "snapshot_count": len(snapshots),
            "composite_score": composite,
            "skill_id": args.skill_id,
        }
        cli_output(result, args, text=lambda: (
            f"\n💡 快速洞察:\n"
            f"   📊 综合能力: {composite} 分\n"
            f"   📈 历史采样: {len(snapshots)} 个采样点\n"
            f"   💡 使用 'growth insight' 查看完整洞察报告"
        ))


def cmd_growth_trend(args: argparse.Namespace) -> None:
    """显示成长趋势图"""
    from zenskill.systems.visualization.metrics_store import MetricsStore
    from zenskill.systems.visualization.charts import ASCIICharts

    # 使用 MetricsStore 获取历史数据
    store = MetricsStore(args.skill_id)
    snapshots = store.get_all_snapshots()

    if not snapshots:
        result = {"skill_id": args.skill_id, "snapshot_count": 0, "dimensions": {}}
        cli_output(result, args, text=lambda: (
            "📊 成长趋势\n"
            "=" * 50 + "\n\n"
            "   暂无历史数据，每 5 次交互记录一次采样点\n\n"
            "💡 继续使用 ZenSkill 积累更多成长数据！"
        ))
        return

    # 构建结构化数据
    dim_names = {
        "composite": "综合能力", "proficiency": "熟练度", "stability": "稳定性",
        "satisfaction": "满意度", "responsiveness": "响应力", "memory": "记忆力",
    }
    dimensions_data = {}
    for dim in dim_names:
        values = [s.ability_scores.get(dim, 0) for s in snapshots]
        if values:
            dimensions_data[dim] = {
                "name": dim_names[dim],
                "values": values,
                "current": values[-1],
                "min": min(values),
                "max": max(values),
            }

    result = {
        "skill_id": args.skill_id,
        "snapshot_count": len(snapshots),
        "dimension": getattr(args, 'dimension', None),
        "dimensions": dimensions_data,
    }

    def _text():
        lines = []
        if getattr(args, 'dimension', None):
            dim = args.dimension
            dim_name = dim_names.get(dim, dim)
            values = [s.ability_scores.get(dim, 0) for s in snapshots]
            lines.append(ASCIICharts.line_chart(values, height=6, title=f"{dim_name}趋势"))
        else:
            lines.append("📊 全维度成长趋势摘要")
            lines.append("═" * 50)
            lines.append("")
            for dim, dn in [("composite", "综合能力"), ("proficiency", "熟练度"),
                            ("stability", "稳定性"), ("satisfaction", "满意度")]:
                values = [s.ability_scores.get(dim, 0) for s in snapshots]
                lines.append(f"   {ASCIICharts.trend_summary_with_sparkline(values, dn)}")
        lines.append("")
        lines.append(f"📊 共 {len(snapshots)} 个历史采样点")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_growth_predict(args: argparse.Namespace) -> None:
    """8F: 技能成长预测"""
    from ..systems.active.growth_predictor import GrowthPredictor

    predictor = GrowthPredictor(args.skill_id)
    prediction = predictor.predict()
    from dataclasses import asdict
    result = asdict(prediction)
    cli_output(result, args, text=lambda: f"\n{prediction.format()}")


def cmd_growth_accelerate(args: argparse.Namespace) -> None:
    """7I: 成长加速器 — 检测学习陡坡, 推荐密集训练"""
    from ..systems.cultivating.growth_accelerator import GrowthAccelerator
    from ..systems.visualization.metrics_store import MetricsStore
    from ..cli_utils import box_header, box_footer

    store = MetricsStore(args.skill_id)
    snaps = store.get_all_snapshots()
    if len(snaps) < 5:
        result = {"skill_id": args.skill_id, "status": "insufficient", "snapshot_count": len(snaps)}
        cli_output(result, args, text=lambda: "📊 数据积累中 (需 5+ 采样点)")
        return

    history = []
    for snap in snaps:
        sc = snap.ability_scores if hasattr(snap, "ability_scores") else {}
        history.append({"ability_scores": sc if isinstance(sc, dict) else {}})

    ga = GrowthAccelerator()
    suggestions = ga.detect(history)

    result = {"skill_id": args.skill_id, "suggestions": suggestions}

    def _text():
        lines = []
        lines.append("")
        lines.append(f"  ┌─ 成长加速器 (7I) " + "─" * 39)
        if suggestions:
            for s in suggestions:
                lines.append(f"  │  🚀 {s['name']}: 近期+{s['recent_growth']} vs 均+{s['avg_growth']}")
                lines.append(f"  │     💡 {s['action']}")
        else:
            lines.append(f"  │  各维度增长稳定, 未检测到加速信号")
            lines.append(f"  │  持续练习, 学习陡坡随时可能出现!")
        lines.append(f"  └{'─' * 60}")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_growth_ceremony(args: argparse.Namespace) -> None:
    """显示境界突破仪式"""
    from zenskill.systems.visualization.level_up_ceremony import LevelUpCeremony

    ceremony = LevelUpCeremony(args.skill_id)

    # 如果指定 --history，显示历史列表
    if getattr(args, 'history', False):
        ceremonies = ceremony.list_ceremonies(limit=10)
        result = {"skill_id": args.skill_id, "mode": "history", "ceremonies": list(reversed(ceremonies))}

        def _history_text():
            lines = ["🏆 境界突破历史", "=" * 60, ""]
            if not ceremonies:
                lines.append("   暂无境界突破记录，继续加油提升境界！")
                return "\n".join(lines)
            for i, c in enumerate(reversed(ceremonies), 1):
                lines.append(f"   {i}. {c['date']} {c['time']}")
                lines.append(f"      {c['old_level']} → {c['new_level']}")
                lines.append("")
            return "\n".join(lines)

        cli_output(result, args, text=_history_text)
        return

    # 显示最近一次突破仪式
    latest = ceremony.get_latest_ceremony()
    if latest:
        result = {"skill_id": args.skill_id, "mode": "latest", "ceremony": latest}
        cli_output(result, args, text=lambda: latest)
    else:
        result = {"skill_id": args.skill_id, "mode": "latest", "ceremony": None}
        cli_output(result, args, text=lambda: (
            "🏆 境界突破仪式\n"
            "=" * 60 + "\n\n"
            "   暂无境界突破记录\n\n"
            "💡 继续使用 ZenSkill，达成 10 次交互将首次突破！"
        ))


def cmd_growth_insight(args: argparse.Namespace) -> None:
    """显示智能成长洞察报告"""
    from zenskill.systems.visualization.insight_engine import GrowthInsightEngine

    brief = getattr(args, 'brief', False)
    engine = GrowthInsightEngine(args.skill_id)
    report = engine.generate_insight_report(brief=brief)
    result = {"skill_id": args.skill_id, "brief": brief, "report": report}
    cli_output(result, args, text=lambda: report)


def cmd_growth_export(args: argparse.Namespace) -> None:
    """7N: 导出成长报告 (Markdown/JSON)"""
    from ..systems.active.growth_exporter import GrowthExporter
    from pathlib import Path

    exporter = GrowthExporter(args.skill_id)
    fmt = getattr(args, 'format', 'markdown')
    period = getattr(args, 'period', 'week')
    out_dir = getattr(args, 'output', None)

    if fmt == 'json':
        export_result = exporter.export_json(output_dir=out_dir)
    else:
        export_result = exporter.export_markdown(period=period, output_dir=out_dir)

    if out_dir:
        result = {"skill_id": args.skill_id, "format": fmt, "output_path": str(export_result)}
        cli_output(result, args, text=lambda: f"✅ 报告已导出: {export_result}")
    else:
        result = {"skill_id": args.skill_id, "format": fmt, "content": export_result}
        cli_output(result, args, text=lambda: str(export_result))


def cmd_growth_report(args: argparse.Namespace) -> None:
    """7Z: 终极成长报告"""
    from ..systems.active.ultimate_report import UltimateReportEngine

    engine = UltimateReportEngine(args.skill_id)
    period = getattr(args, 'period', 'year')
    output_path = getattr(args, 'output', None)
    report = engine.generate(period=period, output_path=output_path)

    if output_path:
        result = {"skill_id": args.skill_id, "period": period, "output_path": str(output_path)}
        cli_output(result, args, text=lambda: f"✅ 报告已生成: {output_path}")
    else:
        result = {"skill_id": args.skill_id, "period": period, "content": report}
        cli_output(result, args, text=lambda: report)


def cmd_growth_compare(args: argparse.Namespace) -> None:
    """7T: 多维对比分析"""
    from ..systems.active.growth_analyzer import GrowthAnalyzer

    analyzer = GrowthAnalyzer(args.skill_id)
    window = getattr(args, 'window', 10)
    result = analyzer.compare(window=window)
    cli_output(result, args, text=lambda: analyzer.format_compare(window=window))


def cmd_growth_replay(args: argparse.Namespace) -> None:
    """7U: 成长路径回放"""
    from ..systems.active.growth_analyzer import GrowthAnalyzer

    analyzer = GrowthAnalyzer(args.skill_id)
    limit = getattr(args, 'limit', 12)
    result = analyzer.replay(limit=limit)
    cli_output(result, args, text=lambda: analyzer.format_replay(limit=limit))


def cmd_growth_errors(args: argparse.Namespace) -> None:
    """7R: 错误模式聚类"""
    from ..systems.active.error_cluster import ErrorClusterAnalyzer

    analyzer = ErrorClusterAnalyzer(args.skill_id)
    days = getattr(args, 'days', 30)
    limit = getattr(args, 'limit', 200)
    result = analyzer.analyze(days=days, limit=limit)
    cli_output(result, args, text=lambda: analyzer.format_report(days=days, limit=limit))


def cmd_growth_feedback(args: argparse.Namespace) -> None:
    """7P: 即时反馈与奖励"""
    from ..systems.active.instant_feedback import InstantFeedbackEngine

    engine = InstantFeedbackEngine(args.skill_id)
    result = {"skill_id": args.skill_id, "feedback": engine.generate()}
    cli_output(result, args, text=lambda: engine.format_report())


def cmd_growth_dimensions(args: argparse.Namespace) -> None:
    """7O: 自定义成长维度"""
    from dataclasses import asdict
    from ..systems.active.custom_dimensions import CustomDimensionManager, parse_milestones

    manager = CustomDimensionManager(args.skill_id)
    action = getattr(args, "action", "list")
    if action == "templates":
        templates_text = CustomDimensionManager.format_templates()
        result = {"skill_id": args.skill_id, "action": "templates", "templates": CustomDimensionManager.TEMPLATES}
        cli_output(result, args, text=lambda: templates_text)
    elif action == "add":
        if not args.id or not args.name:
            raise SystemExit("add 需要 --id 和 --name")
        item = manager.add_dimension(args.id, args.name, args.weight, args.method, parse_milestones(args.milestone))
        result = {"skill_id": args.skill_id, "action": "add", "dimension": asdict(item)}
        cli_output(result, args, text=lambda: f"✅ 已添加自定义维度: {item.name} ({item.dimension_id})")
    elif action == "apply":
        if not args.id:
            raise SystemExit("apply 需要 --id")
        item = manager.apply_template(args.id)
        result = {"skill_id": args.skill_id, "action": "apply", "dimension": asdict(item)}
        cli_output(result, args, text=lambda: f"✅ 已套用维度模板: {item.name} ({item.dimension_id})")
    elif action == "remove":
        if not args.id:
            raise SystemExit("remove 需要 --id")
        removed = manager.remove_dimension(args.id)
        result = {"skill_id": args.skill_id, "action": "remove", "dimension_id": args.id, "removed": removed}
        cli_output(result, args, text=lambda: f"✅ 已删除自定义维度: {args.id}" if removed else f"未找到自定义维度: {args.id}")
    elif action == "export":
        export_text = manager.export_dimensions(args.output)
        result = {"skill_id": args.skill_id, "action": "export", "content": export_text}
        cli_output(result, args, text=lambda: export_text)
    elif action == "import":
        if not args.input:
            raise SystemExit("import 需要 --input")
        count = manager.import_dimensions(args.input)
        result = {"skill_id": args.skill_id, "action": "import", "count": count}
        cli_output(result, args, text=lambda: f"✅ 已导入 {count} 个自定义维度")
    else:
        dims = [asdict(d) for d in manager.list_dimensions()]
        result = {"skill_id": args.skill_id, "action": "list", "dimensions": dims}
        cli_output(result, args, text=lambda: manager.format_report())


def cmd_growth_habits(args: argparse.Namespace) -> None:
    """7X: 习惯养成追踪"""
    from dataclasses import asdict
    from ..systems.active.habit_tracker import HabitTracker

    tracker = HabitTracker(args.skill_id)
    action = getattr(args, "action", "list")
    if action == "templates":
        templates_text = HabitTracker.format_templates()
        result = {"skill_id": args.skill_id, "action": "templates", "templates": HabitTracker.TEMPLATES}
        cli_output(result, args, text=lambda: templates_text)
    elif action == "add":
        if not args.id or not args.title:
            raise SystemExit("add 需要 --id 和 --title")
        habit = tracker.add_habit(args.id, args.title, args.target, args.habit_skill_id or args.skill_id, args.action_contains)
        result = {"skill_id": args.skill_id, "action": "add", "habit": asdict(habit)}
        cli_output(result, args, text=lambda: f"✅ 已添加习惯: {habit.title} ({habit.habit_id})")
    elif action == "apply":
        if not args.id:
            raise SystemExit("apply 需要 --id")
        habit = tracker.apply_template(args.id)
        result = {"skill_id": args.skill_id, "action": "apply", "habit": asdict(habit)}
        cli_output(result, args, text=lambda: f"✅ 已套用习惯模板: {habit.title} ({habit.habit_id})")
    elif action == "remove":
        if not args.id:
            raise SystemExit("remove 需要 --id")
        removed = tracker.remove_habit(args.id)
        result = {"skill_id": args.skill_id, "action": "remove", "habit_id": args.id, "removed": removed}
        cli_output(result, args, text=lambda: f"✅ 已删除习惯: {args.id}" if removed else f"未找到习惯: {args.id}")
    elif action == "export":
        export_text = tracker.export_habits(args.output)
        result = {"skill_id": args.skill_id, "action": "export", "content": export_text}
        cli_output(result, args, text=lambda: export_text)
    elif action == "import":
        if not args.input:
            raise SystemExit("import 需要 --input")
        count = tracker.import_habits(args.input)
        result = {"skill_id": args.skill_id, "action": "import", "count": count}
        cli_output(result, args, text=lambda: f"✅ 已导入 {count} 个习惯")
    else:
        days = getattr(args, 'days', 28)
        habits = [asdict(h) for h in tracker.list_habits()]
        analysis = tracker.analyze(days=days)
        result = {"skill_id": args.skill_id, "action": "list", "habits": habits, "analysis": analysis, "days": days}
        cli_output(result, args, text=lambda: tracker.format_report(days=days))


def cmd_growth_achievements(args: argparse.Namespace) -> None:
    """7Y: 成就与徽章系统"""
    from ..systems.active.achievement_system import AchievementSystem

    system = AchievementSystem(args.skill_id)
    from dataclasses import asdict
    data = system.evaluate()
    result = {k: [asdict(b) if hasattr(b, '__dataclass_fields__') else b for b in v] if isinstance(v, list) else v for k, v in data.items()}
    cli_output(result, args, text=lambda: system.format_report())


def cmd_growth_milestones(args: argparse.Namespace) -> None:
    """列出所有成长里程碑"""
    mgr = SkillStateManager(args.skill_id)
    state = mgr.load()

    milestones = state.get('milestones', [])
    current_level = state.get('level', 'NOVICE')
    usage_count = state.get('usage_count', 0)

    result = {
        "skill_id": args.skill_id,
        "milestones": milestones,
        "current_level": current_level,
        "usage_count": usage_count,
    }

    def _text():
        lines = [f"🏆 成长里程碑: {args.skill_id}", "=" * 60, ""]
        if milestones:
            for i, m in enumerate(milestones, 1):
                level = m.get('level', 'N/A')
                achievement = m.get('achievement', 'N/A')
                timestamp = m.get('timestamp', 'N/A')
                lines.append(f"   {i:2d}. [{level}] {achievement}")
                if timestamp != 'N/A':
                    lines.append(f"       达成时间: {timestamp}")
        else:
            lines.append("   暂无里程碑，继续使用 ZenSkill 解锁成就！")
        lines.append("")
        lines.append(f"📍 当前境界: {current_level}")
        lines.append(f"📊 使用次数: {usage_count} 次")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_growth_abilities(args: argparse.Namespace) -> None:
    """显示已解锁能力"""
    from zenskill.systems.cultivating.skill_manifest import SkillLevel

    # 从状态获取当前境界
    mgr = SkillStateManager(args.skill_id)
    state = mgr.load()
    current_level = SkillLevel[state.get('level', 'NOVICE')]

    # 定义所有能力
    ability_map = {
        SkillLevel.NOVICE: ["基础记忆存储", "简单使用记录"],
        SkillLevel.APPRENTICE: ["基础用户偏好识别", "简单反思摘要生成"],
        SkillLevel.ADEPT: ["主动记忆整合", "性能瓶颈自我诊断", "基础升级提案生成"],
        SkillLevel.EXPERT: ["跨领域洞见生成", "复杂模式识别", "高级升级提案生成"],
        SkillLevel.MASTER: ["自主进化策略规划", "用户需求预判", "多技能协同优化"],
    }

    unlocked = []
    locked_next = []
    for level, abilities in sorted(ability_map.items(), key=lambda x: x[0].value):
        if level.value <= current_level.value:
            unlocked.extend(abilities)
        elif level.value == current_level.value + 1:
            locked_next.extend(abilities)

    result = {
        "skill_id": args.skill_id,
        "current_level": current_level.name,
        "unlocked": unlocked,
        "next_level_locked": locked_next,
        "total_unlocked": len(unlocked),
    }

    def _text():
        lines = [f"🔮 已解锁能力: {args.skill_id}", "=" * 60, f"   当前境界: {current_level.name}", ""]
        lines.append("✅ 已解锁能力:")
        for ability in unlocked:
            lines.append(f"   - {ability}")
        lines.append(f"\n🔜 待解锁能力（下一境界）:")
        if locked_next:
            for ability in locked_next:
                lines.append(f"   - {ability}")
        else:
            lines.append("   已达到最高境界，所有能力已解锁！")
        lines.append(f"\n📈 总共解锁了 {len(unlocked)} 项能力")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


# ================================================================
# Profile 管理命令处理器
# ================================================================



def register_growth_parser(subparsers) -> None:
    """注册 growth 子命令组到 argparse。"""
    growth_parser = subparsers.add_parser("growth", help="成长可视化（默认显示状态）")
    growth_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    growth_parser.set_defaults(func=cmd_growth_status)  # growth 默认为 status
    growth_subparsers = growth_parser.add_subparsers(dest="subcommand", help="成长操作")

    # growth status
    growth_status_parser = growth_subparsers.add_parser("status", help="显示成长状态（五维能力雷达图）")
    growth_status_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    growth_status_parser.add_argument("--dimension", choices=["composite", "proficiency", "stability", "satisfaction", "responsiveness", "memory"], help="指定聚焦维度")
    growth_status_parser.add_argument("--watch", "-w", action="store_true", help="实时轮询监控（每 5s 刷新）")
    growth_status_parser.set_defaults(func=cmd_growth_status)

    # growth trend
    growth_trend_parser = growth_subparsers.add_parser("trend", help="显示成长趋势")
    growth_trend_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    growth_trend_parser.add_argument("--dimension", choices=["composite", "proficiency", "stability", "satisfaction", "responsiveness", "memory"], help="指定显示的维度")
    growth_trend_parser.set_defaults(func=cmd_growth_trend)

    # growth milestones
    growth_milestones_parser = growth_subparsers.add_parser("milestones", help="列出所有成长里程碑")
    growth_milestones_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    growth_milestones_parser.set_defaults(func=cmd_growth_milestones)

    # growth abilities
    growth_abilities_parser = growth_subparsers.add_parser("abilities", help="显示已解锁能力")
    growth_abilities_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    growth_abilities_parser.set_defaults(func=cmd_growth_abilities)

    # growth accelerate (7I: 成长加速器)
    growth_accelerate_parser = growth_subparsers.add_parser("accelerate", help="成长加速器 — 检测学习陡坡 (7I)")
    growth_accelerate_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    growth_accelerate_parser.set_defaults(func=cmd_growth_accelerate)
    # growth predict (8F: 技能成长预测)
    growth_predict_parser = growth_subparsers.add_parser("predict", help="技能成长预测 — 晋升时间估算 (8F)")
    growth_predict_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    growth_predict_parser.set_defaults(func=cmd_growth_predict)

    # growth ceremony
    growth_ceremony_parser = growth_subparsers.add_parser("ceremony", help="显示境界突破仪式")
    growth_ceremony_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    growth_ceremony_parser.add_argument("--history", action="store_true", help="显示突破历史列表")
    growth_ceremony_parser.set_defaults(func=cmd_growth_ceremony)

    # growth insight
    growth_insight_parser = growth_subparsers.add_parser("insight", help="显示智能成长洞察报告")
    growth_insight_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    growth_insight_parser.add_argument("--brief", action="store_true", help="显示精简版报告")
    growth_insight_parser.set_defaults(func=cmd_growth_insight)

    # growth export (7N)
    growth_export_parser = growth_subparsers.add_parser("export", help="导出成长报告 — Markdown/JSON (7N)")
    growth_export_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    growth_export_parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="输出格式")
    growth_export_parser.add_argument("--period", choices=["week", "month", "all"], default="week", help="时间范围")
    growth_export_parser.add_argument("--output", "-o", default=None, help="输出目录 (默认打印到 stdout)")
    growth_export_parser.set_defaults(func=cmd_growth_export)
    # growth report (7Z)
    growth_report_parser = growth_subparsers.add_parser("report", help="生成终极成长报告 (7Z)")
    growth_report_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    growth_report_parser.add_argument("--period", choices=["year", "quarter", "month"], default="year", help="时间范围")
    growth_report_parser.add_argument("--output", "-o", default=None, help="输出文件路径")
    growth_report_parser.set_defaults(func=cmd_growth_report)

    # growth compare (7T)
    growth_compare_parser = growth_subparsers.add_parser("compare", help="多维对比分析 — 本期 vs 过去 (7T)")
    growth_compare_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    growth_compare_parser.add_argument("--window", type=int, default=10, help="对比采样窗口")
    growth_compare_parser.set_defaults(func=cmd_growth_compare)

    # growth replay (7U)
    growth_replay_parser = growth_subparsers.add_parser("replay", help="成长路径回放 — 时间线叙事 (7U)")
    growth_replay_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    growth_replay_parser.add_argument("--limit", type=int, default=12, help="最多显示事件数")
    growth_replay_parser.set_defaults(func=cmd_growth_replay)

    # growth errors (7R)
    growth_errors_parser = growth_subparsers.add_parser("errors", help="错误模式聚类 — Top 错误类型与建议 (7R)")
    growth_errors_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    growth_errors_parser.add_argument("--days", type=int, default=30, help="分析最近 N 天")
    growth_errors_parser.add_argument("--limit", type=int, default=200, help="最多读取错误事件数")
    growth_errors_parser.set_defaults(func=cmd_growth_errors)

    # growth feedback (7P)
    growth_feedback_parser = growth_subparsers.add_parser("feedback", help="即时反馈与奖励 — 微反馈/连击/每日成就 (7P)")
    growth_feedback_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    growth_feedback_parser.set_defaults(func=cmd_growth_feedback)

    # growth dimensions (7O)
    growth_dimensions_parser = growth_subparsers.add_parser("dimensions", help="自定义成长维度 — 定义/模板/导入导出 (7O)")
    growth_dimensions_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    growth_dimensions_parser.add_argument("--action", choices=["list", "templates", "add", "apply", "remove", "export", "import"], default="list", help="操作类型")
    growth_dimensions_parser.add_argument("--id", default="", help="维度ID或模板ID")
    growth_dimensions_parser.add_argument("--name", default="", help="维度名称")
    growth_dimensions_parser.add_argument("--weight", type=float, default=0.1, help="维度权重 (0-1)")
    growth_dimensions_parser.add_argument("--method", default="manual", help="评估方法说明")
    growth_dimensions_parser.add_argument("--milestone", action="append", help="里程碑，格式: 分数:说明，可重复")
    growth_dimensions_parser.add_argument("--output", "-o", default=None, help="导出文件路径")
    growth_dimensions_parser.add_argument("--input", "-i", default=None, help="导入文件路径")
    growth_dimensions_parser.set_defaults(func=cmd_growth_dimensions)

    # growth habits (7X)
    growth_habits_parser = growth_subparsers.add_parser("habits", help="习惯养成追踪 — 打卡日历/连续天数/中断风险 (7X)")
    growth_habits_parser.add_argument("--skill-id", default="zenskill-core", help="报告默认技能ID")
    growth_habits_parser.add_argument("--action", choices=["list", "templates", "add", "apply", "remove", "export", "import"], default="list", help="操作类型")
    growth_habits_parser.add_argument("--id", default="", help="习惯ID或模板ID")
    growth_habits_parser.add_argument("--title", default="", help="习惯标题")
    growth_habits_parser.add_argument("--target", type=int, default=1, help="每日目标事件数")
    growth_habits_parser.add_argument("--habit-skill-id", default="", help="习惯匹配的技能ID")
    growth_habits_parser.add_argument("--action-contains", default="", help="匹配 action 中包含的文本")
    growth_habits_parser.add_argument("--days", type=int, default=28, help="展示最近 N 天")
    growth_habits_parser.add_argument("--output", "-o", default=None, help="导出文件路径")
    growth_habits_parser.add_argument("--input", "-i", default=None, help="导入文件路径")
    growth_habits_parser.set_defaults(func=cmd_growth_habits)

    # growth achievements (7Y)
    growth_achievements_parser = growth_subparsers.add_parser("achievements", help="成就与徽章系统 — 里程碑/习惯/质量徽章 (7Y)")
    growth_achievements_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    growth_achievements_parser.set_defaults(func=cmd_growth_achievements)

    # goal 命令组（主动成长目标）
