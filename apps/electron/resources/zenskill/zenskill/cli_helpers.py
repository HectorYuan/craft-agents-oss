"""CLI 共享辅助函数 — 从 __main__.py 提取。"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .core.paths import SkillStateManager, get_user_data_dir
from .mirroring.collectors import collector_registry
from .mirroring.collectors.claude_code import (
    ClaudeFileHistoryCollector,
    ClaudeHistoryCollector,
    ClaudeMemoryCollector,
    ClaudePlansCollector,
    ClaudeSessionCollector,
    ClaudeShellSnapshotCollector,
    ClaudeTasksCollector,
    CoreSettingsCollector,
)
from .mirroring.collectors.zenskill import (
    ZenskillEventCollector,
    ZenskillMemoryCollector,
    ZenskillZenloopCollector,
)


def _runtime_storage_dir():
    """获取 Runtime 存储目录 ~/.zenskill/profiles/{active}/runtime/"""
    from .core.paths import get_user_data_dir
    d = get_user_data_dir() / "runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d

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
