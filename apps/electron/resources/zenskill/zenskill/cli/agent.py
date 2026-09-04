"""agent-engine 命令组（从 __main__.py 提取）。

包含：serve / stats / session(list/show/tree)
"""
from __future__ import annotations

import argparse


def register_agent_engine_parser(subparsers) -> None:
    """注册 agent-engine 子命令组到 argparse。"""
    agent_parser = subparsers.add_parser("agent-engine", help="Agent 引擎（会话管理等）")
    agent_sub = agent_parser.add_subparsers(dest="agent_command")

    # serve
    serve_p = agent_sub.add_parser("serve", help="JSONL RPC headless 模式（stdin 命令 / stdout 事件流）")
    serve_p.add_argument("--model", help="模型（如 deepseek/deepseek-chat）")
    serve_p.add_argument("--faux", action="store_true", help="离线冒烟模式（回显 provider，不调 LLM）")
    serve_p.add_argument("--permission", choices=["full", "restricted", "plan", "sandbox"], default="full")
    serve_p.add_argument("--cwd", help="工作目录（默认当前目录）")
    serve_p.add_argument("--session-root", help="会话存储根目录（默认 ~/.zenskill/agent/sessions）")
    serve_p.add_argument("--stateless", action="store_true", help="无状态模式（不做会话持久化，由宿主管理）")
    serve_p.set_defaults(
        agent_command="serve",
        func=lambda args: __import__(
            "zenskill.runtime.agent.rpc", fromlist=["serve_main"]
        ).serve_main(args),
    )

    # stats
    stats_p = agent_sub.add_parser("stats", help="agent 用量与成本统计")
    stats_p.add_argument("--days", type=int, default=30)
    stats_p.set_defaults(
        agent_command="stats",
        func=lambda args: __import__(
            "zenskill.runtime.agent.cli", fromlist=["cmd_agent_stats"]
        ).cmd_agent_stats(args),
    )

    # session
    agent_session_parser = agent_sub.add_parser("session", help="会话管理")
    agent_session_sub = agent_session_parser.add_subparsers(dest="session_action")
    agent_session_sub.add_parser("list", help="列出会话")
    show_p = agent_session_sub.add_parser("show", help="查看会话上下文")
    show_p.add_argument("--session-id", help="会话 ID")
    tree_p = agent_session_sub.add_parser("tree", help="查看会话分支树")
    tree_p.add_argument("--session-id", help="会话 ID")
    prune_p = agent_session_sub.add_parser("prune",
        help="清理会话（默认仅预览；--delete 才真删）")
    prune_p.add_argument("--older-than", type=int, default=30, metavar="DAYS",
        help="清理 N 天前的会话（按文件 mtime，默认 30）")
    prune_p.add_argument("--delete", action="store_true",
        help="真删（缺省仅预览）")
    search_p = agent_session_sub.add_parser("search", help="搜索会话消息")
    search_p.add_argument("query", help="搜索关键词")
    search_p.add_argument("--limit", type=int, default=20, help="最多返回条数")
    search_p.add_argument("--json", action="store_true", help="JSON 输出")
    agent_session_parser.set_defaults(func=lambda args: (
        __import__("zenskill.runtime.agent.cli", fromlist=["cmd_agent_session"]).cmd_agent_session(args)
    ))
    agent_parser.set_defaults(func=lambda args: agent_parser.print_help())

    # chat — 持续对话 REPL
    chat_p = agent_sub.add_parser("chat", help="持续对话模式（REPL）")
    chat_p.add_argument("--model", help="模型（如 deepseek/deepseek-chat）")
    chat_p.add_argument("--permission", choices=["full", "restricted", "plan", "sandbox"], default="full")
    chat_p.add_argument("--with-memory", action="store_true", help="启用 Memory Capability")
    chat_p.add_argument("--with-skills", action="store_true", help="注入技能元数据")
    chat_p.add_argument("--session", help="续接已有会话 ID")
    chat_p.add_argument("--debug", action="store_true", help="调试模式")
    chat_p.add_argument("--max-steps", type=int, default=10, help="每轮最大步数")
    chat_p.set_defaults(
        agent_command="chat",
        func=lambda args: __import__(
            "zenskill.runtime.agent.cli", fromlist=["cmd_agent_chat"]
        ).cmd_agent_chat(args),
    )
