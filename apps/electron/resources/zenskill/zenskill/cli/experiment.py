"""experiment 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

from ..cli_utils import output as cli_output

def cmd_experiment_create(args: argparse.Namespace) -> None:
    from ..systems.active.ab_testing import ABTestEngine
    engine = ABTestEngine()
    exp = engine.create(args.name, args.description, args.variants, args.metrics)
    result = {
        "name": exp.name,
        "variants": exp.variants,
        "metrics": exp.metrics,
    }
    cli_output(result, args, text=lambda: (
        f"\n🧪 实验已创建: {exp.name}\n"
        f"   变体: {', '.join(exp.variants)}\n"
        f"   指标: {', '.join(exp.metrics)}\n"
    ))


def cmd_experiment_list(args: argparse.Namespace) -> None:
    from ..systems.active.ab_testing import ABTestEngine
    engine = ABTestEngine()
    exps = engine.list_all()
    result = {
        "count": len(exps),
        "experiments": [
            {"name": e.name, "status": e.status, "variants": e.variants, "metrics": e.metrics}
            for e in exps
        ],
    }
    def _text():
        lines = []
        if not exps:
            lines.append("\n(无实验)\n")
            return "\n".join(lines)
        lines.append(f"\n🧪 实验列表 ({len(exps)} 个)\n")
        for e in exps:
            icon = "🟢" if e.status == "active" else "⚪" if e.status == "completed" else "📦"
            lines.append(f"  {icon} {e.name:30s} [{e.status}] {len(e.variants)} 变体 × {len(e.metrics)} 指标")
        return "\n".join(lines)
    cli_output(result, args, text=_text)


def cmd_experiment_analyze(args: argparse.Namespace) -> None:
    from ..systems.active.ab_testing import ABTestEngine
    engine = ABTestEngine()
    report = engine.format_report(args.name)
    cli_output({"name": args.name, "report": report}, args, text=lambda: f"\n{report}\n")


def cmd_experiment_record(args: argparse.Namespace) -> None:
    from ..systems.active.ab_testing import ABTestEngine
    engine = ABTestEngine()
    try:
        metrics = json.loads(args.metrics)
    except json.JSONDecodeError:
        print(f"❌ 指标格式错误，需要 JSON: {{\"score\": 85}}")
        return
    engine.record(args.name, args.variant, metrics, user_id=args.user_id)
    result = {"name": args.name, "variant": args.variant, "metrics": metrics}
    cli_output(result, args, text=lambda: f"✅ 已记录: {args.name} / {args.variant} / {metrics}")


def cmd_experiment_complete(args: argparse.Namespace) -> None:
    from ..systems.active.ab_testing import ABTestEngine
    engine = ABTestEngine()
    if engine.complete(args.name):
        result = engine.analyze(args.name)
        report = engine.format_report(args.name)
        cli_output({"name": args.name, "analysis": result, "report": report}, args, text=lambda: f"\n{report}\n")
    else:
        print(f"❌ 实验不存在: {args.name}")



def register_experiment_parser(subparsers) -> None:
    """注册 experiment 子命令组。"""
    experiment_parser = subparsers.add_parser("experiment", help="A/B 测试框架 (7J)")
    experiment_subparsers = experiment_parser.add_subparsers(dest="subcommand", help="实验操作")
    # experiment create
    exp_create = experiment_subparsers.add_parser("create", help="创建实验")
    exp_create.add_argument("name", help="实验名称")
    exp_create.add_argument("--description", default="", help="实验描述")
    exp_create.add_argument("--variants", nargs="+", required=True, help="变体名称列表")
    exp_create.add_argument("--metrics", nargs="+", required=True, help="跟踪指标列表")
    exp_create.set_defaults(func=cmd_experiment_create)
    # experiment list
    exp_list = experiment_subparsers.add_parser("list", help="列出所有实验")
    exp_list.set_defaults(func=cmd_experiment_list)
    # experiment analyze
    exp_analyze = experiment_subparsers.add_parser("analyze", help="分析实验结果")
    exp_analyze.add_argument("name", help="实验名称")
    exp_analyze.set_defaults(func=cmd_experiment_analyze)
    # experiment record
    exp_record = experiment_subparsers.add_parser("record", help="记录试验数据")
    exp_record.add_argument("name", help="实验名称")
    exp_record.add_argument("--variant", required=True, help="变体名称")
    exp_record.add_argument("--metrics", required=True, help="指标值 JSON, 如 '{\"score\": 85}'")
    exp_record.add_argument("--user-id", default="", help="用户标识")
    exp_record.set_defaults(func=cmd_experiment_record)
    # experiment complete
    exp_complete = experiment_subparsers.add_parser("complete", help="完成实验")
    exp_complete.add_argument("name", help="实验名称")
    exp_complete.set_defaults(func=cmd_experiment_complete)
    experiment_parser.set_defaults(func=cmd_experiment_list)

    # meta 命令组（元反思系统）
    from .meta import register_meta_parser
    register_meta_parser(subparsers)
