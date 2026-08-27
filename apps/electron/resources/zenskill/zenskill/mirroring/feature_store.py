"""
特征存储引擎

Phase 9A: 用户画像数据层
从原始事件中提取用户行为特征向量，持久化存储
"""

import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .event_collector import EventCollector
from .models import EventType, FeatureVector

MIN_EVENTS_FOR_COMPUTE = 10


class FeatureStore:
    """特征存储引擎"""

    def __init__(self, data_dir: Optional[Path] = None):
        self._mirroring_dir = data_dir or self._get_default_dir()
        self._mirroring_dir.mkdir(parents=True, exist_ok=True)
        self._features_file = self._mirroring_dir / "features.json"
        self._history_file = self._mirroring_dir / "features_history.jsonl"
        self._event_collector = EventCollector(data_dir=data_dir)

    @staticmethod
    def _get_default_dir() -> Path:
        from zenskill.core.paths import get_mirroring_dir
        return get_mirroring_dir()

    def compute_features(self, window_days: int = 30) -> FeatureVector:
        """
        计算用户行为特征向量

        Args:
            window_days: 分析窗口天数

        Returns:
            FeatureVector
        """
        cutoff = time.time() - (window_days * 86400)
        events = self._event_collector.get_events_since(cutoff)

        if len(events) < MIN_EVENTS_FOR_COMPUTE:
            return FeatureVector.empty()

        total = len(events)

        # 会话统计
        sessions: Dict[str, List[float]] = defaultdict(list)
        for e in events:
            sessions[e.session_id].append(e.timestamp)
        session_count = len(sessions)

        # 平均会话时长
        session_durations = []
        for timestamps in sessions.values():
            if len(timestamps) > 1:
                duration = (max(timestamps) - min(timestamps)) / 60.0
                session_durations.append(duration)
        avg_session_duration = (
            sum(session_durations) / len(session_durations)
            if session_durations else 0.0
        )

        # 活跃时段分布 (0-23 小时)
        hour_counts: Dict[int, int] = defaultdict(int)
        for e in events:
            hour = datetime.fromtimestamp(e.timestamp).hour
            hour_counts[hour] += 1
        active_hours = {h: hour_counts.get(h, 0) / total for h in range(24)}

        # 星期分布 (0=Mon, 6=Sun)
        weekday_counts: Dict[int, int] = defaultdict(int)
        for e in events:
            weekday = datetime.fromtimestamp(e.timestamp).weekday()
            weekday_counts[weekday] += 1
        weekday_distribution = {d: weekday_counts.get(d, 0) / total for d in range(7)}

        # 技能偏好
        skill_counts: Dict[str, int] = defaultdict(int)
        for e in events:
            skill_counts[e.skill_id] += 1
        skill_preferences = {sid: count / total for sid, count in skill_counts.items()}

        # 平均任务复杂度
        complexities = [
            e.context.get("complexity", 5)
            for e in events
            if isinstance(e.context.get("complexity", 5), (int, float))
        ]
        avg_complexity = sum(complexities) / len(complexities) if complexities else 5.0

        # 成功率
        success_count = sum(1 for e in events if e.success)
        success_rate = success_count / total

        # 记忆操作率
        memory_ops = sum(1 for e in events if e.event_type == EventType.MEMORY_OP)
        memory_usage_rate = memory_ops / total

        # 反思频率 (per session)
        reflections = sum(1 for e in events if e.event_type == EventType.REFLECTION)
        reflection_freq = reflections / session_count if session_count > 0 else 0.0

        # 目标完成率
        goal_events = [e for e in events if e.event_type == EventType.GOAL_ACTION]
        if goal_events:
            goal_success = sum(1 for e in goal_events if e.success)
            goal_completion_rate = goal_success / len(goal_events)
        else:
            goal_completion_rate = 0.0

        # 趋势分析: 比较窗口前 25% vs 后 25%
        sorted_events = sorted(events, key=lambda e: e.timestamp)
        quarter = max(1, len(sorted_events) // 4)
        first_quarter = sorted_events[:quarter]
        last_quarter = sorted_events[-quarter:]

        engagement_trend = self._compute_trend(
            len(first_quarter) / quarter, len(last_quarter) / quarter
        )
        first_sr = sum(1 for e in first_quarter if e.success) / len(first_quarter) if first_quarter else 0
        last_sr = sum(1 for e in last_quarter if e.success) / len(last_quarter) if last_quarter else 0
        success_trend = self._compute_trend(first_sr, last_sr)

        # 平均响应时间
        exec_events = [e for e in events if e.event_type == EventType.SKILL_EXEC]
        avg_response = (
            sum(e.duration_ms for e in exec_events) / len(exec_events)
            if exec_events else 0.0
        )

        vector = FeatureVector(
            computed_at=time.time(),
            window_days=window_days,
            total_events=total,
            session_count=session_count,
            avg_session_duration_min=avg_session_duration,
            active_hours=active_hours,
            weekday_distribution=weekday_distribution,
            skill_preferences=skill_preferences,
            avg_task_complexity=avg_complexity,
            success_rate=success_rate,
            memory_usage_rate=memory_usage_rate,
            reflection_frequency=reflection_freq,
            goal_completion_rate=goal_completion_rate,
            engagement_trend=engagement_trend,
            success_trend=success_trend,
            avg_response_time_ms=avg_response,
        )

        self._persist_features(vector)
        return vector

    @staticmethod
    def _compute_trend(early: float, late: float, threshold: float = 0.2) -> str:
        """计算趋势: 比较早期和晚期值"""
        if early == 0 and late == 0:
            return "stable"
        base = max(early, 0.001)  # 避免除零
        change = (late - early) / base
        if change > threshold:
            return "increasing"
        elif change < -threshold:
            return "decreasing"
        return "stable"

    def _persist_features(self, vector: FeatureVector) -> None:
        """持久化特征向量"""
        # 原子写入 features.json
        temp_path = self._features_file.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(vector.to_dict(), f, indent=2, ensure_ascii=False)
        temp_path.rename(self._features_file)

        # 追加到 features_history.jsonl
        with open(self._history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(vector.to_dict(), ensure_ascii=False) + "\n")

        # 裁剪历史到最近 50 条
        self._trim_history(50)

    def _trim_history(self, max_entries: int) -> None:
        """裁剪历史文件到指定条数"""
        if not self._history_file.exists():
            return
        lines = []
        with open(self._history_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    lines.append(line)
        if len(lines) > max_entries:
            lines = lines[-max_entries:]
            temp_path = self._history_file.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            temp_path.rename(self._history_file)

    def get_latest_features(self) -> Optional[FeatureVector]:
        """获取最新特征向量"""
        if not self._features_file.exists():
            return None
        try:
            with open(self._features_file, "r", encoding="utf-8") as f:
                return FeatureVector.from_dict(json.load(f))
        except (json.JSONDecodeError, KeyError):
            return None

    def get_feature_history(self, limit: int = 20) -> List[FeatureVector]:
        """获取特征向量历史"""
        if not self._history_file.exists():
            return []
        vectors = []
        with open(self._history_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        vectors.append(FeatureVector.from_dict(json.loads(line)))
                    except (json.JSONDecodeError, KeyError):
                        continue
        return vectors[-limit:]

    def should_recompute(self, max_age_hours: int = 6) -> True:
        """判断是否需要重新计算"""
        latest = self.get_latest_features()
        if latest is None:
            return True
        age_hours = (time.time() - latest.computed_at) / 3600
        return age_hours > max_age_hours

    def get_feature_summary(self) -> str:
        """获取人类可读的特征摘要"""
        vector = self.get_latest_features()
        if vector is None:
            return "暂无特征数据，请先运行 compute_features()"

        lines = [
            "=== 用户行为特征摘要 ===",
            f"计算时间: {datetime.fromtimestamp(vector.computed_at).strftime('%Y-%m-%d %H:%M')}",
            f"分析窗口: {vector.window_days} 天",
            f"总事件数: {vector.total_events}",
            f"会话数: {vector.session_count}",
            f"平均会话时长: {vector.avg_session_duration_min:.1f} 分钟",
            f"成功率: {vector.success_rate:.1%}",
            f"参与度趋势: {vector.engagement_trend}",
            f"成功率趋势: {vector.success_trend}",
        ]

        # 最活跃时段
        if any(v > 0 for v in vector.active_hours.values()):
            peak_hour = max(vector.active_hours, key=vector.active_hours.get)  # type: ignore
            lines.append(f"最活跃时段: {peak_hour}:00")

        # 最常用技能
        if vector.skill_preferences:
            top_skill = max(vector.skill_preferences, key=vector.skill_preferences.get)  # type: ignore
            lines.append(f"最常用技能: {top_skill} ({vector.skill_preferences[top_skill]:.1%})")

        return "\n".join(lines)
