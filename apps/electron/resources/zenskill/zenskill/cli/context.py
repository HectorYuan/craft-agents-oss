"""context 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

from ..cli_utils import output as cli_output

def cmd_context_stats(args: argparse.Namespace) -> None:
    """7Y3+7Y4: ACT 响应统计 + 偏好分析"""
    from ..context_card import (
        _get_act_response_rate, _get_act_type_preference,
        _get_unresponded_count, _get_dialogue_history,
    )

    rate = _get_act_response_rate()
    preferred = _get_act_type_preference()
    skipped = _get_unresponded_count()
    hist = _get_dialogue_history()

    result = {
        "act_response_rate": rate,
        "skipped_count": skipped,
        "preferred_type": preferred,
        "has_dialogue": hist is not None,
    }

    def _text():
        lines = ["", "📊 Context Card ACT 统计", "═" * 50]
        lines.append(f"   ACT 响应率: {rate:.0%}")
        lines.append(f"   连续跳过: {skipped} 次")
        if rate > 0.8:
            lines.append("   频率策略: 每回合 (高响应)")
        elif rate > 0.4:
            lines.append("   频率策略: 60% 概率 (中响应)")
        else:
            lines.append("   频率策略: 仅关键节点 (低响应)")
        if preferred:
            type_names = {"health": "健康", "goal": "目标", "insight": "洞察",
                          "milestone": "里程碑", "workflow": "工作流", "general": "通用"}
            lines.append(f"   偏好类型: {type_names.get(preferred, preferred)} (响应率最高)")
        if hist:
            lines.append(f"\n   上次对话: [{hist.get('topic', '?')}]")
            lines.append(f"   触发词: {hist.get('trigger', '')[:60]}")
            status = "✅ 已响应" if hist.get("responded") else "⏳ 未响应"
            lines.append(f"   状态: {status}")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_context_respond(args: argparse.Namespace) -> None:
    """7X4+7Y3: 标记上次对话已被响应"""
    from ..context_card import _record_act_responded
    _record_act_responded()
    cli_output({"ok": True, "action": "act_responded"}, args,
               text=lambda: "✅ 已标记: 对话响应 + ACT 计数重置")


def cmd_context_history(args: argparse.Namespace) -> None:
    """7X4: 查看多轮对话历史"""
    from ..context_card import _get_dialogue_history
    hist = _get_dialogue_history()
    result = {"has_history": hist is not None}
    if hist:
        import time
        when = time.strftime("%H:%M:%S", time.localtime(hist.get("timestamp", 0)))
        result.update({
            "topic": hist.get("topic", "?"),
            "trigger": hist.get("trigger", "")[:80],
            "responded": hist.get("responded", False),
            "timestamp": when,
        })
        cli_output(result, args, text=lambda: (
            f"\n📝 对话历史\n{'═' * 40}\n"
            f"   主题: {hist.get('topic', '?')}\n"
            f"   触发: {hist.get('trigger', '')[:80]}\n"
            f"   响应: {'✅' if hist.get('responded') else '❌'}\n"
            f"   时间: {when}\n"
        ))
    else:
        cli_output(result, args, text=lambda: "📝 无对话历史 (超过 30 分钟自动过期)")


def cmd_context_guide(args: argparse.Namespace) -> None:
    """7W: 上下文感知引导"""
    from ..systems.active.context_guide import ContextGuideEngine

    engine = ContextGuideEngine()
    hours = getattr(args, 'hours', 24)
    guide_text = engine.format_guide(lookback_hours=hours)
    cli_output({"lookback_hours": hours, "has_guide": bool(guide_text)}, args,
               text=lambda: f"\n{guide_text}\n")


def cmd_context_reset(args: argparse.Namespace) -> None:
    """重置所有 Context Card 追踪数据"""
    from pathlib import Path
    import json
    session_dir = Path.home() / ".zenskill" / "session"
    files = ["unresponded.json", "act_response.json", "act_preferences.json", "dialogue_history.json"]
    deleted = []
    for fn in files:
        f = session_dir / fn
        if f.exists():
            f.unlink()
            deleted.append(fn)
    cli_output({"deleted_files": deleted, "deleted_count": len(deleted)}, args,
               text=lambda: "\n".join(
                   [f"  🗑 {fn}" for fn in deleted] +
                   ["✅ Context Card 追踪数据已重置"]
               ))


def cmd_context_card(_args: argparse.Namespace) -> None:
    """输出 ZenSkill 上下文卡片 — 供 UserPromptSubmit Hook 使用"""
    from ..context_card import generate_context_card
    card = generate_context_card()
    if card:
        cli_output({"card_length": len(card)}, _args, text=lambda: card)



def register_context_parser(subparsers) -> None:
    """注册 context 子命令组。"""
    context_parser = subparsers.add_parser("context", help="Context Card 管理 (预览/统计/标记/重置)")
    context_subparsers = context_parser.add_subparsers(dest="subcommand", help="操作")
    context_parser.set_defaults(func=cmd_context)

    context_stats_parser = context_subparsers.add_parser("stats", help="ACT 响应统计 + 偏好分析 (7Y3/7Y4)")
    context_stats_parser.set_defaults(func=cmd_context_stats)

    context_respond_parser = context_subparsers.add_parser("respond", help="标记对话已被响应 (7X4/7Y3)")
    context_respond_parser.set_defaults(func=cmd_context_respond)

    context_history_parser = context_subparsers.add_parser("history", help="查看多轮对话历史 (7X4)")
    context_history_parser.set_defaults(func=cmd_context_history)

    context_reset_parser = context_subparsers.add_parser("reset", help="重置所有 Context Card 追踪数据")
    context_reset_parser.set_defaults(func=cmd_context_reset)

    context_guide_parser = context_subparsers.add_parser("guide", help="上下文感知引导 — 智能操作建议 (7W)")
    context_guide_parser.add_argument("--hours", type=int, default=24, help="回溯小时数")
    context_guide_parser.set_defaults(func=cmd_context_guide)

    # session 命令

def cmd_context(args: argparse.Namespace) -> None:
    """预览 Context Card 和 Session Briefing（Hook 中注入的内容）"""
    from ..context_card import generate_context_card, generate_session_briefing

    card = generate_context_card()
    briefing = generate_session_briefing()
    result = {
        "has_card": bool(card),
        "card_length": len(card) if card else 0,
        "briefing_length": len(briefing),
    }

    def _text():
        lines = ["", "📋 Context Card (UserPromptSubmit Hook 注入)", "═" * 60]
        lines.append(card if card else "   (无数据)")
        lines.extend(["", "📋 Session Briefing (Stop Hook 输出)", "═" * 60])
        lines.append(briefing)
        return "\n".join(lines)

    cli_output(result, args, text=_text)


