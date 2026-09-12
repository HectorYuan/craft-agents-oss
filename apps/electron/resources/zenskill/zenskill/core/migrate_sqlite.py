"""JSONL → SQLite 一次性迁移（Phase 3）。

幂等迁移：启动时将 JSONL 已有条目导入 SQLite（跳过已有 id）。
验证：JSONL 行数 vs SQLite COUNT 对比。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _resolve_gtd_dir(data_dir: Path | None = None) -> Path | None:
    """定位 gtd 数据目录。优先使用传入路径，否则走标准路径解析。"""
    if data_dir is not None:
        gtd = data_dir / "gtd" if data_dir.name != "gtd" else data_dir
        return gtd if gtd.is_dir() else None
    try:
        from .paths import get_user_data_dir
        return get_user_data_dir() / "gtd"
    except Exception:
        return None


def migrate_jsonl_to_sqlite(data_dir: Path | None = None) -> dict:
    """幂等迁移：JSONL 已有条目导入 SQLite（跳过已有 id）。

    Args:
        data_dir: workspace 数据目录（含 gtd/ 子目录），None 则自动解析。

    Returns:
        迁移摘要：{"actions": N, "inbox": N, "calendar": N, "errors": [...]}
    """
    from .database import db

    # 确保 schema 就绪（含 A2 字段 + 索引）
    db.init_schema()

    gtd_dir = _resolve_gtd_dir(data_dir)
    if gtd_dir is None:
        logger.info("migrate_jsonl_to_sqlite: gtd dir not found, skip")
        return {"actions": 0, "inbox": 0, "calendar": 0, "errors": []}

    summary = {"actions": 0, "inbox": 0, "calendar": 0, "errors": []}

    # --- actions.jsonl ---
    actions_file = gtd_dir / "actions.jsonl"
    if actions_file.exists():
        lines = _read_jsonl_lines(actions_file)
        for row in lines:
            try:
                _insert_action(db, row)
                summary["actions"] += 1
            except Exception as exc:
                summary["errors"].append(f"action {row.get('id', '?')}: {exc}")

    # --- inbox.jsonl ---
    inbox_file = gtd_dir / "inbox.jsonl"
    if inbox_file.exists():
        lines = _read_jsonl_lines(inbox_file)
        for row in lines:
            try:
                _insert_inbox(db, row)
                summary["inbox"] += 1
            except Exception as exc:
                summary["errors"].append(f"inbox {row.get('id', '?')}: {exc}")

    # --- calendar.jsonl ---
    calendar_file = gtd_dir / "calendar.jsonl"
    if calendar_file.exists():
        lines = _read_jsonl_lines(calendar_file)
        for row in lines:
            try:
                _insert_calendar(db, row)
                summary["calendar"] += 1
            except Exception as exc:
                summary["errors"].append(f"calendar {row.get('id', '?')}: {exc}")

    # --- 验证 ---
    _verify_counts(db, summary, actions_file, inbox_file, calendar_file)

    if summary["errors"]:
        logger.warning("migrate_jsonl_to_sqlite: %d errors", len(summary["errors"]))
    else:
        logger.info(
            "migrate_jsonl_to_sqlite done: actions=%d inbox=%d calendar=%d",
            summary["actions"], summary["inbox"], summary["calendar"],
        )
    return summary


def _read_jsonl_lines(path: Path) -> list[dict]:
    """读取 JSONL 文件，逐行解析，跳过空行、损坏行和非对象行。"""
    items = []
    for line in path.read_text(encoding="utf-8").strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        # 合法 JSON 但非对象（"str"/[1,2]/null）会让下游 row.get 抛
        # AttributeError 并中止整个迁移——在此一并过滤。
        if not isinstance(row, dict):
            continue
        items.append(row)
    return items


def _insert_action(db, row: dict) -> None:
    """INSERT OR IGNORE — 幂等，已有 id 跳过。"""
    with db.connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO gtd_actions
               (action_id, title, status, priority, energy_required,
                contexts, due_date, project_id, skill_id, repeat_rule,
                source_session_id, created_by, created_at, completed_at,
                energy_invested, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (row.get("id", ""),
             row.get("title", ""),
             row.get("status", "pending"),
             row.get("priority", "P2"),
             row.get("energy_required", 5),
             json.dumps(row.get("contexts", []), ensure_ascii=False),
             row.get("due_date", ""),
             row.get("project_id", ""),
             row.get("skill_id", ""),
             row.get("repeat_rule", ""),
             row.get("source_session_id", ""),
             row.get("created_by", "user"),
             row.get("created_at", ""),
             row.get("completed_at", ""),
             row.get("energy_invested", 0),
             row.get("created_at", ""))  # updated_at fallback = created_at
        )


def _insert_inbox(db, row: dict) -> None:
    """INSERT OR IGNORE — 幂等，已有 id 跳过。"""
    clarify_result = row.get("clarify_result", {})
    if not isinstance(clarify_result, dict):
        clarify_result = {}
    with db.connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO gtd_inbox
               (item_id, content, source, status, target_type, target_id,
                source_session_id, created_by, created_at, clarified_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (row.get("id", ""),
             row.get("raw_text", ""),
             row.get("source", ""),
             row.get("status", "unprocessed"),
             clarify_result.get("type", ""),
             clarify_result.get("target_id", ""),
             row.get("source_session_id", ""),
             row.get("created_by", "user"),
             row.get("created_at", ""),
             clarify_result.get("clarified_at", ""))
        )


def _insert_calendar(db, row: dict) -> None:
    """INSERT OR IGNORE — 幂等，已有 id 跳过。"""
    with db.connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO gtd_calendar
               (event_id, title, date, time_str, period,
                repeat_rule, status, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (row.get("id", ""),
             row.get("title", ""),
             row.get("date", ""),
             row.get("time_str", ""),
             row.get("period", ""),
             row.get("repeat_rule", ""),
             "scheduled",
             row.get("created_at", ""))
        )


def _verify_counts(db, summary: dict,
                   actions_file: Path, inbox_file: Path,
                   calendar_file: Path) -> None:
    """迁移后验证：JSONL 行数 vs SQLite COUNT。"""
    try:
        with db.connect() as conn:
            db_actions = conn.execute(
                "SELECT COUNT(*) FROM gtd_actions"
            ).fetchone()[0]
            db_inbox = conn.execute(
                "SELECT COUNT(*) FROM gtd_inbox"
            ).fetchone()[0]
            db_calendar = conn.execute(
                "SELECT COUNT(*) FROM gtd_calendar"
            ).fetchone()[0]

        jsonl_actions = len(_read_jsonl_lines(actions_file)) if actions_file.exists() else 0
        jsonl_inbox = len(_read_jsonl_lines(inbox_file)) if inbox_file.exists() else 0
        jsonl_calendar = len(_read_jsonl_lines(calendar_file)) if calendar_file.exists() else 0

        if db_actions != jsonl_actions:
            logger.warning(
                "actions count mismatch: jsonl=%d sqlite=%d",
                jsonl_actions, db_actions,
            )
        if db_inbox != jsonl_inbox:
            logger.warning(
                "inbox count mismatch: jsonl=%d sqlite=%d",
                jsonl_inbox, db_inbox,
            )
        if db_calendar != jsonl_calendar:
            logger.warning(
                "calendar count mismatch: jsonl=%d sqlite=%d",
                jsonl_calendar, db_calendar,
            )
    except Exception as exc:
        logger.warning("migrate verification failed: %s", exc)
