"""
跨技能迁移学习 + 成长预测 (Phase 8E + 8F)

8E: 从高表现技能中提取成功模式, 推荐给低表现技能
8F: 基于历史数据预测技能成长轨迹
"""

from typing import Any, Dict, List, Optional, Tuple

from .dependency_graph import SkillDependencyGraph, SkillNode


class SkillTransferEngine:
    """8E: 跨技能迁移学习引擎"""

    def __init__(self, graph: Optional[SkillDependencyGraph] = None):
        self.graph = graph or SkillDependencyGraph()

    def find_transferable_patterns(self) -> List[Dict]:
        """找到可迁移的成功模式

        算法:
        1. 找出综合分最高的技能 (source)
        2. 找出综合分最低但有关联的技能 (target)
        3. 分析 source 的成长模式 → 推荐给 target
        """
        nodes = self.graph.get_all_skills()
        if len(nodes) < 2:
            return []

        # 排序: 综合分降序
        ranked = sorted(nodes, key=lambda n: n.composite_score, reverse=True)
        source = ranked[0]  # 最高分
        target = ranked[-1]  # 最低分

        if source.composite_score - target.composite_score < 10:
            return []  # 差异太小, 不建议迁移

        patterns = self._analyze_growth_pattern(source, target)
        suggestions = self._generate_suggestions(source, target, patterns)

        return [{
            "source_skill": source.skill_id,
            "source_score": source.composite_score,
            "target_skill": target.skill_id,
            "target_score": target.composite_score,
            "gap": source.composite_score - target.composite_score,
            "patterns": patterns,
            "suggestions": suggestions,
        }]

    def _analyze_growth_pattern(self, source: SkillNode, target: SkillNode) -> Dict:
        """分析成长模式差异"""
        s_abilities = source.ability_scores or {}
        t_abilities = target.ability_scores or {}

        dims = ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]

        # 计算各维度差异
        gaps = {}
        strengths = []
        weaknesses = []
        for dim in dims:
            sv = s_abilities.get(dim, 0)
            tv = t_abilities.get(dim, 0)
            gaps[dim] = sv - tv
            if sv - tv > 10:
                strengths.append(dim)
            elif tv - sv > 5:
                weaknesses.append(dim)

        return {
            "dimension_gaps": gaps,
            "source_strengths": strengths,
            "target_weaknesses": weaknesses,
        }

    def _generate_suggestions(
        self, source: SkillNode, target: SkillNode, patterns: Dict
    ) -> List[str]:
        """基于模式差异生成迁移建议"""
        suggestions = []
        dim_names = {"proficiency": "熟练度", "stability": "稳定性",
                     "satisfaction": "满意度", "responsiveness": "响应力", "memory": "记忆度"}

        gaps = patterns["dimension_gaps"]
        for dim, gap in sorted(gaps.items(), key=lambda x: x[1], reverse=True):
            if gap > 10:
                suggestions.append(
                    f"{source.skill_id} 的 {dim_names.get(dim, dim)} 比 "
                    f"{target.skill_id} 高 {gap:.0f} 分 — "
                    f"建议 {target.skill_id} 采用 {source.skill_id} 的 {dim_names.get(dim, dim)} 练习策略"
                )

        if not suggestions:
            suggestions.append(
                f"{target.skill_id} 可以借鉴 {source.skill_id} 的整体学习方法"
            )
        return suggestions


class GrowthPredictor:
    """8F: 技能成长预测"""

    def predict(self, history: List[Dict[str, Any]], days_ahead: int = 14) -> Dict:
        """基于历史数据预测未来成长轨迹

        Args:
            history: [{timestamp, ability_scores: {dim: score}}]
            days_ahead: 预测未来天数

        Returns:
            预测结果
        """
        if len(history) < 3:
            return {"error": "需要至少 3 个历史数据点"}

        dims = ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]
        dim_names = {"proficiency": "熟练度", "stability": "稳定性",
                     "satisfaction": "满意度", "responsiveness": "响应力", "memory": "记忆度"}
        predictions = {}

        for dim in dims:
            vals = []
            for snap in history:
                scores = snap.get("ability_scores", snap.get("ability_scores", snap))
                if isinstance(scores, dict):
                    vals.append(scores.get(dim, 0))

            if len(vals) < 3:
                continue

            # 简单线性回归: y = a*x + b
            n = len(vals)
            x_mean = (n - 1) / 2
            y_mean = sum(vals) / n
            num = sum((i - x_mean) * (vals[i] - y_mean) for i in range(n))
            den = sum((i - x_mean) ** 2 for i in range(n))
            slope = num / den if den > 0 else 0.01

            # 外推
            current = vals[-1]
            predicted = current + slope * (days_ahead / 7)  # 按周换算

            # 检测平台期
            recent_growth = vals[-1] - vals[-min(5, len(vals))]
            if recent_growth < 2 and len(vals) >= 5:
                stagnation = True
                stagnation_msg = f"{dim_names.get(dim, dim)} 已进入平台期, 建议改变策略"
            else:
                stagnation = False
                stagnation_msg = ""

            predictions[dim] = {
                "name": dim_names.get(dim, dim),
                "current": round(current, 1),
                "predicted": round(min(predicted, 100), 1),
                "weekly_growth": round(slope, 2),
                "stagnation": stagnation,
                "stagnation_msg": stagnation_msg,
            }

        # 综合预测
        if predictions:
            avg_weekly = sum(p["weekly_growth"] for p in predictions.values()) / len(predictions)
            stagnations = [p for p in predictions.values() if p["stagnation"]]

            fastest_dim = max(predictions.items(), key=lambda x: x[1]["weekly_growth"])
            return {
                "dimensions": predictions,
                "avg_weekly_growth": round(avg_weekly, 2),
                "stagnant_dimensions": len(stagnations),
                "fastest_growing": fastest_dim[0],
                "fastest_name": fastest_dim[1]["name"],
                "fastest_growth": fastest_dim[1]["weekly_growth"],
            }

        return {"error": "无有效维度数据"}
