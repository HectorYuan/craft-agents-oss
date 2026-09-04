"""pages 命令组 — `zenskill pages sync` 播种 craft Pages 页面包

把 zenskill/resources/pages/ 下的 zenskill- 前缀页面播种到活跃
workspace 的 pages/ 目录（幂等；用户自建页面不触碰）。
见 docs/repo_management_and_gui_plan_v3.md 1.4 节。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..core.update_pages import resolve_active_workspace_root, sync_pages


def cmd_pages_sync(args: argparse.Namespace) -> int:
    """播种 zenskill- 页面包并打印发现/结果摘要"""
    if args.workspace:
        workspace = Path(args.workspace).expanduser()
    else:
        workspace = resolve_active_workspace_root()
    if workspace is None:
        print("未找到活跃 workspace：请用 --workspace 显式指定，"
              "或检查 ~/.zenskill/craft/config.json 的 activeWorkspaceId")
        return 1

    result = sync_pages(workspace)

    # __main__ 预处理会把全局 --json 提取到 args.json_output（既有约定），
    # 兼容直接经 argparse 解析时落在 args.json 的情况
    as_json = getattr(args, "json_output", False) or getattr(args, "json", False)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"workspace: {result['workspace_root']}")
        print(f"发现页面包: {len(result['discovered'])} 个"
              f"（{', '.join(result['discovered']) or '无'}）")
        for slug in result["seeded"]:
            print(f"  ✓ 播种: {slug}")
        for slug in result["unchanged"]:
            print(f"  - 无变化: {slug}")
        for item in result["failed"]:
            print(f"  ✗ 失败: {item['slug']}（{item['error']}）")
        print(f"完成：播种 {len(result['seeded'])} / "
              f"无变化 {len(result['unchanged'])} / "
              f"失败 {len(result['failed'])}")
    return 1 if result["failed"] else 0


def register_pages_parser(subparsers: Any) -> None:
    """注册 pages 命令组（由 __main__.main 调用）"""
    pages_parser = subparsers.add_parser("pages", help="craft Pages 页面包管理")
    pages_sub = pages_parser.add_subparsers(dest="subcommand", help="Pages 操作")
    sync_p = pages_sub.add_parser(
        "sync",
        help="播种 zenskill- 页面包到 workspace 的 pages/ 目录（幂等覆盖）",
    )
    sync_p.add_argument(
        "--workspace", default="",
        help="workspace 根目录（默认取 ~/.zenskill/craft/config.json 活跃 workspace）",
    )
    sync_p.add_argument(
        "--json", action="store_true",
        help="以 JSON 输出完整结果摘要",
    )
    sync_p.set_defaults(func=cmd_pages_sync)
