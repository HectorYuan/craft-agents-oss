"""perceive 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse


def cmd_perceive(args: argparse.Namespace) -> None:
    """感知引擎评估 — 对当前上下文进行评估，输出告警和建议"""
    import time, json
    from pathlib import Path
    from .perception_engine import PerceptionEngine

    # 加载当前会话状态
    session_file = Path.home() / ".zenskill" / "session" / "current.json"
    tc, elapsed, recent = 0, 0, []
    if session_file.exists():
        try:
            s = json.loads(session_file.read_text())
            tc = s.get("tool_count", 0)
            elapsed = (time.time() - s.get("started", time.time())) / 60
            recent = s.get("recent_tools", [])
        except Exception:
            pass

    # 加载 pipeline 数据
    pipeline_file = Path.home() / ".zenskill" / "mirroring" / "pipeline.json"
    domains, intents = {}, {}
    if pipeline_file.exists():
        try:
            p = json.loads(pipeline_file.read_text())
            nlp = p.get("nlp", {})
            domains = nlp.get("domains", {})
            intents = nlp.get("intents", {})
        except Exception:
            pass

    engine = PerceptionEngine()
    reload_info = None
    if getattr(args, 'reload_rules', False):
        ok = engine.reload_rules()
        icon = "✅" if ok else "⚠️"
        reload_info = f"{icon} 规则重载: {engine.rule_source}"

    lt = time.localtime(time.time())
    ctx = {
        "tool_count": tc, "elapsed_min": elapsed,
        "recent_tools": recent,
        "current_hour": lt.tm_hour, "current_minute": lt.tm_min,
        "last_command": "", "error_rate": 0.0,
    }
    result = engine.evaluate(ctx)
    alerts = result.get("alerts", [])
    suggestions = result.get("suggestions", [])
    wf = result.get("workflow", {})
    pdca = result.get("pdca", {})

    result_data = {
        "tool_count": tc, "elapsed_min": elapsed,
        "alert_count": len(alerts), "alerts": alerts,
        "suggestion_count": len(suggestions), "suggestions": suggestions,
        "workflow": wf, "pdca": pdca,
        "rule_source": engine.rule_source,
        "reload_info": reload_info,
    }

    def _text():
        lines = []
        if reload_info:
            lines.append(reload_info)
        lines.extend(["", f"🔍 ZenSkill 感知评估 [{engine.rule_source}]",
                      "═" * 50,
                      f"   会话: {tc} tools in {elapsed:.0f}min"])
        if domains:
            lines.append(f"   活跃领域: {', '.join(f'{d}({s:.0f}%)' for d, s in sorted(domains.items(), key=lambda x: -x[1])[:3])}")
        if intents:
            lines.append(f"   意图分布: {', '.join(f'{i}({c}x)' for i, c in sorted(intents.items(), key=lambda x: -x[1])[:3])}")

        if alerts:
            lines.append(f"\n   🚨 告警 ({len(alerts)}):")
            for a in alerts:
                sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}.get(a.get("severity", ""), "⚪")
                lines.append(f"   {sev_icon} [{a.get('source', '?')}] {a.get('message', '')}")

        if suggestions:
            lines.append(f"\n   💡 建议 ({len(suggestions)}):")
            for s in suggestions:
                lines.append(f"   → [{s.get('source', '?')}] {s.get('suggestion', '')}")

        if wf and wf.get("matched"):
            lines.append(f"\n   📐 匹配工作流: {wf.get('name', '?')} (置信度: {wf.get('confidence', 0):.0%})")

        if pdca:
            lines.append(f"\n   🔄 PDCA 阶段: {pdca.get('phase', '?')}")
            lines.append(f"   {pdca.get('suggestion', '')}")

        if not alerts and not suggestions:
            lines.append(f"\n   ✅ 一切正常，未发现异常模式")
        return "\n".join(lines)

    cli_output(result_data, args, text=_text)



def cmd_perceive_context(args: argparse.Namespace) -> None:
    """对话上下文分析 — 意图/话题/疲劳度/预加载建议 (Phase 10I)"""
    from .cli_utils import section_blank, box_header, box_footer, bar_chart
    from .context_analyzer import ConversationContextAnalyzer

    analyzer = ConversationContextAnalyzer()
    window = getattr(args, "window", 10)
    result = analyzer.analyze(window=window)

    def _text():
        lines = []
        section_blank("对话上下文分析", "🧠", phase="10I")

        # 意图
        box_header("当前意图", "🎯")
        intent = result.get("intent", "unknown")
        dist = result.get("intent_distribution", {})
        lines.append(f"  │  主导: {intent}")
        if dist:
            max_n = max(dist.values()) or 1
            for action, count in sorted(dist.items(), key=lambda x: -x[1]):
                bar = bar_chart(count, max_n, 10)
                lines.append(f"  │    {action:10s} {bar} {count}")
        box_footer()

        # 话题
        lines.append("")
        box_header("当前话题", "💬")
        lines.append(f"  │  话题: {result.get('topic', 'none')}")
        lines.append(f"  │  领域: {result.get('topic_domain', '通用')}")
        kws = result.get("topic_keywords", [])
        if kws:
            lines.append(f"  │  关键词: {', '.join(kws[:5])}")
        box_footer()

        # 疲劳度
        lines.append("")
        fatigue = result.get("fatigue", 0)
        fatigue_icon = "🟢" if fatigue < 30 else "🟡" if fatigue < 60 else "🔴"
        box_header(f"疲劳度: {fatigue}/100", fatigue_icon)
        for signal in result.get("fatigue_signals", []):
            lines.append(f"  │  ⚠️ {signal}")
        box_footer()

        # 上下文预加载
        preloads = result.get("context_preloads", [])
        if preloads:
            lines.append("")
            box_header("上下文预加载建议", "📎")
            for p in preloads:
                lines.append(f"  │  💡 {p}")
            box_footer()

        # 统计
        lines.append("")
        box_header("统计", "📊")
        lines.append(f"  │  消息数: {result.get('message_count', 0)}")
        lines.append(f"  │  会话数: {result.get('session_count', 0)}")
        box_footer()

        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)



def register_perceive_parser(subparsers) -> None:
    """注册 perceive 子命令组。"""
    perceive_parser = subparsers.add_parser("perceive", help="感知引擎实时评估")
    perceive_sub = perceive_parser.add_subparsers(dest="perceive_action", help="感知操作")
    perceive_check_p = perceive_sub.add_parser("check", help="感知检查")
    perceive_check_p.add_argument("--reload-rules", action="store_true", help="从 zenthink/ 强制重载规则")
    perceive_check_p.set_defaults(func=cmd_perceive)

    # 10I: 对话上下文感知
    perceive_context_p = perceive_sub.add_parser("context", help="对话上下文分析 (Phase 10I)")
    perceive_context_p.add_argument("--window", type=int, default=10, help="分析窗口消息数")
    perceive_context_p.set_defaults(func=cmd_perceive_context)

    # context 命令
    from .context import register_context_parser
    register_context_parser(subparsers)
