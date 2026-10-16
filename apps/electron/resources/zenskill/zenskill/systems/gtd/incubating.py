"""
8.7F: Incubating 孵化引擎

WaitingFor → Incubating — 用 ZenLoop 酝酿未成熟的想法。
四通道孵化: Reflect / Consolidate / Insight / Purify。
成熟度追踪: 0 → 100%, ZenLoop 每轮提升。
"""

from __future__ import annotations

import json
import threading
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class IncubatingItem:
    id: str
    action_id: str = ""
    channel: str = "reflect"  # reflect / consolidate / insight / purify
    raw_concept: str = ""
    entered_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    check_after: str = ""
    maturity: float = 0.0
    zenloop_ref: str = ""
    status: str = "active"  # active / mature / promoted / archived

    def to_dict(self) -> dict:
        return {
            "id": self.id, "action_id": self.action_id, "channel": self.channel,
            "raw_concept": self.raw_concept, "entered_at": self.entered_at,
            "check_after": self.check_after, "maturity": self.maturity,
            "zenloop_ref": self.zenloop_ref, "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IncubatingItem":
        return cls(
            id=data.get("id", ""), action_id=data.get("action_id", ""),
            channel=data.get("channel", "reflect"),
            raw_concept=data.get("raw_concept", ""),
            entered_at=data.get("entered_at", ""),
            check_after=data.get("check_after", ""),
            maturity=data.get("maturity", 0.0),
            zenloop_ref=data.get("zenloop_ref", ""),
            status=data.get("status", "active"),
        )


class IncubatingEngine:
    """孵化管理引擎 — ZenLoop 联动"""
    _id_counter: int = 0

    @classmethod
    def _next_id(cls) -> str:
        cls._id_counter += 1
        return f"incub_{int(time.time() * 1000)}_{cls._id_counter}"

    CHANNELS = {
        "reflect": {"icon": "🧘", "name": "反思酝酿",
                    "desc": "等待反思循环处理，自动关联历史经验"},
        "consolidate": {"icon": "🧩", "name": "记忆巩固",
                        "desc": "夜间自动合并相关记忆为语义知识"},
        "insight": {"icon": "💡", "name": "洞察孵化",
                    "desc": "跨领域联想，检测新颖连接"},
        "purify": {"icon": "🧹", "name": "净化冗余",
                   "desc": ">30天未活动 → 建议清理或合并"},
    }

    def __init__(self, data_dir: str = ""):
        if data_dir:
            self._data_dir = Path(data_dir)
        else:
            from ...core.paths import get_user_data_dir
            self._data_dir = get_user_data_dir() / "gtd"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._data_dir / "incubating.jsonl"
        self._text_cache = None
        self._text_cache_stat = None
        self._append_lock = threading.Lock()  # 多线程并发 append 防丢行

    def add(self, concept: str, channel: str = "reflect",
            action_id: str = "", check_after_days: int = 7) -> IncubatingItem:
        from datetime import datetime, timedelta
        check_after = (datetime.now() + timedelta(days=check_after_days)).strftime("%Y-%m-%d")
        item = IncubatingItem(
            id=IncubatingEngine._next_id(),
            raw_concept=concept, channel=channel,
            action_id=action_id, check_after=check_after,
        )
        self._append(item)
        return item

    def list(self, status: str = "active", channel: str = "",
             limit: int = 50) -> list[IncubatingItem]:
        items = self._read_all()
        if status != "all":
            items = [i for i in items if i.status == status]
        if channel:
            items = [i for i in items if i.channel == channel]
        items.sort(key=lambda i: i.maturity, reverse=True)
        return items[:limit]

    def get(self, item_id: str) -> Optional[IncubatingItem]:
        for item in self._read_all():
            if item.id == item_id:
                return item
        return None

    def mature(self, item_id: str, delta: float = 0.1) -> Optional[IncubatingItem]:
        """提升成熟度 (ZenLoop 每轮调用)"""
        item = self._get_by_id(item_id)
        if item is None:
            return None
        item.maturity = min(1.0, item.maturity + delta)
        if item.maturity >= 0.8:
            item.status = "mature"
        self._append(item)
        return item

    def promote(self, item_id: str) -> bool:
        """成熟孵化项 → 提升为 Action"""
        item = self._get_by_id(item_id)
        if item is None:
            return False
        item.status = "promoted"
        self._append(item)
        # 自动创建 Action
        self._promote_to_action(item)
        return True

    def archive(self, item_id: str) -> bool:
        item = self._get_by_id(item_id)
        if item is None:
            return False
        item.status = "archived"
        self._append(item)
        return True

    def run_zenloop_cycle(self) -> dict:
        """ZenLoop 联动 — 对所有活跃孵化项提升成熟度"""
        items = self._read_all()
        matured = 0
        for item in items:
            if item.status == "active":
                delta = 0.1  # 基础提升
                if item.channel == "insight":
                    delta = 0.15  # 洞察通道快
                item.maturity = min(1.0, item.maturity + delta)
                if item.maturity >= 0.8:
                    item.status = "mature"
                    matured += 1
        self._rewrite(items)

        # 清理 >30天 的 purify 通道项
        archived = 0
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        for item in items:
            if item.channel == "purify" and item.entered_at[:10] < cutoff:
                item.status = "archived"
                archived += 1
        self._rewrite(items)
        return {"matured": matured, "archived": archived,
                "total_active": sum(1 for i in items if i.status == "active")}

    def ready_to_promote(self) -> list[IncubatingItem]:
        """返回成熟待提升的孵化项"""
        return [i for i in self._read_all()
                if i.status == "mature" and i.maturity >= 0.8]

    def stats(self) -> dict:
        items = self._read_all()
        by_channel = {}
        for ch in self.CHANNELS:
            by_channel[ch] = sum(1 for i in items if i.channel == ch)
        return {
            "total": len(items),
            "active": sum(1 for i in items if i.status == "active"),
            "mature": sum(1 for i in items if i.status == "mature"),
            "promoted": sum(1 for i in items if i.status == "promoted"),
            "by_channel": by_channel,
        }

    # ── 内部 ──

    def _read_all(self) -> list[IncubatingItem]:
        """全量读取。追加式更新会产生同 id 多行，按 id last-wins 去重。"""
        if not self._file.exists():
            return []
        items: list[IncubatingItem] = []
        idx: dict[str, int] = {}
        for line in self._file.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                i = IncubatingItem.from_dict(json.loads(line))
            except Exception:
                continue
            if i.id in idx:
                items[idx[i.id]] = i
            else:
                idx[i.id] = len(items)
                items.append(i)
        return items

    def _get_by_id(self, item_id: str) -> Optional[IncubatingItem]:
        """定向读取（last-wins）。快路径子串定位本引擎写入行，未命中回退全量解析。"""
        if not self._file.exists():
            return None
        text = self._cache_text()
        needle = f'"id": "{item_id}"'
        hit: Optional[str] = None
        for line in text.split("\n"):
            if needle in line:
                hit = line
        if hit is not None:
            try:
                return IncubatingItem.from_dict(json.loads(hit))
            except Exception:
                hit = None
        for line in reversed(text.split("\n")):
            if not line.strip():
                continue
            try:
                i = IncubatingItem.from_dict(json.loads(line))
            except Exception:
                continue
            if i.id == item_id:
                return i
        return None

    def _cache_text(self) -> str:
        """带 stat 校验的文件文本缓存（外部写入自动失效重读）。"""
        try:
            st = (self._file.stat().st_mtime_ns, self._file.stat().st_size)
        except OSError:
            st = None
        if self._text_cache is not None and self._text_cache_stat == st:
            return self._text_cache
        text = self._file.read_text(encoding="utf-8") if st else ""
        self._text_cache = text
        self._text_cache_stat = st
        return text

    def _cache_append(self, line: str) -> None:
        if self._text_cache is None:
            return
        self._text_cache += line
        try:
            self._text_cache_stat = (self._file.stat().st_mtime_ns,
                                     self._file.stat().st_size)
        except OSError:
            self._text_cache = None

    def _append(self, item: IncubatingItem) -> None:
        line = json.dumps(item.to_dict(), ensure_ascii=False) + "\n"
        with self._append_lock:
            with open(self._file, "a", encoding="utf-8") as f:
                f.write(line)
            self._cache_append(line)

    def _rewrite(self, items: list[IncubatingItem]) -> None:
        """tmp + replace 原子落盘，防中途崩溃截断。"""
        lines = [json.dumps(i.to_dict(), ensure_ascii=False) for i in items]
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(self._file)
        self._text_cache = None

    def _promote_to_action(self, item: IncubatingItem) -> None:
        try:
            from .action import ActionEngine
            ae = ActionEngine(data_dir=str(self._data_dir))
            channel_info = self.CHANNELS.get(item.channel, {})
            ae.add(
                title=f"[孵化成熟] {item.raw_concept[:60]}",
                description=f"从 {channel_info.get('name', item.channel)} 孵化池提升",
                contexts=[item.channel], priority="P2",
            )
        except Exception:
            pass
