"""
ZenSkill - 技能依赖图谱系统

自动发现和建模技能之间的依赖、促进、互补、竞争关系，形成技能知识网络：
- 共现分析：哪些技能经常一起被使用
- 迁移效应：学会 A 后 B 的学习速度变化
- 内容相似性：技能描述和记忆的语义相似度
- 性能相关性：A 技能提升与 B 技能提升的相关性

这是整个多技能协同系统的基础设施。
"""

from __future__ import annotations

import json
import time
import math
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Tuple, Set
from collections import defaultdict

from zenskill.core.paths import get_user_data_dir
from zenskill.systems.visualization.metrics_store import MetricsStore


@dataclass
class SkillCategory:
    """技能分类"""
    category_id: str
    name: str
    description: str
    parent_category: Optional[str] = None
    sub_categories: List[str] = None

    def __post_init__(self):
        if self.sub_categories is None:
            self.sub_categories = []


@dataclass
class SkillNode:
    """技能节点 - 图谱中的一个技能实体"""
    skill_id: str
    name: str
    description: str = ""
    level: str = "NOVICE"  # NOVICE / APPRENTICE / ADEPT / EXPERT / MASTER
    category: str = "general"
    tags: List[str] = None
    composite_score: float = 0.0
    dimension_scores: Dict[str, float] = None
    interaction_count: int = 0
    first_used_at: Optional[str] = None
    last_used_at: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.dimension_scores is None:
            self.dimension_scores = {}
        if self.metadata is None:
            self.metadata = {}


@dataclass
class SkillRelation:
    """技能关系边 - 两个技能之间的连接"""
    relation_id: str
    from_skill: str
    to_skill: str
    relation_type: str  # prerequisite / complementary / competing / transfer / co_occurrence
    strength: float  # 关系强度 0-1，越接近 1 越强
    confidence: float  # 发现置信度 0-1
    evidence: List[str] = None  # 支持证据列表
    discovered_at: str = None
    last_updated_at: str = None

    def __post_init__(self):
        if self.evidence is None:
            self.evidence = []
        if self.discovered_at is None:
            self.discovered_at = datetime.now().isoformat()
        if self.last_updated_at is None:
            self.last_updated_at = datetime.now().isoformat()


