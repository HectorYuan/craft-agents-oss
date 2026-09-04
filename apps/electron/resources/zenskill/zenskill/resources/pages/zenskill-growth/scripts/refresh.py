#!/usr/bin/env python3
"""ZenSkill Growth 成长中心 Pages 刷新脚本（craft Pages python3 runtime）。

由宿主 cron（page.json refresh spec，默认每 2 小时）调度执行：
- 通过 ZenSkill 只读工具收集成长数据（growth_dashboard / achievement_list /
  habit_analyze / energy_level / goal_progress），调用链做防御性设计：
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
from pathlib import Path

logger = logging.getLogger("zenskill.pages.growth.refresh")

# 页面目录：{workspace_root}/pages/{slug}/（脚本被播种到 scripts/ 子目录）
PAGE_DIR = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = PAGE_DIR / "data" / "snapshot.json"

SKILL_ID = "zenskill-core"
HABIT_DAYS = 28

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

    说明：zen. CLI 目前没有 growth_dashboard 等只读工具的子命令面，
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


# 境界升级阈值（systems/cultivating/skill_manifest.py upgrade_thresholds 同源）
_LEVEL_BANDS = {
    "NOVICE": (0, 10),
    "APPRENTICE": (10, 50),
    "ADEPT": (50, 200),
    "EXPERT": (200, 500),
    "MASTER": (500, None),
}


def _level_progress(level, usage_count) -> float | None:
    """当前境界进度（0-1），MASTER 满级返回 None"""
    band = _LEVEL_BANDS.get(str(level or "").upper())
    if not band or band[1] is None:
        return None
    lo, hi = band
    try:
        n = max(0, int(usage_count or 0))
    except (TypeError, ValueError):
        return None
    return round(min(max((n - lo) / (hi - lo), 0.0), 1.0), 3)


# 五维权重（systems/visualization/ability_calculator.py composite 同源）
_ABILITY_WEIGHTS = (
    ("proficiency", 0.3),
    ("stability", 0.25),
    ("satisfaction", 0.2),
    ("responsiveness", 0.15),
    ("memory", 0.1),
)


def _select_skill(dashboard: dict | None) -> dict:
    """growth_dashboard 多技能时优先 zenskill-core，否则取第一条"""
    skills = (dashboard or {}).get("skills") or []
    for s in skills:
        if isinstance(s, dict) and s.get("skill_id") == SKILL_ID:
            return s
    return skills[0] if skills and isinstance(skills[0], dict) else {}


def _ability_block(scores) -> tuple[dict, int]:
    """五维 scores（asdict 后无 composite 属性）→ (ability, composite)。

    composite 按引擎同款加权平均在本地重算；scores 缺失时五维全 0，
    前端雷达仍可渲染零多边形（数据缺失 ≠ 白屏）。
    """
    ability = {}
    for key, _ in _ABILITY_WEIGHTS:
        raw = (scores or {}).get(key)
        try:
            ability[key] = max(0, min(100, int(raw)))
        except (TypeError, ValueError):
            ability[key] = 0
    composite = round(sum(ability[k] * w for k, w in _ABILITY_WEIGHTS))
    return ability, composite


def _recent_unlocked(achievements: dict | None, limit: int = 3) -> list[dict]:
    """最近解锁 limit 个徽章。

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


def _next_achievements(achievements: dict | None, limit: int = 3) -> list[dict]:
    """locked 徽章按 progress 降序取前 limit 个（"即将解锁"）"""
    rows = []
    for b in (achievements or {}).get("locked", []) or []:
        if not isinstance(b, dict):
            continue
        try:
            prog = float(b.get("progress", 0))
        except (TypeError, ValueError):
            prog = 0.0
        rows.append({
            "icon": b.get("icon", "🔒"),
            "title": b.get("title", ""),
            "progress": round(min(max(prog, 0.0), 1.0), 2),
        })
    rows.sort(key=lambda r: r["progress"], reverse=True)
    return rows[:limit]


def _habit_rows(analysis: dict | None) -> list[dict]:
    """习惯行：{title, streak, best_streak, completion_rate(0-100), daily(28 天 bool map)}"""
    rows = []
    for r in (analysis or {}).get("habits") or []:
        if not isinstance(r, dict):
            continue
        completed = r.get("completed") or {}
        daily = {d: bool(completed[d]) for d in sorted(completed)}
        try:
            rate = round(float(r.get("completion_rate", 0)) * 100)
        except (TypeError, ValueError):
            rate = 0
        rows.append({
            "title": r.get("title", ""),
            "streak": int(r.get("streak", 0) or 0),
            "best_streak": int(r.get("best_streak", 0) or 0),
            "completion_rate": rate,
            "daily": daily,
        })
    return rows


