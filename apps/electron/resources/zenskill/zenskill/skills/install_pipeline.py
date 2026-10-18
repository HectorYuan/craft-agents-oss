"""五阶段安全安装管线（W3，解 G2/G5）— resolve/fetch/scan/gate/promote+supply。

方案 docs/skill_market_integration_plan.md 2.1 与第六章 D；安全补强 S1/S5：
- staging 与目标同目录树（``<target>/.staging``）保 ``os.replace`` 原子性；
  staging 目录 0700，promote 前复验文件哈希（TOCTOU）。
- 解压统一走 safe_extract（SEC-005 前置），URL 下载复用 market_generic
  的 SSRF 校验（评审 S2）。
- MCP 面（mcp_install）不暴露 no_scan（评审 S1），仅 CLI 人工经
  universal_installer.install(..., no_scan=True) 显式传入。

审计表 skill_audit（skill_id/ts/action/risk/rules 摘要）在本模块建表，
经 core/database.py 连接约定写入；审计失败不污染安装语义。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from .safe_extract import SafeExtractError, safe_extract
from .security_scanner import scan_directory
from .universal_installer import universal_installer as _installer
from .usability_validator import validate_usability

logger = logging.getLogger(__name__)

ARCHIVE_SUFFIXES = (
    ".tar.gz", ".tar.bz2", ".tar.xz",
    ".tgz", ".tbz2", ".txz", ".tar", ".zip",
)
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
DOWNLOAD_TIMEOUT = 15.0

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def default_target_dir() -> Path:
    """安装目标目录（运行时求值：测试 conftest 会逐用例改写 HOME）。"""
    return Path.home() / ".agents" / "skills"


class _FetchError(Exception):
    """fetch 阶段失败（解压拒绝/SSRF/下载失败）；kind 供审计与返回体。"""

    def __init__(self, message: str, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


# ═══════════════════════════════════════════════════════════════
# 阶段 1 resolve — 复用 universal_installer._classify_source + 归档/目录识别
# ═══════════════════════════════════════════════════════════════

@dataclass
class _Resolved:
    kind: str                          # archive / directory / url
    slug: str
    path: Optional[Path] = None
    url: Optional[str] = None
    market: str = "file"               # 返回体报告用


def _strip_archive_suffix(name: str) -> str:
    low = name.lower()
    for suf in ARCHIVE_SUFFIXES:
        if low.endswith(suf) and len(low) > len(suf):
            return name[: -len(suf)]
    return name


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")
    return slug or "skill"


def _resolve(uri: str) -> Optional[_Resolved]:
    """解析为管线可处理的来源；不支持（market/github/unknown/单文件内容）返回 None。"""
    classify = _installer._classify_source(uri)
    if classify["type"] == "url":
        # github.com repo URL 已被 _classify_source 归为 github，不进此处
        last = urlsplit(uri).path.rstrip("/").rsplit("/", 1)[-1]
        return _Resolved("url", _slugify(_strip_archive_suffix(last)),
                         url=uri, market="url")
    raw = uri
    if classify["type"] == "file":
        raw = classify.get("path", uri)
    path = Path(raw)
    if path.is_dir():
        return _Resolved("directory", path.name, path=path, market="file")
    if path.is_file() and any(path.name.lower().endswith(s) for s in ARCHIVE_SUFFIXES):
        return _Resolved("archive", _slugify(_strip_archive_suffix(path.name)),
                         path=path, market="file")
    return None


def can_handle(uri: str) -> bool:
    """universal_installer.install 的分流判定：仅本地目录/zip/tar 归档走管线。

    URL 与 .zenskill-package 保持既有安装路径（W1 回归等价）；管线直调
    install() 时 URL 归档下载仍可用（SSRF 校验后）。
    """
    try:
        resolved = _resolve(uri)
    except Exception:
        return False
    return resolved is not None and resolved.kind in ("archive", "directory")


# ═══════════════════════════════════════════════════════════════
# 阶段 2 fetch — 隔离区抓取（S5：staging 0700、同文件系统、safe_extract）
# ═══════════════════════════════════════════════════════════════

def _make_staging(target_dir: Path, slug: str, ts: int) -> Path:
    staging_root = target_dir / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(staging_root, 0o700)
    except OSError:
        pass
    session = staging_root / f"{slug}-{ts}"
    session.mkdir(mode=0o700)
    return session


def _locate_skill_root(extract_dir: Path) -> Path:
    """归档顶层包裹目录识别：根有 SKILL.md 用根，否则唯一子目录含 SKILL.md 用它。"""
    if (extract_dir / "SKILL.md").is_file():
        return extract_dir
    try:
        children = [p for p in extract_dir.iterdir()
                    if not p.name.startswith(".")]
    except OSError:
        return extract_dir
    if (len(children) == 1 and children[0].is_dir()
            and (children[0] / "SKILL.md").is_file()):
        return children[0]
    return extract_dir


def _download(url: str, session_dir: Path) -> Path:
    """URL 归档下载：market_generic SSRF 校验（S2）+ 流式限额（不跟随重定向）。"""
    from .market_generic import MarketSSRFError, assert_public_http_url
    try:
        assert_public_http_url(url)
    except MarketSSRFError as e:
        raise _FetchError(f"SSRF 防护拒绝: {e}", "ssrf_blocked") from e

    last = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    suffix = next((s for s in ARCHIVE_SUFFIXES if last.lower().endswith(s)), "")
    if not suffix:
        raise _FetchError(f"URL 非归档（仅支持 zip/tar）: {url}", "url_not_archive")

    import requests
    try:
        resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True,
                            allow_redirects=False)
    except requests.RequestException as e:
        raise _FetchError(f"下载失败: {type(e).__name__}: {e}"[:300],
                          "download_failed") from e
    dest = session_dir / f"download{suffix}"
    size = 0
    try:
        if resp.status_code != 200:
            raise _FetchError(f"HTTP {resp.status_code} ({url})", "download_failed")
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    raise _FetchError(
                        f"下载数据超过 {MAX_DOWNLOAD_BYTES // (1024 * 1024)}MB 上限",
                        "download_too_large")
                fh.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    finally:
        resp.close()
    return dest


def _fetch(resolved: _Resolved, session_dir: Path) -> Tuple[Path, str]:
    """抓取到 session_dir，返回 (技能根目录, slug)。失败抛 _FetchError。"""
    extract_dir = session_dir / "extract"
    if resolved.kind == "archive":
        try:
            safe_extract(resolved.path, extract_dir)
        except SafeExtractError as e:
            raise _FetchError(f"safe_extract 拒绝: {e}", "extract_rejected") from e
    elif resolved.kind == "directory":
        shutil.copytree(resolved.path, extract_dir, symlinks=True)
    else:
        archive = _download(str(resolved.url), session_dir)
        try:
            safe_extract(archive, extract_dir)
        except SafeExtractError as e:
            raise _FetchError(f"safe_extract 拒绝: {e}", "extract_rejected") from e

    root = _locate_skill_root(extract_dir)
    if root == extract_dir:
        # 无包裹目录：根即技能根，重命名为 slug（U-01 以 root.name 校验目录名）
        slug = resolved.slug or _slugify(extract_dir.name)
        final = session_dir / slug
        os.replace(extract_dir, final)
        root = final
    return root, root.name


# ═══════════════════════════════════════════════════════════════
# 阶段 3 scan — 双扫描 + 扫描期哈希基线（TOCTOU 复验用，S5）
# ═══════════════════════════════════════════════════════════════

def _hash_tree(root: Path) -> Dict[str, str]:
    """技能目录文件指纹：常规文件 md5，symlink 记链接目标。"""
    entries: Dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root))
        if p.is_symlink():
            entries[rel] = "link:" + os.readlink(p)
        elif p.is_file():
            digest = hashlib.md5(p.read_bytes()).hexdigest()
            entries[rel] = "md5:" + digest
    return entries


def _verify_tree(root: Path, recorded: Dict[str, str]) -> List[str]:
    current = _hash_tree(root)
    diffs: List[str] = []
    for rel in sorted(set(recorded) | set(current)):
        if rel not in current:
            diffs.append(f"removed: {rel}")
        elif rel not in recorded:
            diffs.append(f"added: {rel}")
        elif recorded[rel] != current[rel]:
            diffs.append(f"modified: {rel}")
    return diffs


# ═══════════════════════════════════════════════════════════════
# 审计表 skill_audit（方案 4.3：install|force_install|blocked|bypass_no_scan）
# ═══════════════════════════════════════════════════════════════

_AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS skill_audit (
    audit_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id   TEXT NOT NULL,
    action     TEXT NOT NULL,
    risk       TEXT DEFAULT '',
    rules      TEXT DEFAULT '',
    source     TEXT DEFAULT '',
    detail     TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_skill_audit_skill ON skill_audit(skill_id, created_at);
"""

