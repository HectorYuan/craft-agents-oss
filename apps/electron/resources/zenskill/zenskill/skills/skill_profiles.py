"""场景集 Profile + 注入预算池解析（G3，docs/skill_governance_plan.md §4.3/4.4）。

- skill_profiles.yaml（~/.zenskill/skill_profiles.yaml）解析：default + profiles；
  规则优先级 exclude > include > tiers > categories（黑名单否决一切；
  include 白名单无视 tiers/categories 直接入选；tiers 命中判定后不再看 categories）。
- pool_for：profile 规则 ∩ 治理状态硬约束（dormant/archived/deleted 一律排除，
  即便 include 提名——治理状态是硬约束）。治理数据只读 SELECT（本模块自写查询，
  不改 skill_governance.py）；未登记技能视为 active/T2。
- resolve_profile 解析链：显式参数 > ZENSKILL_SKILL_PROFILE > yaml default > None
  （无 profile = 全 active 池）。
- mcp_skills_section_stats：MCP JSON 契约（主会话注册用）。

隔离约定：测试一律 DatabaseManager(db_path=tmp) 注入 db 参数；config_path
可注入避免触碰真实 ~/.zenskill；ZENSKILL_SKILL_FILTER=off 时与 G1 逃生
语义对齐（全池直通）。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

logger = logging.getLogger(__name__)

PROFILES_FILENAME = "skill_profiles.yaml"
DEFAULT_BUDGET_TOKENS = 4000
VALID_TIERS = ("T0", "T1", "T2")
_TIER_SET = set(VALID_TIERS)
_EXCLUDED_STATES = ("dormant", "archived", "deleted")
_CHUNK = 400  # SQLite 绑定变量上限保守分块


def default_config_path() -> Path:
    return Path.home() / ".zenskill" / PROFILES_FILENAME


def _normalize_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(t).strip() for t in value if str(t).strip()]
    return [str(value).strip()]


def _empty_rules() -> Dict[str, List[str]]:
    return {"tiers": [], "categories": [], "include": [], "exclude": []}


def load_profiles(config_path: Optional[str] = None) -> dict:
    """读 skill_profiles.yaml；不存在/非法 YAML/结构不符 → 默认空配置（容错不抛）。

    返回 {"default": <name|None>, "profiles": {name: {tiers, categories,
    include, exclude}}}，各规则字段恒为 list[str]。
    """
    path = Path(config_path) if config_path else default_config_path()
    if not path.is_file():
        return {"default": None, "profiles": {}}
    try:
        import yaml

        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("skill_profiles.yaml 解析失败，按空配置处理 (%s): %s", path, e)
        return {"default": None, "profiles": {}}
    if not isinstance(raw, dict):
        logger.warning("skill_profiles.yaml 不是映射结构，按空配置处理: %s", path)
        return {"default": None, "profiles": {}}

    profiles: Dict[str, Dict[str, List[str]]] = {}
    profiles_raw = raw.get("profiles")
    if isinstance(profiles_raw, dict):
        for name, cfg in profiles_raw.items():
            if not isinstance(cfg, dict):
                cfg = {}
            tiers = [t for t in _normalize_str_list(cfg.get("tiers"))
                     if t.upper() in _TIER_SET]
            profiles[str(name)] = {
                "tiers": [t.upper() for t in tiers],
                "categories": _normalize_str_list(cfg.get("categories")),
                "include": _normalize_str_list(cfg.get("include")),
                "exclude": _normalize_str_list(cfg.get("exclude")),
            }

    default_raw = raw.get("default")
    default = str(default_raw).strip() if isinstance(default_raw, str) else ""
    return {"default": default or None, "profiles": profiles}


def resolve_profile(explicit: Optional[str] = None,
                    config_path: Optional[str] = None) -> dict:
    """profile 解析链：显式参数 > 环境变量 ZENSKILL_SKILL_PROFILE > yaml default > None。

    返回 {"name": <str|None>, "rules": {...}, "source":
    "explicit"|"env"|"default"|"none"}；名字未在 yaml 定义时 rules 为空
    （无过滤 = 全 active 池，不做硬失败）。
    """
    cfg = load_profiles(config_path)
    name: Optional[str] = None
    source = "none"
    if explicit:
        name, source = str(explicit), "explicit"
    else:
        env = os.environ.get("ZENSKILL_SKILL_PROFILE", "").strip()
        if env:
            name, source = env, "env"
        elif cfg["default"]:
            name, source = cfg["default"], "default"
    rules = dict(cfg["profiles"].get(name or "", _empty_rules()))
    return {"name": name, "rules": rules, "source": source}


# ═══════════════════════════════════════════════════════════════
# 治理数据只读查询（不改 skill_governance.py）
# ═══════════════════════════════════════════════════════════════


def _default_db():
    from zenskill.core.database import db
    return db


def _fetch_all_slugs(d) -> Set[str]:
    """governance 全量登记 slug（表缺失/库不可达 → 空集）。"""
    try:
        with d.connect() as conn:
            hit = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='skill_governance'"
            ).fetchone()
            if hit is None:
                return set()
            return {str(r["slug"]) for r in
                    conn.execute("SELECT slug FROM skill_governance")}
    except Exception as e:
        logger.debug("skill_profiles: governance universe unavailable: %s", e)
        return set()


def _fetch_governance(slugs: Set[str], d) -> Dict[str, dict]:
    """批量只读 SELECT slug,tier,pinned,state,last_used_at；表缺失/异常 → {}。"""
    out: Dict[str, dict] = {}
    if not slugs:
        return out
    try:
        with d.connect() as conn:
            hit = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='skill_governance'"
            ).fetchone()
            if hit is None:
                return out
            ordered = sorted(slugs)
            for i in range(0, len(ordered), _CHUNK):
                chunk = ordered[i:i + _CHUNK]
                rows = conn.execute(
                    f"SELECT slug, tier, pinned, state, last_used_at "
                    f"FROM skill_governance WHERE slug IN "
                    f"({','.join('?' * len(chunk))})",
                    tuple(chunk),
                ).fetchall()
                for r in rows:
                    out[str(r["slug"])] = {
                        "tier": str(r["tier"] or "T2"),
                        "pinned": bool(r["pinned"]),
                        "state": str(r["state"] or "active"),
                        "last_used_at": str(r["last_used_at"] or ""),
                    }
    except Exception as e:
        logger.debug("skill_profiles: governance read unavailable: %s", e)
    return out


def _fetch_categories(slugs: Set[str], d) -> Dict[str, str]:
    """批量只读 SELECT skill_registry.category（JOIN 来源）；表缺失/异常 → {}。"""
    out: Dict[str, str] = {}
    if not slugs:
        return out
    try:
        with d.connect() as conn:
            ordered = sorted(slugs)
            for i in range(0, len(ordered), _CHUNK):
                chunk = ordered[i:i + _CHUNK]
                rows = conn.execute(
                    f"SELECT skill_id, category FROM skill_registry "
                    f"WHERE skill_id IN ({','.join('?' * len(chunk))})",
                    tuple(chunk),
                ).fetchall()
                for r in rows:
                    out[str(r["skill_id"])] = str(r["category"] or "")
    except Exception as e:
        logger.debug("skill_profiles: registry category read unavailable: %s", e)
    return out


def _apply_rules(slug: str, tier: str, category: str,
                 rules: Dict[str, List[str]]) -> Optional[str]:
    """规则瀑布（exclude > include > tiers > categories）。

    返回 None = 入选；否则返回排除原因标签。
    """
    if slug in rules.get("exclude", []):
        return "profile:exclude"
    include = rules.get("include", [])
    if include and slug in include:
        return None  # 白名单无视 tiers/categories
    tiers = rules.get("tiers", [])
    if tiers:
        return None if tier in tiers else "profile:tiers"
    categories = rules.get("categories", [])
    if categories:
        return None if category in categories else "profile:categories"
    return None  # 无规则 = 全池


def pool_for(profile_name: Optional[str] = None, db=None,
             slugs: Optional[Iterable[str]] = None,
             config_path: Optional[str] = None) -> dict:
    """计算注入池：profile 规则 ∩ 治理状态硬约束。

    slugs: 候选 slug 全集（磁盘发现）；None 时用 skill_governance 全量登记。
    未登记技能视为 active/T2。返回：
    {
      "included": set,                       # 入池 slug
      "excluded": set,                       # 被剔除 slug
      "excluded_with_reason": {slug: reason},  # governance:<state> | profile:<rule>
      "meta": {slug: {tier, state, pinned, last_used_at, category}},
      "profile": <name|None>, "source": <resolve 来源>,
    }
    """
    resolved = resolve_profile(profile_name, config_path)
    d = db if db is not None else _default_db()
    universe = set(slugs) if slugs is not None else _fetch_all_slugs(d)
    gov = _fetch_governance(universe, d)
    cats = _fetch_categories(universe, d)

    meta: Dict[str, dict] = {}
    for slug in universe:
        row = gov.get(slug)
        meta[slug] = {
            "tier": row["tier"] if row else "T2",
            "state": row["state"] if row else "active",
            "pinned": row["pinned"] if row else False,
            "last_used_at": row["last_used_at"] if row else "",
            "category": cats.get(slug, ""),
        }

    if os.environ.get("ZENSKILL_SKILL_FILTER", "").strip().lower() == "off":
        # G1 逃生开关语义对齐：全池直通（含治理豁免）
        return {"included": set(universe), "excluded": set(),
                "excluded_with_reason": {}, "meta": meta,
                "profile": resolved["name"], "source": resolved["source"]}

    included: Set[str] = set()
    excluded_with_reason: Dict[str, str] = {}
    for slug in universe:
        m = meta[slug]
        if m["state"] in _EXCLUDED_STATES:
            # 治理硬约束：include 提名也不入选
            excluded_with_reason[slug] = f"governance:{m['state']}"
            continue
        reason = _apply_rules(slug, m["tier"], m["category"], resolved["rules"])
        if reason is None:
            included.add(slug)
        else:
            excluded_with_reason[slug] = reason
    return {"included": included, "excluded": set(excluded_with_reason),
            "excluded_with_reason": excluded_with_reason, "meta": meta,
            "profile": resolved["name"], "source": resolved["source"]}


# ═══════════════════════════════════════════════════════════════
# MCP 工具契约（主会话注册用，返回 JSON 可序列化 dict）
# ═══════════════════════════════════════════════════════════════


def mcp_skills_section_stats(args: Dict[str, Any]) -> Dict[str, Any]:
    """MCP skills_section_stats 契约：args={profile?, scenario?, skills_dirs?}。

    调用 build_skills_section 的统计模式（compose_skills_section），
    返回 {profile, injected_count, est_tokens, budget_tokens,
    tier_counts: {T0, T1, T2}, truncated}。
    """
    from ..runtime.agent.skill_tools import compose_skills_section

    dirs = args.get("skills_dirs")
    _section, stats = compose_skills_section(
        scenario=args.get("scenario") or None,
        skills_dirs=[str(x) for x in dirs] if dirs else None,
        profile=args.get("profile") or None,
    )
    return stats
