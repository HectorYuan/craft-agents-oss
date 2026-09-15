"""zenskill share 命令组：分享卡片生成。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def cmd_share_card(args: Any) -> int:
    from ..share.card_data import GrowthCardData
    from ..share.renderer import render_card_html, render_card_png, render_card_text

    fmt = getattr(args, "format", "html") or "html"
    output = getattr(args, "output", None)
    public = bool(getattr(args, "public", False))
    card_data = GrowthCardData().get_card_data()

    if fmt == "json":
        print(json.dumps(card_data, ensure_ascii=False, indent=2))
        return 0

    if public:
        from ..share.public_page import make_card_id, save_public_page

        page_path = save_public_page(make_card_id(card_data))
        print(f"公开页已生成: {page_path}")

    html = render_card_html(card_data)

    if fmt == "png":
        if not output:
            output = str(Path.home() / ".zenskill" / "shares" / f"card_{card_data.get('date', '')}.png")
        result = render_card_png(html, output)
        if result:
            print(f"PNG 已生成: {result}")
            return 0
        print("playwright 不可用，已降级为 HTML 输出。")
        print("可安装: pip install playwright && playwright install chromium")
        fmt = "html"

    if fmt == "html":
        if not output:
            output = str(Path.home() / ".zenskill" / "shares" / f"card_{card_data.get('date', '')}.html")
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(html, encoding="utf-8")
        print(f"HTML 已生成: {output}")
        print("（1080×1080，可在浏览器打开后截图，或安装 playwright 生成 PNG）")
        return 0

    # text 或未知格式
    print(render_card_text(card_data))
    return 0


def register_share_parser(subparsers: Any) -> None:
    """注册 share 命令组（由 __main__.main 调用）"""
    share_parser = subparsers.add_parser("share", help="成长分享卡片")
    share_sub = share_parser.add_subparsers(dest="subcommand", help="share 操作")
    card_p = share_sub.add_parser("card", help="生成成长分享卡片")
    card_p.add_argument("--output", "-o", default=None, help="输出文件路径")
    card_p.add_argument(
        "--format", "-f",
        default="html",
        choices=["json", "html", "png", "text"],
        help="输出格式（默认 html；png 需要 playwright）",
    )
    card_p.add_argument(
        "--public", action="store_true",
        help="额外生成免登录公开页 HTML（base64 内嵌卡片图）",
    )
    card_p.set_defaults(func=cmd_share_card)

    stats_p = share_sub.add_parser("stats", help="查看分享观察期指标（数据驱动，不设期限）")
    stats_p.add_argument("--days", type=int, default=7, help="陪伴事件统计天数（默认 7）")
    stats_p.set_defaults(func=cmd_share_stats)


def cmd_share_stats(args: Any) -> int:
    """查看 B 方案观察期指标。"""
    from ..share.metrics import get_observation_summary, get_companion_metrics
    obs = get_observation_summary()
    comp = get_companion_metrics(days=args.days)
    print("📊 B 方案观察期指标")
    print(f"  卡片生成: {obs['card_count']} 张")
    print(f"  公开页:   {obs['public_page_count']} 个")
    if comp.get("events_available"):
        print(f"  陪伴事件（近 {comp['days']} 天）:")
        print(f"    展示:   {comp['displayed']} 次")
        print(f"    洞察点击: {comp['insight_clicked']} 次")
        print(f"    反馈:   {comp['feedback']} 次")
    else:
        print("  陪伴事件: 暂无数据")
    return 0
