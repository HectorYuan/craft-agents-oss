"""
TUI 数据适配器

统一数据访问层，封装所有引擎调用。
屏幕层通过此适配器获取数据，不直接调用引擎。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.paths import get_user_data_dir, SkillStateManager
from ..systems.visualization.ability_calculator import AbilityCalculator
from ..systems.visualization.metrics_store import MetricsStore
from ..systems.cultivating.skill_manifest import SkillManifest, SkillLevel
from ..systems.active.goal_engine import ActiveGoalEngine
from ..systems.active.task_recommender import TaskRecommendationEngine
from ..systems.active.proactive_insight import ProactiveInsightEngine
from ..systems.visualization.insight_engine import GrowthInsightEngine
from ..systems.cultivating.cultivating_system import CultivatingSystem
from ..mirroring.feature_store import FeatureStore
from ..mirroring.privacy_layer import PrivacyLayer
from ..mirroring.event_collector import EventCollector


class TuiDataAdapter:
    """TUI 统一数据访问层

    所有数据读取方法在遇到异常时返回安全默认值，保证 TUI 不崩溃。
    """

    def get_skill_state(self, skill_id: str) -> Dict[str, Any]:
        """获取技能状态"""
        try:
            return SkillStateManager(skill_id).load()
        except Exception:
            return {"level": "NOVICE", "usage_count": 0, "skill_name": skill_id, "metrics": {}, "episodes": []}

    def list_skills(self) -> List[Dict[str, Any]]:
        """列出所有技能"""
        states_dir = get_user_data_dir() / "states"
        if not states_dir.exists():
            return []
        skills = []
        for f in sorted(states_dir.glob("*.json")):
            if f.name.endswith(".history.jsonl"):
                continue
            try:
                skill_id = f.stem
                manager = SkillStateManager(skill_id)
                manager.state_path = f
                manager.history_path = f.with_suffix(".history.jsonl")
                state = manager.load()
                if manager.last_load_recovery_failed:
                    continue
                skills.append({
                    "skill_id": skill_id,
                    "level": state.get("level", "NOVICE"),
                    "usage_count": state.get("usage_count", 0),
                    "last_used": state.get("last_used", ""),
                    "success_rate": state.get("metrics", {}).get("success_rate", 0.0),
                })
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                continue
        return skills

    def get_ability_scores(self, skill_id: str) -> Optional[Any]:
        """计算五维能力分数"""
        try:
            state = self.get_skill_state(skill_id)
            calculator = AbilityCalculator()
            store = MetricsStore(skill_id)
            snapshots = store.get_all_snapshots()

            manifest = SkillManifest(
                skill_id=skill_id,
                skill_name=state.get("skill_name", skill_id),
            )
            manifest.current_level = SkillLevel[state.get("level", "NOVICE")]
            manifest.stats.total_interactions = state.get("usage_count", 0)
            manifest.stats.successful_executions = state.get("metrics", {}).get("successful_executions", 0)
            manifest.stats.user_feedback_score = state.get("metrics", {}).get("user_feedback_score", 0.8)
            manifest.stats.memory_usage_count = len(state.get("episodes", []))
            manifest.stats.average_response_time_ms = state.get("metrics", {}).get("avg_duration_ms", 500)

            return calculator.calculate_from_skill_manifest(manifest)
        except Exception:
            return None

    def get_previous_scores(self, skill_id: str) -> Optional[Dict[str, int]]:
        """获取上一次的能力分数快照"""
        store = MetricsStore(skill_id)
        prev = store.get_previous_snapshot()
        if prev and hasattr(prev, "ability_scores"):
            return prev.ability_scores
        return None

    def get_metric_history(self, skill_id: str, n: int = 30) -> List[Any]:
        """获取指标历史"""
        store = MetricsStore(skill_id)
        return store.get_all_snapshots()[-n:]

    def get_active_goals(self, skill_id: str) -> List[Any]:
        """获取活跃目标"""
        try:
            engine = ActiveGoalEngine(skill_id)
            return engine.get_active_goals()
        except Exception:
            return []

    def get_goal_progress(self, skill_id: str, goal: Any) -> Any:
        """获取目标进度"""
        engine = ActiveGoalEngine(skill_id)
        return engine.get_goal_progress(goal)

    def suggest_goals(self, skill_id: str) -> List[Any]:
        """推荐成长目标"""
        engine = ActiveGoalEngine(skill_id)
        return engine.suggest_goals()

    def get_pending_tasks(self, skill_id: str) -> List[Any]:
        """获取待办推荐任务（无任务时自动生成）"""
        engine = TaskRecommendationEngine(skill_id)
        tasks = engine.get_pending_tasks()
        if not tasks:
            # 首次访问时自动生成基于技能状态的推荐任务
            engine.recommend_tasks(count=5)
            tasks = engine.get_pending_tasks()
        return tasks

    def complete_task(self, skill_id: str, task_id: str) -> bool:
        """完成任务"""
        engine = TaskRecommendationEngine(skill_id)
        return engine.complete_task(task_id)

    def get_insights(self, skill_id: str, include_read: bool = False) -> List[Any]:
        """获取洞察列表"""
        try:
            engine = ProactiveInsightEngine(skill_id)
            if include_read:
                return engine.get_all_insights()
            return engine.get_unread_insights()
        except Exception:
            return []

    def get_growth_report(self, skill_id: str) -> str:
        """获取成长洞察报告"""
        try:
            engine = GrowthInsightEngine(skill_id)
            return engine.generate_insight_report()
        except Exception:
            return "数据不足，暂时无法生成报告"

    def get_growth_compare(self, skill_id: str) -> str:
        from ..systems.active.growth_analyzer import GrowthAnalyzer
        return GrowthAnalyzer(skill_id).format_compare()

    def get_growth_replay(self, skill_id: str) -> str:
        from ..systems.active.growth_analyzer import GrowthAnalyzer
        return GrowthAnalyzer(skill_id).format_replay()

    def get_error_clusters(self, skill_id: str) -> str:
        from ..systems.active.error_cluster import ErrorClusterAnalyzer
        return ErrorClusterAnalyzer(skill_id).format_report()

    def get_instant_feedback(self, skill_id: str) -> str:
        from ..systems.active.instant_feedback import InstantFeedbackEngine
        return InstantFeedbackEngine(skill_id).format_report()

    def get_custom_dimensions(self, skill_id: str) -> str:
        from ..systems.active.custom_dimensions import CustomDimensionManager
        return CustomDimensionManager(skill_id).format_report()

    def get_habits(self, skill_id: str) -> str:
        from ..systems.active.habit_tracker import HabitTracker
        return HabitTracker(skill_id).format_report()

    def get_achievements(self, skill_id: str) -> str:
        from ..systems.active.achievement_system import AchievementSystem
        return AchievementSystem(skill_id).format_report()

    def get_feature_summary(self) -> str:
        """获取用户镜像特征摘要"""
        try:
            store = FeatureStore()
            return store.get_feature_summary()
        except Exception:
            return "特征数据不足"

    def get_privacy_prefs(self) -> Any:
        """获取隐私偏好"""
        try:
            privacy = PrivacyLayer()
            return privacy.get_prefs()
        except Exception:
            return None

    def get_mirror_data_summary(self) -> Dict[str, Any]:
        """获取镜像数据概览"""
        try:
            privacy = PrivacyLayer()
            collector = EventCollector()
            summary = privacy.get_data_summary()
            summary["event_count"] = collector.get_event_count()
            return summary
        except Exception:
            return {"event_count": 0, "total_size_bytes": 0}

    def mark_insight_read(self, skill_id: str, insight_id: str) -> bool:
        """标记洞察已读"""
        engine = ProactiveInsightEngine(skill_id)
        return engine.mark_as_read(insight_id)

    def mark_all_insights_read(self, skill_id: str) -> int:
        """标记所有洞察已读"""
        engine = ProactiveInsightEngine(skill_id)
        return engine.mark_all_as_read()

    def complete_goal(self, skill_id: str, goal_id: str) -> bool:
        """完成目标"""
        engine = ActiveGoalEngine(skill_id)
        return engine.complete_goal(goal_id)

    def create_goal(self, skill_id: str, dimension: str, target_score: int) -> Any:
        """创建新目标"""
        engine = ActiveGoalEngine(skill_id)
        return engine.create_goal(dimension=dimension, target_score=target_score)

    def get_cultivating_info(self, skill_id: str) -> Optional[Any]:
        """获取修炼体系信息"""
        try:
            system = CultivatingSystem()
            return system.get_manifest(skill_id)
        except Exception:
            return None

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """
        获取仪表盘今日摘要 (10C)

        Returns:
            {
                "today_usage": 今日交互次数,
                "active_skills": 活跃技能数,
                "avg_session_min": 平均会话时长(分钟),
                "today_insights": 今日洞察数,
                "running_session": 当前正在会话中,
                "recent_tools": 最近工具列表,
                "perception_alerts": 感知告警列表,
            }
        """
        import time
        from pathlib import Path
        from datetime import datetime

        result: Dict[str, Any] = {
            "today_usage": 0,
            "active_skills": 0,
            "avg_session_min": 0,
            "today_insights": 0,
            "running_session": False,
            "recent_tools": [],
            "perception_alerts": [],
            "event_count": 0,
        }

        # 会话缓存
        sf = Path.home() / ".zenskill" / "session" / "current.json"
        if sf.exists():
            try:
                s = json.loads(sf.read_text(encoding="utf-8"))
                tc = s.get("tool_count", 0)
                started = s.get("started", 0)
                tools = s.get("recent_tools", [])
                elapsed = (time.time() - started) / 60 if started else 0
                result["today_usage"] = tc
                result["running_session"] = tc > 0
                result["recent_tools"] = tools[-5:] if tools else []
                result["avg_session_min"] = round(elapsed, 1) if elapsed else 0
            except Exception:
                pass

        # pipeline 数据
        pf = Path.home() / ".zenskill" / "mirroring" / "pipeline.json"
        if pf.exists():
            try:
                p = json.loads(pf.read_text(encoding="utf-8"))
                result["event_count"] = p.get("event_count", 0)
                nlp = p.get("nlp", {})
                if nlp.get("intents"):
                    result["today_insights"] = sum(nlp["intents"].values())
            except Exception:
                pass

        # 活跃技能
        try:
            skills = self.list_skills()
            result["active_skills"] = len(skills)
        except Exception:
            pass

        # 感知告警
        try:
            from ..perception_engine import PerceptionEngine
            engine = PerceptionEngine()
            lt = time.localtime(time.time())
            ctx = {
                "tool_count": result["today_usage"],
                "elapsed_min": result["avg_session_min"],
                "recent_tools": result["recent_tools"],
                "current_hour": lt.tm_hour,
                "current_minute": lt.tm_min,
                "last_command": "",
                "error_rate": 0.0,
            }
            p = engine.evaluate(ctx)
            result["perception_alerts"] = p.get("alerts", [])
        except Exception:
            pass

        return result