_audit_ready = False


def _ensure_audit_table() -> None:
    global _audit_ready
    if _audit_ready:
        return
    from zenskill.core.database import db
    db.executescript(_AUDIT_DDL)
    _audit_ready = True


def audit_install(skill_id: str, action: str, *, risk: str = "", rules: str = "",
                  source: str = "", detail: Optional[Dict[str, Any]] = None) -> None:
    """写审计行；审计失败仅 debug 日志，不影响安装语义。"""
    try:
        _ensure_audit_table()
        from zenskill.core.database import db
        db.execute(
            "INSERT INTO skill_audit (skill_id, action, risk, rules, source, detail) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (skill_id, action, risk, rules, source,
             json.dumps(detail or {}, ensure_ascii=False)),
        )
    except Exception:
        logger.debug("skill_audit 写入失败", exc_info=True)


def _rules_summary(security: Dict[str, Any]) -> str:
    return ";".join(sorted({str(f.get("rule_id"))
                            for f in security.get("findings", [])}))


# ═══════════════════════════════════════════════════════════════
# 阶段 5 promote + supply
# ═══════════════════════════════════════════════════════════════

def _promote(skill_root: Path, slug: str, target_dir: Path,
             ts: int) -> Optional[Path]:
    """同名旧技能备份到 .backup/<slug>-<ts>/，os.replace 原子入正式目录。"""
    dest = target_dir / slug
    backup: Optional[Path] = None
    target_dir.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        backup_root = target_dir / ".backup"
        backup_root.mkdir(parents=True, exist_ok=True)
        backup = backup_root / f"{slug}-{ts}"
        os.replace(dest, backup)
    try:
        os.replace(skill_root, dest)
    except OSError:
        if backup is not None:
            os.replace(backup, dest)  # 回滚：新版本未入位时恢复旧技能
        raise
    return backup


