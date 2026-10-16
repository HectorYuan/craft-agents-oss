"""技能治理数据层（G1，docs/skill_governance_plan.md §5.1；G2 §4.1/4.2 状态机+Tier）。

双源真相裁决：skill_governance 是治理状态唯一 master；
skill_registry.is_active 降为派生列（set_state 写入时同步维护，
保持旧消费方兼容）。治理状态属用户本地数据，不污染技能包 frontmatter。

G2 扩展：
- 状态机迁移校验（宽松手动迁移；deleted 仅从 archived 可达且需 30 天恢复窗口外或 force）
- Tier 分级（set_tier / recompute_tiers，pinned 恒 T0，T1→T2 滞回带）
- record_use 唤醒评估（dormant 30 天内 ≥2 次使用自动唤醒，1 次给 wake_hint）
- MCP 工具契约纯函数（mcp_skill_state / mcp_set_tier，JSON 可序列化）
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from zenskill.core.database import DatabaseManager

logger = logging.getLogger(__name__)

VALID_STATES = ("active", "dormant", "archived", "deleted")
VALID_TIERS = ("T0", "T1", "T2")
ARCHIVE_GRACE_DAYS = 30   # deleted 前的恢复窗口
WAKE_USES_30D = 2         # dormant 自动唤醒阈值（30 天内使用次数）
TIER_ACTIVE_DAYS = 30     # T1 活跃窗口
TIER_HYSTERESIS_DAYS = 37 # T1→T2 滞回带（30+7 天无使用才降级）

GOVERNANCE_DDL = """
CREATE TABLE IF NOT EXISTS skill_governance (
  slug TEXT PRIMARY KEY,
  state TEXT DEFAULT 'active',
  tier TEXT DEFAULT 'T2',
  pinned INTEGER DEFAULT 0,
  quality_score INTEGER DEFAULT -1,
  dormant_reason TEXT DEFAULT '',
  last_used_at TEXT DEFAULT '',
  last_reviewed_at TEXT DEFAULT '',
  archived_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_governance_state ON skill_governance(state);
"""

_GOV_UPSERT = """
INSERT INTO skill_governance (slug, state, dormant_reason, archived_at)
VALUES (?, ?, ?, ?)
ON CONFLICT(slug) DO UPDATE SET
  state = excluded.state,
  dormant_reason = excluded.dormant_reason,
  archived_at = excluded.archived_at
"""


class InvalidTransition(ValueError):
    """非法治理状态迁移（结构化错误：slug/from_state/to_state/reason）。"""

    def __init__(self, slug: str, from_state: str, to_state: str, reason: str):
        self.slug = slug
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        super().__init__(
            f"invalid transition {slug}: {from_state} -> {to_state} ({reason})"
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            "error": "invalid_transition",
            "slug": self.slug,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
        }

# SQLite 单语句绑定变量上限保守分块（老版本默认 999）
_CHUNK = 400


def _default_db():
    from zenskill.core.database import db
    return db


def _resolve(db) -> "DatabaseManager":
    return db if db is not None else _default_db()


def ensure_table(db=None) -> None:
    """幂等建表 skill_governance（不进 core SCHEMA_DDL，独立演进）。

    G1 旧表缺 archived_at 列时补列（SQLite ADD COLUMN 无 IF NOT EXISTS，
    以 PRAGMA table_info 判定）。
    """
    d = _resolve(db)
    with d.connect() as conn:
        conn.executescript(GOVERNANCE_DDL)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(skill_governance)")}
        if "archived_at" not in cols:
            conn.execute(
                "ALTER TABLE skill_governance ADD COLUMN archived_at TEXT DEFAULT ''"
            )


def get_states(slugs: List[str] | Set[str], db=None) -> Dict[str, str]:
    """批量查询治理状态；未登记或表缺失的 slug 一律按 'active'。"""
    wanted = list(slugs)
    result: Dict[str, str] = {s: "active" for s in wanted}
    if not wanted:
        return result
    d = _resolve(db)
    try:
        with d.connect() as conn:
            for i in range(0, len(wanted), _CHUNK):
                chunk = wanted[i:i + _CHUNK]
                ph = ",".join("?" * len(chunk))
                rows = conn.execute(
                    f"SELECT slug, state FROM skill_governance WHERE slug IN ({ph})",
                    tuple(chunk),
                ).fetchall()
                for r in rows:
                    result[r["slug"]] = r["state"]
    except Exception:
        # 表未建/库不可达 → 未登记语义（active）；降级链在 governance_filter
        pass
    return result


def set_state(slug: str, state: str, reason: str = "", db=None,
              force: bool = False) -> Dict[str, Any]:
    """状态机迁移（宽松策略）+ 派生列同步，返回迁移结果 dict。

    规则（docs/skill_governance_plan.md §4.1）：
    - 任意手动迁移合法（active→dormant/archived、dormant→archived、
      archived→active(restore) 等均可直达）；
    - 唯一硬约束：deleted 仅从 archived 可达，且需 archived_at 距今
      ≥ ARCHIVE_GRACE_DAYS（30 天恢复窗口已过）或 force=True；
      违反抛 InvalidTransition（结构化错误）；
    - 进入 archived 时记录 archived_at，离开时清空；
    - state=='active' → skill_registry.is_active=1，否则 0；
      skill_registry 无记录时跳过同步（governance 仍写入）；
    - 不触碰 tier/pinned（pinned 技能的 T0 不因状态操作被降级）。
    """
    if state not in VALID_STATES:
        raise ValueError(
            f"invalid governance state: {state!r}, expected one of {VALID_STATES}"
        )
    d = _resolve(db)
    ensure_table(d)
    with d.connect() as conn:
        row = conn.execute(
            "SELECT state, "
            "CAST(julianday('now') - julianday(NULLIF(archived_at, '')) AS INTEGER) "
            "AS days_archived "
            "FROM skill_governance WHERE slug = ?",
            (slug,),
        ).fetchone()
        from_state = str(row["state"]) if row is not None else "unregistered"
        days_archived = row["days_archived"] if row is not None else None

        if state == "deleted":
            if from_state != "archived":
                raise InvalidTransition(
                    slug, from_state, state,
                    "deleted is only reachable from archived",
                )
            if days_archived is None:
                if not force:
                    raise InvalidTransition(
                        slug, from_state, state, "archive time unknown; use force",
                    )
            elif days_archived < ARCHIVE_GRACE_DAYS and not force:
                raise InvalidTransition(
                    slug, from_state, state,
                    f"restore window {ARCHIVE_GRACE_DAYS}d not elapsed "
                    f"(archived {days_archived}d ago); use force to override",
                )

        if state == "archived":
            archived_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        else:
            archived_at = ""
        conn.execute(_GOV_UPSERT, (slug, state, reason, archived_at))
        conn.execute(
            "UPDATE skill_registry SET is_active = ?, updated_at = datetime('now') "
            "WHERE skill_id = ?",
            (1 if state == "active" else 0, slug),
        )
    return {
        "ok": True,
        "slug": slug,
        "from": from_state,
        "state": state,
        "changed": from_state != state,
        "forced": force and state == "deleted",
    }


def _disk_slugs(skills_root: Path) -> Set[str]:
    """磁盘技能 slug 集合（~/.agents/skills 下一级目录，排除隐藏目录）。"""
    if not skills_root.is_dir():
        return set()
    return {
        p.name for p in skills_root.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    }


def _read_registry_sets(conn) -> Tuple[Set[str], Set[str]]:
    active = {
        r["skill_id"] for r in
        conn.execute("SELECT skill_id FROM skill_registry WHERE is_active = 1")
    }
    inactive = {
        r["skill_id"] for r in
        conn.execute("SELECT skill_id FROM skill_registry WHERE is_active = 0")
    }
    return active, inactive


def reconcile(apply: bool = False, db=None,
              skills_root: Optional[Path] = None) -> Dict[str, object]:
    """对账 skill_registry ↔ 磁盘 ↔ governance（幂等）。

    - ghost_archive: registry is_active=0 且磁盘无目录 → governance 标 archived
      （registry 行保留历史，不删除）；
    - register_missing: 磁盘有目录但 registry 无 active 记录 → upsert active
      （重装场景同时把 governance 非 active 状态复位为 active）。

    apply=False 为完全只读 dry-run（不建表、不写入），返回计划与执行统计。
    """
    d = _resolve(db)
    root = Path(skills_root) if skills_root else Path.home() / ".agents" / "skills"

    with d.connect() as conn:
        active, inactive = _read_registry_sets(conn)
    disk = _disk_slugs(root)

    ghost = sorted(inactive - disk)
    missing = sorted(disk - active)

    plan = {"ghost_archive": ghost, "register_missing": missing}
    executed = {"ghost_archive": 0, "register_missing": 0}
    result: Dict[str, object] = {
        "apply": apply,
        "db": str(d.path),
        "skills_root": str(root),
        "plan": plan,
        "executed": executed,
    }
    if not apply:
        return result

    ensure_table(d)
    from .frontmatter import parse_skill_md

    with d.connect() as conn:
        gov_states = {
            r["slug"]: r["state"]
            for r in conn.execute("SELECT slug, state FROM skill_governance")
        }

        for slug in ghost:
            if gov_states.get(slug) == "archived":
                continue
            conn.execute(
                _GOV_UPSERT,
                (slug, "archived", "reconcile: directory removed from disk",
                 datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")),
            )
            gov_states[slug] = "archived"
            executed["ghost_archive"] += 1

        for slug in missing:
            skill_md = root / slug / "SKILL.md"
            name, desc = slug, ""
            if skill_md.exists():
                try:
                    meta, _ = parse_skill_md(skill_md)
                    name = meta.name or slug
                    desc = (meta.description or "").strip()
                except Exception:
                    pass
            row = conn.execute(
                "SELECT skill_id FROM skill_registry WHERE skill_id = ?", (slug,)
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO skill_registry (skill_id, name, description, source, is_active) "
                    "VALUES (?, ?, ?, 'installed', 1)",
                    (slug, name, desc),
                )
                executed["register_missing"] += 1
            else:
                cur = conn.execute(
                    "UPDATE skill_registry SET is_active = 1, "
                    "updated_at = datetime('now') "
                    "WHERE skill_id = ? AND is_active = 0",
                    (slug,),
                )
                if cur.rowcount:
                    executed["register_missing"] += 1
            # 重装场景：archived/deleted 残留状态复位 active（§5.1 promote 复用）
            if gov_states.get(slug) not in (None, "active"):
                conn.execute(_GOV_UPSERT, (slug, "active", "", ""))
                gov_states[slug] = "active"

    return result


# ═══════════════════════════════════════════════════════════════════
# G2 §4.2: Tier 分级
# ═══════════════════════════════════════════════════════════════════

def get_governance(slug: str, db=None) -> Optional[Dict[str, Any]]:
    """查询单个 slug 的治理行；未登记/表缺失返回 None。"""
    d = _resolve(db)
    try:
        with d.connect() as conn:
            row = conn.execute(
                "SELECT * FROM skill_governance WHERE slug = ?", (slug,)
            ).fetchone()
        return dict(row) if row is not None else None
    except Exception:
        return None


def set_tier(slug: str, tier: str, db=None) -> Dict[str, Any]:
    """设置 Tier：T0 同时置 pinned=1，T1/T2 清 pinned（§4.2 pinned 恒 T0）。

    未登记 slug 会补登记（state 默认 active）。返回结果 dict。
    """
    if tier not in VALID_TIERS:
        raise ValueError(
            f"invalid tier: {tier!r}, expected one of {VALID_TIERS}"
        )
    d = _resolve(db)
    ensure_table(d)
    pinned = 1 if tier == "T0" else 0
    with d.connect() as conn:
        conn.execute(
            "INSERT INTO skill_governance (slug, tier, pinned) VALUES (?, ?, ?) "
            "ON CONFLICT(slug) DO UPDATE SET "
            "tier = excluded.tier, pinned = excluded.pinned",
            (slug, tier, pinned),
        )
    return {"ok": True, "slug": slug, "tier": tier, "pinned": bool(pinned)}


def _tier_use_sets(conn) -> Tuple[Set[str], Set[str], Dict[str, float]]:
    """recompute 输入：(30 天内活跃 slug 集, 37 天滞回集, proficiency>=0.7 映射)。"""
    recent = {
        r["skill_id"] for r in conn.execute(
            "SELECT DISTINCT skill_id FROM skill_events "
            "WHERE created_at >= datetime('now', ?)", ("-30 days",)
        )
    }
    stale = {
        r["skill_id"] for r in conn.execute(
            "SELECT DISTINCT skill_id FROM skill_events "
            "WHERE created_at >= datetime('now', ?)", ("-37 days",)
        )
    }
    proficient = {
        r["skill_id"]: float(r["proficiency"])
        for r in conn.execute(
            "SELECT skill_id, proficiency FROM skill_abilities WHERE proficiency >= ?",
            (0.7,),
        )
    }
    return recent, stale, proficient


def recompute_tiers(db=None) -> Dict[str, int]:
    """全员 Tier 重算（§4.2，只处理 state=active 行，非 active tier 原样保留）。

    - T0: pinned=1 或 skill_abilities.proficiency >= 0.7
    - T1: 近 30 天有使用（skill_events 或 last_used_at）
    - T2: 其余；滞回带——当前 T1 且近 37 天仍有使用痕迹则保留 T1，
      连续 7 天（37 天窗口）无使用才降 T2，30 天内活跃升 T1 即刻。

    返回 {"T0": n, "T1": n, "T2": n, "changed": n}。
    """
    d = _resolve(db)
    ensure_table(d)
    stats = {"T0": 0, "T1": 0, "T2": 0, "changed": 0}
    with d.connect() as conn:
        # 磁盘技能全量补录（G1 对账只登记了幽灵/新装，active 磁盘技能可能无行）
        from pathlib import Path as _P
        skills_root = _P.home() / ".agents" / "skills"
        if skills_root.is_dir():
            have = {r["slug"] for r in conn.execute(
                "SELECT slug FROM skill_governance")}
            for _d in sorted(skills_root.iterdir()):
                if (_d.is_dir() and not _d.name.startswith(".")
                        and (_d / "SKILL.md").exists() and _d.name not in have):
                    conn.execute(
                        "INSERT OR IGNORE INTO skill_governance "
                        "(slug, state, tier) VALUES (?, 'active', 'T2')",
                        (_d.name,))
        # 冷启动回填：last_used_at 为空时从 skill_events 取该技能最近事件时间
        # （touch_use 上线前无历史；agent_session/daily_review 等事件挂在
        # skill_id 上即代表该技能被触达，作 T1 判定的回填近似）
        conn.execute(
            "UPDATE skill_governance SET last_used_at = COALESCE( "
            "  (SELECT MAX(e.created_at) FROM skill_events e "
            "   WHERE e.skill_id = skill_governance.slug), last_used_at) "
            "WHERE last_used_at IS NULL OR last_used_at = ''")
        rows = conn.execute(
            "SELECT slug, tier, pinned, state, "
            "CAST(julianday('now') - julianday(NULLIF(last_used_at, '')) AS REAL) "
            "AS days_idle FROM skill_governance"
        ).fetchall()
        recent, stale, proficient = _tier_use_sets(conn)

        for r in rows:
            if r["state"] != "active":
                continue
            slug = r["slug"]
            cur = r["tier"]
            days_idle = r["days_idle"]
            used_30d = slug in recent or (days_idle is not None and days_idle <= TIER_ACTIVE_DAYS)
            used_37d = slug in stale or (days_idle is not None and days_idle <= TIER_HYSTERESIS_DAYS)

            if r["pinned"] or slug in proficient:
                new = "T0"
            elif used_30d:
                new = "T1"
            elif cur == "T1" and used_37d:
                new = "T1"  # 滞回带：37 天内仍有痕迹，暂不降级
            else:
                new = "T2"

            if new != cur:
                conn.execute(
                    "UPDATE skill_governance SET tier = ? WHERE slug = ?",
                    (new, slug),
                )
                stats["changed"] += 1
            stats[new] += 1
    return stats


# ═══════════════════════════════════════════════════════════════════
# G2 §4.1: 使用信号与唤醒评估
# ═══════════════════════════════════════════════════════════════════

_touch_ts: Dict[str, float] = {}
_TOUCH_MIN_INTERVAL = 60.0  # 进程内节流：同 slug 60s 内只 touch 一次


def touch_use(slug: str, db=None) -> bool:
    """skill_load 钩子专用轻量记录：仅 UPDATE last_used_at（active 行）。

    与 record_use 的区别：不 INSERT skill_events、不补 registry 行、
    不做唤醒评估（唤醒走每日重算 + 显式 skill_state wake）——
    每次加载同步写库的开销与副作用（事件表膨胀/测试污染）不可接受。
    """
    import time as _time
    if not slug:
        return False
    now = _time.monotonic()
    if now - _touch_ts.get(slug, 0.0) < _TOUCH_MIN_INTERVAL:
        return False
    _touch_ts[slug] = now
    try:
        d = _resolve(db)
        ensure_table(d)
        with d.connect() as conn:
            cur = conn.execute(
                "UPDATE skill_governance SET last_used_at = ? "
                "WHERE slug = ? AND state = 'active'",
                (datetime.now().isoformat(timespec="seconds"), slug))
        return cur.rowcount > 0
    except Exception:
        return False


def record_use(slug: str, db=None) -> Dict[str, Any]:
    """记录一次使用（skill_load/skill_used 命中）并做 dormant 唤醒评估。

    - governance.last_used_at 刷新 + skill_events 追加 skill_used 事件
      （registry 无行时先补 minimal 行，满足 FK）；
    - 若 state=dormant：近 30 天 skill_used >= WAKE_USES_30D（含本次）
      → 自动 set_state active 并返回 {"woken": True}；
      恰 1 次 → {"wake_hint": True}（不自动唤醒，供 doctor 建议位）；
    - 非 dormant 仅记录，返回 {"woken": False}。
    """
    d = _resolve(db)
    ensure_table(d)
    with d.connect() as conn:
        if conn.execute(
            "SELECT 1 FROM skill_registry WHERE skill_id = ?", (slug,)
        ).fetchone() is None:
            conn.execute(
                "INSERT INTO skill_registry (skill_id, name, source, is_active) "
                "VALUES (?, ?, 'agent', 1)",
                (slug, slug),
            )
        conn.execute(
            "INSERT INTO skill_governance (slug, state, last_used_at) "
            "VALUES (?, 'active', datetime('now')) "
            "ON CONFLICT(slug) DO UPDATE SET last_used_at = datetime('now')",
            (slug,),
        )
        conn.execute(
            "INSERT INTO skill_events (skill_id, action, content) "
            "VALUES (?, 'skill_used', ?)",
            (slug, "governance record_use"),
        )
        row = conn.execute(
            "SELECT state, (SELECT count(*) FROM skill_events "
            " WHERE skill_id = ? AND action = 'skill_used' "
            " AND created_at >= datetime('now', '-30 days')) AS uses_30d "
            "FROM skill_governance WHERE slug = ?",
            (slug, slug),
        ).fetchone()
        state = str(row["state"])
        uses_30d = int(row["uses_30d"])

    if state == "dormant":
        if uses_30d >= WAKE_USES_30D:
            set_state(slug, "active", reason="wake: 2+ uses in 30d", db=d)
            return {"woken": True, "wake_hint": False, "state": "active",
                    "uses_30d": uses_30d}
        return {"woken": False, "wake_hint": True, "state": "dormant",
                "uses_30d": uses_30d}
    return {"woken": False, "wake_hint": False, "state": state,
            "uses_30d": uses_30d}


# ═══════════════════════════════════════════════════════════════════
# G2 §5.2: MCP 工具契约纯函数（主会话注册用，返回 JSON 可序列化 dict）
# ═══════════════════════════════════════════════════════════════════

_MCP_ACTION_STATE = {
    "wake": "active",
    "restore": "active",
    "dormant": "dormant",
    "archive": "archived",
    "delete": "deleted",
}


def mcp_skill_state(args: Dict[str, Any]) -> Dict[str, Any]:
    """MCP skill_state 契约：args={skill_id|slug, action, force?}。

    action ∈ wake/dormant/archive/restore/delete → set_state，
    返回 {ok, skill_id, state, woken?} 或 {ok: False, error: {...}}。
    """
    skill_id = str(args.get("skill_id") or args.get("slug") or "")
    action = str(args.get("action") or "")
    if not skill_id:
        return {"ok": False, "skill_id": "", "error": "skill_id is required"}
    if not _skill_exists(skill_id):
        return {"ok": False, "skill_id": skill_id,
                "error": f"skill not found: {skill_id}"}
    if action not in _MCP_ACTION_STATE:
        return {"ok": False, "skill_id": skill_id,
                "error": f"invalid action: {action!r}, expected one of "
                         f"{sorted(_MCP_ACTION_STATE)}"}
    try:
        r = set_state(
            skill_id, _MCP_ACTION_STATE[action],
            reason=f"mcp:{action}",
            force=bool(args.get("force", False)),
        )
    except InvalidTransition as e:
        out: Dict[str, Any] = {"ok": False, "skill_id": skill_id}
        out.update(e.to_dict())
        return out
    except ValueError as e:
        return {"ok": False, "skill_id": skill_id, "error": str(e)}
    out = {"ok": True, "skill_id": skill_id, "state": r["state"],
           "changed": r["changed"]}
    if action == "wake":
        out["woken"] = True
    if action == "delete":
        out["forced"] = r["forced"]
    return out


def _skill_exists(skill_id: str, db=None) -> bool:
    """技能存在性校验：磁盘技能目录或 governance/registry 有记录均算存在。"""
    from pathlib import Path
    if (Path.home() / ".agents" / "skills" / skill_id).is_dir():
        return True
    try:
        d = db if db is not None else _default_db()
        with d.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM skill_governance WHERE slug = ? "
                "UNION SELECT 1 FROM skill_registry WHERE skill_id = ? "
                "AND is_active = 1 LIMIT 1",
                (skill_id, skill_id)).fetchone()
        return row is not None
    except Exception:
        return False


def mcp_set_tier(args: Dict[str, Any]) -> Dict[str, Any]:
    """MCP skill_set_tier 契约：args={skill_id|slug, tier}。

    tier ∈ T0/T1/T2 → set_tier（T0 即 pinned），返回 {ok, skill_id, tier, pinned}。
    """
    skill_id = str(args.get("skill_id") or args.get("slug") or "")
    tier = str(args.get("tier") or "")
    if not skill_id:
        return {"ok": False, "skill_id": "", "error": "skill_id is required"}
    if not _skill_exists(skill_id):
        return {"ok": False, "skill_id": skill_id,
                "error": f"skill not found: {skill_id}"}
    if tier not in VALID_TIERS:
        return {"ok": False, "skill_id": skill_id,
                "error": f"invalid tier: {tier!r}, expected one of {VALID_TIERS}"}
    try:
        r = set_tier(skill_id, tier)
    except Exception as e:
        return {"ok": False, "skill_id": skill_id, "error": str(e)}
    return {"ok": True, "skill_id": skill_id, "tier": r["tier"],
            "pinned": r["pinned"]}


# ═══════════════════════════════════════════════════════════════════
# G4 §4.5: quality_score 写回辅助 + doctor 只读快照
# ═══════════════════════════════════════════════════════════════════

def set_quality_scores(batch: List[Tuple[str, int]], db=None) -> int:
    """批量写回 quality_score（G4 doctor 专用，executemany 单次事务）。

    batch 为 (slug, score) 列表；未登记 slug 由 upsert 补建行（state 取表
    默认 active）。返回写入行数。
    """
    if not batch:
        return 0
    d = _resolve(db)
    ensure_table(d)
    with d.connect() as conn:
        conn.executemany(
            "INSERT INTO skill_governance (slug, quality_score) VALUES (?, ?) "
            "ON CONFLICT(slug) DO UPDATE SET quality_score = excluded.quality_score",
            [(str(s), int(v)) for s, v in batch],
        )
    return len(batch)


def get_governance_snapshot(db=None) -> Dict[str, Dict[str, Any]]:
    """doctor 只读快照（G4）：slug -> {state, tier, last_used_at}。

    表未建/库不可达返回 {}（与 get_states 的未登记语义一致，调用方按
    active/T2/空 兜底）。
    """
    d = _resolve(db)
    try:
        with d.connect() as conn:
            rows = conn.execute(
                "SELECT slug, state, tier, last_used_at FROM skill_governance"
            ).fetchall()
        return {r["slug"]: dict(r) for r in rows}
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════
# B4: 治理字段增补（磁盘页 refresh.py / growth_dashboard MCP 共用）
# ═══════════════════════════════════════════════════════════════

def governance_rows(db=None) -> Dict[str, Dict[str, Any]]:
    """只读 SELECT skill_governance 全表 → slug -> 治理字段 dict。

    quality_score 归一化为 int（NULL/非法 → -1）；表不存在/库不可达抛出，
    由 apply_governance_to_nodes 兜底为默认值。只读，不 import 写函数。
    """
    d = _resolve(db)
    with d.connect() as conn:
        rows = conn.execute(
            "SELECT slug, state, tier, quality_score, last_used_at "
            "FROM skill_governance"
        ).fetchall()
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        try:
            quality = int(r["quality_score"])
        except (TypeError, ValueError):
            quality = -1
        out[str(r["slug"])] = {
            "state": str(r["state"] or ""),
            "tier": str(r["tier"] or ""),
            "quality_score": quality,
            "last_used_at": str(r["last_used_at"] or ""),
        }
    return out


def apply_governance_to_nodes(nodes: List[Dict[str, Any]], db=None,
                              id_key: str = "id") -> None:
    """节点 payload 增补治理字段 state/tier/quality_score/last_used_at。

    全程 try/except：治理数据缺失（表未建/库不可达/行缺失）只降级为
    默认值（active/T2/-1/空时间），绝不让调用方（snapshot 生成 /
    MCP 工具返回）失败。单点实现，磁盘页 refresh 脚本与 growth_dashboard
    MCP 工具共用，保证两处增补口径一致。

    Args:
        nodes: 就地增补的节点 dict 列表；
        db: DatabaseManager 覆写（测试用），缺省 _default_db()；
        id_key: 节点主键字段名——refresh 节点用 "id"，
                growth_dashboard 技能行用 "skill_id"。
    """
    try:
        rows = governance_rows(db)
    except Exception as exc:  # noqa: BLE001 — 治理数据缺失必须兜底
        logger.info("governance table unavailable, nodes use defaults: %s", exc)
        rows = {}
    for node in nodes:
        try:
            row = rows.get(str(node.get(id_key) or "")) or {}
            node["state"] = str(row.get("state") or "active")
            node["tier"] = str(row.get("tier") or "T2")
            try:
                node["quality_score"] = int(row.get("quality_score", -1))
            except (TypeError, ValueError):
                node["quality_score"] = -1
            node["last_used_at"] = str(row.get("last_used_at") or "")
        except Exception as exc:  # noqa: BLE001 — 单节点失败不影响整体
            logger.warning("governance enrich failed for %s: %s",
                           node.get(id_key), exc)
