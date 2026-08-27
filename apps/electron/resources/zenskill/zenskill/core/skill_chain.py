"""组合式/链式路由 (PROP-20260712-091)

支持多技能协作：并行组合路由 + 串行链式管线。

用法:
    from zenskill.core.skill_chain import SkillChain, ChainStage
    from zenskill.core.protocols import RoutingCandidate

    chain = SkillChain(
        preprocessors=[RoutingCandidate("analyzer", 0.9, "preprocessor")],
        primary=RoutingCandidate("writer", 0.85, "primary"),
        postprocessors=[RoutingCandidate("reviewer", 0.7, "postprocessor")],
    )

    result = await chain.execute(task, context)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .protocols import RoutingCandidate, RoutingContext


@dataclass
class ChainStage:
    """链式管线中的一个阶段"""
    candidate: RoutingCandidate
    handler: Optional[Any] = None  # SkillHandler 实现
    output: Any = None  # 阶段输出
    error: Optional[str] = None
    executed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.candidate.skill_id,
            "role": self.candidate.role,
            "confidence": self.candidate.confidence,
            "executed": self.executed,
            "error": self.error,
        }


@dataclass
class ChainResult:
    """链式执行结果"""
    task: str
    stages: List[ChainStage]
    success: bool
    final_output: Any = None
    total_confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "stages": [s.to_dict() for s in self.stages],
            "success": self.success,
            "total_confidence": round(self.total_confidence, 4),
        }


class SkillChain:
    """技能链 — 串行执行多个技能

    结构: preprocessors → primary → postprocessors

    每个阶段可以有多个候选，取置信度最高的执行。
    前一阶段的输出作为后一阶段的输入。
    """

    def __init__(
        self,
        preprocessors: Optional[List[RoutingCandidate]] = None,
        primary: Optional[RoutingCandidate] = None,
        postprocessors: Optional[List[RoutingCandidate]] = None,
        max_retries: int = 1,
    ) -> None:
        self._preprocessors = preprocessors or []
        self._primary = primary
        self._postprocessors = postprocessors or []
        self._max_retries = max_retries
        self._handler_registry: Dict[str, Any] = {}

    def register_handler(self, skill_id: str, handler: Any) -> None:
        """注册技能处理器"""
        self._handler_registry[skill_id] = handler

    def _get_handler(self, candidate: RoutingCandidate) -> Optional[Any]:
        """获取候选的处理器"""
        return self._handler_registry.get(candidate.skill_id)

    def _select_best(self, candidates: List[RoutingCandidate]) -> Optional[RoutingCandidate]:
        """选择置信度最高的候选"""
        if not candidates:
            return None
        return max(candidates, key=lambda c: c.confidence)

    def build_stages(self) -> List[ChainStage]:
        """构建执行阶段列表"""
        stages = []

        # 前置处理阶段
        for cand in self._preprocessors:
            stages.append(ChainStage(
                candidate=cand,
                handler=self._get_handler(cand),
            ))

        # 主要执行阶段
        if self._primary:
            stages.append(ChainStage(
                candidate=self._primary,
                handler=self._get_handler(self._primary),
            ))

        # 后置处理阶段
        for cand in self._postprocessors:
            stages.append(ChainStage(
                candidate=cand,
                handler=self._get_handler(cand),
            ))

        return stages

    async def execute(
        self, task: str, context: Optional[RoutingContext] = None
    ) -> ChainResult:
        """执行技能链

        Args:
            task: 任务描述
            context: 路由上下文

        Returns:
            ChainResult 包含各阶段执行结果
        """
        stages = self.build_stages()
        current_input = task
        success = True
        total_confidence = 0.0

        for stage in stages:
            if stage.handler is None:
                stage.error = f"No handler registered for {stage.candidate.skill_id}"
                stage.executed = False
                success = False
                continue

            # 执行阶段（带重试）
            for attempt in range(self._max_retries):
                try:
                    if hasattr(stage.handler, "execute"):
                        result = await stage.handler.execute(current_input, context)
                    elif hasattr(stage.handler, "can_handle"):
                        # 如果只有 can_handle，调用它获取置信度
                        result = {
                            "confidence": stage.handler.can_handle(current_input, context),
                            "output": current_input,
                        }
                    else:
                        result = {"output": current_input}

                    stage.output = result
                    stage.executed = True
                    total_confidence += stage.candidate.confidence

                    # 下一阶段的输入
                    if isinstance(result, dict) and "output" in result:
                        current_input = result["output"]
                    else:
                        current_input = result

                    break

                except Exception as e:
                    if attempt == self._max_retries - 1:
                        stage.error = str(e)
                        stage.executed = False
                        success = False
                    else:
                        continue

        # 计算总置信度
        if stages:
            total_confidence /= len(stages)

        return ChainResult(
            task=task,
            stages=stages,
            success=success,
            final_output=current_input,
            total_confidence=total_confidence,
        )

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "preprocessors": [c.to_dict() for c in self._preprocessors],
            "primary": self._primary.to_dict() if self._primary else None,
            "postprocessors": [c.to_dict() for c in self._postprocessors],
            "max_retries": self._max_retries,
        }

    @classmethod
    def from_candidates(
        cls, candidates: List[RoutingCandidate], max_retries: int = 1
    ) -> "SkillChain":
        """从候选列表构建技能链

        自动分类候选角色：
        - preprocessor: 前置处理
        - primary: 主要执行
        - postprocessor: 后置处理
        - fallback: 忽略（单独处理）
        """
        preprocessors = []
        primary = None
        postprocessors = []

        for cand in candidates:
            if cand.role == "preprocessor":
                preprocessors.append(cand)
            elif cand.role == "primary":
                if primary is None or cand.confidence > primary.confidence:
                    primary = cand
            elif cand.role == "postprocessor":
                postprocessors.append(cand)
            elif cand.role == "fallback":
                continue  # fallback 单独处理

        return cls(
            preprocessors=preprocessors,
            primary=primary,
            postprocessors=postprocessors,
            max_retries=max_retries,
        )


class ChainBuilder:
    """技能链构建器 — 从任务描述自动构建链"""

    def __init__(self) -> None:
        self._handlers: Dict[str, Any] = {}

    def register_handler(self, skill_id: str, handler: Any) -> None:
        """注册技能处理器"""
        self._handlers[skill_id] = handler

    def build_from_suggestion(
        self,
        task: str,
        candidates: List[RoutingCandidate],
        context: Optional[RoutingContext] = None,
    ) -> SkillChain:
        """从 suggest_chain() 结果构建技能链"""
        chain = SkillChain.from_candidates(candidates)

        # 注册处理器
        for cand in candidates:
            handler = self._handlers.get(cand.skill_id)
            if handler:
                chain.register_handler(cand.skill_id, handler)

        return chain

    def build_simple(
        self,
        task: str,
        primary_skill: str,
        context: Optional[RoutingContext] = None,
    ) -> SkillChain:
        """构建简单链（单个主要技能）"""
        handler = self._handlers.get(primary_skill)
        return SkillChain(
            primary=RoutingCandidate(primary_skill, 0.8, "primary"),
        )
