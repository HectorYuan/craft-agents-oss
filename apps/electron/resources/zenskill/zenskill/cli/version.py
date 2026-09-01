"""version 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

from ..cli_utils import output as cli_output
from ..cli_helpers import _runtime_storage_dir


def cmd_version_list(args: argparse.Namespace) -> None:
    """列出所有技能版本"""
    from ..runtime import VersionTracker

    tracker = VersionTracker(_runtime_storage_dir() / "versions.json")
    versions = tracker.get_all_versions()

    def _text():
        if not versions:
            return "  暂无注册的技能版本\n  使用 'zenskill version register <id> <version>' 注册"
        lines = ["  技能版本:", ""]
        for skill_id, ver in sorted(versions.items()):
            info = tracker.get_version_info(skill_id)
            flag = " ⬆ 可升级" if info and info.upgrade_available else ""
            lines.append(f"  • {skill_id}: {ver}{flag}")
        return "\n".join(lines)

    cli_output({"versions": versions}, args, text=_text)



def cmd_version_register(args: argparse.Namespace) -> None:
    """注册技能版本"""
    from ..runtime import VersionTracker

    tracker = VersionTracker(_runtime_storage_dir() / "versions.json")
    info = tracker.register(args.skill, args.version)

    cli_output(info.to_dict(), args, text=lambda: (
        f"✅ 已注册技能版本\n"
        f"   技能: {info.skill_id}\n"
        f"   版本: {info.current_version}"
    ))



def cmd_upgrade_check(args: argparse.Namespace) -> None:
    """检查技能更新"""
    import asyncio
    from ..runtime import VersionTracker, RollbackManager, UpgradeManager

    tracker = VersionTracker(_runtime_storage_dir() / "versions.json")
    rollback_mgr = RollbackManager(_runtime_storage_dir() / "rollback.json")
    manager = UpgradeManager(tracker, rollback_mgr)

    skill_ids = list(tracker.get_all_versions().keys())
    if not skill_ids:
        print("  暂无注册的技能，无法检查更新")
        return

    async def _check():
        return await manager.check_updates(skill_ids)

    updates = asyncio.run(_check())

    def _text():
        if not updates:
            return "  ✅ 所有技能均为最新版本"
        lines = ["  可升级的技能:", ""]
        for u in updates:
            lines.append(f"  • {u.skill_id}: {u.current_version} → {u.latest_version}")
        return "\n".join(lines)

    cli_output({"updates": [u.to_dict() for u in updates]}, args, text=_text)



def cmd_upgrade_apply(args: argparse.Namespace) -> None:
    """执行技能升级"""
    import asyncio
    from ..runtime import VersionTracker, RollbackManager, UpgradeManager

    tracker = VersionTracker(_runtime_storage_dir() / "versions.json")
    rollback_mgr = RollbackManager(_runtime_storage_dir() / "rollback.json")
    manager = UpgradeManager(tracker, rollback_mgr)

    async def _upgrade():
        return await manager.upgrade(
            skill_id=args.skill,
            target_version=args.version,
            snapshot_data={"version": tracker.get_version_info(args.skill).current_version}
            if tracker.get_version_info(args.skill) else None,
        )

    result = asyncio.run(_upgrade())

    def _text():
        if result.success:
            rp = f"\n   回滚点: {result.rollback_point.point_id}" if result.rollback_point else ""
            return (
                f"✅ 升级成功\n"
                f"   技能: {result.skill_id}\n"
                f"   {result.old_version} → {result.new_version}{rp}"
            )
        return f"❌ 升级失败: {result.error}"

    cli_output(result.to_dict(), args, text=_text)



def cmd_upgrade_rollback(args: argparse.Namespace) -> None:
    """回滚到指定回滚点"""
    import asyncio
    from ..runtime import VersionTracker, RollbackManager, UpgradeManager

    tracker = VersionTracker(_runtime_storage_dir() / "versions.json")
    rollback_mgr = RollbackManager(_runtime_storage_dir() / "rollback.json")
    manager = UpgradeManager(tracker, rollback_mgr)

    async def _rollback():
        return await manager.rollback(args.point_id)

    snapshot = asyncio.run(_rollback())

    def _text():
        if snapshot is None:
            return f"❌ 回滚点不存在: {args.point_id}"
        return f"✅ 已回滚\n   快照数据: {snapshot}"

    cli_output({"snapshot": snapshot}, args, text=_text)



def register_version_parser(subparsers) -> None:
    """注册 version 子命令组。"""
    version_parser = subparsers.add_parser("version", help="版本跟踪 (Phase 12.5)")
    version_sub = version_parser.add_subparsers(dest="subcommand", help="版本操作")
    version_list_p = version_sub.add_parser("list", help="列出所有技能版本")
    version_list_p.set_defaults(func=cmd_version_list)
    version_reg_p = version_sub.add_parser("register", help="注册技能版本")
    version_reg_p.add_argument("skill", help="技能ID")
    version_reg_p.add_argument("version", help="版本号 (如 1.0.0)")
    version_reg_p.set_defaults(func=cmd_version_register)

