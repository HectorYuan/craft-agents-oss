"""
ZenSkill - MetaMemory 元记忆系统主类

整合三层记忆：
- L1 Working Memory: 工作记忆，LRU
- L2 Episodic Memory: 情景记忆，倒排索引联想
- L3 Semantic Memory: 语义记忆，三元组知识图谱

特性：
- 零外部依赖，纯 Python 实现
- 仿生遗忘机制
- 记忆整合（Consolidation）
"""
from __future__ import annotations

import logging
import hashlib
from typing import Any, Optional, List

from ...core.base import (
    BaseSystem,
    SystemConfig,
    SystemMetadata,
    SystemType,
)

from .memory_base import MemoryItem
from .working_memory import WorkingMemory
from .episodic_memory import EpisodicMemory
from .semantic_memory import SemanticMemory

logger = logging.getLogger(__name__)


class MetaMemory(BaseSystem):
    """
    MetaMemory - 仿生三层记忆系统
    
    零依赖开箱即用，支持后续可升级向量库。
    """
    
    def __init__(
        self,
        working_size: int = 20,
        episodic_size: int = 1000,
        skill_id: str = "zenskill-core",
    ) -> None:
        self._skill_id = skill_id
        # 三层记忆 — episodic 支持持久化
        self._working = WorkingMemory(working_size)
        self._episodic = EpisodicMemory(episodic_size, skill_id=skill_id)
        self._semantic = SemanticMemory(skill_id=skill_id)
        # 首次初始化：从 SkillStateManager 桥接已有 episodes
        self._bridge_if_empty()

        logger.debug(
            f"MetaMemory initialized: "
            f"Working({working_size}), "
            f"Episodic({episodic_size}), "
            f"Semantic(unlimited)"
        )

    def _bridge_if_empty(self) -> None:
        """首次使用时从 SkillStateManager 导入已有 episodes"""
        if len(self._episodic) > 0:
            return
        try:
            from ...core.paths import SkillStateManager
            mgr = SkillStateManager(self._skill_id)
            state = mgr.load()
            episodes = state.get("episodes", [])
            if episodes:
                import hashlib
                for ep in episodes[-200:]:  # 最近 200 条
                    if not isinstance(ep, dict):
                        continue
                    content = ep.get("content", "") or ep.get("action", "")
                    item_id = hashlib.md5(content.encode()).hexdigest()[:12]
                    item = MemoryItem(
                        id=item_id,
                        content=str(content)[:200],
                        importance=0.5,
                        tags={ep.get("action", "general"), "bridged"},
                    )
                    self._episodic._episodes[item_id] = item
                self._episodic._save_to_disk()
                logger.info(f"Bridged {len(self._episodic)} episodes from SkillStateManager")
        except Exception as e:
            logger.debug(f"Bridge skipped: {e}")
    
    @property
    def system_type(self) -> SystemType:
        return SystemType.MEMORY
    
    @property
    def metadata(self) -> SystemMetadata:
        return SystemMetadata(
            name="meta-memory",
            version="1.0.0",
            description="MetaMemory - 三层仿生记忆系统",
            priority=20,
            dependencies=[],
        )
    
    async def initialize(self, config: SystemConfig) -> None:
        """初始化记忆系统"""
        await super().initialize(config)
        logger.info("MetaMemory system initialized")
    
    # ====================================================================
    # 统一存储接口
    # ====================================================================
    
    async def store(
        self,
        content: str,
        memory_type: str = "auto",
        importance: float = 0.5,
        tags: Optional[set[str]] = None,
        **kwargs,
    ) -> str:
        """
        存入记忆
        
        Args:
            content: 记忆内容
            memory_type: 
                - "working": 存入工作记忆
                - "episodic": 存入情景记忆
                - "semantic": 存入语义记忆（需要 subject, predicate, object）
                - "auto": 自动选择（默认存入情景记忆）
            importance: 重要性 0-1
            tags: 标签集合
            **kwargs: 语义记忆需要的 subject, predicate, object
        
        Returns:
            记忆 ID
        """
        if memory_type == "working":
            item_id = hashlib.md5(content.encode()).hexdigest()[:12]
            item = MemoryItem(
                id=item_id,
                content=content,
                importance=importance,
                tags=tags or set(),
                metadata=kwargs,
            )
            return await self._working.store(item)
        
        elif memory_type == "semantic":
            # 语义记忆：提取三元组
            subject = kwargs.get("subject", "unknown")
            predicate = kwargs.get("predicate", "related_to")
            object = kwargs.get("object", content)
            return await self._semantic.store(
                subject=subject,
                predicate=predicate,
                object=object,
                confidence=importance,
            )
        
        else:  # 默认：auto 或 episodic
            item_id = hashlib.md5(content.encode()).hexdigest()[:12]
            item = MemoryItem(
                id=item_id,
                content=content,
                importance=importance,
                tags=tags or set(),
                metadata=kwargs,
            )
            return await self._episodic.store(item)
    
    # ====================================================================
    # 统一检索接口
    # ====================================================================
    
    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[Any]:
        """
        统一检索入口
        
        返回混合结果：
        - L1 工作记忆的匹配结果（最先返回）
        - L2 情景记忆的联想结果
        - L3 语义记忆的相关事实
        
        Args:
            query: 查询文本
            top_k: 每层返回数量
        
        Returns:
            混合记忆列表
        """
        # L1 工作记忆快速检索
        working_results = await self._working.retrieve(query, top_k=2)
        
        # L2 情景记忆联想检索
        episodic_results = await self._episodic.retrieve(query, top_k=top_k)
        
        # L3 语义记忆自然语言查询
        semantic_results = await self._semantic.query_natural(query, top_k=3)
        
        # 合并返回（工作记忆在前，表示正在想的事情）
        all_results: List[Any] = []
        all_results.extend(working_results)
        all_results.extend(episodic_results)
        all_results.extend(semantic_results)
        
        return all_results
    
    async def retrieve_with_context(
        self,
        query: str,
        current_context: dict[str, Any],
        top_k: int = 5,
    ) -> List[Any]:
        """
        上下文感知的记忆检索
        
        算法：
        1. 基础相似度得分（语义/关键词）
        2. + 上下文匹配加权（如：用户是谁、当前任务类型）
        3. + 记忆强度加权（重要性×衰减）
        4. + 时间近因加权
        5. 重排序返回
        
        Args:
            query: 查询文本
            current_context: 当前上下文字典
            top_k: 返回数量
        
        Returns:
            重排序后的记忆列表
        """
        # 1. 基础检索
        candidates = await self.retrieve(query, top_k=top_k * 2)
        
        # 2. 上下文重排序
        scored = []
        for mem in candidates:
            base_score = 1.0
            
            # 判断是否是 MemoryItem（情景/工作记忆）
            if hasattr(mem, "content"):
                # 是 MemoryItem
                # 上下文匹配：用户身份
                if "user_id" in current_context and hasattr(mem, "metadata"):
                    if mem.metadata.get("user_id") == current_context["user_id"]:
                        base_score *= 1.5
                
                # 上下文匹配：当前任务
                if "task_type" in current_context and hasattr(mem, "metadata"):
                    if mem.metadata.get("task_type") == current_context["task_type"]:
                        base_score *= 1.3
                
                # 记忆强度
                if hasattr(mem, "get_strength"):
                    base_score *= mem.get_strength()
                
                # 时间近因：越新的记忆越强
                if hasattr(mem, "created_at"):
                    import time
                    age_hours = (time.time() - mem.created_at) / 3600
                    recency_factor = 1.0 / (1.0 + age_hours * 0.1)
                    base_score *= recency_factor
            
            scored.append((mem, base_score))
        
        # 3. 排序返回
        scored.sort(key=lambda x: x[1], reverse=True)
        return [mem for mem, _ in scored[:top_k]]
    
    # ====================================================================
    # 记忆操作
    # ====================================================================
    
    async def consolidate(self) -> int:
        """
        记忆整合（Consolidation）
        
        从情景记忆中提取高重要性的记忆，升华为语义记忆
        
        这就是 ZenLoop 的深度睡眠阶段做的事
        
        Returns:
            升华到语义记忆的事实数量
        """
        # 从情景记忆提取高重要性记忆
        important = await self._episodic.consolidate(ratio=0.1)
        if not important:
            return 0
        
        count = 0
        for item in important:
            # 简单策略：只处理有 metadata 中提取三元组
            # 如果有 subject/predicate/object 就存入语义记忆
            if "subject" in item.metadata and "predicate" in item.metadata:
                await self._semantic.store(
                    subject=item.metadata["subject"],
                    predicate=item.metadata["predicate"],
                    object=item.metadata.get("object", item.content),
                    confidence=item.importance,
                )
                count += 1
        
        logger.info(f"Consolidated {count} memories from episodic to semantic")
        return count
    
    async def decay_all(self) -> None:
        """
        全系统遗忘
        定期调用，模拟自然遗忘
        """
        # 工作记忆：自然 LRU 淘汰，不需要额外衰减
        
        # 情景记忆：定期清理弱的
        await self._episodic._forget_weakest()
        
        # 语义记忆：置信度衰减
        await self._semantic.decay_all()
    
    # ====================================================================
    # 各层直接访问（高级用法）
    # ====================================================================
    
    @property
    def working(self) -> WorkingMemory:
        """访问工作记忆层"""
        return self._working
    
    @property
    def episodic(self) -> EpisodicMemory:
        """访问情景记忆层"""
        return self._episodic
    
    @property
    def semantic(self) -> SemanticMemory:
        """访问语义记忆层"""
        return self._semantic
    
    # ====================================================================
    # 统计信息
    # ====================================================================
    
    def get_stats(self) -> dict:
        """获取记忆系统统计信息"""
        return {
            "working": {
                "count": len(self._working),
                "capacity": self._working._max_items,
            },
            "episodic": {
                "count": len(self._episodic),
                "capacity": self._episodic._max_items,
                **self._episodic.get_index_stats(),
            },
            "semantic": self._semantic.get_stats(),
        }
    
    async def shutdown(self) -> None:
        """关闭记忆系统"""
        await super().shutdown()
        logger.info("MetaMemory system shutdown complete")
    
    def __repr__(self) -> str:
        stats = self.get_stats()
        return (
            f"MetaMemory("
            f"L1={stats['working']['count']}/{stats['working']['capacity']}, "
            f"L2={stats['episodic']['count']}/{stats['episodic']['capacity']}, "
            f"L3={stats['semantic']['total_facts']})"
        )
