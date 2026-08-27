"""
ZenSkill - Insight Loop 洞见循环

积累足够记忆后触发，跨领域关联产生新洞见：
- 发现用户行为模式
- 识别任务之间的关联
- 产生改进建议
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


class InsightLoop(ZenLoopPlugin):
    """
    洞见循环 - 跨领域关联，产生新洞见
    
    人类类比：突然灵光一闪，发现了事物之间的关联
    """
    
    def __init__(
        self,
        trigger_threshold: int = 5,  # 每 5 条记忆触发一次
    ) -> None:
        self._threshold = trigger_threshold
        self._last_insight_count = 0  # 上次产生洞见时的记忆数量
    
    @property
    def loop_type(self) -> LoopType:
        return LoopType.INSIGHT
    
    @property
    def trigger_condition(self) -> str:
        return f"情景记忆数量每增加 {self._threshold} 条时触发一次"
    
    async def should_trigger(self, context: dict[str, Any]) -> bool:
        """判断是否应该触发洞见"""
        # 检查记忆系统
        memory_system = context.get("memory_system")
        if not memory_system:
            return False
        
        # 获取当前记忆总数
        total_memories = 0
        if hasattr(memory_system, "episodic"):
            total_memories = len(memory_system.episodic)
        
        # 超过阈值且自上次洞察后又积累了足够的记忆
        if total_memories - self._last_insight_count >= self._threshold:
            return True
        
        return False
    
    async def execute(
        self,
        context: dict[str, Any],
        memory_system: Optional[Any] = None,
    ) -> LoopResult:
        """
        执行洞见生成
        
        步骤：
        1. 检索近期所有记忆
        2. 跨领域关联，发现新模式
        3. 生成洞见存入语义记忆
        """
        start_time = __import__("time").time()
        import time
        
        new_insights: list[str] = []
        memory_updates = []
        
        if memory_system is None:
            return LoopResult(
                loop_type=LoopType.INSIGHT,
                success=False,
                summary="没有记忆系统，无法生成洞见",
            )
        
        # 1. 获取近期记忆
        recent_memories = []
        if hasattr(memory_system, "episodic"):
            episodic = memory_system.episodic
            if hasattr(episodic, "get_by_time"):
                recent_memories = episodic.get_by_time(limit=50)
        
        # 2. 分析记忆内容
        contents = []
        for item in recent_memories:
            if hasattr(item, "content"):
                contents.append(item.content.lower())
        
        all_content = " ".join(contents)
        
        # 3. 产生洞见
        new_insights = self._generate_insights(all_content, recent_memories)
        
        # 4. 洞见存入语义记忆
        for insight in new_insights:
            if memory_system:
                insight_id = await memory_system.store(
                    content=insight,
                    memory_type="semantic",
                    subject="系统",
                    predicate="洞见",
                    object=insight,
                    importance=0.9,  # 洞见重要性很高
                )
                memory_updates.append({"type": "insight", "id": insight_id})
        
        # 更新计数
        self._last_insight_count = len(recent_memories)
        
        # 生成摘要
        if new_insights:
            summary = f"产生了 {len(new_insights)} 条新洞见:\n"
            insight_summaries = [f"- {insight}" for insight in new_insights[:3]]
            summary += "\n".join(insight_summaries)
        else:
            summary = "本次未发现新的跨领域关联"
        
        duration = (time.time() - start_time) * 1000
        
        logger.info(
            f"InsightLoop completed: {len(new_insights)} insights generated, "
            f"{duration:.1f}ms"
        )
        
        return LoopResult(
            loop_type=LoopType.INSIGHT,
            success=True,
            summary=summary,
            new_insights=new_insights,
            memory_updates=memory_updates,
            duration_ms=duration,
        )
    
    def _generate_insights(
        self,
        all_content: str,
        memories: list[Any],
    ) -> list[str]:
        """
        从记忆内容中生成洞见
        
        简单版本：基于关键词频率和共现模式
        """
        insights = []
        content_lower = all_content.lower()
        
        # 1. 用户角色推断
        code_terms = ["架构", "代码", "调试", "优化"]
        code_count = sum(content_lower.count(term) for term in code_terms)
        
        if code_count >= 6:
            insights.append("用户似乎是一名软件工程师，正在做系统设计工作")
        elif code_count >= 3:
            insights.append("用户正在进行大量编程相关的工作")
        
        # 2. 用户偏好模式
        if "简洁" in content_lower and "示例" in content_lower:
            insights.append("用户偏好简洁的代码示例")
        if "详细" in content_lower and "解释" in content_lower:
            insights.append("用户喜欢详细的解释和说明")
        
        # 3. 任务复杂度分析
        memory_count = len(memories)
        if memory_count >= 20:
            insights.append(
                f"用户已经进行了 {memory_count} 次交互，"
                f"看起来正在处理复杂的长期项目"
            )
        
        # 4. 技术栈识别
        tech_stack = []
        for tech in ["python", "javascript", "java", "go", "rust", "c++"]:
            if tech in content_lower:
                tech_stack.append(tech)
        
        if len(tech_stack) >= 2:
            insights.append(
                f"用户的技术栈包括: {', '.join(tech_stack)}"
            )
        
        # 5. 默认洞见
        if not insights:
            insights.append(
                "用户正在探索多个技术领域，持续观察中"
            )
        
        return insights[:5]  # 最多返回 5 条洞见
