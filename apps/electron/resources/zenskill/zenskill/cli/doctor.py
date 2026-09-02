"""doctor 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

from ..cli_utils import output as cli_output
from ..core.paths import get_data_layout

def cmd_doctor_snapshot(args: argparse.Namespace) -> None:
    """创建/管理数据快照"""
    from ..core.snapshot import create_snapshot, list_snapshots, restore_snapshot

    if getattr(args, 'subsubcommand', None) == 'list':
        snapshots = list_snapshots()
        result = {
            "command": "snapshot_list",
            "count": len(snapshots),
            "snapshots": [s.to_dict() for s in snapshots],
        }
        def _text():
            lines = []
            lines.append("")
            lines.append("  📸 快照列表")
            lines.append(f"  ══════════════════════════════════════════════════════════════")
            if not snapshots:
                lines.append("  (无快照)")
            for s in snapshots:
                lines.append(f"  {s.id}  |  {s.file_count} 文件  |  {s.timestamp}")
            lines.append("")
            return "\n".join(lines)
        cli_output(result, args, text=_text)
        return

    if getattr(args, 'subsubcommand', None) == 'restore':
        snap_id = getattr(args, 'restore_id', '')
        dry = getattr(args, 'dry_run', False)
        try:
            res = restore_snapshot(snap_id, dry_run=dry)
            cli_output(res, args, text=lambda: (
                f"\n  📥 快照{'预览' if dry else '恢复'}: {snap_id}\n"
                f"     文件数: {res['restored_files']}"
                + ("\n     (dry-run, 未实际修改)" if dry else "")
                + "\n"
            ))
        except FileNotFoundError as e:
            print(f"\n  ❌ {e}\n")
            sys.exit(2)
        return

    # default: create
    info = create_snapshot()
    result = info.to_dict()
    cli_output(result, args, text=lambda: (
        f"\n"
        f"  📸 快照已创建\n"
        f"  ══════════════════════════════════════════════════════════════\n"
        f"  ID:       {info.id}\n"
        f"  文件数:   {info.file_count}\n"
        f"  时间:     {info.timestamp}\n"
        f"  路径:     {info.path}\n"
    ))


def cmd_doctor_state(args: argparse.Namespace) -> None:
    """状态数据完整性扫描"""
    from ..core.state_doctor import scan_state_integrity

    report = scan_state_integrity()
    result = report.to_dict()

    problem_files = [
        item for group in (report.states, report.histories, report.events, report.metrics)
        for item in group
        if not item.ok
    ]

    def _text():
        status_icon = {
            "healthy": "🟢 健康",
            "degraded": "🟡 降级",
            "critical": "🔴 严重",
        }.get(report.status, report.status)

        lines = []
        lines.append("")
        lines.append("  🩺 状态完整性扫描 — Doctor State")
        lines.append("  ══════════════════════════════════════════════════════════════")
        lines.append("")
        lines.append(f"  {status_icon}")
        lines.append("")
        lines.append("  ┌─ 📊 数据统计 ────────────────────────────────────────────")
        for key, value in report.summary.items():
            lines.append(f"  │  {key:24s} {value}")
        lines.append("  └───────────────────────────────────────────────────────────")
        lines.append("")

        if problem_files:
            lines.append("  ┌─ ⚠️  问题文件 ───────────────────────────────────────────")
            for item in problem_files:
                detail = item.error or f"坏行 {item.bad_lines}/{item.total_lines}"
                lines.append(f"  │  {item.path}")
                lines.append(f"  │    {detail}")
            lines.append("  └───────────────────────────────────────────────────────────")
            lines.append("")

        if report.corrupted_backups:
            lines.append("  ┌─ 🧾 Corrupted 备份 ─────────────────────────────────────")
            for path in report.corrupted_backups[:10]:
                lines.append(f"  │  {path}")
            if len(report.corrupted_backups) > 10:
                lines.append(f"  │  ... 还有 {len(report.corrupted_backups) - 10} 个")
            lines.append("  └───────────────────────────────────────────────────────────")
            lines.append("")

        lines.append("  ┌─ 💡 建议 ────────────────────────────────────────────────")
        for suggestion in report.suggestions:
            lines.append(f"  │  {suggestion}")
        lines.append("  └───────────────────────────────────────────────────────────")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_doctor_diagnostics(args: argparse.Namespace) -> None:
    """查看诊断日志"""
    from ..core.diagnostics import read_diagnostics

    n = getattr(args, 'n', 50)
    records = read_diagnostics(n=n)
    result = {"count": len(records), "records": records}

    def _text():
        lines = []
        lines.append("")
        lines.append(f"  📋 诊断日志 (最近 {len(records)} 条)")
        lines.append(f"  ══════════════════════════════════════════════════════════════")
        if not records:
            lines.append("  (无记录)")
            lines.append("")
            return "\n".join(lines)
        lines.append("")

        for r in records:
            ts = r.get("ts", "?")[:19]
            event = r.get("event", "?")
            rest = {k: v for k, v in r.items() if k not in ("ts", "event")}
            detail = ", ".join(f"{k}={v}" for k, v in rest.items())
            lines.append(f"  {ts}  {event:25s}  {detail}" if detail else f"  {ts}  {event}")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


# ================================================================
# 9T: 技能包管理命令
# ================================================================

def cmd_doctor_migrate(args: argparse.Namespace) -> None:
    """数据迁移版本化"""
    from ..core.paths import SkillStateManager, get_user_data_dir

    dry_run = getattr(args, 'dry_run', False)
    migrate_all = getattr(args, 'all', False)
    states_dir = get_user_data_dir() / "states"

    if migrate_all and states_dir.exists():
        state_files = sorted(
            p for p in states_dir.glob("*.json")
            if not p.name.endswith(".history.jsonl") and ".corrupted." not in p.name
        )
    else:
        state_files = []

    # 总是检查 zenskill-core
    results = []
    for skill_id in [args.skill_id] + [f.stem for f in state_files if f.stem != args.skill_id]:
        mgr = SkillStateManager(skill_id)
        info = mgr.get_migration_info()
        if info["needs_migration"]:
            r = mgr.migrate(dry_run=dry_run)
            results.append(r)

    result = {
        "dry_run": dry_run,
        "migrated_count": sum(1 for r in results if r.get("migrated")),
        "results": results,
    }

    def _text():
        label = "预览" if dry_run else "迁移"
        lines = []
        lines.append("")
        lines.append(f"  📦 Schema {label} — Doctor Migrate")
        lines.append(f"  ══════════════════════════════════════════════════════════════")
        if dry_run:
            lines.append(f"  (dry-run 模式，不会实际修改文件)")
        lines.append("")

        if not results:
            lines.append("  ✅ 所有状态文件已是最新版本")
            lines.append("")
            return "\n".join(lines)

        for r in results:
            ver = f"v{r.get('from_version', '?')} → v{r.get('to_version', '?')}"
            lines.append(f"  {'🔧' if r.get('migrated') else '📋'} {r['skill_id']:30s} {ver}")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_doctor_repair(args: argparse.Namespace) -> None:
    """修复状态数据"""
    from ..core.state_doctor import repair_state_integrity
    from ..core.snapshot import create_snapshot

    dry_run = getattr(args, 'dry_run', False)

    # 修复前自动快照
    snap = None
    if not dry_run:
        snap = create_snapshot()

    report = repair_state_integrity(dry_run=dry_run)
    result = report.to_dict()
    if snap:
        result["pre_repair_snapshot"] = {"id": snap.id, "file_count": snap.file_count}

    def _text():
        label = "预览" if dry_run else "修复"
        lines = []

        if snap:
            lines.append(f"\n  📸 自动快照: {snap.id} ({snap.file_count} 文件)")

        lines.append("")
        lines.append(f"  🔧 状态数据{label} — Doctor Repair")
        lines.append(f"  ══════════════════════════════════════════════════════════════")
        if dry_run:
            lines.append(f"  (dry-run 模式，不会实际修改文件)")
        lines.append("")

        if not report.repairs:
            lines.append("  ✅ 没有需要修复的文件")
            lines.append("")
            return "\n".join(lines)

        lines.append(f"  ┌─ 📋 {label}项目 ────────────────────────────────────────────")
        for r in report.repairs:
            icon = "🔧" if r.action in ("recovered_json", "cleaned_jsonl") else "⏭️"
            lines.append(f"  │  {icon} {r.action:30s} {r.path}")
            if r.bad_lines_removed:
                lines.append(f"  │     移除坏行: {r.bad_lines_removed}")
            if r.backup:
                lines.append(f"  │     备份: {r.backup}")
            if r.error:
                lines.append(f"  │     错误: {r.error}")
        lines.append(f"  └───────────────────────────────────────────────────────────")
        lines.append("")

        if not dry_run:
            lines.append(f"  📊 已修复 {report.repaired_count} 个文件，跳过 {report.skipped_count} 个")
        else:
            lines.append(f"  📊 可修复 {report.repaired_count} 个文件，将跳过 {report.skipped_count} 个")

        for err in report.errors:
            lines.append(f"  ⚠️  {err}")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_doctor(args: argparse.Namespace) -> None:
    """系统健康检查"""
    import os
    import sys
    from pathlib import Path

    check_results = []  # [{name, ok, message}]

    # 1. Python 版本
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    check_results.append({
        "name": "python_version",
        "ok": sys.version_info >= (3, 9),
        "message": f"Python {py_version}" + ("" if sys.version_info >= (3, 9) else " (建议 3.9+)"),
    })

    # 2. 数据目录
    layout = get_data_layout()
    data_dir = Path(layout.get('user_data_dir', ''))
    check_results.append({
        "name": "data_dir",
        "ok": data_dir.exists(),
        "message": str(data_dir),
    })

    # 3. 状态文件
    state_file = Path(layout.get('state_file', ''))
    check_results.append({
        "name": "state_file",
        "ok": state_file.exists(),
        "message": "存在" if state_file.exists() else "不存在（首次使用自动创建）",
    })

    # 4. 指标目录
    metrics_dir = Path(layout.get('metrics_dir', ''))
    if metrics_dir.exists():
        snapshots = list(metrics_dir.glob('*.jsonl'))
        check_results.append({
            "name": "metrics_dir",
            "ok": True,
            "message": f"存在, {len(snapshots)} 个快照",
        })
    else:
        check_results.append({
            "name": "metrics_dir",
            "ok": False,
            "message": "不存在",
        })

    # 5. 仪式目录
    ceremony_dir = Path(layout.get('ceremony_dir', ''))
    if ceremony_dir.exists():
        ceremonies = list(ceremony_dir.glob('*.txt'))
        check_results.append({
            "name": "ceremony_dir",
            "ok": True,
            "message": f"{len(ceremonies)} 次记录",
        })
    else:
        check_results.append({
            "name": "ceremony_dir",
            "ok": False,
            "message": "不存在",
        })

    # 6. 记忆循环
    zenloop_dir = Path(layout.get('zenloop_dir', ''))
    if zenloop_dir.exists():
        reflections = list(zenloop_dir.glob('reflection_*.md'))
        check_results.append({
            "name": "zenloop_dir",
            "ok": True,
            "message": f"{len(reflections)} 次反思",
        })
    else:
        check_results.append({
            "name": "zenloop_dir",
            "ok": False,
            "message": "不存在",
        })

    # 7. 模块检查
    modules_to_check = [
        ('skill_manifest', 'zenskill.systems.cultivating.skill_manifest'),
        ('charts', 'zenskill.systems.visualization.charts'),
        ('metrics_store', 'zenskill.systems.visualization.metrics_store'),
        ('insight_engine', 'zenskill.systems.active.proactive_insight'),
        ('level_up_ceremony', 'zenskill.systems.cultivating.level_up_ceremony'),
    ]
    for name, full_mod in modules_to_check:
        try:
            __import__(full_mod)
            check_results.append({"name": f"module_{name}", "ok": True, "message": name})
        except ImportError as e:
            check_results.append({"name": f"module_{name}", "ok": False, "message": f"{name}: {e}"})

    # 构建输出
    ok_count = sum(1 for c in check_results if c["ok"])
    warn_count = sum(1 for c in check_results if not c["ok"])
    status = "healthy" if warn_count == 0 else "degraded"
    result = {
        "status": status,
        "checks": check_results,
        "summary": {"ok": ok_count, "warnings": warn_count},
    }

    def _text():
        ok_items = [c for c in check_results if c["ok"]]
        warn_items = [c for c in check_results if not c["ok"]]
        ok_pct = len(ok_items) / max(len(check_results), 1) * 100
        health = "🟢 优秀" if not warn_items else "🟡 良好" if len(warn_items) <= 2 else "🔴 需要修复"

        lines = []
        lines.append("")
        lines.append(f"  🩺 系统健康检查 — Doctor")
        lines.append(f"  ══════════════════════════════════════════════════════════════")
        lines.append("")
        lines.append(f"  {health}  |  {len(ok_items)}/{len(check_results)} 通过  |  {ok_pct:.0f}% 健康")
        lines.append("")
        lines.append(f"  ┌─ 📦 模块状态 ────────────────────────────────────────────")
        for c in check_results:
            icon = "🟢" if c["ok"] else "🔴"
            lines.append(f"  │  {icon} {c['name']:35s} {c['message']}")
        lines.append(f"  └───────────────────────────────────────────────────────────")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)



def register_doctor_parser(subparsers) -> None:
    """注册 doctor 子命令组。"""
    doctor_parser = subparsers.add_parser("doctor",
        help="系统健康检查",
        description="数据诊断与修复工具。数据文件位于 ~/.zenskill/ 目录下。",
        epilog="排障流程:\n"
               "  1. zenskill doctor state      扫描数据完整性\n"
               "  2. zenskill doctor repair     修复可恢复的文件(自动创建快照)\n"
               "  3. zenskill doctor snapshot   手动创建数据快照\n"
               "  4. zenskill doctor diagnostics 查看诊断日志\n"
               "  5. zenskill doctor migrate --all  升级状态文件版本",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    doctor_subparsers = doctor_parser.add_subparsers(dest="subcommand", help="诊断类型")
    doctor_state_parser = doctor_subparsers.add_parser("state", help="扫描状态数据完整性")
    doctor_state_parser.set_defaults(func=cmd_doctor_state)
    doctor_repair_parser = doctor_subparsers.add_parser("repair", help="修复可恢复的状态数据")
    doctor_repair_parser.add_argument("--dry-run", action="store_true", help="预览修复计划，不实际修改")
    doctor_repair_parser.set_defaults(func=cmd_doctor_repair)
    # doctor snapshot
    doctor_snapshot_parser = doctor_subparsers.add_parser("snapshot", help="管理数据快照")
    doctor_snap_sub = doctor_snapshot_parser.add_subparsers(dest="subsubcommand", help="快照操作")
    doctor_snap_list = doctor_snap_sub.add_parser("list", help="列出所有快照")
    doctor_snap_list.set_defaults(func=cmd_doctor_snapshot)
    doctor_snap_restore = doctor_snap_sub.add_parser("restore", help="恢复快照")
    doctor_snap_restore.add_argument("restore_id", help="快照 ID")
    doctor_snap_restore.add_argument("--dry-run", action="store_true", help="预览恢复计划")
    doctor_snap_restore.set_defaults(func=cmd_doctor_snapshot)
    doctor_snapshot_parser.set_defaults(func=cmd_doctor_snapshot)
    # doctor migrate
    doctor_migrate_parser = doctor_subparsers.add_parser("migrate", help="迁移状态 schema 版本")
    doctor_migrate_parser.add_argument("--dry-run", action="store_true", help="预览迁移计划")
    doctor_migrate_parser.add_argument("--all", action="store_true", help="迁移所有技能状态")
    doctor_migrate_parser.set_defaults(func=cmd_doctor_migrate)
    # doctor diagnostics
    doctor_diag_parser = doctor_subparsers.add_parser("diagnostics", help="查看诊断日志")
    doctor_diag_parser.add_argument("--n", type=int, default=50, help="显示最近 N 条 (默认 50)")
    doctor_diag_parser.set_defaults(func=cmd_doctor_diagnostics)
    doctor_parser.set_defaults(func=cmd_doctor)

    # ── Phase D: 数据库管理 ──
