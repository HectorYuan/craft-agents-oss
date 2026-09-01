"""session 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

from ..cli_utils import output as cli_output


def cmd_session(args: argparse.Namespace) -> None:
    """会话状态管理 — 查看/重置当前会话"""
    import json, time, os
    from pathlib import Path

    session_file = Path.home() / ".zenskill" / "session" / "current.json"
    reset_requested = (getattr(args, 'reset', False) or
                       getattr(args, 'session_action', '') == 'reset')

    if reset_requested:
        if session_file.exists():
            session_file.unlink()
            cli_output({"ok": True, "action": "reset", "was_active": True}, args,
                       text=lambda: "✅ 会话已重置")
        else:
            cli_output({"ok": True, "action": "reset", "was_active": False}, args,
                       text=lambda: "✅ 无活跃会话")
        return

    if not session_file.exists():
        cli_output({"ok": True, "active": False}, args,
                   text=lambda: "\n📊 当前会话状态\n═" + "═" * 49 + "\n   无活跃会话")
        return

    try:
        s = json.loads(session_file.read_text())
    except Exception:
        print("   ❌ 会话文件损坏")
        return

    now = time.time()
    tc = s.get("tool_count", 0)
    elapsed = (now - s.get("started", now)) / 60
    recent = s.get("recent_tools", [])
    started_str = time.strftime('%H:%M:%S', time.localtime(s.get('started', now)))
    pid = s.get("_claude_pid", 0)
    pid_mismatch = pid != os.getppid() if pid else False

    result = {
        "active": True,
        "tool_count": tc,
        "elapsed_min": round(elapsed, 1),
        "started": started_str,
        "recent_tools": recent[-5:],
        "claude_pid": pid,
        "current_pid": os.getppid(),
        "pid_mismatch": pid_mismatch,
    }

    def _text():
        lines = ["", "📊 当前会话状态", "═" * 50]
        lines.append(f"   工具调用: {tc} 次")
        lines.append(f"   持续时长: {elapsed:.0f} 分钟")
        lines.append(f"   开始时间: {started_str}")
        lines.append(f"   最近工具: {', '.join(recent[-5:]) if recent else '无'}")
        if pid:
            lines.append(f"   Claude PID: {pid} (当前: {os.getppid()})")
            if pid_mismatch:
                lines.append("   ⚠️ PID 不匹配，下次 hook 将自动重置会话")
        lines.append("")
        lines.append("   重置会话: zenskill session --reset")
        return "\n".join(lines)

    cli_output(result, args, text=_text)



def cmd_session_briefing(_args: argparse.Namespace) -> None:
    """输出会话摘要 — 供 Stop Hook 使用"""
    from ..context_card import generate_session_briefing
    briefing = generate_session_briefing()
    cli_output({"briefing_length": len(briefing)}, _args, text=lambda: briefing)



def register_session_parser(subparsers) -> None:
    """注册 session 子命令组。"""
    session_parser = subparsers.add_parser("session", help="会话状态管理")
    session_sub = session_parser.add_subparsers(dest="session_action", help="会话操作")
    session_stats_p = session_sub.add_parser("stats", help="显示当前会话状态")
    session_stats_p.set_defaults(func=cmd_session)
    session_reset_p = session_sub.add_parser("reset", help="重置当前会话")
    session_reset_p.set_defaults(func=cmd_session)

    # config 命令组
    from .config import register_config_parser
    register_config_parser(subparsers)
    from .goal import register_goal_parser
    register_goal_parser(subparsers)
    from .task import register_task_parser
    register_task_parser(subparsers)
    from .graph import register_graph_parser
    register_graph_parser(subparsers)
