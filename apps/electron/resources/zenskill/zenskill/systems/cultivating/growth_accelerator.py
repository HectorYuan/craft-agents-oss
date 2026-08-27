"""
成长加速器 (Phase 7I)

检测学习陡坡: 当某个维度的增长速度超过历史均值 2 倍时，
自动生成加速建议和强化计划。
"""

from typing import Any, Dict, List, Optional


class GrowthAccelerator:
    """检测并放大学习陡坡"""

    def detect(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """检测加速中的技能维度

        Args:
            history: 技能状态历史 [{timestamp, ability_scores: {dim: score}}]

        Returns:
            加速建议列表
        """
        if len(history) < 5:
            return []

        suggestions = []
        dims = ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]
        dim_names = {"proficiency": "熟练度", "stability": "稳定性",
                     "satisfaction": "满意度", "responsiveness": "响应力", "memory": "记忆度"}

        for dim in dims:
            vals = []
            for snap in history:
                scores = snap.get("ability_scores", snap)
                if isinstance(scores, dict):
                    vals.append(scores.get(dim, 0))

            if len(vals) < 5:
                continue

            # 最近 5 次 vs 前 5 次的增长率对比
            recent_growth = vals[-1] - vals[-5]
            early_growth = vals[4] - vals[0] if len(vals) >= 10 else 1
            avg_growth = early_growth / max(len(vals) - 5, 1) if early_growth > 0 else 1

            if recent_growth > avg_growth * 2 and recent_growth > 3:
                suggestions.append({
                    "dimension": dim,
                    "name": dim_names.get(dim, dim),
                    "recent_growth": round(recent_growth, 1),
                    "avg_growth": round(avg_growth, 1),
                    "message": (
                        f"{dim_names.get(dim, dim)} 正在快速成长 "
                        f"(近期+{recent_growth:.0f} vs 均+{avg_growth:.0f})，"
                        f"建议趁热打铁，增加练习频率"
                    ),
                    "action": f"连续 3 天集中练习 {dim_names.get(dim, dim)} 相关任务",
                })

        return suggestions
