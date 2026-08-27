"""data 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

def cmd_data_paths(args: argparse.Namespace) -> None:
    """显示所有数据目录路径"""
    layout = get_data_layout()
    paths_info = {}
    for k, v in sorted(layout.items()):
        if v:
            from pathlib import Path
            paths_info[k] = {"path": v, "exists": Path(v).exists()}

    def _text():
        lines = ["📂 ZenSkill 数据目录", "=" * 60, ""]
        from pathlib import Path
        for k, v in sorted(layout.items()):
            if v:
                path = Path(v)
                exists = "✅" if path.exists() else "❌"
                lines.append(f"{exists} {k:20s}: {v}")
        lines.append("")
        lines.append("💡 提示: 可以直接打开这些目录查看或备份数据")
        return "\n".join(lines)

    cli_output({"paths": paths_info}, args, text=_text)


def cmd_data_stats(args: argparse.Namespace) -> None:
    """显示详细的数据统计"""
    from pathlib import Path
    from datetime import datetime

    layout = get_data_layout()

    mgr = SkillStateManager(args.skill_id)
    state = mgr.load()

    # 预计算所有统计数据
    metrics_dir = Path(layout.get('metrics_dir', ''))
    snapshot_count = 0
    total_points = 0
    if metrics_dir.exists():
        snapshots = list(metrics_dir.glob('*.jsonl'))
        snapshot_count = len(snapshots)
        total_points = sum(1 for f in snapshots for _ in open(f, encoding='utf-8'))

    ceremony_dir = Path(layout.get('ceremony_dir', ''))
    ceremony_count = 0
    if ceremony_dir.exists():
        ceremonies = list(ceremony_dir.glob('*.txt'))
        ceremony_count = len(ceremonies)

    zenloop_dir = Path(layout.get('zenloop_dir', ''))
    reflection_count = 0
    if zenloop_dir.exists():
        reflections = list(zenloop_dir.glob('reflection_*.md'))
        reflection_count = len(reflections)

    history = mgr.get_history(limit=100)
    first_ts = history[0].get('timestamp', 'N/A') if history else 'N/A'
    last_ts = history[-1].get('timestamp', 'N/A') if history else 'N/A'

    result = {
        "skill_id": args.skill_id,
        "level": state.get('level', 'NOVICE'),
        "usage_count": state.get('usage_count', 0),
        "episode_count": len(state.get('episodes', [])),
        "milestone_count": len(state.get('milestones', [])),
        "snapshot_count": snapshot_count,
        "total_data_points": total_points,
        "ceremony_count": ceremony_count,
        "reflection_count": reflection_count,
        "history_versions": len(history),
        "first_record": first_ts,
        "last_record": last_ts,
    }

    def _text():
        lines = ["📊 ZenSkill 数据统计", "=" * 60, ""]
        lines.append(f"🎯 状态数据 ({args.skill_id}):")
        lines.append(f"   当前境界:        {state.get('level', 'NOVICE')}")
        lines.append(f"   使用次数:        {state.get('usage_count', 0)} 次")
        lines.append(f"   记忆条目:        {len(state.get('episodes', []))} 条")
        lines.append(f"   里程碑数:        {len(state.get('milestones', []))} 个")
        lines.append("")

        if snapshot_count:
            lines.append(f"📈 成长指标:")
            lines.append(f"   快照文件:        {snapshot_count} 个")
            lines.append(f"   数据点总数:      {total_points} 个")
            lines.append("")

        if ceremony_count:
            lines.append(f"🏆 境界仪式:")
            lines.append(f"   突破记录:        {ceremony_count} 次")
            lines.append("")

        if reflection_count:
            lines.append(f"🧘 禅思反思:")
            lines.append(f"   反思报告:        {reflection_count} 份")
            lines.append("")

        lines.append(f"📜 历史记录:")
        lines.append(f"   总版本数:        {len(history)} 个")
        if history:
            lines.append(f"   最早记录:        {first_ts}")
            lines.append(f"   最新记录:        {last_ts}")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_data_export(args: argparse.Namespace) -> None:
    """导出所有数据进行备份"""
    import json
    import shutil
    from pathlib import Path
    from datetime import datetime

    layout = get_data_layout()
    output_dir = Path(args.output) if args.output else Path.cwd() / "zenskill_backup"
    if output_dir.is_dir():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = output_dir / f"zenskill_export_{timestamp}"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_dir = output_dir

    try:
        export_dir.mkdir(parents=True, exist_ok=True)

        exported = 0
        # 遍历所有数据目录
        for key, path_str in layout.items():
            if not path_str:
                continue
            p = Path(path_str)
            if not p.exists():
                continue
            dest = export_dir / key
            try:
                if p.is_dir():
                    shutil.copytree(p, dest, dirs_exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, dest)
                exported += 1
            except Exception:
                pass

        # 导出清单文件
        manifest = {
            "exported_at": datetime.now().isoformat(),
            "version": __version__,
            "contents": [
                "state",
                "metrics",
                "ceremonies",
                "zenloop",
                "history"
            ]
        }
        with open(export_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        result = {
            "ok": True,
            "export_dir": str(export_dir),
            "exported_dirs": exported,
            "manifest": manifest,
        }

        def _text():
            lines = ["📦 ZenSkill 数据导出", "=" * 60, ""]
            if exported > 0:
                lines.append(f"✅ 已导出 {exported} 个数据目录")
            else:
                lines.append("⚠️  无数据可导出")
            lines.append("")
            lines.append(f"🎉 导出完成！")
            lines.append(f"   导出目录: {export_dir}")
            lines.append("")
            lines.append(f"💡 提示: 可以通过 'python -m zenskill memory import' 导入备份")
            return "\n".join(lines)

        cli_output(result, args, text=_text)

    except Exception as e:
        print(f"❌ 导出失败: {e}")
        raise


# ====================================================================
# LLM 服务命令
# ====================================================================


def register_data_parser(subparsers) -> None:
    """注册 data 子命令组。"""
    data_parser = subparsers.add_parser("data", help="数据管理工具")
    data_subparsers = data_parser.add_subparsers(dest="subcommand", help="数据操作")

    # data paths
    paths_parser = data_subparsers.add_parser("paths", help="显示所有数据目录路径")
    paths_parser.set_defaults(func=cmd_data_paths)

    # data export
    data_export_parser = data_subparsers.add_parser("export", help="导出所有数据（全量备份）")
    data_export_parser.add_argument("--output", help="输出目录（默认: ./zenskill_backup）")
    data_export_parser.set_defaults(func=cmd_data_export)

    # data stats
    stats_parser = data_subparsers.add_parser("stats", help="显示数据统计")
    stats_parser.add_argument("--skill-id", default="zenskill-core", help="技能ID")
    stats_parser.set_defaults(func=cmd_data_stats)

    # _internal 内部命令（hook 等内部调用）
