#!/usr/bin/env python3
"""ZenSkill Dashboard 首页 Pages 刷新脚本（craft Pages python3 runtime）。

由宿主 cron（page.json refresh spec，每小时整点）调度执行：
- 聚合七类只读工具收集首页数据（companion_summary / daily_review /
  energy_level / proactive_insight / achievement_list / action_list /
  habit_analyze），调用链做防御性设计：
    1. 进程内 import zenskill → build_default_registry().call()
       （与 `zenskill mcp serve` 完全相同的工具面）
    2. 失败时换子进程（sys.executable -c）重试一次
    3. 任一工具失败只降级该字段，绝不阻断 snapshot 生成
- 组装 PageDataSnapshot（version 1，kv）写入
  pages/{slug}/data/snapshot.json（tmp + os.replace 原子写）

snapshot 是唯一跨进程数据契约；本脚本只写 data/ 目录，
绝不触碰 page.json / index.html（page.json 由宿主作为完成标记写）。
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

logger = logging.getLogger("zenskill.pages.dashboard.refresh")

# 页面目录：{workspace_root}/pages/{slug}/（脚本被播种到 scripts/ 子目录）
PAGE_DIR = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = PAGE_DIR / "data" / "snapshot.json"

SKILL_ID = "zenskill-core"

# 工具调用超时（秒）——refresh spec 的 timeoutMs（60s）之内必须完成
_TOOL_TIMEOUT_S = 30.0

_SUBPROCESS_SNIPPET = (
    "import json, sys; "
    "from zenskill.runtime.mcp.registry import build_default_registry; "
    "print(build_default_registry().call(sys.argv[1], json.loads(sys.argv[2])))"
)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _call_tool_inprocess(name: str, args: dict) -> dict:
    """进程内调用 ZenSkill 工具（与 MCP server 同一 registry）"""
    from zenskill.runtime.mcp.registry import build_default_registry

    registry = build_default_registry()
    if not registry.has(name):
        raise RuntimeError(f"tool not registered: {name}")
    return json.loads(registry.call(name, args))


def _call_tool_subprocess(name: str, args: dict) -> dict:
    """降级第二层：当前解释器 import 失败时换子进程再试一次。

    说明：zen. CLI 目前没有 companion_summary 等只读工具的子命令面，
    这里直接复用 registry 调用面（sys.executable 与本脚本同解释器）。
    """
    proc = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_SNIPPET, name, json.dumps(args or {})],
        capture_output=True,
        text=True,
        timeout=_TOOL_TIMEOUT_S,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"subprocess exit {proc.returncode}: {proc.stderr.strip()[:200]}")
    return json.loads(proc.stdout)


def _call_tool(name: str, args: dict | None = None) -> dict | None:
    """防御性工具调用：两层链路任选其一，全失败返回 None（字段级降级）"""
    args = args or {}
    for attempt, caller in enumerate((_call_tool_inprocess, _call_tool_subprocess), start=1):
        try:
            result = caller(name, args)
            return result if isinstance(result, dict) else None
        except Exception as exc:  # noqa: BLE001 — 任何失败都降级为缺数据
            logger.warning("tool %s attempt %d failed: %s", name, attempt, exc)
    return None


# ============================================================
# kv 字段组装（字段级降级：缺工具 → 缺省值）
# ============================================================

def _pick(*values):
    """返回第一个非 None 值"""
    for v in values:
        if v is not None:
            return v
    return None


def _greeting(now_ms: int) -> str:
    """时间感知问候语（按 generated_at 小时段，三段口径）"""
    hour = time.localtime(now_ms / 1000).tm_hour
    if 5 <= hour < 12:
        return "早上好"
    if 12 <= hour < 18:
        return "下午好"
    return "晚上好"


# companion_summary 的 mood 会内嵌问候前缀（"早上好——……"），
# 两端口径（中午好/夜深了）可能不一致，统一剥掉避免页面重复问候
_KNOWN_GREETINGS = ("早上好", "中午好", "下午好", "晚上好", "夜深了")


def _strip_greeting_prefix(mood: str | None) -> str:
    text = str(mood or "").strip()
    for prefix in _KNOWN_GREETINGS:
        if text.startswith(prefix):
            rest = text[len(prefix):]
            stripped = rest.lstrip("—–-")
            # 前缀后确实跟着问候分隔符才剥，避免误伤以问候词开头的正文
            return stripped if stripped != rest else text
    return text


def _energy_pct_100(raw) -> float | None:
    """引擎 pct（0-1）→ 显示百分比（0-100）"""
    if raw is None:
        return None
    try:
        return round(min(max(float(raw), 0.0), 1.0) * 100, 1)
    except (TypeError, ValueError):
        return None


def _energy_block(energy: dict | None, companion: dict | None) -> dict:
    """能量块：energy_level 引擎为准，companion_summary 兜底"""
    status = (energy or {}).get("status") or {}
    comp_energy = (companion or {}).get("energy") or {}
    return {
        "level": _pick(status.get("level"), comp_energy.get("level"), "unknown"),
        "pct": _pick(_energy_pct_100(status.get("pct")),
                     _energy_pct_100(comp_energy.get("pct"))),
        "current": _pick(status.get("current_energy"), comp_energy.get("current")),
        "max": _pick(status.get("max_energy"), comp_energy.get("max")),
    }


def _insight_block(insights: dict | None, companion: dict | None) -> dict | None:
    """最新一条洞察 {title, type}；两源都拿不到时返回 None（前端占位）"""
    items = (insights or {}).get("items") or []
    for item in items:
        if isinstance(item, dict) and (item.get("title") or item.get("content")):
            return {"title": item.get("title") or item.get("content"),
                    "type": item.get("type", "info")}
    top = (companion or {}).get("top_insight")
    if isinstance(top, dict) and top.get("title"):
        return {"title": top.get("title"), "type": top.get("type", "info")}
    return None


def _recent_unlocked(achievements: dict | None, limit: int = 3) -> list[dict]:
    """最近解锁 limit 个徽章 [{icon, title}]。

    首选解锁历史（~/.zenskill/.../growth/achievements.json）按
    unlocked_at 倒序；历史不可读/为空时回退为已解锁徽章前 limit 个。
    """
    badges = (achievements or {}).get("badges", []) or []
    by_id = {b.get("id"): b for b in badges if isinstance(b, dict)}
    try:
        from zenskill.core.paths import get_user_data_dir

        hist_path = get_user_data_dir() / "growth" / "achievements.json"
        history = json.loads(hist_path.read_text(encoding="utf-8")).get(SKILL_ID, {})
        ordered = sorted(
            history.items(),
            key=lambda kv: str((kv[1] or {}).get("unlocked_at", "")),
            reverse=True,
        )
        if ordered:
            items = []
            for bid, info in ordered:
                badge = by_id.get(bid) or {}
                items.append({
                    "icon": badge.get("icon", "🏅"),
                    "title": badge.get("title") or (info or {}).get("title", bid),
                })
            return items[:limit]
    except Exception as exc:  # noqa: BLE001 — 历史不可读才走回退
        logger.warning("achievement history unavailable: %s", exc)
    return [
        {"icon": b.get("icon", "🏅"), "title": b.get("title", "")}
        for b in badges if isinstance(b, dict)
    ][:limit]


def _next_action_rows(actions: dict | None, limit: int = 5) -> list[dict]:
    """推荐下一步 [{title, priority, due_date}]（引擎已按优先级排序）"""
    rows = []
    for item in (actions or {}).get("items") or []:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        rows.append({
            "title": item.get("title", ""),
            "priority": item.get("priority", "P2"),
            "due_date": item.get("due_date") or "",
        })
        if len(rows) >= limit:
            break
    return rows


def _habit_rows(analysis: dict | None, limit: int = 5) -> list[dict]:
    """习惯行 [{title, streak}]，按 streak 降序取前 limit 个"""
    rows = []
    for r in (analysis or {}).get("habits") or []:
        if not isinstance(r, dict):
            continue
        rows.append({
            "title": r.get("title", ""),
            "streak": int(r.get("streak", 0) or 0),
        })
    rows.sort(key=lambda r: r["streak"], reverse=True)
    return rows[:limit]


# ============================================================
# snapshot 原子写
# ============================================================

def _atomic_write_json(path: Path, data: dict) -> None:
    """tmp + os.replace 原子写（不依赖 zenskill 包，降级路径也可用）"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def build_snapshot() -> dict:
    """收集数据并组装 PageDataSnapshot（字段级降级，尽力而为）"""
    companion = _call_tool("companion_summary")
    review = _call_tool("daily_review")
    energy = _call_tool("energy_level")
    insights = _call_tool("proactive_insight")
    achievements = _call_tool("achievement_list", {"skill_id": SKILL_ID})
    actions = _call_tool("action_list", {"status": "pending", "limit": 5})
    habits = _call_tool("habit_analyze", {"days": 7})

    now_ms = int(time.time() * 1000)
    ach_unlocked = _pick((achievements or {}).get("count"), 0)
    ach_total = _pick((achievements or {}).get("total"), 0)

    kv = {
        "greeting": _greeting(now_ms),
        "mood": _strip_greeting_prefix(
            _pick((companion or {}).get("mood"), (companion or {}).get("greeting"))),
        "energy": _energy_block(energy, companion),
        "review_message": _pick(
            (review or {}).get("message"),
            "今日复盘数据暂不可用——请确认 ZenSkill 运行环境"),
        "insight": _insight_block(insights, companion),
        "achievements": {
            "unlocked_count": ach_unlocked,
            "total": ach_total,
            "recent": _recent_unlocked(achievements),
        },
        "next_actions": _next_action_rows(actions),
        "habits": _habit_rows(habits),
        "overdue": _pick((companion or {}).get("overdue"), 0),
        "due_today": _pick((companion or {}).get("due_today"), 0),
        "inbox_pending": _pick((companion or {}).get("inbox_pending"),
                               ((review or {}).get("inbox") or {}).get("pending"), 0),
        "generated_at": now_ms,
    }
    return {
        "version": 1,
        "generatedAt": now_ms,
        "kv": kv,
        "series": {},
    }


def main() -> int:
    _setup_logging()
    try:
        snapshot = build_snapshot()
        _atomic_write_json(SNAPSHOT_PATH, snapshot)
        logger.info("snapshot written: %s", SNAPSHOT_PATH)
        return 0
    except Exception as exc:  # noqa: BLE001 — 刷新失败必须让宿主感知
        logger.exception("refresh failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
