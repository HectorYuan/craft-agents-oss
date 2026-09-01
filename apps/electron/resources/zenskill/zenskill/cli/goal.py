"""goal 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

from ..cli_utils import output as cli_output

def cmd_goal_status(args: argparse.Namespace) -> None:
    """显示目标状态"""
    from zenskill.systems.active.goal_engine import ActiveGoalEngine

    engine = ActiveGoalEngine(args.skill_id)

    goals = engine.get_active_goals()
    result = []
    for goal in goals:
        progress = engine.get_goal_progress(goal)  # 传 GrowthGoal 对象，不是 goal_id 字符串
        pct = progress.progress_pct if progress else 0
        result.append({
            "goal_id": goal.goal_id,
            "dimension": goal.dimension,
            "target_score": goal.target_score,
            "current_score": goal.current_score,
            "progress_pct": round(pct, 1),
            "status": goal.status,
            "strategy": goal.strategy,
        })
    cli_output(result, args, text=lambda: engine.generate_status_report())


def cmd_goal_suggest(args: argparse.Namespace) -> None:
    """推荐成长目标"""
    from zenskill.systems.active.goal_engine import ActiveGoalEngine

    engine = ActiveGoalEngine(args.skill_id)
    goals = engine.suggest_goals()

    result = []
    for goal in goals:
        result.append({
            "dimension": goal.dimension,
            "target_score": goal.target_score,
            "current_score": goal.current_score,
            "gap": goal.target_score - goal.current_score,
            "strategy": goal.strategy,
            "deadline_interactions": goal.deadline_interactions,
        })

    def _text():
        lines = ["🎯 推荐成长目标", "=" * 60, ""]
        if not goals:
            lines.append("   暂无推荐目标，继续使用积累数据")
            return "\n".join(lines)
        for goal in goals:
            dim_name = {
                "proficiency": "熟练度",
                "stability": "稳定性",
                "satisfaction": "满意度",
                "responsiveness": "响应力",
                "memory": "记忆力",
                "composite": "综合能力",
            }.get(goal.dimension, goal.dimension)
            lines.append(f"   📍 [{dim_name}] {goal.current_score} → {goal.target_score} 分")
            lines.append(f"      策略: {goal.strategy}")
            lines.append("")
        lines.append(f"💡 使用 'python -m zenskill goal set --dimension {goals[0].dimension} --target {goals[0].target_score}' 设置目标")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_goal_set(args: argparse.Namespace) -> None:
    """设置成长目标"""
    from zenskill.systems.active.goal_engine import ActiveGoalEngine

    engine = ActiveGoalEngine(args.skill_id)

    try:
        goal = engine.create_goal(
            dimension=args.dimension,
            target_score=args.target,
            deadline_interactions=getattr(args, 'deadline', None),
        )

        dim_name = {
            "proficiency": "熟练度",
            "stability": "稳定性",
            "satisfaction": "满意度",
            "responsiveness": "响应力",
            "memory": "记忆力",
            "composite": "综合能力",
        }.get(goal.dimension, goal.dimension)

        result = {
            "ok": True,
            "dimension": goal.dimension,
            "dim_name": dim_name,
            "current_score": goal.current_score,
            "target_score": goal.target_score,
            "strategy": goal.strategy,
        }
        def _text():
            lines = []
            lines.append(f"✅ 目标已创建！")
            lines.append(f"   [{dim_name}] {goal.current_score} → {goal.target_score} 分")
            lines.append(f"   策略: {goal.strategy}")
            lines.append("")
            lines.append(f"💡 使用 'python -m zenskill goal status' 查看进度")
            return "\n".join(lines)
        cli_output(result, args, text=_text)

    except ValueError as e:
        cli_output({"ok": False, "error": str(e)}, args, text=lambda: f"❌ 创建失败: {e}")



def register_goal_parser(subparsers) -> None:
    """注册 goal 子命令组。"""
    goal_parser = subparsers.add_parser("goal", help="成长目标管理")
    goal_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    goal_parser.set_defaults(func=cmd_goal_status)  # goal 默认为 status
    goal_subparsers = goal_parser.add_subparsers(dest="subcommand", help="目标操作")

    # goal status
    goal_status_parser = goal_subparsers.add_parser("status", help="显示当前目标状态")
    goal_status_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    goal_status_parser.set_defaults(func=cmd_goal_status)

    # goal suggest
    goal_suggest_parser = goal_subparsers.add_parser("suggest", help="推荐成长目标")
    goal_suggest_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    goal_suggest_parser.set_defaults(func=cmd_goal_suggest)

    # goal set
    goal_set_parser = goal_subparsers.add_parser("set", help="设置成长目标")
    goal_set_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    goal_set_parser.add_argument("--dimension", required=True, choices=["proficiency", "stability", "satisfaction", "responsiveness", "memory", "composite"], help="目标维度")
    goal_set_parser.add_argument("--target", type=int, required=True, help="目标分数 (0-100)")
    goal_set_parser.set_defaults(func=cmd_goal_set)

    # task 命令组（智能任务推荐）
