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

    def consolidate_incubating(self, maturity: Optional[dict] = None) -> dict:
        """Consolidate 循环: 检查孵化池 check_after 到期项。

        成熟度增长由 run_all_cycles 中唯一一次 run_zenloop_cycle 统一驱动，
        这里不再各调一次（否则单次 bridge run 成熟度 +0.2）。"""
        try:
            from .incubating import IncubatingEngine
            from datetime import datetime

            engine = IncubatingEngine(data_dir=self._data_dir)
            today = datetime.now().strftime("%Y-%m-%d")
            active = engine.list(status="active", limit=1000)
            due = [i for i in active
                   if i.check_after and i.check_after[:10] <= today]

            result = {
                "consolidate_type": "incubating",
                "matured": 0,
                "archived": 0,
                "total_active": len(active),
                "due_for_review": [i.id for i in due],
                "message": (f"孵化检查: {len(due)} 项到期复核, "
                            f"{len(active)} 项活跃"),
            }
            if maturity is not None and "error" not in maturity:
                result["matured"] = maturity.get("matured", 0)
                result["archived"] = maturity.get("archived", 0)
            return result
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
        """Purify 循环: 归档 >30 天未活动的 Incubating items / 清理重复 Action。

        不再调用 run_zenloop_cycle（成熟度增长统一由 run_all_cycles 驱动）。"""
        try:
            from .incubating import IncubatingEngine
            from .action import ActionEngine
            from datetime import datetime, timedelta

            # 归档 >30 天的 purify 通道孵化项（与引擎内清理口径一致）
            incubating = IncubatingEngine(data_dir=self._data_dir)
            cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            incubating_archived = 0
            for item in incubating.list(status="active", limit=1000):
                if item.channel == "purify" and item.entered_at[:10] < cutoff:
                    if incubating.archive(item.id):
                        incubating_archived += 1

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
                "incubating_archived": incubating_archived,
                "duplicate_actions_removed": len(duplicates),
                "message": f"净化: {incubating_archived} 孵化项清理, {len(duplicates)} 重复 Action 删除",
            }
        except Exception as e:
            logger.warning(f"Purify stale failed: {e}")
            return {"purify_type": "stale_cleanup", "error": str(e)}

    def _run_maturity_cycle(self) -> dict:
        """全池唯一一次 ZenLoop 成熟度周期（run_all_cycles 专用入口）"""
        try:
            from .incubating import IncubatingEngine

            engine = IncubatingEngine(data_dir=self._data_dir)
            return engine.run_zenloop_cycle()
        except Exception as e:
            logger.warning(f"ZenLoop maturity cycle failed: {e}")
            return {"error": str(e)}

    def run_all_cycles(self) -> dict:
        """运行所有 GTD × ZenLoop 联动周期（成熟度增长仅此一处）"""
        maturity = self._run_maturity_cycle()
        return {
            "reflect": self.reflect_gtd_review(),
            "consolidate": self.consolidate_incubating(maturity=maturity),
            "insight": self.insight_incubating(),
            "purify": self.purify_stale(),
        }
