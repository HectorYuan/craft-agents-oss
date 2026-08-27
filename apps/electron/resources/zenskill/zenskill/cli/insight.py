"""insight 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

def cmd_insight_unread(args: argparse.Namespace) -> None:
    """查看未读洞察"""
    from zenskill.systems.active.proactive_insight import ProactiveInsightEngine

    engine = ProactiveInsightEngine(args.skill_id)

    insights = engine.get_unread_insights()
    result = []
    for ins in insights:
        result.append({
            "insight_id": ins.insight_id,
            "type": ins.type,
            "level": ins.level,
            "title": ins.title,
            "content": ins.content,
            "created_at": ins.created_at,
        })
    cli_output(result, args, text=lambda: engine.generate_summary_report(include_read=False))


def cmd_insight_mark_read(args: argparse.Namespace) -> None:
    """标记洞察为已读"""
    from zenskill.systems.active.proactive_insight import ProactiveInsightEngine

    engine = ProactiveInsightEngine(args.skill_id)
    success = engine.mark_as_read(args.insight_id)

    if success:
        cli_output(
            {"ok": True, "insight_id": args.insight_id},
            args,
            text=lambda: f"✅ 洞察已标记为已读\n   ID: {args.insight_id}",
        )
    else:
        cli_output(
            {"ok": False, "error": "未找到该洞察"},
            args,
            text=lambda: f"❌ 未找到该洞察",
        )


def cmd_insight_generate(args: argparse.Namespace) -> None:
    """强制生成新洞察 (7F) — 基于当前指标数据"""
    from zenskill.systems.active.proactive_insight import ProactiveInsightEngine

    engine = ProactiveInsightEngine(args.skill_id)
    new = engine.check_and_generate_insights()

    result = []
    for ins in new:
        result.append({
            "insight_id": ins.insight_id,
            "type": ins.type,
            "level": ins.level,
            "title": ins.title,
            "content": ins.content,
        })

    def _text():
        lines = []
        if new:
            lines.append(f"💡 生成 {len(new)} 条新洞察:")
            lines.append("")
            for ins in new:
                icon = {"milestone": "🏆", "celebration": "🎊", "warning": "⚠️", "bottleneck": "🔍"}.get(ins.type, "💡")
                lines.append(f"  {icon} [{ins.level}] {ins.title}")
                lines.append(f"     {ins.content[:100]}")
                lines.append("")
        else:
            lines.append("✅ 当前无新洞察产生，数据积累中...")
            unread = engine.get_unread_insights()
            if unread:
                lines.append(f"   📬 仍有 {len(unread)} 条未读洞察: zenskill insight unread")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


# ====================================================================
# 7J A/B 测试框架命令
# ====================================================================


def register_insight_parser(subparsers) -> None:
    """注册 insight 子命令组。"""
    insight_parser = subparsers.add_parser("insight", help="主动洞察推送")
    insight_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    insight_parser.set_defaults(func=cmd_insight_unread)  # insight 默认为 unread
    insight_subparsers = insight_parser.add_subparsers(dest="subcommand", help="洞察操作")

    # insight unread
    insight_unread_parser = insight_subparsers.add_parser("unread", help="查看未读洞察")
    insight_unread_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    insight_unread_parser.set_defaults(func=cmd_insight_unread)

    # insight read
    insight_read_parser = insight_subparsers.add_parser("read", help="标记洞察为已读")
    insight_read_parser.add_argument("insight_id", help="洞察ID")
    insight_read_parser.set_defaults(func=cmd_insight_mark_read)

    # insight generate
    insight_generate_parser = insight_subparsers.add_parser("generate", help="强制生成新洞察 (7F)")
    insight_generate_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    insight_generate_parser.set_defaults(func=cmd_insight_generate)

    # experiment 命令组（A/B 测试框架）
    from .experiment import register_experiment_parser
    register_experiment_parser(subparsers)
