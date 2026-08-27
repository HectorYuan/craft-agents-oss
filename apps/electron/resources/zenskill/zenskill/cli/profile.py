"""profile 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

def cmd_profile_list(args: argparse.Namespace) -> None:
    """列出所有 profile"""
    from .core.paths import list_profiles, get_active_profile

    profiles = list_profiles()
    active = get_active_profile()

    result = {
        "profiles": profiles,
        "active": active,
        "count": len(profiles),
    }

    def _text():
        lines = [""]
        lines.append("  👥 Profile 列表")
        lines.append("  ═══════════════════════════════════════")
        for p in profiles:
            marker = "🟢" if p == active else "⚪"
            lines.append(f"  {marker} {p}")
        lines.append(f"\n  共 {len(profiles)} 个 profile，当前激活: {active}")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_profile_create(args: argparse.Namespace) -> None:
    """创建新 profile"""
    from .core.paths import create_profile, list_profiles, get_active_profile

    try:
        profile_dir = create_profile(args.name)
        result = {
            "created": args.name,
            "path": str(profile_dir),
            "profiles": list_profiles(),
        }
        print(f"\n  ✅ Profile '{args.name}' 创建成功")
        print(f"  📂 数据目录: {profile_dir}")
        print(f"\n  💡 切换到新 profile: zenskill profile switch {args.name}")
    except ValueError as e:
        print(f"\n  ❌ 创建失败: {e}")
        return

    cli_output(result, args, text=None)


def cmd_profile_switch(args: argparse.Namespace) -> None:
    """切换激活的 profile"""
    from .core.paths import set_active_profile, get_active_profile, list_profiles

    profiles = list_profiles()
    if args.name not in profiles:
        print(f"\n  ❌ Profile '{args.name}' 不存在")
        print(f"  📋 可用 profile: {', '.join(profiles)}")
        return

    set_active_profile(args.name)
    result = {
        "switched_to": args.name,
        "previous": get_active_profile(),  # 已经是新的了
        "profiles": profiles,
    }

    print(f"\n  ✅ 已切换到 profile: {args.name}")
    print(f"  💡 所有后续命令将使用 '{args.name}' 的数据空间")


def cmd_profile_info(args: argparse.Namespace) -> None:
    """查看 profile 详情"""
    from .core.paths import (get_profile_dir, get_active_profile,
                             list_profiles, get_global_dir)

    name = args.name if args.name else get_active_profile()
    profiles = list_profiles()

    if name not in profiles:
        print(f"\n  ❌ Profile '{name}' 不存在")
        return

    profile_dir = get_profile_dir(name)
    active = get_active_profile()
    is_active = (name == active)

    # 统计各子目录大小
    sizes = {}
    for subdir in profile_dir.iterdir():
        if subdir.is_dir():
            total = sum(f.stat().st_size for f in subdir.rglob("*") if f.is_file())
            sizes[subdir.name] = total

    total_size = sum(sizes.values())

    def _format_size(b: int) -> str:
        if b > 1024 * 1024:
            return f"{b / (1024 * 1024):.1f} MB"
        elif b > 1024:
            return f"{b / 1024:.1f} KB"
        return f"{b} B"

    result = {
        "name": name,
        "is_active": is_active,
        "path": str(profile_dir),
        "total_size": total_size,
        "sizes": {k: _format_size(v) for k, v in sizes.items()},
    }

    def _text():
        lines = [""]
        marker = "🟢" if is_active else "⚪"
        lines.append(f"  {marker} Profile: {name}")
        lines.append("  ═══════════════════════════════════════")
        lines.append(f"  📂 路径: {profile_dir}")
        lines.append(f"  📊 总大小: {_format_size(total_size)}")
        lines.append(f"  🌐 全局目录: {get_global_dir()}")
        if sizes:
            lines.append("")
            lines.append("  ┌─ 子目录大小 ─────────────────────────")
            for sub, size in sorted(sizes.items(), key=lambda x: -x[1]):
                bar_len = min(20, int(size / max(1, total_size) * 20))
                bar = "█" * bar_len + "░" * (20 - bar_len)
                lines.append(f"  │ {sub:<20} {bar} {_format_size(size)}")
            lines.append("  └──────────────────────────────────────")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_profile_delete(args: argparse.Namespace) -> None:
    """删除 profile"""
    from .core.paths import delete_profile, list_profiles, get_active_profile

    if not args.force:
        print(f"\n  ⚠️  即将删除 profile '{args.name}' 及其所有数据！")
        print(f"  📋 此操作不可逆。")
        try:
            confirm = input(f"  输入 profile 名称以确认删除: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  ❌ 已取消")
            return
        if confirm != args.name:
            print(f"  ❌ 名称不匹配，已取消")
            return

    try:
        delete_profile(args.name)
        result = {
            "deleted": args.name,
            "remaining": list_profiles(),
        }
        print(f"\n  ✅ Profile '{args.name}' 已删除")
        print(f"  📋 剩余 profile: {', '.join(list_profiles())}")
    except ValueError as e:
        print(f"\n  ❌ 删除失败: {e}")


def cmd_profile_migrate(args: argparse.Namespace) -> None:
    """迁移旧数据到 Profile 结构"""
    from .core.paths import migrate_to_profile_structure

    dry_run = getattr(args, 'dry_run', False)
    do_backup = not getattr(args, 'no_backup', False)

    result = migrate_to_profile_structure(dry_run=dry_run, backup=do_backup)

    if dry_run:
        print(f"\n  🔍 迁移预览（dry-run 模式）")
        print("  ═══════════════════════════════════════")
        print(f"  待迁移: {len(result.get('to_migrate', []))} 项")
        for item in result.get('to_migrate', []):
            print(f"    → {item['name']} ({item['type']})")
        print(f"  跳过: {len(result.get('to_skip', []))} 项")
        return

    if result.get("migrated"):
        print(f"\n  ✅ 数据已迁移到 Profile 结构")
        print(f"  📂 Profile: {result.get('profile', 'default')}")
        if result.get("backup_path"):
            print(f"  💾 备份: {result['backup_path']}")
        print(f"  📊 迁移项: {result.get('migrated_count', 0)}")
    elif result.get("reason") == "already_migrated":
        print(f"\n  ℹ️  数据已经是 Profile 结构，无需迁移")
    else:
        print(f"\n  ℹ️  无可迁移的数据: {result.get('reason', 'unknown')}")


def cmd_profile_rename(args: argparse.Namespace) -> None:
    """重命名 profile"""
    import shutil
    from .core.paths import (_profile_exists, get_profile_dir, get_active_profile,
                             set_active_profile, DEFAULT_PROFILE)

    old_name = args.old_name
    new_name = args.new_name

    if old_name == DEFAULT_PROFILE:
        print(f"\n  ❌ 不能重命名 default profile")
        return
    if not _profile_exists(old_name):
        print(f"\n  ❌ Profile '{old_name}' 不存在")
        return
    if _profile_exists(new_name):
        print(f"\n  ❌ Profile '{new_name}' 已存在")
        return

    old_dir = get_profile_dir(old_name)
    new_dir = get_profile_dir(new_name)

    # 如果新目录已经自动创建了，先删除
    if new_dir.exists() and not any(new_dir.iterdir()):
        new_dir.rmdir()

    shutil.move(str(old_dir), str(new_dir))

    # 如果当前激活的是旧 profile，更新激活状态
    if get_active_profile() == old_name:
        set_active_profile(new_name)

    result = {
        "renamed_from": old_name,
        "renamed_to": new_name,
    }
    print(f"\n  ✅ Profile 已重命名: {old_name} → {new_name}")



def register_profile_parser(subparsers) -> None:
    """注册 profile 子命令组。"""
    profile_parser = subparsers.add_parser("profile",
        help="Profile 管理 — 多用户/多场景数据隔离",
        description="管理本地 Profile，每个 Profile 拥有独立的数据空间。",
        epilog="示例:\n"
               "  zenskill profile list               - 列出所有 profile\n"
               "  zenskill profile create work         - 创建工作 profile\n"
               "  zenskill profile switch work         - 切换到工作 profile\n"
               "  zenskill profile info                - 查看当前 profile 详情\n"
               "  zenskill profile delete test         - 删除 test profile\n"
               "  zenskill --profile work skill info   - 在指定 profile 下运行命令",
    )
    profile_subparsers = profile_parser.add_subparsers(dest="subcommand",
                                                        help="Profile 操作")

    # profile list
    profile_list_parser = profile_subparsers.add_parser("list", help="列出所有 profile")
    profile_list_parser.set_defaults(func=cmd_profile_list)

    # profile create
    profile_create_parser = profile_subparsers.add_parser("create", help="创建新 profile")
    profile_create_parser.add_argument("name", help="profile 名称（字母/数字/下划线/连字符）")
    profile_create_parser.set_defaults(func=cmd_profile_create)

    # profile switch
    profile_switch_parser = profile_subparsers.add_parser("switch", help="切换当前激活的 profile")
    profile_switch_parser.add_argument("name", help="目标 profile 名称")
    profile_switch_parser.set_defaults(func=cmd_profile_switch)

    # profile info
    profile_info_parser = profile_subparsers.add_parser("info", help="查看当前 profile 详情")
    profile_info_parser.add_argument("--name", default=None, help="指定 profile 名称（默认当前）")
    profile_info_parser.set_defaults(func=cmd_profile_info)

    # profile delete
    profile_delete_parser = profile_subparsers.add_parser("delete", help="删除 profile 及其所有数据")
    profile_delete_parser.add_argument("name", help="要删除的 profile 名称")
    profile_delete_parser.add_argument("--force", action="store_true",
                                       help="跳过确认，直接删除")
    profile_delete_parser.set_defaults(func=cmd_profile_delete)

    # profile migrate
    profile_migrate_parser = profile_subparsers.add_parser(
        "migrate", help="将旧版单用户数据迁移到 Profile 结构"
    )
    profile_migrate_parser.add_argument("--dry-run", action="store_true",
                                        help="预览迁移结果，不实际执行")
    profile_migrate_parser.add_argument("--no-backup", action="store_true",
                                        help="跳过备份步骤")
    profile_migrate_parser.set_defaults(func=cmd_profile_migrate)

    # profile rename
    profile_rename_parser = profile_subparsers.add_parser("rename", help="重命名 profile")
    profile_rename_parser.add_argument("old_name", help="当前名称")
    profile_rename_parser.add_argument("new_name", help="新名称")
    profile_rename_parser.set_defaults(func=cmd_profile_rename)

    # doctor 命令
