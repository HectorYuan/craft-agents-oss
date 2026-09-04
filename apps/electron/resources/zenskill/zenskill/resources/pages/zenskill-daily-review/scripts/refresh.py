#!/usr/bin/env python3
"""ZenSkill 每日复盘 Pages 刷新脚本（craft Pages python3 runtime）。

由宿主 cron（page.json refresh spec，默认每日 07:00）调度执行：
- 通过 ZenSkill 只读工具收集复盘数据（daily_review / companion_summary /
  energy_level / achievement_list），调用链做防御性设计：
    1. 进程内 import zenskill → build_default_registry().call()
       （与 `zenskill mcp serve` 完全相同的工具面）
    2. 失败时换子进程（sys.executable -c）重试一次
    3. 任一工具失败只降级该字段，绝不阻断 snapshot 生成
- 组装 PageDataSnapshot（version 1，kv + series）写入
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
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("zenskill.pages.refresh")

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

    说明：zen. CLI 目前没有 daily_review 等只读工具的子命令面，
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


def _energy_pct_100(raw) -> float | None:
    """引擎 pct（0-1）→ 显示百分比（0-100）"""
    if raw is None:
        return None
    try:
        return round(min(max(float(raw), 0.0), 1.0) * 100, 1)
    except (TypeError, ValueError):
        return None


def _recent_achievements(achievements: dict | None, days: int = 1) -> list[dict]:
    """最近 N 天新解锁成就 [{icon, title}]。

    首选：解锁历史（~/.zenskill/.../growth/achievements.json）里的
    unlocked_at 时间戳判定"新"；历史不可读时回退为已解锁徽章前 5 个。
    """
    badges = (achievements or {}).get("badges", []) or []
    by_id = {b.get("id"): b for b in badges if isinstance(b, dict)}
    try:
        from zenskill.core.paths import get_user_data_dir

        hist_path = get_user_data_dir() / "growth" / "achievements.json"
        history = json.loads(hist_path.read_text(encoding="utf-8")).get(SKILL_ID, {})
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        new_ids = [
            bid for bid, info in history.items()
            if str((info or {}).get("unlocked_at", "")) >= cutoff
        ]
        items = []
        for bid in new_ids:
            badge = by_id.get(bid) or {}
            items.append({
                "icon": badge.get("icon", "🏅"),
                "title": badge.get("title") or (history[bid] or {}).get("title", bid),
            })
        if items:
            return items[:5]
        # 历史可读但确实没有新解锁——这是正常状态，不再回退
        return []
    except Exception as exc:  # noqa: BLE001 — 历史不可读才走回退
        logger.warning("achievement history unavailable: %s", exc)
        return [
            {"icon": b.get("icon", "🏅"), "title": b.get("title", "")}
            for b in badges[:5]
        ]


# ============================================================
# series：energy_history（最近 7 天每日收尾能量，0-100）
# ============================================================

def _reconstruct_daily_energy() -> list[dict] | None:
    """从能量引擎持久层重建最近 7 天每日收尾能量百分比。

    E_end(d) = E_now - Σrecover(晚于 d) + Σburn(晚于 d)，
    历史仅保留最近 100 条事件，更早的日期以当前值近似。
    """
    try:
        from zenskill.core.paths import get_user_data_dir

        data = json.loads(
            (get_user_data_dir() / "gtd" / "energy.json").read_text(encoding="utf-8"))
        current = float(data.get("current_energy", 0))
        max_energy = max(float(data.get("max_energy", 1)), 1)
        history = data.get("history") or []

        now = datetime.now()
        points = []
        for offset in range(6, -1, -1):  # 升序：6 天前 → 今天
            day = now - timedelta(days=offset)
            next_day = (day + timedelta(days=1)).strftime("%Y-%m-%d")
            net_after = 0.0
            for h in history:
                at = str(h.get("at", ""))
                if at >= next_day:  # ISO 格式可直接字典序比较
                    amount = float(h.get("amount", 0))
                    net_after += amount if h.get("type") == "recover" else -amount
            end_energy = min(max(current - net_after, 0.0), max_energy)
            day_end = day.replace(hour=23, minute=59, second=59, microsecond=0)
            points.append({
                "t": int(time.mktime(day_end.timetuple()) * 1000),
                "v": round(end_energy / max_energy * 100, 1),
            })
        return points
    except Exception as exc:  # noqa: BLE001 — 重建失败由调用方降级
        logger.warning("energy history reconstruction failed: %s", exc)
        return None


def _energy_series(default_pct: float | None) -> list[dict]:
    """series.energy_history：重建失败时降级为单点当前值"""
    points = _reconstruct_daily_energy()
    if points:
        return points
    if default_pct is not None:
        return [{"t": int(time.time() * 1000), "v": default_pct}]
    return []


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
    review = _call_tool("daily_review")
    companion = _call_tool("companion_summary")
    energy = _call_tool("energy_level")
    achievements = _call_tool("achievement_list", {"skill_id": SKILL_ID})

    energy_status = (energy or {}).get("status") or {}
    energy_kv = (companion or {}).get("energy") or {}
    level = _pick(energy_status.get("level"), energy_kv.get("level"),
                  ((review or {}).get("energy") or {}).get("level"), "unknown")
    pct = _pick(_energy_pct_100(energy_status.get("pct")),
                _energy_pct_100(energy_kv.get("pct")))

    now_ms = int(time.time() * 1000)
    kv = {
        "review_message": _pick(
            (review or {}).get("message"),
            "今日复盘数据暂不可用——请确认 ZenSkill 运行环境"),
        "companion_mood": (companion or {}).get("mood", ""),
        "energy_level": level,
        "energy_pct": pct,
        "inbox_pending": _pick((companion or {}).get("inbox_pending"),
                               ((review or {}).get("inbox") or {}).get("pending"), 0),
        "pending_actions": _pick((companion or {}).get("pending_actions"), 0),
        "achievements_new": _recent_achievements(achievements),
        "generated_at": now_ms,
    }
    return {
        "version": 1,
        "generatedAt": now_ms,
        "kv": kv,
        "series": {"energy_history": _energy_series(pct)},
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
