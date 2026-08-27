"""task 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

def cmd_task_recommend(args: argparse.Namespace) -> None:
    """推荐练习任务"""
    from zenskill.systems.active.task_recommender import TaskRecommendationEngine

    engine = TaskRecommendationEngine(args.skill_id)

    tasks = engine.get_pending_tasks()
    result = []
    for task in tasks:
        result.append({
            "task_id": task.task_id,
            "title": task.title,
            "description": task.description,
            "difficulty": task.difficulty,
            "target_dimensions": task.target_dimensions,
            "estimated_interactions": task.estimated_interactions,
            "priority": task.priority,
        })
    cli_output(result, args, text=lambda: engine.generate_recommendation_report())


def cmd_task_status(args: argparse.Namespace) -> None:
    """查看任务状态"""
    from zenskill.systems.active.task_recommender import TaskRecommendationEngine

    engine = TaskRecommendationEngine(args.skill_id)
    pending = engine.get_pending_tasks()

    result = []
    for task in pending:
        result.append({
            "task_id": task.task_id,
            "title": task.title,
            "description": task.description,
            "difficulty": task.difficulty,
        })

    def _text():
        lines = []
        lines.append(f"📋 练习任务状态")
        lines.append("=" * 60)
        lines.append("")

        if not pending:
            lines.append("   暂无待完成任务")
            lines.append("")
            lines.append(f"💡 使用 'python -m zenskill task recommend' 获取推荐")
            return "\n".join(lines)

        lines.append(f"   待完成任务: {len(pending)} 个")
        lines.append("")

        for task in pending:
            icon = {
                "easy": "🟢",
                "medium": "🟡",
                "hard": "🔴",
            }.get(task.difficulty, "•")

            lines.append(f"   {icon} {task.title}")
            lines.append(f"      {task.description}")
            lines.append(f"      ID: {task.task_id}")
            lines.append("")

        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_task_complete(args: argparse.Namespace) -> None:
    """标记任务完成"""
    from zenskill.systems.active.task_recommender import TaskRecommendationEngine

    engine = TaskRecommendationEngine(args.skill_id)
    success = engine.complete_task(args.task_id)

    if success:
        cli_output(
            {"ok": True, "task_id": args.task_id},
            args,
            text=lambda: f"✅ 任务已标记为完成！\n   ID: {args.task_id}\n\n🎉 继续加油，更多练习帮助你更快成长！",
        )
    else:
        cli_output(
            {"ok": False, "error": "未找到该任务"},
            args,
            text=lambda: f"❌ 未找到该任务",
        )


def cmd_task_generate(args: argparse.Namespace) -> None:
    """LLM 个性化任务生成 (7G) — 基于活跃目标，用 DeepSeek 生成定制练习任务"""
    from zenskill.systems.active.goal_engine import ActiveGoalEngine
    from zenskill.task_generator import TaskGenerator

    engine = ActiveGoalEngine(args.skill_id)
    active = engine.get_active_goals()
    if not active:
        cli_output(
            {"ok": False, "error": "当前无活跃目标"},
            args,
            text=lambda: "📋 当前无活跃目标，请先设定目标: zenskill goal suggest",
        )
        return

    gen = TaskGenerator(args.skill_id)
    all_generated = []

    def _text():
        lines = []
        for goal in active[:2]:
            dim_name = engine.DIMENSION_NAMES.get(goal.dimension, goal.dimension)
            lines.append(f"\n🎯 目标: {dim_name} ({goal.current_score}→{goal.target_score})")
            lines.append(f"   策略: {goal.strategy}")
            lines.append("")
            tasks = gen.generate_for_goal(goal)
            source = "LLM" if tasks and tasks[0].get("source") != "template" else "模板"
            lines.append(f"   📋 生成 {len(tasks)} 个{source}任务:")
            for t in tasks:
                diff_icon = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(t.get("difficulty", ""), "⚪")
                lines.append(f"   {diff_icon} {t['title']}")
                lines.append(f"      {t['description'][:80]}")
                lines.append(f"      预计 {t.get('estimated_minutes', '?')} 分钟 | 目标维度: {', '.join(t.get('target_dimensions', []))}")
                lines.append("")
                all_generated.append(t)
        return "\n".join(lines)

    # 生成数据并收集到 result（通过 _text 中的副作用填充 all_generated）
    text_out = _text()
    cli_output(all_generated, args, text=lambda: text_out)



def register_task_parser(subparsers) -> None:
    """注册 task 子命令组。"""
    task_parser = subparsers.add_parser("task", help="练习任务管理")
    task_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    task_parser.set_defaults(func=cmd_task_recommend)  # task 默认为 recommend
    task_subparsers = task_parser.add_subparsers(dest="subcommand", help="任务操作")

    # task recommend
    task_recommend_parser = task_subparsers.add_parser("recommend", help="推荐练习任务")
    task_recommend_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    task_recommend_parser.set_defaults(func=cmd_task_recommend)

    # task status
    task_status_parser = task_subparsers.add_parser("status", help="查看任务状态")
    task_status_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    task_status_parser.set_defaults(func=cmd_task_status)

    # task complete
    task_complete_parser = task_subparsers.add_parser("complete", help="标记任务完成")
    task_complete_parser.add_argument("task_id", help="任务ID")
    task_complete_parser.set_defaults(func=cmd_task_complete)

    # task generate (7G LLM 个性化)
    task_generate_parser = task_subparsers.add_parser("generate", help="LLM 生成个性化任务 (7G)")
    task_generate_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    task_generate_parser.set_defaults(func=cmd_task_generate)

    # insight 命令组（主动洞察推送）
    from .insight import register_insight_parser
    register_insight_parser(subparsers)
