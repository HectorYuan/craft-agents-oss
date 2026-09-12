"""B 方案观察期指标采集——数据驱动，不设固定期限。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict


def get_card_count() -> int:
    """获取已生成的分享卡片数量。"""
    shares_dir = Path.home() / ".zenskill" / "shares"
    if not shares_dir.exists():
        return 0
    return len(list(shares_dir.glob("card_*.png")))


def get_public_page_count() -> int:
    """获取公开页数量。"""
    shares_dir = Path.home() / ".zenskill" / "shares"
    if not shares_dir.exists():
        return 0
    return len(list(shares_dir.glob("*.html")))


def get_observation_summary() -> Dict[str, Any]:
    """返回观察期摘要（供 CLI 或 TUI 展示）。"""
    return {
        "card_count": get_card_count(),
        "public_page_count": get_public_page_count(),
        "shares_dir": str(Path.home() / ".zenskill" / "shares"),
    }


def get_companion_metrics(days: int = 7) -> Dict[str, Any]:
    """获取陪伴指标（从 mirroring 事件分析）。

    统计近 N 天的 companion 相关事件计数。
    """
    events_path = Path.home() / ".zenskill" / "mirroring" / "events.jsonl"
    if not events_path.exists():
        return {"events_available": False}

    cutoff = time.time() - days * 86400
    counts: Dict[str, int] = {"displayed": 0, "insight_clicked": 0, "feedback": 0}

    try:
        with open(events_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = event.get("timestamp", 0)
                if ts < cutoff:
                    continue

                etype = event.get("event_type", "") or event.get("task", "")
                if etype == "companion_displayed":
                    counts["displayed"] += 1
                elif etype in ("companion_insight_clicked", "insight_clicked"):
                    counts["insight_clicked"] += 1
                elif etype in ("companion_feedback", "feedback_triggered"):
                    counts["feedback"] += 1
    except OSError:
        pass

    return {**counts, "events_available": True, "days": days}
