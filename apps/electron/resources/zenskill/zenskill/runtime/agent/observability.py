"""轻量结构化可观测性（O6）：JSONL 事件日志 + 日粒度指标计数。

设计约束：
- 零外部依赖（stdlib），单机部署形态，不引监控栈
- 全部 fire-and-forget：观测失败绝不影响主流程（吞异常，一次性 stderr 提示）
- 目录可被 ZENSKILL_LOG_DIR / ZENSKILL_METRICS_DIR 覆盖（测试隔离）；
  ZENSKILL_OBS=off 一键关闭
- JSONL 按日分文件（agent-YYYYMMDD.jsonl），metrics 按日聚合单文件
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

_warned = False
_lock = threading.Lock()

METRICS_FIELDS = ("turns", "input_tokens", "output_tokens", "tool_calls",
                  "tool_errors", "llm_errors")


def _log_dir() -> Path:
    d = os.environ.get("ZENSKILL_LOG_DIR")
    return Path(d) if d else Path.home() / ".zenskill" / "logs"


def _metrics_path() -> Path:
    d = os.environ.get("ZENSKILL_METRICS_DIR")
    return Path(d) if d else Path.home() / ".zenskill" / "metrics"


def _enabled() -> bool:
    return os.environ.get("ZENSKILL_OBS", "").lower() != "off"


def _warn_once(msg: str) -> None:
    global _warned
    if not _warned:
        _warned = True
        print(f"[observability] {msg}", file=sys.stderr)


def log_event(event: str, **fields: Any) -> None:
    """追加一条结构化事件。任何失败静默（一次性 stderr 提示）。"""
    if not _enabled():
        return
    try:
        record = {"ts": round(time.time(), 3), "event": event, **fields}
        d = _log_dir()
        d.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, default=str)
        with _lock:
            with open(d / f"agent-{date.today():%Y%m%d}.jsonl", "a",
                      encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception as e:  # pragma: no cover - 观测永不影响主流程
        _warn_once(f"log_event failed: {e}")


def bump_metrics(**counters: Any) -> None:
    """日粒度计数累加（仅认 METRICS_FIELDS 中的键，其余忽略）。"""
    if not _enabled():
        return
    clean = {k: v for k, v in counters.items() if k in METRICS_FIELDS}
    if not clean:
        return
    try:
        p = _metrics_path() / "agent-metrics.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            data: Dict[str, Dict[str, Any]] = {}
            if p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            today = date.today().isoformat()
            day = data.setdefault(today, {})
            for k, v in clean.items():
                day[k] = day.get(k, 0) + v
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                           encoding="utf-8")
            os.replace(tmp, p)  # 原子替换，避免并发写撕裂
    except Exception as e:  # pragma: no cover
        _warn_once(f"bump_metrics failed: {e}")


def metrics_summary(days: int = 7) -> Dict[str, Any]:
    """读取近 N 天指标聚合（供 CLI/GUI 展示，只读）。"""
    try:
        p = _metrics_path() / "agent-metrics.json"
        if not p.exists():
            return {"days": 0}
        data = json.loads(p.read_text(encoding="utf-8"))
        keys = sorted(data.keys())[-days:]
        total: Dict[str, Any] = {"days": len(keys)}
        for k in keys:
            for field, v in data[k].items():
                total[field] = total.get(field, 0) + v
        total["by_day"] = {k: data[k] for k in keys}
        return total
    except Exception as e:  # pragma: no cover
        return {"days": 0, "error": str(e)}
