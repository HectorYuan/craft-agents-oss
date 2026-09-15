"""
层 3: 任务自动推进引擎 (Task Progression Engine)

扫描 GTD / 成长数据，基于状态与阶段自动生成推进建议（TaskProgression），
每条建议携带可直接发给 Agent 的一句话提示词（conversational_gtd_proposal.md 层 3）。

规则（按优先级降序）:
state-based（数据状态驱动）:
- high   逾期行动 / 今日到期          ← ActionEngine
- medium 项目停滞                    ← ProjectEngine（+ ActionEngine 完成记录）
- medium 孵化成熟                    ← IncubatingEngine
- medium 能量偏低                    ← EnergyEngine
- low    习惯未打卡                  ← HabitTracker（growth 体系）
- low    目标截止临近                ← goals JSONL（deadline 字段，ISO 日期）
time-based（当前时间驱动，trigger_type="time"）:
- high   晨间启动仪式                ← 当日无 action_done 且今日有日程/到期行动
- medium 收工复盘仪式                ← 18:00 后且当日已有 action_done
- medium 周五回顾仪式                ← 周五 15:00 后
- low    沉默唤醒                    ← actions/inbox 最近交互超过 3 天
event-based（事件驱动，trigger_type="event"）:
- high   低能量模式                  ← 能量 < 30% 且存在待办轻量任务（⚡≤3）
- medium 项目完成庆祝                ← 项目 1h 内完成（复盘 + 分享卡片）

实现要点:
- 每条规则独立实例化所需 Engine 并独立容错，单引擎故障不影响其余建议
- TaskProgression.trigger_type: "state"（状态规则默认）/ "time"（时间规则）
  / "event"（事件规则）
- 低能量双规则去重: event 规则（low_energy，含轻量任务清单）命中时抑制
  state 规则（energy_low:*），避免同一状态出两条建议
- 当前时间经 _now() 获取（测试可注入固定时刻）；time-based 规则追加在
  state-based 规则之后，结果同样进入类级缓存
- 缓存: 类级 _cache + _cache_version（相关数据文件指纹，zenskill:changed
  写入后 mtime 变化即失配）+ TTL 30s；写工具后可 invalidate_cache() 立即失效
- data_dir 约定与 GTDZenLoopBridge 一致: 传空时各 Engine 用各自默认路径，
  传具体路径时作为 GTD 数据目录共享（actions.jsonl / proj_*.json 同目录）
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from hashlib import sha1
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TaskProgression:
    """一条推进建议：触发器 + 建议文案 + Agent 提示词"""
    trigger: str          # "overdue_action:act_xxx" / "due_today:act_yyy" / ...
    suggestion: str       # 人类可读建议文案
    prompt: str           # 转化为 Agent 提示词（一句话）
    priority: str         # "high"/"medium"/"low"
    entity_type: str      # "action"/"project"/"incubating"/"habit"/"energy"/"goal"/"system"
    entity_id: str        # 关联实体 ID
    trigger_type: str = "state"  # "state"(默认) | "time" | "event"

    def to_dict(self) -> dict:
        return asdict(self)


_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


class TaskProgressionEngine:
    """任务自动推进引擎 — 规则扫描 + 类级缓存"""

    CACHE_TTL = 30.0        # 缓存有效期（秒）
    STALL_DAYS = 7          # 项目停滞：N 天无完成行动
    GOAL_WINDOW_DAYS = 7    # 目标截止临近窗口（天）
    ENERGY_LOW_PCT = 0.3    # 能量偏低阈值（30%）
    LOW_ENERGY_TASK_MAX = 3 # 低能量模式：轻量任务能量上限（⚡≤3）
    CELEBRATION_WINDOW = 3600  # 项目完成庆祝窗口（秒）
    INCUBATION_MATURE = 0.8 # 孵化成熟度阈值
    SILENCE_DAYS = 3        # 沉默唤醒：N 天无交互

    _cache: list | None = None
    _cache_version: tuple = ()
    _cache_at: float = 0.0

    def __init__(self, data_dir: str = ""):
        self._data_dir = str(data_dir or "")

    def _now(self) -> datetime:
        """当前时间（time-based 规则的时钟源，测试可注入固定时刻）"""
        return datetime.now()

    # ── 对外 API ──

    def generate_progressions(self, limit: int = 0) -> dict:
        """生成排序后的推进建议列表。

        排序: priority 降序（high → medium → low），同级按 entity_type。
        limit>0 时截取前 N 条（count/message 与截取后一致）。
        返回前经 ProgressionGovernor 频控过滤（层 4: quiet / 每日上限 /
        同类冷却； Governor 故障时放行，不影响建议生成）。
        """
        items = [p.to_dict() for p in self._get_cached()]
        items = self._govern(items)
        if isinstance(limit, int) and limit > 0:
            items = items[:limit]
        if not items:
            return {"count": 0, "progressions": [], "message": "暂无推进建议"}
        by_pri = {k: 0 for k in _PRIORITY_RANK}
        for it in items:
            by_pri[it["priority"]] = by_pri.get(it["priority"], 0) + 1
        message = (f"共 {len(items)} 条推进建议"
                   f"（high {by_pri['high']} / medium {by_pri['medium']}"
                   f" / low {by_pri['low']}）")
        return {"count": len(items), "progressions": items, "message": message}

    @classmethod
    def invalidate_cache(cls) -> None:
        """清空类级缓存（写工具执行后 / 测试隔离用）"""
        cls._cache = None
        cls._cache_version = ()
        cls._cache_at = 0.0

    def _govern(self, items: list[dict]) -> list[dict]:
        """层 4 治理: 经 ProgressionGovernor 频控过滤（quiet/每日上限/冷却）

        过滤在缓存读取之后进行——Governor 状态变化（如切换主动度）无需
        失效建议缓存即可生效。data_dir 与建议引擎共享（测试隔离一致）。
        """
        try:
            from ...core.progression_governor import ProgressionGovernor
            governor = ProgressionGovernor(data_dir=self._data_dir)
            return [p for p in items
                    if governor.can_push(str(p.get("trigger_type") or "state"))]
        except Exception:
            logger.warning("progression governor filter failed; pass through",
                           exc_info=True)
            return items

    # ── 缓存 ──

    _CONTENT_HASH_FILES = frozenset({"energy.json"})

    def _get_cached(self) -> list[TaskProgression]:
        cls = type(self)
        if (cls._cache is not None
                and cls._cache_version == self._compute_version()
                and time.time() - cls._cache_at < cls.CACHE_TTL):
            return cls._cache
        items = self._scan_all()
        # 以扫描后的指纹为基准版本：扫描本身可能触发引擎初始化写盘
        # （如 EnergyEngine 首次落盘 energy.json），否则缓存永不命中
        cls._cache = items
        cls._cache_version = self._compute_version()
        cls._cache_at = time.time()
        return items

    def _data_paths(self) -> list[Path]:
        """参与缓存指纹的数据文件（仅 stat，不解析内容）"""
        paths: list[Path] = []
        try:
            from ...core.paths import get_user_data_dir, get_mirroring_dir
            user_dir = get_user_data_dir()
            if self._data_dir:
                gtd = Path(self._data_dir)
                paths += sorted(gtd.glob("proj_*.json"))
            else:
                gtd = user_dir / "gtd"
                paths += sorted((gtd / "projects").glob("proj_*.json"))
            paths += [
                gtd / "actions.jsonl", gtd / "incubating.jsonl",
                gtd / "energy.json", gtd / "calendar.jsonl",
                user_dir / "growth" / "habits.json",
                get_mirroring_dir(autocreate=False) / "events.jsonl",
            ]
            paths += sorted((user_dir / "goals").glob("*_goals.jsonl"))
        except Exception:
            pass
        return paths

    def _compute_version(self) -> tuple:
        # energy.json 会被引擎读路径重写（mtime 不稳定但内容不变），用内容哈希
        parts = []
        for p in self._data_paths():
            try:
                if p.name in self._CONTENT_HASH_FILES:
                    parts.append((str(p), sha1(p.read_bytes()).hexdigest()))
                    continue
                st = p.stat()
                parts.append((str(p), st.st_mtime_ns, st.st_size))
            except OSError:
                parts.append((str(p), 0, 0))
        return tuple(parts)

    # ── 规则扫描 ──

    def _scan_all(self) -> list[TaskProgression]:
        progressions: list[TaskProgression] = []
        rules = (
            # state-based（数据状态驱动）
            self._rule_overdue_actions,
            self._rule_due_today,
            self._rule_stalled_projects,
            self._rule_mature_incubating,
            self._rule_low_energy,
            self._rule_habit_checkin,
            self._rule_goal_deadline,
            # time-based（当前时间驱动；结果同样进入类级缓存）
            self._check_morning_ritual,
            self._check_shutdown_ritual,
            self._check_weekly_review,
            self._check_silence_wakeup,
            # event-based（事件驱动）
            self._check_low_energy,
            self._check_project_celebration,
        )
        for rule in rules:
            try:
                progressions.extend(rule() or [])
            except Exception:
                logger.warning("progression rule %s failed", rule.__name__,
                               exc_info=True)
        progressions = self._suppress_low_energy_overlap(progressions)
        progressions.sort(key=lambda p: (_PRIORITY_RANK.get(p.priority, 9),
                                         p.entity_type, p.entity_id, p.trigger))
        return progressions

    @staticmethod
    def _suppress_low_energy_overlap(
            progressions: list[TaskProgression]) -> list[TaskProgression]:
        """低能量去重: event 规则（low_energy）命中时抑制 state 规则（energy_low:*）

        两条规则共享同一个能量阈值，event 版带轻量任务清单、优先级更高；
        同时出现会让进度条出现两条同源建议。
        """
        if not any(p.trigger == "low_energy" for p in progressions):
            return progressions
        return [p for p in progressions
                if not p.trigger.startswith("energy_low:")]

    def _rule_overdue_actions(self) -> list[TaskProgression]:
        """逾期行动: action.status=pending + due_date < today"""
        from .action import ActionEngine
        today = time.strftime("%Y-%m-%d")
        out = []
        for a in ActionEngine(data_dir=self._data_dir).list(
                status="pending", limit=200):
            due = (a.due_date or "")[:10]
            if not due or due >= today:
                continue
            days = self._days_between(due, today)
            if days is None or days <= 0:
                continue
            out.append(TaskProgression(
                trigger=f"overdue_action:{a.id}",
                suggestion=f"「{a.title}」已逾期 {days} 天",
                prompt=f"帮我评估「{a.title}」是否需要调整优先级或推迟",
                priority="high", entity_type="action", entity_id=a.id))
        return out

    def _rule_due_today(self) -> list[TaskProgression]:
        """今日到期: action.status=pending + due_date = today"""
        from .action import ActionEngine
        today = time.strftime("%Y-%m-%d")
        out = []
        for a in ActionEngine(data_dir=self._data_dir).list(
                status="pending", limit=200):
            if (a.due_date or "")[:10] != today:
                continue
            out.append(TaskProgression(
                trigger=f"due_today:{a.id}",
                suggestion=f"「{a.title}」今天到期",
                prompt=f"帮我优先处理「{a.title}」",
                priority="high", entity_type="action", entity_id=a.id))
        return out

    def _rule_stalled_projects(self) -> list[TaskProgression]:
        """项目停滞: project.status=active + 无 next_action + 7 天无完成行动"""
        from .action import ActionEngine
        from .project import ProjectEngine
        projects = ProjectEngine(data_dir=self._data_dir).list(status="active")
        if not projects:
            return []
        cutoff = (datetime.now()
                  - timedelta(days=self.STALL_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
        recent_done = set()
        for a in ActionEngine(data_dir=self._data_dir).list(
                status="done", limit=200):
            if (a.completed_at or "") >= cutoff:
                recent_done.add(a.project_id)
        out = []
        for p in projects:
            if p.next_action_id or p.id in recent_done:
                continue
            out.append(TaskProgression(
                trigger=f"stalled_project:{p.id}",
                suggestion=f"项目「{p.name}」停滞中",
                prompt=f"帮我为项目「{p.name}」规划下一步",
                priority="medium", entity_type="project", entity_id=p.id))
        return out

    def _rule_mature_incubating(self) -> list[TaskProgression]:
        """孵化成熟: incubating.maturity >= 0.8（active/mature 未提升条目）"""
        from .incubating import IncubatingEngine
        out = []
        for i in IncubatingEngine(data_dir=self._data_dir).list(
                status="all", limit=100):
            if i.maturity < self.INCUBATION_MATURE:
                continue
            if i.status not in ("active", "mature"):
                continue
            out.append(TaskProgression(
                trigger=f"incubating_mature:{i.id}",
                suggestion=f"孵化项「{i.raw_concept}」已成熟",
                prompt=f"帮我将「{i.raw_concept}」提升为可执行行动",
                priority="medium", entity_type="incubating", entity_id=i.id))
        return out

    def _rule_low_energy(self) -> list[TaskProgression]:
        """能量偏低: energy.pct < 30%

        event 规则（low_energy）命中时本规则被 _suppress_low_energy_overlap
        抑制；仅无轻量待办时作为兜底建议出现。
        """
        from .energy import EnergyEngine
        status = EnergyEngine(data_dir=self._data_dir).status()
        pct = float(status.get("pct", 1.0))
        if pct >= self.ENERGY_LOW_PCT:
            return []
        pct_int = int(round(pct * 100))
        skill_id = str(status.get("skill_id") or "energy")
        return [TaskProgression(
            trigger=f"energy_low:{skill_id}",
            suggestion=f"能量偏低 ({pct_int}%)",
            prompt="帮我安排一些低能量消耗的任务",
            priority="medium", entity_type="energy", entity_id=skill_id)]

    def _rule_habit_checkin(self) -> list[TaskProgression]:
        """习惯未打卡: 打卡连续性未中断（不含今天的 streak > 0）且今日无打卡"""
        from ...systems.active.habit_tracker import HabitTracker
        today = time.strftime("%Y-%m-%d")
        out = []
        for report in HabitTracker().analyze(days=7).get("habits", []):
            completed = report.get("completed", {})
            if completed.get(today, False):
                continue
            streak = 0
            for day in sorted(completed, reverse=True):
                if day >= today:
                    continue
                if completed[day]:
                    streak += 1
                else:
                    break
            if streak <= 0:
                continue
            habit = report.get("habit", {})
            habit_id = str(habit.get("habit_id", ""))
            title = str(habit.get("title") or habit_id)
            out.append(TaskProgression(
                trigger=f"habit_checkin:{habit_id}",
                suggestion=f"习惯「{title}」今天未打卡",
                prompt=f"提醒我完成「{title}」",
                priority="low", entity_type="habit", entity_id=habit_id))
        return out

    def _rule_goal_deadline(self) -> list[TaskProgression]:
        """目标截止临近: goal.status=active + deadline 在 7 天内。

        deadline 取 goals JSONL 的 ISO 日期字段（GrowthGoal 暂无该字段时
        规则静默不触发，向前兼容后续带截止日的目标模型）。
        """
        try:
            from ...core.paths import get_user_data_dir
            goals_dir = get_user_data_dir() / "goals"
        except Exception:
            return []
        if not goals_dir.is_dir():
            return []
        today = time.strftime("%Y-%m-%d")
        out = []
        for path in goals_dir.glob("*_goals.jsonl"):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                if not isinstance(data, dict) or data.get("status") != "active":
                    continue
                deadline = str(data.get("deadline") or "")[:10]
                if not deadline:
                    continue
                days = self._days_between(today, deadline)
                if days is None or not (0 <= days <= self.GOAL_WINDOW_DAYS):
                    continue
                dimension = str(data.get("dimension") or "综合")
                goal_id = str(data.get("goal_id") or path.stem)
                suggestion = (f"目标「{dimension}」今天截止" if days == 0
                              else f"目标「{dimension}」{days} 天后截止")
                out.append(TaskProgression(
                    trigger=f"goal_deadline:{goal_id}",
                    suggestion=suggestion,
                    prompt=f"帮我检查目标「{dimension}」的进度",
                    priority="low", entity_type="goal", entity_id=goal_id))
        return out

    # ── time-based 规则（依赖当前时间，trigger_type="time"）──

    def _check_morning_ritual(self) -> list[TaskProgression]:
        """晨间启动仪式: 当日无 action_done（尚未开工）且今日有日程或到期行动"""
        from .action import ActionEngine
        from .calendar import CalendarEngine
        from .energy import EnergyEngine
        today = self._now().strftime("%Y-%m-%d")
        done_today = [a for a in ActionEngine(data_dir=self._data_dir).list(
                          status="done", limit=200)
                      if (a.completed_at or "")[:10] == today]
        if done_today:
            return []
        due_today = [a for a in ActionEngine(data_dir=self._data_dir).list(
                         status="pending", limit=200)
                     if (a.due_date or "")[:10] == today]
        events = CalendarEngine(data_dir=self._data_dir).today()
        if not due_today and not events:
            return []
        energy = EnergyEngine(data_dir=self._data_dir).status()
        pct_int = int(round(float(energy.get("pct", 0)) * 100))
        return [TaskProgression(
            trigger="morning_ritual",
            trigger_type="time",
            suggestion=(f"今日 {len(events)} 场日程，{len(due_today)} 项到期行动，"
                        f"能量 {pct_int}%"),
            prompt=(f"帮我规划今天的工作。今日日程 {len(events)} 场，"
                    f"到期行动 {len(due_today)} 项。能量 {pct_int}%。"),
            priority="high", entity_type="system", entity_id="morning")]

    def _check_shutdown_ritual(self) -> list[TaskProgression]:
        """收工复盘仪式: 18:00 后且当日已有 action_done（用户已工作）"""
        from .action import ActionEngine
        now = self._now()
        if now.hour < 18:
            return []
        today = now.strftime("%Y-%m-%d")
        engine = ActionEngine(data_dir=self._data_dir)
        done_today = [a for a in engine.list(status="done", limit=200)
                      if (a.completed_at or "")[:10] == today]
        if not done_today:
            return []
        pending = [a for a in engine.list(status="all", limit=200)
                   if a.status in ("pending", "next")]
        return [TaskProgression(
            trigger="shutdown_ritual",
            trigger_type="time",
            suggestion=f"今日完成 {len(done_today)} 项行动，{len(pending)} 项待处理",
            prompt=(f"帮我做今日复盘。完成了 {len(done_today)} 项，"
                    f"还有 {len(pending)} 项待处理。帮我安排明天的重点。"),
            priority="medium", entity_type="system", entity_id="shutdown")]

    def _check_weekly_review(self) -> list[TaskProgression]:
        """周五回顾仪式: 周五 15:00 后"""
        now = self._now()
        if now.weekday() != 4 or now.hour < 15:
            return []
        return [TaskProgression(
            trigger="weekly_review",
            trigger_type="time",
            suggestion="周五回顾时间",
            prompt="帮我回顾本周：完成了多少行动？有哪些被拖延了？能量曲线如何？",
            priority="medium", entity_type="system", entity_id="weekly")]

    def _check_silence_wakeup(self) -> list[TaskProgression]:
        """沉默唤醒: actions/inbox 最近一次交互超过 3 天，挑最小行动低压力唤醒"""
        from .action import ActionEngine
        latest = self._latest_activity_ts()
        if latest is None:
            return []  # 无任何历史记录（新用户）不算沉默
        if (self._now() - latest).total_seconds() <= self.SILENCE_DAYS * 86400:
            return []
        pending = ActionEngine(data_dir=self._data_dir).list(
            status="pending", limit=100)
        if not pending:
            return []
        lightest = min(pending, key=lambda a: (a.energy_required,
                                               a.estimated_minutes,
                                               a.created_at))
        return [TaskProgression(
            trigger="silence_wakeup",
            trigger_type="time",
            suggestion=f"有阵子没见了。挑了一件最小的事：{lightest.title}",
            prompt="我有一阵子没互动了。帮我找一件最容易完成的行动，10 分钟内能搞定的那种。",
            priority="low", entity_type="system", entity_id="silence")]

    # ── event-based 规则（事件驱动，trigger_type="event"）──

    def _check_low_energy(self) -> list[TaskProgression]:
        """低能量模式: 能量 < 30% 且存在待办轻量任务（⚡≤3）时给出重排建议。

        需至少一个轻量任务才触发——空清单的"重新安排"是无噪音价值的空建议；
        此时退回 state 规则（energy_low:*）的通用建议。
        """
        from .action import ActionEngine
        from .energy import EnergyEngine
        status = EnergyEngine(data_dir=self._data_dir).status()
        pct = float(status.get("pct", 1.0))
        if pct >= self.ENERGY_LOW_PCT:
            return []
        pending = ActionEngine(data_dir=self._data_dir).list(
            status="pending", limit=20)
        light = [a for a in pending
                 if (a.energy_required or 5) <= self.LOW_ENERGY_TASK_MAX]
        if not light:
            return []
        pct_int = int(round(pct * 100))
        return [TaskProgression(
            trigger="low_energy",
            trigger_type="event",
            suggestion=(f"能量偏低 ({pct_int}%)，"
                        f"有 {len(light)} 个轻量任务（⚡≤{self.LOW_ENERGY_TASK_MAX}）"),
            prompt=(f"我能量偏低（{pct_int}%）。帮我从待办中筛选低能量消耗的任务"
                    f"（⚡≤{self.LOW_ENERGY_TASK_MAX}），重新安排今天的优先级。"),
            priority="high", entity_type="energy", entity_id="energy_pool")]

    def _check_project_celebration(self) -> list[TaskProgression]:
        """项目完成庆祝: 1h 内完成的项目触发复盘 + 分享卡片建议（取最近一个）"""
        from .project import ProjectEngine
        now = self._now()
        for p in ProjectEngine(data_dir=self._data_dir).list(status="done")[:5]:
            completed = self._parse_ts(p.completed_at)
            if completed is None:
                continue
            if (now - completed).total_seconds() >= self.CELEBRATION_WINDOW:
                continue
            return [TaskProgression(
                trigger=f"project_completed:{p.id}",
                trigger_type="event",
                suggestion=f"🎉 项目「{p.name}」已完成！",
                prompt=(f"项目「{p.name}」刚完成。帮我复盘："
                        f"这个项目最值得沉淀的经验是什么？"),
                priority="medium", entity_type="project", entity_id=p.id)]
        return []

    def _latest_activity_ts(self) -> datetime | None:
        """actions.jsonl / inbox.jsonl 中最近一次交互时间戳（无记录返回 None）"""
        latest: datetime | None = None
        try:
            from .action import ActionEngine
            from .inbox import InboxEngine
            candidates: list[str] = []
            for a in ActionEngine(data_dir=self._data_dir).list(
                    status="all", limit=500):
                candidates += [a.created_at or "", a.completed_at or ""]
            for i in InboxEngine(data_dir=self._data_dir).list(
                    status="all", limit=500):
                candidates.append(i.created_at or "")
                clarified = i.clarify_result or {}
                candidates.append(str(clarified.get("clarified_at") or ""))
            for ts in candidates:
                dt = self._parse_ts(ts)
                if dt is not None and (latest is None or dt > latest):
                    latest = dt
        except Exception:
            return latest
        return latest

    # ── 内部 ──

    @staticmethod
    def _days_between(from_date: str, to_date: str) -> int | None:
        """from_date 到 to_date 的天数（to - from），解析失败返回 None"""
        try:
            delta = (datetime.strptime(to_date, "%Y-%m-%d")
                     - datetime.strptime(from_date, "%Y-%m-%d"))
            return delta.days
        except ValueError:
            return None

    @staticmethod
    def _parse_ts(ts: str) -> datetime | None:
        """解析 ISO 时间戳（容忍日期后缀/纯日期），失败返回 None"""
        ts = (ts or "").strip()
        if not ts:
            return None
        for text, fmt in ((ts[:19], "%Y-%m-%dT%H:%M:%S"),
                          (ts[:19], "%Y-%m-%d %H:%M:%S"),
                          (ts[:10], "%Y-%m-%d")):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None
