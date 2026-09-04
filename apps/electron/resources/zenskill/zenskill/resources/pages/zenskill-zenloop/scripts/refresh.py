#!/usr/bin/env python3
"""ZenSkill ZenLoop 循环 Pages 刷新脚本（craft Pages python3 runtime）。

由宿主 cron（page.json refresh spec，每小时第 15 分）调度执行：
- 通过 ZenSkill 只读工具收集孵化池数据（zenloop_status / incubating_list /
  daily_review），调用链做防御性设计：
    1. 进程内 import zenskill → build_default_registry().call()
       （与 `zenskill mcp serve` 完全相同的工具面）
    2. 失败时换子进程（sys.executable -c）重试一次
    3. 任一工具失败只降级该字段，绝不阻断 snapshot 生成
- 组装 PageDataSnapshot（version 1，kv；series 本页无时间序列，恒为空）写入
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

logger = logging.getLogger("zenskill.pages.zenloop.refresh")

# 页面目录：{workspace_root}/pages/{slug}/（脚本被播种到 scripts/ 子目录）
PAGE_DIR = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = PAGE_DIR / "data" / "snapshot.json"

# 四通道固定顺序（systems/gtd/incubating.py channel 取值域）
CHANNELS = ("reflect", "consolidate", "insight", "purify")

# 条目抓取上限——与 zenloop_status 内部的 limit=50 对齐
INCUBATING_LIMIT = 50

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

    说明：zen. CLI 目前没有 zenloop_status 等只读工具的子命令面，
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


def _maturity_01(raw) -> float:
    """引擎 maturity（0-1）→ 快照同量纲（前端负责 ×100 显示百分比）"""
    try:
        return round(min(max(float(raw or 0), 0.0), 1.0), 3)
    except (TypeError, ValueError):
        return 0.0


def _channel_rows(items) -> dict[str, list[dict]]:
    """incubating_list 条目按四通道分组（通道缺失 → 空数组，前端渲染"暂无条目"）"""
    rows: dict[str, list[dict]] = {ch: [] for ch in CHANNELS}
    for it in items or []:
        if not isinstance(it, dict):
            continue
        channel = it.get("channel", "")
        if channel not in rows:
            continue
        rows[channel].append({
            "concept": it.get("raw_concept", ""),
            "maturity": _maturity_01(it.get("maturity")),
            "check_after": it.get("check_after", ""),
            "status": it.get("status", ""),
        })
    return rows


def _loop_stats(overview: dict | None) -> dict | None:
    """zenloop_status 概览 → loop_stats（工具失败时整个键省略）"""
    if not overview:
        return None
    return {
        "active": overview.get("active"),
        "by_channel": overview.get("by_channel") or {},
    }


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
    overview = _call_tool("zenloop_status")
    listing = _call_tool(
        "incubating_list", {"status": "active", "limit": INCUBATING_LIMIT})
    review = _call_tool("daily_review")

    now_ms = int(time.time() * 1000)
    kv: dict = {
        "channels": _channel_rows((listing or {}).get("items")),
        "summary": _pick(
            (overview or {}).get("message"),
            "孵化池状态暂不可用——请确认 ZenSkill 运行环境"),
        "generated_at": now_ms,
    }
    stats = _loop_stats(overview)
    if stats is not None:
        kv["loop_stats"] = stats
    review_message = (review or {}).get("message")
    if review_message:
        kv["review_message"] = review_message

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
