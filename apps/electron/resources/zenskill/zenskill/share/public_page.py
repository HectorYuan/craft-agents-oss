"""生成免登录公开页——卡片图片内嵌 HTML，保存即可分享。

自包含静态页：卡片图片以 base64 data URI 内嵌，无外部资源，
保存为 .html 后可直接浏览器打开或上传任意静态托管（B 方案 3.3）。
PNG 渲染不可用时降级为内嵌 SVG，保证公开页始终有卡片图。
"""

from __future__ import annotations

import base64
import hashlib
import html as html_escape
import json
from pathlib import Path


def make_card_id(card_data: dict) -> str:
    """按卡片内容生成稳定 ID（date + 内容 hash 前 8 位）。"""
    payload = json.dumps(card_data, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]
    return f"card_{card_data.get('date', 'unknown')}_{digest}"


def render_card_svg(card_data: dict) -> str:
    """纯 Python 渲染 SVG 卡片图（1080×1080，PNG 不可用时的降级内嵌图）。"""
    esc = html_escape.escape

    def _bar(i: int, name: str, score: int) -> str:
        y = 700 + i * 90
        return (
            f'<text x="80" y="{y}" font-size="30" fill="#8b93a7">{esc(name)}</text>'
            f'<rect x="300" y="{y - 24}" width="560" height="10" rx="5" fill="#2a2e38"/>'
            f'<rect x="300" y="{y - 24}" width="{int(score) * 5.6:.0f}" height="10" rx="5" fill="#5b8cff"/>'
            f'<text x="900" y="{y}" font-size="32" font-weight="600" fill="#ffffff">{int(score)}</text>'
        )

    dims = (card_data.get("dimensions") or [])[:3]
    ach = (card_data.get("achievements") or [])[:2]
    ach_rows = "".join(
        f'<text x="80" y="{980 + k * 40}" font-size="28" fill="#d7dce6">'
        f'<tspan fill="#f5c451">★</tspan> {esc(a)}</text>'
        for k, a in enumerate(ach)
    ) or '<text x="80" y="980" font-size="26" fill="#8b93a7">暂无成就，继续修炼</text>'

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">
<rect width="1080" height="1080" fill="#1a1d24"/>
<text x="80" y="110" font-size="28" letter-spacing="6" fill="#8b93a7">ZENSKILL 成长卡片</text>
<text x="80" y="280" font-size="96" font-weight="700" fill="#ffffff">{esc(str(card_data.get("level_name", "")))}</text>
<text x="80" y="340" font-size="30" fill="#8b93a7">{esc(str(card_data.get("level", "")))} · 累计交互 {int(card_data.get("total_interactions", 0))} 次</text>
<rect x="80" y="420" width="920" height="14" rx="7" fill="#2a2e38"/>
<rect x="80" y="420" width="{int(card_data.get("progress_pct", 0)) * 9.2:.0f}" height="14" rx="7" fill="#5b8cff"/>
<text x="80" y="480" font-size="26" fill="#8b93a7">下一境界进度 {int(card_data.get("progress_pct", 0))}%</text>
{''.join(_bar(i, d.get('name', d.get('key', '')), int(d.get('score', 0))) for i, d in enumerate(dims))}
<text x="80" y="660" font-size="30" letter-spacing="3" fill="#8b93a7">最近成就</text>
{ach_rows}
<text x="80" y="1040" font-size="26" fill="#8b93a7">{esc(str(card_data.get("date", "")))}</text>
<text x="800" y="1040" font-size="26" fill="#5b8cff">Powered by ZenSkill</text>
</svg>'''


def _image_data_uri(image_base64: str) -> str:
    b64 = image_base64.strip()
    if b64.startswith("data:"):
        return b64
    return f"data:image/png;base64,{b64}"


def generate_public_page(card_id: str, card_data: dict, image_base64: str) -> str:
    """生成公开分享 HTML 页面（自包含，可直接保存为 .html）。"""
    esc = html_escape.escape
    uri = _image_data_uri(image_base64)
    level_name = esc(str(card_data.get("level_name", "")))
    level = esc(str(card_data.get("level", "")))
    date = esc(str(card_data.get("date", "")))
    interactions = int(card_data.get("total_interactions", 0))
    progress = int(card_data.get("progress_pct", 0))
    top_dims = (card_data.get("dimensions") or [])[:3]
    stat_cells = "".join(
        f'<div class="stat"><div class="stat-num">{int(d.get("score", 0))}</div>'
        f'<div class="stat-label">{esc(str(d.get("name", d.get("key", ""))))}</div></div>'
        for d in top_dims
    )
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta property="og:type" content="website">
<meta property="og:title" content="ZenSkill Growth Card · {level_name}">
<meta property="og:description" content="{level_name}（{level}）· 下一境界进度 {progress}% · 累计交互 {interactions} 次">
<meta property="og:image" content="{uri}">
<title>ZenSkill Growth Card · {level_name}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #1a1d24; color: #ffffff; min-height: 100vh;
    font-family: 'PingFang SC', 'Microsoft YaHei', -apple-system, sans-serif;
    display: flex; justify-content: center; padding: 24px 12px;
  }}
  .container {{ width: 100%; max-width: 560px; margin: auto; }}
  .card-img {{ width: 100%; height: auto; border-radius: 12px; display: block;
    border: 1px solid #2a2e38; }}
  .stats {{ display: flex; gap: 12px; margin-top: 16px; }}
  .stat {{ flex: 1; background: #22262f; border-radius: 10px; padding: 14px; text-align: center; }}
  .stat-num {{ font-size: 28px; font-weight: 600; }}
  .stat-label {{ font-size: 13px; color: #8b93a7; margin-top: 4px; }}
  .meta {{ margin-top: 16px; color: #8b93a7; font-size: 14px; line-height: 1.8; }}
  .footer {{ margin-top: 24px; text-align: center; }}
  .footer a {{ color: #5b8cff; text-decoration: none; font-size: 14px; }}
  .footer a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<div class="container">
  <img class="card-img" src="{uri}" alt="ZenSkill Growth Card">
  <div class="stats">{stat_cells}</div>
  <div class="meta">
    <div>境界：{level_name}（{level}）</div>
    <div>下一境界进度：{progress}%</div>
    <div>累计交互：{interactions} 次 · {date}</div>
  </div>
  <div class="footer"><a href="https://github.com/zen-engine/zenskill">Powered by ZenSkill</a></div>
</div>
</body>
</html>'''


