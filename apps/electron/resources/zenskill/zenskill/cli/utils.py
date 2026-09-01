"""CLI 共享工具函数（从 __main__.py 提取，保持向后兼容）。"""
from __future__ import annotations

import argparse
import json
from typing import Any, Callable


def str_section(title: str, emoji: str = "", phase: str = "") -> str:
    tag = f" — Phase {phase}" if phase else ""
    return f"\n  {emoji} {title}{tag}\n  {'═' * 62}"


def str_box_header(title: str, emoji: str = "") -> str:
    line = f"  ┌─ {emoji} {title} " if emoji else f"  ┌─ {title} "
    return "\n" + line + "─" * max(0, 58 - len(line) + 1)


def str_box_footer() -> str:
    return f"  └{'─' * 60}"


def safe_execute(func: Callable[..., Any], args: argparse.Namespace) -> int:
    """安全执行命令，捕获异常并给出修复建议"""
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
    except json.JSONDecodeError as e:
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
        if getattr(args, "debug", False):
            import traceback
            traceback.print_exc()
        return 1


def runtime_storage_dir():
    """获取 Runtime 存储目录 ~/.zenskill/profiles/{active}/runtime/"""
    from ..core.paths import get_user_data_dir
    d = get_user_data_dir() / "runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d