def _read_frontmatter(skill_md: Path) -> Dict[str, Any]:
    import yaml
    try:
        content = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}
    try:
        raw = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _supply(slug: str, dest: Path, market: str, source_url: str,
            content_hash: str) -> Tuple[bool, List[str]]:
    """供血三步（全 try/except，失败不污染安装语义）：
    SkillDAO.upsert_spec → skill_router.sync_installed_skills → learning_hint。"""
    errors: List[str] = []
    meta: Dict[str, Any] = {}
    try:
        from zenskill.core.skill_dao import SkillDAO
        from zenskill.core.skill_spec import SkillSpec
        meta = _read_frontmatter(dest / "SKILL.md")
        tags = meta.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        spec = SkillSpec(
            id=slug,
            name=str(meta.get("name") or slug),
            description=str(meta.get("description") or ""),
            category=str(meta.get("category") or "general"),
            difficulty=str(meta.get("difficulty") or "beginner"),
            tags=[str(t) for t in tags],
            version=str(meta.get("version") or "0.1.0"),
            source=market,
            source_url=source_url,
            content_hash=content_hash,
        )
        if not SkillDAO.upsert_spec(spec):
            errors.append("upsert_spec: persist returned False")
    except Exception as e:
        errors.append(f"upsert_spec: {e}")
    try:
        from zenskill.skill_router import skill_router
        skill_router.sync_installed_skills()
    except Exception as e:
        errors.append(f"skill_router.sync: {e}")
    return (not errors), errors


