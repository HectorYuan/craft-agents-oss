"""
ZenSkill 统一数据库管理器 (Phase D: D1A)

SQLite WAL 模式 + 外键约束 + 连接池。
43 张表覆盖全部 14 个功能模块。

数据库文件: ~/.zenskill/zenskill.db

用法:
    from zenskill.core.database import db
    db.init_schema()
    with db.connect() as conn:
        conn.execute("SELECT ...")
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DB_FILENAME = "zenskill.db"


class DatabaseManager:
    """SQLite 数据库管理器 (Thread-safe)"""

    def __init__(self, db_path: Optional[Path] = None):
        env_path = os.environ.get("ZENSKILL_DB_PATH")
        self._db_path = (
            Path(db_path) if db_path
            else Path(env_path) if env_path
            else Path.home() / ".zenskill" / DB_FILENAME
        )
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._initialized = False
        self._initializing = False

    @property
    def path(self) -> Path:
        return self._db_path

    @contextmanager
    def connect(self):
        """获取数据库连接 (自动 commit/rollback，首次调用懒初始化 schema)"""
        if not self._initialized and not self._initializing:
            self.init_schema()
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, sql: str, params=()) -> List[Dict[str, Any]]:
        """执行查询并返回结果行列表（自动 commit；懒初始化由 connect() 统一负责）"""
        with self.connect() as conn:
            cursor = conn.execute(sql, params)
            # 如果是 SELECT，返回结果
            if sql.strip().upper().startswith("SELECT") or sql.strip().upper().startswith("PRAGMA"):
                return [dict(r) for r in cursor.fetchall()]
            # 否则返回空列表
            return []

    def executescript(self, sql: str) -> None:
        """执行多条 SQL"""
        with self.connect() as conn:
            conn.executescript(sql)

    def table_exists(self, name: str) -> bool:
        try:
            with self.connect() as conn:
                row = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
                ).fetchone()
                return row is not None
        except Exception:
            return False

    def init_schema(self) -> Dict[str, Any]:
        """首次运行时初始化全部 43 张表

        重入安全: connect() 懒初始化与直接调用可能嵌套（如本方法内
        table_exists → connect → init_schema），以 _initializing 护栏短路。
        """
        if self._initializing:
            return {"ok": True, "message": "Schema initialization in progress", "tables": 44}

        self._initializing = True
        try:
            with self._lock:
                already = self._initialized or self.table_exists("skill_registry")

                # SCHEMA_DDL 全部 CREATE ... IF NOT EXISTS，幂等：
                # 存量库也执行以补建后续版本新增的表（如 skill_version_history）
                self.executescript(SCHEMA_DDL)
                # 先置位再跑迁移: 迁移内部走 execute()，避免触发懒初始化递归
                self._initialized = True
                self._run_migrations()

                if already:
                    return {"ok": True, "message": "Schema already initialized", "tables": 44}
                logger.info("Database schema initialized at %s", self._db_path)
                return {"ok": True, "message": "Schema initialized", "tables": 44}
        finally:
            self._initializing = False

    def _run_migrations(self) -> None:
        """增量 Schema 迁移"""
        migrations = [
            ("ALTER TABLE skill_registry ADD COLUMN adapter TEXT DEFAULT ''",
             "adapter"),
            ("ALTER TABLE skill_registry ADD COLUMN entry_point TEXT DEFAULT ''",
             "entry_point"),
            ("ALTER TABLE skill_dependencies ADD COLUMN dep_version TEXT DEFAULT ''",
             "dep_version"),
        ]
        for sql, col_name in migrations:
            try:
                self.execute(sql)
                logger.info("Migration applied: add column %s", col_name)
            except Exception:
                pass  # 列已存在

    def get_stats(self) -> Dict[str, Any]:
        """数据库统计"""
        tables = []
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            for r in rows:
                name = str(r[0])
                # sqlite_master 来源可信，仍以标识符白名单硬校验防注入
                if not re.fullmatch(r"[A-Za-z0-9_]+", name):
                    continue
                cnt = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
                tables.append({"name": name, "rows": cnt})
        return {
            "path": str(self._db_path),
            "size_mb": round(self._db_path.stat().st_size / (1024 * 1024), 2)
            if self._db_path.exists() else 0,
            "tables": tables,
        }

    def vacuum(self) -> None:
        """压缩数据库"""
        self.execute("VACUUM")

    def backup(self, output: Optional[Path] = None) -> Path:
        """备份数据库"""
        import shutil
        dest = output or self._db_path.parent / "backups" / f"zenskill-{int(time.time())}.db"
        dest.parent.mkdir(parents=True, exist_ok=True)
        # 确保源数据库一致
        with self.connect() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        shutil.copy2(self._db_path, dest)
        logger.info("Database backed up to %s", dest)
        return dest


# 全局单例
db = DatabaseManager()


# ═══════════════════════════════════════════════════════════════
# 完整 Schema DDL (43 表)
# ═══════════════════════════════════════════════════════════════

SCHEMA_DDL = """
-- ═══ 表组 1: 技能核心 (8 表) ═══

