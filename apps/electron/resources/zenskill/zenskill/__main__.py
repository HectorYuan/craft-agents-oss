"""
ZenSkill CLI 命令行入口

Usage:
    python -m zenskill                    - 默认显示成长概览
    python -m zenskill --version          - 显示版本
    python -m zenskill memory add "内容" --tags "tag1,tag2"
    python -m zenskill memory list
    python -m zenskill skill status
    python -m zenskill skill list
    python -m zenskill reflect trigger
    python -m zenskill growth             - 显示成长状态（默认）
    python -m zenskill growth status      - 显示五维能力雷达
    python -m zenskill growth insight     - 显示智能洞察报告
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Optional, Callable, Any

# 导入核心模块
from .core.paths import SkillStateManager, atomic_write_json, atomic_write_text, file_lock, get_user_data_dir, get_data_layout, get_zenloop_dir, ensure_data_dirs, normalize_tags
from .cli_utils import output as cli_output, write_output

# ── 纯字符串版本（供 _text() 内使用，替代打印版 CLI 工具）──────────
def _str_section(title: str, emoji: str = "", phase: str = "") -> str:
    """section_blank 的字符串版本"""
    tag = f" — Phase {phase}" if phase else ""
    return f"\n  {emoji} {title}{tag}\n  {'═' * 62}"

def _str_box_header(title: str, emoji: str = "") -> str:
    """box_header 的字符串版本（返回头行，不含缩进）"""
    line = f"  ┌─ {emoji} {title} " if emoji else f"  ┌─ {title} "
    return "\n" + line + "─" * max(0, 58 - len(line) + 1)

def _str_box_footer() -> str:
    """box_footer 的字符串版本"""
    return f"  └{'─' * 60}"

# 版本信息（与 __init__.py 同步
__title__ = "ZenSkill"
__version__ = "2.7.1"
__version_info__ = (1, 9, 0)
__author__ = "ZenSkill Team"


# ═══════════════════════════════════════════════════════════════════
# Runtime v2.0 — 技能链 / 升级 / 版本 (Phase 12.5 + 13.0)
# ═══════════════════════════════════════════════════════════════════

def _runtime_storage_dir():
    """获取 Runtime 存储目录 ~/.zenskill/profiles/{active}/runtime/"""
    from .core.paths import get_user_data_dir
    d = get_user_data_dir() / "runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ═══════════════════════════════════════════════════════
# model 命令处理 — 参考 ModelSwitcher
# ═══════════════════════════════════════════════════════



from .cli.reflect import generate_reflection_report  # noqa: E402 (向后兼容 re-export)
from .cli.growth import cmd_growth_status  # noqa: E402
from .cli.collector import _run_light_pipeline  # noqa: E402


def cmd_default_overview(args: argparse.Namespace) -> None:
    """默认概览命令 - 显示成长状态 + 洞察摘要"""
    # 先显示五维能力雷达
    cmd_growth_status(args)

    # 如果有数据，追加洞察摘要
    from zenskill.systems.visualization.insight_engine import GrowthInsightEngine

    engine = GrowthInsightEngine(args.skill_id)
    snapshots = engine.metrics_store.get_all_snapshots()

    if len(snapshots) >= 2:
        latest = snapshots[-1]
        composite = latest.ability_scores.get('composite', 0)
        result = {
            "snapshot_count": len(snapshots),
            "composite_score": composite,
            "skill_id": args.skill_id,
        }
        cli_output(result, args, text=lambda: (
            f"\n💡 快速洞察:\n"
            f"   📊 综合能力: {composite} 分\n"
            f"   📈 历史采样: {len(snapshots)} 个采样点\n"
            f"   💡 使用 'growth insight' 查看完整洞察报告"
        ))


def cmd_info(args: argparse.Namespace) -> None:
    """显示系统信息"""
    layout = get_data_layout()

    mgr = SkillStateManager(args.skill_id)
    state = mgr.load()
    result = {
        "version": __version__,
        "data_dir": layout.get('user_data_dir', ''),
        "skill_count": 1,
        "level": state.get('level', 'NOVICE'),
        "usage_count": state.get('usage_count', 0),
        "config": layout,
    }

    def _text():
        lines = [f"ℹ️  ZenSkill 系统信息", "=" * 60]
        lines.append(f"   版本: {__version__}")
        for k, v in layout.items():
            if v:
                lines.append(f"   {k}: {v}")
        lines.append(f"\n   当前境界: {state.get('level', 'NOVICE')}")
        lines.append(f"   使用次数: {state.get('usage_count', 0)} 次")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_package_build(args: argparse.Namespace) -> None:
    """构建技能包"""
    from .skill_package import SkillPackage
    from .cli_utils import section_blank, box_header, box_footer

    sp = SkillPackage()
    result = sp.build(args.skill_id, output=getattr(args, 'output', None))

    def _text():
        lines = []
        section_blank("技能包构建", "📦", phase="9T")
        box_header(f"构建成功: {result['skill_id']}")
        lines.append(f"  │  输出: {result['output_path']}")
        lines.append(f"  │  大小: {result['size_bytes'] / 1024:.1f} KB")
        lines.append(f"  │  内容: {', '.join(result['contents'])}")
        box_footer()
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_package_validate(args: argparse.Namespace) -> None:
    """验证技能包"""
    from .skill_package import SkillPackage
    from .cli_utils import section_blank, box_header, box_footer

    sp = SkillPackage()
    result = sp.validate(args.path)

    def _text():
        lines = []
        section_blank("技能包验证", "🔍", phase="9T")
        box_header(f"{'✅ 有效' if result['valid'] else '❌ 无效'}")
        if result.get("meta"):
            m = result["meta"]
            lines.append(f"  │  名称: {m.get('name', '?')}")
            lines.append(f"  │  版本: {m.get('version', '?')}")
        for err in result.get("errors", []):
            lines.append(f"  │  ❌ {err}")
        for warn in result.get("warnings", []):
            lines.append(f"  │  ⚠️ {warn}")
        box_footer()
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_package_install(args: argparse.Namespace) -> None:
    """安装技能包"""
    from .skill_package import SkillPackage
    from .cli_utils import section_blank, box_header, box_footer

    sp = SkillPackage()
    result = sp.install(args.path)

    def _text():
        lines = []
        section_blank("技能包安装", "📥", phase="9T")
        if result["success"]:
            box_header(f"✅ 安装成功: {result['name']}")
            lines.append(f"  │  路径: {result['path']}")
        else:
            box_header(f"❌ 安装失败")
            for err in result["errors"]:
                lines.append(f"  │  {err}")
        box_footer()
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_package_export(args: argparse.Namespace) -> None:
    """导出技能为分享包"""
    from .skill_package import SkillPackage
    from .cli_utils import section_blank, box_header, box_footer

    sp = SkillPackage()
    result = sp.export(args.skill_id, output=getattr(args, 'output', None))

    def _text():
        lines = []
        section_blank("技能包导出", "📤", phase="9T")
        box_header("导出成功")
        lines.append(f"  │  输出: {result['output_path']}")
        lines.append(f"  │  大小: {result['size_bytes'] / 1024:.1f} KB")
        box_footer()
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_package_list(args: argparse.Namespace) -> None:
    """列出已安装的技能包"""
    from .skill_package import SkillPackage
    from .cli_utils import section_blank, box_header, box_footer

    sp = SkillPackage()
    packages = sp.list_packages()

    def _text():
        lines = []
        section_blank("已安装技能包", "📦", phase="9T")
        if not packages:
            lines.append("  [dim]暂无已安装的技能包[/dim]")
            lines.append("")
            return "\n".join(lines)
        box_header(f"共 {len(packages)} 个")
        for p in packages:
            lines.append(f"  │  • {p.get('name', '?')}  v{p.get('version', '?')}")
            if p.get("description", ""):
                lines.append(f"  │    {p['description'][:60]}")
        box_footer()
        lines.append("")
        return "\n".join(lines)

    cli_output({"packages": packages, "count": len(packages)}, args, text=_text)


def cmd_package_rollback(args: argparse.Namespace) -> None:
    """回滚技能包到安装前快照 (P2-3)"""
    from .skill_package import SkillPackage

    sp = SkillPackage()
    if args.list_backups:
        backups = sp.list_backups(args.name)
        cli_output(
            {"name": args.name, "backups": backups},
            args,
            text=lambda: "\n".join(
                [f"\n  {args.name} 可用快照（新在前）:"] +
                [f"    - {b}" for b in backups] + [""]
            ) if backups else f"\n  {args.name} 无可用快照\n",
        )
        return

    result = sp.rollback(args.name, snapshot_id=args.snapshot)
    cli_output(
        result,
        args,
        text=lambda: (
            f"回滚成功: {args.name} → {result.get('snapshot')}"
            if result.get("success")
            else f"回滚失败: {'; '.join(result.get('errors', []))}"
        ),
    )
    if not result.get("success"):
        raise SystemExit(1)


# ================================================================
# 9U: 技能搜索与发现命令
# ================================================================

def _search_markets_cli(args: argparse.Namespace, market: str) -> None:
    """市场搜索（P3-2: GitHub / skills.sh / npm / PyPI / ClawHub）"""
    from .skills.universal_installer import search_markets, universal_installer

    if market == "all":
        entries = search_markets(args.query, top_k=args.top_k)
    else:
        adapter = universal_installer._adapters.get(market)
        if adapter is None:
            available = ["all"] + sorted(universal_installer._adapters.keys())
            print(f"未知市场: {market}; 可用: {', '.join(available)}")
            raise SystemExit(1)
        entries = adapter.search(args.query, top_k=args.top_k)

    from .render import table

    if entries:
        table(
            ["ID", "市场", "热度", "说明"],
            [[e.skill_id, e.market, str(e.downloads or "-"),
              (e.description or "-")[:56]] for e in entries],
            title=f"市场搜索: {args.query} @ {market}",
        )
    else:
        print("  未找到匹配技能（市场可能需要 token 配置或网络不可达）")

    cli_output(
        {
            "query": args.query,
            "market": market,
            "total": len(entries),
            "results": [{
                "skill_id": e.skill_id,
                "name": e.name,
                "market": e.market,
                "description": e.description[:100],
                "url": e.url,
                "downloads": e.downloads,
            } for e in entries],
        },
        args,
        text=lambda: "",
    )


def cmd_browse(args: argparse.Namespace) -> None:
    """浏览市场热门技能（skills.sh 排行榜，无 token 自动回退 skillhub.cn 榜单）"""
    from .render import table
    from .skills.market_adapters import SkillHubAdapter, SkillsShAdapter

    entries = SkillsShAdapter().trending(view=args.view, top_k=args.top_k)
    source = "skills.sh"

    if not entries:
        entries = SkillHubAdapter().top(top_k=args.top_k)
        source = "skillhub.cn"

    if entries:
        table(
            ["ID", "名称", "热度", "来源"],
            [[e.skill_id, e.name[:24], str(e.downloads or "-"), e.author or "-"]
             for e in entries],
            title=f"热门技能榜 ({source} · {args.view})",
        )
    else:
        print("  暂无数据:")
        print("    - skills.sh: API 需要 OIDC token（配置 SKILLS_SH_TOKEN 环境变量）")
        print("    - skillhub.cn: 网络不可达或无数据")
        print("  备选: zenskill search <关键词> --market github  # GitHub 技能仓库搜索（匿名可用）")

    cli_output(
        {"view": args.view, "source": source, "total": len(entries),
         "results": [{"skill_id": e.skill_id, "downloads": e.downloads} for e in entries]},
        args,
        text=lambda: "",
    )


def cmd_search(args: argparse.Namespace) -> None:
    """搜索技能"""
    market = getattr(args, 'market', None)
    if market:
        _search_markets_cli(args, market)
        return

    from .skills.search_engine import SkillSearchEngine
    from .render import table

    engine = SkillSearchEngine()
    engine.build_index()
    results = engine.search(
        args.query,
        category=getattr(args, 'category', None),
        difficulty=getattr(args, 'difficulty', None),
        tags=getattr(args, 'tags', None),
        top_k=args.top_k,
    )

    if results:
        table(
            ["名称", "分类", "难度", "评分", "匹配"],
            [[r.skill.name, r.skill.category, r.skill.difficulty,
              f"{r.score:.0%}", ", ".join(r.matched_terms[:3]) if r.matched_terms else "-"]
             for r in results],
            title=f"搜索: {args.query}"
        )
    else:
        print("  未找到匹配的技能")

    result_data = [{
        "skill_id": r.skill.skill_id,
        "name": r.skill.name,
        "score": round(r.score, 3),
        "category": r.skill.category,
        "difficulty": r.skill.difficulty,
        "description": r.skill.description[:100],
        "usage_count": r.skill.usage_count,
        "level": r.skill.level,
    } for r in results]
    cli_output({"query": args.query, "total": len(results), "results": result_data}, args, text=lambda: "")


def cmd_discover(args: argparse.Namespace) -> None:
    """发现推荐技能"""
    from .skills.search_engine import SkillSearchEngine

    engine = SkillSearchEngine()
    engine.build_index()
    owned = getattr(args, 'owned', None)
    owned_list = owned.split(",") if owned else []
    results = engine.discover(owned_skills=owned_list, top_k=args.top_k)

    def _text():
        lines = []
        lines.append(f"\n  💡 技能推荐发现 — Phase 9U")
        lines.append(f"  {'═' * 62}")
        lines.append("")
        if not results:
            lines.append("  [dim]暂无推荐[/dim]")
            lines.append("")
            return "\n".join(lines)
        lines.append(f"  ┌─ 推荐 {len(results)} 个技能 {'─' * 40}")
        for i, r in enumerate(results, 1):
            s = r.skill
            reason = r.matched_terms[0] if r.matched_terms else "推荐技能"
            lines.append(f"  │  {i}. 📚 {s.name}")
            lines.append(f"  │     {s.category} | {s.difficulty}")
            lines.append(f"  │     💡 {s.description[:60]}")
            lines.append(f"  │     📌 {reason}")
            lines.append(f"  │")
        lines.append(f"  └{'─' * 60}")
        lines.append("")
        return "\n".join(lines)

    result_data = [{
        "skill_id": r.skill.skill_id,
        "name": r.skill.name,
        "score": round(r.score, 3),
        "category": r.skill.category,
        "difficulty": r.skill.difficulty,
        "description": r.skill.description[:100],
        "reason": r.matched_terms[0] if r.matched_terms else "",
    } for r in results]
    cli_output({"total": len(results), "results": result_data}, args, text=_text)


def cmd_trending(args: argparse.Namespace) -> None:
    """热门趋势技能"""
    from .skills.search_engine import SkillSearchEngine

    engine = SkillSearchEngine()
    engine.build_index()
    results = engine.trending(top_k=args.top_k)

    def _text():
        lines = []
        lines.append(f"\n  🔥 热门技能趋势 — Phase 9U")
        lines.append(f"  {'═' * 62}")
        lines.append("")
        if not results:
            lines.append("  [dim]暂无数据[/dim]")
            lines.append("")
            return "\n".join(lines)
        lines.append(f"  ┌─ 热门排行 Top {len(results)} {'─' * 40}")
        for i, r in enumerate(results, 1):
            s = r.skill
            medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}."
            usage_str = f"使用 {s.usage_count} 次" if s.usage_count else "新技能"
            lines.append(f"  │  {medal} {s.name}")
            lines.append(f"  │     {s.category} | {s.difficulty} | {usage_str} | 境界: {s.level}")
            lines.append(f"  │")
        lines.append(f"  └{'─' * 60}")
        lines.append("")
        return "\n".join(lines)

    result_data = [{
        "rank": i,
        "skill_id": r.skill.skill_id,
        "name": r.skill.name,
        "score": round(r.score, 3),
        "category": r.skill.category,
        "difficulty": r.skill.difficulty,
        "usage_count": r.skill.usage_count,
        "level": r.skill.level,
    } for i, r in enumerate(results, 1)]
    cli_output({"total": len(results), "results": result_data}, args, text=_text)


def cmd_path(args: argparse.Namespace) -> None:
    """推荐学习路径"""
    from .skills.search_engine import SkillSearchEngine

    engine = SkillSearchEngine()
    engine.build_index()
    owned = getattr(args, 'owned', None)
    owned_list = owned.split(",") if owned else []
    result = engine.path(args.goal, owned_skills=owned_list, top_k=args.steps)

    def _text():
        lines = []
        lines.append(f"\n  🗺️ 学习路径: {result['goal']} — Phase 9U")
        lines.append(f"  {'═' * 62}")
        lines.append("")
        steps = result["steps"]
        if not steps:
            lines.append("  [dim]暂无可用路径[/dim]")
            lines.append("")
            return "\n".join(lines)
        lines.append(f"  ┌─ 共 {len(steps)} 步 · 预计 {result['estimated_total_interactions']} 次交互 {'─' * 30}")
        for i, s in enumerate(steps, 1):
            marker = "✅" if s["skill_id"] in owned_list else f"{i}."
            diff_icon = {"beginner": "🟢", "intermediate": "🟡", "advanced": "🔴", "expert": "🟣"}
            icon = diff_icon.get(s["difficulty"], "⚪")
            lines.append(f"  │  {marker} {icon} {s['name']}")
            lines.append(f"  │     {s['difficulty']} | ~{s['estimated_interactions']}次交互")
            lines.append(f"  │     {s['description'][:70]}")
            lines.append(f"  │")
        lines.append(f"  └{'─' * 60}")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


# ================================================================
# 9V: 技能质量评级命令
# ================================================================

def cmd_rating(args: argparse.Namespace) -> None:
    """查看技能评级"""
    from .skills.rating_engine import SkillRatingEngine, DIMENSION_NAMES, DIMENSION_ICONS
    from .skills.search_engine import SkillSearchEngine

    engine = SkillRatingEngine()
    skill_id = args.skill_id

    # 先尝试加载已有评级
    rating_data = engine.get_rating(skill_id)
    if rating_data and not getattr(args, 'refresh', False):
        pass  # 使用缓存
    else:
        # 获取技能名称
        se = SkillSearchEngine()
        entry = se.get_entry(skill_id)
        name = entry.name if entry else skill_id
        rating = engine.rate(skill_id, name)
        rating_data = rating.to_dict()

    def _text():
        lines = []
        lines.append(f"\n  📊 技能评级: {rating_data.get('skill_name', skill_id)} — Phase 9V")
        lines.append(f"  {'═' * 62}")
        lines.append("")
        d = rating_data
        lines.append(f"  {d['star_icon']}  {d['star_level']}  (综合: {d['overall']}/5)")
        lines.append("")
        lines.append(f"  ┌─ 各维度评分 {'─' * 45}")
        for dim_key, dim_info in d.get("dimensions", {}).items():
            score = dim_info["score"]
            weight = dim_info["weight"]
            name = dim_info["name"]
            icon = dim_info["icon"]
            bar_w = 30
            filled = int(score * bar_w)
            bar = "█" * filled + "░" * (bar_w - filled)
            lines.append(f"  │  {icon} {name:12s} [{bar}] {score:.0%}  (权重 {weight:.0%})")
        lines.append(f"  └{'─' * 60}")
        lines.append("")
        if d.get("user_rating_count", 0) > 0:
            lines.append(f"  ⭐ 用户评分: {d['user_rating_avg']}/5 ({d['user_rating_count']} 次)")
        lines.append(f"  更新: {d.get('updated_at', '?')}")
        lines.append("")
        return "\n".join(lines)

    cli_output(rating_data, args, text=_text)


def cmd_rate(args: argparse.Namespace) -> None:
    """给技能打分"""
    from .skills.rating_engine import SkillRatingEngine

    engine = SkillRatingEngine()
    rating = engine.add_user_rating(
        args.skill_id,
        args.score,
        comment=getattr(args, 'comment', ''),
        user=getattr(args, 'user', 'anonymous'),
    )
    data = rating.to_dict()

    def _text():
        d = data
        lines = [
            f"\n  ⭐ 评分已提交: {d.get('skill_name', args.skill_id)}",
            f"  {'═' * 62}",
            "",
            f"  你的评分: {'⭐' * int(args.score)} {args.score}/5",
            f"  当前平均: {d['user_rating_avg']}/5 ({d['user_rating_count']} 次)",
            f"  综合评级: {d['star_icon']} {d['star_level']} ({d['overall']}/5)",
            "",
        ]
        return "\n".join(lines)

    cli_output(data, args, text=_text)


def cmd_ratings_list(args: argparse.Namespace) -> None:
    """列出所有已评级的技能"""
    from .skills.rating_engine import SkillRatingEngine

    engine = SkillRatingEngine()
    ratings = engine.list_ratings()

    def _text():
        lines = [
            f"\n  📊 已评级技能列表 — Phase 9V",
            f"  {'═' * 62}",
            "",
        ]
        if not ratings:
            lines.append("  [dim]暂无评级数据[/dim]")
            lines.append("")
            return "\n".join(lines)
        lines.append(f"  ┌─ 共 {len(ratings)} 个技能 {'─' * 45}")
        for r in ratings:
            lines.append(f"  │  {r['star_icon']} {r['name']:25s} {r['overall']}/5  [{r['star_level']}]")
        lines.append(f"  └{'─' * 60}")
        lines.append("")
        return "\n".join(lines)

    cli_output({"count": len(ratings), "ratings": ratings}, args, text=_text)


def cmd_ratings_rate_all(args: argparse.Namespace) -> None:
    """批量评级所有已知技能"""
    from .skills.rating_engine import SkillRatingEngine
    from .cli_utils import section_blank, box_header, box_footer

    engine = SkillRatingEngine()
    results = engine.rate_all()

    def _text():
        lines = [
            f"\n  📊 批量评级完成 — Phase 9V",
            f"  {'═' * 62}",
            "",
        ]
        if not results:
            lines.append("  [dim]无可评级的技能[/dim]")
            lines.append("")
            return "\n".join(lines)
        lines.append(f"  ┌─ 评级了 {len(results)} 个技能 {'─' * 40}")
        for r in sorted(results, key=lambda x: x["overall"], reverse=True):
            lines.append(f"  │  {r['star_icon']} {r['name']:25s} {r['overall']}/5  [{r['star_level']}]")
        lines.append(f"  └{'─' * 60}")
        lines.append("")
        return "\n".join(lines)

    cli_output({"count": len(results), "ratings": results}, args, text=_text)


# ================================================================
# Phase E: 技能生态命令
# ================================================================

def cmd_install(args: argparse.Namespace) -> None:
    """统一技能安装"""
    from .skills.universal_installer import install_skill
    from .render import ok, fail as print_fail

    # 解析 --from-url / --from-file
    source = args.source
    if not source:
        from_url = getattr(args, 'from_url', None)
        from_file = getattr(args, 'from_file', None)
        if from_url:
            source = from_url
        elif from_file:
            source = f"file://{from_file}"

    if not source:
        print_fail("请提供安装来源", "zenskill install <来源>")
        return

    result = install_skill(source)

    if result.get("success"):
        ok("技能安装成功",
           f"{result.get('source', '?')} → {result.get('skill_id', '?')} "
           f"({result.get('method', '?')})")
    else:
        print_fail("安装失败", result.get("error", "unknown"))

    # JSON 兼容
    cli_output(result, args, text=lambda: "")


# ── Phase U0E: uninstall ──

def cmd_uninstall(args: argparse.Namespace) -> None:
    """卸载技能"""
    from .skills.universal_installer import uninstall_skill
    from .render import ok, fail as print_fail

    skill_id = args.skill_id
    force = getattr(args, "force", False)

    # 确认提示 (非 force)
    if not force and sys.stdin.isatty():
        try:
            confirm = input(f"  确认卸载 {skill_id}? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if confirm not in ("y", "yes"):
            print("  已取消")
            return

    result = uninstall_skill(skill_id, force=True)

    def _text():
        if result.get("success"):
            lines = [f"\n🗑️ 卸载完成 — {result['name']}", f"{'═' * 40}"]
            for item in result.get("cleaned", []):
                lines.append(f"  ✅ 清理: {item}")
            return "\n".join(lines)
        return f"\n❌ {result.get('error', 'unknown')}"

    cli_output(result, args, text=_text)


# ── Phase U3D: content 命令 ──

def cmd_content_from_text(args: argparse.Namespace) -> None:
    """从文本创建技能"""
    from .skills.content_extractor import ContentToSkillConverter
    from .render import ok, fail as print_fail

    converter = ContentToSkillConverter()
    spec = converter.convert_from_text(args.text, title=getattr(args, 'title', ''))

    if spec and spec.save():
        ok("技能已创建", f"{spec.id} — {spec.name}")
    else:
        print_fail("创建失败", "请检查文本内容")

    cli_output(spec.to_dict() if spec else {}, args, text=lambda: "")


def cmd_content_from_url(args: argparse.Namespace) -> None:
    """从 URL 创建技能"""
    from .skills.content_extractor import ContentToSkillConverter
    from .render import ok, fail as print_fail

    converter = ContentToSkillConverter()
    spec = converter.convert_from_url(args.url)

    if spec and spec.save():
        ok("技能已创建", f"{spec.id} — {spec.name}")
    else:
        print_fail("创建失败", f"无法从 {args.url} 提取内容")

    cli_output(spec.to_dict() if spec else {}, args, text=lambda: "")


def cmd_content_from_file(args: argparse.Namespace) -> None:
    """从文件创建技能"""
    from .skills.content_extractor import ContentToSkillConverter
    from .render import ok, fail as print_fail

    converter = ContentToSkillConverter()
    spec = converter.convert_from_file(args.path)

    if spec and spec.save():
        ok("技能已创建", f"{spec.id} — {spec.name}")
    else:
        print_fail("创建失败", f"无法从 {args.path} 提取内容")

    cli_output(spec.to_dict() if spec else {}, args, text=lambda: "")


# ── Phase S: SkillSpec 命令处理 ──

def cmd_spec_validate(args: argparse.Namespace) -> None:
    """验证 skill.toml"""
    from .core.skill_spec import SkillSpec

    if not args.path:
        cli_output({"error": "请提供 skill.toml 路径"}, args,
                   text=lambda: "❌ 用法: zenskill spec validate <path>\n")
        return

    try:
        spec = SkillSpec.from_toml(args.path)
    except FileNotFoundError:
        cli_output({"error": f"文件不存在: {args.path}"}, args,
                   text=lambda: f"❌ 文件不存在: {args.path}\n")
        return
    except ImportError:
        cli_output({"error": "缺少 tomllib/tomli. pip install tomli"}, args,
                   text=lambda: "❌ 缺少 TOML 支持: pip install tomli\n")
        return

    errors = spec.validate(stage=args.stage)

    def _text():
        lines = [f"\n📋 SkillSpec 验证 — {args.path}", f"{'═' * 62}"]
        lines.append(f"  阶段: {args.stage}")
        lines.append(f"  ID: {spec.id}")
        lines.append(f"  Name: {spec.name}")
        lines.append(f"  推断阶段: {spec.stage}")
        if errors:
            lines.append(f"\n  ❌ {len(errors)} 个错误:")
            for e in errors:
                lines.append(f"     • {e}")
        else:
            lines.append(f"\n  ✅ 通过 ({args.stage} 阶段)")
        return "\n".join(lines)

    cli_output({"valid": len(errors) == 0, "errors": errors, "spec": spec.to_dict()},
               args, text=_text)


def cmd_spec_export(args: argparse.Namespace) -> None:
    """导出 SkillSpec"""
    from .core.skill_spec import SkillSpec

    spec = SkillSpec.from_db(args.skill_id)
    if spec is None:
        cli_output({"error": f"技能不存在: {args.skill_id}"}, args,
                   text=lambda: f"❌ 技能不存在: {args.skill_id}\n")
        return

    if args.format == "toml":
        if args.output:
            spec.to_toml(args.output)
            content = f"Exported to {args.output}"
        else:
            content = spec.to_json()  # fallback if no toml available
    else:
        content = spec.to_json()

    def _text():
        lines = [f"\n📤 SkillSpec 导出 — {spec.id}", f"{'═' * 62}"]
        lines.append(f"  名称: {spec.name}")
        lines.append(f"  阶段: {spec.stage}")
        lines.append(f"  格式: {args.format}")
        if args.output:
            lines.append(f"  输出: {args.output}")
        else:
            lines.append(f"\n{content}")
        return "\n".join(lines)

    cli_output({"spec": spec.to_dict(), "format": args.format}, args, text=_text)


def cmd_spec_inspect(args: argparse.Namespace) -> None:
    """查看 SkillSpec 详情"""
    from .core.skill_spec import SkillSpec
    from .render import p, fail as print_fail

    spec = SkillSpec.from_db(args.skill_id)
    if spec is None:
        print_fail("技能不存在", args.skill_id)
        return

    # 使用统一渲染引擎
    p.section(spec.name, icon=spec.icon)
    p.card(spec.id, [
        ("显示名", spec.display_name or spec.name),
        ("描述", spec.description or "—"),
    ], icon=spec.icon)
    p.card("版本与分类", [
        ("版本", f"v{spec.version}"),
        ("Spec", f"v{spec.spec_version}"),
        ("分类", f"{spec.category} · {spec.skill_type.value} · {spec.difficulty}"),
        ("标签", ", ".join(spec.tags) if spec.tags else "—"),
    ])
    p.card("来源", [
        ("作者", spec.author or "—"),
        ("许可", spec.license or "—"),
        ("来源", spec.source),
        ("市场", spec.source_market or "—"),
        ("URL", spec.source_url or "—"),
    ])
    p.bar([
        ("熟练度", spec.proficiency_weight, 1.0),
        ("稳定性", spec.stability_weight, 1.0),
        ("满意度", spec.satisfaction_weight, 1.0),
        ("响应力", spec.responsiveness_weight, 1.0),
        ("记忆力", spec.memory_weight, 1.0),
    ], colors=["dim_proficiency", "dim_stability", "dim_satisfaction",
               "dim_responsiveness", "dim_memory"])
    p.card("运行时", [
        ("等级", spec.level),
        ("调用", str(spec.usage_count)),
        ("成功率", f"{spec.success_rate:.0%}"),
        ("适配器", spec.adapter or "N/A"),
        ("入口", spec.entry_point or "N/A"),
        ("能力数", str(len(spec.capabilities))),
    ])

    # JSON 输出保留完整数据
    cli_output(spec.to_dict(), args, text=lambda: "")


# ── Phase E2: GitHub 命令处理 ──

def cmd_github_info(args: argparse.Namespace) -> None:
    """预览 GitHub 仓库信息"""
    from .skills.github_installer import preview_github_skill

    parts = args.repo.split("/")
    if len(parts) != 2:
        cli_output({"error": "格式: owner/repo"}, args,
                   text=lambda: "❌ 格式: zenskill github info owner/repo\n")
        return

    owner, repo = parts
    result = preview_github_skill(owner, repo)

    def _text():
        lines = [f"\n🐙 GitHub 仓库分析 — {owner}/{repo} (Phase E2)", f"{'═' * 62}"]
        if "error" in result:
            lines.append(f"\n  ❌ {result['error']}")
            return "\n".join(lines)

        a = result.get("analysis", {})
        lines.append(f"  语言: {a.get('primary_language', 'N/A')}")
        if a.get("languages"):
            langs = ", ".join(f"{k} {v:.0%}" for k, v in a.get("languages", {}).items())
            lines.append(f"  分布: {langs}")
        lines.append(f"  文件: {a.get('total_files', 0)} · 行数: {a.get('total_lines', 0):,}")
        lines.append(f"  许可证: {a.get('license', 'N/A')}")
        lines.append(f"  CI/CD: {'✅' if a.get('has_ci') else '❌'} · 测试: {'✅' if a.get('has_tests') else '❌'}")

        deps = a.get("dependencies", [])
        if deps:
            lines.append(f"  依赖: {', '.join(deps[:8])}")

        prompts = result.get("prompts_preview", [])
        if prompts:
            lines.append(f"\n  📝 Agent 提示词 ({len(prompts)}):")
            for p in prompts:
                lines.append(f"     [{p['role']}] {p['title']}")

        readme = result.get("readme_preview", "")
        if readme:
            lines.append(f"\n  📖 README 预览:")
            lines.append(f"     {readme[:200]}...")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_market_search(args: argparse.Namespace) -> None:
    """跨市场搜索"""
    from .skills.universal_installer import search_markets

    results = search_markets(args.query, top_k=getattr(args, 'top_k', 10))

    def _text():
        lines = [f"\n🌐 跨市场搜索: {args.query} — Phase E", f"{'═' * 62}", ""]
        if not results:
            lines.append("  [dim]未找到匹配的技能[/dim]")
        else:
            lines.append(f"  ┌─ {len(results)} 个结果 {'─' * 45}")
            for r in results:
                lines.append(f"  │  {r.name:25s} [{r.market}] {r.rating or '-'}")
        lines.append(f"  └{'─' * 60}")
        lines.append("")
        return "\n".join(lines)

    cli_output({"query": args.query, "total": len(results),
                "results": [{"name": r.name, "market": r.market, "rating": r.rating} for r in results]},
               args, text=_text)
# Phase D: 数据库管理命令
# ================================================================

def cmd_db(args: argparse.Namespace) -> None:
    """数据库管理"""
    from .core.database import db

    action = getattr(args, 'db_action', 'stats')

    if action == 'init':
        result = db.init_schema()
        cli_output(result, args, text=lambda: (
            f"🗄️ 数据库初始化\n{'═' * 60}\n"
            f"  路径: {db.path}\n"
            f"  状态: {result['message']}\n"
        ))
    elif action == 'stats':
        stats = db.get_stats()
        cli_output(stats, args, text=lambda: (
            f"\n🗄️ 数据库统计 — Phase D\n{'═' * 62}\n\n"
            f"  路径: {stats['path']}\n"
            f"  大小: {stats['size_mb']} MB\n"
            f"  表数: {len(stats['tables'])}\n"
            + "".join(
                f"    {t['name']:35s} {t['rows']} rows\n"
                for t in stats['tables'] if t['rows'] > 0
            )
        ))
    elif action == 'vacuum':
        db.vacuum()
        cli_output({"ok": True}, args, text=lambda: "🗜️ 数据库已压缩\n")
    elif action == 'backup':
        dest = db.backup()
        cli_output({"ok": True, "path": str(dest)}, args, text=lambda: (
            f"💾 备份完成: {dest}\n"
        ))
    elif action == 'migrate':
        from .core.migrate_to_sqlite import migrate_all
        dry_run = getattr(args, 'dry_run', False)
        archive = getattr(args, 'archive', False)
        result = migrate_all(dry_run=dry_run, archive=archive)
        cli_output(result, args, text=lambda: (
            f"\n🔄 数据迁移{' (预览)' if dry_run else ''} — Phase D\n{'═' * 62}\n\n"
            + "".join(f"  {k}: {v}\n" for k, v in result["summary"].items())
            + (f"\n  ⚠️ 错误: {len(result['errors'])}" if result["errors"] else "")
            + ("\n  (dry-run 模式，未实际修改)\n" if dry_run else "\n  ✅ 迁移完成\n")
        ))


def cmd_cross_report(args: argparse.Namespace) -> None:
    """全局成长报告"""
    from zenskill.systems.collaboration.cross_insight import CrossSkillInsightEngine

    engine = CrossSkillInsightEngine()
    report = engine.generate_global_report()
    cli_output({"report": report}, args, text=lambda: report)


def cmd_cross_insights(args: argparse.Namespace) -> None:
    """查看跨技能洞察"""
    from zenskill.systems.collaboration.cross_insight import CrossSkillInsightEngine

    engine = CrossSkillInsightEngine()
    insights = engine.generate_cross_insights()
    type_names = {
        "comparison": "对比分析", "pattern": "模式发现",
        "bottleneck": "共同瓶颈", "synergy": "协同效应", "milestone": "里程碑",
    }

    def _format_insights():
        lines = ["💡 跨技能洞察", "=" * 60, ""]
        if not insights:
            lines.append("   暂无跨技能洞察（需要至少 2 个已注册的技能）\n")
            lines.append("💡 使用 'zenskill graph register' 注册多个技能")
            return "\n".join(lines)
        for i, insight in enumerate(insights, 1):
            type_name = type_names.get(insight.type, insight.type)
            severity_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(insight.severity, "⚪")
            lines.append(f"   {i}. {severity_emoji} [{type_name}] {insight.title}")
            lines.append(f"      {insight.content}")
            lines.append(f"      影响技能: {len(insight.affected_skills)} 个\n")
        return "\n".join(lines)

    cli_output({
        "count": len(insights),
        "insights": [{"type": i.type, "title": i.title, "content": i.content,
                       "severity": i.severity, "affected_count": len(i.affected_skills)} for i in insights],
    }, args, text=_format_insights)


def cmd_cross_compare(args: argparse.Namespace) -> None:
    """跨技能对比分析"""
    from zenskill.systems.collaboration.cross_insight import CrossSkillInsightEngine

    engine = CrossSkillInsightEngine()
    result = engine.compare_skills(args.skill_ids)
    cli_output({"skill_ids": args.skill_ids, "comparison": result}, args, text=lambda: result)


def cmd_eco_dashboard(args: argparse.Namespace) -> None:
    """技能生态系统仪表盘"""
    from zenskill.systems.collaboration.dashboard import SkillEcosystemDashboard

    dashboard = SkillEcosystemDashboard()
    report = dashboard.generate_dashboard()
    cli_output({"dashboard": report}, args, text=lambda: report)


def cmd_eco_heatmap(args: argparse.Namespace) -> None:
    """成长热力图详细报告"""
    from zenskill.systems.collaboration.dashboard import SkillEcosystemDashboard

    dashboard = SkillEcosystemDashboard()
    report = dashboard.generate_heatmap_report()
    cli_output({"heatmap": report}, args, text=lambda: report)


def cmd_eco_health(args: argparse.Namespace) -> None:
    """生态系统健康度评估"""
    from zenskill.systems.collaboration.dashboard import SkillEcosystemDashboard

    dashboard = SkillEcosystemDashboard()
    health = dashboard._calculate_ecosystem_health()
    level_names = {"excellent": "优秀", "good": "良好", "fair": "一般", "poor": "待改善"}
    level_icons = {"excellent": "🟢", "good": "🟡", "fair": "🟠", "poor": "🔴"}
    level_name = level_names.get(health["level"], "未知")
    level_icon = level_icons.get(health["level"], "⚪")
    suggestions = {
        "poor": "增加技能使用频率，注册更多相关技能形成网络",
        "fair": "加强技能间的关联训练，提升整体均衡度",
        "good": "继续保持，探索更多技能组合的可能性",
        "excellent": "恭喜! 你的技能生态系统非常健康，保持领先!",
    }

    def _format_health():
        lines = ["🏥 技能生态系统健康度评估", "=" * 60, ""]
        lines.append(f"   整体评级: {level_icon} {level_name} ({health['overall_score']:.1f}/100)\n")
        lines.append(f"   📈 成长均衡度: {health['balance_score']:.1f}/100")
        lines.append(f"   🔗 连接密度: {health['connectivity_score']:.1f}/100")
        lines.append(f"   📊 活跃度评分: {health['activity_score']:.1f}/100\n")
        lines.append(f"   💡 建议: {suggestions.get(health['level'], '')}")
        return "\n".join(lines)

    cli_output(health, args, text=_format_health)


def _inject_model_switcher_keys():
    """从 model-switcher DB 读取 API key 注入环境变量（与 Craft 共享同一份 key）。"""
    import os
    import sqlite3
    from pathlib import Path

    db_path = Path.home() / ".model-switch" / "modelswitcher.db"
    if not db_path.exists():
        return

    # 已有环境变量则跳过
    key_map = {
        "deepseek": "DEEPSEEK_API_KEY",
        "mimo": "MIMO_API_KEY",
    }
    need_inject = any(not os.environ.get(v) for v in key_map.values())
    if not need_inject:
        return

    try:
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT ka.pool_name, es.var_value FROM key_accounts ka "
            "JOIN env_vars es ON ka.key_env = es.var_name "
            "WHERE ka.pool_name IN ('deepseek', 'mimo') AND ka.status = 'active'"
        ).fetchall()
        conn.close()

        for pool_name, key_value in rows:
            env_var = key_map.get(pool_name)
            if env_var and key_value and not os.environ.get(env_var):
                os.environ[env_var] = key_value
    except Exception:
        pass


def cmd_tui(args: argparse.Namespace) -> None:
    """启动交互式终端界面 (TUI) -- 自动降级 + 依赖安装提示"""
    import asyncio

    _inject_model_switcher_keys()

    mode = getattr(args, "mode", "interactive")
    if mode == "c":
        mode = "command"
    elif mode == "i":
        mode = "interactive"

    # 一键安装依赖
    if getattr(args, "install_deps", False):
        from .tui.deps import install_all_deps, check_deps
        print("  ⏳ 安装 TUI 依赖...")
        results = install_all_deps()
        for pkg, ok in results.items():
            print(f"  {'✅' if ok else '❌'} {pkg}")
        deps = check_deps()
        print(f"\n  ℹ️  当前可用: {[k for k, v in deps.items() if v]}")
        return

    # 检测依赖
    from .tui.deps import check_deps, get_missing

    deps = check_deps()
    missing = get_missing(deps)

    if missing and mode not in ("command",):
        # 显示依赖状态 + 提供一键安装
        from .tui.deps import render_dep_status, prompt_install_interactive
        print(render_dep_status(deps, rich_available=deps["rich"]))

        # 非交互模式直接提示
        if not sys.stdin.isatty():
            if missing:
                print(f"  💡 安装依赖: pip install {' '.join(missing)}")
            sys.exit(1)

        # 交互模式：让用户选择
        choice = prompt_install_interactive()
        if choice is None:
            sys.exit(0)
        if choice == "plain":
            pass  # 继续往下走 PlainTUI
        elif choice in ("textual", "rich"):
            # 依赖已安装，重新检测
            deps = check_deps()

    # 指定模式: 命令模式用 CommandMode (Rich fallback)
    if mode == "command":
        try:
            from .tui.command_mode import CommandMode
            CommandMode().run()
            return
        except ImportError:
            pass

    # 指定模式: rich 用 ZenRichTUI
    if mode in ("rich", "interactive", "textual"):
        if deps.get("rich_app"):
            try:
                from .tui.rich_app import ZenRichTUI
                print(f"\n  ℹ️  TUI 模式: Rich App (Rich + prompt_toolkit)")
                use_agent = getattr(args, "use_agent", None)
                if use_agent is None:
                    use_agent = os.environ.get("ZENSKILL_TUI_AGENT", "1") == "1"
                app = ZenRichTUI(use_agent=use_agent)
                asyncio.run(app.run())
                return
            except Exception as e:
                print(f"\n  ⚠️  Rich App 启动失败: {e}，尝试降级...")

    # 自动选择最佳后端 (降级链)
    try:
        from .tui import get_best_tui
        TUIClass = get_best_tui()
        print(f"\n  ℹ️  TUI 模式: {TUIClass.__name__}")
        if TUIClass.__name__ == "ZenRichTUI":
            asyncio.run(TUIClass().run())
        else:
            TUIClass().run()
    except ImportError as e:
        print(f"\n  ❌ TUI 不可用: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n  ❌ TUI 启动失败: {e}")
        sys.exit(1)


def cmd_chat(args: argparse.Namespace) -> None:
    """AI 对话 — 默认流式输出"""
    import asyncio
    import sys
    from .core.llm_provider import get_llm_provider, ChatMessage

    # 如果指定了 --model，临时切换 Provider
    provider = None
    if args.model:
        from .core.llm_config import get_model_info
        from .core.llm_provider import (
            DeepSeekLLMProvider, VolcEngineLLMProvider, QwenLLMProvider,
            AnthropicLLMProvider, OpenAILLMProvider, SimpleLLMProvider,
        )
        info = get_model_info(args.model)
        if info:
            p = info["provider"]
            provider = {"deepseek": DeepSeekLLMProvider, "volc": VolcEngineLLMProvider,
                        "qwen": QwenLLMProvider, "anthropic": AnthropicLLMProvider,
                        "openai": OpenAILLMProvider, "mock": SimpleLLMProvider}.get(p, SimpleLLMProvider)(model=args.model)
        else:
            provider = get_llm_provider()
    else:
        provider = get_llm_provider()

    async def _stream_round(provider, user_input):
        """流式一轮对话，显示推理 + 回答"""
        has_stream = hasattr(provider, "stream_chat")
        if not has_stream:
            return await provider.simple_chat(user_input)

        messages = [ChatMessage(role="user", content=user_input)]
        in_reasoning = False
        reasoning_buf = ""
        answer_buf = ""
        REASONING_SHOW_MAX = 120  # 推理最多显示字符数
        last_reasoning_flush = 0

        async for chunk in provider.stream_chat(messages):
            ctype = chunk.get("type", "content")
            ctext = chunk.get("content", "")
            if ctype == "reasoning":
                if not in_reasoning:
                    in_reasoning = True
                    sys.stdout.write("\n\033[2m💭 思考中...\n")
                    sys.stdout.flush()
                reasoning_buf += ctext
                # 只显示最近一段推理（滚动窗口），每 10 字符刷新一次
                if len(reasoning_buf) - last_reasoning_flush >= 10:
                    last_reasoning_flush = len(reasoning_buf)
                    disp = reasoning_buf[-REASONING_SHOW_MAX:]
                    if len(reasoning_buf) > REASONING_SHOW_MAX:
                        disp = "..." + disp
                    # 用 \r 回到行首覆盖
                    sys.stdout.write(f"\r\033[2m{disp}\033[K\033[0m")
                    sys.stdout.flush()
            elif ctype == "content":
                if in_reasoning:
                    # 推理结束，换行
                    sys.stdout.write("\n\033[0m\n🤖 ")
                    sys.stdout.flush()
                    in_reasoning = False
                sys.stdout.write(ctext)
                sys.stdout.flush()
                answer_buf += ctext
        return answer_buf

    def _do_stream(provider, message):
        return asyncio.run(_stream_round(provider, message))

    if args.message is None:
        # 交互模式
        print()
        print(f"💬 ZenSkill AI 对话（模型: {provider.get_model_name()}）")
        print("=" * 80)
        print("流式对话模式 | 输入 exit 退出")
        print()

        try:
            while True:
                user_input = input("👤 You: ").strip()
                if user_input.lower() in ["exit", "quit", "q"]:
                    break
                if not user_input:
                    continue

                _do_stream(provider, user_input)
                print("\n")

        except KeyboardInterrupt:
            print("\n")
        print("👋 再见！")

    else:
        # 单次对话
        message = args.message
        provider_name = provider.get_model_name()

        if getattr(args, 'json_output', False):
            # JSON 模式：静默收集（重定向流式输出）
            import io, contextlib
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    answer = _do_stream(provider, message)
                result = {"ok": True, "message": message, "model": provider_name, "response": answer}
            except Exception as e:
                result = {"ok": False, "message": message, "model": provider_name, "error": str(e)}
            cli_output(result, args, text=lambda: result.get("response", ""))
        else:
            # 文本模式：流式输出
            print()
            print(f"👤 You: {message}")
            print(f"🤖 模型: {provider_name}")
            try:
                _do_stream(provider, message)
                print()
            except Exception as e:
                print(f"\n❌ 失败: {e}")


# ====================================================================
# 用户镜像命令
# ====================================================================

def _cmd_internal_record_event(args: argparse.Namespace) -> None:
    """内部命令：记录事件（供 hook 调用）"""
    import json
    from .mirroring.event_collector import EventCollector
    from .mirroring.models import EventType

    collector = EventCollector()

    try:
        event_type = EventType(args.event_type)
    except (ValueError, KeyError):
        event_type = EventType.SKILL_EXEC

    try:
        context = json.loads(args.context) if args.context else {}
    except (json.JSONDecodeError, ValueError):
        context = {}

    success = args.success.lower() in ("true", "1", "yes", "t")

    collector.record(
        event_type=event_type,
        skill_id=args.skill_id,
        action=args.action,
        success=success,
        duration_ms=args.duration,
        context=context,
    )

    # ── 桥接: 同步更新 SkillStateManager（Issue #2 修复）──
    from .core.paths import SkillStateManager
    mgr = SkillStateManager(args.skill_id)
    mgr.record_episode(
        action=f"{event_type.value if hasattr(event_type, 'value') else str(event_type)}: {args.action}",
        content=json.dumps(context) if context else "",
        success=success,
        duration_ms=args.duration or 0,
    )


# ====================================================================
# 智能体生态采集器命令
# ====================================================================



# ═══════════════════════════════════════════════════════════════
# Hook 管理命令
# ═══════════════════════════════════════════════════════════════

def _get_notify_context() -> dict:
    """获取通知引擎的上下文"""
    import json, time
    from pathlib import Path
    sf = Path.home() / ".zenskill" / "session" / "current.json"
    ctx = {"tool_count": 0, "elapsed_min": 0, "level": "", "old_level": ""}
    if sf.exists():
        s = json.loads(sf.read_text())
        ctx["tool_count"] = s.get("tool_count", 0)
        ctx["elapsed_min"] = (time.time() - s.get("started", time.time())) / 60
    try:
        from .core.paths import SkillStateManager
        zs = SkillStateManager("zenskill-core").load()
        ctx["level"] = zs.get("level", "")
        ctx["old_level"] = zs.get("_old_level", "")
    except Exception:
        pass
    return ctx


def _register_collectors():
    """注册所有内置采集器（幂等）"""
    from .mirroring.collectors import collector_registry
    if collector_registry.count > 0:
        return

    from .mirroring.collectors.claude_code import (
        ClaudeHistoryCollector, ClaudeMemoryCollector,
        ClaudePlansCollector, ClaudeTasksCollector, CoreSettingsCollector,
        ClaudeSessionCollector, ClaudeFileHistoryCollector, ClaudeShellSnapshotCollector,
    )
    from .mirroring.collectors.zenskill import (
        ZenskillEventCollector, ZenskillMemoryCollector, ZenskillZenloopCollector,
    )

    collector_registry.register(ClaudeHistoryCollector())
    collector_registry.register(ClaudeMemoryCollector())
    collector_registry.register(ClaudePlansCollector())
    collector_registry.register(ClaudeTasksCollector())
    collector_registry.register(CoreSettingsCollector())
    collector_registry.register(ClaudeSessionCollector())
    collector_registry.register(ClaudeFileHistoryCollector())
    collector_registry.register(ClaudeShellSnapshotCollector())
    collector_registry.register(ZenskillEventCollector())
    collector_registry.register(ZenskillMemoryCollector())
    collector_registry.register(ZenskillZenloopCollector())


def cmd_agent_discover(args: argparse.Namespace) -> None:
    """智能发现适合任务的代理 (9P)"""
    from .cli_utils import section_blank, box_header, box_footer, bar_chart
    from .agent.capability_matcher import (
        CapabilityMatcher, TaskSpecification, format_match_result,
    )
    from .agent.protocol import MessageBus
    from .agent.evaluator import AgentEvaluator
    from .agent.shared_memory import SharedMemory

    bus = MessageBus()
    evaluator = AgentEvaluator()
    memory = SharedMemory()
    matcher = CapabilityMatcher(bus, evaluator, memory)

    task = TaskSpecification(
        task_type=args.task_type,
        domain=args.domain,
        difficulty=args.difficulty,
    )

    results = matcher.find_best_agents(task, top_k=args.top_k)

    def _text():
        lines = []
        section_blank("代理能力发现", "🤖", phase="9P")
        box_header("任务需求", "📋")
        lines.append(f"  │  类型: {task.task_type}")
        lines.append(f"  │  领域: {task.domain or '通用'}")
        lines.append(f"  │  难度: {task.difficulty}")
        box_footer()

        if not results:
            lines.append("")
            box_header("未找到匹配代理", "🔍")
            lines.append("  │  [dim]没有注册的 Agent 能满足当前任务需求[/dim]")
            lines.append("  │  [dim]请先注册 Agent 再重试[/dim]")
            box_footer()
        else:
            lines.append("")
            box_header(f"最佳匹配 (Top-{len(results)})", "🏆")
            for r in results:
                lines.append("")
                lines.append(format_match_result(r))
            box_footer()

            # 权重说明
            lines.append("")
            box_header("匹配权重", "⚖️")
            lines.append("  │  技能相关性  25% · 能力水平  20%")
            lines.append("  │  历史表现    25% · 可用性    15%")
            lines.append("  │  协作契合    15%")
            box_footer()

        lines.append("")
        return "\n".join(lines)

    cli_output({"task": task.__dict__, "results": [r.to_dict() for r in results]},
               args, text=_text)


def safe_execute(func: Callable[..., Any], args: argparse.Namespace) -> int:
    """安全执行命令，捕获异常并给出修复建议"""
    import json as _json

    try:
        func(args)
        return 0
    except KeyboardInterrupt:
        print("\n\n👋 用户中断，退出")
        return 130
    except FileNotFoundError as e:
        print(f"\n❌ 文件不存在: {e}")
        return 2
    except PermissionError as e:
        print(f"\n❌ 权限不足: {e}")
        return 3
    except _json.JSONDecodeError as e:
        print(f"\n❌ 数据文件 JSON 解析失败: {e}")
        print(f"💡 建议运行: zenskill doctor state   (扫描损坏文件)")
        print(f"💡 建议运行: zenskill doctor repair  (修复可恢复文件)")
        return 5
    except UnicodeDecodeError as e:
        print(f"\n❌ 数据文件编码错误: {e}")
        print(f"💡 建议运行: zenskill doctor state   (扫描损坏文件)")
        print(f"💡 建议运行: zenskill doctor repair  (修复可恢复文件)")
        return 6
    except ValueError as e:
        print(f"\n❌ 参数错误: {e}")
        return 4
    except OSError as e:
        msg = str(e).lower()
        print(f"\n❌ 文件系统错误: {e}")
        if "lock" in msg or "timeout" in msg or "超时" in msg:
            print(f"💡 可能存在并发进程冲突，稍后重试")
        elif "corrupt" in msg or "损坏" in msg:
            print(f"💡 建议运行: zenskill doctor repair --dry-run")
        return 7
    except Exception as e:
        msg = str(e).lower()
        print(f"\n❌ 执行失败: {e}")
        if any(k in msg for k in ("json", "decode", "parse", "corrupt", "损坏", "jsondecode")):
            print(f"💡 建议运行: zenskill doctor state   (扫描数据完整性)")
        if getattr(args, 'debug', False):
            import traceback
            traceback.print_exc()
        return 1


# ═══════════════════════════════════════════════════════════════════
# 8.7G-L: GTD CLI 命令 (v2.1.0)
# ═══════════════════════════════════════════════════════════════════

def cmd_gtd_dashboard(args: argparse.Namespace) -> None:
    """GTD 综合仪表盘"""
    from .systems.gtd import InboxEngine, ActionEngine, ProjectEngine, EnergyEngine

    inbox = InboxEngine()
    actions = ActionEngine()
    projects = ProjectEngine()
    energy = EnergyEngine()

    inbox_info = inbox.check_backlog()
    action_stats = actions.stats()
    proj_info = projects.dashboard()
    energy_status = energy.status()

    result = {
        "inbox": inbox_info,
        "actions": action_stats,
        "projects": proj_info,
        "energy": energy_status,
    }

    def _text():
        lines = [
            "", f"  🎯 GTD 仪表盘",
            f"  {'═' * 62}", "",
            f"  📥 Inbox:       {inbox_info['unprocessed']} 未处理 "
            + ("⚠️ 积压!" if inbox_info['alert'] else "✅"),
            f"  📋 Actions:     {action_stats['pending']} pending / {action_stats['done']} done"
            + (f" | {action_stats['overdue']} overdue ⚠️" if action_stats['overdue'] else ""),
            f"  📦 Projects:    {proj_info['active']} active / {proj_info['done']} done"
            + (f" | {proj_info['stale']} stale" if proj_info['stale'] else ""),
            f"  ⚡ Energy:      {energy_status['current_energy']}/{energy_status['max_energy']}"
            + f" ({energy_status['pct']:.0%}) {energy_status['level_icon']}",
            "",
        ]
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_gtd_weekly_review(args: argparse.Namespace) -> None:
    """GTD 周回顾"""
    from .systems.gtd import InboxEngine, ActionEngine, ProjectEngine, IncubatingEngine
    from .systems.gtd.zenloop_bridge import GTDZenLoopBridge

    inbox = InboxEngine()
    actions = ActionEngine()
    projects = ProjectEngine()
    incubating = IncubatingEngine()

    # 清零 Inbox
    inbox_count = inbox.count()
    # 项目进度
    proj_dash = projects.dashboard()
    # 孵化产出
    inc_stats = incubating.stats()
    # 完成统计
    act_stats = actions.stats()

    # ZenLoop 联动
    bridge = GTDZenLoopBridge()
    zenloop_result = bridge.run_all_cycles()

    result = {
        "inbox_cleared": inbox_count,
        "projects": proj_dash,
        "incubating": inc_stats,
        "actions_weekly": act_stats,
        "zenloop": zenloop_result,
    }

    def _text():
        lines = [
            "", f"  📋 GTD 周回顾",
            f"  {'═' * 62}", "",
            f"  📥 Inbox: 处理 {inbox_count} 条",
            f"  📋 Actions: {act_stats['done']} 完成 (本周)",
            f"  📦 Projects: {proj_dash['active']} active, {proj_dash['stale']} stale",
            f"  📊 完成率: {act_stats['completion_rate']:.0%}",
            f"  🐣 Incubating: {inc_stats['active']} active, {inc_stats['mature']} mature",
            "",
        ]
        if proj_dash['stale']:
            lines.append(f"  ⚠️ 停滞项目 (>7天无进度):")
            for name in proj_dash['stale_projects']:
                lines.append(f"    - {name}")

        # ZenLoop 联动结果
        lines.append(f"\n  🔄 ZenLoop × GTD 联动:")
        for cycle_name, cycle_result in zenloop_result.items():
            msg = cycle_result.get("message", cycle_result.get("error", ""))
            lines.append(f"    {cycle_name}: {msg}")

        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_gtd_migrate(args: argparse.Namespace) -> None:
    """旧系统数据迁移到 GTD"""
    from .systems.gtd.migrate import GTDMigrator

    migrator = GTDMigrator()
    skill_id = getattr(args, "skill_id", "zenskill-core") or "zenskill-core"

    if args.dry_run:
        # 干跑模式：只统计不写入
        result = {"dry_run": True, "skill_id": skill_id, "message": "干跑模式，不执行实际迁移"}
    else:
        result = migrator.migrate_all(skill_id)

    def _text():
        lines = ["", "  🔄 GTD 数据迁移", f"  {'═' * 62}", ""]
        for source, stats in result.items():
            if source in ("migrated_at", "dry_run", "skill_id", "message"):
                continue
            if isinstance(stats, dict):
                migrated = stats.get("migrated", 0)
                skipped = stats.get("skipped", 0)
                total = stats.get("total", 0)
                reason = stats.get("reason", "")
                if reason:
                    lines.append(f"  {source}: 跳过 ({reason})")
                else:
                    lines.append(f"  {source}: {migrated} 迁移 / {skipped} 跳过 / {total} 总计")
        if args.dry_run:
            lines.append(f"\n  ℹ️ {result.get('message', '')}")
        else:
            lines.append(f"\n  ✅ 迁移完成")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_report_weekly(args: argparse.Namespace) -> None:
    """GTD 周报"""
    from .systems.gtd.report import GTDReportEngine

    engine = GTDReportEngine()
    weeks = getattr(args, "weeks", 1) or 1
    data = engine.weekly_report(weeks=weeks)

    fmt = getattr(args, "format", "json")
    if fmt == "markdown" or (not getattr(args, "json_output", False) and fmt != "json"):
        print(engine.format_weekly_markdown(data))
    else:
        cli_output(data, args, text=lambda: engine.format_weekly_markdown(data))


def cmd_report_monthly(args: argparse.Namespace) -> None:
    """GTD 月报"""
    from .systems.gtd.report import GTDReportEngine

    engine = GTDReportEngine()
    months = getattr(args, "months", 1) or 1
    data = engine.monthly_report(months=months)

    fmt = getattr(args, "format", "json")
    if fmt == "markdown" or (not getattr(args, "json_output", False) and fmt != "json"):
        print(engine.format_monthly_markdown(data))
    else:
        cli_output(data, args, text=lambda: engine.format_monthly_markdown(data))


def cmd_health_score(args: argparse.Namespace) -> None:
    """GTD 健康度评分"""
    from .systems.gtd.health import GTDHealthEngine

    engine = GTDHealthEngine()
    days = getattr(args, "days", 30) or 30
    data = engine.compute_health(days=days)

    fmt = getattr(args, "format", "json")
    if fmt == "markdown" or (not getattr(args, "json_output", False) and fmt != "json"):
        print(engine.format_health_markdown(data))
    else:
        cli_output(data, args, text=lambda: engine.format_health_markdown(data))


def cmd_health_annual(args: argparse.Namespace) -> None:
    """年度 GTD 回顾"""
    from .systems.gtd.health import GTDHealthEngine

    engine = GTDHealthEngine()
    year = getattr(args, "year", 0) or 0
    data = engine.annual_review(year=year)

    def _text():
        lines = [
            "", f"  📅 {data['year']} 年度 GTD 回顾",
            f"  {'═' * 62}", "",
            f"  ✅ 完成 Action: {data['actions']['done']}/{data['actions']['total']}",
            f"  📊 完成率: {data['actions']['completion_rate']:.0%}",
            f"  ⏰ 最高效时段: {data['peak_hour']['hour']}时 ({data['peak_hour']['count']}次)",
            "",
        ]
        if data["most_active_projects"]:
            lines.append("  🏆 最活跃项目:")
            for p in data["most_active_projects"][:3]:
                lines.append(f"    - {p['project_id']}: {p['actions']} 个 Action")
        if data["top_contexts"]:
            lines.append("")
            lines.append("  📊 上下文分布:")
            for ctx, count in list(data["top_contexts"].items())[:5]:
                lines.append(f"    - {ctx}: {count}")
        return "\n".join(lines)

    cli_output(data, args, text=_text)


def cmd_health_card(args: argparse.Namespace) -> None:
    """技能成长评分卡"""
    from .systems.gtd.health import GTDHealthEngine

    engine = GTDHealthEngine()
    skill_id = getattr(args, "skill_id", "zenskill-core") or "zenskill-core"
    data = engine.skill_growth_card(skill_id=skill_id)

    def _text():
        grade_emoji = {"S": "🏆", "A": "⭐", "B": "👍", "C": "⚠️", "D": "❌"}
        emoji = grade_emoji.get(data["health_grade"], "")
        lines = [
            "", f"  {emoji} GTD × 技能成长评分卡",
            f"  {'═' * 62}", "",
            f"  技能: {data['skill_id']}",
            f"  健康度: {data['health_score']} ({data['health_grade']})",
            "",
            f"  📋 技能相关 Action: {data['skill_actions']['done']}/{data['skill_actions']['total']} ({data['skill_actions']['ratio']}%)",
            f"  📦 技能相关 Project: {data['skill_projects']['total']} (活跃: {data['skill_projects']['active']})",
            "",
            f"  💡 {data['recommendation']}",
        ]
        return "\n".join(lines)

    cli_output(data, args, text=_text)


def cmd_inbox_add(args: argparse.Namespace) -> None:
    """快速捕获到 Inbox"""
    from .systems.gtd import InboxEngine
    engine = InboxEngine()
    source = getattr(args, 'source', 'cli')
    item = engine.add(args.text, source=source)
    intent = engine.auto_classify(args.text)
    cli_output({
        "ok": True, "id": item.id, "intent": intent, "text": args.text,
    }, args, text=lambda: f"📥 Inbox: {args.text[:60]}  ({intent})")


def cmd_inbox_list(args: argparse.Namespace) -> None:
    """列出 Inbox"""
    from .systems.gtd import InboxEngine
    engine = InboxEngine()
    items = engine.list(status=args.status, limit=args.n)
    result = {
        "count": len(items), "status": args.status,
        "items": [{"id": i.id, "text": i.raw_text, "source": i.source,
                    "created_at": i.created_at, "clarify_result": i.clarify_result}
                  for i in items],
    }

    def _text():
        status_icon = {"unprocessed": "📥", "clarified": "✅", "archived": "📦", "all": "📋"}
        lines = [f"\n{status_icon.get(args.status, '📋')} Inbox ({args.status}): {len(items)} items"]
        for i in items:
            intent = i.clarify_result.get("type", "") if i.clarify_result else ""
            lines.append(f"  [{intent or engine.auto_classify(i.raw_text):10s}] {i.raw_text[:50]}")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_inbox_process(args: argparse.Namespace) -> None:
    """处理 Inbox 项"""
    from .systems.gtd import InboxEngine
    engine = InboxEngine()
    success = engine.clarify(args.item_id, args.type, getattr(args, 'target_id', ''))
    cli_output({"ok": success, "item_id": args.item_id},
               args, text=lambda: f"✅ 已处理: {args.item_id} → {args.type}" if success
               else f"❌ 未找到: {args.item_id}")


def cmd_action_add(args: argparse.Namespace) -> None:
    """添加 Action"""
    from .systems.gtd.action import ActionEngine
    engine = ActionEngine()
    action = engine.add(
        args.title,
        description=getattr(args, 'description', ''),
        contexts=getattr(args, 'context', '').split(',') if getattr(args, 'context', '') else [],
        priority=getattr(args, 'priority', 'P2'),
        energy_required=getattr(args, 'energy', 5),
        due_date=getattr(args, 'due', ''),
        estimated_minutes=getattr(args, 'estimated', 25),
        project_id=getattr(args, 'project', ''),
        skill_id=getattr(args, 'skill_id', ''),
        repeat_rule=getattr(args, 'repeat', ''),
    )
    cli_output({
        "ok": True, "id": action.id, "title": action.title,
        "priority": action.priority, "due_date": action.due_date,
    }, args, text=lambda: f"✅ Action: [{action.priority}] {action.title}")


def cmd_action_list(args: argparse.Namespace) -> None:
    """列出 Actions"""
    from .systems.gtd.action import ActionEngine
    engine = ActionEngine()
    if getattr(args, 'next', False):
        actions = engine.next_actions(limit=args.n)
    else:
        actions = engine.list(
            status=getattr(args, 'status', 'pending'),
            project_id=getattr(args, 'project', ''),
            context=getattr(args, 'context', ''),
            priority=getattr(args, 'priority', ''),
            due_today=getattr(args, 'due_today', False),
            limit=args.n,
        )

    result = {"count": len(actions), "actions": [a.to_dict() for a in actions]}

    def _text():
        label = "Next Actions" if getattr(args, 'next', False) else f"Actions ({getattr(args, 'status', 'pending')})"
        lines = [f"\n📋 {label}: {len(actions)}"]
        for a in actions:
            ctx = f" @{' '.join(a.contexts)}" if a.contexts else ""
            due = f" ⏰{a.due_date[:10]}" if a.due_date else ""
            energy = f" ⚡{a.energy_required}" if a.energy_required else ""
            lines.append(f"  [{a.priority}] {a.title[:50]}{ctx}{due}{energy}")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_action_done(args: argparse.Namespace) -> None:
    """完成 Action"""
    from .systems.gtd.action import ActionEngine
    from .systems.gtd.energy import EnergyEngine
    from .systems.active.achievement_system import AchievementSystem

    engine = ActionEngine()
    action = engine.get(args.action_id)
    success = engine.done(args.action_id, energy_invested=getattr(args, 'energy_invested', 0))
    if not success:
        cli_output({"ok": False, "action_id": args.action_id},
                   args, text=lambda: f"❌ 未找到: {args.action_id}")
        return

    # 成长反馈（与 GUI/agent 路径一致）：能量扣减 + 成就解锁
    extras = []
    try:
        energy = EnergyEngine().status()
        extras.append(f"⚡ 能量 {energy.get('current_energy')}/{energy.get('max_energy')}")
    except Exception:
        pass
    try:
        skill_id = (action.skill_id if action else '') or 'zenskill-core'
        system = AchievementSystem(skill_id)
        new_ids = system.evaluate()['new_unlocks']
        if new_ids:
            titles = [f"{b.icon} {b.title}" for b in system.evaluate()['unlocked']
                      if b.badge_id in new_ids]
            if titles:
                extras.append("🏆 解锁成就：" + "、".join(titles))
    except Exception:
        pass

    title = action.title if action else args.action_id
    cli_output({"ok": True, "action_id": args.action_id},
               args, text=lambda: "✅ Done: " + title
               + ("\n   " + "\n   ".join(extras) if extras else ""))


def cmd_action_delete(args: argparse.Namespace) -> None:
    """删除 Action"""
    from .systems.gtd.action import ActionEngine
    engine = ActionEngine()
    success = engine.delete(args.action_id)
    cli_output({"ok": success}, args,
               text=lambda: f"🗑️ 已删除: {args.action_id}" if success
               else f"❌ 未找到: {args.action_id}")


def cmd_project_create(args: argparse.Namespace) -> None:
    """创建 Project"""
    from .systems.gtd.project import ProjectEngine
    engine = ProjectEngine()
    proj = engine.create(
        args.name,
        outcome=getattr(args, 'outcome', ''),
        skill_id=getattr(args, 'skill_id', ''),
        notes=getattr(args, 'notes', ''),
    )
    cli_output({"ok": True, "id": proj.id, "name": proj.name},
               args, text=lambda: f"📦 Project: {proj.name}" + (
                   f"\n   预期结果: {proj.outcome}" if proj.outcome else ""))


def cmd_project_list(args: argparse.Namespace) -> None:
    """列出 Projects"""
    from .systems.gtd.project import ProjectEngine
    engine = ProjectEngine()
    projects = engine.list(status=getattr(args, 'status', 'active'))
    result = {"count": len(projects), "projects": [p.to_dict() for p in projects]}

    def _text():
        lines = [f"\n📦 Projects ({getattr(args, 'status', 'active')}): {len(projects)}"]
        for p in projects:
            outcome = (p.outcome or "")[:40]
            lines.append(f"  [{p.status:8s}] {p.name:30s} {outcome}")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_project_show(args: argparse.Namespace) -> None:
    """查看 Project 详情"""
    from .systems.gtd.project import ProjectEngine
    engine = ProjectEngine()
    proj = engine.get(args.project_id)
    if not proj:
        cli_output({"ok": False}, args, text=lambda: f"❌ 未找到: {args.project_id}")
        return

    result = proj.to_dict()
    def _text():
        lines = [
            f"\n📦 {proj.name}", f"  ID: {proj.id}",
            f"  期望结果: {proj.outcome or '-'}",
            f"  状态: {proj.status} | 关联技能: {proj.skill_id or '-'}",
            f"  创建: {proj.created_at[:19]}",
        ]
        if proj.next_action_id:
            lines.append(f"  Next Action: {proj.next_action_id}")
        if proj.notes:
            lines.append(f"  备注: {proj.notes}")
        if proj.review_date:
            lines.append(f"  上次 Review: {proj.review_date[:19]}")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_project_templates(args: argparse.Namespace) -> None:
    """列出项目模板"""
    from .systems.gtd.project import ProjectEngine
    engine = ProjectEngine()
    templates = engine.template_list()
    result = {"templates": templates}

    def _text():
        lines = [f"\n📋 Project 模板 ({len(templates)})"]
        for t in templates:
            lines.append(f"  {t['key']:20s} {t['name']:15s} — {t['outcome']}")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_energy_status(args: argparse.Namespace) -> None:
    """能量状态"""
    from .systems.gtd.energy import EnergyEngine
    engine = EnergyEngine(skill_id=args.skill_id)
    s = engine.status()

    def _text():
        bar_w = 30
        filled = int(s['pct'] * bar_w)
        bar = "█" * filled + "░" * (bar_w - filled)
        return (f"\n⚡ Energy: [{bar}] {s['current_energy']}/{s['max_energy']} ({s['pct']:.0%})"
                f"  {s['level_icon']}\n   恢复速度: {s['recovery_rate']:.0f}/h")

    cli_output(s, args, text=_text)


def cmd_energy_advise(args: argparse.Namespace) -> None:
    """能量优化建议"""
    from .systems.gtd.energy import EnergyEngine
    engine = EnergyEngine(skill_id=args.skill_id)
    adv = engine.advise()

    def _text():
        lines = [f"\n⚡ 能量分析", f"  {'═' * 30}",
                 f"  近 7 天消耗: {adv['total_burned_7d']}",
                 f"  高效时段: {adv['peak_hour']}:00"]
        if adv['suggestions']:
            lines.append("")
            for s in adv['suggestions']:
                lines.append(f"  {s}")
        return "\n".join(lines)

    cli_output(adv, args, text=_text)


def cmd_calendar_today(args: argparse.Namespace) -> None:
    """今日日程"""
    from .systems.gtd.calendar import CalendarEngine
    engine = CalendarEngine()
    import time
    today_str = time.strftime("%Y-%m-%d")
    date = getattr(args, 'date', None) or today_str
    events = engine.today() if date == today_str else engine._on_date(date)
    result = {"date": date, "count": len(events),
              "events": [e.to_dict() for e in events]}

    def _text():
        lines = [f"\n📅 {date} ({len(events)} events)"]
        if not events:
            lines.append("  (无日程)")
        for e in events:
            time_str = e.time_str or "全天"
            repeat = " 🔁" if e.repeat_rule else ""
            lines.append(f"  {time_str:5s} {e.title[:45]}{repeat}")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_calendar_week(args: argparse.Namespace) -> None:
    """本周日程"""
    from .systems.gtd.calendar import CalendarEngine
    engine = CalendarEngine()
    week = engine.week()
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    import time
    from datetime import datetime, timedelta
    today = time.strftime("%Y-%m-%d")
    monday = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d")

    total = sum(len(day) for day in week)
    result = {"total": total, "days": [{monday: wd} for monday, wd in
              zip([(datetime.now() - timedelta(days=datetime.now().weekday() - i)).strftime("%Y-%m-%d")
                   for i in range(7)], week)]}

    def _text():
        lines = [f"\n📅 Week ({total} events)"]
        from datetime import datetime, timedelta
        for i, day_events in enumerate(week):
            date = (datetime.now() - timedelta(days=datetime.now().weekday() - i)).strftime("%Y-%m-%d")
            marker = " ←" if date == time.strftime("%Y-%m-%d") else ""
            lines.append(f"  {weekdays[i]} {date}{marker}: {' | '.join(e.title[:20] for e in day_events) or '-'}")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_calendar_add(args: argparse.Namespace) -> None:
    """添加日程"""
    from .systems.gtd.calendar import CalendarEngine
    engine = CalendarEngine()
    event = engine.add(
        args.date, args.title,
        time_str=getattr(args, 'time', ''),
        repeat_rule=getattr(args, 'repeat_rule', ''),
    )
    cli_output({"ok": True, "id": event.id, "date": event.date, "title": event.title},
               args, text=lambda: f"📅 {event.date} {event.time_str} {event.title}" +
               (f" 🔁{event.repeat_rule}" if event.repeat_rule else ""))


# ═══════════════════════════════════════════════════════════════
# ZenTest 命令
# ═══════════════════════════════════════════════════════════════

def cmd_zentest(args: argparse.Namespace) -> None:
    """运行 ZenTest 测试框架"""
    from .zentest.core import ZenTestRunner
    from .zentest.reporters import get_reporter
    from .zentest.coverage import CoverageScanner, get_test_plan_summary

    # ── 覆盖矩阵报告 ──
    if args.coverage:
        scanner = CoverageScanner()
        report = scanner.scan()
        fmt = args.format or "text"
        if fmt == "json":
            print(report.to_json())
        else:
            print(report.to_markdown())
        return

    # ── 测试计划 ──
    if args.plan:
        print(get_test_plan_summary())
        return

    runner = ZenTestRunner()

    if args.smoke or args.quick:
        report = runner.smoke(report_format="silent")
    elif args.category:
        report = runner.run(category=args.category, report_format="silent")
    elif args.module:
        # 按模块过滤 — 暂走全量，后续支持细粒度
        report = runner.run_all(report_format="silent")
        print(f"📦 模块过滤 '{args.module}' 暂不支持细粒度，已运行全量")
    else:
        report = runner.run_all(report_format="silent")

    # 输出报告
    fmt = args.format or "text"
    output = get_reporter(report, fmt).generate()

    if args.output:
        import pathlib
        pathlib.Path(args.output).write_text(output, encoding="utf-8")
        print(f"报告已保存至: {args.output}")
    else:
        print(output)

    # 退出码
    sys.exit(runner.exit_code(report))


def cmd_run(args: argparse.Namespace) -> None:
    """运行技能（Agent 引擎执行；旧关键词引擎已于 v3.1 退役）"""
    if getattr(args, "background", False):
        _run_background(args)
        return
    from .runtime.agent.cli import cmd_run_agent
    raise SystemExit(cmd_run_agent(args))


def _run_background(args: argparse.Namespace) -> None:
    """后台执行 agent 任务：spawn 子进程，输出写入日志文件。"""
    import subprocess
    import time
    from pathlib import Path

    log_dir = Path.home() / ".zenskill" / "agent" / "background"
    log_dir.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S")
    task_short = (args.task or "task")[:30].replace(" ", "_").replace("/", "_")
    log_file = log_dir / f"{ts}_{task_short}.log"
    pid_file = log_dir / f"{ts}_{task_short}.pid"

    # 构建命令
    cmd = [sys.executable, "-m", "zenskill", "run", args.task or ""]
    for flag in ["model", "permission", "session", "max_steps", "timeout"]:
        val = getattr(args, flag, None)
        if val is not None:
            cmd.extend([f"--{flag.replace('_', '-')}", str(val)])
    if getattr(args, "with_memory", False):
        cmd.append("--with-memory")
    if getattr(args, "with_skills", False):
        cmd.append("--with-skills")
    if getattr(args, "debug", False):
        cmd.append("--debug")

    with open(log_file, "w") as log:
        from .runtime.platform_utils import get_new_process_kwargs
        proc = subprocess.Popen(
            cmd, stdout=log, stderr=subprocess.STDOUT,
            **get_new_process_kwargs(),
        )

    pid_file.write_text(str(proc.pid))
    print(f"后台任务已启动")
    print(f"  PID: {proc.pid}")
    if platform.system() == "Windows":
        print(f"  日志: Get-Content {log_file} -Wait")
    else:
        print(f"  日志: tail -f {log_file}")
    print(f"  停止: kill {proc.pid}")


def cmd_test_skill(args: argparse.Namespace) -> None:
    """测试技能"""
    import asyncio

    from .core.skill_deployer import SkillDeployer
    from .runtime import ExecutionConfig

    async def _test():
        executor = SkillDeployer(
            mcp_server_path=args.mcp_server,
            config=ExecutionConfig(timeout_seconds=args.timeout),
        )

        result = await executor.test_skill(args.skill_id)
        cli_output(result.to_dict(), args,
                  text=lambda: f"Test {'passed' if result.success else 'failed'}: {result.output or result.error}")

    asyncio.run(_test())


def cmd_deploy_skill(args: argparse.Namespace) -> None:
    """部署技能（经 SkillDeployer 委托 platforms DeployAdapter 统一管线）"""
    import asyncio

    from .core.skill_deployer import SkillDeployer
    from .runtime import ExecutionConfig

    async def _deploy():
        executor = SkillDeployer(
            mcp_server_path=args.mcp_server,
            config=ExecutionConfig(timeout_seconds=args.timeout),
        )

        result = await executor.deploy_skill(args.skill_id, args.platform)
        cli_output(result.to_dict(), args,
                  text=lambda: f"Deploy {'success' if result.success else 'failed'}: {result.output or result.error}")

    asyncio.run(_deploy())


def main() -> int:
    """主入口函数"""
    # 从 model-switcher 注入 API key（与 Craft GUI 共享同一份 key）
    _inject_model_switcher_keys()

    # 确保所有数据目录存在（首次运行时创建）
    ensure_data_dirs()

    # 预处理：提取 --json 标志（argparse 子命令不继承父级参数）
    json_output = "--json" in sys.argv
    if json_output:
        sys.argv = [a for a in sys.argv if a != "--json"]

    parser = argparse.ArgumentParser(
        prog="zenskill",
        description="ZenSkill - 有生命的技能系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m zenskill                            - 启动 TUI 界面（需安装 rich prompt_toolkit）
  python -m zenskill tui                        - 启动 TUI 界面
  python -m zenskill info                       - 显示系统信息
  python -m zenskill memory add "完成CLI开发"   - 添加记忆
  python -m zenskill memory list --n 10         - 列出记忆
  python -m zenskill memory search "反思"       - 搜索记忆
  python -m zenskill memory export              - 导出记忆备份
  python -m zenskill memory import backup.json  - 导出记忆备份
  python -m zenskill skill status               - 查询修炼状态
  python -m zenskill skill metrics              - 显示使用指标
  python -m zenskill skill history --n 10       - 查看状态历史
  python -m zenskill skill rollback --n 1       - 回滚状态
  python -m zenskill reflect trigger            - 触发禅思反思
  python -m zenskill reflect issues             - 系统自我诊断
  python -m zenskill growth status              - 显示成长状态（五维能力雷达）
  python -m zenskill growth trend               - 显示成长趋势
  python -m zenskill growth compare             - 显示多维对比分析
  python -m zenskill growth replay              - 回放成长路径
  python -m zenskill growth errors              - 显示错误模式聚类
  python -m zenskill growth feedback            - 显示即时反馈与奖励
  python -m zenskill growth dimensions          - 管理自定义成长维度
  python -m zenskill growth habits              - 追踪习惯养成
  python -m zenskill growth achievements        - 显示成就与徽章
  python -m zenskill growth milestones          - 显示成长里程碑
  python -m zenskill growth abilities           - 显示已解锁能力
  python -m zenskill growth insight             - 显示智能洞察报告
  python -m zenskill goal status                - 显示成长目标状态
  python -m zenskill goal suggest               - 推荐成长目标
  python -m zenskill goal set --dimension proficiency --target 50 - 设置目标
  python -m zenskill task recommend             - 推荐练习任务
  python -m zenskill task status                - 查看任务状态
  python -m zenskill insight unread             - 查看未读洞察
  python -m zenskill insight read <ID>          - 标记洞察为已读
  python -m zenskill doctor state               - 扫描状态数据完整性
  python -m zenskill doctor repair              - 修复可恢复的状态文件
  python -m zenskill doctor repair --dry-run    - 预览修复计划
  python -m zenskill doctor snapshot            - 创建数据快照
  python -m zenskill doctor snapshot list       - 列出所有快照
  python -m zenskill doctor migrate --all       - 迁移状态 schema 版本
  python -m zenskill doctor diagnostics --n 20  - 查看诊断日志
  python -m zenskill search "技术写作"           - 搜索技能 (9U)
  python -m zenskill discover                   - 发现推荐技能 (9U)
  python -m zenskill trending                   - 热门趋势技能 (9U)
  python -m zenskill path "Python 全栈"         - 推荐学习路径 (9U)
  python -m zenskill rating <skill_id>           - 查看技能评级 (9V)
  python -m zenskill rate <skill_id> 4           - 给技能打分 (9V)
  python -m zenskill ratings list                - 列出所有评级 (9V)
  python -m zenskill ratings rate-all            - 批量评级所有技能 (9V)
        """,
    )

    # 全局参数
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--debug", action="store_true", help="显示调试信息（错误时显示堆栈）")
    parser.add_argument("--skill-id", default="zenskill-core", help="指定技能ID")
    parser.add_argument("--profile", default=None, metavar="NAME",
                        help="指定 Profile（默认为当前激活的 profile）")

    # 子命令
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # info 命令
    info_parser = subparsers.add_parser("info", help="显示系统信息")
    info_parser.set_defaults(func=cmd_info)

    # ================================================================
    # profile 命令组 — 多 Profile 管理
    # ================================================================
    from .cli.profile import register_profile_parser
    register_profile_parser(subparsers)
    from .cli.session import register_session_parser
    register_session_parser(subparsers)
    from .cli.perceive import register_perceive_parser
    register_perceive_parser(subparsers)
    from .cli.version import register_version_parser
    register_version_parser(subparsers)
    from .cli.chain import register_chain_parser
    register_chain_parser(subparsers)
    from .cli.skill import register_skill_parser
    register_skill_parser(subparsers)
    from .cli.doctor import register_doctor_parser
    register_doctor_parser(subparsers)
    db_parser = subparsers.add_parser("db", help="数据库管理 (Phase D)")
    db_sub = db_parser.add_subparsers(dest="db_action", help="数据库操作")
    db_init_p = db_sub.add_parser("init", help="初始化数据库")
    db_init_p.set_defaults(func=cmd_db)
    db_stats_p = db_sub.add_parser("stats", help="数据库统计")
    db_stats_p.set_defaults(func=cmd_db)
    db_vacuum_p = db_sub.add_parser("vacuum", help="压缩数据库")
    db_vacuum_p.set_defaults(func=cmd_db)
    db_backup_p = db_sub.add_parser("backup", help="备份数据库")
    db_backup_p.set_defaults(func=cmd_db)
    db_migrate_p = db_sub.add_parser("migrate", help="从旧 JSON/JSONL 迁移数据")
    db_migrate_p.add_argument("--dry-run", action="store_true", help="预览迁移")
    db_migrate_p.add_argument("--archive", action="store_true", help="迁移后归档旧文件")
    db_migrate_p.set_defaults(func=cmd_db)
    db_parser.set_defaults(func=cmd_db)

    # ── 9T: 技能包管理 ──
    package_parser = subparsers.add_parser("package", help="技能包管理 (Phase 9T)")
    package_sub = package_parser.add_subparsers(dest="package_action", help="技能包操作")
    package_build_p = package_sub.add_parser("build", help="构建技能包")
    package_build_p.add_argument("skill_id", help="技能 ID")
    package_build_p.add_argument("--output", help="输出路径")
    package_build_p.set_defaults(func=cmd_package_build)
    package_validate_p = package_sub.add_parser("validate", help="验证技能包")
    package_validate_p.add_argument("path", help="技能包路径")
    package_validate_p.set_defaults(func=cmd_package_validate)
    package_install_p = package_sub.add_parser("install", help="安装技能包")
    package_install_p.add_argument("path", help="技能包路径")
    package_install_p.set_defaults(func=cmd_package_install)

    # package rollback (P2-3: 安装前快照回滚)
    package_rollback_p = package_sub.add_parser("rollback", help="回滚技能包到安装前快照")
    package_rollback_p.add_argument("name", help="技能包名称")
    package_rollback_p.add_argument("--to", dest="snapshot", help="目标快照 ID（缺省取最新）")
    package_rollback_p.add_argument("--list", dest="list_backups", action="store_true", help="仅列出可用快照")
    package_rollback_p.set_defaults(func=cmd_package_rollback)

    package_export_p = package_sub.add_parser("export", help="导出技能为分享包")
    package_export_p.add_argument("skill_id", help="技能 ID")
    package_export_p.add_argument("--output", help="输出路径")
    package_export_p.set_defaults(func=cmd_package_export)
    package_list_p = package_sub.add_parser("list", help="列出已安装的技能包")
    package_list_p.set_defaults(func=cmd_package_list)

    # ── 9U: 技能搜索与发现 ──
    search_parser = subparsers.add_parser("search", help="搜索技能 (Phase 9U)")
    search_parser.add_argument("query", help="搜索关键词（支持自然语言）")
    search_parser.add_argument("--category", help="按分类过滤 (dev/design/data/ops/writing/general)")
    search_parser.add_argument("--difficulty", choices=["beginner", "intermediate", "advanced", "expert"],
                               help="按难度过滤")
    search_parser.add_argument("--tags", nargs="*", help="按标签过滤")
    search_parser.add_argument("--top-k", type=int, default=10, help="返回数量")
    search_parser.add_argument("--market", choices=["all", "github", "skillssh", "skillhub", "coze", "npm", "pypi", "clawhub", "builtin"],
                               help="搜索外部市场而非本地索引 (P3-2)")
    search_parser.add_argument("--json", action="store_true", help="JSON 输出")
    search_parser.set_defaults(func=cmd_search)

    # browse (P3-2: 市场热门榜)
    browse_parser = subparsers.add_parser("browse", help="浏览市场热门技能榜")
    browse_parser.add_argument("--view", choices=["all-time", "trending", "hot"],
                               default="trending", help="榜单视角")
    browse_parser.add_argument("--top-k", type=int, default=10, help="返回数量")
    browse_parser.add_argument("--json", action="store_true", help="JSON 输出")
    browse_parser.set_defaults(func=cmd_browse)

    discover_parser = subparsers.add_parser("discover", help="发现推荐技能 (Phase 9U)")
    discover_parser.add_argument("--owned", help="已有技能 ID（逗号分隔）")
    discover_parser.add_argument("--top-k", type=int, default=10, help="推荐数量")
    discover_parser.set_defaults(func=cmd_discover)

    trending_parser = subparsers.add_parser("trending", help="热门趋势技能 (Phase 9U)")
    trending_parser.add_argument("--top-k", type=int, default=10, help="排行数量")
    trending_parser.set_defaults(func=cmd_trending)

    path_parser = subparsers.add_parser("path", help="推荐学习路径 (Phase 9U)")
    path_parser.add_argument("goal", help="学习目标描述")
    path_parser.add_argument("--owned", help="已掌握的技能 ID（逗号分隔）")
    path_parser.add_argument("--steps", type=int, default=5, help="路径步数")
    path_parser.set_defaults(func=cmd_path)

    # ── 9V: 技能质量评级 ──
    rating_parser = subparsers.add_parser("rating", help="查看技能评级 (Phase 9V)")
    rating_parser.add_argument("skill_id", help="技能 ID")
    rating_parser.add_argument("--refresh", action="store_true", help="强制重新计算")
    rating_parser.set_defaults(func=cmd_rating)

    rate_parser = subparsers.add_parser("rate", help="给技能打分 (Phase 9V)")
    rate_parser.add_argument("skill_id", help="技能 ID")
    rate_parser.add_argument("score", type=float, help="评分 1-5")
    rate_parser.add_argument("--comment", help="评价文字")
    rate_parser.add_argument("--user", default="anonymous", help="用户名")
    rate_parser.set_defaults(func=cmd_rate)

    ratings_parser = subparsers.add_parser("ratings", help="列出所有评级 (Phase 9V)")
    ratings_sub = ratings_parser.add_subparsers(dest="ratings_action", help="评级操作")
    ratings_list_p = ratings_sub.add_parser("list", help="列出已评级的技能")
    ratings_list_p.set_defaults(func=cmd_ratings_list)
    ratings_rate_all_p = ratings_sub.add_parser("rate-all", help="批量评级所有已知技能")
    ratings_rate_all_p.set_defaults(func=cmd_ratings_rate_all)
    ratings_parser.set_defaults(func=cmd_ratings_list)

    # ── Phase E: 技能生态 ──
    install_parser = subparsers.add_parser("install", help="安装技能 (Phase E)")
    install_parser.add_argument("source", nargs="?", help="github://user/repo | clawhub://skill | https://... | file://...")
    install_parser.add_argument("--from-url", help="从 URL 安装（文章/博客）")
    install_parser.add_argument("--from-file", help="从文件安装（.md/.pdf/.epub）")
    install_parser.set_defaults(func=cmd_install)

    # ── Phase U0E: uninstall ──
    uninstall_parser = subparsers.add_parser("uninstall", help="卸载技能 (Phase U0E)")
    uninstall_parser.add_argument("skill_id", help="技能 ID")
    uninstall_parser.add_argument("--force", "-f", action="store_true", help="跳过确认")
    uninstall_parser.set_defaults(func=cmd_uninstall)

    # ── Phase U3D: content ──
    content_parser = subparsers.add_parser("content", help="内容→技能转换 (Phase U3)")
    content_sub = content_parser.add_subparsers(dest="content_action", help="内容操作")
    content_from_text = content_sub.add_parser("from-text", help="从文本创建技能")
    content_from_text.add_argument("text", help="文本内容")
    content_from_text.add_argument("--title", "-t", default="", help="标题")
    content_from_text.set_defaults(func=cmd_content_from_text)
    content_from_url = content_sub.add_parser("from-url", help="从 URL 创建技能")
    content_from_url.add_argument("url", help="网页 URL")
    content_from_url.set_defaults(func=cmd_content_from_url)
    content_from_file = content_sub.add_parser("from-file", help="从文件创建技能")
    content_from_file.add_argument("path", help="文件路径")
    content_from_file.set_defaults(func=cmd_content_from_file)
    content_parser.set_defaults(func=cmd_content_from_text)

    # ── Phase S: SkillSpec ──
    spec_parser = subparsers.add_parser("spec", help="SkillSpec 生命周期管理 (Phase S)")
    spec_sub = spec_parser.add_subparsers(dest="spec_action", help="SkillSpec 操作")

    spec_validate_p = spec_sub.add_parser("validate", help="验证 skill.toml")
    spec_validate_p.add_argument("path", help="skill.toml 路径")
    spec_validate_p.add_argument("--stage", default="package",
                                 choices=["define", "package", "install", "invoke", "full"])
    spec_validate_p.set_defaults(func=cmd_spec_validate)

    spec_export_p = spec_sub.add_parser("export", help="导出 SkillSpec")
    spec_export_p.add_argument("skill_id", help="技能 ID")
    spec_export_p.add_argument("--format", default="toml", choices=["toml", "json"])
    spec_export_p.add_argument("--output", "-o", help="输出文件路径")
    spec_export_p.set_defaults(func=cmd_spec_export)

    spec_inspect_p = spec_sub.add_parser("inspect", help="查看 SkillSpec 详情")
    spec_inspect_p.add_argument("skill_id", help="技能 ID")
    spec_inspect_p.set_defaults(func=cmd_spec_inspect)

    spec_parser.set_defaults(func=cmd_spec_validate)

    # ── Phase E2: GitHub 技能 ──
    github_parser = subparsers.add_parser("github", help="GitHub 技能管理 (Phase E2)")
    github_sub = github_parser.add_subparsers(dest="github_action", help="GitHub 操作")

    github_info_p = github_sub.add_parser("info", help="预览 GitHub 仓库")
    github_info_p.add_argument("repo", help="owner/repo")
    github_info_p.set_defaults(func=cmd_github_info)

    github_parser.set_defaults(func=cmd_github_info)

    market_parser = subparsers.add_parser("market", help="技能市场 (Phase E)")
    market_sub = market_parser.add_subparsers(dest="market_action", help="市场操作")
    market_search_p = market_sub.add_parser("search", help="跨市场搜索")
    market_search_p.add_argument("query", help="搜索关键词")
    market_search_p.add_argument("--top-k", type=int, default=10, help="返回数量")
    market_search_p.set_defaults(func=cmd_market_search)
    market_list_p = market_sub.add_parser("list", help="列出已注册市场")
    market_list_p.set_defaults(func=cmd_market_search)  # reuses handler
    market_parser.set_defaults(func=cmd_market_search)

    # tui 命令
    tui_parser = subparsers.add_parser("tui", help="启动交互式终端界面")
    tui_parser.add_argument(
        "-m", "--mode",
        choices=["interactive", "command", "rich", "i", "c"],
        default="interactive",
        help="运行模式: rich(Rich+prompt_toolkit,推荐) | interactive(自动选择) | command(命令模式,简洁)",
    )
    tui_parser.add_argument(
        "--install-deps", action="store_true",
        help="一键安装缺失的 TUI 依赖 (textual, rich)",
    )
    tui_parser.add_argument(
        "--agent", dest="use_agent", action="store_true", default=None,
        help="启用 Agent Engine（工具执行/能力/会话持久化）",
    )
    tui_parser.add_argument(
        "--no-agent", dest="use_agent", action="store_false",
        help="禁用 Agent Engine（纯 LLM 对话，更快）",
    )
    tui_parser.set_defaults(func=cmd_tui)

    # mcp 命令组（实现位于 zenskill/cli/mcp.py，渐进拆分试点）
    from .cli.mcp import register_mcp_parser
    register_mcp_parser(subparsers)

    # pages 命令组（craft Pages 页面包播种，实现位于 zenskill/cli/pages.py）
    from .cli.pages import register_pages_parser
    register_pages_parser(subparsers)

    # serve 命令（WebUI server）
    from .cli.serve import register_serve_parser
    register_serve_parser(subparsers)

    # memory 命令组
    from .cli.memory import register_memory_parser
    register_memory_parser(subparsers)

    # skill 命令组
    cross_parser = subparsers.add_parser("cross", help="跨技能洞察整合（P8 多技能协同）")
    cross_parser.set_defaults(func=cmd_cross_report)  # cross 默认为 report
    cross_subparsers = cross_parser.add_subparsers(dest="subcommand", help="跨技能操作")

    # cross report (默认)
    cross_report_parser = cross_subparsers.add_parser("report", help="全局成长报告")
    cross_report_parser.set_defaults(func=cmd_cross_report)

    # cross insights
    cross_insights_parser = cross_subparsers.add_parser("insights", help="查看跨技能洞察")
    cross_insights_parser.set_defaults(func=cmd_cross_insights)

    # cross compare
    cross_compare_parser = cross_subparsers.add_parser("compare", help="跨技能对比分析")
    cross_compare_parser.add_argument("skill_ids", nargs="+", help="技能ID列表")
    cross_compare_parser.set_defaults(func=cmd_cross_compare)

    # eco 命令组（技能生态系统仪表盘）
    eco_parser = subparsers.add_parser("eco", help="技能生态系统仪表盘（P8 多技能协同）")
    eco_parser.set_defaults(func=cmd_eco_dashboard)  # eco 默认为 dashboard
    eco_subparsers = eco_parser.add_subparsers(dest="subcommand", help="生态系统操作")

    # eco dashboard (默认)
    eco_dash_parser = eco_subparsers.add_parser("dashboard", help="技能生态系统仪表盘")
    eco_dash_parser.set_defaults(func=cmd_eco_dashboard)

    # eco heatmap
    eco_heatmap_parser = eco_subparsers.add_parser("heatmap", help="成长热力图详细报告")
    eco_heatmap_parser.set_defaults(func=cmd_eco_heatmap)

    # eco health
    eco_health_parser = eco_subparsers.add_parser("health", help="生态系统健康度评估")
    eco_health_parser.set_defaults(func=cmd_eco_health)

    # data 命令组（数据管理）
    from .cli.data import register_data_parser
    register_data_parser(subparsers)
    internal_parser = subparsers.add_parser("_internal", help="内部命令")
    internal_subparsers = internal_parser.add_subparsers(dest="subcommand", help="内部操作")

    # _internal record_event
    internal_record_parser = internal_subparsers.add_parser("record_event", help="记录事件")
    internal_record_parser.add_argument("event_type", help="事件类型")
    internal_record_parser.add_argument("skill_id", help="技能ID")
    internal_record_parser.add_argument("action", help="操作描述")
    internal_record_parser.add_argument("--success", default="true", help="是否成功")
    internal_record_parser.add_argument("--duration", type=float, default=0, help="时长(ms)")
    internal_record_parser.add_argument("--context", default="{}", help="上下文JSON")
    internal_record_parser.set_defaults(func=_cmd_internal_record_event)

    # mirror 命令组（用户镜像 Phase 9A）
    # llm 命令组（大模型服务管理）
    from .cli.llm import register_llm_parser
    register_llm_parser(subparsers)
    chat_parser = subparsers.add_parser("chat", help="AI 对话")
    chat_parser.add_argument("message", nargs="?", help="对话内容（不传则进入交互模式）")
    chat_parser.add_argument("--model", help="指定使用的模型（临时，不修改默认）")
    chat_parser.set_defaults(func=cmd_chat)

    # collector 命令组（智能体生态采集）
    # hook 命令组（Claude Code 实时采集 Hook 管理）
    # notify (通知引擎)
    from .cli.notify import register_notify_parser
    register_notify_parser(subparsers)
    from .cli.hook import register_hook_parser
    register_hook_parser(subparsers)
    from .cli.collector import register_collector_parser
    register_collector_parser(subparsers)
    from .cli.mirror import register_mirror_parser
    register_mirror_parser(subparsers)
    agent_parser = subparsers.add_parser("agent", help="多代理系统（Phase 9L-9S）")
    agent_sub = agent_parser.add_subparsers(dest="agent_action", help="代理操作")

    agent_discover_p = agent_sub.add_parser("discover", help="智能发现最适合任务的代理")
    agent_discover_p.add_argument("task_type", help="任务类型（如 coding/testing/architecture）")
    agent_discover_p.add_argument("--domain", default="", help="任务领域（如 python/backend/security）")
    agent_discover_p.add_argument("--difficulty", default="medium",
                                  choices=["trivial", "easy", "medium", "hard", "expert"],
                                  help="任务难度")
    agent_discover_p.add_argument("--top-k", type=int, default=3, help="返回 Top-K 结果")
    agent_discover_p.set_defaults(func=cmd_agent_discover)

    # ── Runtime 命令组 ──

    # run 命令
    run_parser = subparsers.add_parser("run",
        help="运行技能（Runtime 执行）",
        description="通过 LLM 驱动 agent 引擎执行技能任务",
        epilog="示例:\n"
               "  zenskill run \"读取文件内容\" --mcp-server /path/to/server\n"
               "  zenskill run \"执行测试\" --skill-id my-skill --timeout 60\n"
               "  zenskill run \"部署技能\" --max-steps 5",
    )
    run_parser.add_argument("task", help="任务描述")
    run_parser.add_argument("--engine", choices=["agent"], default="agent",
        help="执行引擎（旧关键词引擎已退役，仅 agent）")
    run_parser.add_argument("--model", help="agent 引擎模型（如 deepseek/deepseek-chat、anthropic/claude-sonnet-4-5）")
    run_parser.add_argument("--permission", choices=["full", "restricted", "plan", "sandbox"], default="full",
        help="agent 引擎权限模式：full=放行 / plan=只读 / restricted|sandbox=白名单沙箱")
    run_parser.add_argument("--session", help="agent 引擎会话 ID（自动创建/落盘 JSONL）")
    run_parser.add_argument("--continue", dest="continue_session", action="store_true",
        help="续接 --session 指定的会话")
    run_parser.add_argument("--fork", dest="fork_entry",
        help="从指定 entry 分叉（需配合 --session --continue）")
    run_parser.add_argument("--with-memory", action="store_true",
        help="启用 Memory Capability（记忆注入/episode 落库/记忆工具）")
    run_parser.add_argument("--with-skills", action="store_true",
        help="把 ~/.agents/skills 技能元数据注入系统提示词（渐进披露）")
    run_parser.add_argument("--debug", action="store_true",
        help="调试模式：输出每轮 token 用量/耗时/工具详情")
    run_parser.add_argument("--planning", action="store_true",
        help="规划模式：第一轮先输出步骤计划，后续轮次按计划执行")
    run_parser.add_argument("--graph", action="store_true",
        help="图模式：用 LLM 分解任务为子任务 DAG，无依赖子任务并行执行")
    run_parser.add_argument("--interactive", action="store_true",
        help="任务完成后进入 REPL 继续对话")
    run_parser.add_argument("--json-response", action="store_true",
        help="强制 LLM 输出合法 JSON（response_format json_object）")
    run_parser.add_argument("--image", action="append", default=[],
        help="图片文件路径（可多次指定，需视觉模型如 gpt-4o/claude）")
    run_parser.add_argument("--args", help="工具参数 JSON (e.g. '{\"path\": \"/tmp/test.txt\"}')")
    run_parser.add_argument("--mcp-server", action="append", default=None,
        help="MCP Server 可执行文件路径（可多次指定接入多台，经 pool 前缀路由）")
    run_parser.add_argument("--skill-id", help="技能 ID")
    run_parser.add_argument("--max-steps", type=int, default=10, help="最大执行步数")
    run_parser.add_argument("--thinking-level", choices=["on", "off"], default=None,
        help="思考深度控制（仅 deepseek 等支持开关的模型生效；off 可显著省 token）")
    run_parser.add_argument("--timeout", type=float, default=300.0, help="超时时间（秒）")
    run_parser.add_argument("--background", action="store_true",
        help="后台执行：输出写入日志文件，可用 run --status 查看状态")
    run_parser.add_argument("--no-delegate", action="store_true",
        help="禁用 SubAgent delegate 工具（子任务隔离子上下文执行）")
    run_parser.set_defaults(func=cmd_run)

    # agent-engine 命令组（从 cli/agent.py 注册）
    from .cli.agent import register_agent_engine_parser
    register_agent_engine_parser(subparsers)

    # growth 命令组（从 cli/growth.py 注册）
    from .cli.growth import register_growth_parser
    register_growth_parser(subparsers)

    # test 命令
    test_parser = subparsers.add_parser("test-skill",
        help="测试技能",
        description="运行技能测试用例",
    )
    test_parser.add_argument("skill_id", help="技能 ID")
    test_parser.add_argument("--mcp-server", help="MCP Server 路径")
    test_parser.add_argument("--timeout", type=float, default=60.0, help="超时时间（秒）")
    test_parser.set_defaults(func=cmd_test_skill)

    # deploy 命令
    deploy_parser = subparsers.add_parser("deploy-skill",
        help="部署技能",
        description="将技能部署到目标平台",
    )
    deploy_parser.add_argument("skill_id", help="技能 ID")
    deploy_parser.add_argument("--platform", default="local", choices=["local", "opencode", "cursor", "codex"],
                               help="目标平台")
    deploy_parser.add_argument("--dry-run", action="store_true", help="预览部署内容，不实际写入")
    deploy_parser.add_argument("--force", action="store_true", help="覆盖已存在的技能")
    deploy_parser.add_argument("--output-dir", help="指定输出目录（默认 dist/）")
    deploy_parser.add_argument("--mcp-server", help="MCP Server 路径")
    deploy_parser.add_argument("--timeout", type=float, default=120.0, help="超时时间（秒）")
    deploy_parser.set_defaults(func=cmd_deploy_skill)

    # ── 8.7G-L: GTD 命令组 ──

    # gtd 全局入口
    gtd_parser = subparsers.add_parser("gtd", help="GTD 生产力系统")
    gtd_sub = gtd_parser.add_subparsers(dest="gtd_action", help="GTD 操作")
    gtd_dashboard_p = gtd_sub.add_parser("dashboard", help="GTD 综合仪表盘")
    gtd_dashboard_p.set_defaults(func=cmd_gtd_dashboard)
    gtd_weekly_p = gtd_sub.add_parser("weekly-review", help="GTD 周回顾")
    gtd_weekly_p.set_defaults(func=cmd_gtd_weekly_review)
    gtd_stats_p = gtd_sub.add_parser("stats", help="GTD 统计")
    gtd_stats_p.set_defaults(func=cmd_gtd_dashboard)
    gtd_migrate_p = gtd_sub.add_parser("migrate", help="旧系统数据迁移到 GTD")
    gtd_migrate_p.add_argument("--skill-id", default="zenskill-core", help="技能 ID")
    gtd_migrate_p.add_argument("--dry-run", action="store_true", help="干跑模式，不执行实际迁移")
    gtd_migrate_p.set_defaults(func=cmd_gtd_migrate)

    # report subparser
    report_parser = subparsers.add_parser("report", help="GTD 报告")
    report_sub = report_parser.add_subparsers(dest="report_action", help="报告类型")
    report_weekly_p = report_sub.add_parser("weekly", help="GTD 周报")
    report_weekly_p.add_argument("--weeks", type=int, default=1, help="统计周数")
    report_weekly_p.add_argument("--format", choices=["json", "markdown"], default="json", help="输出格式")
    report_weekly_p.set_defaults(func=cmd_report_weekly)
    report_monthly_p = report_sub.add_parser("monthly", help="GTD 月报")
    report_monthly_p.add_argument("--months", type=int, default=1, help="统计月数")
    report_monthly_p.add_argument("--format", choices=["json", "markdown"], default="json", help="输出格式")
    report_monthly_p.set_defaults(func=cmd_report_monthly)

    # health subparser
    health_parser = subparsers.add_parser("health", help="GTD 健康度")
    health_sub = health_parser.add_subparsers(dest="health_action", help="健康度操作")
    health_score_p = health_sub.add_parser("score", help="GTD 健康度评分")
    health_score_p.add_argument("--days", type=int, default=30, help="统计天数")
    health_score_p.add_argument("--format", choices=["json", "markdown"], default="json", help="输出格式")
    health_score_p.set_defaults(func=cmd_health_score)
    health_annual_p = health_sub.add_parser("annual", help="年度 GTD 回顾")
    health_annual_p.add_argument("--year", type=int, default=0, help="年份")
    health_annual_p.set_defaults(func=cmd_health_annual)
    health_card_p = health_sub.add_parser("card", help="技能成长评分卡")
    health_card_p.add_argument("--skill-id", default="zenskill-core", help="技能 ID")
    health_card_p.set_defaults(func=cmd_health_card)

    # inbox 命令组
    inbox_parser = subparsers.add_parser("inbox", help="GTD Inbox 捕获")
    inbox_sub = inbox_parser.add_subparsers(dest="inbox_action", help="Inbox 操作")
    inbox_add_p = inbox_sub.add_parser("add", help="快速捕获")
    inbox_add_p.add_argument("text", help="捕获内容")
    inbox_add_p.add_argument("--source", default="cli", choices=["cli", "tui", "hook", "stdin"])
    inbox_add_p.set_defaults(func=cmd_inbox_add)
    inbox_list_p = inbox_sub.add_parser("list", help="列出 Inbox")
    inbox_list_p.add_argument("--status", default="unprocessed", choices=["unprocessed", "clarified", "archived", "all"])
    inbox_list_p.add_argument("--n", type=int, default=20, help="显示条数")
    inbox_list_p.set_defaults(func=cmd_inbox_list)
    inbox_process_p = inbox_sub.add_parser("process", help="处理 Inbox 项")
    inbox_process_p.add_argument("item_id", help="Inbox ID")
    inbox_process_p.add_argument("--type", required=True, choices=["action", "project", "reference", "trash"])
    inbox_process_p.add_argument("--target-id", help="关联 ID")
    inbox_process_p.set_defaults(func=cmd_inbox_process)

    # action 命令组
    action_parser = subparsers.add_parser("action", help="GTD Action 管理")
    action_sub = action_parser.add_subparsers(dest="action_cmd", help="Action 操作")
    a_add_p = action_sub.add_parser("add", help="添加 Action")
    a_add_p.add_argument("title", help="行动标题")
    a_add_p.add_argument("--context", help="场景标签,逗号分隔")
    a_add_p.add_argument("--priority", default="P2", choices=["P0", "P1", "P2", "P3"])
    a_add_p.add_argument("--energy", type=int, default=5, help="能量消耗 1-10")
    a_add_p.add_argument("--due", help="截止日期 YYYY-MM-DD")
    a_add_p.add_argument("--estimated", type=int, default=25, help="预计分钟数")
    a_add_p.add_argument("--project", help="关联 Project ID")
    a_add_p.add_argument("--repeat", choices=["daily", "weekly", "monthly"], help="重复规则")
    a_add_p.set_defaults(func=cmd_action_add)
    a_list_p = action_sub.add_parser("list", help="列出 Actions")
    a_list_p.add_argument("--status", default="pending", choices=["pending", "next", "done", "all"])
    a_list_p.add_argument("--context", help="按场景过滤")
    a_list_p.add_argument("--priority", choices=["P0", "P1", "P2", "P3"])
    a_list_p.add_argument("--project", help="按项目过滤")
    a_list_p.add_argument("--due-today", action="store_true", help="仅今日到期")
    a_list_p.add_argument("--next", action="store_true", help="推荐下一步")
    a_list_p.add_argument("--n", type=int, default=20, help="显示条数")
    a_list_p.set_defaults(func=cmd_action_list)
    a_done_p = action_sub.add_parser("done", help="完成 Action")
    a_done_p.add_argument("action_id", help="Action ID")
    a_done_p.add_argument("--energy-invested", type=int, default=0, help="实际能量消耗")
    a_done_p.set_defaults(func=cmd_action_done)
    a_delete_p = action_sub.add_parser("delete", help="删除 Action")
    a_delete_p.add_argument("action_id", help="Action ID")
    a_delete_p.set_defaults(func=cmd_action_delete)

    # project 命令组
    project_parser = subparsers.add_parser("project", help="GTD Project 管理")
    project_sub = project_parser.add_subparsers(dest="project_cmd", help="Project 操作")
    p_create_p = project_sub.add_parser("create", help="创建 Project")
    p_create_p.add_argument("name", help="项目名称")
    p_create_p.add_argument("--outcome", help="期望结果")
    p_create_p.add_argument("--skill-id", help="关联技能")
    p_create_p.add_argument("--notes", help="备注")
    p_create_p.set_defaults(func=cmd_project_create)
    p_list_p = project_sub.add_parser("list", help="列出 Projects")
    p_list_p.add_argument("--status", default="active", choices=["active", "someday", "done", "all"])
    p_list_p.set_defaults(func=cmd_project_list)
    p_show_p = project_sub.add_parser("show", help="查看 Project 详情")
    p_show_p.add_argument("project_id", help="Project ID")
    p_show_p.set_defaults(func=cmd_project_show)
    p_tmpl_p = project_sub.add_parser("templates", help="列出项目模板")
    p_tmpl_p.set_defaults(func=cmd_project_templates)

    # energy 命令组
    energy_parser = subparsers.add_parser("energy", help="GTD Energy 能量管理")
    energy_sub = energy_parser.add_subparsers(dest="energy_cmd", help="Energy 操作")
    e_status_p = energy_sub.add_parser("status", help="能量状态")
    e_status_p.set_defaults(func=cmd_energy_status)
    e_advise_p = energy_sub.add_parser("advise", help="能量优化建议")
    e_advise_p.set_defaults(func=cmd_energy_advise)

    # calendar 命令组
    calendar_parser = subparsers.add_parser("calendar", help="GTD Calendar 日程")
    cal_sub = calendar_parser.add_subparsers(dest="cal_cmd", help="Calendar 操作")
    cal_today_p = cal_sub.add_parser("today", help="今日日程")
    cal_today_p.add_argument("--date", help="指定日期 YYYY-MM-DD")
    cal_today_p.set_defaults(func=cmd_calendar_today)
    cal_week_p = cal_sub.add_parser("week", help="本周日程")
    cal_week_p.set_defaults(func=cmd_calendar_week)
    cal_add_p = cal_sub.add_parser("add", help="添加日程")
    cal_add_p.add_argument("date", help="日期 YYYY-MM-DD")
    cal_add_p.add_argument("title", help="日程标题")
    cal_add_p.add_argument("--time", help="时间 HH:MM")
    cal_add_p.add_argument("--repeat-rule", choices=["daily", "weekly", "monthly"], help="重复规则")
    cal_add_p.set_defaults(func=cmd_calendar_add)

    # ═══════════════════════════════════════════════════════════
    # test 命令组 — ZenTest 测试框架
    # ═══════════════════════════════════════════════════════════
    test_parser = subparsers.add_parser("test", help="ZenTest 测试框架 — 运行多层级测试")
    test_parser.add_argument("--category", "-c",
        choices=["unit", "integration", "e2e", "skill", "platform", "security"],
        help="测试分类（默认全量）")
    test_parser.add_argument("--format", "-f",
        choices=["text", "json", "html", "junit"],
        default="text", help="报告格式")
    test_parser.add_argument("--quick", "-q", action="store_true",
        help="快速验证 (<30s) — 仅 unit + integration")
    test_parser.add_argument("--smoke", action="store_true",
        help="烟雾测试 (<10s)")
    test_parser.add_argument("--output", "-o",
        help="保存报告到文件")
    test_parser.add_argument("--coverage", "-C", action="store_true",
        help="显示测试覆盖矩阵报告")
    test_parser.add_argument("--plan", action="store_true",
        help="显示测试计划路线图")
    test_parser.add_argument("--module", "-m",
        help="按模块名过滤测试（如 gtd, tui, market）")
    test_parser.add_argument("--priority", "-p",
        choices=["p0", "p1", "p2", "p3"],
        help="按优先级过滤测试计划")
    test_parser.set_defaults(func=cmd_zentest)

    args = parser.parse_args()
    args.json_output = json_output

    # 全局 --profile：临时切换 profile（优先级高于 active_profile）
    if args.profile:
        os.environ["ZENSKILL_PROFILE"] = args.profile

    # 无命令时，TTY 环境启动 TUI，非 TTY 降级到 CLI 概览
    if args.command is None:
        if sys.stdin.isatty():
            try:
                import rich  # noqa: F401
                return safe_execute(cmd_tui, args)
            except ImportError:
                return safe_execute(cmd_default_overview, args)
        else:
            return safe_execute(cmd_default_overview, args)

    # 安全执行命令
    if hasattr(args, "func"):
        return safe_execute(args.func, args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
