"""
数据迁移工具 (Phase D: D3A)

将旧的 JSON/JSONL 文件迁移到 SQLite 数据库。

用法:
    from zenskill.core.migrate_to_sqlite import migrate_all
    result = migrate_all(dry_run=True)   # 预览
    result = migrate_all()               # 执行
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .database import db
from .skill_dao import SkillDAO

logger = logging.getLogger(__name__)

USER_DIR = Path.home() / ".zenskill"


def migrate_all(dry_run: bool = False, archive: bool = False) -> Dict[str, Any]:
    """一键迁移全部旧数据

    Args:
        dry_run: True = 仅预览
        archive: True = 迁移后归档旧文件

    Returns:
        {"ok": bool, "summary": {...}, "errors": [...]}
    """
    results: Dict[str, Any] = {"ok": True, "summary": {}, "errors": []}

    migrations = [
        ("skills", _migrate_skills),
        ("ratings", _migrate_ratings),
        ("events", _migrate_events),
        ("gtd_energy", _migrate_gtd_energy),
        ("mirror_events", _migrate_mirror_events),
        ("mirror_features", _migrate_mirror_features),
        ("mirror_prefs", _migrate_mirror_prefs),
        ("sessions", _migrate_sessions),
    ]

    # 确保 Schema 已初始化
    if not dry_run:
        db.init_schema()
        # 迁移期间关闭外键检查（因为迁移顺序不确定）
        db.execute("PRAGMA foreign_keys = OFF")

    for name, func in migrations:
        try:
            count = func(dry_run=dry_run)
            results["summary"][name] = count
        except Exception as e:
            results["errors"].append(f"{name}: {e}")

    # 恢复外键检查
    if not dry_run:
        db.execute("PRAGMA foreign_keys = ON")

    # Archive
    if archive and not dry_run:
        _archive_old_files()

    # 总计数
    total = sum(v for v in results["summary"].values() if isinstance(v, int))
    results["summary"]["total"] = total

    return results


def _migrate_skills(dry_run: bool = False) -> int:
    """迁移 states/*.json → skill_registry + skill_cultivation"""
    states_dir = USER_DIR / "states"
    if not states_dir.exists():
        return 0

    count = 0
    for f in sorted(states_dir.glob("*.json")):
        if f.name.endswith(".history.jsonl") or f.name.endswith(".lock"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            skill_id = f.stem
            if dry_run:
                count += 1
                continue
            SkillDAO.upsert(
                skill_id,
                name=data.get("skill_name", skill_id),
                description=data.get("skill_name", ""),
                source="installed",
                is_active=1,
            )
            # Cultivation stats
            usage = data.get("usage_count", 0)
            if usage:
                level = data.get("level", "NOVICE")
                db.execute("""
                    INSERT INTO skill_cultivation (skill_id, level, total_interactions)
                    VALUES (?, ?, ?)
                    ON CONFLICT(skill_id) DO UPDATE SET
                        total_interactions = excluded.total_interactions,
                        level = excluded.level
                """, (skill_id, level, usage))
            count += 1
        except Exception as e:
            logger.warning("Failed to migrate state %s: %s", f.name, e)

    return count


def _migrate_ratings(dry_run: bool = False) -> int:
    """迁移 ratings/*.json → skill_ratings + user_ratings"""
    ratings_dir = USER_DIR / "ratings"
    if not ratings_dir.exists():
        return 0

    count = 0
    for f in sorted(ratings_dir.glob("*_rating.json")):
        if "user_ratings" in f.name:
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            skill_id = data.get("skill_id", f.stem.replace("_rating", ""))
            if dry_run:
                count += 1
                continue
            # 确保 skill 已注册
            if not SkillDAO.exists(skill_id):
                SkillDAO.upsert(skill_id, name=data.get("skill_name", skill_id),
                                source="migrated", is_active=1)
            # Main rating
            dims = data.get("dimensions", {})
            overall = data.get("overall", 0.0)
            star = data.get("star_level", "Experimental")
            icon = data.get("star_icon", "⭐")
            # Direct SQL to avoid parameter binding issues with update_rating_dimensions
            with db.connect() as conn:
                conn.execute("""
                    INSERT INTO skill_ratings (skill_id, overall, star_level, star_icon,
                        test_coverage, metadata_completeness, user_score, usage_score,
                        maintenance_score, security_audit)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(skill_id) DO UPDATE SET
                        overall = excluded.overall,
                        star_level = excluded.star_level,
                        star_icon = excluded.star_icon,
                        test_coverage = excluded.test_coverage,
                        metadata_completeness = excluded.metadata_completeness,
                        user_score = excluded.user_score,
                        usage_score = excluded.usage_score,
                        maintenance_score = excluded.maintenance_score,
                        security_audit = excluded.security_audit
                """, (skill_id, overall, star, icon,
                      dims.get("test_coverage", {}).get("score", 0.0),
                      dims.get("metadata_completeness", {}).get("score", 0.0),
                      dims.get("user_score", {}).get("score", 0.0),
                      dims.get("usage_score", {}).get("score", 0.0),
                      dims.get("maintenance_score", {}).get("score", 0.0),
                      dims.get("security_audit", {}).get("score", 1.0)))
            count += 1
        except Exception as e:
            logger.warning("Failed to migrate rating %s: %s", f.name, e)

    # User ratings
    for f in sorted(ratings_dir.glob("*_user_ratings.jsonl")):
        try:
            for line in f.read_text(encoding="utf-8").strip().split("\n"):
                if not line:
                    continue
                r = json.loads(line)
                if dry_run:
                    continue
                SkillDAO.rate(
                    r.get("skill_id", ""),
                    r.get("score", 0),
                    r.get("comment", ""),
                    r.get("user", "anonymous"),
                )
        except Exception as e:
            logger.warning("Failed to migrate user ratings %s: %s", f.name, e)

    return count


def _migrate_events(dry_run: bool = False) -> int:
    """迁移 events/*.json + mirroring/events.jsonl → skill_events"""
    count = 0
    events_dir = USER_DIR / "events"
    if events_dir.exists():
        for f in sorted(events_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
                if dry_run:
                    count += 1
                    continue
                sid = data.get("agent_id", "zenskill-core")
                # 先确保 skill 已注册
                if not SkillDAO.exists(sid):
                    SkillDAO.upsert(sid, name=sid, source="migrated", is_active=1)
                SkillDAO.record_event(
                    skill_id=sid,
                    action=data.get("event_type", "swarm"),
                    content=json.dumps(data.get("details", {}), ensure_ascii=False),
                    metadata={"source": data.get("source", ""),
                              "module": data.get("module", ""),
                              "growth_delta": data.get("growth_delta", {})},
                )
                count += 1
            except Exception as e:
                logger.warning("Failed to migrate event %s: %s", f.name, e)

    return count


def _migrate_gtd_energy(dry_run: bool = False) -> int:
    """迁移 gtd/energy.json → gtd_energy"""
    energy_file = USER_DIR / "gtd" / "energy.json"
    if not energy_file.exists():
        return 0
    try:
        data = json.loads(energy_file.read_text(encoding="utf-8"))
        if dry_run:
            return 1
        with db.connect() as conn:
            conn.execute("""
                INSERT INTO gtd_energy (skill_id, max_energy, current_energy, recovery_rate)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(skill_id) DO UPDATE SET
                    max_energy = excluded.max_energy,
                    current_energy = excluded.current_energy,
                    recovery_rate = excluded.recovery_rate
            """, (data.get("skill_id", "zenskill-core"),
                  data.get("max_energy", 100),
                  data.get("current_energy", 100),
                  data.get("recovery_rate", 10)))
            # Energy history
            for h in data.get("history", []):
                conn.execute("""
                    INSERT INTO gtd_energy_history (skill_id, change_type, amount, reason, recorded_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (data.get("skill_id", "zenskill-core"),
                      h.get("type", "burn"), h.get("amount", 0),
                      h.get("reason", ""), h.get("ts", "")))
        return 1
    except Exception as e:
        logger.warning("Failed to migrate energy: %s", e)
        return 0


def _migrate_mirror_events(dry_run: bool = False) -> int:
    """迁移 mirroring/events.jsonl → mirror_events"""
    f = USER_DIR / "mirroring" / "events.jsonl"
    if not f.exists():
        return 0
    count = 0
    for line in f.read_text(encoding="utf-8").strip().split("\n"):
        if not line:
            continue
        try:
            data = json.loads(line)
            if dry_run:
                count += 1
                continue
            with db.connect() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO mirror_events (event_id, skill_id, event_type, source, payload, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (data.get("event_id", ""),
                      data.get("skill_id", ""),
                      data.get("event_type", ""),
                      data.get("action", "zenskill"),
                      json.dumps(data, ensure_ascii=False),
                      data.get("timestamp", "")))
            count += 1
        except Exception:
            pass
    return count


def _migrate_mirror_features(dry_run: bool = False) -> int:
    """迁移 mirroring/pipeline.json → mirror_features"""
    f = USER_DIR / "mirroring" / "pipeline.json"
    if not f.exists():
        return 0
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if dry_run:
            return 1
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                with db.connect() as conn:
                    conn.execute("""
                        INSERT INTO mirror_features (skill_id, dimension, vector_data)
                        VALUES (?, ?, ?)
                    """, ("zenskill-core", key, json.dumps(value, ensure_ascii=False)))
        return 1
    except Exception:
        return 0


def _migrate_mirror_prefs(dry_run: bool = False) -> int:
    """迁移 mirroring/privacy_prefs.json → mirror_privacy + mirror_preferences"""
    f = USER_DIR / "mirroring" / "privacy_prefs.json"
    if not f.exists():
        return 0
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if dry_run:
            return 1
        with db.connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO mirror_privacy (skill_id, data_retention_days, auto_delete, anonymize, share_analytics)
                VALUES (?, ?, ?, ?, ?)
            """, ("zenskill-core",
                  data.get("data_retention_days", 90),
                  int(data.get("auto_delete", False)),
                  int(data.get("anonymize", False)),
                  int(data.get("share_analytics", True))))
        return 1
    except Exception:
        return 0


def _migrate_sessions(dry_run: bool = False) -> int:
    """迁移 session/*.json → sessions"""
    session_dir = USER_DIR / "session"
    if not session_dir.exists():
        return 0
    try:
        current_file = session_dir / "current.json"
        act_file = session_dir / "act_preferences.json"
        resp_file = session_dir / "act_response.json"
        dialogue_file = session_dir / "dialogue_history.json"

        current = json.loads(current_file.read_text(encoding="utf-8")) if current_file.exists() else {}
        prefs = json.loads(act_file.read_text(encoding="utf-8")) if act_file.exists() else {}
        resp = json.loads(resp_file.read_text(encoding="utf-8")) if resp_file.exists() else {}
        dialogue = json.loads(dialogue_file.read_text(encoding="utf-8")) if dialogue_file.exists() else []

        if dry_run:
            return 1

        sid = current.get("started", "") or "legacy-session"
        with db.connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO sessions (session_id, dialogue_history, act_preferences, act_response,
                    context_snapshot, message_count, tool_call_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (sid,
                  json.dumps(dialogue, ensure_ascii=False),
                  json.dumps(prefs, ensure_ascii=False),
                  json.dumps(resp, ensure_ascii=False),
                  json.dumps(current, ensure_ascii=False),
                  len(dialogue) if isinstance(dialogue, list) else 0,
                  current.get("tool_count", 0)))
        return 1
    except Exception as e:
        logger.warning("Failed to migrate sessions: %s", e)
        return 0


def _archive_old_files() -> None:
    """将已迁移的旧文件移到 archive/"""
    archive_dir = USER_DIR / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    import shutil

    for sub in ["states", "ratings", "events", "gtd", "mirroring", "session", "memory", "graph",
                "goals", "tasks", "insights", "metrics"]:
        src = USER_DIR / sub
        if src.exists() and src.is_dir():
            dst = archive_dir / sub
            try:
                shutil.move(str(src), str(dst))
                logger.info("Archived %s → %s", sub, dst)
            except Exception as e:
                logger.warning("Failed to archive %s: %s", sub, e)
