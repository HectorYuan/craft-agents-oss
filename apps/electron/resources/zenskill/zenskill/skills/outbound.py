"""W5 技能发布/部署出站表面 — MCP 契约纯函数（skill_export / skill_deploy）。

方案 docs/skill_market_integration_plan.md §7.1 W5 行：
- skill_export {skills?, format?}   → read；清单内容直接返回不落盘
- skill_deploy {skill_id, platform} → write；platform 白名单 + 沙箱确认流

写安全分层（评审对齐）：deploy 是外发写操作，但确认流不在契约层执行——
返回体恒带 confirm_required=True，提示主会话把它注册为 WRITE 工具
（runtime/permission 的 classify_tool + PERMISSION_MATRIX 在 RESTRICTED
模式走确认；registry _WRITE_TOOLS_EXACT 命中写缓存清理）。

目标注入：所有写路径经 args.skills_dir / args.target_root 注入
（直通 DeployAdapter 的 skills_dir / deploy_root 构造参数）；缺省才落
真实目录（~/.zenskill/skills 与各平台 default_deploy_root，codex 写
~/.codex/skills、opencode 写 ~/.config/opencode/skills）。测试必须传 tmp。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..platforms.deploy import discover_skill, get_deploy_adapter, load_skill_manifest

# 部署白名单：与 platforms.deploy.DEPLOY_ADAPTERS 对齐（drift 由测试守护）。
# installer 的 9 平台中仅这四个是部署型；coze/pip/claude 等是安装型，不外发。
DEPLOYABLE_PLATFORMS: Tuple[str, ...] = ("local", "codex", "cursor", "opencode")

SUPPORTED_EXPORT_FORMATS: Tuple[str, ...] = ("json",)

_SKILL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def default_skills_dir() -> Path:
    """技能源目录缺省值（运行时求值）。

    ~/.agents/skills 是安装管线 promote 目标（338 技能实际所在，
    与 skill_tools.DEFAULT_SKILLS_DIRS 一致）；旧目录作回退。
    """
    primary = Path.home() / ".agents" / "skills"
    if primary.is_dir():
        return primary
    return Path.home() / ".zenskill" / "skills"


# ═══════════════════════════════════════════════════════════════
# skill_export — read，清单内容直接返回（agent 拿去做发布准备）
# ═══════════════════════════════════════════════════════════════

def mcp_skill_export(args: Dict[str, Any]) -> Dict[str, Any]:
    """MCP skill_export：{skills?, format?, skills_dir?}。

    - skills: skill_id（安装目录名）过滤列表，缺省导出全部已装
    - format: v1 仅 "json"
    - skills_dir: 技能源目录注入（测试/程序化用，缺省 ~/.zenskill/skills）

    不落盘：清单内容直接随返回体给出。
    过滤命中但目录里没有的 id 记入 missing（不视为失败——导出动作本身成功）。

    Returns:
        {ok, count, format, manifest: [...], skills_dir, missing?}
        异常结构化为 {ok: False, error}。
    """
    args = args or {}
    fmt = str(args.get("format") or "json").strip().lower()
    if fmt not in SUPPORTED_EXPORT_FORMATS:
        return {"ok": False, "error": (
            f"unsupported format: {fmt} "
            f"(v1 supports: {', '.join(SUPPORTED_EXPORT_FORMATS)})")}

    try:
        skills_dir = (Path(args["skills_dir"])
                      if args.get("skills_dir") else default_skills_dir())
        if not skills_dir.is_dir():
            return {"ok": False,
                    "error": f"skills_dir not found: {skills_dir}",
                    "skills_dir": str(skills_dir)}

        wanted = _normalize_skill_filter(args.get("skills"))
        entries, matched = _collect_export_entries(skills_dir, wanted)

        body: Dict[str, Any] = {
            "ok": True,
            "count": len(entries),
            "format": fmt,
            "manifest": entries,
            "skills_dir": str(skills_dir),
        }
        if wanted is not None:
            body["missing"] = sorted(wanted - matched)
        return body
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _normalize_skill_filter(raw: Any) -> Optional[Set[str]]:
    """skills 参数归一化为 id 集合；未传/空返回 None（= 全量）。"""
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = [raw]
    ids = {str(s).strip() for s in raw if str(s).strip()}
    return ids or None


def _collect_export_entries(
    skills_dir: Path, wanted: Optional[Set[str]]
) -> Tuple[List[Dict[str, Any]], Set[str]]:
    """按目录名（skill_id）收集导出条目，返回 (条目列表, 命中的目录名集合)。

    exporter.py 不在本次可改边界内且无过滤参数；条目由其构建函数产出
    （与公开 API export_installed_skills 同源），过滤只能借道目录名。
    """
    from . import exporter

    entries: List[Dict[str, Any]] = []
    matched: Set[str] = set()
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir() or child.name in matched:
            continue
        if wanted is not None and child.name not in wanted:
            continue
        manifest = exporter._load_manifest(child)
        if manifest is None:
            continue
        matched.add(child.name)
        entry = exporter._build_export_entry(child, manifest)
        entry.setdefault("skill_id", child.name)
        entries.append(entry)
    return entries, matched


# ═══════════════════════════════════════════════════════════════
# skill_deploy — write，平台白名单；dry_run 只校验不写
# ═══════════════════════════════════════════════════════════════

def mcp_skill_deploy(args: Dict[str, Any]) -> Dict[str, Any]:
    """MCP skill_deploy：{skill_id, platform, force?, dry_run?, skills_dir?, target_root?}。

    - platform ∈ DEPLOYABLE_PLATFORMS 白名单
    - dry_run=True（默认 False）只做前置校验（技能存在/清单可加载/平台合法/
      目标路径解析），不产生任何写入
    - target_root: 部署目标目录注入（直通 DeployAdapter.deploy_root）——
      缺省落平台真实目录，测试与程序化调用必须传 tmp
    - force=True: 目标已有部署时抑制覆盖警告（适配器语义本就覆盖重部署）
    - confirm_required 恒为 True：registry 权限层注册提示（WRITE 分类、
      沙箱确认流），契约层自身不做确认

    Returns:
        {ok, skill_id, platform, deployed_to?, dry_run?, trigger?,
         warnings?, confirm_required: True}
        skill 不存在 / 平台不在白名单 / 参数缺失 → 结构化 {ok: False, error}。
    """
    args = args or {}
    result: Dict[str, Any] = {"confirm_required": True}
    skill_id = str(args.get("skill_id") or "").strip()
    platform = str(args.get("platform") or "").strip().lower()
    dry_run = bool(args.get("dry_run", False))
    force = bool(args.get("force", False))

    if not skill_id:
        return {**result, "ok": False, "error": "skill_id required"}
    if not _SKILL_ID_RE.match(skill_id):
        return {**result, "ok": False,
                "error": f"invalid skill_id: {skill_id!r} "
                         "(路径分量注入防护)"}
    if not platform:
        return {**result, "ok": False, "error": "platform required",
                "deployable_platforms": list(DEPLOYABLE_PLATFORMS)}
    if platform not in DEPLOYABLE_PLATFORMS:
        return {**result, "ok": False,
                "error": f"unsupported platform: {platform}",
                "deployable_platforms": list(DEPLOYABLE_PLATFORMS)}

    try:
        skills_dir = (Path(args["skills_dir"]) if args.get("skills_dir")
                      else default_skills_dir())
        skill_path = discover_skill(skill_id, skills_dir)
        if skill_path is None:
            return {**result, "ok": False,
                    "error": f"skill not found: {skill_id}",
                    "skill_id": skill_id, "platform": platform}

        manifest = load_skill_manifest(skill_path)
        if not manifest:
            return {**result, "ok": False,
                    "error": f"failed to load skill manifest: {skill_id}",
                    "skill_id": skill_id, "platform": platform}

        target_root = Path(args["target_root"]) if args.get("target_root") else None
        adapter = get_deploy_adapter(
            platform, skills_dir=skills_dir, deploy_root=target_root)
        target = adapter.target_dir(skill_id)

        warnings: List[str] = []
        if target.exists() and not force:
            warnings.append(
                f"target already deployed, deploy overwrites it "
                f"(pass force=true to acknowledge): {target}")

        if dry_run:
            return {**result, "ok": True, "skill_id": skill_id,
                    "platform": platform, "dry_run": True,
                    "deployed_to": str(target),
                    "skill_path": str(skill_path),
                    "trigger": adapter.trigger_hint,
                    "warnings": warnings}

        install_result = adapter.install(skill_id)
        if not install_result.success:
            return {**result, "ok": False, "error": install_result.message,
                    "skill_id": skill_id, "platform": platform,
                    "warnings": warnings}

        result.update(ok=True, skill_id=skill_id, platform=platform,
                      dry_run=False,
                      deployed_to=install_result.skill_path or str(target),
                      trigger=adapter.trigger_hint, warnings=warnings)
        return result
    except Exception as e:
        return {**result, "ok": False, "error": f"{type(e).__name__}: {e}",
                "skill_id": skill_id, "platform": platform}
