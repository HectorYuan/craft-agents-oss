"""
ZenSkill - 技能生态系统仪表盘

统一的多技能管理和监控界面，可视化整个技能生态系统的状态：
- 技能生态总览
- 成长热力图（各维度、各技能的成长速度）
- 关系网络图（ASCII 可视化）
- 知识流动追踪
- 协同效应评估
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
from zenskill.systems.collaboration.cross_insight import CrossSkillInsightEngine


class SkillEcosystemDashboard:
    """
    技能生态系统仪表盘

    提供整个技能生态系统的统一视图：
    - 生态健康度评估
    - 成长热力图
    - 知识流动追踪
    - 协同效应量化
    """

    def __init__(self):
        self.graph = SkillDependencyGraph()
        self.cross_insight = CrossSkillInsightEngine()

    def generate_dashboard(self) -> str:
        """
        生成完整的仪表盘报告

        Returns:
            格式化的仪表盘字符串
        """
        lines = []
        lines.append("🌐 技能生态系统仪表盘")
        lines.append("═" * 60)
        lines.append("")

        skills = self.graph.get_all_skills()

        if not skills:
            lines.append("   暂无注册的技能")
            lines.append("")
            lines.append("💡 使用 'zenskill graph register <skill_id>' 注册技能")
            return "\n".join(lines)

        # 1. 生态健康度总览
        health = self._calculate_ecosystem_health()
        lines.append("🏥 生态系统健康度")
        health_icon = {
            "excellent": "🟢",
            "good": "🟡",
            "fair": "🟠",
            "poor": "🔴",
        }.get(health["level"], "⚪")

        lines.append(f"   {health_icon} 整体健康度: {health['overall_score']:.1f} / 100")
        lines.append(f"   📈 成长均衡度: {health['balance_score']:.1f} / 100")
        lines.append(f"   🔗 连接密度: {health['connectivity_score']:.1f} / 100")
        lines.append(f"   📊 活跃度评分: {health['activity_score']:.1f} / 100")
        lines.append("")

        # 2. 成长热力图
        heatmap = self._generate_growth_heatmap(skills)
        lines.append("🔥 成长热力图（最近 7 天）")
        lines.append("")
        for line in heatmap:
            lines.append(f"   {line}")
        lines.append("")

        # 3. 技能网络 ASCII 图
        network_vis = self._generate_network_visualization(skills)
        lines.append("🕸️ 技能关系网络")
        lines.append("")
        for line in network_vis:
            lines.append(f"   {line}")
        lines.append("")

        # 4. 协同效应评估
        synergy = self._calculate_synergy_score(skills)
        lines.append("🤝 协同效应评估")
        synergy_icon = "🟢" if synergy > 70 else "🟡" if synergy > 40 else "🔴"
        lines.append(f"   {synergy_icon} 协同效应评分: {synergy:.1f} / 100")

        if synergy > 60:
            lines.append("   ✅ 技能之间协同良好，知识正在有效迁移")
        elif synergy > 30:
            lines.append("   ℹ️ 有一定协同效应，技能间关系还有加强空间")
        else:
            lines.append("   💡 协同效应较弱，建议加强相关技能的同步训练")
        lines.append("")

        # 5. 快速洞察
        insights = self.cross_insight.generate_cross_insights()
        if insights:
            lines.append("💡 快速洞察")
            lines.append("")
            for insight in insights[:2]:
                icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(insight.severity, "⚪")
                lines.append(f"   {icon} {insight.title}")
                lines.append(f"      {insight.content[:60]}...")
            lines.append("")

        lines.append("=" * 60)
        lines.append("💡 子命令: heatmap | network | synergy | health")

        return "\n".join(lines)

    def _calculate_ecosystem_health(self) -> Dict[str, Any]:
        """计算生态系统健康度"""
        skills = self.graph.get_all_skills()

        if not skills:
            return {
                "level": "unknown",
                "overall_score": 0,
                "balance_score": 0,
                "connectivity_score": 0,
                "activity_score": 0,
            }

        # 1. 均衡度评分（基于境界分布和分数方差）
        scores = [s.composite_score for s in skills]
        avg_score = sum(scores) / len(scores) if scores else 0
        variance = sum((s - avg_score) ** 2 for s in scores) / len(scores) if scores else 0
        balance_score = max(0, 100 - variance / 10)

        # 2. 连接度评分（基于关系边数）
        relation_count = len(self.graph.relations)
        max_possible = len(skills) * (len(skills) - 1) / 2 if len(skills) > 1 else 1
        connectivity_score = min(100, relation_count / max_possible * 100) if max_possible > 0 else 0

        # 3. 活跃度评分（基于总交互次数）
        total_interactions = sum(s.interaction_count for s in skills)
        activity_score = min(100, total_interactions / 10)

        # 4. 综合评分
        overall_score = (balance_score + connectivity_score + activity_score) / 3

        # 评级
        if overall_score >= 80:
            level = "excellent"
        elif overall_score >= 60:
            level = "good"
        elif overall_score >= 40:
            level = "fair"
        else:
            level = "poor"

        return {
            "level": level,
            "overall_score": overall_score,
            "balance_score": balance_score,
            "connectivity_score": connectivity_score,
            "activity_score": activity_score,
        }

    def _generate_growth_heatmap(self, skills: List[SkillNode]) -> List[str]:
        """生成成长热力图（文本版）"""
        lines = []
        dimensions = ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]
        dim_short_names = {
            "proficiency": "熟练度",
            "stability": "稳定性",
            "satisfaction": "满意度",
            "responsiveness": "响应力",
            "memory": "记忆力",
        }

        heat_icons = ["░", "▒", "▓", "█"]  # 从冷到热

        # 表头
        header = "技能\\维度"
        for dim in dimensions:
            header += f" {dim_short_names.get(dim, dim[:2])}"
        lines.append(header)
        lines.append("─" * 35)

        # 每技能一行
        for skill in skills[:5]:  # 最多显示 5 个技能
            row = f"{skill.name[:8]:8}"
            for dim in dimensions:
                score = skill.dimension_scores.get(dim, 0)
                heat_level = min(3, int(score / 25))
                row += f"  {heat_icons[heat_level]} "
            row += f" ({skill.level[:3]})"
            lines.append(row)

        if len(skills) > 5:
            lines.append(f"   ... 还有 {len(skills) - 5} 个技能未显示")

        lines.append("")
        lines.append("   热力: ░ 冷(<25) | ▒ 温(25-50) | ▓ 热(50-75) | █ 极热(>75)")

        return lines

    def _generate_network_visualization(self, skills: List[SkillNode]) -> List[str]:
        """生成 ASCII 网络关系图"""
        lines = []

        if len(skills) < 2:
            lines.append("需要至少 2 个技能才能显示网络关系图")
            return lines

        # 简化的星型网络（以使用最多的技能为中心）
        central_skill = max(skills, key=lambda s: s.interaction_count)
        others = [s for s in skills if s.skill_id != central_skill.skill_id][:4]

        # 第一层：中心节点
        central_icon = {"NOVICE": "🌱", "APPRENTICE": "🌿", "ADEPT": "🌳", "EXPERT": "🌲", "MASTER": "🏆"}.get(central_skill.level, "❓")
        lines.append(f"           {central_icon} {central_skill.name[:10]}")
        lines.append("           │")

        # 第二层：连接
        connections = "           "
        for i, other in enumerate(others):
            # 查找关系强度
            related = self.graph.get_related_skills(central_skill.skill_id)
            strength = 0.5
            for sk, rel in related:
                if sk.skill_id == other.skill_id:
                    strength = rel.strength
                    break

            conn_icon = "═══" if strength > 0.7 else "───" if strength > 0.3 else "┈┈┈"
            if i < len(others) - 1:
                connections += f"├{conn_icon}"
            else:
                connections += f"└{conn_icon}"

        lines.append(connections.rstrip("─"))

        # 第三层：外围节点
        node_line = " " * 11
        for other in others:
            icon = {"NOVICE": "🌱", "APPRENTICE": "🌿", "ADEPT": "🌳", "EXPERT": "🌲", "MASTER": "🏆"}.get(other.level, "❓")
            node_line += f" {icon}{other.name[:7]:7}"
        lines.append(node_line)

        lines.append("")
        lines.append("   连线: ═══ 强关联 | ─── 中关联 | ┈┈┈ 弱关联")

        return lines

    def _calculate_synergy_score(self, skills: List[SkillNode]) -> float:
        """计算协同效应评分"""
        if len(skills) < 2:
            return 0.0

        # 1. 基于关系强度
        relation_strengths = [r.strength for r in self.graph.relations]
        avg_relation = sum(relation_strengths) / len(relation_strengths) if relation_strengths else 0
        relation_score = avg_relation * 50  # 占 50%

        # 2. 基于能力均衡（方差越小，协同潜力越大）
        scores = [s.composite_score for s in skills]
        avg_score = sum(scores) / len(scores) if scores else 0
        variance = sum((s - avg_score) ** 2 for s in scores) / len(scores) if scores else 0
        balance_score = max(0, 30 - variance / 50)  # 占 30%

        # 3. 基于境界提升
        high_level_count = sum(1 for s in skills if s.level in ["ADEPT", "EXPERT", "MASTER"])
        high_level_score = min(20, high_level_count * 10)  # 占 20%

        return relation_score + balance_score + high_level_score

    def generate_heatmap_report(self) -> str:
        """生成详细的热力图报告"""
        skills = self.graph.get_all_skills()

        lines = []
        lines.append("🔥 技能成长热力图 - 详细报告")
        lines.append("═" * 60)
        lines.append("")

        if not skills:
            lines.append("   暂无数据")
            return "\n".join(lines)

        dimensions = ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]
        dim_names = {
            "proficiency": "熟练度",
            "stability": "稳定性",
            "satisfaction": "满意度",
            "responsiveness": "响应力",
            "memory": "记忆力",
        }

        # 维度热力排名
        lines.append("📊 维度热力排名")
        lines.append("")

        for dim in dimensions:
            scores = [s.dimension_scores.get(dim, 0) for s in skills]
            avg_score = sum(scores) / len(scores) if scores else 0

            heat_icon = "🔥" if avg_score >= 75 else "🌡️" if avg_score >= 50 else "🧊"
            status = "热门" if avg_score >= 75 else "适中" if avg_score >= 50 else "冷门"

            lines.append(f"   {heat_icon} {dim_names.get(dim, dim):6}: {avg_score:5.1f} 分 ({status})")

            # 列出该维度表现最好和最差的技能
            sorted_by_dim = sorted(skills, key=lambda s: s.dimension_scores.get(dim, 0), reverse=True)
            if sorted_by_dim and sorted_by_dim[0].dimension_scores.get(dim, 0) > 0:
                lines.append(f"      最好: {sorted_by_dim[0].name} ({sorted_by_dim[0].dimension_scores.get(dim, 0):.0f} 分)")
            if len(sorted_by_dim) > 1 and sorted_by_dim[-1].dimension_scores.get(dim, 0) < 50:
                lines.append(f"      需提升: {sorted_by_dim[-1].name} ({sorted_by_dim[-1].dimension_scores.get(dim, 0):.0f} 分)")
            lines.append("")

        # 技能总排名
        lines.append("🏆 技能综合热力排名")
        lines.append("")

        sorted_skills = sorted(skills, key=lambda s: s.composite_score, reverse=True)
        for i, skill in enumerate(sorted_skills, 1):
            heat_icon = "🔥" if skill.composite_score >= 75 else "🌡️" if skill.composite_score >= 50 else "🧊"
            level_icon = {"NOVICE": "🌱", "APPRENTICE": "🌿", "ADEPT": "🌳", "EXPERT": "🌲", "MASTER": "🏆"}.get(skill.level, "❓")
            lines.append(f"   {i}. {heat_icon} {level_icon} {skill.name:15} {skill.composite_score:5.1f} 分")

        return "\n".join(lines)
