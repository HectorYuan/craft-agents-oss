"""
ZenSkill - Purification Loop 净化循环

连续出错或收到负面反馈时触发：
- 分析错误原因
- 记录错误模式
- 生成改进策略
- 更新认知偏差
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from ..loop_base import (
    ZenLoopPlugin,
    LoopType,
    LoopResult,
)

logger = logging.getLogger(__name__)


class PurificationLoop(ZenLoopPlugin):
    """
    净化循环 - 错误修正，认知净化
    
    人类类比：做错了事之后反思、总结经验教训，
    避免下次再犯同样的错误
    """
    
    def __init__(
        self,
        error_threshold: int = 3,  # 连续 3 次错误触发
    ) -> None:
        self._error_threshold = error_threshold
        self._consecutive_errors = 0  # 连续错误计数
    
    @property
    def loop_type(self) -> LoopType:
        return LoopType.PURIFICATION
    
    @property
    def trigger_condition(self) -> str:
        return f"连续 {self._error_threshold} 次收到负面反馈或执行失败时触发"
    
    async def should_trigger(self, context: dict[str, Any]) -> bool:
        """判断是否应该触发净化循环"""
        
        # 检查是否有明确的错误上下文
        error_occurred = context.get("error_occurred", False)
        is_negative_feedback = context.get("feedback_is_negative", False)
        
        # 检查连续错误计数
        if error_occurred or is_negative_feedback:
            self._consecutive_errors += 1
        else:
            # 成功时重置计数
            self._consecutive_errors = 0
        
        # 超过阈值时触发
        if self._consecutive_errors >= self._error_threshold:
            return True
        
        # 手动强制触发
        if context.get("force_purification", False):
            return True
        
        return False
    
    async def execute(
        self,
        context: dict[str, Any],
        memory_system: Optional[Any] = None,
    ) -> LoopResult:
        """
        执行净化逻辑
        
        步骤：
        1. 分析最近的错误记录
        2. 识别错误模式
        3. 生成改进策略
        4. 存入记忆，避免再犯
        """
        start_time = __import__("time").time()
        import time
        
        action_items: list[str] = []
        memory_updates = []
        
        # 1. 分析错误上下文
        error_message = context.get("error_message", "")
        error_query = context.get("error_query", "")
        recent_errors = context.get("recent_errors", [])
        
        # 2. 识别错误模式
        error_patterns = self._analyze_error_patterns(
            error_message, error_query, recent_errors
        )
        
        # 3. 生成改进策略
        action_items = self._generate_improvement_strategies(error_patterns)
        
        # 4. 存入记忆系统
        if memory_system:
            # 存入错误记录
            error_id = await memory_system.store(
                content=f"错误记录: {error_message[:100]}...",
                memory_type="episodic",
                importance=0.7,
                tags={"错误", "净化", "需要改进"},
            )
            memory_updates.append({"type": "error_record", "id": error_id})
            
            # 存入改进策略
            for strategy in action_items[:3]:
                strategy_id = await memory_system.store(
                    content="",
                    memory_type="semantic",
                    subject="系统",
                    predicate="改进策略",
                    object=strategy,
                    importance=0.85,
                )
                memory_updates.append({"type": "improvement", "id": strategy_id})
        
        # 重置计数（净化完成后）
        self._consecutive_errors = 0
        
        # 生成摘要
        summary_parts = ["认知净化完成:"]
        summary_parts.append(f"- 分析了 {len(error_patterns)} 种错误模式")
        summary_parts.append(f"- 生成了 {len(action_items)} 项改进策略")
        if error_patterns:
            summary_parts.append(f"- 主要问题: {error_patterns[0]}")
        
        summary = "\n".join(summary_parts)
        
        duration = (time.time() - start_time) * 1000
        
        logger.warning(
            f"PurificationLoop executed: {len(error_patterns)} patterns, "
            f"{len(action_items)} improvements identified"
        )
        
        return LoopResult(
            loop_type=LoopType.PURIFICATION,
            success=True,
            summary=summary,
            extracted_patterns=error_patterns,
            action_items=action_items,
            memory_updates=memory_updates,
            duration_ms=duration,
        )
    
    def _analyze_error_patterns(
        self,
        error_message: str,
        error_query: str,
        recent_errors: list[str],
    ) -> list[str]:
        """分析错误模式"""
        patterns = []
        error_lower = error_message.lower()
        query_lower = error_query.lower()
        
        # 1. 理解错误类型
        if "超时" in error_lower or "timeout" in error_lower:
            patterns.append("执行超时 - 需要优化任务拆分策略")
        elif "理解" in error_lower or "无法" in error_lower or "不清楚" in error_lower:
            patterns.append("意图理解错误 - 需要改进查询解析")
        elif "格式" in error_lower or "语法" in error_lower:
            patterns.append("输出格式错误 - 需要加强格式校验")
        
        # 2. 查询复杂性分析
        if len(query_lower) > 200:
            patterns.append("查询过于复杂 - 需要优化长文本处理能力")
        
        if "为什么" in query_lower or "怎么" in query_lower:
            patterns.append("用户需要解释性回答 - 回答要更详细有条理")
        
        # 3. 连续错误模式
        if len(recent_errors) >= 2:
            patterns.append("连续出错模式 - 需要增加前置校验和重试机制")
        
        # 默认模式
        if not patterns:
            patterns.append("通用执行错误 - 需要更详细的日志追踪")
        
        return patterns
    
    def _generate_improvement_strategies(self, error_patterns: list[str]) -> list[str]:
        """根据错误模式生成改进策略"""
        strategies = []
        
        for pattern in error_patterns:
            if "超时" in pattern:
                strategies.append("下次遇到类似任务时，先估计复杂度，适当拆分")
            elif "理解错误" in pattern:
                strategies.append("对于模糊的查询，先向用户确认意图再执行")
            elif "格式" in pattern:
                strategies.append("输出前进行格式校验，确保符合用户期望")
            elif "连续出错" in pattern:
                strategies.append("增加失败重试机制和降级方案")
        
        # 通用策略
        if len(strategies) < 2:
            strategies.append("增加执行前的输入验证步骤")
            strategies.append("记录更多上下文信息便于事后分析")
        
        return strategies