def _energy_block(energy: dict | None) -> dict:
    status = (energy or {}).get("status") or {}
    suggestions = ((energy or {}).get("advice") or {}).get("suggestions") or []
    return {
        "level": status.get("level", "unknown"),
        "pct": _energy_pct_100(status.get("pct")),
        "current": status.get("current_energy"),
        "max": status.get("max_energy"),
        "advice": suggestions[0] if suggestions else "",
    }


def _goal_rows(progress: dict | None) -> list[dict]:
    rows = []
    for g in (progress or {}).get("active") or []:
        if not isinstance(g, dict):
            continue
        rows.append({
            "dimension": g.get("dimension", ""),
            "current": g.get("current_score"),
            "target": g.get("target_score"),
            "pct": g.get("progress_pct"),
        })
    return rows


# ============================================================
# series：ability_composite_trend（state history 重建，可得才输出）
# ============================================================

# 满意度/记忆力历史不可重建，沿用 TuiDataAdapter 的运行时默认值
_SERIES_FEEDBACK_DEFAULT = 0.8
_SERIES_MEMORY_DEFAULT = 0
_SERIES_MAX_POINTS = 30


def _composite_trend() -> list[dict] | None:
    """从 SkillStateManager 状态历史重建综合能力趋势。

    每条 history 记录的 snapshot.metrics 含 usage_count / success_rate /
    avg_duration_ms，按 AbilityCalculator 公式重算当日 composite
    （satisfaction/memory 用运行时默认值近似）；同一天取最后一条。
    历史不可读或有效点 < 2 时返回 None（series 键整体省略）。
    """
    try:
        from zenskill.core.paths import get_state_history_path

        hist_path = get_state_history_path(SKILL_ID, autocreate=False)
        by_day: dict[str, float] = {}
        with open(hist_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                metrics = (record.get("snapshot") or {}).get("metrics") or {}
                usage = metrics.get("total_executions") or metrics.get("usage_count")
                if not usage:
                    continue
                success = int(metrics.get("successful_executions", 0))
                proficiency = min(100, int(usage) // 5)
                stability = round(success / max(1, int(usage)) * 100)
                avg_ms = float(metrics.get("avg_duration_ms", 0) or 0)
                responsiveness = max(0, round(100 - avg_ms / 50))
                composite = round(
                    proficiency * 0.3
                    + stability * 0.25
                    + _SERIES_FEEDBACK_DEFAULT * 100 * 0.2
                    + responsiveness * 0.15
                    + min(100, _SERIES_MEMORY_DEFAULT // 2) * 0.1
                )
                day = str(record.get("timestamp", ""))[:10]
                if day:
                    by_day[day] = composite  # 后写覆盖：同日取最后一条
        days = sorted(by_day)
        if len(days) < 2:
            return None
        step = max(1, len(days) // _SERIES_MAX_POINTS)
        sampled = days[::step]
        if sampled[-1] != days[-1]:
            sampled.append(days[-1])
        points = []
        for day in sampled:
            try:
                t = int(time.mktime(time.strptime(day, "%Y-%m-%d")) * 1000)
            except ValueError:
                continue
            points.append({"t": t, "v": by_day[day]})
        return points or None
    except Exception as exc:  # noqa: BLE001 — 历史不可得则省略该 series
        logger.warning("composite trend unavailable: %s", exc)
        return None


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
    dashboard = _call_tool("growth_dashboard")
    achievements = _call_tool("achievement_list", {"skill_id": SKILL_ID})
    habits = _call_tool("habit_analyze", {"days": HABIT_DAYS})
    energy = _call_tool("energy_level")
    goals = _call_tool("goal_progress", {"skill_id": SKILL_ID})

    skill = _select_skill(dashboard)
    level = _pick(skill.get("level"), "NOVICE")
    usage_count = _pick(skill.get("usage_count"), 0)
    ability, composite = _ability_block(skill.get("scores"))

    achievements_block = {
        "unlocked_count": _pick((achievements or {}).get("count"), 0),
        "locked_total": _pick(
            (achievements or {}).get("total"), 0) - _pick(
            (achievements or {}).get("count"), 0),
        "completion_rate": _pick((achievements or {}).get("completion_rate"), 0),
        "recent": _recent_unlocked(achievements),
        "next": _next_achievements(achievements),
    }

    series = {}
    trend = _composite_trend()
    if trend:
        series["ability_composite_trend"] = trend

    now_ms = int(time.time() * 1000)
    kv = {
        "level": level,
        "level_progress": _level_progress(level, usage_count),
        "usage_count": usage_count,
        "success_rate": _pick(skill.get("success_rate"), 0),
        "composite": composite,
        "ability": ability,
        "achievements": achievements_block,
        "habits": _habit_rows(habits),
        "energy": _energy_block(energy),
        "goals": _goal_rows(goals),
        "generated_at": now_ms,
    }
    return {
        "version": 1,
        "generatedAt": now_ms,
        "kv": kv,
        "series": series,
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
