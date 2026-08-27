"""会话用量统计与成本记账（M4-5，B4）。

SQLite 落库 ~/.zenskill/agent_stats.db；费率表 $/1M tokens（主流模型，
近似值，供成本可观测而非计费）。provider 重试在各自 stream 模块内实现
（仅连接建立/首字节前失败重试，流开始后不重试）。
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, Optional

from .types import Usage

STATS_DB = Path.home() / ".zenskill" / "agent_stats.db"

# 近似费率 $/1M tokens（input, output）
COST_TABLE: Dict[str, tuple] = {
    "deepseek-chat": (0.27, 1.10),
    "deepseek-v4-flash": (0.14, 0.56),
    "deepseek-reasoner": (0.55, 2.19),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "qwen-plus": (0.40, 1.20),
    "doubao-pro-32k": (0.10, 0.30),
    "mimo-v2.5-pro": (0.20, 0.80),
    "mimo-v2.5": (0.10, 0.40),
}


def estimate_cost_usd(model_id: str, usage: Usage) -> float:
    rates = COST_TABLE.get(model_id)
    if not rates:
        return 0.0
    return usage.input / 1_000_000 * rates[0] + usage.output / 1_000_000 * rates[1]


class SessionStats:
    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = Path(db_path) if db_path else STATS_DB
        with self._conn() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, model TEXT NOT NULL, session_id TEXT, turns INTEGER, input_tokens INTEGER, output_tokens INTEGER, total_tokens INTEGER, cost_usd REAL)")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection that is committed on success, rolled back on
        error, and always closed afterward (avoids leaking connections).
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record_run(self, model: str, session_id: Optional[str], turns: int,
                   usage: Usage) -> float:
        cost = estimate_cost_usd(model.split("/")[-1], usage)
        params = (time.time(), model, session_id, turns, usage.input, usage.output, usage.total_tokens, cost)
        with self._conn() as conn:
            conn.execute("INSERT INTO runs (ts, model, session_id, turns, input_tokens, output_tokens, total_tokens, cost_usd) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", params)
        return cost

    def summary(self, days: int = 30) -> Dict:
        cutoff = time.time() - days * 86400
        with self._conn() as conn:
            overall = conn.execute("SELECT COUNT(*) n, SUM(input_tokens) i, SUM(output_tokens) o, SUM(total_tokens) t, SUM(cost_usd) c FROM runs WHERE ts >= ?", (cutoff,)).fetchone()
            by_model = conn.execute("SELECT model, COUNT(*) n, SUM(total_tokens) t, SUM(cost_usd) c FROM runs WHERE ts >= ? GROUP BY model ORDER BY t DESC", (cutoff,)).fetchall()
        return {
            "days": days,
            "runs": overall["n"] or 0,
            "input_tokens": overall["i"] or 0,
            "output_tokens": overall["o"] or 0,
            "total_tokens": overall["t"] or 0,
            "cost_usd": round(overall["c"] or 0.0, 4),
            "by_model": [
                {"model": r["model"], "runs": r["n"],
                 "total_tokens": r["t"] or 0, "cost_usd": round(r["c"] or 0.0, 4)}
                for r in by_model
            ],
        }
