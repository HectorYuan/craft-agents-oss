"""notify 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

def cmd_notify_hook(args: argparse.Namespace) -> None:
    """Notification Hook 格式输出"""
    from .notifier import notifier as zn
    notifs = zn.check(_get_notify_context())
    if notifs:
        cli_output({"notification_count": len(notifs), "notifications": notifs}, args,
                   text=lambda: zn.format_for_hook(notifs))



def register_notify_parser(subparsers) -> None:
    """注册 notify 子命令组。"""
    notify_parser = subparsers.add_parser("notify", help="查看主动通知 (里程碑/疲劳/洞察/升级)")
    notify_subparsers = notify_parser.add_subparsers(dest="subcommand", help="通知操作")
    notify_list_parser = notify_subparsers.add_parser("list", help="列出当前待推送通知")
    notify_list_parser.set_defaults(func=cmd_notify)
    notify_hook_parser = notify_subparsers.add_parser("hook", help="输出 Hook 格式通知 (供 Notification hook 使用)")
    notify_hook_parser.set_defaults(func=cmd_notify_hook)
    notify_parser.set_defaults(func=cmd_notify)


def cmd_notify(args: argparse.Namespace) -> None:
    """查看主动通知"""
    from .notifier import notifier as zn
    notifs = zn.check(_get_notify_context())
    result = {"notification_count": len(notifs), "notifications": notifs}
    if notifs:
        cli_output(result, args, text=lambda: zn.format_for_hook(notifs) + "\n")
    else:
        cli_output(result, args, text=lambda: "  [dim]暂无新通知[/dim]\n")


