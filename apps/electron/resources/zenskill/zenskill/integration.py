"""
跨模块集成 (P7×P9 + P8×P9)

7E: 目标引擎 × 9E 预测引擎 — 自动生成目标
8D: 技能图谱 × Hook — 实时关系更新
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════
# 7E: 目标引擎 × 预测引擎集成
# ═══════════════════════════════════════════════════════════════

def suggest_goals_from_pipeline() -> List[Dict[str, str]]:
    """从采集管道结果自动生成目标建议

    读取 pipeline.json → 分析弱领域/高意图 → 映射为成长目标
    """
    pipeline_file = Path.home() / ".zenskill" / "mirroring" / "pipeline.json"
    if not pipeline_file.exists():
        return []

    try:
        pipeline = json.loads(pipeline_file.read_text())
    except Exception:
        return []

    nlp = pipeline.get("nlp", {})
    intents = nlp.get("intents", {})
    domains = nlp.get("domains", {})
    goals = []

    # 1. 低覆盖领域 → 目标
    domain_goals = {
        "cli_tui": ("提升 CLI/TUI 技能", "用 zenskill tui 探索交互功能，每天使用 collector list 查看数据"),
        "devops": ("加强 DevOps 实践", "为当前项目添加 Dockerfile 和 CI 配置"),
        "frontend": ("接触前端开发", "用 React 或 Vue 构建一个简单的管理界面"),
        "data": ("探索数据处理", "用 pandas 分析 ~/.zenskill/mirroring/events.jsonl"),
        "backend": ("深化后端能力", "优化 API 性能，添加缓存和限流"),
        "ai_ml": ("扩展 AI 应用", "尝试用 LLM API 实现一个新功能"),
    }
    for domain, (title, desc) in domain_goals.items():
        score = domains.get(domain, 100)
        if score < 25:
            goals.append({
                "dimension": domain,
                "title": title,
                "description": desc,
                "reason": f"{domain} 领域覆盖率仅 {score:.0f}%，建议补强",
            })

    # 2. 高频 debug 意图 → 测试目标
    if intents.get("debug", 0) >= 3:
        goals.append({
            "dimension": "stability",
            "title": "降低调试频率",
            "description": f"当前 debug 意图 {intents['debug']} 次，增加自动化测试来减少调试时间",
            "reason": f"debug 意图 {intents['debug']} 次，高于平均水平",
        })

    # 3. 高频 refactor → 架构规划目标
    if intents.get("refactor", 0) >= 2 and intents.get("plan", 0) < 2:
        goals.append({
            "dimension": "proficiency",
            "title": "增加架构规划",
            "description": "重构前先花 5 分钟做架构设计，减少返工",
            "reason": f"重构 {intents['refactor']} 次但规划仅 {intents.get('plan', 0)} 次",
        })

    return goals[:3]  # Top-3


# ═══════════════════════════════════════════════════════════════
# 8D: 技能图谱 × Hook 实时更新
# ═══════════════════════════════════════════════════════════════

def auto_discover_graph() -> Optional[Dict[str, Any]]:
    """自动发现并更新技能关系图谱

    由 collector hook 周期性调用（每 30 分钟冷却）。
    返回: {"new_relationships": N, "total_nodes": N} 或 None(跳过)
    """
    cache_file = Path.home() / ".zenskill" / "graph" / ".last_auto_discover"
    now = time.time()

    # 30 分钟冷却
    if cache_file.exists():
        try:
            last = float(cache_file.read_text().strip())
            if now - last < 1800:
                return None
        except Exception:
            pass

    try:
        from zenskill.systems.collaboration.dependency_graph import SkillDependencyGraph

        graph = SkillDependencyGraph()
        before = len(graph.get_all_skills())

        # 发现新关系
        new_rels = graph.discover_relations()
        after = len(graph.get_all_skills())

        # 写入冷却时间
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(str(now))

        return {
            "new_relationships": len(new_rels),
            "total_nodes": after,
            "nodes_added": after - before,
        }
    except Exception as e:
        return {"error": str(e)}


def integrated_hook_output() -> Dict[str, Any]:
    """集成输出：同时运行 7E + 8D

    供 collector hook 调用，一次性获取所有跨模块建议。
    """
    result: Dict[str, Any] = {}

    # 7E: 目标建议
    goal_suggestions = suggest_goals_from_pipeline()
    if goal_suggestions:
        result["goal_suggestions"] = goal_suggestions

    # 8D: 图谱更新
    graph_result = auto_discover_graph()
    if graph_result:
        result["graph_update"] = graph_result

    return result
