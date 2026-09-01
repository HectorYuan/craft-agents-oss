"""
事件采集器

Phase 9A: 用户画像数据层
统一的事件采集 API，所有交互自动记录元数据
"""

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from zenskill.core.paths import append_jsonl_locked, atomic_write_text, file_lock

from .models import EventType, InteractionEvent
from .privacy_layer import PrivacyLayer


class EventCollector:
    """事件采集器"""

    def __init__(self, data_dir: Optional[Path] = None):
        self._mirroring_dir = data_dir or self._get_default_dir()
        self._mirroring_dir.mkdir(parents=True, exist_ok=True)
        self._events_file = self._mirroring_dir / "events.jsonl"
        self._privacy = PrivacyLayer(data_dir=data_dir)
        self._session_id = uuid.uuid4().hex[:12]

    @staticmethod
    def _get_default_dir() -> Path:
        from zenskill.core.paths import get_mirroring_dir
        return get_mirroring_dir()

    def start_session(self) -> str:
        """开始新会话，返回 session_id"""
        self._session_id = uuid.uuid4().hex[:12]
        return self._session_id

    def record(
        self,
        event_type: EventType,
        skill_id: str,
        action: str,
        success: bool = True,
        duration_ms: float = 0,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        记录一条事件

        Args:
            event_type: 事件类型
            skill_id: 技能 ID
            action: 操作描述
            success: 是否成功
            duration_ms: 执行时长(毫秒)
            context: 附加上下文

        Returns:
            event_id
        """
        if not self._privacy.should_collect(event_type):
            return ""

        ctx = dict(context or {})
        # 过滤敏感数据
        ctx = self._privacy.filter_sensitive_data(ctx)
        # 可选加密
        ctx = self._privacy.encrypt_sensitive(ctx)

        event = InteractionEvent.create(
            event_type=event_type,
            skill_id=skill_id,
            action=action,
            success=success,
            duration_ms=duration_ms,
            context=ctx,
            session_id=self._session_id,
        )

        self._append_event(event)
        return event.event_id

    def _append_event(self, event: InteractionEvent) -> None:
        """追加事件到 JSONL 文件（非关键路径，锁超时静默跳过）"""
        try:
            append_jsonl_locked(self._events_file, event.to_dict())
        except TimeoutError:
            pass  # 遥测事件丢失不影响核心功能

    # === 便捷方法 ===

    def record_skill_execution(
        self,
        skill_id: str,
        task: str,
        success: bool,
        duration_ms: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """记录技能执行事件"""
        return self.record(
            event_type=EventType.SKILL_EXEC,
            skill_id=skill_id,
            action=task[:200] if task else "",
            success=success,
            duration_ms=duration_ms,
            context=context,
        )

    def record_user_input(
        self,
        skill_id: str,
        input_text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """记录用户输入事件（数据最小化：只存 hash 和长度）"""
        ctx = dict(context or {})
        ctx.update(self._privacy.hash_user_input(input_text))
        return self.record(
            event_type=EventType.USER_INPUT,
            skill_id=skill_id,
            action="user_input",
            success=True,
            duration_ms=0,
            context=ctx,
        )

    def record_memory_op(
        self,
        skill_id: str,
        op_type: str,
        content_preview: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """记录记忆操作事件"""
        ctx = dict(context or {})
        ctx["op_type"] = op_type
        if content_preview:
            ctx["content_preview"] = content_preview[:100]
        return self.record(
            event_type=EventType.MEMORY_OP,
            skill_id=skill_id,
            action=f"memory_{op_type}",
            success=True,
            duration_ms=0,
            context=ctx,
        )

    def record_session_event(
        self,
        event_type: EventType,
        skill_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """记录会话事件（SESSION_START / SESSION_END）"""
        return self.record(
            event_type=event_type,
            skill_id=skill_id,
            action=event_type.value,
            success=True,
            duration_ms=0,
            context=context,
        )

    def record_level_up(
        self,
        skill_id: str,
        old_level: str,
        new_level: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """记录境界突破事件"""
        ctx = dict(context or {})
        ctx["old_level"] = old_level
        ctx["new_level"] = new_level
        return self.record(
            event_type=EventType.LEVEL_UP,
            skill_id=skill_id,
            action=f"{old_level} -> {new_level}",
            success=True,
            duration_ms=0,
            context=ctx,
        )

    def record_error(
        self,
        skill_id: str,
        error_msg: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """记录错误事件"""
        ctx = dict(context or {})
        ctx["error"] = error_msg[:200]  # 截断错误消息
        return self.record(
            event_type=EventType.ERROR,
            skill_id=skill_id,
            action="error",
            success=False,
            duration_ms=0,
            context=ctx,
        )

    # === 查询方法 ===

    def _read_all_events(self) -> List[InteractionEvent]:
        """读取所有事件"""
        if not self._events_file.exists():
            return []
        events = []
        with open(self._events_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(InteractionEvent.from_dict(json.loads(line)))
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
        return events

    def query(
        self,
        event_type: Optional[EventType] = None,
        skill_id: Optional[str] = None,
        since: Optional[float] = None,
        limit: int = 100,
    ) -> List[InteractionEvent]:
        """查询事件"""
        events = self._read_all_events()

        if event_type is not None:
            events = [e for e in events if e.event_type == event_type]
        if skill_id is not None:
            events = [e for e in events if e.skill_id == skill_id]
        if since is not None:
            events = [e for e in events if e.timestamp >= since]

        return events[-limit:]

    def get_event_count(self) -> int:
        """获取事件总数"""
        if not self._events_file.exists():
            return 0
        count = 0
        with open(self._events_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count

    def get_events_since(self, timestamp: float) -> List[InteractionEvent]:
        """获取指定时间之后的所有事件"""
        return self.query(since=timestamp)

    def get_session_events(self, session_id: str) -> List[InteractionEvent]:
        """获取指定会话的所有事件"""
        events = self._read_all_events()
        return [e for e in events if e.session_id == session_id]

    def purge_old_events(self) -> int:
        """清理超过保留期限的旧事件，返回清理数量"""
        retention_days = self._privacy.get_prefs().retention_days
        threshold = time.time() - (retention_days * 86400)

        if not self._events_file.exists():
            return 0

        kept = []
        purged = 0
        with file_lock(self._events_file, timeout=2.0):
            with open(self._events_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        if event.get("timestamp", 0) >= threshold:
                            kept.append(line)
                        else:
                            purged += 1
                    except (json.JSONDecodeError, KeyError):
                        kept.append(line)

            if purged > 0:
                content = "\n".join(kept)
                atomic_write_text(self._events_file, content + "\n" if content else "")

        return purged
