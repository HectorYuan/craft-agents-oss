"""
技能路由引擎 (深度融合架构 Phase 1)

实现原设计中的三个核心能力:
- SkillCapability: 技能能力粒度描述
- can_handle(): 技能声明自己能做什么
- route_task(): 自动路由到最合适的技能

Phase Z1B 扩展: 支持 RuleEngine 声明式路由 + RoutingContext 上下文感知
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .core.protocols import RoutingCandidate, RoutingContext, SkillHandler


@dataclass
class SkillCapability:
    """技能能力描述（原设计 SkillCapability）"""
    name: str               # 能力名称
    description: str        # 能力描述
    proficiency: float = 0.5  # 熟练度 0-1
    keywords: List[str] = field(default_factory=list)  # 匹配关键词
    examples: List[str] = field(default_factory=list)  # 使用示例

    def to_spec(self) -> "CapabilitySpec":
        """升级到 CapabilitySpec (Phase S)"""
        from zenskill.core.skill_spec import CapabilitySpec
        return CapabilitySpec.from_capability(self)


@dataclass
class SkillRoute:
    """技能路由条目"""
    skill_id: str
    capabilities: List[SkillCapability]
    level_bonus: float = 1.0  # 境界加成 (NOVICE=0.8, MASTER=1.5)


class SkillRouter:
    """技能路由引擎"""

    def __init__(self):
        self._routes: Dict[str, SkillRoute] = {}
        self._keyword_index: Dict[str, List[str]] = defaultdict(list)

        # 注册已知技能
        self._register_builtin_skills()

    def _register_builtin_skills(self):
        """注册内置技能能力"""
        skills = {
            "zenskill-core": SkillRoute(
                skill_id="zenskill-core",
                capabilities=[
                    SkillCapability(
                        name="memory_management",
                        description="记忆管理: 添加/搜索/导出记忆",
                        proficiency=0.7,
                        keywords=["记忆", "memory", "记录", "回忆", "搜索记忆", "导出"],
                        examples=["添加记忆", "搜索之前的讨论", "导出项目记忆"],
                    ),
                    SkillCapability(
                        name="growth_tracking",
                        description="成长追踪: 查看技能等级/进度/趋势",
                        proficiency=0.8,
                        keywords=["成长", "等级", "进度", "熟练度", "境界", "修炼"],
                        examples=["查看当前等级", "成长趋势", "什么时候升级"],
                    ),
                    SkillCapability(
                        name="zen_reflection",
                        description="禅思反思: 触发反思/生成洞见/系统诊断",
                        proficiency=0.6,
                        keywords=["反思", "禅思", "回顾", "总结", "诊断", "健康"],
                        examples=["帮我反思今天的收获", "总结这次会话", "系统健康检查"],
                    ),
                    SkillCapability(
                        name="data_collection",
                        description="数据采集: 11 源全量采集 + NLP 分析",
                        proficiency=0.9,
                        keywords=["采集", "收集", "数据", "分析", "collect", "统计"],
                        examples=["采集最新数据", "今天的数据统计", "查看用户画像"],
                    ),
                    SkillCapability(
                        name="prediction",
                        description="预测辅助: 下一步行动预测 + 目标建议",
                        proficiency=0.7,
                        keywords=["预测", "建议", "下一步", "推荐", "目标"],
                        examples=["下一步该做什么", "给我建议", "推荐任务"],
                    ),
                ],
            ),
            "claude-code": SkillRoute(
                skill_id="claude-code",
                capabilities=[
                    SkillCapability(
                        name="code_assistance",
                        description="代码辅助: 编写/修改/审查代码",
                        proficiency=0.9,
                        keywords=["代码", "写", "修改", "实现", "编程", "code", "函数", "类"],
                        examples=["写一个函数", "修改这段代码", "审查这个 PR"],
                    ),
                    SkillCapability(
                        name="debugging",
                        description="调试: 排查/修复/诊断问题",
                        proficiency=0.8,
                        keywords=["debug", "修复", "bug", "错误", "报错", "排查", "调试"],
                        examples=["修复这个 bug", "为什么报错", "排查问题"],
                    ),
                    SkillCapability(
                        name="file_operations",
                        description="文件操作: 读写/搜索/管理文件",
                        proficiency=0.9,
                        keywords=["文件", "读取", "写入", "搜索", "查找", "目录"],
                        examples=["读取这个文件", "搜索所有 Python 文件"],
                    ),
                ],
            ),
        }

        for sid, route in skills.items():
            self.register(sid, route)

    def register(self, skill_id: str, route: SkillRoute) -> None:
        """注册技能路由"""
        self._routes[skill_id] = route
        # 构建关键词倒排索引
        for cap in route.capabilities:
            for kw in cap.keywords:
                self._keyword_index[kw.lower()].append(skill_id)

    def sync_installed_skills(self) -> int:
        """从 SkillDAO 同步已安装技能进路由表 (P3-1: 路由与真实库存联动)

        以 tags/keywords 作为触发词注册通用能力路由；已在路由表中的技能跳过。
        返回新增数量（DB 不可用时返回 0，不影响内置路由）。
        """
        try:
            from .core.skill_profile import SkillProfile

            profiles = SkillProfile.list_all(top_k=200)
        except Exception:
            return 0

        count = 0
        for p in profiles:
            if not p.skill_id or p.skill_id in self._routes:
                continue
            keywords = [t for t in (p.tags or []) if t][:8]
            if not keywords and not p.description:
                continue
            self.register(p.skill_id, SkillRoute(
                skill_id=p.skill_id,
                capabilities=[SkillCapability(
                    name="general",
                    description=(p.description or p.name)[:100],
                    proficiency=0.5,
                    keywords=keywords or [p.name.lower()[:12]] if p.name else [],
                    examples=[],
                )],
            ))
            count += 1
        return count

    def find_best_skill(self, task: str) -> Optional[Tuple[str, SkillCapability, float]]:
        """找到最适合处理此任务的技能

        评分策略:
        1. 关键词精确匹配: +3 分/词
        2. 关键词部分匹配: +1 分/词
        3. 境界加成: × level_bonus
        4. 能力熟练度: × proficiency

        Returns:
            (skill_id, best_capability, score) 或 None
        """
        task_lower = task.lower()
        scores: Dict[str, List[Tuple[SkillCapability, float]]] = defaultdict(list)

        for sid, route in self._routes.items():
            for cap in route.capabilities:
                score = 0.0
                matched = False
                for kw in cap.keywords:
                    # 精确匹配
                    if kw.lower() in task_lower:
                        score += 3.0
                        matched = True
                    # 部分匹配: 要求 ≥2 个 bigram 重叠（单 bigram 偶合误触发）
                    elif len(kw) >= 3:
                        overlaps = sum(
                            1 for i in range(len(kw) - 1)
                            if kw[i:i+2].lower() in task_lower
                        )
                        if overlaps >= 2:
                            score += 1.0
                            matched = True

                if matched:
                    # 境界加成 + 熟练度加权
                    score *= route.level_bonus * cap.proficiency
                    scores[sid].append((cap, score))

        if not scores:
            return None

        # 找最高分
        best_sid = max(scores, key=lambda s: max(p[1] for p in scores[s]))
        best_cap, best_score = max(scores[best_sid], key=lambda p: p[1])

        return (best_sid, best_cap, round(best_score, 1))

    def route_task(self, task: str) -> Optional[Dict[str, Any]]:
        """智能路由: 找到最佳技能并返回执行建议

        Returns:
            {"skill_id": ..., "capability": ..., "confidence": ..., "suggestion": ...}
        """
        result = self.find_best_skill(task)
        if not result:
            return {
                "skill_id": "unknown",
                "capability": None,
                "confidence": 0,
                "suggestion": "未找到匹配的技能能力, 请尝试更具体的描述",
            }

        sid, cap, score = result
        return {
            "skill_id": sid,
            "capability": cap.name,
            "confidence": min(score / 10, 1.0),  # 归一化到 0-1
            "proficiency": cap.proficiency,
            "suggestion": self._generate_suggestion(sid, cap, task),
        }

    # ═══════════════════════════════════════════════════════════════
    # Phase Z1B: 声明式规则路由 (PROP-20260712-090)
    # ═══════════════════════════════════════════════════════════════

    def route_with_context(
        self, task: str, context: Optional[RoutingContext] = None
    ) -> Optional[Dict[str, Any]]:
        """带上下文的智能路由

        优先使用 RuleEngine 声明式规则，无匹配时回退到关键词匹配。

        Returns:
            {"skill_id": ..., "confidence": ..., "rule_id": ..., "source": ...}
        """
        from .core.rule_engine import rule_engine

        # 1. 尝试 RuleEngine 声明式路由
        candidates = rule_engine.evaluate(task, context)
        if candidates:
            best = candidates[0]
            return {
                "skill_id": best.skill_id,
                "confidence": best.confidence,
                "rule_id": None,
                "source": "rule_engine",
                "role": best.role,
            }

        # 2. 回退到关键词匹配
        result = self.find_best_skill(task)
        if result:
            sid, cap, score = result
            return {
                "skill_id": sid,
                "confidence": min(score / 10, 1.0),
                "rule_id": None,
                "source": "keyword_match",
                "capability": cap.name,
            }

        return None

    def register_handler(self, skill_id: str, handler: SkillHandler) -> None:
        """注册 SkillHandler 到路由表

        让 SkillHandler Protocol 实现也能参与路由。
        """
        if not hasattr(self, "_handlers"):
            self._handlers: Dict[str, SkillHandler] = {}
        self._handlers[skill_id] = handler

    def route_to_handler(
        self, task: str, context: Optional[RoutingContext] = None
    ) -> Optional[Tuple[str, SkillHandler, float]]:
        """通过 SkillHandler Protocol 路由到最匹配的处理器

        Returns:
            (skill_id, handler, confidence) 或 None
        """
        if not hasattr(self, "_handlers") or not self._handlers:
            return None

        best_id = None
        best_handler = None
        best_score = 0.0

        for sid, handler in self._handlers.items():
            try:
                score = handler.can_handle(task, context)
                if score > best_score:
                    best_score = score
                    best_handler = handler
                    best_id = sid
            except Exception:
                continue

        if best_handler and best_score > 0.0:
            return (best_id, best_handler, best_score)
        return None

    def list_capabilities(self) -> List[Dict]:
        """列出所有已注册的技能能力"""
        result = []
        for sid, route in self._routes.items():
            for cap in route.capabilities:
                result.append({
                    "skill_id": sid,
                    "capability": cap.name,
                    "proficiency": cap.proficiency,
                    "keywords": cap.keywords[:5],
                })
        return result

    @staticmethod
    def _generate_suggestion(skill_id: str, cap: SkillCapability, task: str) -> str:
        """基于技能和能力生成执行建议"""
        cmd_map = {
            "memory_management": "zenskill memory search",
            "growth_tracking": "zenskill growth status",
            "zen_reflection": "zenskill reflect trigger",
            "data_collection": "zenskill collector run-all",
            "prediction": "zenskill mirror predict",
        }

        cmd = cmd_map.get(cap.name, "")
        if cmd:
            return (
                f"对于「{task[:30]}」, 建议使用 {skill_id} 的 {cap.name} 能力。"
                f"可执行: `{cmd}`"
            )
        return (
            f"对于「{task[:30]}」, {skill_id} 的 {cap.name} 能力最匹配 "
            f"(熟练度 {cap.proficiency:.0%})"
        )


    # ═══════════════════════════════════════════════════════════════
    # 阶段 2: 跨技能编排 (8H)
    # ═══════════════════════════════════════════════════════════════

    def coordinate_skills(self, task: str) -> List[Dict]:
        """多技能编排: 将复杂任务分解为子任务, 分配给多个技能

        算法:
        1. 关键词扫描 → 识别需要的能力组合
        2. 能力分组 → 按技能聚合
        3. 排序 → 按依赖关系排序
        """
        task_lower = task.lower()
        assigned: Dict[str, List[SkillCapability]] = defaultdict(list)

        for sid, route in self._routes.items():
            for cap in route.capabilities:
                if any(kw.lower() in task_lower for kw in cap.keywords):
                    assigned[sid].append(cap)

        if not assigned:
            return []

        plan = []
        for sid, caps in assigned.items():
            route = self._routes.get(sid)
            bonus = route.level_bonus if route else 1.0
            plan.append({
                "skill_id": sid,
                "capabilities": [c.name for c in caps],
                "confidence": round(
                    sum(c.proficiency for c in caps) / len(caps) * bonus, 2
                ),
                "order": self._estimate_order(caps),
            })

        # 按依赖排序: 数据采集 → 分析 → 建议
        order_map = {"data_collection": 1, "code_assistance": 2, "debugging": 2,
                     "prediction": 3, "zen_reflection": 3, "growth_tracking": 3,
                     "memory_management": 2, "file_operations": 1}
        plan.sort(key=lambda p: min(
            order_map.get(c, 5) for c in p["capabilities"]
        ))

        for i, p in enumerate(plan):
            p["step"] = i + 1

        return plan

    @staticmethod
    def _estimate_order(capabilities: List[SkillCapability]) -> int:
        """估算执行顺序: 采集(1) → 处理(2) → 输出(3)"""
        names = {c.name for c in capabilities}
        if "data_collection" in names or "file_operations" in names:
            return 1
        if "prediction" in names or "zen_reflection" in names:
            return 3
        return 2

    # ═══════════════════════════════════════════════════════════════
    # 阶段 3: 进化历史追踪 (8M)
    # ═══════════════════════════════════════════════════════════════

    def get_evolution_history(self, skill_id: str) -> List[Dict]:
        """获取技能进化历史"""
        import json
        from pathlib import Path

        history_file = Path.home() / ".zenskill" / "states" / f"{skill_id}.history.jsonl"
        if not history_file.exists():
            return []

        events = []
        for line in open(history_file):
            try:
                entry = json.loads(line.strip())
                events.append({
                    "timestamp": entry.get("timestamp", ""),
                    "action": entry.get("action", ""),
                    "level": entry.get("snapshot", {}).get("level", ""),
                    "usage_count": entry.get("snapshot", {}).get("usage_count", 0),
                })
            except Exception:
                pass
        return events[-20:]  # 最近 20 条


# 全局单例
skill_router = SkillRouter()
