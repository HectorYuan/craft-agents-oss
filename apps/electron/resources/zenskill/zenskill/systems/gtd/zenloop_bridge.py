"""
8.7T: ZenLoop × GTD 联动

为 ZenLoop 四大循环提供 GTD 数据:
- Reflect: Review 本周完成的 Action / 未完成的 Project
- Consolidate: Incubating → 夜间自动合并相关记忆为语义知识
- Insight: 从 Incubating 孵化池中提取跨界连接
- Purify: 清理 >30 天未活动的 Incubating items / 重复 Action
"""

from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class GTDZenLoopBridge:
    """GTD × ZenLoop 联动桥接器"""

    def __init__(self, data_dir: str = ""):
        self._data_dir = data_dir

    def reflect_gtd_review(self) -> dict:
        """Reflect 循环: Review 本周完成的 Action / 未完成的 Project"""
        try:
            from .action import ActionEngine
            from .project import ProjectEngine

            actions = ActionEngine(data_dir=self._data_dir)
            projects = ProjectEngine(data_dir=self._data_dir)

            # 本周完成的 Action
            done_actions = actions.list(status="done", limit=50)
            stats = actions.stats()

            # 未完成的 Project
            active_projects = projects.list(status="active")
            dash = projects.dashboard()

            result = {
                "review_type": "weekly_gtd",
                "actions_done": len(done_actions),
                "actions_pending": stats["pending"],
                "actions_overdue": stats["overdue"],
                "projects_active": len(active_projects),
                "projects_stale": dash["stale"],
                "stale_project_names": dash["stale_projects"],
            }

            # 生成反思文本
            lines = [f"📋 GTD 周回顾: {len(done_actions)} 完成 / {stats['pending']} 待办"]
            if stats["overdue"] > 0:
                lines.append(f"  ⚠️ {stats['overdue']} 个 Action 已逾期")
            if dash["stale"] > 0:
                lines.append(f"  📦 {dash['stale']} 个项目停滞 >7天: {', '.join(dash['stale_projects'][:3])}")
            result["reflection_text"] = "\n".join(lines)

            return result
        except Exception as e:
            logger.warning(f"Reflect GTD review failed: {e}")
            return {"review_type": "weekly_gtd", "error": str(e)}

    def consolidate_incubating(self) -> dict:
        """Consolidate 循环: Incubating → 夜间自动合并相关记忆"""
        try:
            from .incubating import IncubatingEngine

            engine = IncubatingEngine(data_dir=self._data_dir)
            result = engine.run_zenloop_cycle()

            return {
                "consolidate_type": "incubating",
                "matured": result.get("matured", 0),
                "archived": result.get("archived", 0),
                "total_active": result.get("total_active", 0),
                "message": f"孵化周期: {result['matured']} 成熟, {result['archived']} 清理",
            }
        except Exception as e:
            logger.warning(f"Consolidate incubating failed: {e}")
            return {"consolidate_type": "incubating", "error": str(e)}

    def insight_incubating(self) -> dict:
        """Insight 循环: 从 Incubating 孵化池中提取跨界连接"""
        try:
            from .incubating import IncubatingEngine

            engine = IncubatingEngine(data_dir=self._data_dir)
            ready = engine.ready_to_promote()

            if not ready:
                return {
                    "insight_type": "incubating",
                    "ready_count": 0,
                    "message": "孵化池中无成熟项",
                }

            # 自动提升成熟项为 Action
            promoted = []
            for item in ready:
                engine.promote(item.id)
                promoted.append(item.raw_concept[:50])

            return {
                "insight_type": "incubating",
                "ready_count": len(ready),
                "promoted": promoted,
                "message": f"提升 {len(ready)} 个孵化项为 Action",
            }
        except Exception as e:
            logger.warning(f"Insight incubating failed: {e}")
            return {"insight_type": "incubating", "error": str(e)}

    def purify_stale(self) -> dict:
        """Purify 循环: 清理 >30 天未活动的 Incubating items / 重复 Action"""
        try:
            from .incubating import IncubatingEngine
            from .action import ActionEngine

            # 清理 Incubating
            incubating = IncubatingEngine(data_dir=self._data_dir)
            incubating_result = incubating.run_zenloop_cycle()

            # 清理重复 Action (同 title 的 pending 只保留最新)
            actions = ActionEngine(data_dir=self._data_dir)
            all_actions = actions.list(status="pending", limit=1000)
            seen_titles = {}
            duplicates = []
            for a in all_actions:
                if a.title in seen_titles:
                    duplicates.append(a.id)
                else:
                    seen_titles[a.title] = a.id
            for dup_id in duplicates:
                actions.delete(dup_id)

            return {
                "purify_type": "stale_cleanup",
                "incubating_archived": incubating_result.get("archived", 0),
                "duplicate_actions_removed": len(duplicates),
                "message": f"净化: {incubating_result.get('archived', 0)} 孵化项清理, {len(duplicates)} 重复 Action 删除",
            }
        except Exception as e:
            logger.warning(f"Purify stale failed: {e}")
            return {"purify_type": "stale_cleanup", "error": str(e)}

    def run_all_cycles(self) -> dict:
        """运行所有 GTD × ZenLoop 联动周期"""
        return {
            "reflect": self.reflect_gtd_review(),
            "consolidate": self.consolidate_incubating(),
            "insight": self.insight_incubating(),
            "purify": self.purify_stale(),
        }
