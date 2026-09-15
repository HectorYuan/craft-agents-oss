"""分享卡片渲染：HTML → PNG（分层降级）→ 纯文本。

降级链：
1. playwright sync API 渲染 HTML → PNG（1080×1080）
2. 失败则输出 HTML（用户自行截图）
3. 最终降级为终端纯文本
"""

from __future__ import annotations

import html as html_escape
from pathlib import Path
from string import Template

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "growth_card.html"


def render_card_html(card_data: dict) -> str:
    """生成 1080×1080 深色主题 HTML 卡片字符串。"""
    dims = (card_data.get("dimensions") or [])[:3]
    dim_rows = []
    for d in dims:
        name = html_escape.escape(str(d.get("name", d.get("key", ""))))
        score = d.get("score", 0)
        dim_rows.append(
            f'<div style="display:flex;align-items:center;margin-top:22px;">'
            f'<div style="width:220px;font-size:30px;">{name}</div>'
            f'<div style="width:560px;height:10px;background:#2a2e38;border-radius:5px;overflow:hidden;">'
            f'<div style="width:{int(score)}%;height:10px;background:#5b8cff;"></div></div>'
            f'<div style="width:120px;text-align:right;font-size:32px;font-weight:600;">{int(score)}</div></div>'
        )
    achievements = card_data.get("achievements") or []
    ach_rows = []
    for a in achievements:
        ach_rows.append(
            f'<div style="margin-top:18px;font-size:30px;color:#d7dce6;">'
            f'<span style="color:#f5c451;">&#9733;</span> {html_escape.escape(str(a))}</div>'
        )
    if not ach_rows:
        ach_rows.append(
            '<div style="margin-top:18px;font-size:28px;color:#8b93a7;">暂无成就，继续修炼</div>'
        )

    tpl = Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))
    return tpl.substitute(
        level_name=html_escape.escape(str(card_data.get("level_name", ""))),
        level=html_escape.escape(str(card_data.get("level", ""))),
        total_interactions=int(card_data.get("total_interactions", 0)),
        progress_pct=int(card_data.get("progress_pct", 0)),
        dimension_rows="".join(dim_rows),
        achievement_rows="".join(ach_rows),
        date=html_escape.escape(str(card_data.get("date", ""))),
    )


def render_card_png(html: str, output_path: str) -> str | None:
    """渲染 HTML 为 PNG（需要 playwright + chromium），失败返回 None。"""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1080, "height": 1080})
            page.set_content(html)
            page.screenshot(path=output_path)
            browser.close()
            return output_path
    except Exception:
        return None


def render_card_text(card_data: dict) -> str:
    """终端纯文本降级输出。"""
    level_name = card_data.get("level_name", "")
    level = card_data.get("level", "")
    pct = int(card_data.get("progress_pct", 0))
    bar_w = 20
    filled = int(pct / 100 * bar_w)
    bar = "█" * filled + "░" * (bar_w - filled)

    lines = [
        "╔" + "═" * 46 + "╗",
        f"║ ZenSkill 成长卡片 · {card_data.get('date', '')}".ljust(48) + "║",
        "╠" + "═" * 46 + "╣",
        f"  境界: {level_name} ({level})",
        f"  下一境界进度 [{bar}] {pct}%",
        f"  累计交互: {card_data.get('total_interactions', 0)} 次",
        "",
        "  能力维度:",
    ]
    for d in (card_data.get("dimensions") or [])[:3]:
        lines.append(f"    - {d.get('name', d.get('key', ''))}: {d.get('score', 0)}")
    lines.append("")
    lines.append("  最近成就:")
    achievements = card_data.get("achievements") or []
    if achievements:
        for a in achievements:
            lines.append(f"    ★ {a}")
    else:
        lines.append("    暂无成就，继续修炼")
    lines.append("")
    lines.append("  Powered by ZenSkill")
    return "\n".join(lines)
