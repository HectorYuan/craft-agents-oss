"""
ZenSkill - Consolidation Loop 整合循环

周期性执行，类似人类睡眠期间的记忆整理：
- 清理重复、弱记忆
- 从情景记忆中提取模式，升华为语义记忆
- 优化记忆索引结构
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


class ConsolidationLoop(ZenLoopPlugin):
    """
    整合循环 - 周期性记忆整理固化
    
    人类类比：睡眠期间，大脑整理白天的记忆，
    把重要的短期记忆转化为长期记忆
    """
    
    def __init__(
        self,
        interval_seconds: int = 3600,  # 默认每小时执行一次
    ) -> None:
        self._interval = interval_seconds
        self._last_run: float = 0.0
    
    @property
    def loop_type(self) -> LoopType:
        return LoopType.CONSOLIDATION
    
    @property
    def trigger_condition(self) -> str:
        return f"每 {self._interval} 秒周期性执行，或记忆数量超过阈值时触发"
    
    async def should_trigger(self, context: dict[str, Any]) -> bool:
        """判断是否应该执行整合"""
        import time
        
        # 检查是否有手动强制触发
        if context.get("force_consolidation", False):
            return True
        
        # 检查时间间隔
        now = time.time()
        if now - self._last_run >= self._interval:
            return True
        
        # 检查记忆数量阈值（情景记忆超过 100 条时触发）
        memory_system = context.get("memory_system")
        if memory_system and hasattr(memory_system, "episodic"):
            if len(memory_system.episodic) >= 100:
                return True
        
        return False
    
    async def execute(
        self,
        context: dict[str, Any],
        memory_system: Optional[Any] = None,
    ) -> LoopResult:
        """
        执行记忆整合
        
        步骤：
        1. 触发 MetaMemory 的 consolidate 方法
        2. 清理弱记忆（重要性 < 0.3，且很久没访问的）
        3. 更新最后运行时间
        """
        start_time = __import__("time").time()
        import time
        
        results: list[str] = []
        memory_updates = []
        extracted_patterns = []
        
        if memory_system is None:
            return LoopResult(
                loop_type=LoopType.CONSOLIDATION,
                success=False,
                summary="没有记忆系统，无法执行整合",
            )
        
        # 1. 执行 MetaMemory 自带的 consolidate
        if hasattr(memory_system, "consolidate"):
            consolidated_count = await memory_system.consolidate()
            results.append(
                f"从情景记忆升华了 {consolidated_count} 条知识到语义记忆"
            )
            memory_updates.append({
                "type": "consolidation",
                "count": consolidated_count,
            })
        
        # 2. 触发全系统遗忘
        if hasattr(memory_system, "decay_all"):
            await memory_system.decay_all()
            results.append("执行全系统记忆衰减")
        
        # 3. 清理语义记忆中低置信度的事实
        if hasattr(memory_system, "semantic"):
            semantic = memory_system.semantic
            if hasattr(semantic, "forget_low_confidence"):
                removed = await semantic.forget_low_confidence(threshold=0.3)
                if removed > 0:
                    results.append(f"清理了 {removed} 条低置信度的语义事实")
        
        # 4. 提取常见模式
        patterns = await self._extract_common_patterns(memory_system)
        extracted_patterns.extend(patterns)
        
        # 更新最后运行时间
        self._last_run = time.time()
        
        # 生成摘要
        summary = "记忆整合完成:\n" + "\n".join(f"- {r}" for r in results)
        
        # 存入记忆
        if memory_system:
            await memory_system.store(
                content=f"记忆整合记录: {summary}",
                memory_type="episodic",
                importance=0.5,
                tags={"记忆整合", "系统维护"},
            )
        
        duration = (time.time() - start_time) * 1000
        
        logger.info(
            f"ConsolidationLoop completed: {len(results)} actions, "
            f"{len(extracted_patterns)} patterns extracted, "
            f"{duration:.1f}ms"
        )
        
        return LoopResult(
            loop_type=LoopType.CONSOLIDATION,
            success=True,
            summary=summary,
            extracted_patterns=extracted_patterns,
            memory_updates=memory_updates,
            duration_ms=duration,
        )
    
    async def _extract_common_patterns(self, memory_system: Any) -> list[str]:
        """从所有记忆中提取常见模式"""
        patterns = []
        
        if not hasattr(memory_system, "episodic"):
            return patterns
        
        # 检索最近的记忆
        episodic = memory_system.episodic
        if hasattr(episodic, "get_by_time"):
            recent = episodic.get_by_time(limit=20)
            
            # 统计标签频率
            tag_counts: dict[str, int] = {}
            for item in recent:
                if hasattr(item, "tags"):
                    for tag in item.tags:
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1
            
            # 提取高频标签模式
            for tag, count in tag_counts.items():
                if count >= 3:
                    patterns.append(f"近期高频话题: {tag} 出现了 {count} 次")
        
        # 统计语义记忆中的主题
        if hasattr(memory_system, "semantic"):
            semantic = memory_system.semantic
            if hasattr(semantic, "get_entities"):
                entities = semantic.get_entities()
                if "用户" in entities:
                    patterns.append("已建立完整的用户画像")
        
        return patterns
