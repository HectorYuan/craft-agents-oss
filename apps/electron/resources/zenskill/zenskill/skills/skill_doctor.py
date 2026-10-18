"""技能体检 doctor（G4，docs/skill_governance_plan.md §4.5，解 P6/P7）。

quality_score 四维（0-100，doctor 产出并批量写回 skill_governance）：
- frontmatter 完整 40：六字段（name/description/category/type/when/tags），
  每缺一项扣 40//6=6 分（空值语义与 validate_one / U-02 一致：falsy 或空列表）；
- description 质量 20：len>=40 字符得 10 + when 非空得 10；
- 引用一致 20：SKILL.md 正文 scripts/ resources/ 相对引用全部存在得满分，
  缺失按比例扣（借鉴 usability_validator U-03 的正则提取思路，轻量重写）；
- 活跃度 20：governance.last_used_at 30 天内 20 / 90 天内 10 / 更久或空 5
  （不给 0，冷启动友好）。

体检节（建议制，除 quality_score 写回外不改任何治理状态）：
- overview：总数 / tier 分布 / state 分布 / 平均质量分；
- dormant_suggestions：active 且闲置 >90 天（last_used_at 为空回退目录
  mtime）且熟练度 <0.3，排除未完成 GTD 行动引用与活跃修炼行；
- duplicates：同 category 且关键词集合 Jaccard >0.6，建议保留高分者；
- when_conflicts：同 category 且 when 触发词重叠 >=3 词；
- quality_low：score<60 top10（附 fix_hint）。

MCP 契约：mcp_skills_doctor({section?})，JSON 可序列化；
338 技能全量为纯内存计算 + 一次批量写回（<10s 红线）。
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import yaml

from .skill_governance import (
    ensure_table,
    get_governance_snapshot,
    set_quality_scores,
)

# ═══════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════

DOCTOR_FIELDS = ("name", "description", "category", "type", "when", "tags")

_FM_FULL = 40
_FM_PER_FIELD = _FM_FULL // len(DOCTOR_FIELDS)      # 40//6 → 6，向下取整
_DESC_MIN_LEN = 40
_DESC_LEN_POINTS = 10
_DESC_WHEN_POINTS = 10
_REF_FULL = 20
_ACTIVITY_FULL = 20
_ACTIVITY_RECENT_DAYS = 30
_ACTIVITY_MID_DAYS = 90
_ACTIVITY_FLOOR = 5
_LOW_QUALITY_THRESHOLD = 60
_LOW_QUALITY_TOP = 10

_DUP_JACCARD = 0.6
_CONFLICT_MIN_OVERLAP = 3
_DORMANT_IDLE_DAYS = 90
_DORMANT_MAX_PROFICIENCY = 0.3
_CULTIVATION_ACTIVE_DAYS = 30

ALL_SECTIONS = ("overview", "dormant_suggestions", "duplicates",
                "quality_low", "when_conflicts")
MCP_SECTIONS = ("overview", "dormant", "duplicates", "quality", "conflicts")
SECTION_ALIASES: Dict[str, str] = {
    "overview": "overview",
    "dormant": "dormant_suggestions",
    "dormant_suggestions": "dormant_suggestions",
    "duplicates": "duplicates",
    "quality": "quality_low",
    "quality_low": "quality_low",
    "conflicts": "when_conflicts",
    "when_conflicts": "when_conflicts",
}

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_REF_RE = re.compile(r"(?:scripts|resources)/[A-Za-z0-9_][A-Za-z0-9_./-]*",
                     re.IGNORECASE)
# 轻量分词：小写后按非（字母/数字/中文）切分
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9\u4e00-\u9fff]+")
_TS_FALLBACK_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


# ═══════════════════════════════════════════════════════════════════
# 基础工具
# ═══════════════════════════════════════════════════════════════════

def _parse_frontmatter(content: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """返回 (frontmatter dict 或 None, 正文)。YAML 非法/非映射按缺失处理。"""
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return None, content
    try:
        raw = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None, content[m.end():]
    return (raw if isinstance(raw, dict) else None), content[m.end():]


def _as_text(value: Any) -> str:
    """字段值转文本（list 拼接；标量 str()；None/空 → ''）。"""
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_as_text(v) for v in value if v is not None)
    return str(value)


def tokenize(text: str) -> Set[str]:
    """轻量分词：小写 + 按非（字母/数字/中文）切分，去空串。"""
    if not text:
        return set()
    return {t for t in _TOKEN_SPLIT_RE.split(text.lower()) if t}


def _parse_ts(value: str) -> Optional[datetime]:
    if not value:
        return None
    s = str(value)
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    for fmt in _TS_FALLBACK_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


# ═══════════════════════════════════════════════════════════════════
# 单技能扫描与四维评分
# ═══════════════════════════════════════════════════════════════════

def _missing_fields(meta: Optional[Dict[str, Any]]) -> List[str]:
    missing: List[str] = []
    for f in DOCTOR_FIELDS:
        v = (meta or {}).get(f)
        if not v or (isinstance(v, (list, tuple, set)) and not v):
            missing.append(f)
    return missing


def _reference_stats(skill_dir: Path, body: str) -> Tuple[int, List[str]]:
    """正文 scripts/ resources/ 引用统计：返回 (引用总数, 缺失列表)。"""
    refs = {r.rstrip(".") for r in _REF_RE.findall(body)}
    refs.discard("")
    missing = sorted(r for r in refs if not (skill_dir / r).exists())
    return len(refs), missing


def _scan_skill(skill_dir: Path) -> Dict[str, Any]:
    """扫描单技能目录：frontmatter/关键词/引用（不含活跃度，需 governance）。"""
    slug = skill_dir.name
    meta: Optional[Dict[str, Any]] = None
    body = ""
    skill_md = skill_dir / "SKILL.md"
    if skill_md.is_file():
        try:
            content = skill_md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            content = ""
        meta, body = _parse_frontmatter(content)

    raw = meta or {}
    name = _as_text(raw.get("name"))
    when = _as_text(raw.get("when"))
    desc = _as_text(raw.get("description"))
    raw_tags = raw.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]
    tags = [t.strip() for t in (_as_text(v) for v in raw_tags) if t.strip()]
    name_tokens = tokenize(name)
    when_tokens = tokenize(when)
    tag_tokens: Set[str] = set()
    for t in tags:
        tag_tokens |= tokenize(t)
    refs_total, refs_missing = _reference_stats(skill_dir, body)

    return {
        "slug": slug,
        "dir": skill_dir,
        "meta": meta,
        "category": _as_text(raw.get("category")).strip(),
        "missing_fields": _missing_fields(meta),
        "description": desc,
        "when": when,
        "tags": tags,
        "keywords": name_tokens | when_tokens | tag_tokens,
        "when_tokens": when_tokens,
        "refs_total": refs_total,
        "refs_missing": refs_missing,
    }


def _frontmatter_score(missing: List[str]) -> int:
    return max(0, _FM_FULL - _FM_PER_FIELD * len(missing))


def _description_score(desc: str, when: str) -> int:
    return (_DESC_LEN_POINTS if len(desc) >= _DESC_MIN_LEN else 0) \
        + (_DESC_WHEN_POINTS if when.strip() else 0)


def _reference_score(total: int, missing_count: int) -> int:
    if total <= 0:
        return _REF_FULL
    return int(_REF_FULL * (total - missing_count) / total)


def _activity_score(last_used_at: str, now: datetime) -> int:
    """活跃度：30 天内 20 / 90 天内 10 / 更久或空 5（不给 0）。"""
    ts = _parse_ts(last_used_at)
    if ts is None:
        return _ACTIVITY_FLOOR
    days = (now - ts).days
    if days <= _ACTIVITY_RECENT_DAYS:
        return _ACTIVITY_FULL
    if days <= _ACTIVITY_MID_DAYS:
        return 10
    return _ACTIVITY_FLOOR


def _score_scan(scan: Dict[str, Any], last_used_at: str,
                now: datetime) -> None:
    """就地补齐 scan 的 breakdown 与 score（含活跃度维度）。"""
    breakdown = {
        "frontmatter": _frontmatter_score(scan["missing_fields"]),
        "description": _description_score(scan["description"], scan["when"]),
        "references": _reference_score(scan["refs_total"],
                                       len(scan["refs_missing"])),
        "activity": _activity_score(last_used_at, now),
    }
    scan["breakdown"] = breakdown
    scan["score"] = sum(breakdown.values())


# ═══════════════════════════════════════════════════════════════════
# 重复检测 / when 冲突 / 休眠建议
# ═══════════════════════════════════════════════════════════════════

def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _by_category(scans: Sequence[Dict[str, Any]]) -> Dict[str, List[dict]]:
    """category 分组（缺失 category 的技能不参与重复/冲突检测）。"""
    groups: Dict[str, List[dict]] = {}
    for s in scans:
        if s["category"]:
            groups.setdefault(s["category"], []).append(s)
    return groups


def find_duplicates(scans: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """同 category 且关键词 Jaccard >0.6 的候选对（O(n²)，338 技能可接受）。"""
    out: List[Dict[str, Any]] = []
    for cat, group in sorted(_by_category(scans).items()):
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                jac = _jaccard(a["keywords"], b["keywords"])
                if jac <= _DUP_JACCARD:
                    continue
                if (a["score"] > b["score"]
                        or (a["score"] == b["score"] and a["slug"] <= b["slug"])):
                    keep, archive = a, b
                else:
                    keep, archive = b, a
                out.append({
                    "a": a["slug"],
                    "b": b["slug"],
                    "jaccard": round(jac, 3),
                    "category": cat,
                    "keep": keep["slug"],
                    "archive": archive["slug"],
                    "suggestion": (
                        f"保留 {keep['slug']}(quality_score={keep['score']})，"
                        f"建议将 {archive['slug']}(quality_score={archive['score']}) 转归档"
                    ),
                })
    return out


def find_when_conflicts(
        scans: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """同 category 下 when 触发词集合重叠 >=3 词的对。"""
    out: List[Dict[str, Any]] = []
    for cat, group in sorted(_by_category(scans).items()):
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                shared = a["when_tokens"] & b["when_tokens"]
                if len(shared) < _CONFLICT_MIN_OVERLAP:
                    continue
                out.append({
                    "a": a["slug"],
                    "b": b["slug"],
                    "category": cat,
                    "shared_words": sorted(shared),
                    "suggestion": "同 category 下 when 触发词高度重叠，建议差异化触发词或合并",
                })
    return out


def _db_slug_set(db, sql: str) -> Set[str]:
    """辅助：单列查询转 slug 集合（表缺失/库不可达返回空集）。"""
    try:
        with db.connect() as conn:
            return {str(r[0]) for r in conn.execute(sql) if r[0]}
    except Exception:
        return set()


def _cultivation_active(db, now: datetime) -> Set[str]:
    """活跃修炼集合：total_interactions>0 且最近交互 30 天内。"""
    try:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT skill_id, last_interaction_at FROM skill_cultivation "
                "WHERE total_interactions > 0"
            ).fetchall()
    except Exception:
        return set()
    active: Set[str] = set()
    for r in rows:
        ts = _parse_ts(str(r["last_interaction_at"] or ""))
        if ts is not None and (now - ts).days <= _CULTIVATION_ACTIVE_DAYS:
            active.add(str(r["skill_id"]))
    return active


def _proficiency_map(db) -> Dict[str, float]:
    try:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT skill_id, proficiency FROM skill_abilities").fetchall()
        return {str(r["skill_id"]): float(r["proficiency"]) for r in rows}
    except Exception:
        return {}


def find_dormant_candidates(
        scans: Sequence[Dict[str, Any]],
        snapshot: Dict[str, Dict[str, Any]],
        db,
        now: datetime) -> List[Dict[str, Any]]:
    """休眠建议（建议制，不改状态）：
    state=active 且闲置 >90 天（last_used_at 为空回退目录 mtime）
    且 proficiency<0.3（无记录视为满足）；
    排除：未完成 GTD 行动引用、活跃修炼行（30 天内有交互）。
    """
    gtd_block = _db_slug_set(
        db,
        "SELECT DISTINCT skill_id FROM gtd_actions "
        "WHERE status IS NOT NULL AND status != 'completed'")
    cult_block = _cultivation_active(db, now)
    proficiencies = _proficiency_map(db)

    out: List[Dict[str, Any]] = []
    for s in scans:
        slug = s["slug"]
        row = snapshot.get(slug) or {}
        if str(row.get("state") or "active") != "active":
            continue
        if slug in gtd_block or slug in cult_block:
            continue
        proficiency = proficiencies.get(slug)
        if proficiency is not None and proficiency >= _DORMANT_MAX_PROFICIENCY:
            continue

        ts = _parse_ts(str(row.get("last_used_at") or ""))
        if ts is not None:
            idle_days = (now - ts).days
            source = "last_used_at"
        else:
            try:
                mtime = datetime.fromtimestamp(s["dir"].stat().st_mtime)
            except OSError:
                continue
            idle_days = (now - mtime).days
            source = "dir_mtime"
        if idle_days <= _DORMANT_IDLE_DAYS:
            continue

        prof_text = ("无记录" if proficiency is None
                     else f"{proficiency:.2f}")
        out.append({
            "slug": slug,
            "idle_days": idle_days,
            "idle_source": source,
            "proficiency": proficiency,
            "reason": f"最后使用 {idle_days} 天前（{source}），"
                      f"熟练度 {prof_text} → 建议 dormant",
        })
    out.sort(key=lambda x: (-x["idle_days"], x["slug"]))
    return out


# ═══════════════════════════════════════════════════════════════════
# 报告组装
# ═══════════════════════════════════════════════════════════════════

def _overview(scans: Sequence[Dict[str, Any]],
              snapshot: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    by_tier = {"T0": 0, "T1": 0, "T2": 0}
    by_state = {"active": 0, "dormant": 0, "archived": 0, "deleted": 0}
    for s in scans:
        row = snapshot.get(s["slug"]) or {}
        tier = str(row.get("tier") or "T2")
        state = str(row.get("state") or "active")
        by_tier[tier if tier in by_tier else "T2"] += 1
        by_state[state if state in by_state else "active"] += 1
    scores = [s["score"] for s in scans]
    avg = round(sum(scores) / len(scores), 1) if scores else 0.0
    return {
        "total": len(scans),
        "by_tier": by_tier,
        "by_state": by_state,
        "avg_quality": avg,
    }


def _quality_low(scans: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """score<60 top10（附 fix_hint：缺失字段清单 + 其他可修项）。"""
    rows = sorted((s for s in scans if s["score"] < _LOW_QUALITY_THRESHOLD),
                  key=lambda s: (s["score"], s["slug"]))
    out: List[Dict[str, Any]] = []
    for s in rows[:_LOW_QUALITY_TOP]:
        hints: List[str] = []
        if s["missing_fields"]:
            hints.append("补充缺失字段: " + ", ".join(s["missing_fields"]))
        if len(s["description"]) < _DESC_MIN_LEN:
            hints.append(f"description 扩写到 {_DESC_MIN_LEN} 字符以上")
        if s["refs_missing"]:
            hints.append("修复失效引用: " + ", ".join(s["refs_missing"]))
        out.append({
            "slug": s["slug"],
            "score": s["score"],
            "breakdown": dict(s["breakdown"]),
            "fix_hint": "；".join(hints) if hints else "各项达标，低分来自长期未使用",
        })
    return out


def _resolve_sections(sections: Optional[Sequence[str]]) -> Set[str]:
    if sections is None:
        return set(ALL_SECTIONS)
    if isinstance(sections, str):
        sections = [sections]
    if not sections:
        return set(ALL_SECTIONS)
    want = {SECTION_ALIASES.get(str(x).strip(), str(x).strip())
            for x in sections}
    valid = want & set(ALL_SECTIONS)
    return valid or set(ALL_SECTIONS)


def run_doctor(skills_dir: str | Path | None = None, db=None,
               sections: Sequence[str] | None = None) -> Dict[str, Any]:
    """全量体检：扫描 → 评分 → 批量写回 quality_score → 组装报告。

    skills_dir 缺省 ~/.agents/skills；db 缺省全局库。sections 指定输出节
    （支持 overview/dormant/duplicates/quality/conflicts 及全名别名），
    quality_score 写回无论取哪些节都会执行。
    """
    root = Path(skills_dir) if skills_dir is not None \
        else Path.home() / ".agents" / "skills"
    now = datetime.now()

    scans: List[Dict[str, Any]] = []
    if root.is_dir():
        for d in sorted(root.iterdir()):
            if (d.is_dir() and not d.name.startswith(".")
                    and (d / "SKILL.md").is_file()):
                scans.append(_scan_skill(d))

    snapshot = get_governance_snapshot(db)
    batch: List[Tuple[str, int]] = []
    for s in scans:
        last_used = str((snapshot.get(s["slug"]) or {}).get("last_used_at") or "")
        _score_scan(s, last_used, now)
        batch.append((s["slug"], s["score"]))
    set_quality_scores(batch, db)

    want = _resolve_sections(sections)
    report: Dict[str, Any] = {}
    if "overview" in want:
        report["overview"] = _overview(scans, snapshot)
    if "dormant_suggestions" in want:
        report["dormant_suggestions"] = find_dormant_candidates(
            scans, snapshot, db, now)
    if "duplicates" in want:
        report["duplicates"] = find_duplicates(scans)
    if "quality_low" in want:
        report["quality_low"] = _quality_low(scans)
    if "when_conflicts" in want:
        report["when_conflicts"] = find_when_conflicts(scans)
    return report


def mcp_skills_doctor(args: Optional[Dict[str, Any]] = None, db=None,
                      skills_dir: str | Path | None = None) -> Dict[str, Any]:
    """MCP skills_doctor 契约（read）：args={section?}，缺省全量报告。

    section ∈ overview|dormant|duplicates|quality|conflicts。
    db/skills_dir 为可选注入参数（工具宿主/测试用），缺省走全局库与
    ~/.agents/skills。返回 JSON 可序列化 dict。
    """
    section = str((args or {}).get("section") or "").strip()
    if not section:
        return {"ok": True, **run_doctor(db=db, skills_dir=skills_dir)}
    key = SECTION_ALIASES.get(section)
    if key is None or section not in MCP_SECTIONS:
        return {
            "ok": False,
            "error": f"invalid section: {section!r}, expected one of "
                     f"{list(MCP_SECTIONS)}",
        }
    return {"ok": True, **run_doctor(sections=[key], db=db,
                                     skills_dir=skills_dir)}


# ensure_table 供工具宿主初始化（doctor 写回路径内部已保证建表）
__all__ = [
    "ALL_SECTIONS",
    "DOCTOR_FIELDS",
    "MCP_SECTIONS",
    "SECTION_ALIASES",
    "ensure_table",
    "find_duplicates",
    "find_dormant_candidates",
    "find_when_conflicts",
    "mcp_skills_doctor",
    "run_doctor",
    "tokenize",
]
