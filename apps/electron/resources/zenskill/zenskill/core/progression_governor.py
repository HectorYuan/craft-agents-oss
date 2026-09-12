"""层 4: 推进建议治理（ProgressionGovernor）

治理推进建议的"打扰度"（conversational_gtd_proposal.md 层 4 /
interaction_deepening_plan.md Day 4）：
- 反馈三态记录: 用户对建议的 accepted / rejected / dismissed 落 JSONL
- 频控: 每日推送上限 + 同类触发冷却期
- 主动度分级: active（默认）/ quiet（静默）/ ritual_only（仅仪式）

存储（与 GTD 引擎同为 JSONL，data_dir 约定一致）:
- 反馈与推送记录: ~/.zenskill/gtd/progression_feedback.jsonl
  每行 {"kind": "feedback"|"push", ...}；缺 kind 的历史行按 feedback 处理
- 主动度: ~/.zenskill/gtd/progression_mode.json {"mode": "active"}

实现要点:
- data_dir 传空时用默认 GTD 数据目录，传具体路径时与 actions.jsonl 同目录
  （TaskProgressionEngine 集成时共享，测试可隔离）
- 读路径无副作用（不建目录、不写文件），写路径才 mkdir
- can_push 的三条件按文档顺序短路: quiet → 每日上限 → 同类冷却；
  ritual_only 不在后端拦截（由前端按档位过滤显示密度），推送照常计数
- _now_ts 为时钟源（测试可注入固定时刻）；记录时间戳为本地 ISO
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ProgressionFeedback:
    """一条推进建议的用户反馈"""
    trigger: str    # 完整触发器，如 "overdue_action:act_xxx" / "morning_ritual"
    action: str     # "accepted" / "rejected" / "dismissed"
    timestamp: str  # 本地 ISO 时间戳 "%Y-%m-%dT%H:%M:%S"

    def to_dict(self) -> dict:
        return asdict(self)


class ProgressionGovernor:
    """层 4 治理: 频控 + 反馈三态 + 主动度分级"""

    DAILY_LIMIT = 3          # 每日主动推送上限
    COOLDOWN_HOURS = 24      # 同类触发冷却期（小时）
    DEFAULT_MODE = "active"
    MODES = ("active", "quiet", "ritual_only")
    FEEDBACK_ACTIONS = ("accepted", "rejected", "dismissed")

    _FEEDBACK_KIND = "feedback"
    _PUSH_KIND = "push"

    def __init__(self, data_dir: str = ""):
        if str(data_dir or ""):
            self._data_dir = Path(data_dir)
        else:
            from .paths import get_user_data_dir
            self._data_dir = get_user_data_dir() / "gtd"
        self._feedback_file = self._data_dir / "progression_feedback.jsonl"
        self._mode_file = self._data_dir / "progression_mode.json"

    # ── 时钟源（测试可注入）──

    def _now_ts(self) -> float:
        return time.time()

    def _now_iso(self) -> str:
        return datetime.fromtimestamp(self._now_ts()).strftime("%Y-%m-%dT%H:%M:%S")

    # ── 反馈三态 ──

    def record_feedback(self, trigger: str, action: str) -> ProgressionFeedback:
        """记录一条用户反馈（action 必须是三态之一，否则 ValueError）"""
        trigger = str(trigger or "").strip()
        action = str(action or "").strip()
        if not trigger:
            raise ValueError("trigger 不能为空")
        if action not in self.FEEDBACK_ACTIONS:
            raise ValueError(f"action 必须是 {self.FEEDBACK_ACTIONS} 之一: {action!r}")
        feedback = ProgressionFeedback(
            trigger=trigger, action=action, timestamp=self._now_iso())
        self._append({"kind": self._FEEDBACK_KIND, **feedback.to_dict()})
        return feedback

    def get_feedback_stats(self, days: int = 7) -> dict:
        """近 N 天反馈统计: 三态总数 + 按触发器族分桶

        触发器族取 ':' 前缀（如 overdue_action:act_1 → overdue_action），
        与频控的 trigger_type 粒度对齐。
        """
        try:
            window = max(1, int(days))
        except (TypeError, ValueError):
            window = 7
        cutoff = self._now_ts() - window * 86400
        stats = {
            "days": window, "total": 0,
            "accepted": 0, "rejected": 0, "dismissed": 0,
            "by_trigger": {},
        }
        for rec in self._read_records():
            if rec.get("kind", self._FEEDBACK_KIND) != self._FEEDBACK_KIND:
                continue
            ts = self._parse_ts(str(rec.get("timestamp") or ""))
            if ts is not None and ts < cutoff:
                continue
            action = str(rec.get("action") or "")
            if action not in self.FEEDBACK_ACTIONS:
                continue
            family = self._family(str(rec.get("trigger") or ""))
            stats["total"] += 1
            stats[action] += 1
            bucket = stats["by_trigger"].setdefault(
                family, {"accepted": 0, "rejected": 0, "dismissed": 0})
            bucket[action] += 1
        return stats

    def should_suppress(self, trigger: str) -> bool:
        """同触发器族连续 2 次 rejected → 当日降频（文档 4.1 规则）"""
        family = self._family(str(trigger or ""))
        streak = 0
        for rec in reversed(self._read_records()):
            if rec.get("kind", self._FEEDBACK_KIND) != self._FEEDBACK_KIND:
                continue
            if self._family(str(rec.get("trigger") or "")) != family:
                continue
            if str(rec.get("action") or "") == "rejected":
                streak += 1
                if streak >= 2:
                    return True
            else:
                break
        return False

    # ── 频控 ──

    def record_push(self, trigger_type: str) -> None:
        """记录一次推送（trigger_type: "state" / "time" / "event"）"""
        trigger_type = str(trigger_type or "").strip() or "state"
        self._append({
            "kind": self._PUSH_KIND,
            "trigger_type": trigger_type,
            "timestamp": self._now_iso(),
        })

    def can_push(self, trigger_type: str) -> bool:
        """是否允许推送该类建议

        1. 主动度 != quiet（quiet 全部静默）
        2. 每日推送计数 < DAILY_LIMIT
        3. 同类 trigger_type 上次推送距今 > COOLDOWN_HOURS
        """
        if self.get_mode() == "quiet":
            return False
        trigger_type = str(trigger_type or "").strip() or "state"
        now = self._now_ts()
        pushes = [r for r in self._read_records()
                  if r.get("kind") == self._PUSH_KIND]
        today = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
        pushed_today = 0
        last_same: float | None = None
        for rec in pushes:
            ts = self._parse_ts(str(rec.get("timestamp") or ""))
            if ts is None:
                continue
            if datetime.fromtimestamp(ts).strftime("%Y-%m-%d") == today:
                pushed_today += 1
            if str(rec.get("trigger_type") or "") == trigger_type:
                if last_same is None or ts > last_same:
                    last_same = ts
        if pushed_today >= self.DAILY_LIMIT:
            return False
        if (last_same is not None
                and now - last_same < self.COOLDOWN_HOURS * 3600):
            return False
        return True

    # ── 主动度分级 ──

    def set_mode(self, mode: str) -> str:
        """设置主动度（active / quiet / ritual_only），非法值 ValueError"""
        mode = str(mode or "").strip()
        if mode not in self.MODES:
            raise ValueError(f"mode 必须是 {self.MODES} 之一: {mode!r}")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._mode_file.write_text(
            json.dumps({"mode": mode}, ensure_ascii=False), encoding="utf-8")
        return mode

    def get_mode(self) -> str:
        """读取主动度（缺文件/损坏/非法值回落 DEFAULT_MODE）"""
        try:
            data = json.loads(self._mode_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self.DEFAULT_MODE
        if isinstance(data, dict):
            mode = data.get("mode")
            if mode in self.MODES:
                return str(mode)
        return self.DEFAULT_MODE

    # ── 存储 ──

    @staticmethod
    def _family(trigger: str) -> str:
        """触发器族: ':' 前缀（overdue_action:act_1 → overdue_action）"""
        return trigger.split(":", 1)[0] if trigger else ""

    @staticmethod
    def _parse_ts(ts: str) -> float | None:
        """解析本地 ISO 时间戳（容忍日期后缀/纯日期），失败返回 None"""
        ts = (ts or "").strip()
        if not ts:
            return None
        for text, fmt in ((ts[:19], "%Y-%m-%dT%H:%M:%S"),
                          (ts[:19], "%Y-%m-%d %H:%M:%S"),
                          (ts[:10], "%Y-%m-%d")):
            try:
                return datetime.strptime(text, fmt).timestamp()
            except ValueError:
                continue
        return None

    def _read_records(self) -> list[dict]:
        try:
            lines = self._feedback_file.read_text(
                encoding="utf-8").splitlines()
        except OSError:
            return []
        out: list[dict] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if isinstance(data, dict):
                out.append(data)
        return out

    def _append(self, record: dict) -> None:
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            with self._feedback_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            logger.warning("progression governor append failed",
                           exc_info=True)
