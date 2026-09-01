"""
Claude Code 生态采集器

History / Memory / Plans / Tasks / CoreSettings / Sessions / FileHistory / ShellSnapshots
"""

from .history import ClaudeHistoryCollector
from .memory import ClaudeMemoryCollector
from .plans import ClaudePlansCollector
from .tasks import ClaudeTasksCollector
from .settings import CoreSettingsCollector
from .meta import (
    ClaudeSessionCollector,
    ClaudeFileHistoryCollector,
    ClaudeShellSnapshotCollector,
)

__all__ = [
    "ClaudeHistoryCollector",
    "ClaudeMemoryCollector",
    "ClaudePlansCollector",
    "ClaudeTasksCollector",
    "CoreSettingsCollector",
    "ClaudeSessionCollector",
    "ClaudeFileHistoryCollector",
    "ClaudeShellSnapshotCollector",
]
