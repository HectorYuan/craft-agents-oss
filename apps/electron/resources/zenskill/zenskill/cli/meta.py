"""meta 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

def cmd_meta_report(args: argparse.Namespace) -> None:
    """元反思综合报告"""
    from zenskill.systems.active.meta_reflection import MetaReflectionEngine

    engine = MetaReflectionEngine(args.skill_id)
    report = engine.generate_meta_report()
    cli_output({"ok": True, "report": report}, args, text=lambda: report)


def cmd_meta_suggestions(args: argparse.Namespace) -> None:
    """生成优化建议列表"""
    from zenskill.systems.active.meta_reflection import MetaReflectionEngine

    engine = MetaReflectionEngine(args.skill_id)
    suggestions = engine.generate_optimization_suggestions()

    result = []
    for opt in suggestions:
        result.append({
            "optimization_id": opt.optimization_id,
            "suggestion": opt.suggestion,
            "target_component": opt.target_component,
            "implementation_complexity": opt.implementation_complexity,
            "expected_improvement": opt.expected_improvement,
            "status": opt.status,
        })

    def _text():
        lines = []
        lines.append(f"🧠 元反思 - 优化建议列表")
        lines.append("═" * 60)
        lines.append("")

        if not suggestions:
            lines.append("   暂无优化建议")
            lines.append("")
            lines.append("💡 继续使用反思功能，积累更多数据后会自动生成优化建议")
            return "\n".join(lines)

        for i, opt in enumerate(suggestions, 1):
            complexity_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(opt.implementation_complexity, "⚪")
            status_emoji = {"proposed": "📋", "implementing": "🔧", "implemented": "✅", "reverted": "↩️"}.get(opt.status, "❓")

            lines.append(f"   {i}. {status_emoji} {opt.suggestion}")
            lines.append(f"      目标组件: {opt.target_component}")
            lines.append(f"      实现难度: {complexity_emoji} {opt.implementation_complexity}")
            lines.append(f"      预期提升: {int(opt.expected_improvement * 100)}%")
            lines.append(f"      建议 ID: {opt.optimization_id}")
            lines.append("")

        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_meta_implement(args: argparse.Namespace) -> None:
    """标记优化建议为已实现"""
    from zenskill.systems.active.meta_reflection import MetaReflectionEngine

    engine = MetaReflectionEngine(args.skill_id)
    success = engine.mark_optimization_implemented(args.optimization_id)

    if success:
        cli_output(
            {"ok": True, "optimization_id": args.optimization_id},
            args,
            text=lambda: f"✅ 优化建议已标记为已实现！\n   ID: {args.optimization_id}\n\n🎉 ZenSkill 的自我进化能力 +1",
        )
    else:
        cli_output(
            {"ok": False, "error": "未找到该优化建议"},
            args,
            text=lambda: f"❌ 未找到该优化建议",
        )


def cmd_meta_biases(args: argparse.Namespace) -> None:
    """查看系统性偏差分析"""
    from zenskill.systems.active.meta_reflection import MetaReflectionEngine

    engine = MetaReflectionEngine(args.skill_id)
    biases = engine.identify_systemic_biases()

    result = {"count": len(biases), "biases": biases}

    def _text():
        lines = []
        lines.append(f"🔍 系统性偏差分析报告")
        lines.append("═" * 60)
        lines.append("")

        for i, bias in enumerate(biases, 1):
            severity_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(bias["severity"], "⚪")

            lines.append(f"   {i}. {severity_emoji} [{bias['severity'].upper()}]")
            lines.append(f"      {bias['description']}")
            lines.append(f"      💡 建议: {bias['suggestion']}")
            lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)



def register_meta_parser(subparsers) -> None:
    """注册 meta 子命令组。"""
    meta_parser = subparsers.add_parser("meta", help="元反思系统（自我进化）")
    meta_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    meta_parser.set_defaults(func=cmd_meta_report)  # meta 默认为 report
    meta_subparsers = meta_parser.add_subparsers(dest="subcommand", help="元反思操作")

    # meta report (默认)
    meta_report_parser = meta_subparsers.add_parser("report", help="元反思综合报告")
    meta_report_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    meta_report_parser.set_defaults(func=cmd_meta_report)

    # meta suggestions
    meta_suggestions_parser = meta_subparsers.add_parser("suggestions", help="生成优化建议列表")
    meta_suggestions_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    meta_suggestions_parser.set_defaults(func=cmd_meta_suggestions)

    # meta implement
    meta_implement_parser = meta_subparsers.add_parser("implement", help="标记优化建议为已实现")
    meta_implement_parser.add_argument("optimization_id", help="优化建议ID")
    meta_implement_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    meta_implement_parser.set_defaults(func=cmd_meta_implement)

    # meta biases
    meta_biases_parser = meta_subparsers.add_parser("biases", help="查看系统性偏差分析")
    meta_biases_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    meta_biases_parser.set_defaults(func=cmd_meta_biases)

    # graph 命令组（技能依赖图谱）
