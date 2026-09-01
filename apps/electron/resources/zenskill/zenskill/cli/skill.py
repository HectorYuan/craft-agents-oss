"""skill 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

from ..cli_helpers import _str_section, _str_box_header, _str_box_footer

from ..cli_utils import output as cli_output
from ..core.paths import SkillStateManager


def cmd_skill_status(args: argparse.Namespace) -> None:
    """查询技能修炼状态"""
    mgr = SkillStateManager(args.skill_id)
    state = mgr.load()

    level = state.get('level', 'NOVICE')
    usage = state.get('usage_count', 0)
    episodes = len(state.get('episodes', []))
    level_icons = {"NOVICE": "🌱", "APPRENTICE": "🌿", "ADEPT": "🪴",
                   "EXPERT": "🌳", "MASTER": "🏆"}
    level_colors = {"NOVICE": "🔵", "APPRENTICE": "🟢", "ADEPT": "🟡",
                    "EXPERT": "🟠", "MASTER": "🔴"}
    last_used = state.get('last_used')
    milestones = state.get('milestones', [])

    result = {
        "skill_id": args.skill_id,
        "level": level,
        "usage_count": usage,
        "episode_count": episodes,
        "last_used": last_used,
        "milestones": milestones,
    }

    def _text():
        lines = ["",
                 f"  🎯 技能修炼 — {args.skill_id}",
                 f"  {'═' * 62}",
                 "",
                 f"  ┌─ 🏆 核心状态 ────────────────────────────────────────────",
                 f"  │  {level_icons.get(level, '⚪')} 境界:     {level:12s} {level_colors.get(level, '⚪')}",
                 f"  │  使用次数:   {usage} 次",
                 f"  │  成长事件:   {episodes} 条"]
        if last_used:
            lines.append(f"  │  最后使用:   {last_used}")
        lines.append(f"  └───────────────────────────────────────────────────────────")

        if milestones:
            lines.append("")
            lines.append(f"  ┌─ 🏅 里程碑 ({len(milestones)}) ──────────────────────────────")
            for m in milestones:
                mlv = m.get('level', 'N/A')
                ach = m.get('achievement', 'N/A')
                lines.append(f"  │  🔹 {mlv}: {ach}")
            lines.append(f"  └───────────────────────────────────────────────────────────")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)



def cmd_skill_list(args: argparse.Namespace) -> None:
    """列出所有已注册技能"""
    # TODO: 从注册中心获取
    cli_output({"skills": [args.skill_id]}, args, text=lambda: (
        f"📦 已注册技能列表\n"
        f"{"=" * 60}\n"
        f"   {args.skill_id} - ZenSkill 核心技能\n\n"
        f"提示: 使用 'python -m zenskill skill status <skill_id>' 查看详细状态"
    ))



def cmd_skill_diff(args: argparse.Namespace) -> None:
    """对比两个版本的技能状态"""
    mgr = SkillStateManager(args.skill_id)
    result = mgr.diff_states(args.v1, args.v2)

    def _text():
        if not result.get("ok"):
            return f"❌ {result.get('error')} (共 {result.get('history_len', 0)} 条历史)"
        lines = [
            f"📊 状态对比: {args.skill_id}",
            "=" * 60,
            f"  v{result['v1']['index']}: {result['v1']['timestamp'][:19]} | {result['v1']['action']}",
            f"  v{result['v2']['index']}: {result['v2']['timestamp'][:19]} | {result['v2']['action']}",
            "", f"  episode: {result['episode_diff']['v1_count']} → {result['episode_diff']['v2_count']}",
        ]
        for key, change in result.get("changes", {}).items():
            lines.append(f"  {key}: {change['from']} → {change['to']}")
        return "\n".join(lines)

    cli_output(result, args, text=_text)



def cmd_skill_route(args: argparse.Namespace) -> None:
    """智能路由: 找到最匹配的技能能力"""
    from ..skill_router import skill_router
    from ..cli_utils import bar_chart

    # P3-1: 路由表与已安装技能库联动（DB 不可用时静默跳过）
    skill_router.sync_installed_skills()

    if getattr(args, 'list', False):
        caps = skill_router.list_capabilities()
        result_list = {"caps": caps}

        def _text_list():
            lines = []
            lines.append(_str_section("已注册技能能力", "🗺️"))
            for c in caps:
                b = bar_chart(c["proficiency"] * 100, 100, 10)
                lines.append(f"  {c['skill_id']:20s} {c['capability']:25s} {b} {c['proficiency']:.0%}")
            lines.append("")
            return "\n".join(lines)

        cli_output(result_list, args, text=_text_list)
        return

    task = args.task
    route_result = skill_router.route_task(task)

    def _text():
        lines = []
        lines.append(_str_section("技能路由", "🧭"))
        lines.append(_str_box_header("匹配结果"))
        lines.append(f"  │  任务:     {task[:60]}")
        lines.append(f"  │  技能:     {route_result['skill_id']}")
        if route_result['capability']:
            lines.append(f"  │  能力:     {route_result['capability']}")
        conf = route_result['confidence']
        b = bar_chart(conf * 100, 100, 10)
        lines.append(f"  │  置信度:   {b} {conf:.0%}")
        lines.append(f"  │  建议:     {route_result['suggestion']}")
        lines.append(_str_box_footer())
        lines.append("")
        return "\n".join(lines)

    cli_output(route_result, args, text=_text)


def cmd_skill_curve(args: argparse.Namespace) -> None:
    """学习曲线可视化 (7Q)"""
    from ..systems.cultivating.learning_curve import LearningCurveViz
    from ..core.paths import SkillStateManager
    import json

    sid = args.skill_id
    dim = getattr(args, 'dim', 'proficiency')
    mgr = SkillStateManager(sid)
    history = []

    if mgr.history_path.exists():
        for line in open(mgr.history_path):
            try:
                entry = json.loads(line.strip())
                snap = entry.get("snapshot", {})
                uc = snap.get("usage_count", 0)
                level = snap.get("level", "NOVICE")
                lb = {"NOVICE": 10, "APPRENTICE": 30, "ADEPT": 50,
                      "EXPERT": 70, "MASTER": 90}.get(level, 10)
                if uc > 0:
                    history.append({
                        "timestamp": entry.get("timestamp", ""),
                        "ability_scores": {
                            "proficiency": min(uc * 0.5, 100),
                            "stability": min(50 + uc * 0.2, 100),
                            "satisfaction": min(lb + (uc % 10) * 2, 100),
                            "responsiveness": min(60 + uc * 0.15, 100),
                            "memory": min(30 + uc * 0.3, 100),
                        },
                    })
            except Exception:
                pass

    dim_names = {"proficiency": "熟练度", "stability": "稳定性",
                 "satisfaction": "满意度", "responsiveness": "响应力", "memory": "记忆度"}
    title = f"{sid} — {dim_names.get(dim, dim)} 学习曲线"
    chart = LearningCurveViz.plot(history, dim=dim, title=title)
    cli_output({"skill_id": sid, "dimension": dim, "data_points": len(history)},
               args, text=lambda: f"\n{chart}\n")



def cmd_skill_forget(args: argparse.Namespace) -> None:
    """遗忘检测 (7S)"""
    from ..systems.cultivating.learning_curve import ForgettingCurveDetector
    from ..cli_utils import bar_chart

    detector = ForgettingCurveDetector()
    at_risk = detector.check_skills()
    suggestions = detector.get_review_plan() if at_risk else []

    result = {
        "skills_at_risk": at_risk,
        "suggestions": suggestions,
    }

    def _text():
        lines = []
        lines.append(_str_section("技能遗忘检测", "🧠", phase="7S"))

        if not at_risk:
            lines.append("  🟢 所有技能保持活跃，无遗忘风险")
            lines.append("")
            return "\n".join(lines)

        lines.append(_str_box_header("遗忘风险"))
        for skill in at_risk:
            b = bar_chart(skill["retention"], 100, 10)
            lines.append(f"  │  {skill['skill_id']:20s} {b} {skill['retention']:.0f}% 保留 "
                        f"({skill['days_inactive']:.0f} 天未用)")
        lines.append(_str_box_footer())

        if suggestions:
            lines.append("")
            lines.append(_str_box_header("复习建议"))
            for s in suggestions:
                lines.append(f"  │  📝 {s}")
            lines.append(_str_box_footer())
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)



def cmd_skill_break(args: argparse.Namespace) -> None:
    """7V: 智能间歇建议 — 番茄钟 + 疲劳检测 + 最佳时段"""
    from ..systems.active.break_advisor import BreakAdvisor

    advisor = BreakAdvisor()

    # 读取当前会话
    import json, time
    from pathlib import Path
    session_file = Path.home() / ".zenskill" / "session" / "current.json"
    tc, elapsed = 0, 0.0
    if session_file.exists():
        try:
            s = json.loads(session_file.read_text())
            tc = s.get("tool_count", 0)
            elapsed = (time.time() - s.get("started", time.time())) / 60
        except Exception:
            pass

    pomodoro_status = advisor.get_pomodoro_status(elapsed)
    suggestions = advisor.check(tc, elapsed)
    daily_rhythm = advisor.get_daily_rhythm()

    result = {
        "tool_count": tc, "elapsed_min": elapsed,
        "pomodoro_status": pomodoro_status,
        "suggestions": suggestions,
    }

    def _text():
        lines = []
        lines.append(_str_box_header("智能间歇建议 (7V)"))
        lines.append(f"  │  当前会话: {tc} 工具 | {elapsed:.0f} 分钟")
        lines.append(f"  │  {pomodoro_status}")
        lines.append(_str_box_footer())

        if suggestions:
            lines.append("")
            lines.append(_str_box_header("休息提醒"))
            for s in suggestions:
                icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}.get(s["priority"], "⚪")
                lines.append(f"  │  {icon} {s['message']}")
            lines.append(_str_box_footer())

        lines.append("")
        lines.append(daily_rhythm)
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)



def cmd_skill_transfer(args: argparse.Namespace) -> None:
    """跨技能迁移学习 (8E)"""
    from ..systems.collaboration.skill_transfer import SkillTransferEngine
    from ..cli_utils import bar_chart

    engine = SkillTransferEngine()
    patterns = engine.find_transferable_patterns()

    result = {"patterns": patterns}

    def _text():
        lines = []
        lines.append(_str_section("跨技能迁移学习", "🔄", phase="8E"))

        if not patterns:
            lines.append("  [dim]技能间差异不足, 暂无迁移建议[/dim]")
            lines.append("")
            return "\n".join(lines)

        for p in patterns:
            lines.append(_str_box_header(f"{p['source_skill']} → {p['target_skill']}"))
            lines.append(f"  │  源技能: {p['source_skill']} (综合分 {p['source_score']:.0f})")
            lines.append(f"  │  目标:   {p['target_skill']} (综合分 {p['target_score']:.0f})")
            gap = p['gap']
            b = bar_chart(gap, 100, 16)
            lines.append(f"  │  差距:   {b} {gap:.0f} 分")
            lines.append(f"  │")
            lines.append(f"  │  迁移建议:")
            for s in p['suggestions'][:3]:
                lines.append(f"  │  🔹 {s}")
            lines.append(_str_box_footer())
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)



def cmd_skill_predict(args: argparse.Namespace) -> None:
    """技能成长预测 (8F)"""
    from ..systems.collaboration.skill_transfer import GrowthPredictor
    from ..core.paths import SkillStateManager
    from ..cli_utils import bar_chart

    sid = args.skill_id
    mgr = SkillStateManager(sid)
    state = mgr.load()

    # 从 state history 构建数据
    history_file = mgr.history_path
    history = []
    import json
    if history_file.exists():
        for line in open(history_file):
            try:
                entry = json.loads(line.strip())
                snap = entry.get("snapshot", {})
                uc = snap.get("usage_count", 0)
                level = snap.get("level", "NOVICE")
                level_bonus = {"NOVICE": 10, "APPRENTICE": 30, "ADEPT": 50,
                               "EXPERT": 70, "MASTER": 90}.get(level, 10)
                if uc > 0:
                    history.append({
                        "timestamp": entry.get("timestamp", ""),
                        "ability_scores": {
                            "proficiency": min(uc * 0.5, 100),
                            "stability": min(50 + uc * 0.2, 100),
                            "satisfaction": min(level_bonus + (uc % 10) * 2, 100),
                            "responsiveness": min(60 + uc * 0.15, 100),
                            "memory": min(30 + uc * 0.3, 100),
                            "composite": min(level_bonus + uc * 0.2, 100),
                        },
                    })
            except Exception:
                pass

    if len(history) < 3:
        cli_output({"skill_id": sid, "data_points": len(history), "error": "insufficient_data"},
                   args, text=lambda: "  [dim]历史数据不足 (需要 3+ 数据点), 继续使用将自动积累[/dim]\n")
        return

    predictor = GrowthPredictor()
    pred_result = predictor.predict(history, days_ahead=14)

    if "error" in pred_result:
        cli_output({"skill_id": sid, "error": pred_result["error"]},
                   args, text=lambda: f"  [dim]{pred_result['error']}[/dim]\n")
        return

    dims = pred_result["dimensions"]

    def _text():
        lines = []
        lines.append(_str_section(f"技能成长预测: {sid}", "📈", phase="8F"))
        lines.append(_str_box_header("14 天预测"))
        for dim, info in dims.items():
            cur = info["current"]
            pred = info["predicted"]
            growth = info["weekly_growth"]
            b_cur = bar_chart(cur, 100, 12)
            b_pred = bar_chart(pred, 100, 12)
            arrow = "↗" if growth > 0 else "→" if growth == 0 else "↘"
            lines.append(f"  │  {info['name']:6s} 当前: {b_cur} {cur:.0f}")
            lines.append(f"  │         预测: {b_pred} {pred:.0f}  ({arrow} +{growth:.1f}/周)")
            if info["stagnation"]:
                lines.append(f"  │  ⚠️  {info['stagnation_msg']}")
        lines.append(_str_box_footer())
        lines.append("")
        lines.append(f"  📊 平均周增长率: +{pred_result['avg_weekly_growth']:.1f} 分")
        fastest = pred_result.get("fastest_name", "")
        if fastest:
            lines.append(f"  🚀 增长最快: {fastest} (+{pred_result.get('fastest_growth', 0):.1f}/周)")
        if pred_result.get("stagnant_dimensions", 0) > 0:
            lines.append(f"  ⚠️ 停滞维度: {pred_result['stagnant_dimensions']} 个")
        lines.append("")
        return "\n".join(lines)

    cli_output(pred_result, args, text=_text)



def cmd_skill_define(args: argparse.Namespace) -> None:
    """用自然语言定义新技能 (9F-9G)"""
    from ..skill_dsl import SkillNLParser

    parser = SkillNLParser()
    skill = parser.parse(args.description, name=getattr(args, 'name', None))

    # ── 自动注册技能状态（Issue #1 修复）──
    from ..core.paths import SkillStateManager
    mgr = SkillStateManager(skill.name)
    mgr.save({
        **(mgr._default_state()),
        "category": skill.category,
        "difficulty": skill.difficulty,
        "weights": {
            "proficiency": skill.proficiency_weight,
            "stability": skill.stability_weight,
            "satisfaction": skill.satisfaction_weight,
            "responsiveness": skill.responsiveness_weight,
            "memory": skill.memory_weight,
        },
    }, action="skill_define")

    output_path = getattr(args, 'output', None)
    if output_path:
        from pathlib import Path
        Path(output_path).write_text(skill.to_markdown(), encoding="utf-8")

    cli_result = {
        "name": skill.name, "category": skill.category,
        "difficulty": skill.difficulty, "tools": skill.tools,
        "weights": {
            "proficiency": skill.proficiency_weight,
            "stability": skill.stability_weight,
            "satisfaction": skill.satisfaction_weight,
            "responsiveness": skill.responsiveness_weight,
            "memory": skill.memory_weight,
        },
        "practice_tasks": skill.practice_tasks,
        "output_path": str(output_path) if output_path else None,
    }

    def _text():
        lines = []
        lines.append(_str_section("技能定义", "📝", phase="9F-9G"))
        lines.append(_str_box_header("解析结果"))
        lines.append(f"  │  名称:   {skill.name}")
        lines.append(f"  │  分类:   {skill.category}")
        lines.append(f"  │  难度:   {skill.difficulty}")
        lines.append(f"  │  工具:   {', '.join(skill.tools) or '(无)'}")
        lines.append(_str_box_footer())
        lines.append("")
        lines.append(_str_box_header("五维权重"))
        dims = [
            ("熟练度", skill.proficiency_weight),
            ("稳定性", skill.stability_weight),
            ("满意度", skill.satisfaction_weight),
            ("响应力", skill.responsiveness_weight),
            ("记忆力", skill.memory_weight),
        ]
        for name, w in dims:
            bar_len = int(w * 20)
            bar = "█" * bar_len + "·" * (20 - bar_len)
            lines.append(f"  │  {name:6s}  {bar}  {w:.0%}")
        lines.append(_str_box_footer())
        if skill.practice_tasks:
            lines.append("")
            lines.append(_str_box_header("练习任务"))
            for i, t in enumerate(skill.practice_tasks, 1):
                lines.append(f"  │  {i}. [{t['level']}] {t['description']}")
            lines.append(_str_box_footer())
        if output_path:
            lines.append(f"\n  📄 已导出 Markdown: {output_path}")
        else:
            lines.append(f"\n  💡 使用 --output <path> 导出为 Markdown 文件")
        lines.append("")
        return "\n".join(lines)

    cli_output(cli_result, args, text=_text)



def cmd_skill_generate(args: argparse.Namespace) -> None:
    """从 DSL 生成可执行技能代码 (9J)"""
    from ..skill_dsl import SkillNLParser, SkillCodeGenerator
    from pathlib import Path

    parser = SkillNLParser()
    skill = parser.parse(args.description, name=getattr(args, 'name', None))
    generator = SkillCodeGenerator()

    code = generator.generate(skill)
    output_path = getattr(args, 'output', None)

    if output_path:
        Path(output_path).write_text(code, encoding="utf-8")
    else:
        # 默认输出到 skills/ 目录
        skill_id = generator._to_skill_id(skill.name)
        default_dir = Path.home() / ".zenskill" / "skills"
        default_dir.mkdir(parents=True, exist_ok=True)
        output_path = default_dir / f"{skill_id}.py"
        output_path.write_text(code, encoding="utf-8")

    result = {
        "skill_id": generator._to_skill_id(skill.name),
        "skill_name": skill.name,
        "category": skill.category,
        "difficulty": skill.difficulty,
        "generated_file": str(output_path),
        "code_lines": len(code.splitlines()),
    }

    def _text():
        lines = []
        from ..cli_utils import section_blank, box_header, box_footer
        section_blank("技能代码生成", "⚙️", phase="9J")
        box_header("生成结果")
        lines.append(f"  │  技能 ID:   {result['skill_id']}")
        lines.append(f"  │  技能名:    {result['skill_name']}")
        lines.append(f"  │  分类/难度:  {result['category']} / {result['difficulty']}")
        lines.append(f"  │  代码行数:   {result['code_lines']}")
        lines.append(f"  │  输出文件:   {result['generated_file']}")
        box_footer()
        lines.append("")
        box_header("生成内容")
        lines.append(f"  │  ✅ SkillManifest 子类")
        lines.append(f"  │  ✅ TaskGenerator（{len(skill.practice_tasks)} 个任务）")
        lines.append(f"  │  ✅ SkillEvaluator（评估函数）")
        lines.append(f"  │  ✅ PromptTemplates（4 角色）")
        lines.append(f"  │  ✅ MemoryConfig（记忆索引）")
        box_footer()
        lines.append(f"\n  💡 运行: python {output_path}")
        lines.append(f"  💡 立即开始: zenskill skill status --skill-id {result['skill_id']}")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)



def cmd_skill_optimize(args: argparse.Namespace) -> None:
    """优化技能定义 (9K)"""
    import json
    from pathlib import Path
    from ..skill_dsl import SkillOptimizer, SkillNLParser

    feedback_file = getattr(args, 'feedback', None)
    feedback_log = []

    if feedback_file:
        try:
            feedback_log = json.loads(Path(feedback_file).read_text(encoding="utf-8"))
        except Exception:
            pass

    analysis = SkillOptimizer.analyze_feedback(feedback_log)

    result = {
        "completion_rate": analysis.get("completion_rate", 0),
        "avg_score": analysis.get("avg_score", 0),
        "avg_duration_min": analysis.get("avg_duration_min", 0),
        "suggestions": analysis.get("suggestions", []),
        "adjustment_needed": analysis.get("adjustment_needed", False),
        "entries_analyzed": len(feedback_log),
    }

    def _text():
        lines = []
        from ..cli_utils import section_blank, box_header, box_footer, bar_chart
        section_blank("技能反馈分析", "🔍", phase="9K")

        if len(feedback_log) == 0:
            lines.append("  [dim]无反馈数据，使用技能后将自动生成分析[/dim]")
            lines.append("")
            return "\n".join(lines)

        box_header(f"分析摘要 ({len(feedback_log)} 条反馈)")
        lines.append(f"  │  完成率: {analysis['completion_rate']:.0%}")
        lines.append(f"  │  平均分: {analysis['avg_score']:.1f}")
        lines.append(f"  │  平均耗时: {analysis['avg_duration_min']:.0f} 分钟")
        lines.append(f"  │  需调整: {'是' if analysis['adjustment_needed'] else '否'}")
        box_footer()

        if analysis.get("suggestions"):
            lines.append("")
            box_header("优化建议", "💡")
            for s in analysis["suggestions"]:
                lines.append(f"  │  • {s}")
            box_footer()

        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)



def cmd_skill_testgen(args: argparse.Namespace) -> None:
    """LLM 自动生成技能测试用例 (9I)"""
    import asyncio
    from ..skill_dsl import SkillNLParser, SkillTestGenerator

    parser = SkillNLParser()
    skill = parser.parse(args.description, name=getattr(args, 'name', None))

    # 生成测试
    print(f"  ⏳ 正在用 LLM 生成 {skill.name} 的测试用例...")
    generator = SkillTestGenerator()
    tests = asyncio.run(generator.generate(skill))

    if not tests:
        cli_output({"ok": False, "skill_name": skill.name, "test_count": 0},
                   args, text=lambda: f"  🔴 LLM 生成失败，请稍后重试\n")
        return

    result = {"skill_name": skill.name, "test_count": len(tests), "tests": tests}

    def _text():
        lines = []
        lines.append(_str_section("LLM 测试生成", "🧪", phase="9I"))
        lines.append(_str_box_header(f"测试用例: {skill.name} ({len(tests)} 个)"))
        for i, t in enumerate(tests, 1):
            diff_icon = {"beginner": "🟢", "intermediate": "🟡", "advanced": "🔴"}
            icon = diff_icon.get(t.get("difficulty", "beginner"), "⚪")
            lines.append(f"  │  {i}. {icon} {t.get('test_name', 'N/A')} ({t.get('points', 5)} 分)")
            lines.append(f"  │     场景: {t.get('scenario', '')}")
            lines.append(f"  │     预期: {t.get('expected', '')}")
            lines.append("")
        lines.append(_str_box_footer())
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


# ── 8I: 模板库命令 ──


def cmd_skill_template(args: argparse.Namespace) -> None:
    """生成技能模板/计划/清单 (9H)"""
    from ..skill_dsl import SkillNLParser, SkillTemplateEngine

    parser = SkillNLParser()
    engine = SkillTemplateEngine()
    skill = parser.parse(args.description)
    fmt = getattr(args, 'format', 'plan')
    days = getattr(args, 'days', 7)

    templates = {
        "skill.md": ("SKILL.md", engine.render_skill_md(skill)),
        "plan": ("练习计划", engine.render_practice_plan(skill, days=days)),
        "checklist": ("掌握清单", engine.render_checklist(skill)),
    }
    label, content = templates.get(fmt, templates["plan"])

    output_path = getattr(args, 'output', None)
    if output_path:
        from pathlib import Path
        Path(output_path).write_text(content, encoding="utf-8")

    result = {
        "template_type": fmt,
        "label": label,
        "content": content,
        "output_path": str(output_path) if output_path else None,
    }

    def _text():
        lines = [f"\n  📋 技能模板: {label} — Phase 9H",
                 f"  {'═' * 62}", ""]
        lines.append(content)
        if output_path:
            lines.append(f"\n  📄 已保存到: {output_path}")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)



def cmd_skill_info(args: argparse.Namespace) -> None:
    """技能全貌：Claude Code + ZenSkill 技能信息"""
    import json
    import os
    import re
    from pathlib import Path
    from collections import Counter
    from ..cli_utils import bar_chart

    # ── 1. 读取数据源 ──
    settings = {}
    settings_path = Path.home() / ".claude" / "settings.json"
    if settings_path.exists():
        with open(settings_path) as f:
            settings = json.load(f)

    plugins = settings.get("enabledPlugins", {})

    # ZenSkill 状态
    state_path = Path.home() / ".zenskill" / "states" / f"{args.skill_id}.json"
    zen_state = {}
    if state_path.exists():
        with open(state_path) as f:
            zen_state = json.load(f)

    # 已安装 skill 元数据 (SKILL.md frontmatter)
    from ..skills.frontmatter import parse_skill_md

    skills_dir = Path.home() / ".claude" / "skills"
    skill_metas = []
    if skills_dir.exists():
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            md = skill_dir / "SKILL.md"
            if md.exists():
                meta, _body = parse_skill_md(md)
                meta_d = meta.to_dict()
                meta_d["_dir"] = skill_dir.name
                skill_metas.append(meta_d)

    # 预计算统计
    episodes = zen_state.get("episodes", [])
    action_counts = Counter()
    if episodes:
        for ep in episodes[-50:]:
            action_counts[ep.get("action", "unknown")[:20]] += 1
    milestones = zen_state.get("milestones", [])
    level = zen_state.get("level", "NOVICE")
    usage = zen_state.get("usage_count", 0)

    cwd_count = Counter()
    history_path = Path.home() / ".claude" / "history.jsonl"
    if history_path.exists():
        for line in open(history_path):
            try:
                entry = json.loads(line.strip())
                proj = entry.get("project", "")
                if proj:
                    cwd_count[Path(proj).name] += 1
            except Exception:
                pass

    cli_result = {
        "claude_code": {
            "enabled_plugins": list(plugins.keys()),
            "installed_skills": [m.get('name', m.get('_dir', '')) for m in skill_metas],
            "total_enabled": len(plugins),
            "total_installed": len(skill_metas),
        },
        "zenskill": {
            "skill_id": zen_state.get("skill_id", ""),
            "level": level,
            "usage_count": usage,
            "last_used": zen_state.get("last_used", ""),
            "milestones_count": len(milestones),
        },
    }

    def _text():
        level_icons = {"NOVICE": "🌱", "APPRENTICE": "🌿", "ADEPT": "🪴",
                       "EXPERT": "🌳", "MASTER": "🏆"}
        lines = []
        lines.append(_str_section("技能全貌", "🛠️"))

        # Claude Code 技能
        lines.append(_str_box_header("Claude Code 技能", "🤖"))
        lines.append(f"  │  已启用: {len(plugins)} 个")
        for name in plugins:
            display = name.replace("@claude-plugins-official", "").replace("@zenskill-marketplace", "")
            lines.append(f"  │  🟢 {display}")
        if skill_metas:
            lines.append(f"  │")
            lines.append(f"  │  已安装: {len(skill_metas)} 个")
            for m in skill_metas:
                desc = m.get("description", "")[:60]
                lines.append(f"  │  📦 {m['_dir'][:30]:30s} {desc}")
        lines.append(_str_box_footer())

        # ZenSkill 修炼
        lines.append("")
        lines.append(_str_box_header("ZenSkill 修炼", "🧘"))
        lines.append(f"  │  {level_icons.get(level, '⚪')} 境界:   {level}")
        lines.append(f"  │  使用次数: {usage}")
        lines.append(f"  │  最后活跃: {str(zen_state.get('last_used', ''))[:19]}")
        if episodes:
            lines.append(f"  │")
            lines.append(f"  │  最近 {min(50, len(episodes))} 次操作类型:")
            for action, count in action_counts.most_common(5):
                b = bar_chart(count, max(action_counts.values()), 10)
                lines.append(f"  │    {action:20s} {b} {count}")
        if milestones:
            lines.append(f"  │  里程碑: {len(milestones)} 个")
            for m in milestones:
                lines.append(f"  │    🏅 {m.get('level', '')}: {m.get('achievement', '')}")
        lines.append(_str_box_footer())

        # 使用统计
        lines.append("")
        lines.append(_str_box_header("使用统计", "📊"))
        if cwd_count:
            total = sum(cwd_count.values())
            for proj, count in cwd_count.most_common(5):
                pct = count / total * 100
                b = bar_chart(pct, 100, 12)
                lines.append(f"  │  {proj:20s} {b} {pct:.0f}%")
        else:
            lines.append(f"  │  [dim]暂无使用数据[/dim]")
        lines.append(_str_box_footer())

        lines.append(f"\n  💡 共 {len(plugins)} 个 Claude Code 技能 + 1 个 ZenSkill 修炼  |  技能信息每 5 分钟自动更新")
        lines.append("")
        return "\n".join(lines)

    cli_output(cli_result, args, text=_text)



def cmd_skill_lint(args: argparse.Namespace) -> None:
    """技能 lint：SKILL.md frontmatter 校验 + 目录结构建议 (P0-2)"""
    from pathlib import Path

    from ..skills.frontmatter import parse_skill_md, validate_frontmatter

    target = Path(args.path).expanduser()
    if target.is_file():
        skill_dir, skill_md = target.parent, target
    else:
        skill_dir, skill_md = target, target / "SKILL.md"

    errors: list = []
    warnings: list = []
    meta = None
    body = ""

    if not skill_md.exists():
        errors.append(f"SKILL.md 不存在: {skill_md}")
    else:
        meta, body = parse_skill_md(skill_md)
        errors.extend(validate_frontmatter(meta))

        from ..skills.skill_optimizer import estimate_tokens
        result["body_tokens"] = estimate_tokens(body)

        if not body.strip():
            errors.append("正文为空")
        elif len(body.splitlines()) > 200:
            warnings.append(
                f"正文 {len(body.splitlines())} 行超过 200 行，"
                "建议把细节章节抽到 references/（渐进式披露）"
            )

        if not (skill_dir / "references").exists():
            warnings.append("缺少 references/ 子目录（可选，存放扩展文档）")
        if not (skill_dir / "examples").exists():
            warnings.append("缺少 examples/ 子目录（可选，存放示例）")

    result = {
        "path": str(skill_dir),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }
    if meta:
        result["name"] = meta.name
        result["version"] = meta.version

    def _text():
        lines = [f"\n  技能 lint: {skill_dir}", "  " + "─" * 50]
        for e in errors:
            lines.append(f"  [错误] {e}")
        for w in warnings:
            lines.append(f"  [警告] {w}")
        if not errors and not warnings:
            lines.append("  [通过] 全部检查通过")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)

    if errors:
        raise SystemExit(1)



def cmd_skill_slim(args: argparse.Namespace) -> None:
    """SKILL.md 瘦身: 超预算章节抽取到 references/ (P2-1)"""
    from ..skills.skill_optimizer import optimize_skill_md

    report = optimize_skill_md(
        args.path,
        max_tokens=args.max_tokens,
        budget=args.budget,
        dry_run=args.dry_run,
    )

    def _text():
        r = report
        mode = "（dry-run 预览）" if r.dry_run else ""
        lines = [
            f"\n  技能优化{mode}: {r.path}",
            "  " + "─" * 50,
            f"  正文行数: {r.original_lines} → {r.optimized_lines}",
            f"  token 估算: {r.original_tokens} → {r.optimized_tokens}（预算 {r.budget}）",
        ]
        if r.extracted:
            lines.append(f"  抽取章节: {len(r.extracted)} 个")
            for item in r.extracted:
                lines.append(
                    f"    - {item['section']}（{item['lines']} 行）→ {item['file']}"
                )
        else:
            lines.append("  未达抽取条件，内容不变")
        lines.append("")
        return "\n".join(lines)

    cli_output(report.to_dict(), args, text=_text)



def cmd_skill_deps(args: argparse.Namespace) -> None:
    """技能依赖: 拓扑安装序 + 缺失/环/版本冲突检查 (P2-2)"""
    from ..core.dependency_resolver import resolve_skill

    result = resolve_skill(args.skill_id)

    payload = {
        "skill_id": args.skill_id,
        "ok": result.ok,
        "install_order": result.order,
        "missing": result.missing,
        "cycles": result.cycles,
        "conflicts": result.conflicts,
    }

    def _text():
        lines = [f"\n  依赖解析: {args.skill_id}", "  " + "─" * 50]
        if result.order:
            lines.append("  安装顺序（依赖在前）:")
            for i, sid in enumerate(result.order, 1):
                lines.append(f"    {i}. {sid}")
        for m in result.missing:
            lines.append(f"  [缺失] {m} 未注册")
        for c in result.cycles:
            lines.append(f"  [环] {' → '.join(c)} → {c[0]}")
        for c in result.conflicts:
            lines.append(
                f"  [冲突] {c['skill']} 依赖 {c['dep']} {c['constraint']}，"
                f"实际 {c['installed_version']}"
            )
        if result.ok:
            lines.append("  [通过] 依赖完整，无环，版本满足约束")
        lines.append("")
        return "\n".join(lines)

    cli_output(payload, args, text=_text)

    if not result.ok and not getattr(args, "no_fail", False):
        raise SystemExit(1)



def register_skill_parser(subparsers) -> None:
    """注册 skill 子命令组。"""
    skill_parser = subparsers.add_parser("skill", help="技能管理")
    skill_subparsers = skill_parser.add_subparsers(dest="subcommand", help="技能操作")

    # skill status
    status_parser = skill_subparsers.add_parser("status", help="查询修炼状态")
    status_parser.set_defaults(func=cmd_skill_status)

    # skill list
    skill_list_parser = skill_subparsers.add_parser("list", help="列出所有技能")
    skill_list_parser.set_defaults(func=cmd_skill_list)

    # skill metrics
    metrics_parser = skill_subparsers.add_parser("metrics", help="显示使用指标")
    metrics_parser.set_defaults(func=cmd_metrics)

    # skill history
    history_parser = skill_subparsers.add_parser("history", help="查看状态历史")
    history_parser.add_argument("--n", type=int, default=10, help="显示最近 N 条")
    history_parser.set_defaults(func=cmd_history)

    # skill rollback
    rollback_parser = skill_subparsers.add_parser("rollback", help="回滚状态")
    rollback_parser.add_argument("--n", type=int, default=1, help="回滚步数")
    rollback_parser.set_defaults(func=cmd_rollback)

    # skill snapshot (8W+8X: 快照管理)
    snapshot_parser = skill_subparsers.add_parser("snapshot", help="管理状态快照 (8W)")
    snap_sub = snapshot_parser.add_subparsers(dest="snap_action", help="快照操作")
    snap_list_parser = snap_sub.add_parser("list", help="列出历史快照")
    snap_list_parser.add_argument("--n", type=int, default=20, help="显示条数")
    snap_list_parser.set_defaults(func=cmd_snapshot_list)
    snap_save_parser = snap_sub.add_parser("save", help="创建命名快照")
    snap_save_parser.add_argument("--name", required=True, help="快照名称")
    snap_save_parser.set_defaults(func=cmd_snapshot_save)
    snap_restore_parser = snap_sub.add_parser("restore", help="恢复到命名快照")
    snap_restore_parser.add_argument("name", help="快照名称")
    snap_restore_parser.set_defaults(func=cmd_snapshot_restore)

    # skill diff (8X: 版本对比)
    diff_parser = skill_subparsers.add_parser("diff", help="对比两个版本的状态差异 (8X)")
    diff_parser.add_argument("--v1", type=int, required=True, help="旧版本号 (history index)")
    diff_parser.add_argument("--v2", type=int, required=True, help="新版本号 (history index)")
    diff_parser.set_defaults(func=cmd_skill_diff)

    # skill branch (8W: 学习分支)
    branch_parser = skill_subparsers.add_parser("branch", help="管理学习分支 (8W)")
    branch_sub = branch_parser.add_subparsers(dest="branch_action", help="分支操作")
    branch_create_parser = branch_sub.add_parser("create", help="创建学习分支")
    branch_create_parser.add_argument("branch_name", help="分支名称")
    branch_create_parser.set_defaults(func=cmd_branch_create)
    branch_list_parser = branch_sub.add_parser("list", help="列出所有分支")
    branch_list_parser.set_defaults(func=cmd_branch_list)

    # skill info (Claude Code 技能全貌)
    skill_info_parser = skill_subparsers.add_parser("info", help="技能全貌（Claude Code + ZenSkill）")
    skill_info_parser.add_argument("--json", action="store_true", help="JSON 输出")
    skill_info_parser.set_defaults(func=cmd_skill_info)

    # skill lint (P0-2: frontmatter 校验)
    skill_lint_parser = skill_subparsers.add_parser("lint", help="技能 lint — SKILL.md 校验 + 目录结构建议")
    skill_lint_parser.add_argument("path", help="技能目录或 SKILL.md 文件路径")
    skill_lint_parser.add_argument("--json", action="store_true", help="JSON 输出")
    skill_lint_parser.set_defaults(func=cmd_skill_lint)

    # skill slim (P2-1: 瘦身 + token 预算；与 Phase 9K 的 optimize 反馈优化区分)
    skill_slim_parser = skill_subparsers.add_parser("slim", help="SKILL.md 瘦身 — 超预算章节抽取到 references/")
    skill_slim_parser.add_argument("path", help="技能目录或 SKILL.md 文件路径")
    skill_slim_parser.add_argument("--max-tokens", type=int, help="正文 token 预算")
    skill_slim_parser.add_argument("--budget", choices=["tight", "normal", "loose"], help="预算档位（500/2000/8000）")
    skill_slim_parser.add_argument("--dry-run", action="store_true", help="只出报告不写盘")
    skill_slim_parser.add_argument("--json", action="store_true", help="JSON 输出")
    skill_slim_parser.set_defaults(func=cmd_skill_slim)

    # skill deps (P2-2: 依赖解析)
    skill_deps_parser = skill_subparsers.add_parser("deps", help="技能依赖解析 — 拓扑安装序 + 缺失/环/版本冲突")
    skill_deps_parser.add_argument("skill_id", help="技能 ID")
    skill_deps_parser.add_argument("--json", action="store_true", help="JSON 输出")
    skill_deps_parser.set_defaults(func=cmd_skill_deps)

    # skill check-deps（deps 的检查别名，语义更显式）
    skill_checkdeps_parser = skill_subparsers.add_parser("check-deps", help="检查技能依赖完整性（问题非零退出）")
    skill_checkdeps_parser.add_argument("skill_id", help="技能 ID")
    skill_checkdeps_parser.add_argument("--json", action="store_true", help="JSON 输出")
    skill_checkdeps_parser.set_defaults(func=cmd_skill_deps)

    # skill route (深度融合: 智能路由)
    skill_route_parser = skill_subparsers.add_parser("route", help="智能路由: 找到最匹配的技能能力")
    skill_route_parser.add_argument("task", help="任务描述")
    skill_route_parser.add_argument("--list", action="store_true", help="列出所有能力")
    skill_route_parser.set_defaults(func=cmd_skill_route)

    # skill transfer (8E: 跨技能迁移)
    skill_transfer_parser = skill_subparsers.add_parser("transfer", help="跨技能迁移学习 (8E)")
    skill_transfer_parser.set_defaults(func=cmd_skill_transfer)

    # skill predict (8F: 成长预测)
    skill_predict_parser = skill_subparsers.add_parser("predict", help="技能成长预测 (8F)")
    skill_predict_parser.set_defaults(func=cmd_skill_predict)

    # skill curve (7Q: 学习曲线)
    skill_curve_parser = skill_subparsers.add_parser("curve", help="学习曲线可视化 (7Q)")
    skill_curve_parser.add_argument("--dim", default="proficiency", help="维度名称")
    skill_curve_parser.set_defaults(func=cmd_skill_curve)

    # skill forget (7S: 遗忘曲线)
    skill_forget_parser = skill_subparsers.add_parser("forget", help="遗忘检测 — 长时间未使用的技能 (7S)")
    skill_forget_parser.set_defaults(func=cmd_skill_forget)

    # skill break (7V: 智能间歇建议)
    skill_break_parser = skill_subparsers.add_parser("break", help="智能间歇建议 — 番茄钟 + 疲劳 + 最佳时段 (7V)")
    skill_break_parser.set_defaults(func=cmd_skill_break)

    # skill tutor (8Y: 智能导师引擎)
    tutor_parser = skill_subparsers.add_parser("tutor", help="智能导师 — 学习风格/错误诊断/自适应建议 (8Y)")
    tutor_parser.set_defaults(func=cmd_tutor)

    # skill define (9F-9G: NL 定义技能)
    skill_define_parser = skill_subparsers.add_parser("define", help="用自然语言定义新技能（Phase 9F-9G）")
    skill_define_parser.add_argument("description", help="技能的自然语言描述")
    skill_define_parser.add_argument("--name", help="技能名称（可选，自动提取）")
    skill_define_parser.add_argument("--output", help="输出 Markdown 文件路径")
    skill_define_parser.set_defaults(func=cmd_skill_define)

    # skill template list (8I: 预置模板库)
    skill_template_parser = skill_subparsers.add_parser("template", help="技能模板库 (8I+9H)")
    tmpl_sub = skill_template_parser.add_subparsers(dest="tmpl_action", help="模板操作")
    tmpl_list_parser = tmpl_sub.add_parser("list", help="列出预置模板")
    tmpl_list_parser.add_argument("--category", choices=["coding", "writing", "devops", "analysis", "learning", "productivity", "communication"], help="按分类筛选")
    tmpl_list_parser.add_argument("--difficulty", choices=["beginner", "intermediate", "advanced", "expert"], help="按难度筛选")
    tmpl_list_parser.set_defaults(func=cmd_template_list)
    tmpl_use_parser = tmpl_sub.add_parser("use", help="使用模板创建技能")
    tmpl_use_parser.add_argument("template_name", help="模板名称")
    tmpl_use_parser.add_argument("--skill-id", help="技能 ID（默认使用模板名）")
    tmpl_use_parser.set_defaults(func=cmd_template_use)
    tmpl_info_parser = tmpl_sub.add_parser("info", help="查看模板详情")
    tmpl_info_parser.add_argument("template_name", help="模板名称")
    tmpl_info_parser.set_defaults(func=cmd_template_info)
    # legacy: 直接 skill template <desc> (9H 模板引擎)
    tmpl_gen_parser = tmpl_sub.add_parser("generate", help="从描述生成技能模板")
    tmpl_gen_parser.add_argument("description", help="技能描述")
    tmpl_gen_parser.add_argument("--format", choices=["skill.md", "plan", "checklist"], default="plan", help="输出格式")
    tmpl_gen_parser.add_argument("--days", type=int, default=7, help="练习计划天数")
    tmpl_gen_parser.add_argument("--output", help="输出文件路径")
    tmpl_gen_parser.set_defaults(func=cmd_skill_template)

    # skill testgen (9I: LLM 测试生成)
    skill_testgen_parser = skill_subparsers.add_parser("testgen", help="自动生成技能测试用例（Phase 9I）")
    skill_testgen_parser.add_argument("description", help="技能描述")
    skill_testgen_parser.add_argument("--name", help="技能名称")
    skill_testgen_parser.set_defaults(func=cmd_skill_testgen)

    # skill generate (9J: 代码生成)
    skill_generate_parser = skill_subparsers.add_parser("generate", help="从 DSL 生成可执行代码（Phase 9J）")
    skill_generate_parser.add_argument("description", help="技能描述")
    skill_generate_parser.add_argument("--name", help="技能名称")
    skill_generate_parser.add_argument("--output", help="输出文件路径")
    skill_generate_parser.set_defaults(func=cmd_skill_generate)

    # skill optimize (9K: 反馈优化)
    skill_optimize_parser = skill_subparsers.add_parser("optimize", help="优化技能定义（Phase 9K）")
    skill_optimize_parser.add_argument("--feedback", help="反馈日志 JSON 文件路径")
    skill_optimize_parser.set_defaults(func=cmd_skill_optimize)

    # reflect 命令组
    from .reflect import register_reflect_parser
    register_reflect_parser(subparsers)

def cmd_metrics(args: argparse.Namespace) -> None:
    """显示使用指标"""
    mgr = SkillStateManager(args.skill_id)
    metrics = mgr.get_metrics()

    cli_output({
        "skill_id": args.skill_id,
        "total_executions": metrics.get('total_executions', 0),
        "successful_executions": metrics.get('successful_executions', 0),
        "success_rate": metrics.get('success_rate', 0),
        "total_duration_ms": metrics.get('total_duration_ms', 0),
        "avg_duration_ms": metrics.get('avg_duration_ms', 0),
    }, args, text=lambda: (
        f"📊 技能使用指标: {args.skill_id}\n"
        f"{"=" * 60}\n"
        f"   总执行次数:    {metrics.get('total_executions', 0)} 次\n"
        f"   成功次数:      {metrics.get('successful_executions', 0)} 次\n"
        f"   成功率:        {metrics.get('success_rate', 0):.2%}\n"
        f"   总耗时:        {metrics.get('total_duration_ms', 0):.0f}ms\n"
        f"   平均耗时:      {metrics.get('avg_duration_ms', 0):.2f}ms"
    ))



def cmd_history(args: argparse.Namespace) -> None:
    """显示状态历史"""
    mgr = SkillStateManager(args.skill_id)
    history = mgr.get_history(limit=args.n)
    summary = mgr.get_history_summary()

    items = [{"index": i, "timestamp": h['timestamp'], "action": h['action']}
             for i, h in enumerate(reversed(history), 1)]

    def _text():
        lines = [f"📜 状态历史记录: {args.skill_id}", "=" * 60,
                 f"   总版本数:      {summary['total_versions']}",
                 f"   首次记录:      {summary.get('first_version', 'N/A')}",
                 f"   最近记录:      {summary.get('last_version', 'N/A')}",
                 "", f"   最近 {len(history)} 次操作:"]
        for i, h in enumerate(reversed(history), 1):
            lines.append(f"   {i:2d}. [{h['timestamp']}] {h['action']}")
        return "\n".join(lines)

    cli_output({
        "skill_id": args.skill_id,
        "total_versions": summary['total_versions'],
        "first_version": summary.get('first_version'),
        "last_version": summary.get('last_version'),
        "recent_actions": items,
    }, args, text=_text)



def cmd_rollback(args: argparse.Namespace) -> None:
    """回滚状态"""
    mgr = SkillStateManager(args.skill_id)
    count_before = mgr.get_usage_count()

    success = mgr.rollback(n=args.n)

    if success:
        count_after = mgr.get_usage_count()
        cli_output({
            "ok": True, "rollback_steps": args.n,
            "usage_before": count_before, "usage_after": count_after,
        }, args, text=lambda: (
            f"✅ 状态回滚成功！\n"
            f"   回滚步数:     {args.n}\n"
            f"   使用次数:     {count_before} → {count_after}"
        ))
    else:
        cli_output({"ok": False, "error": "历史记录不足"}, args, text=lambda: (
            f"❌ 回滚失败！历史记录不足\n"
            f"   使用 'history' 命令查看可用历史记录"
        ))


# ── 8W+8X: 快照/版本控制/分支 ──


def cmd_snapshot_list(args: argparse.Namespace) -> None:
    """列出历史快照"""
    mgr = SkillStateManager(args.skill_id)
    snapshots = mgr.list_snapshots(limit=args.n)

    def _text():
        lines = [f"📸 历史快照: {args.skill_id}", "=" * 60]
        for s in snapshots:
            marker = " ⭐" if s.get("named") else ""
            lines.append(
                f"  [{s['version']:3d}]{marker} {s['timestamp'][:19]:19s} | "
                f"{s['action']:12s} | {s['level']:10s} | usage={s['usage_count']}"
            )
        return "\n".join(lines)

    cli_output({"skill_id": args.skill_id, "snapshots": snapshots}, args, text=_text)



def cmd_snapshot_save(args: argparse.Namespace) -> None:
    """创建命名快照"""
    mgr = SkillStateManager(args.skill_id)
    result = mgr.create_named_snapshot(args.name)
    cli_output(result, args, text=lambda: (
        f"✅ 快照已创建: {args.name}\n   时间: {result.get('timestamp', '?')}"
    ) if result.get("ok") else f"❌ {result.get('error')}"
    )



def cmd_snapshot_restore(args: argparse.Namespace) -> None:
    """恢复到命名快照"""
    mgr = SkillStateManager(args.skill_id)
    result = mgr.restore_snapshot(args.name)
    cli_output(result, args, text=lambda: (
        f"✅ 已恢复到快照: {args.name}\n"
        f"   时间: {result.get('timestamp', '?')}\n"
        f"   境界: {result.get('level', '?')} | 使用次数: {result.get('usage_count', '?')}"
    ) if result.get("ok") else f"❌ {result.get('error')}"
    )



def cmd_branch_create(args: argparse.Namespace) -> None:
    """创建学习分支"""
    mgr = SkillStateManager(args.skill_id)
    result = mgr.create_branch(args.branch_name)
    cli_output(result, args, text=lambda: (
        f"🌿 分支已创建: {args.branch_name}\n"
        f"   基于: {result.get('meta', {}).get('source_level', '?')} "
        f"(usage={result.get('meta', {}).get('source_version', 0)})\n"
        f"   路径: {result.get('path', '?')}"
    ) if result.get("ok") else f"❌ {result.get('error')}"
    )



def cmd_branch_list(args: argparse.Namespace) -> None:
    """列出分支"""
    branches = SkillStateManager.list_branches(args.skill_id)

    def _text():
        lines = [f"🌿 技能分支: {args.skill_id}"]
        if not branches:
            lines.append("  (无分支)")
        for b in branches:
            lines.append(
                f"  {b['branch']:20s} | {b.get('source_level', '-'):10s} | "
                f"{b.get('created_at', '-')[:19]} | {b['size']:5d} bytes"
            )
        return "\n".join(lines)

    cli_output({"skill_id": args.skill_id, "branches": branches}, args, text=_text)



def cmd_tutor(args: argparse.Namespace) -> None:
    """8Y: 智能导师 — 学习风格诊断 + 自适应建议 + 错误诊断"""
    from ..core.paths import SkillStateManager
    from ..systems.cultivating.skill_tutor import SkillTutor

    mgr = SkillStateManager(args.skill_id)
    state = mgr.load()
    history = mgr.get_history(limit=100)

    tutor = SkillTutor(args.skill_id)
    analysis = tutor.analyze(state, history or [])
    result = {
        "skill_id": args.skill_id,
        "level": analysis["level"],
        "usage_count": analysis["usage_count"],
        "style": analysis["style"]["style"],
        "diagnosis": analysis["diagnosis"],
        "adaptive_task": analysis["adaptive_task"],
        "pace_advice": analysis["pace_advice"],
        "next_steps": analysis["next_steps"],
    }
    cli_output(result, args, text=lambda: tutor.format_report(analysis))



def cmd_template_list(args: argparse.Namespace) -> None:
    """列出预置技能模板"""
    from ..skill_dsl import PREDEFINED_SKILL_TEMPLATES, SKILL_TEMPLATE_CATEGORIES, SKILL_TEMPLATE_STATS

    templates = PREDEFINED_SKILL_TEMPLATES
    # 按分类/难度筛选
    cat = getattr(args, 'category', None)
    diff = getattr(args, 'difficulty', None)
    filtered = []
    for key, tmpl in templates.items():
        if cat and tmpl.get("category") != cat:
            continue
        if diff and tmpl.get("difficulty") != diff:
            continue
        filtered.append((key, tmpl))
    if not filtered:
        filtered = list(templates.items())

    result = {
        "total": len(templates), "filtered": len(filtered),
        "by_category": SKILL_TEMPLATE_STATS["by_category"],
        "by_difficulty": SKILL_TEMPLATE_STATS["by_difficulty"],
        "results": [{"key": k, "name": t["name"], "category": t["category"],
                      "difficulty": t["difficulty"], "tags": t["tags"]} for k, t in filtered],
    }

    diff_icons = {"beginner": "🌱", "intermediate": "📈", "advanced": "🎯", "expert": "🏆"}

    def _text():
        lines = [f"📋 技能模板库 ({len(filtered)}/{len(templates)})", "=" * 60]
        for key, tmpl in filtered:
            icon = diff_icons.get(tmpl["difficulty"], "⚪")
            lines.append(
                f"  {icon} {key:20s} | {tmpl['category']:12s} | {tmpl['difficulty']:12s} | "
                f"{', '.join(tmpl['tags'][:3])}"
            )
        lines.append(f"\n  分类: {'  '.join(f'{k}({v})' for k,v in SKILL_TEMPLATE_STATS['by_category'].items())}")
        return "\n".join(lines)

    cli_output(result, args, text=_text)



def cmd_template_use(args: argparse.Namespace) -> None:
    """使用模板创建技能"""
    from ..skill_dsl import PREDEFINED_SKILL_TEMPLATES
    from ..core.paths import SkillStateManager

    tmpl = PREDEFINED_SKILL_TEMPLATES.get(args.template_name)
    if not tmpl:
        cli_output({"ok": False, "error": f"模板 '{args.template_name}' 不存在"},
                   args, text=lambda: f"❌ 模板 '{args.template_name}' 不存在\n   使用 'skill template list' 查看")
        return

    skill_id = getattr(args, 'skill_id', None) or args.template_name
    mgr = SkillStateManager(skill_id)
    state = mgr._default_state()
    state.update({
        "name": tmpl["name"],
        "category": tmpl.get("category"),
        "difficulty": tmpl.get("difficulty"),
        "weights": {
            "proficiency": tmpl["proficiency_weight"],
            "stability": tmpl["stability_weight"],
            "satisfaction": tmpl["satisfaction_weight"],
            "responsiveness": tmpl["responsiveness_weight"],
            "memory": tmpl["memory_weight"],
        },
        "template": args.template_name,
    })
    mgr.save(state, action="template_use")

    cli_output({
        "ok": True, "skill_id": skill_id, "template": args.template_name,
        "name": tmpl["name"], "category": tmpl["category"],
        "task_count": len(tmpl["practice_tasks"]),
    }, args, text=lambda: (
        f"✅ 已从模板创建技能: {skill_id}\n"
        f"   名称: {tmpl['name']}\n"
        f"   分类: {tmpl['category']} | 难度: {tmpl['difficulty']}\n"
        f"   练习任务: {len(tmpl['practice_tasks'])} 个\n"
        f"   使用 'zenskill skill status --skill-id {skill_id}' 查看状态"
    ))



def cmd_template_info(args: argparse.Namespace) -> None:
    """查看模板详情"""
    from ..skill_dsl import PREDEFINED_SKILL_TEMPLATES

    tmpl = PREDEFINED_SKILL_TEMPLATES.get(args.template_name)
    if not tmpl:
        cli_output({"ok": False, "error": f"模板 '{args.template_name}' 不存在"},
                   args, text=lambda: f"❌ 模板 '{args.template_name}' 不存在\n   使用 'skill template list' 查看可用模板")
        return

    def _text():
        lines = [f"📋 {tmpl['name']} ({args.template_name})", "=" * 60,
                 f"   分类: {tmpl['category']} | 难度: {tmpl['difficulty']}",
                 f"   标签: {', '.join(tmpl['tags'])}",
                 f"   前置: {', '.join(tmpl['prerequisites']) or '无'}", "",
                 "练习任务:"]
        for task in tmpl["practice_tasks"]:
            lines.append(f"   [{task['level']}] {task['description']}")
        return "\n".join(lines)

    cli_output({"template": tmpl}, args, text=_text)


