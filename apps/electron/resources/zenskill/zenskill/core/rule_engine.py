"""声明式路由规则引擎 (PROP-20260712-090)

将路由规则从代码抽离为声明式 DSL，支持热更新、版本化、审计。

用法:
    from zenskill.core.rule_engine import RuleEngine

    engine = RuleEngine()
    engine.load_from_yaml("routing_rules.yaml")
    candidates = engine.evaluate("帮我分析这个数据集", context)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .protocols import RoutingCandidate, RoutingContext, SkillType


@dataclass
class RuleMatch:
    """规则匹配条件"""
    keywords: List[str] = field(default_factory=list)
    regex: Optional[str] = None
    skill_type: Optional[str] = None
    env: Optional[List[str]] = None
    min_load: Optional[float] = None
    max_load: Optional[float] = None

    def matches(self, task: str, context: Optional[RoutingContext] = None) -> bool:
        """检查是否匹配"""
        task_lower = task.lower()

        # 关键词匹配
        if self.keywords:
            if not any(kw.lower() in task_lower for kw in self.keywords):
                return False

        # 正则匹配
        if self.regex:
            if not re.search(self.regex, task, re.IGNORECASE):
                return False

        # 技能类型匹配
        if self.skill_type and context and context.skill_type:
            if context.skill_type.value != self.skill_type:
                return False

        # 环境匹配
        if self.env and context:
            if context.env not in self.env:
                return False

        # 负载匹配
        if context:
            if self.min_load is not None and context.load_level < self.min_load:
                return False
            if self.max_load is not None and context.load_level > self.max_load:
                return False

        return True


@dataclass
class RoutingRule:
    """路由规则"""
    id: str
    match: RuleMatch
    target: str
    confidence: float = 0.8
    priority: int = 0
    fallback: Optional[str] = None
    description: str = ""

    def to_candidate(self) -> RoutingCandidate:
        """转换为路由候选"""
        return RoutingCandidate(
            skill_id=self.target,
            confidence=self.confidence,
            role="primary",
        )


@dataclass
class RuleSet:
    """规则集 — 一组路由规则"""
    rules: List[RoutingRule] = field(default_factory=list)
    version: str = "1.0.0"

    def evaluate(
        self, task: str, context: Optional[RoutingContext] = None
    ) -> List[RoutingCandidate]:
        """评估规则集，返回匹配的候选列表（按优先级排序）"""
        matched = []
        for rule in self.rules:
            if rule.match.matches(task, context):
                matched.append(rule)

        # 按优先级降序排列
        matched.sort(key=lambda r: r.priority, reverse=True)

        # 转换为候选列表
        candidates = [rule.to_candidate() for rule in matched]

        # 添加 fallback
        if candidates and candidates[0].confidence < 0.5:
            for rule in matched:
                if rule.fallback:
                    candidates.append(RoutingCandidate(
                        skill_id=rule.fallback,
                        confidence=0.5,
                        role="fallback",
                    ))
                    break

        return candidates


class RuleEngine:
    """声明式路由规则引擎

    支持:
    - YAML/JSON 规则文件加载
    - 热更新（reload）
    - 多规则集管理
    - 与 can_handle Protocol 兜底
    """

    def __init__(self) -> None:
        self._rule_sets: Dict[str, RuleSet] = {}
        self._default_rule_set: str = "default"

    def load_from_yaml(self, path: str) -> int:
        """从 YAML 文件加载规则

        Returns:
            加载的规则数量
        """
        file_path = Path(path)
        if not file_path.exists():
            return 0

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return self.load_from_dict(data)

    def load_from_dict(self, data: Dict[str, Any]) -> int:
        """从字典加载规则

        Returns:
            加载的规则数量
        """
        if not data or "rules" not in data:
            return 0

        rules = []
        for rule_data in data["rules"]:
            match_data = rule_data.get("match", {})
            rule = RoutingRule(
                id=rule_data.get("id", f"rule-{len(rules)}"),
                match=RuleMatch(
                    keywords=match_data.get("keywords", []),
                    regex=match_data.get("regex"),
                    skill_type=match_data.get("skill_type"),
                    env=match_data.get("env"),
                    min_load=match_data.get("min_load"),
                    max_load=match_data.get("max_load"),
                ),
                target=rule_data["target"],
                confidence=rule_data.get("confidence", 0.8),
                priority=rule_data.get("priority", 0),
                fallback=rule_data.get("fallback"),
                description=rule_data.get("description", ""),
            )
            rules.append(rule)

        rule_set = RuleSet(
            rules=rules,
            version=data.get("version", "1.0.0"),
        )

        name = data.get("name", self._default_rule_set)
        self._rule_sets[name] = rule_set

        # 如果没有默认规则集，使用第一个加载的
        if self._default_rule_set not in self._rule_sets:
            self._default_rule_set = name

        return len(rules)

    def evaluate(
        self,
        task: str,
        context: Optional[RoutingContext] = None,
        rule_set: Optional[str] = None,
    ) -> List[RoutingCandidate]:
        """评估路由规则

        Args:
            task: 任务描述
            context: 路由上下文
            rule_set: 规则集名称（None 使用默认）

        Returns:
            匹配的候选列表（按优先级排序）
        """
        name = rule_set or self._default_rule_set
        rs = self._rule_sets.get(name)
        if not rs:
            return []
        return rs.evaluate(task, context)

    def reload(self, path: str) -> int:
        """热更新规则文件

        Returns:
            更新的规则数量
        """
        return self.load_from_yaml(path)

    def list_rules(self, rule_set: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出规则"""
        name = rule_set or self._default_rule_set
        rs = self._rule_sets.get(name)
        if not rs:
            return []
        return [
            {
                "id": r.id,
                "target": r.target,
                "confidence": r.confidence,
                "priority": r.priority,
                "keywords": r.match.keywords,
                "description": r.description,
            }
            for r in rs.rules
        ]


# 全局单例
rule_engine = RuleEngine()
