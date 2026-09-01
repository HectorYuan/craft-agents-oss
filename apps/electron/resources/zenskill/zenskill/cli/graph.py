"""graph 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

from ..cli_utils import output as cli_output

def cmd_graph_overview(args: argparse.Namespace) -> None:
    """技能图谱概览"""
    from zenskill.systems.collaboration.dependency_graph import SkillDependencyGraph

    graph = SkillDependencyGraph()
    nodes = graph.get_all_skills()
    edges = graph.relations
    cli_output({
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": [{"skill_id": n.skill_id, "name": n.name, "level": n.level} for n in nodes],
    }, args, text=graph.visualize_ascii_graph)


def cmd_graph_register(args: argparse.Namespace) -> None:
    """注册技能到图谱"""
    from zenskill.systems.collaboration.dependency_graph import SkillDependencyGraph

    graph = SkillDependencyGraph()
    node = graph.register_skill(args.skill_id, args.name, args.category)
    cli_output({
        "skill_id": node.skill_id, "name": node.name,
        "category": node.category, "level": node.level,
        "composite_score": node.composite_score,
    }, args, text=lambda: (
        f"✅ 技能已注册到图谱\n"
        f"   ID: {node.skill_id}\n"
        f"   名称: {node.name}\n"
        f"   分类: {node.category}\n"
        f"   当前境界: {node.level}\n"
        f"   综合分数: {node.composite_score:.0f}"
    ))


def cmd_graph_discover(args: argparse.Namespace) -> None:
    """发现技能间的关系"""
    from zenskill.systems.collaboration.dependency_graph import SkillDependencyGraph

    graph = SkillDependencyGraph()
    new_relations = graph.discover_relations()
    type_names = {
        "prerequisite": "前置依赖", "complementary": "互补关系",
        "competing": "竞争关系", "transfer": "知识迁移", "co_occurrence": "共同使用",
    }

    def _format_discover():
        lines = ["🔍 技能关系发现", "=" * 60, ""]
        if not new_relations:
            lines.append("   未发现新的技能关系（需要至少 2 个已注册的技能）")
            lines.append("")
            lines.append("💡 使用 'zenskill graph register <skill_id>' 注册技能")
            return "\n".join(lines)
        lines.append(f"   发现 {len(new_relations)} 条新关系：\n")
        for i, rel in enumerate(new_relations, 1):
            rel_name = type_names.get(rel.relation_type, rel.relation_type)
            from_skill = graph.get_skill(rel.from_skill)
            to_skill = graph.get_skill(rel.to_skill)
            from_name = from_skill.name if from_skill else rel.from_skill
            to_name = to_skill.name if to_skill else rel.to_skill
            lines.append(f"   {i}. {from_name} ←→ {to_name}")
            lines.append(f"      类型: {rel_name} | 强度: {rel.strength:.0%} | 置信度: {rel.confidence:.0%}")
            if rel.evidence:
                lines.append(f"      证据: {rel.evidence[0]}")
            lines.append("")
        return "\n".join(lines)

    relations_data = []
    for rel in new_relations:
        from_skill = graph.get_skill(rel.from_skill)
        to_skill = graph.get_skill(rel.to_skill)
        relations_data.append({
            "from": from_skill.name if from_skill else rel.from_skill,
            "to": to_skill.name if to_skill else rel.to_skill,
            "type": rel.relation_type, "strength": rel.strength,
            "confidence": rel.confidence,
        })
    cli_output({"count": len(new_relations), "relations": relations_data}, args, text=_format_discover)


def cmd_graph_related(args: argparse.Namespace) -> None:
    """查看技能的关联技能"""
    from zenskill.systems.collaboration.dependency_graph import SkillDependencyGraph

    graph = SkillDependencyGraph()
    related = graph.get_related_skills(args.skill_id, args.type)
    type_names = {
        "prerequisite": "前置依赖", "complementary": "互补关系",
        "competing": "竞争关系", "transfer": "知识迁移", "co_occurrence": "共同使用",
    }

    def _format_related():
        lines = [f"🔗 {args.skill_id} 的关联技能", "=" * 60, ""]
        if not related:
            lines.append("   暂无关联技能\n")
            lines.append("💡 使用 'zenskill graph discover' 发现关系")
            return "\n".join(lines)
        for i, (skill, relation) in enumerate(related, 1):
            rel_name = type_names.get(relation.relation_type, relation.relation_type)
            lines.append(f"   {i}. {skill.name} [{skill.level}]")
            lines.append(f"      关系: {rel_name} | 强度: {relation.strength:.0%}")
            if relation.evidence:
                lines.append(f"      证据: {relation.evidence[0]}")
            lines.append("")
        return "\n".join(lines)

    cli_output({
        "skill_id": args.skill_id,
        "related": [{"name": s.name, "level": s.level, "type": r.relation_type,
                      "strength": r.strength} for s, r in related],
    }, args, text=_format_related)


def cmd_graph_query(args: argparse.Namespace) -> None:
    """8P: 知识图谱查询"""
    from ..systems.collaboration.dependency_graph import SkillDependencyGraph
    g = SkillDependencyGraph()
    results = g.query(keyword=args.keyword, category=getattr(args, 'category', ''))
    cli_output({"count": len(results), "results": results}, args, text=lambda: (
        f"\n🔍 图谱查询结果 ({len(results)} 条)\n\n" +
        "\n".join(f"  {r['skill_id']:25s} {r['category']:12s} 连接: {r['relations']}  → {', '.join(r['connected_to'][:3]) or '-'}" for r in results) + "\n"
    ))


def cmd_graph_combos(args: argparse.Namespace) -> None:
    """8Q: 技能组合推荐"""
    from ..systems.collaboration.dependency_graph import SkillDependencyGraph
    g = SkillDependencyGraph()
    combos = g.recommend_combinations(skill_id=getattr(args, 'skill_id', ''))
    cli_output({"count": len(combos), "combos": combos}, args, text=lambda: (
        f"\n🤝 推荐技能组合 ({len(combos)} 组)\n\n" +
        "\n".join(f"  {c['source']} + {c['target']:20s} {c['type']:15s} 协同: {c['synergy_score']}" for c in combos) + "\n"
    ))


def cmd_graph_alerts(args: argparse.Namespace) -> None:
    """8J: 生态健康预警"""
    from ..systems.collaboration.dependency_graph import SkillDependencyGraph
    g = SkillDependencyGraph()
    alerts = g.health_alerts()
    cli_output({"count": len(alerts), "alerts": alerts}, args, text=lambda: (
        f"\n⚠️  生态健康预警 ({len(alerts)} 条)\n\n" +
        ("  ✅ 生态系统健康" if not alerts else
         "\n".join(f"  {'⚠️' if a['level'] == 'warning' else 'ℹ️'} {a['message']}" for a in alerts)) + "\n"
    ))


def cmd_graph_conflicts(args: argparse.Namespace) -> None:
    """8O: 跨技能冲突检测"""
    from ..systems.collaboration.dependency_graph import SkillDependencyGraph
    g = SkillDependencyGraph()
    conflicts = g.detect_conflicts()
    cli_output({"count": len(conflicts), "conflicts": conflicts}, args, text=lambda: (
        f"\n⚡ 跨技能冲突 ({len(conflicts)} 个)\n\n" +
        ("  ✅ 未检测到冲突" if not conflicts else
         "\n".join(f"  {c['skill_a']} ↔ {c['skill_b']:20s} 严重度: {c['severity']}\n    💡 {c['suggestion']}" for c in conflicts)) + "\n"
    ))


def cmd_graph_dynamics(args: argparse.Namespace) -> None:
    """8N: 网络动力学分析"""
    from ..systems.collaboration.dependency_graph import SkillDependencyGraph
    g = SkillDependencyGraph()
    d = g.network_dynamics()

    def _format_dynamics():
        lines = [f"\n🌐 网络动力学分析\n"]
        lines.append(f"  节点: {d['node_count']}  边: {d['edge_count']}  密度: {d['density']:.3f}")
        lines.append(f"\n  Top 度中心性:")
        for item in d.get("top_by_degree", [])[:5]:
            lines.append(f"    {item['skill']:30s} degree={item['degree']}")
        lines.append(f"\n  Top 聚类系数:")
        for item in d.get("top_by_clustering", [])[:5]:
            lines.append(f"    {item['skill']:30s} clustering={item['clustering']}")
        lines.append("")
        return "\n".join(lines)

    cli_output(d, args, text=_format_dynamics)


def cmd_graph_lifecycle(args: argparse.Namespace) -> None:
    """8M: 技能生命周期分析"""
    from ..systems.collaboration.dependency_graph import SkillDependencyGraph
    g = SkillDependencyGraph()
    stages = g.lifecycle_analysis()
    icons = {"creation": "🌱", "growth": "📈", "maturity": "🌳", "dormant": "💤"}
    cli_output({"count": len(stages), "stages": stages}, args, text=lambda: (
        f"\n🔄 技能生命周期 ({len(stages)} 个)\n\n" +
        "\n".join(f"  {icons.get(s['stage'], '  ')} {s['skill_id']:30s} [{s['stage']:10s}] use={s['usage_count']} prof={s['proficiency']}" for s in stages) + "\n"
    ))


def cmd_graph_transfer(args: argparse.Namespace) -> None:
    """8E: 迁移学习模式检测"""
    from ..systems.collaboration.dependency_graph import SkillDependencyGraph
    g = SkillDependencyGraph()
    patterns = g.detect_transfer_patterns()
    cli_output({"count": len(patterns), "patterns": patterns[:10]}, args, text=lambda: (
        f"\n🔄 迁移学习模式 ({len(patterns)} 个)\n\n" +
        ("  (未检测到迁移模式，运行 graph discover 发现关联)" if not patterns else
         "\n".join(f"  {p['from_skill']} → {p['to_skill']:25s} 强度: {p['transfer_strength']}\n    💡 {p['suggestion']}" for p in patterns[:10])) + "\n"
    ))


def cmd_graph_orchestrate(args: argparse.Namespace) -> None:
    """8H: 跨技能任务编排"""
    from ..systems.collaboration.dependency_graph import SkillDependencyGraph
    g = SkillDependencyGraph()
    tasks = g.orchestrate_tasks()
    icons = {"paired_practice": "🤝", "transfer_practice": "🔄", "sequential": "📋"}

    def _format_tasks():
        lines = [f"\n🎯 跨技能任务编排 ({len(tasks)} 个)\n"]
        if not tasks:
            lines.append("  (技能关联不足，运行 graph discover 发现更多关联)")
        for t in tasks:
            icon = icons.get(t["type"], "  ")
            lines.append(f"  {icon} [{t['type']:20s}] 优先级: {t['priority']}")
            lines.append(f"    技能: {' + '.join(t['skills'][:2])}")
            lines.append(f"    {t['task']}")
        lines.append("")
        return "\n".join(lines)

    cli_output({"count": len(tasks), "tasks": tasks}, args, text=_format_tasks)


def cmd_graph_cross_project(args: argparse.Namespace) -> None:
    """8K: 跨项目知识迁移"""
    from ..systems.collaboration.dependency_graph import SkillDependencyGraph
    g = SkillDependencyGraph()
    patterns = g.cross_project_patterns()
    cli_output({"count": len(patterns), "patterns": patterns}, args, text=lambda: (
        f"\n📦 跨项目知识迁移 ({len(patterns)} 个)\n\n" +
        "\n".join(
            f"  {'✅' if p['transferable'] else '⏳'} {p['skill_id']:30s} [{p['category']:10s}] prof={p['proficiency']} use={p['usage_count']}" +
            (f"\n    💡 {p['suggestion']}" if p["transferable"] else "")
            for p in patterns
        ) + "\n"
    ))


def cmd_graph_influence(args: argparse.Namespace) -> None:
    """8S: 技能影响力评估"""
    from ..systems.collaboration.dependency_graph import SkillDependencyGraph
    g = SkillDependencyGraph()
    scores = g.influence_scores()
    cli_output({"count": len(scores), "scores": scores}, args, text=lambda: (
        f"\n⭐ 技能影响力 (PageRank) ({len(scores)} 个)\n\n" +
        "\n".join(f"  [{'█' * int(s['percentile'] / 10)}{'░' * (10 - int(s['percentile'] / 10))}] {s['skill_id']:30s} {s['influence']:.4f}" for s in scores) + "\n"
    ))


def cmd_graph_redundancy(args: argparse.Namespace) -> None:
    """8U: 知识冗余检测"""
    from ..systems.collaboration.dependency_graph import SkillDependencyGraph
    g = SkillDependencyGraph()
    redundant = g.detect_redundancy()
    cli_output({"count": len(redundant), "redundant": redundant}, args, text=lambda: (
        f"\n🔄 知识冗余检测 ({len(redundant)} 个)\n\n" +
        ("  ✅ 未检测到明显冗余" if not redundant else
         "\n".join(f"  ⚠️  重叠度: {r['overlap']}% — {r['skill_a']} ↔ {r['skill_b']}\n    💡 {r['suggestion']}" for r in redundant)) + "\n"
    ))


def cmd_graph_resources(args: argparse.Namespace) -> None:
    """8V: 学习资源推荐"""
    from ..systems.collaboration.dependency_graph import SkillDependencyGraph
    g = SkillDependencyGraph()
    resources = g.recommend_resources(skill_id=getattr(args, 'skill_id', ''))
    icons = {"beginner": "🌱", "intermediate": "📈", "advanced": "🎯", "expert": "🏆"}
    cli_output({"count": len(resources), "resources": resources}, args, text=lambda: (
        f"\n📚 学习资源推荐 ({len(resources)} 个)\n\n" +
        "\n".join(f"  {icons.get(r['level'], '  ')} [{r['level']:12s}] {r['skill_id']:25s} prof={r['proficiency']}\n    {r['recommendation']}" for r in resources) + "\n"
    ))


def cmd_graph_innovate(args: argparse.Namespace) -> None:
    """8T: 跨领域创新检测"""
    from ..systems.collaboration.dependency_graph import SkillDependencyGraph
    g = SkillDependencyGraph()
    innovations = g.detect_innovation()
    cli_output({"count": len(innovations), "innovations": innovations[:10]}, args, text=lambda: (
        f"\n💡 跨领域创新检测 ({len(innovations)} 个)\n\n" +
        ("  (跨领域关联不足，运行 graph discover 发现更多)" if not innovations else
         "\n".join(f"  {inv['categories']:25s} {inv['skill_a']} + {inv['skill_b']}\n    强度: {inv['strength']} — {inv['potential']}" for inv in innovations[:10])) + "\n"
    ))


def cmd_graph_learning_path(args: argparse.Namespace) -> None:
    """推荐学习路径"""
    from zenskill.systems.collaboration.dependency_graph import SkillDependencyGraph

    graph = SkillDependencyGraph()
    path = graph.recommend_learning_path(args.target_skill, args.max_depth)
    level_icons = {"NOVICE": "🌱", "APPRENTICE": "🌿", "ADEPT": "🌳", "EXPERT": "🌲", "MASTER": "🏆"}

    def _format_path():
        lines = [f"🎯 学习路径推荐 - 目标: {args.target_skill}", "=" * 60, ""]
        if not path:
            lines.append("   暂无推荐（需要先注册多个技能并发现关系）\n")
            lines.append("💡 先使用 'zenskill graph register' 注册技能")
            return "\n".join(lines)
        lines.append("   推荐按以下顺序学习：\n")
        for i, item in enumerate(path, 1):
            skill = item["skill"]
            icon = level_icons.get(skill.level, "❓")
            lines.append(f"   {i}. {icon} {skill.name} [{skill.level}]")
            lines.append(f"      {item['reason']}\n")
        return "\n".join(lines)

    cli_output({
        "target": args.target_skill,
        "path": [{"name": item["skill"].name, "level": item["skill"].level,
                  "reason": item["reason"]} for item in path],
    }, args, text=_format_path)



def register_graph_parser(subparsers) -> None:
    """注册 graph 子命令组。"""
    graph_parser = subparsers.add_parser("graph", help="技能依赖图谱（P8 多技能协同）")
    graph_parser.set_defaults(func=cmd_graph_overview)  # graph 默认为 overview
    graph_subparsers = graph_parser.add_subparsers(dest="subcommand", help="图谱操作")

    # graph overview (默认)
    graph_overview_parser = graph_subparsers.add_parser("overview", help="技能图谱概览")
    graph_overview_parser.set_defaults(func=cmd_graph_overview)

    # graph register
    graph_register_parser = graph_subparsers.add_parser("register", help="注册技能到图谱")
    graph_register_parser.add_argument("skill_id", help="技能ID")
    graph_register_parser.add_argument("--name", help="技能显示名称")
    graph_register_parser.add_argument("--category", default="general", help="技能分类（coding/writing/analysis/learning/productivity/communication/general）")
    graph_register_parser.set_defaults(func=cmd_graph_register)

    # graph discover
    graph_discover_parser = graph_subparsers.add_parser("discover", help="自动发现技能间的关系")
    graph_discover_parser.set_defaults(func=cmd_graph_discover)

    # graph related
    graph_related_parser = graph_subparsers.add_parser("related", help="查看技能的关联技能")
    graph_related_parser.add_argument("skill_id", help="技能ID")
    graph_related_parser.add_argument("--type", help="按关系类型过滤")
    graph_related_parser.set_defaults(func=cmd_graph_related)

    # graph learn-path
    graph_learnpath_parser = graph_subparsers.add_parser("learn-path", help="推荐学习路径")
    graph_learnpath_parser.add_argument("target_skill", help="目标技能ID")
    graph_learnpath_parser.add_argument("--max-depth", type=int, default=3, help="最大深度")
    graph_learnpath_parser.set_defaults(func=cmd_graph_learning_path)
    # graph query (8P)
    graph_query_parser = graph_subparsers.add_parser("query", help="查询知识图谱 (8P)")
    graph_query_parser.add_argument("--keyword", default="", help="搜索关键词")
    graph_query_parser.add_argument("--category", default="", help="技能分类")
    graph_query_parser.set_defaults(func=cmd_graph_query)
    # graph combos (8Q)
    graph_combos_parser = graph_subparsers.add_parser("combos", help="推荐技能组合 (8Q)")
    graph_combos_parser.add_argument("--skill-id", default="", help="指定技能")
    graph_combos_parser.set_defaults(func=cmd_graph_combos)
    # graph alerts (8J)
    graph_alerts_parser = graph_subparsers.add_parser("alerts", help="生态健康预警 (8J)")
    graph_alerts_parser.set_defaults(func=cmd_graph_alerts)
    # graph conflicts (8O)
    graph_conflicts_parser = graph_subparsers.add_parser("conflicts", help="跨技能冲突检测 (8O)")
    graph_conflicts_parser.set_defaults(func=cmd_graph_conflicts)
    # graph dynamics (8N)
    graph_dynamics_parser = graph_subparsers.add_parser("dynamics", help="网络动力学分析 (8N)")
    graph_dynamics_parser.set_defaults(func=cmd_graph_dynamics)
    # graph lifecycle (8M)
    graph_lifecycle_parser = graph_subparsers.add_parser("lifecycle", help="技能生命周期分析 (8M)")
    graph_lifecycle_parser.set_defaults(func=cmd_graph_lifecycle)
    # graph transfer (8E)
    graph_transfer_parser = graph_subparsers.add_parser("transfer", help="迁移学习模式检测 (8E)")
    graph_transfer_parser.set_defaults(func=cmd_graph_transfer)
    # graph orchestrate (8H)
    graph_orch_parser = graph_subparsers.add_parser("orchestrate", help="跨技能任务编排 (8H)")
    graph_orch_parser.set_defaults(func=cmd_graph_orchestrate)
    # graph cross-project (8K)
    graph_crossproj_parser = graph_subparsers.add_parser("cross-project", help="跨项目知识迁移 (8K)")
    graph_crossproj_parser.set_defaults(func=cmd_graph_cross_project)
    # graph influence (8S)
    graph_influence_parser = graph_subparsers.add_parser("influence", help="技能影响力评估 (8S)")
    graph_influence_parser.set_defaults(func=cmd_graph_influence)
    # graph redundancy (8U)
    graph_redundancy_parser = graph_subparsers.add_parser("redundancy", help="知识冗余检测 (8U)")
    graph_redundancy_parser.set_defaults(func=cmd_graph_redundancy)
    # graph resources (8V)
    graph_resources_parser = graph_subparsers.add_parser("resources", help="学习资源推荐 (8V)")
    graph_resources_parser.add_argument("--skill-id", default="", help="指定技能")
    graph_resources_parser.set_defaults(func=cmd_graph_resources)
    # graph innovate (8T)
    graph_innovate_parser = graph_subparsers.add_parser("innovate", help="跨领域创新检测 (8T)")
    graph_innovate_parser.set_defaults(func=cmd_graph_innovate)

    # cross 命令组（跨技能洞察）
