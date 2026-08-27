"""hook 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

def cmd_hook_list(args: argparse.Namespace) -> None:
    """列出所有 Hook 及状态"""
    from .hooks import HookManager

    mgr = HookManager()
    hooks = mgr.list_hooks()

    active = [h for h in hooks if h["active"]]
    inactive = [h for h in hooks if not h["active"]]

    result = {
        "total_hooks": len(hooks),
        "active_count": len(active),
        "inactive_count": len(inactive),
        "active_names": [h["name"] for h in active],
        "inactive_names": [h["name"] for h in inactive],
    }

    def _text():
        lines = [_str_section("Claude Code Hook 管理", "🪝")]
        if active:
            lines.append(_str_box_header("已启用", "🟢"))
            for h in active:
                lines.append(f"  │  🟢 {h['name']:22s} {h['description']}")
            lines.append(_str_box_footer())
        if inactive:
            lines.append("")
            lines.append(_str_box_header("可用（未启用）", "⚪"))
            for h in inactive:
                lines.append(f"  │  ⚪ {h['name']:22s} {h['description']}")
            lines.append(_str_box_footer())
        lines.append("")
        lines.append(f"  📊 {len(active)}/{len(hooks)} hooks 已启用")
        lines.append("  💡 zenskill hook enable <name>     # 启用指定 hook")
        lines.append("       zenskill hook enable-all       # 启用推荐组合")
        lines.append("       zenskill hook disable <name>   # 禁用")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_hook_enable(args: argparse.Namespace) -> None:
    """启用 Hook"""
    from .hooks import HookManager

    mgr = HookManager()
    if args.name:
        ok = mgr.enable(args.name)
        if ok:
            cli_output({"ok": True, "hook_name": args.name}, args,
                       text=lambda: f"\n  🟢 Hook '{args.name}' 已启用\n")
        else:
            cli_output({"ok": False, "hook_name": args.name,
                        "available": list(mgr.HOOK_TEMPLATES.keys())}, args,
                       text=lambda: (
                           f"\n  🔴 未知 Hook: {args.name}\n"
                           f"  可用: {', '.join(mgr.HOOK_TEMPLATES.keys())}\n"
                       ))
    else:
        # 启用推荐组合
        n = mgr.enable_all()
        cli_output({"ok": True, "enabled_count": n}, args,
                   text=lambda: (
                       f"\n  🟢 已启用 {n} 个推荐 Hook (PostToolUse + Stop)\n"
                       f"  💡 PostToolUse: 每次工具调用后轻量采集\n"
                       f"  💡 Stop: 会话结束时全量采集 + 智能分析\n"
                   ))


def cmd_hook_disable(args: argparse.Namespace) -> None:
    """禁用 Hook"""
    from .hooks import HookManager

    mgr = HookManager()
    if args.name:
        ok = mgr.disable(args.name)
        if ok:
            cli_output({"ok": True, "hook_name": args.name}, args,
                       text=lambda: f"\n  🟢 Hook '{args.name}' 已禁用\n")
        else:
            cli_output({"ok": False, "hook_name": args.name}, args,
                       text=lambda: f"\n  ⚪ Hook '{args.name}' 未启用\n")
    else:
        n = mgr.disable_all()
        cli_output({"ok": True, "disabled_count": n}, args,
                   text=lambda: f"\n  🟢 已禁用 {n} 个 ZenSkill hooks\n")


def cmd_hook_status(args: argparse.Namespace) -> None:
    """Hook 状态摘要"""
    from .hooks import HookManager

    mgr = HookManager()
    status = mgr.status()

    result = {
        "active_zen_hooks": status["active_zen_hooks"],
        "active_names": status["active_names"],
        "settings_file": status["settings_file"],
    }

    def _text():
        lines = [_str_section("Hook 状态", "🪝"),
                 _str_box_header("运行时信息")]
        lines.append(f"  │  已激活:  {status['active_zen_hooks']} 个")
        lines.append(f"  │  名称:    {', '.join(status['active_names']) or '(无)'}")
        lines.append(f"  │  配置文件:{status['settings_file']}")
        lines.append(_str_box_footer())
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)



def register_hook_parser(subparsers) -> None:
    """注册 hook 子命令组。"""
    hook_parser = subparsers.add_parser("hook", help="Claude Code Hook 管理")
    hook_parser.set_defaults(func=cmd_hook_list)  # 默认为 list
    hook_subparsers = hook_parser.add_subparsers(dest="subcommand", help="Hook 操作")

    hook_list_parser = hook_subparsers.add_parser("list", help="列出所有 Hook 及状态")
    hook_list_parser.set_defaults(func=cmd_hook_list)

    hook_enable_parser = hook_subparsers.add_parser("enable", help="启用指定 Hook")
    hook_enable_parser.add_argument("name", nargs="?", help="Hook 名称")
    hook_enable_parser.set_defaults(func=cmd_hook_enable)

    hook_disable_parser = hook_subparsers.add_parser("disable", help="禁用指定 Hook")
    hook_disable_parser.add_argument("name", nargs="?", help="Hook 名称")
    hook_disable_parser.set_defaults(func=cmd_hook_disable)

    hook_status_parser = hook_subparsers.add_parser("status", help="Hook 状态摘要")
    hook_status_parser.set_defaults(func=cmd_hook_status)

