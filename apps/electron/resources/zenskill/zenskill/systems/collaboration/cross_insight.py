"""
ZenSkill - 跨技能洞察整合系统

整合多个技能的洞察，发现跨领域的模式和规律：
- 全局成长报告：所有技能的综合分析
- 跨技能对比：各能力维度的横向对比
- 模式迁移分析：哪些模式在多个技能中都有效
- 短板共性分析：多个技能共同的问题
- 协同效应检测：技能组合使用的增益
"""

from __future__ import annotations

import json
import time
import math
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

from zenskill.core.paths import get_user_data_dir
from zenskill.systems.visualization.metrics_store import MetricsStore
from zenskill.systems.collaboration.dependency_graph import SkillDependencyGraph, SkillNode


@dataclass
class CrossSkillInsight:
    """跨技能洞察"""
    insight_id: str
    type: str  # comparison / pattern / bottleneck / synergy / milestone
    severity: str  # low / medium / high
    title: str
    content: str
    affected_skills: List[str]
    data_evidence: Dict[str, Any]
    created_at: str = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


class CrossSkillInsightEngine:
    """
    跨技能洞察引擎

    从全局视角分析多个技能的数据，产生跨领域的洞察：
    - 技能间的强弱对比
    - 共同存在的问题和瓶颈
    - 成功模式的普适性
    - 协同效应检测
    """

    def __init__(self):
        self.graph = SkillDependencyGraph()
        self.insights_dir = self._get_insights_dir()
        self.insights_file = self.insights_dir / "cross_skill_insights.jsonl"

    def _get_insights_dir(self) -> Path:
        """获取洞察存储目录"""
        user_dir = get_user_data_dir()
        insights_dir = user_dir / "cross_insights"
        insights_dir.mkdir(parents=True, exist_ok=True)
        return insights_dir

    def _generate_id(self) -> str:
        """生成唯一 ID"""
        timestamp = int(time.time() * 1000)
        return f"cross_{timestamp}"

    def generate_global_report(self) -> str:
        """
        生成全局成长报告

        Returns:
            格式化的报告字符串
        """
        skills = self.graph.get_all_skills()

        lines = []
        lines.append("🌐 技能生态系统 - 全局成长报告")
        lines.append("═" * 60)
        lines.append("")

        if not skills:
            lines.append("   暂无注册的技能")
            lines.append("")
            lines.append("💡 使用 'zenskill graph register <skill_id>' 注册技能")
            return "\n".join(lines)

        # 1. 整体统计
        lines.append("📊 整体概览")
        total_interactions = sum(s.interaction_count for s in skills)
        avg_score = sum(s.composite_score for s in skills) / len(skills) if skills else 0

        level_counts: Dict[str, int] = defaultdict(int)
        for s in skills:
            level_counts[s.level] += 1

        lines.append(f"   技能总数: {len(skills)} 个")
        lines.append(f"   总交互次数: {total_interactions} 次")
        lines.append(f"   平均综合分数: {avg_score:.1f}")
        lines.append("")

        # 境界分布
        lines.append("   境界分布:")
        for level, count in level_counts.items():
            icon = {"NOVICE": "🌱", "APPRENTICE": "🌿", "ADEPT": "🌳", "EXPERT": "🌲", "MASTER": "🏆"}.get(level, "❓")
            lines.append(f"      {icon} {level}: {count} 个")
        lines.append("")

        # 2. 维度对比分析
        lines.append("🔍 跨技能维度对比")
        dimensions = ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]
        dim_names = {
            "proficiency": "熟练度",
            "stability": "稳定性",
            "satisfaction": "满意度",
            "responsiveness": "响应力",
            "memory": "记忆力",
        }

        for dim in dimensions:
            scores = [s.dimension_scores.get(dim, 0) for s in skills]
            if scores:
                avg = sum(scores) / len(scores)
                max_score = max(scores)
                min_score = min(scores)
                variance = sum((s - avg) ** 2 for s in scores) / len(scores) if scores else 0

                lines.append(f"   {dim_names.get(dim, dim)}:")
                lines.append(f"      平均: {avg:.1f} | 最高: {max_score:.1f} | 最低: {min_score:.1f}")

                # 技能间差异评估
                if variance > 100:
                    lines.append(f"      ⚠️ 技能间差异较大（方差 {variance:.1f}）")
                elif variance > 25:
                    lines.append(f"      ℹ️ 技能间有一定差异（方差 {variance:.1f}）")
                else:
                    lines.append(f"      ✅ 技能间发展均衡（方差 {variance:.1f}）")
        lines.append("")

        # 3. 最强和最弱技能
        sorted_skills = sorted(skills, key=lambda s: s.composite_score, reverse=True)
        lines.append("🏆 技能排行榜")

        lines.append("   最强技能 TOP 3:")
        for i, skill in enumerate(sorted_skills[:3], 1):
            icon = {"NOVICE": "🌱", "APPRENTICE": "🌿", "ADEPT": "🌳", "EXPERT": "🌲", "MASTER": "🏆"}.get(skill.level, "❓")
            lines.append(f"      {i}. {icon} {skill.name} - {skill.composite_score:.0f} 分")

        if len(sorted_skills) > 3:
            lines.append("")
            lines.append("   需要关注的技能:")
            for skill in sorted_skills[-3:]:
                lines.append(f"      💡 {skill.name} - {skill.composite_score:.0f} 分（建议加强）")
        lines.append("")

        # 4. 协同效应分析
        relations = self.graph.relations
        if relations:
            strong_relations = [r for r in relations if r.strength > 0.6]
            if strong_relations:
                lines.append("🔗 强关联技能对")
                for rel in strong_relations[:3]:
                    from_skill = self.graph.get_skill(rel.from_skill)
                    to_skill = self.graph.get_skill(rel.to_skill)
                    from_name = from_skill.name if from_skill else rel.from_skill
                    to_name = to_skill.name if to_skill else rel.to_skill
                    lines.append(f"   • {from_name} ←→ {to_name}（强度 {rel.strength:.0%}）")
                lines.append("")

        # 5. 洞察摘要
        insights = self.generate_cross_insights()
        if insights:
            lines.append("💡 跨技能洞察")
            for insight in insights[:3]:
                icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(insight.severity, "⚪")
                lines.append(f"   {icon} {insight.title}")
                lines.append(f"      {insight.content}")
                if len(insight.affected_skills) > 1:
                    lines.append(f"      影响: {', '.join(insight.affected_skills[:3])} {'等' if len(insight.affected_skills) > 3 else ''}")
            lines.append("")

        lines.append("💡 使用 'zenskill cross insights' 查看完整洞察列表")
        lines.append("💡 使用 'zenskill cross compare' 查看详细对比分析")

        return "\n".join(lines)

    def generate_cross_insights(self) -> List[CrossSkillInsight]:
        """
        生成跨技能洞察列表

        Returns:
            洞察列表
        """
        skills = self.graph.get_all_skills()
        insights: List[CrossSkillInsight] = []

        if len(skills) < 2:
            return insights

        # 洞察 1: 共同瓶颈检测
        common_bottlenecks = self._find_common_bottlenecks(skills)
        insights.extend(common_bottlenecks)

        # 洞察 2: 成功模式迁移
        pattern_insights = self._find_transferable_patterns(skills)
        insights.extend(pattern_insights)

        # 洞察 3: 协同效应
        synergy_insights = self._detect_synergy_effects(skills)
        insights.extend(synergy_insights)

        # 洞察 4: 发展不均衡
        imbalance_insights = self._detect_imbalance_issues(skills)
        insights.extend(imbalance_insights)

        return insights

    def _find_common_bottlenecks(self, skills: List[SkillNode]) -> List[CrossSkillInsight]:
        """检测多个技能共同存在的能力瓶颈"""
        insights = []
        dimensions = ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]
        dim_names = {
            "proficiency": "熟练度",
            "stability": "稳定性",
            "satisfaction": "满意度",
            "responsiveness": "响应力",
            "memory": "记忆力",
        }

        for dim in dimensions:
            low_score_skills = [s for s in skills if s.dimension_scores.get(dim, 0) < 30]
            if len(low_score_skills) >= 2:  # 至少 2 个技能在该维度得分低
                insight = CrossSkillInsight(
                    insight_id=self._generate_id(),
                    type="bottleneck",
                    severity="medium" if len(low_score_skills) > len(skills) / 2 else "low",
                    title=f"发现共同瓶颈：{dim_names.get(dim, dim)}",
                    content=f"有 {len(low_score_skills)} 个技能在 {dim_names.get(dim, dim)} 维度得分较低（< 30分），这是一个系统性的提升机会。建议针对该维度进行专项训练，效果会在多个技能中体现。",
                    affected_skills=[s.skill_id for s in low_score_skills],
                    data_evidence={"dimension": dim, "low_skill_count": len(low_score_skills)},
                )
                insights.append(insight)

        return insights

    def _find_transferable_patterns(self, skills: List[SkillNode]) -> List[CrossSkillInsight]:
        """发现可迁移的成功模式"""
        insights = []

        # 找出高表现技能（ADEPT 及以上）
        high_performers = [s for s in skills if s.level in ["ADEPT", "EXPERT", "MASTER"]]
        low_performers = [s for s in skills if s.level in ["NOVICE", "APPRENTICE"]]

        if high_performers and low_performers:
            # 分析高表现技能的能力分布
            high_dims: Dict[str, List[float]] = defaultdict(list)
            for s in high_performers:
                for dim, score in s.dimension_scores.items():
                    high_dims[dim].append(score)

            # 找出高表现技能的共性优势
            high_avg = {dim: sum(scores) / len(scores) for dim, scores in high_dims.items()}
            strong_dims = [dim for dim, avg in high_avg.items() if avg > 60]

            if strong_dims:
                insight = CrossSkillInsight(
                    insight_id=self._generate_id(),
                    type="pattern",
                    severity="low",
                    title="发现可迁移的成功模式",
                    content=f"高表现技能在 {', '.join(strong_dims)} 维度表现突出。建议在其他技能训练中也重点加强这些维度，可能获得类似的成长效果。",
                    affected_skills=[s.skill_id for s in low_performers],
                    data_evidence={"strong_dimensions": strong_dims, "high_performer_count": len(high_performers)},
                )
                insights.append(insight)

        return insights

    def _detect_synergy_effects(self, skills: List[SkillNode]) -> List[CrossSkillInsight]:
        """检测技能间的协同效应"""
        insights = []

        # 找出强关联技能对
        relations = self.graph.relations
        strong_pairs = [(r.from_skill, r.to_skill, r.strength)
                        for r in relations if r.strength > 0.7]

        if strong_pairs:
            for from_id, to_id, strength in strong_pairs:
                from_skill = self.graph.get_skill(from_id)
                to_skill = self.graph.get_skill(to_id)

                if from_skill and to_skill:
                    both_high = from_skill.level in ["ADEPT", "EXPERT"] and to_skill.level in ["ADEPT", "EXPERT"]
                    if both_high:
                        insight = CrossSkillInsight(
                            insight_id=self._generate_id(),
                            type="synergy",
                            severity="low",
                            title="技能协同效应",
                            content=f"{from_skill.name} 和 {to_skill.name} 都达到了较高境界，强关联技能同时提升会产生 1+1>2 的效果。建议继续保持这对技能的同步训练。",
                            affected_skills=[from_id, to_id],
                            data_evidence={"strength": strength},
                        )
                        insights.append(insight)

        return insights

    def _detect_imbalance_issues(self, skills: List[SkillNode]) -> List[CrossSkillInsight]:
        """检测技能发展不均衡问题"""
        insights = []

        if len(skills) < 3:
            return insights

        scores = [s.composite_score for s in skills]
        avg_score = sum(scores) / len(scores)
        variance = sum((s - avg_score) ** 2 for s in scores) / len(scores)

        if variance > 400:  # 方差过大
            max_skill = max(skills, key=lambda s: s.composite_score)
            min_skill = min(skills, key=lambda s: s.composite_score)

            insight = CrossSkillInsight(
                insight_id=self._generate_id(),
                type="comparison",
                severity="medium",
                title="技能发展不均衡",
                content=f"技能间发展差异较大（方差 {variance:.1f}），最强技能 {max_skill.name} 和最弱技能 {min_skill.name} 差距明显。建议均衡分配练习时间，避免出现短板效应。",
                affected_skills=[s.skill_id for s in skills],
                data_evidence={"variance": variance, "gap": max_skill.composite_score - min_skill.composite_score},
            )
            insights.append(insight)

        return insights

    def compare_skills(self, skill_ids: List[str]) -> str:
        """
        生成技能对比报告

        Args:
            skill_ids: 要对比的技能 ID 列表

        Returns:
            格式化的对比报告
        """
        skills = [self.graph.get_skill(sid) for sid in skill_ids]
        skills = [s for s in skills if s is not None]

        lines = []
        lines.append("📊 技能对比分析")
        lines.append("═" * 60)
        lines.append("")

        if not skills:
            lines.append("   未找到指定的技能")
            return "\n".join(lines)

        if len(skills) < 2:
            lines.append("   至少需要 2 个技能才能进行对比")
            return "\n".join(lines)

        # 维度对比（雷达图文字版）
        dimensions = ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]
        dim_names = {
            "proficiency": "熟练度",
            "stability": "稳定性",
            "satisfaction": "满意度",
            "responsiveness": "响应力",
            "memory": "记忆力",
        }

        lines.append("🔍 五维能力对比:")
        lines.append("")

        for dim in dimensions:
            dim_name = dim_names.get(dim, dim)
            scores = [(s, s.dimension_scores.get(dim, 0)) for s in skills]
            scores.sort(key=lambda x: x[1], reverse=True)

            best_skill, best_score = scores[0]
            worst_skill, worst_score = scores[-1]

            bar_max = 20
            lines.append(f"   {dim_name:6}:")
            for skill, score in scores:
                bar_len = int(score / 100 * bar_max)
                bar = "█" * bar_len + "░" * (bar_max - bar_len)
                marker = "🏆" if score == best_score and len(scores) > 1 else ""
                lines.append(f"      {skill.name[:12]:12} |{bar}| {score:3.0f} {marker}")
            lines.append("")

        # 综合对比
        lines.append("📈 综合对比:")
        lines.append("")
        for skill in sorted(skills, key=lambda s: s.composite_score, reverse=True):
            level_icon = {
                "NOVICE": "🌱",
                "APPRENTICE": "🌿",
                "ADEPT": "🌳",
                "EXPERT": "🌲",
                "MASTER": "🏆",
            }.get(skill.level, "❓")

            lines.append(f"   {level_icon} {skill.name}")
            lines.append(f"      境界: {skill.level} | 综合分: {skill.composite_score:.0f}")
            lines.append(f"      交互数: {skill.interaction_count} 次 | 分类: {skill.category}")
        lines.append("")

        # 关系分析
        if len(skills) == 2:
            s1, s2 = skills
            related = self.graph.get_related_skills(s1.skill_id)
            relation = next((r for sk, r in related if sk.skill_id == s2.skill_id), None)

            if relation:
                type_names = {
                    "prerequisite": "前置依赖关系",
                    "complementary": "互补关系",
                    "competing": "竞争关系",
                    "transfer": "知识迁移关系",
                    "co_occurrence": "共同使用关系",
                }
                rel_name = type_names.get(relation.relation_type, "关联关系")
                lines.append(f"🔗 关系分析: {rel_name}（强度 {relation.strength:.0%}）")
                if relation.evidence:
                    lines.append(f"   证据: {relation.evidence[0]}")

        return "\n".join(lines)