def _build_warnings(security: Dict[str, Any],
                    usability: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    if not security.get("skipped_scan"):
        for f in security.get("findings", []):
            if f.get("severity") in ("medium", "low"):
                warnings.append(f"{f.get('rule_id')}[{f.get('severity')}] "
                                f"{f.get('message')} ({f.get('file')}:{f.get('line')})")
    if not usability.get("skipped_scan"):
        for issue in usability.get("issues", []):
            warnings.append(f"{issue.get('check')}[{issue.get('level')}] "
                            f"{issue.get('message')}")
    return warnings


def _cleanup(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# install — 五阶段编排主入口
# ═══════════════════════════════════════════════════════════════

def install(uri: str, *, no_scan: bool = False, force: bool = False,
            confirm: bool = False,
            target_dir: Optional[Path | str] = None) -> Dict[str, Any]:
    """安全安装管线主入口。

    Args:
        uri: 本地目录/zip/tar 归档路径，或归档 URL（SSRF 校验后下载）
        no_scan: 跳过扫描（仅 CLI 人工路径，审计记 bypass_no_scan）
        force: 覆盖 dangerous/broken 拦截（审计记 force_install）
        confirm: warn/degraded 确认流放行
        target_dir: 安装目标（默认 ~/.agents/skills；测试注入 tmp 目录）

    Returns:
        {ok, skill_id, promoted, security, usability, supply_ok,
         learning_hint, warnings, ...}；拦截时 {ok: false, blocked: true,
        reason, security} 或 {ok: false, need_confirm: true, security}。
    """
    start = time.perf_counter()
    target = Path(target_dir) if target_dir else default_target_dir()
    result: Dict[str, Any] = {"ok": False, "source": str(uri)}
    session_dir: Optional[Path] = None
    resolved: Optional[_Resolved] = None
    try:
        # ① resolve
        resolved = _resolve(uri)
        if resolved is None:
            result["error"] = ("不支持的安装来源（管线支持本地目录/zip/tar 归档"
                               f"/归档 URL）: {uri}")
            return result
        slug = resolved.slug
        ts = int(time.time() * 1000)

        # ② fetch（隔离区）
        session_dir = _make_staging(target, slug, ts)
        skill_root, slug = _fetch(resolved, session_dir)
        result["skill_id"] = slug

        # ③ scan（先记哈希基线再扫描：扫描时点之后的任何改动都会被 ⑤ 复验捕获）
        if no_scan:
            security: Dict[str, Any] = {
                "skill_id": slug, "risk_level": "unknown", "findings": [],
                "scanned_files": 0, "skipped": [], "duration_ms": 0,
                "skipped_scan": True,
            }
            usability: Dict[str, Any] = {
                "skill_id": slug, "status": "unknown", "issues": [],
                "skipped": ["*"], "skipped_scan": True,
            }
            recorded: Optional[Dict[str, str]] = None
        else:
            recorded = _hash_tree(skill_root)
            security = asdict(scan_directory(skill_root))
            usability = asdict(validate_usability(skill_root))
        result["security"] = security
        result["usability"] = usability
        result["staged_ms"] = int((time.perf_counter() - start) * 1000)

        risk = str(security.get("risk_level", "unknown"))
        status = str(usability.get("status", "unknown"))
        rules = _rules_summary(security)

        # ④ gate
        blocked_reason = ""
        if risk == "dangerous" and not force:
            blocked_reason = "dangerous"
        elif status == "broken" and not force:
            blocked_reason = "usability_broken"
        if blocked_reason:
            audit_install(slug, "blocked", risk=risk, rules=rules,
                          source=str(uri),
                          detail={"reason": blocked_reason, "force": force})
            result.update(blocked=True, promoted=False, reason=blocked_reason)
            return result

        if (risk == "warn" or status == "degraded") and not (confirm or force):
            audit_install(slug, "need_confirm", risk=risk, rules=rules,
                          source=str(uri),
                          detail={"risk": risk, "usability": status})
            result.update(need_confirm=True, promoted=False)
            return result

        # TOCTOU 复验（S5）：promote 前哈希与扫描期基线一致
        if recorded is not None:
            changed = _verify_tree(skill_root, recorded)
            if changed:
                audit_install(slug, "blocked", risk=risk, rules=rules,
                              source=str(uri),
                              detail={"reason": "toctou_modified",
                                      "changed": changed[:10]})
                result.update(blocked=True, promoted=False,
                              reason="toctou_modified", changed=changed[:10])
                return result

        content_hash = hashlib.md5(
            json.dumps(recorded or {}, sort_keys=True).encode()).hexdigest()

        # ⑤ promote + supply
        backup = _promote(skill_root, slug, target, ts)
        supply_ok, supply_errors = _supply(slug, target / slug,
                                           resolved.market, str(uri),
                                           content_hash)
        action = ("bypass_no_scan" if no_scan
                  else "force_install" if force else "install")
        audit_install(slug, action, risk=risk, rules=rules, source=str(uri),
                      detail={"force": force, "no_scan": no_scan,
                              "supply_ok": supply_ok,
                              "backup": str(backup) if backup else None})
        result.update(
            ok=True, skill_id=slug, promoted=True, market=resolved.market,
            method="pipeline", target=str(target / slug),
            backup=str(backup) if backup else None,
            supply_ok=supply_ok, supply_errors=supply_errors,
            learning_hint={"tool": "learning_path_start", "skill_id": slug},
            warnings=_build_warnings(security, usability),
            elapsed_ms=int((time.perf_counter() - start) * 1000),
        )
        return result
    except _FetchError as e:
        sid = resolved.slug if resolved else ""
        audit_install(sid or "unknown", "blocked", source=str(uri),
                      detail={"reason": e.kind, "error": str(e)})
        result.update(skill_id=sid, blocked=True, reason=e.kind,
                      error=str(e), promoted=False)
        return result
    except Exception as e:
        logger.exception("install pipeline failed: %s", uri)
        result.update(error=f"{type(e).__name__}: {e}", promoted=False)
        return result
    finally:
        if session_dir is not None:
            _cleanup(session_dir)


# ═══════════════════════════════════════════════════════════════
# MCP 契约纯函数（供 registry 注册；评审 S1：不暴露 no_scan）
# ═══════════════════════════════════════════════════════════════

def mcp_install(args: Dict[str, Any]) -> Dict[str, Any]:
    """MCP skill_install：uri/force/confirm；no_scan 即使传入也被忽略（S1）。"""
    uri = str(args.get("uri") or args.get("source") or "").strip()
    if not uri:
        return {"ok": False, "error": "uri required"}
    return install(
        uri,
        force=bool(args.get("force", False)),
        confirm=bool(args.get("confirm", False)),
        target_dir=args.get("target_dir") or None,
    )


def mcp_scan(args: Dict[str, Any]) -> Dict[str, Any]:
    """MCP skill_scan：skill_id 缺省扫全部已装；返回 {total, dangerous, warn,
    safe, details(top 20，危险优先)}，每条含双扫描结论。"""
    target = Path(args.get("target_dir") or default_target_dir())
    skill_id = str(args.get("skill_id") or "").strip()
    empty = {"total": 0, "dangerous": 0, "warn": 0, "safe": 0, "details": []}
    if skill_id:
        dirs = [target / skill_id] if (target / skill_id).is_dir() else []
    elif target.is_dir():
        dirs = sorted(d for d in target.iterdir()
                      if d.is_dir() and not d.name.startswith("."))
    else:
        return empty

    counts = {"dangerous": 0, "warn": 0, "safe": 0}
    details: List[Dict[str, Any]] = []
    for d in dirs:
        sec = scan_directory(d)
        usa = validate_usability(d)
        counts[sec.risk_level] = counts.get(sec.risk_level, 0) + 1
        details.append({
            "skill_id": d.name,
            "risk_level": sec.risk_level,
            "usability": usa.status,
            "rules": sorted({f.rule_id for f in sec.findings}),
            "findings_count": len(sec.findings),
        })
    order = {"dangerous": 0, "warn": 1, "safe": 2}
    details.sort(key=lambda x: (order.get(x["risk_level"], 9), x["skill_id"]))
    return {"total": len(dirs), **counts, "details": details[:20]}
