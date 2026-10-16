"""Pages zenskill-* 页面包 — 已退役（2026-10-01 拍板）。

历史沿革：
- 播种机制：zenskill/resources/pages/{slug}/ 播种到 {workspace_root}/pages/，
  66c1ca7 退役 create_session 自动播种（934011c rebase 回潮、41dbab7 二次移除，
  TestPagesSeedRetired 反向断言防线）
- 模版池：磁盘五页（dashboard/daily-review/growth/skill-graph/zenloop）降级
  为按需模版（仅 CLI 可达，WS handler 从未建成，GUI 无入口）
- 本拍板：五模版页彻底退役——模版池资源、实例化/列举基础设施、CLI 命令组
  全部移除；ZenSkill 侧栏 React 页（概览/洞察/画像/技能图谱/ZenLoop）为唯一
  等价面；Craft 通用 Pages 通道（pages:get/create/lease/grants 等通用 handler）
  保留，服务用户自建页面

本模块现仅保留：
- resolve_active_workspace_root：TUI automations 页依赖的活跃 workspace 解析
- cleanup_retired_zenkill_pages：存量播种实体一次性清扫（server 启动时调用）
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

# 系统管理命名空间：退役清扫只删该前缀的 slug（用户自建页面绝不触碰）
MANAGED_SLUG_PREFIX = "zenskill-"

# 退役的五个 zenskill 播种页 slug（等价功能见侧栏 React 页）
RETIRED_PAGE_SLUGS = frozenset({
    "zenskill-daily-review",
    "zenskill-dashboard",
    "zenskill-growth",
    "zenskill-skill-graph",
    "zenskill-zenloop",
})

_ENCODING = "utf-8"


def resolve_active_workspace_root() -> Path | None:
    """从桌面端 config.json 解析活跃 workspace 根目录。

    优先读桌面数据目录 ~/.zenskill/desktop/config.json（P3 后约定），
    回退顶层 ~/.zenskill/config.json（同 schema，跟随桌面端写入方）。
    仅当 workspace 根目录真实存在时返回（旧配置可能残留指向
    ~/.craft-agent 的悬空 rootPath，不得为其重建目录树）。
    """
    for config_path in (
        Path.home() / ".zenskill" / "desktop" / "config.json",
        Path.home() / ".zenskill" / "config.json",
    ):
        try:
            cfg = json.loads(config_path.read_text(encoding=_ENCODING))
            active_id = cfg.get("activeWorkspaceId", "")
            for ws in cfg.get("workspaces", []):
                if ws.get("id") == active_id:
                    root = Path(ws["rootPath"]).expanduser()
                    if root.is_dir():
                        return root
        except Exception:  # noqa: BLE001 — 当前路径无配置时尝试下一个
            pass
    return None


def _load_page_json(path: Path) -> dict | None:
    """读 page.json；缺失/坏 JSON 返回 None（清扫路径容错用）"""
    try:
        cfg = json.loads(path.read_text(encoding=_ENCODING))
        return cfg if isinstance(cfg, dict) else None
    except Exception:  # noqa: BLE001 — 坏文件按未识别处理，不阻塞清扫
        return None


def cleanup_retired_zenkill_pages(workspace_root: Path) -> list[str]:
    """清扫 workspace 内退役的 zenskill-* 播种页实体，返回被删 slug 列表。

    识别口径（满足其一即删）：
    - 目录名在 RETIRED_PAGE_SLUGS
    - page.json 的 slug 在 RETIRED_PAGE_SLUGS
    - page.json 带 template=true（退役后模版标记即退役标记）

    边界：CLI createFromTemplate 实例化产生的自命名实例（slug 为用户命名、
    template 标记已剥除）不可识别，不在此清扫范围——该入口从未接入 GUI，
    实际存在概率趋零；若确有，用户可经 pages:delete 手动清理。
    """
    removed: list[str] = []
    pages_root = Path(workspace_root) / "pages"
    if not pages_root.is_dir():
        return removed
    for page_dir in sorted(pages_root.iterdir()):
        if not page_dir.is_dir():
            continue
        cfg = _load_page_json(page_dir / "page.json") or {}
        slug = str(cfg.get("slug") or page_dir.name)
        if (
            page_dir.name in RETIRED_PAGE_SLUGS
            or slug in RETIRED_PAGE_SLUGS
            or cfg.get("template") is True
        ):
            shutil.rmtree(page_dir, ignore_errors=True)
            removed.append(slug)
    return removed