def save_public_page(card_id: str, output_dir: str = "~/.zenskill/shares") -> str:
    """生成并保存公开页，返回文件路径。

    图片来源：优先 playwright 渲染 PNG；不可用时降级内嵌 SVG。
    """
    from .card_data import GrowthCardData
    from .renderer import render_card_html, render_card_png

    card_data = GrowthCardData().get_card_data()
    if not card_id:
        card_id = make_card_id(card_data)

    image_base64 = ""
    try:
        tmp_png = Path(output_dir).expanduser() / f"{card_id}.png"
        tmp_png.parent.mkdir(parents=True, exist_ok=True)
        png_path = render_card_png(render_card_html(card_data), str(tmp_png))
        if png_path:
            image_base64 = base64.b64encode(Path(png_path).read_bytes()).decode("ascii")
    except Exception:
        image_base64 = ""
    if not image_base64:
        image_base64 = base64.b64encode(
            render_card_svg(card_data).encode("utf-8")).decode("ascii")
        mime = "svg+xml"
    else:
        mime = "png"

    page = generate_public_page(
        card_id, card_data, f"data:image/{mime};base64,{image_base64}")

    out_dir = Path(output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    page_path = out_dir / f"{card_id}.html"
    page_path.write_text(page, encoding="utf-8")
    return str(page_path)
