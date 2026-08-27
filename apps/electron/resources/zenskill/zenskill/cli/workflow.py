"""workflow 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

def cmd_workflow_patterns(args: argparse.Namespace) -> None:
    """发现工作流模式 — 识别编码-测试-重构等高频模式 (9D)"""
    from .cli_utils import section_blank, box_header, box_footer, bar_chart
    from .mirroring.workflow import WorkflowAnalyzer

    analyzer = WorkflowAnalyzer()
    result = analyzer.detect_patterns()

    def _text():
        lines = []
        section_blank("工作流模式分析", "🔄", phase="9D")
        patterns = result.get("patterns", [])
        if not patterns:
            box_header("模式匹配", "🔍")
            lines.append("  │  [dim]尚无足够数据识别工作流模式[/dim]")
            lines.append("  │  [dim]持续使用后自动生成[/dim]")
            box_footer()
            lines.append("")
            return "\n".join(lines)

        box_header(f"主导模式: {result['dominant']}", "🏆")
        lines.append(f"  │  分析窗口: {result.get('total_windows', 0)} 个工具序列")
        lines.append(f"  │  已匹配:   {result.get('total_matched', 0)} 次")
        lines.append(f"  │  未识别:   {result.get('unknown_ratio', 0)}%")
        box_footer()

        lines.append("")
        box_header("所有匹配模式", "📊")
        max_count = max(p["count"] for p in patterns) if patterns else 1
        for p in patterns:
            bar = bar_chart(p["count"], max_count, 20)
            efficiency_icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(p.get("efficiency", "medium"), "⚪")
            lines.append(f"  │  {efficiency_icon} {p['name']:12s} {bar} {p['pct']}%")
            lines.append(f"  │     {p['description']}")
            if p.get("tags"):
                lines.append(f"  │     [dim]标签: {', '.join(p['tags'])}[/dim]")
        box_footer()

        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_workflow_bottlenecks(args: argparse.Namespace) -> None:
    """查看工作流瓶颈 — 检测停顿、卡点、低效环节 (9D)"""
    from .cli_utils import section_blank, box_header, box_footer, status_icon
    from .mirroring.workflow import BottleneckDetector

    detector = BottleneckDetector()
    result = detector.detect_all()

    overall = result.get("overall_score", {})
    grade = overall.get("grade", "N/A")
    score = overall.get("overall", 0)

    def _text():
        lines = []
        section_blank("工作流瓶颈检测", "🔍", phase="9D")

        # 健康度
        grade_icon = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴"}.get(grade, "⚪")
        box_header(f"整体健康度: {grade} ({score}/100)", grade_icon)
        details = overall.get("details", {})
        for dim, s in details.items():
            lines.append(f"  │  {dim:15s} {status_icon(s)} {s}/100")
        box_footer()

        # 错误工具
        err_tools = result.get("high_error_tools", {})
        if err_tools.get("problem_tools"):
            lines.append("")
            box_header("高频错误工具", "⚠️")
            for pt in err_tools["problem_tools"]:
                sev_icon = "🔴" if pt["severity"] == "high" else "🟡"
                lines.append(f"  │  {sev_icon} {pt['tool']}: 失败 {pt['fails']}/{pt['total']} ({pt['fail_rate']:.0%})")
            box_footer()

        # 重复循环
        loops = result.get("repetitive_loops", {})
        if loops.get("loops"):
            lines.append("")
            box_header("重复循环", "🔁")
            for loop in loops["loops"]:
                lines.append(f"  │  {loop['transition']}  — 占比 {loop['ratio']:.0%} ({loop['count']} 次)")
            box_footer()

        # 停顿
        stalls = result.get("long_stalls", {})
        total_stalls = stalls.get("total_stalls", 0)
        if total_stalls > 0:
            lines.append("")
            box_header("工作停顿", "⏸️")
            lines.append(f"  │  总停顿: {total_stalls} 次")
            lines.append(f"  │  长停顿: {stalls.get('long_stalls_count', 0)} 次（>15分钟）")
            lines.append(f"  │  平均间隔: {stalls.get('avg_gap_min', 0)} 分钟")
            box_footer()

        # 中断成本
        interrupt = result.get("interruption_cost", {})
        cost = interrupt.get("cost_min", 0)
        if cost > 0:
            lines.append("")
            box_header("中断恢复", "⏱️")
            lines.append(f"  │  平均恢复时间: {cost} 分钟")
            lines.append(f"  │  中断次数: {interrupt.get('interruptions', 0)} 次")
            box_footer()

        # 项目切换
        switch = result.get("project_switch_cost", {})
        cost_label = switch.get("cost", "unknown")
        cost_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(cost_label, "⚪")
        lines.append("")
        box_header("项目切换代价", cost_icon)
        lines.append(f"  │  切换代价: {cost_label}")
        lines.append(f"  │  总切换: {switch.get('total_switches', 0)} 次")
        box_footer()

        if not err_tools.get("problem_tools") and not loops.get("loops") and total_stalls == 0:
            lines.append("")
            box_header("✅ 未检测到明显瓶颈", "🎉")
            lines.append("  │  工作流状态良好，继续保持！")
            box_footer()

        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_workflow_optimize(args: argparse.Namespace) -> None:
    """获取工作流优化建议 — 基于瓶颈和模式生成改进方案 (9D)"""
    from .cli_utils import section_blank, box_header, box_footer, bar_chart
    from .mirroring.workflow import WorkflowOptimizer

    optimizer = WorkflowOptimizer()
    result = optimizer.generate_advice()
    automation = optimizer.estimate_automation_potential()

    def _text():
        lines = []
        section_blank("工作流优化建议", "💡", phase="9D")

        grade = result.get("overall_grade", "N/A")
        score = result.get("overall_score", 0)
        grade_icon = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴"}.get(grade, "⚪")
        box_header(f"整体评分: {grade} ({score}/100)", grade_icon)
        lines.append(f"  │  建议总数: {result.get('total', 0)} 条")
        lines.append(f"  │  高优先级: {result.get('high_priority', 0)} 条")
        box_footer()

        suggestions = result.get("suggestions", [])
        if not suggestions:
            lines.append("")
            box_header("✅ 工作流状态良好", "🎉")
            lines.append("  │  暂无优化建议，继续保持！")
            box_footer()
        else:
            lines.append("")
            for i, s in enumerate(suggestions, 1):
                priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s["priority"], "⚪")
                box_header(f"建议 #{i} [{s['priority']}]", priority_icon)
                lines.append(f"  │  {s['message']}")
                lines.append(f"  │  [dim]💡 {s['action']}[/dim]")
                box_footer()
                lines.append("")

        # 自动化潜力
        box_header("自动化潜力评估", "🤖")
        ac = automation.get("automation_candidates", [])
        if ac:
            lines.append(f"  │  预估时间节省: {automation.get('estimated_time_saving', 'N/A')}")
            lines.append(f"  │  可优化项:")
            for c in ac:
                lines.append(f"  │    • {c['suggestion']}")
        else:
            lines.append("  │  [dim]暂未发现可自动化的工作流[/dim]")
        box_footer()

        lines.append("")
        return "\n".join(lines)

    result["automation"] = automation
    cli_output(result, args, text=_text)


# ================================================================
# 9P: 代理能力发现与智能路由命令
# ================================================================


def register_workflow_parser(subparsers) -> None:
    """注册 workflow 子命令组。"""
    workflow_parser = subparsers.add_parser("workflow", help="工作流模式识别（Phase 9D）")
    workflow_sub = workflow_parser.add_subparsers(dest="workflow_action", help="工作流操作")

    workflow_patterns_p = workflow_sub.add_parser("patterns", help="发现工作流模式")
    workflow_patterns_p.set_defaults(func=cmd_workflow_patterns)

    workflow_bottlenecks_p = workflow_sub.add_parser("bottlenecks", help="查看工作流瓶颈")
    workflow_bottlenecks_p.set_defaults(func=cmd_workflow_bottlenecks)

    workflow_optimize_p = workflow_sub.add_parser("optimize", help="获取工作流优化建议")
    workflow_optimize_p.set_defaults(func=cmd_workflow_optimize)

    # ── 9P: 代理能力发现与智能路由 ──