class SkillDependencyGraph:
    """
    技能依赖图谱

    自动发现技能之间的关系，构建和维护技能知识网络：
    - 共现关系：哪些技能经常一起使用
    - 迁移关系：学会一个技能是否帮助学习另一个
    - 依赖关系：掌握某个技能是另一个的前提
    - 互补关系：技能组合使用效果更好
    - 竞争关系：技能功能重叠，使用一个会减少使用另一个
    """

    # 内置技能分类体系
    DEFAULT_CATEGORIES = [
        SkillCategory("coding", "编程开发", "与代码相关的技能"),
        SkillCategory("writing", "内容创作", "文档、博客、创意写作"),
        SkillCategory("analysis", "数据分析", "数据处理、分析、可视化"),
        SkillCategory("learning", "学习辅助", "学习新技能、知识管理"),
        SkillCategory("productivity", "效率工具", "日常工作效率提升"),
        SkillCategory("communication", "沟通协作", "会议、邮件、团队协作"),
        SkillCategory("general", "通用技能", "其他通用能力"),
    ]

    def __init__(self):
        self.nodes: Dict[str, SkillNode] = {}
        self.relations: List[SkillRelation] = []
        self.categories: Dict[str, SkillCategory] = {}
        self.graph_dir = self._get_graph_dir()
        self.nodes_file = self.graph_dir / "skill_nodes.jsonl"
        self.relations_file = self.graph_dir / "skill_relations.jsonl"

        # 初始化默认分类
        for cat in self.DEFAULT_CATEGORIES:
            self.categories[cat.category_id] = cat

        # 加载已有数据
        self._load_graph()

    def _get_graph_dir(self) -> Path:
        """获取图谱数据目录"""
        user_dir = get_user_data_dir()
        graph_dir = user_dir / "graph"
        graph_dir.mkdir(parents=True, exist_ok=True)
        return graph_dir

    def _generate_id(self, prefix: str = "rel") -> str:
        """生成唯一 ID"""
        timestamp = int(time.time() * 1000)
        return f"{prefix}_{timestamp}"

    def _load_graph(self) -> None:
        """从文件加载图谱数据"""
        # 加载技能节点
        if self.nodes_file.exists():
            with open(self.nodes_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            node = SkillNode(**data)
                            self.nodes[node.skill_id] = node
                        except (json.JSONDecodeError, ValueError, TypeError):
                            continue

        # 加载关系边
        if self.relations_file.exists():
            with open(self.relations_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            relation = SkillRelation(**data)
                            self.relations.append(relation)
                        except (json.JSONDecodeError, ValueError, TypeError):
                            continue

    def _save_node(self, node: SkillNode) -> None:
        """保存技能节点到文件"""
        # 先读取所有节点，然后写入更新
        nodes = []
        if self.nodes_file.exists():
            with open(self.nodes_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            if data.get("skill_id") != node.skill_id:
                                nodes.append(line)
                        except json.JSONDecodeError:
                            nodes.append(line)

        # 添加更新后的节点
        nodes.append(json.dumps(asdict(node), ensure_ascii=False))

        # 写回文件
        with open(self.nodes_file, "w", encoding="utf-8") as f:
            f.write("\n".join(nodes) + "\n")

    def _save_relation(self, relation: SkillRelation) -> None:
        """保存关系到文件"""
        # 先检查是否已存在相同的关系
        relations = []
        exists = False
        if self.relations_file.exists():
            with open(self.relations_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            if (data.get("from_skill") == relation.from_skill and
                                data.get("to_skill") == relation.to_skill and
                                data.get("relation_type") == relation.relation_type):
                                exists = True
                                relations.append(json.dumps(asdict(relation), ensure_ascii=False))
                            else:
                                relations.append(line)
                        except json.JSONDecodeError:
                            relations.append(line)

        if not exists:
            relations.append(json.dumps(asdict(relation), ensure_ascii=False))

        # 写回文件
        with open(self.relations_file, "w", encoding="utf-8") as f:
            f.write("\n".join(relations) + "\n")

    def register_skill(self, skill_id: str, name: Optional[str] = None, category: str = "general") -> SkillNode:
        """
        注册或更新一个技能到图谱中

        Args:
            skill_id: 技能唯一标识
            name: 技能显示名称
            category: 技能分类

        Returns:
            技能节点
        """
        if name is None:
            name = skill_id.replace("-", " ").replace("_", " ").title()

        # 尝试从现有数据获取技能状态
        metrics_store = MetricsStore(skill_id)
        snapshots = metrics_store.get_all_snapshots()

        level = "NOVICE"
        composite_score = 0.0
        dimension_scores = {}
        interaction_count = 0
        first_used = None
        last_used = None

        if snapshots:
            latest = snapshots[-1]
            level = latest.level
            # 从 ability_scores 中获取 composite，或计算平均值
            composite_score = latest.ability_scores.get("composite", 0)
            dimension_scores = latest.ability_scores.copy()
            interaction_count = latest.interaction_count
            first_used = snapshots[0].timestamp
            last_used = latest.timestamp

        node = SkillNode(
            skill_id=skill_id,
            name=name,
            level=level,
            category=category,
            composite_score=composite_score,
            dimension_scores=dimension_scores,
            interaction_count=interaction_count,
            first_used_at=first_used,
            last_used_at=last_used,
        )

        self.nodes[skill_id] = node
        self._save_node(node)
        return node

    def get_all_skills(self) -> List[SkillNode]:
        """获取所有已注册的技能"""
        return list(self.nodes.values())

    def get_skill(self, skill_id: str) -> Optional[SkillNode]:
        """获取特定技能节点"""
        return self.nodes.get(skill_id)

    def discover_relations(self) -> List[SkillRelation]:
        """
        自动发现技能之间的关系

        基于以下信号发现关系：
        1. 使用时间重叠（共现）
        2. 能力维度相似度
        3. 成长模式相似性
        4. 标签和分类相似度

        Returns:
            新发现的关系列表
        """
        skills = list(self.nodes.values())
        new_relations = []

        if len(skills) < 2:
            return new_relations

        # 对每对技能计算关系
        for i, skill_a in enumerate(skills):
            for skill_b in skills[i + 1:]:
                relation = self._calculate_skill_relation(skill_a, skill_b)
                if relation and relation.strength > 0.3:  # 强度阈值
                    self.relations.append(relation)
                    self._save_relation(relation)
                    new_relations.append(relation)

        return new_relations

    def _calculate_skill_relation(self, skill_a: SkillNode, skill_b: SkillNode) -> Optional[SkillRelation]:
        """计算两个技能之间的关系"""
        strength_scores = []
        evidence = []

        # 1. 分类相似度（同一分类的技能关系更强）
        if skill_a.category == skill_b.category:
            strength_scores.append(0.5)
            evidence.append(f"属于同一分类: {skill_a.category}")
        else:
            strength_scores.append(0.1)

        # 2. 能力维度相似度（向量余弦相似度）
        dim_similarity = self._calculate_dimension_similarity(
            skill_a.dimension_scores,
            skill_b.dimension_scores
        )
        strength_scores.append(dim_similarity * 0.8)
        if dim_similarity > 0.5:
            evidence.append(f"能力维度相似度: {dim_similarity:.2f}")

        # 3. 使用模式相似度（境界和交互数）
        levels = ["NOVICE", "APPRENTICE", "ADEPT", "EXPERT", "MASTER"]
        a_level_idx = levels.index(skill_a.level) if skill_a.level in levels else 0
        b_level_idx = levels.index(skill_b.level) if skill_b.level in levels else 0
        level_diff = abs(a_level_idx - b_level_idx)
        level_similarity = 1.0 - (level_diff / len(levels))
        strength_scores.append(level_similarity * 0.3)
        if level_similarity > 0.8:
            evidence.append(f"境界相近: {skill_a.level} vs {skill_b.level}")

        # 4. 标签重叠度
        tags_a = set(skill_a.tags)
        tags_b = set(skill_b.tags)
        if tags_a and tags_b:
            overlap = len(tags_a & tags_b) / len(tags_a | tags_b)
            strength_scores.append(overlap * 0.6)
            if overlap > 0.3:
                evidence.append(f"标签重叠度: {overlap:.2f}")

        # 计算综合强度
        avg_strength = sum(strength_scores) / len(strength_scores) if strength_scores else 0

        # 确定关系类型
        relation_type = self._determine_relation_type(skill_a, skill_b, avg_strength, evidence)

        # 置信度基于证据数量
        confidence = min(1.0, len(evidence) * 0.25 + 0.25)

        if avg_strength < 0.2:
            return None

        return SkillRelation(
            relation_id=self._generate_id("rel"),
            from_skill=skill_a.skill_id,
            to_skill=skill_b.skill_id,
            relation_type=relation_type,
            strength=round(avg_strength, 3),
            confidence=round(confidence, 3),
            evidence=evidence,
        )

    def _calculate_dimension_similarity(self, scores_a: Dict[str, float], scores_b: Dict[str, float]) -> float:
        """计算能力维度的余弦相似度"""
        dimensions = ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]

        vec_a = []
        vec_b = []
        for dim in dimensions:
            vec_a.append(scores_a.get(dim, 0))
            vec_b.append(scores_b.get(dim, 0))

        # 计算余弦相似度
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    def _determine_relation_type(self, skill_a: SkillNode, skill_b: SkillNode, strength: float, evidence: List[str]) -> str:
        """根据技能特征和证据确定关系类型"""
        # 根据能力分布判断关系类型
        a_scores = skill_a.dimension_scores
        b_scores = skill_b.dimension_scores

        # 如果两个技能在不同维度各有所长 → 互补关系
        a_strengths = sorted([(dim, score) for dim, score in a_scores.items()], key=lambda x: -x[1])[:2]
        b_strengths = sorted([(dim, score) for dim, score in b_scores.items()], key=lambda x: -x[1])[:2]

        a_top_dims = {dim for dim, _ in a_strengths}
        b_top_dims = {dim for dim, _ in b_strengths}

        if a_top_dims.isdisjoint(b_top_dims) and strength > 0.4:
            return "complementary"

        # 如果分类相同且能力分布相似 → 共现关系
        if skill_a.category == skill_b.category and strength > 0.5:
            return "co_occurrence"

        # 默认：迁移关系（所有技能都可以有知识迁移）
        return "transfer"

    def get_related_skills(self, skill_id: str, relation_type: Optional[str] = None) -> List[Tuple[SkillNode, SkillRelation]]:
        """
        获取与指定技能相关的所有技能

        Args:
            skill_id: 目标技能 ID
            relation_type: 可选的关系类型过滤

        Returns:
            (技能节点, 关系) 的元组列表
        """
        related = []
        for relation in self.relations:
            if relation.from_skill == skill_id or relation.to_skill == skill_id:
                if relation_type and relation.relation_type != relation_type:
                    continue
                other_id = relation.to_skill if relation.from_skill == skill_id else relation.from_skill
                other_node = self.nodes.get(other_id)
                if other_node:
                    related.append((other_node, relation))

        # 按强度排序
        related.sort(key=lambda x: x[1].strength, reverse=True)
        return related

    def recommend_learning_path(self, target_skill_id: str, max_depth: int = 3) -> List[Dict[str, Any]]:
        """
        推荐学习路径（前置技能推荐）

        Args:
            target_skill_id: 想要学习的目标技能
            max_depth: 最大路径深度

        Returns:
            学习路径列表，每个元素包含技能和推荐理由
        """
        if target_skill_id not in self.nodes:
            return []

        path = []
        visited = set()
        current = target_skill_id

        # 基于关系强度的 BFS 推荐
        queue = [(current, 0)]
        while queue and len(path) < max_depth:
            skill_id, depth = queue.pop(0)
            if skill_id in visited:
                continue
            visited.add(skill_id)

            related = self.get_related_skills(skill_id, "prerequisite")
            if not related:
                related = self.get_related_skills(skill_id, "transfer")[:2]

            for related_skill, relation in related:
                if related_skill.skill_id not in visited and related_skill.level == "NOVICE":
                    path.append({
                        "skill": related_skill,
                        "relation": relation,
                        "recommended_before": target_skill_id,
                        "reason": self._get_recommendation_reason(related_skill, relation, target_skill_id),
                    })
                    queue.append((related_skill.skill_id, depth + 1))

        return path

    def _get_recommendation_reason(self, skill: SkillNode, relation: SkillRelation, target: str) -> str:
        """生成推荐理由的自然语言描述"""
        if relation.relation_type == "prerequisite":
            return f"学习 {target} 之前建议先掌握 {skill.name}，关系强度 {relation.strength:.1%}"
        elif relation.relation_type == "complementary":
            return f"{skill.name} 与 {target} 互补，同时学习可以产生协同效应"
        elif relation.relation_type == "transfer":
            return f"{skill.name} 学到的经验可以迁移到 {target}，加速学习"
        else:
            return f"{skill.name} 与 {target} 相关，推荐学习"

    def visualize_ascii_graph(self) -> str:
        """
        生成 ASCII 格式的技能图谱可视化

        Returns:
            ASCII 图谱字符串
        """
        lines = []
        lines.append("🌐 技能依赖图谱")
        lines.append("═" * 60)
        lines.append("")

        if not self.nodes:
            lines.append("   暂无注册的技能，请先使用 'zenskill graph register <skill_id>' 注册")
            return "\n".join(lines)

        # 按分类分组显示
        by_category: Dict[str, List[SkillNode]] = defaultdict(list)
        for node in self.nodes.values():
            by_category[node.category].append(node)

        for category, skills in by_category.items():
            cat_name = self.categories.get(category, SkillCategory(category, category, "")).name
            lines.append(f"📂 {cat_name.upper()}")
            lines.append("")

            for skill in skills:
                level_icon = {
                    "NOVICE": "🌱",
                    "APPRENTICE": "🌿",
                    "ADEPT": "🌳",
                    "EXPERT": "🌲",
                    "MASTER": "🏆",
                }.get(skill.level, "❓")

                related = self.get_related_skills(skill.skill_id)
                related_str = f", 连接 {len(related)} 个技能" if related else ""

                lines.append(f"   {level_icon} {skill.name} [{skill.level}]")
                lines.append(f"      综合分: {skill.composite_score:.0f} | 交互: {skill.interaction_count} 次{related_str}")

                # 显示最强的 2 个连接
                for related_skill, relation in related[:2]:
                    rel_icon = {
                        "prerequisite": "⬇️",
                        "complementary": "🔗",
                        "competing": "⚔️",
                        "transfer": "↔️",
                        "co_occurrence": "📊",
                    }.get(relation.relation_type, "•")
                    lines.append(f"      {rel_icon} {related_skill.name} ({relation.relation_type}, 强度 {relation.strength:.0%})")

                lines.append("")

        # 统计信息
        total_relations = len(self.relations)
        avg_degree = (total_relations * 2) / len(self.nodes) if self.nodes else 0

        lines.append("📊 图谱统计")
        lines.append(f"   技能节点: {len(self.nodes)} 个")
        lines.append(f"   关系边: {total_relations} 条")
        lines.append(f"   平均连接度: {avg_degree:.1f}")
        lines.append(f"   分类数: {len(by_category)} 个")

        return "\n".join(lines)

    def get_graph_overview(self) -> Dict[str, Any]:
        """获取图谱概览统计"""
        skill_count = len(self.nodes)
        relation_count = len(self.relations)

        by_category: Dict[str, int] = defaultdict(int)
        for node in self.nodes.values():
            by_category[node.category] += 1

        by_type: Dict[str, int] = defaultdict(int)
        for rel in self.relations:
            by_type[rel.relation_type] += 1

        return {
            "skill_count": skill_count,
            "relation_count": relation_count,
            "average_degree": (relation_count * 2) / skill_count if skill_count > 0 else 0,
            "by_category": dict(by_category),
            "by_relation_type": dict(by_type),
        }

    # ---- 8D: 图谱实时更新 ----

    def auto_discover_if_stale(self, max_hours: int = 6) -> list[SkillRelation]:
        """自动发现（如果距离上次发现超过 max_hours 小时）(8D)"""
        from pathlib import Path
        marker = Path.home() / ".zenskill" / "graph" / ".last_auto_discover"
        now = __import__("time").time()
        if marker.exists():
            try:
                last = float(marker.read_text().strip())
                if now - last < max_hours * 3600:
                    return []
            except (ValueError, OSError):
                pass
        new_rels = self.discover_relations()
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(now))
        return new_rels

    # ---- 8P: 知识图谱查询 ----

    def query(self, keyword: str = "", category: str = "", limit: int = 20) -> list[dict]:
        """查询知识图谱 (8P)"""
        results = []
        for node in self.nodes.values():
            if keyword and keyword.lower() not in node.skill_id.lower():
                continue
            if category and node.category != category:
                continue
            related = [r.target_id for r in self.relations if r.source_id == node.skill_id]
            related += [r.source_id for r in self.relations if r.target_id == node.skill_id]
            results.append({
                "skill_id": node.skill_id,
                "category": node.category,
                "proficiency": getattr(node, "proficiency", 0),
                "usage_count": getattr(node, "usage_count", 0),
                "relations": len(set(related)),
                "connected_to": list(set(related))[:5],
            })
        return sorted(results, key=lambda x: x["relations"], reverse=True)[:limit]

    # ---- 8Q: 技能组合推荐 ----

    def recommend_combinations(self, skill_id: str = "", top_n: int = 5) -> list[dict]:
        """推荐技能组合 (8Q)"""
        pairs = []
        for rel in self.relations:
            if rel.relation_type in ("complementary", "transfer"):
                score = rel.strength * 100
                pairs.append({
                    "source": rel.source_id,
                    "target": rel.target_id,
                    "type": rel.relation_type,
                    "strength": round(rel.strength, 2),
                    "synergy_score": round(score, 1),
                })
        if skill_id:
            pairs = [p for p in pairs if p["source"] == skill_id or p["target"] == skill_id]
        return sorted(pairs, key=lambda x: x["synergy_score"], reverse=True)[:top_n]

    # ---- 8J: 生态健康预警 ----

    def health_alerts(self) -> list[dict]:
        """生态健康预警 (8J)"""
        alerts = []
        overview = self.get_graph_overview()
        if overview["skill_count"] < 2:
            return alerts
        if overview["average_degree"] < 1.0:
            alerts.append({"level": "warning", "message": f"图谱平均连接度低 ({overview['average_degree']:.1f})，技能之间缺少关联"})
        isolated = [n.skill_id for n in self.nodes.values() if not any(
            r.source_id == n.skill_id or r.target_id == n.skill_id for r in self.relations
        )]
        if isolated:
            alerts.append({"level": "info", "message": f"孤立技能: {', '.join(isolated[:5])}，建议运行 graph discover"})
        categories = overview.get("by_category", {})
        if len(categories) <= 1:
            alerts.append({"level": "info", "message": "技能类别单一，建议拓展新领域"})
        return alerts

    # ---- 8O: 跨技能冲突检测 ----

    def detect_conflicts(self) -> list[dict]:
        """跨技能冲突检测 (8O)"""
        conflicts = []
        for rel in self.relations:
            if rel.relation_type == "competitive":
                conflicts.append({
                    "skill_a": rel.source_id, "skill_b": rel.target_id,
                    "severity": round(rel.strength * 100, 1),
                    "suggestion": "这两个技能使用模式存在竞争，考虑分时专注练习",
                })
        return sorted(conflicts, key=lambda x: x["severity"], reverse=True)

    # ---- 8N: 技能网络动力学 ----

    def network_dynamics(self) -> dict:
        """技能网络动力学分析 (8N)"""
        nodes = list(self.nodes.values())
        n = len(nodes)
        if n == 0:
            return {"node_count": 0, "edge_count": 0}
        # 度中心性
        degree: dict[str, int] = {}
        for node in nodes:
            degree[node.skill_id] = sum(
                1 for r in self.relations
                if r.source_id == node.skill_id or r.target_id == node.skill_id
            )
        # 聚类系数
        clustering: dict[str, float] = {}
        for node in nodes:
            neighbors = set()
            for r in self.relations:
                if r.source_id == node.skill_id:
                    neighbors.add(r.target_id)
                elif r.target_id == node.skill_id:
                    neighbors.add(r.source_id)
            if len(neighbors) < 2:
                clustering[node.skill_id] = 0.0
                continue
            edges_between = sum(
                1 for r in self.relations
                if r.source_id in neighbors and r.target_id in neighbors
            )
            possible = len(neighbors) * (len(neighbors) - 1)
            clustering[node.skill_id] = edges_between / possible if possible > 0 else 0.0
        # Top 中心节点
        top_central = sorted(degree.items(), key=lambda x: x[1], reverse=True)[:5]
        top_clustered = sorted(clustering.items(), key=lambda x: x[1], reverse=True)[:5]
        return {
            "node_count": n,
            "edge_count": len(self.relations),
            "density": len(self.relations) / (n * (n - 1)) if n > 1 else 0,
            "top_by_degree": [{"skill": k, "degree": v} for k, v in top_central],
            "top_by_clustering": [{"skill": k, "clustering": round(v, 3)} for k, v in top_clustered],
        }

    # ---- 8M: 技能生命周期 ----

    def lifecycle_analysis(self) -> list[dict]:
        """技能生命周期分析 (8M): creation→growth→maturity→decline"""
        results = []
        for node in self.nodes.values():
            uc = getattr(node, "usage_count", 0)
            prof = getattr(node, "proficiency", 0)
            if uc == 0: stage = "dormant"
            elif prof < 20: stage = "creation"
            elif prof < 50: stage = "growth"
            elif uc > 200: stage = "maturity"
            else: stage = "growth"
            results.append({
                "skill_id": node.skill_id,
                "stage": stage,
                "usage_count": uc,
                "proficiency": prof,
                "category": node.category,
            })
        return results

    # ---- 8E: 跨技能迁移学习 ----

    def detect_transfer_patterns(self) -> list[dict]:
        """跨技能迁移学习检测 (8E): 哪些技能之间存在可迁移模式"""
        patterns = []
        for rel in self.relations:
            if rel.relation_type in ("transfer", "complementary"):
                patterns.append({
                    "from_skill": rel.source_id,
                    "to_skill": rel.target_id,
                    "type": rel.relation_type,
                    "transfer_strength": round(rel.strength, 3),
                    "suggestion": f"将在 {rel.source_id} 中学到的模式应用到 {rel.target_id}",
                })
        return sorted(patterns, key=lambda x: x["transfer_strength"], reverse=True)

    # ---- 8H: 跨技能任务编排 ----

    def orchestrate_tasks(self, top_n: int = 5) -> list[dict]:
        """跨技能任务编排 (8H): 基于图谱推荐跨技能练习任务"""
        tasks = []
        # 互补关系 → 配对练习任务
        for rel in self.relations:
            if rel.relation_type == "complementary":
                tasks.append({
                    "type": "paired_practice",
                    "skills": [rel.source_id, rel.target_id],
                    "task": f"同时练习 {rel.source_id} 和 {rel.target_id}，强化互补效应",
                    "priority": round(rel.strength * 100, 1),
                })
        # 迁移关系 → 迁移练习任务
        for rel in self.relations:
            if rel.relation_type == "transfer":
                tasks.append({
                    "type": "transfer_practice",
                    "skills": [rel.source_id, rel.target_id],
                    "task": f"将 {rel.source_id} 的成功策略应用到 {rel.target_id}",
                    "priority": round(rel.strength * 100, 1),
                })
        # 前提关系 → 顺序练习任务
        for rel in self.relations:
            if rel.relation_type == "prerequisite":
                tasks.append({
                    "type": "sequential",
                    "skills": [rel.source_id, rel.target_id],
                    "task": f"先巩固 {rel.source_id}，再学习 {rel.target_id}",
                    "priority": round(rel.strength * 100, 1),
                })
        return sorted(tasks, key=lambda x: x["priority"], reverse=True)[:top_n]

    # ---- 8K: 跨项目知识迁移 ----

    def cross_project_patterns(self) -> list[dict]:
        """跨项目知识迁移 (8K): 检测可跨项目复用的技能模式"""
        patterns = []
        for node in self.nodes.values():
            if getattr(node, "usage_count", 0) > 10:
                patterns.append({
                    "skill_id": node.skill_id,
                    "category": node.category,
                    "usage_count": getattr(node, "usage_count", 0),
                    "proficiency": getattr(node, "proficiency", 0),
                    "transferable": getattr(node, "proficiency", 0) > 50,
                    "suggestion": f"{node.skill_id} 技能成熟，可尝试在新项目中应用",
                })
        return sorted(patterns, key=lambda x: x["proficiency"], reverse=True)

    # ---- 8S: 技能影响力评估 ----

    def influence_scores(self) -> list[dict]:
        """技能影响力评估 (8S): PageRank-like 影响力分数"""
        nodes = list(self.nodes.values())
        if not nodes:
            return []
        n = len(nodes)
        scores = {node.skill_id: 1.0 / n for node in nodes}
        for _ in range(20):
            new_scores = {node.skill_id: 0.0 for node in nodes}
            for node in nodes:
                out_degree = sum(1 for r in self.relations if r.source_id == node.skill_id)
                if out_degree == 0:
                    for other in nodes:
                        new_scores[other.skill_id] += scores[node.skill_id] / n
                else:
                    share = scores[node.skill_id] / max(out_degree, 1)
                    for r in self.relations:
                        if r.source_id == node.skill_id:
                            new_scores[r.target_id] += share
            scores = new_scores
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [{"skill_id": k, "influence": round(v, 4), "percentile": round(v / ranked[0][1] * 100, 1) if ranked[0][1] > 0 else 0}
                for k, v in ranked]

    # ---- 8U: 知识冗余检测 ----

    def detect_redundancy(self) -> list[dict]:
        """知识冗余检测 (8U): 检测过度重叠的技能对"""
        redundant = []
        for rel in self.relations:
            if rel.relation_type == "complementary" and rel.strength > 0.8:
                redundant.append({
                    "skill_a": rel.source_id, "skill_b": rel.target_id,
                    "overlap": round(rel.strength * 100, 1),
                    "suggestion": f"{rel.source_id} 和 {rel.target_id} 高度重叠，考虑合并或选择一个深入",
                })
        return sorted(redundant, key=lambda x: x["overlap"], reverse=True)

    # ---- 8V: 学习资源推荐 ----

    def recommend_resources(self, skill_id: str = "") -> list[dict]:
        """学习资源推荐 (8V): 基于技能当前水平推荐学习资源"""
        resources = []
        for node in self.nodes.values():
            if skill_id and node.skill_id != skill_id:
                continue
            prof = getattr(node, "proficiency", 0)
            if prof < 20:
                level = "beginner"
                rec = f"{node.skill_id}: 推荐入门教程和基础练习"
            elif prof < 50:
                level = "intermediate"
                rec = f"{node.skill_id}: 推荐项目实战和中级课程"
            elif prof < 80:
                level = "advanced"
                rec = f"{node.skill_id}: 推荐源码阅读和高级架构"
            else:
                level = "expert"
                rec = f"{node.skill_id}: 推荐开源贡献和教学分享"
            resources.append({"skill_id": node.skill_id, "level": level, "proficiency": prof, "recommendation": rec})
        return sorted(resources, key=lambda x: x["proficiency"])

    # ---- 8T: 跨领域创新检测 ----

    def detect_innovation(self) -> list[dict]:
        """跨领域创新检测 (8T): 检测不同分类技能间的创新组合"""
        innovations = []
        for rel in self.relations:
            src_node = self.nodes.get(rel.source_id)
            tgt_node = self.nodes.get(rel.target_id)
            if src_node and tgt_node and src_node.category != tgt_node.category:
                innovations.append({
                    "categories": f"{src_node.category} + {tgt_node.category}",
                    "skill_a": rel.source_id, "skill_b": rel.target_id,
                    "strength": round(rel.strength, 3),
                    "potential": "跨领域组合，可能产生创新应用",
                })
        return sorted(innovations, key=lambda x: x["strength"], reverse=True)