CREATE TABLE IF NOT EXISTS skill_registry (
    skill_id        TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    display_name    TEXT DEFAULT '',
    description     TEXT DEFAULT '',
    icon            TEXT DEFAULT '📚',
    source          TEXT DEFAULT 'builtin',
    source_market   TEXT DEFAULT '',
    source_url      TEXT DEFAULT '',
    source_format   TEXT DEFAULT '',
    license         TEXT DEFAULT '',
    author          TEXT DEFAULT '',
    version         TEXT DEFAULT '0.1.0',
    category        TEXT DEFAULT 'general',
    difficulty      TEXT DEFAULT 'beginner',
    tags            TEXT DEFAULT '[]',
    install_method  TEXT DEFAULT '',
    content_hash    TEXT DEFAULT '',
    verified        INTEGER DEFAULT 0,
    is_active       INTEGER DEFAULT 1,
    adapter         TEXT DEFAULT '',
    entry_point     TEXT DEFAULT '',
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    installed_at    TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_skill_source ON skill_registry(source);
CREATE INDEX IF NOT EXISTS idx_skill_category ON skill_registry(category);
CREATE INDEX IF NOT EXISTS idx_skill_difficulty ON skill_registry(difficulty);

CREATE TABLE IF NOT EXISTS skill_cultivation (
    skill_id            TEXT PRIMARY KEY REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
    level               TEXT DEFAULT 'NOVICE',
    level_progress      REAL DEFAULT 0.0,
    total_interactions  INTEGER DEFAULT 0,
    success_count       INTEGER DEFAULT 0,
    fail_count          INTEGER DEFAULT 0,
    avg_duration_ms     REAL DEFAULT 0.0,
    last_interaction_at TEXT,
    updated_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS skill_abilities (
    skill_id            TEXT PRIMARY KEY REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
    proficiency         REAL DEFAULT 0.0,
    stability           REAL DEFAULT 0.0,
    satisfaction        REAL DEFAULT 0.0,
    responsiveness      REAL DEFAULT 0.0,
    memory              REAL DEFAULT 0.0,
    updated_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS skill_ratings (
    skill_id            TEXT PRIMARY KEY REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
    overall             REAL DEFAULT 0.0,
    star_level          TEXT DEFAULT 'Experimental',
    star_icon           TEXT DEFAULT '⭐',
    test_coverage       REAL DEFAULT 0.0,
    metadata_completeness REAL DEFAULT 0.0,
    user_score          REAL DEFAULT 0.0,
    usage_score         REAL DEFAULT 0.0,
    maintenance_score   REAL DEFAULT 0.0,
    security_audit      REAL DEFAULT 1.0,
    user_rating_count   INTEGER DEFAULT 0,
    user_rating_avg     REAL DEFAULT 0.0,
    updated_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_ratings (
    rating_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id            TEXT NOT NULL REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
    score               REAL NOT NULL CHECK(score >= 1 AND score <= 5),
    comment             TEXT DEFAULT '',
    user_name           TEXT DEFAULT 'anonymous',
    rated_at            TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_user_ratings_skill ON user_ratings(skill_id);

CREATE TABLE IF NOT EXISTS skill_dependencies (
    skill_id            TEXT NOT NULL REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
    dep_skill_id        TEXT NOT NULL REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
    dep_type            TEXT DEFAULT 'prerequisite',
    dep_version         TEXT DEFAULT '',
    strength            REAL DEFAULT 0.5,
    created_at          TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (skill_id, dep_skill_id)
);
CREATE INDEX IF NOT EXISTS idx_skill_deps_skill ON skill_dependencies(skill_id);

CREATE TABLE IF NOT EXISTS skill_version_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id            TEXT NOT NULL REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
    version             TEXT NOT NULL,
    source_url          TEXT DEFAULT '',
    content_hash        TEXT DEFAULT '',
    recorded_at         TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_version_history_skill ON skill_version_history(skill_id);

CREATE TABLE IF NOT EXISTS skill_milestones (
    milestone_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id            TEXT NOT NULL REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
    level               TEXT NOT NULL,
    achieved_at         TEXT NOT NULL,
    description         TEXT DEFAULT '',
    unlocked_abilities  TEXT DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_milestones_skill ON skill_milestones(skill_id);

-- FTS5 全文搜索
CREATE VIRTUAL TABLE IF NOT EXISTS skill_fts USING fts5(
    skill_id, name, display_name, description, tags, category,
    content='skill_registry', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS skill_fts_insert AFTER INSERT ON skill_registry BEGIN
    INSERT INTO skill_fts(rowid, skill_id, name, display_name, description, tags, category)
    VALUES (new.rowid, new.skill_id, new.name, new.display_name, new.description, new.tags, new.category);
END;

CREATE TRIGGER IF NOT EXISTS skill_fts_delete AFTER DELETE ON skill_registry BEGIN
    INSERT INTO skill_fts(skill_fts, rowid, skill_id, name, display_name, description, tags, category)
    VALUES ('delete', old.rowid, old.skill_id, old.name, old.display_name, old.description, old.tags, old.category);
END;

CREATE TRIGGER IF NOT EXISTS skill_fts_update AFTER UPDATE ON skill_registry BEGIN
    INSERT INTO skill_fts(skill_fts, rowid, skill_id, name, display_name, description, tags, category)
    VALUES ('delete', old.rowid, old.skill_id, old.name, old.display_name, old.description, old.tags, old.category);
    INSERT INTO skill_fts(rowid, skill_id, name, display_name, description, tags, category)
    VALUES (new.rowid, new.skill_id, new.name, new.display_name, new.description, new.tags, new.category);
END;

-- ═══ 表组 2: 事件/目标 (5 表) ═══

CREATE TABLE IF NOT EXISTS skill_events (
    event_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id            TEXT NOT NULL REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
    action              TEXT NOT NULL,
    content             TEXT DEFAULT '',
    tags                TEXT DEFAULT '',
    success             INTEGER DEFAULT 1,
    duration_ms         REAL DEFAULT 0.0,
    metadata            TEXT DEFAULT '{}',
    created_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_skill ON skill_events(skill_id);
CREATE INDEX IF NOT EXISTS idx_events_created ON skill_events(created_at);

CREATE TABLE IF NOT EXISTS skill_insights (
    insight_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id            TEXT NOT NULL REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
    type                TEXT DEFAULT 'info',
    title               TEXT DEFAULT '',
    description         TEXT DEFAULT '',
    priority            TEXT DEFAULT 'medium',
    is_read             INTEGER DEFAULT 0,
    created_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_insights_skill ON skill_insights(skill_id, is_read);

CREATE TABLE IF NOT EXISTS skill_goals (
    goal_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id            TEXT NOT NULL REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
    dimension           TEXT NOT NULL,
    target              REAL NOT NULL,
    current             REAL DEFAULT 0.0,
    status              TEXT DEFAULT 'active',
    created_at          TEXT DEFAULT (datetime('now')),
    completed_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_goals_skill ON skill_goals(skill_id);

CREATE TABLE IF NOT EXISTS skill_metrics (
    metric_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id            TEXT NOT NULL REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
    metric_type         TEXT NOT NULL,
    metric_data         TEXT NOT NULL,
    sampled_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_metrics_skill ON skill_metrics(skill_id, metric_type);
CREATE INDEX IF NOT EXISTS idx_metrics_time ON skill_metrics(sampled_at);

CREATE TABLE IF NOT EXISTS skill_tasks (
    task_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id            TEXT NOT NULL REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
    title               TEXT NOT NULL,
    description         TEXT DEFAULT '',
    difficulty          TEXT DEFAULT 'easy',
    status              TEXT DEFAULT 'pending',
    rating              REAL DEFAULT 0.0,
    created_at          TEXT DEFAULT (datetime('now')),
    completed_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_skill ON skill_tasks(skill_id);

-- ═══ 表组 3: GTD 生产力 (8 表) ═══

CREATE TABLE IF NOT EXISTS gtd_actions (
    action_id       TEXT PRIMARY KEY,
    skill_id        TEXT REFERENCES skill_registry(skill_id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    status          TEXT DEFAULT 'pending',
    priority        TEXT DEFAULT 'medium',
    energy_required INTEGER DEFAULT 3,
    contexts        TEXT DEFAULT '[]',
    due_date        TEXT,
    repeat_rule     TEXT,
    project_id      TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    completed_at    TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_actions_status ON gtd_actions(status);
CREATE INDEX IF NOT EXISTS idx_actions_project ON gtd_actions(project_id);

CREATE TABLE IF NOT EXISTS gtd_projects (
    project_id      TEXT PRIMARY KEY,
    skill_id        TEXT REFERENCES skill_registry(skill_id) ON DELETE SET NULL,
    name            TEXT NOT NULL,
    outcome         TEXT DEFAULT '',
    status          TEXT DEFAULT 'active',
    notes           TEXT DEFAULT '',
    next_action_id  TEXT,
    review_date     TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    completed_at    TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gtd_calendar (
    event_id        TEXT PRIMARY KEY,
    skill_id        TEXT REFERENCES skill_registry(skill_id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    date            TEXT NOT NULL,
    time_str        TEXT,
    period          TEXT DEFAULT 'morning',
    repeat_rule     TEXT,
    status          TEXT DEFAULT 'scheduled',
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_calendar_date ON gtd_calendar(date);

CREATE TABLE IF NOT EXISTS gtd_energy (
    skill_id        TEXT PRIMARY KEY REFERENCES skill_registry(skill_id),
    current_energy  REAL DEFAULT 100.0,
    max_energy      REAL DEFAULT 100.0,
    recovery_rate   REAL DEFAULT 10.0,
    last_burn_at    TEXT,
    last_recover_at TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gtd_energy_history (
    record_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id        TEXT REFERENCES skill_registry(skill_id),
    change_type     TEXT NOT NULL,
    amount          REAL NOT NULL,
    reason          TEXT DEFAULT '',
    recorded_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gtd_inbox (
    item_id         TEXT PRIMARY KEY,
    skill_id        TEXT REFERENCES skill_registry(skill_id) ON DELETE SET NULL,
    content         TEXT NOT NULL,
    source          TEXT DEFAULT '',
    status          TEXT DEFAULT 'unprocessed',
    target_type     TEXT,
    target_id       TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    clarified_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_inbox_status ON gtd_inbox(status);

CREATE TABLE IF NOT EXISTS gtd_incubating (
    item_id         TEXT PRIMARY KEY,
    skill_id        TEXT REFERENCES skill_registry(skill_id) ON DELETE SET NULL,
    concept         TEXT NOT NULL,
    notes           TEXT DEFAULT '',
    status          TEXT DEFAULT 'incubating',
    promoted_to     TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    promoted_at     TEXT
);

CREATE TABLE IF NOT EXISTS gtd_health_snapshots (
    snapshot_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id        TEXT REFERENCES skill_registry(skill_id),
    capture_rate    REAL DEFAULT 0.0,
    completion_rate REAL DEFAULT 0.0,
    cleanup_rate    REAL DEFAULT 0.0,
    energy_efficiency REAL DEFAULT 0.0,
    review_frequency  REAL DEFAULT 0.0,
    overall_score   REAL DEFAULT 0.0,
    grade           TEXT DEFAULT 'C',
    period          TEXT DEFAULT 'weekly',
    period_start    TEXT NOT NULL,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- ═══ 表组 4: Memory 记忆 (4 表) ═══

CREATE TABLE IF NOT EXISTS episodic_memory (
    memory_id       TEXT PRIMARY KEY,
    skill_id        TEXT REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    action          TEXT DEFAULT 'general',
    importance      REAL DEFAULT 0.5,
    tags            TEXT DEFAULT '',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_episodic_skill ON episodic_memory(skill_id);

CREATE TABLE IF NOT EXISTS semantic_memory (
    fact_id         TEXT PRIMARY KEY,
    skill_id        TEXT REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
    object_name     TEXT NOT NULL,
    predicate       TEXT NOT NULL,
    value           TEXT DEFAULT '',
    confidence      REAL DEFAULT 0.5,
    source          TEXT DEFAULT '',
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_semantic_skill ON semantic_memory(skill_id);

CREATE TABLE IF NOT EXISTS working_memory (
    item_id         TEXT PRIMARY KEY,
    skill_id        TEXT REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    ttl_seconds     INTEGER DEFAULT 3600,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cross_sessions (
    session_id      TEXT PRIMARY KEY,
    skill_id        TEXT REFERENCES skill_registry(skill_id),
    summary         TEXT DEFAULT '',
    intent_labels   TEXT DEFAULT '[]',
    keywords        TEXT DEFAULT '[]',
    tool_usage      TEXT DEFAULT '{}',
    duration_sec    REAL DEFAULT 0.0,
    message_count   INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS session_links (
    link_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_a       TEXT NOT NULL REFERENCES cross_sessions(session_id),
    session_b       TEXT NOT NULL REFERENCES cross_sessions(session_id),
    link_type       TEXT DEFAULT 'related',
    strength        REAL DEFAULT 0.5
);

-- ═══ 表组 5: ZenLoop 禅思 (2 表) ═══

CREATE TABLE IF NOT EXISTS zenloop_reflections (
    reflection_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id        TEXT REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
    loop_type       TEXT NOT NULL,
    content         TEXT NOT NULL,
    quality_score   REAL DEFAULT 0.5,
    actionable_count INTEGER DEFAULT 0,
    pattern_accuracy REAL DEFAULT 0.0,
    insight_depth   REAL DEFAULT 0.0,
    clarity         REAL DEFAULT 0.0,
    adoption_rate   REAL DEFAULT 0.0,
    relevance       REAL DEFAULT 0.0,
    suggestions     TEXT DEFAULT '[]',
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_zenloop_skill ON zenloop_reflections(skill_id);

CREATE TABLE IF NOT EXISTS zenloop_triggers (
    trigger_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id        TEXT REFERENCES skill_registry(skill_id),
    loop_type       TEXT NOT NULL,
    trigger_reason  TEXT DEFAULT '',
    memory_count    INTEGER DEFAULT 0,
    triggered_at    TEXT DEFAULT (datetime('now'))
);

-- ═══ 表组 6: Active 主动成长 (4 表) ═══

CREATE TABLE IF NOT EXISTS active_habits (
    habit_id        TEXT PRIMARY KEY,
    skill_id        TEXT REFERENCES skill_registry(skill_id),
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    frequency       TEXT DEFAULT 'daily',
    target_count    INTEGER DEFAULT 1,
    current_streak  INTEGER DEFAULT 0,
    best_streak     INTEGER DEFAULT 0,
    total_completions INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS habit_logs (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_id        TEXT REFERENCES active_habits(habit_id) ON DELETE CASCADE,
    completed       INTEGER DEFAULT 1,
    note            TEXT DEFAULT '',
    logged_at       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_habit_logs_date ON habit_logs(logged_at);

CREATE TABLE IF NOT EXISTS active_achievements (
    achievement_id  TEXT PRIMARY KEY,
    skill_id        TEXT REFERENCES skill_registry(skill_id),
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    icon            TEXT DEFAULT '🏆',
    unlocked        INTEGER DEFAULT 0,
    unlocked_at     TEXT,
    progress        REAL DEFAULT 0.0,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS active_meta_reflections (
    reflection_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id        TEXT REFERENCES skill_registry(skill_id),
    actionable_count  INTEGER DEFAULT 0,
    pattern_accuracy  REAL DEFAULT 0.0,
    insight_depth     REAL DEFAULT 0.0,
    clarity           REAL DEFAULT 0.0,
    adoption_rate     REAL DEFAULT 0.0,
    relevance         REAL DEFAULT 0.0,
    biases            TEXT DEFAULT '[]',
    suggestions       TEXT DEFAULT '[]',
    created_at        TEXT DEFAULT (datetime('now'))
);

-- ═══ 表组 7: Collaboration 协作 (2 表) ═══

CREATE TABLE IF NOT EXISTS graph_skill_nodes (
    node_id         TEXT PRIMARY KEY,
    skill_id        TEXT NOT NULL REFERENCES skill_registry(skill_id),
    node_name       TEXT NOT NULL,
    category        TEXT DEFAULT 'general',
    level           TEXT DEFAULT 'NOVICE',
    ability_scores  TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS graph_relationships (
    rel_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL REFERENCES graph_skill_nodes(node_id),
    target_id       TEXT NOT NULL REFERENCES graph_skill_nodes(node_id),
    rel_type        TEXT DEFAULT 'complementary',
    strength        REAL DEFAULT 0.5,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_graph_source ON graph_relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_graph_target ON graph_relationships(target_id);

-- ═══ 表组 8: Mirroring 镜像 (5 表) ═══

CREATE TABLE IF NOT EXISTS mirror_events (
    event_id        TEXT PRIMARY KEY,
    skill_id        TEXT REFERENCES skill_registry(skill_id),
    event_type      TEXT NOT NULL,
    source          TEXT DEFAULT 'zenskill',
    payload         TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_mirror_events_type ON mirror_events(event_type);
CREATE INDEX IF NOT EXISTS idx_mirror_events_time ON mirror_events(created_at);

CREATE TABLE IF NOT EXISTS mirror_features (
    feature_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id        TEXT REFERENCES skill_registry(skill_id),
    dimension       TEXT NOT NULL,
    vector_data     TEXT NOT NULL,
    sampled_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_mirror_features_dim ON mirror_features(dimension);

CREATE TABLE IF NOT EXISTS mirror_preferences (
    pref_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id        TEXT REFERENCES skill_registry(skill_id),
    pref_key        TEXT NOT NULL,
    pref_value      TEXT NOT NULL,
    confidence      REAL DEFAULT 0.5,
    source          TEXT DEFAULT 'inferred',
    updated_at      TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pref_key ON mirror_preferences(skill_id, pref_key);

CREATE TABLE IF NOT EXISTS mirror_privacy (
    skill_id        TEXT PRIMARY KEY REFERENCES skill_registry(skill_id),
    data_retention_days INTEGER DEFAULT 90,
    auto_delete      INTEGER DEFAULT 0,
    anonymize        INTEGER DEFAULT 0,
    share_analytics  INTEGER DEFAULT 1,
    allowed_sources  TEXT DEFAULT '[]',
    updated_at       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mirror_patterns (
    pattern_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id        TEXT REFERENCES skill_registry(skill_id),
    pattern_name    TEXT NOT NULL,
    pattern_type    TEXT DEFAULT 'workflow',
    confidence      REAL DEFAULT 0.5,
    details         TEXT DEFAULT '{}',
    detected_at     TEXT DEFAULT (datetime('now'))
);

-- ═══ 表组 9: Agent 代理 (5 表) ═══

CREATE TABLE IF NOT EXISTS agent_memory (
    entry_id        TEXT PRIMARY KEY,
    skill_id        TEXT REFERENCES skill_registry(skill_id),
    content         TEXT NOT NULL,
    memory_type     TEXT DEFAULT 'shared',
    created_by      TEXT DEFAULT 'system',
    visibility      TEXT DEFAULT 'all',
    ttl_seconds     INTEGER,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_agent_memory_type ON agent_memory(memory_type);

CREATE TABLE IF NOT EXISTS agent_performance (
    record_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_role      TEXT NOT NULL,
    skill_id        TEXT REFERENCES skill_registry(skill_id),
    task_id         TEXT NOT NULL,
    success         INTEGER DEFAULT 1,
    duration_ms     REAL DEFAULT 0.0,
    quality_score   REAL DEFAULT 0.5,
    feedback        TEXT DEFAULT '',
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_agent_perf_role ON agent_performance(agent_role);

CREATE TABLE IF NOT EXISTS agent_ab_tests (
    test_id         TEXT PRIMARY KEY,
    skill_id        TEXT REFERENCES skill_registry(skill_id),
    variant_a       TEXT NOT NULL,
    variant_b       TEXT NOT NULL,
    metric          TEXT NOT NULL,
    a_score         REAL DEFAULT 0.0,
    b_score         REAL DEFAULT 0.0,
    winner          TEXT,
    confidence      REAL DEFAULT 0.0,
    sample_size     INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_decompositions (
    decomp_id       TEXT PRIMARY KEY,
    skill_id        TEXT REFERENCES skill_registry(skill_id),
    task            TEXT NOT NULL,
    complexity      TEXT DEFAULT 'simple',
    strategy        TEXT DEFAULT 'sequential',
    steps           TEXT NOT NULL,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_workflows (
    workflow_id     TEXT PRIMARY KEY,
    skill_id        TEXT REFERENCES skill_registry(skill_id),
    workflow_name   TEXT NOT NULL,
    status          TEXT DEFAULT 'pending',
    steps_total     INTEGER DEFAULT 0,
    steps_completed INTEGER DEFAULT 0,
    started_at      TEXT,
    completed_at    TEXT,
    result          TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (datetime('now'))
);

-- ═══ 表组 10: Session 会话 (1 表) ═══

CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,
    profile_name    TEXT DEFAULT 'default',
    dialogue_history TEXT DEFAULT '[]',
    act_preferences  TEXT DEFAULT '{}',
    act_response     TEXT DEFAULT '{}',
    context_snapshot TEXT DEFAULT '{}',
    started_at      TEXT DEFAULT (datetime('now')),
    ended_at        TEXT,
    message_count   INTEGER DEFAULT 0,
    tool_call_count INTEGER DEFAULT 0
);
"""

# ═══════════════════════════════════════════════════════════════
# 表名快捷访问
# ═══════════════════════════════════════════════════════════════

ALL_TABLES = [
    # 技能核心
    "skill_registry", "skill_cultivation", "skill_abilities", "skill_ratings",
    "user_ratings", "skill_dependencies", "skill_milestones", "skill_fts",
    # 事件/目标
    "skill_events", "skill_insights", "skill_goals", "skill_metrics", "skill_tasks",
    # GTD
    "gtd_actions", "gtd_projects", "gtd_calendar", "gtd_energy",
    "gtd_energy_history", "gtd_inbox", "gtd_incubating", "gtd_health_snapshots",
    # Memory
    "episodic_memory", "semantic_memory", "working_memory",
    "cross_sessions", "session_links",
    # ZenLoop
    "zenloop_reflections", "zenloop_triggers",
    # Active
    "active_habits", "habit_logs", "active_achievements", "active_meta_reflections",
    # Collaboration
    "graph_skill_nodes", "graph_relationships",
    # Mirroring
    "mirror_events", "mirror_features", "mirror_preferences",
    "mirror_privacy", "mirror_patterns",
    # Agent
    "agent_memory", "agent_performance", "agent_ab_tests",
    "agent_decompositions", "agent_workflows",
    # Session
    "sessions",
]
