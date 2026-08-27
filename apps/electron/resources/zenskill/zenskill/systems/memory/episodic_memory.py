"""
ZenSkill - L2 情景记忆

特性：
- 中等容量（默认 1000 条）
- 倒排索引加速关键词联想检索
- 定期遗忘低强度记忆
- JSONL 持久化到磁盘
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Set, Optional

from .memory_base import MemoryItem, BaseMemory

logger = logging.getLogger(__name__)


class EpisodicMemory(BaseMemory):
    """
    L2 情景记忆 - 用户交互历史的长期记忆

    类似人类的情景记忆：
    - 记住发生过什么事
    - 通过关键词联想检索
    - 不重要的事会逐渐被遗忘
    - 每次 store 自动持久化
    """

    # 停用词（简单分词时过滤）
    STOP_WORDS = {
        "the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "with",
        "是", "的", "了", "我", "你", "他", "她", "它", "们", "在", "有",
    }

    def __init__(self, max_items: int = 1000, forget_ratio: float = 0.05,
                 skill_id: str = "zenskill-core") -> None:
        self._max_items = max_items
        self._forget_ratio = forget_ratio
        self._skill_id = skill_id
        self._episodes: dict[str, MemoryItem] = {}
        self._inverted_index: dict[str, Set[str]] = {}
        self._file_path: Optional[Path] = None
        self._init_file_path()
        self._load_from_disk()
        logger.debug(f"EpisodicMemory initialized, capacity={max_items}, loaded={len(self._episodes)}")

    def _init_file_path(self) -> None:
        try:
            from ...core.paths import get_user_data_dir
            d = get_user_data_dir() / "memory" / "episodic"
            d.mkdir(parents=True, exist_ok=True)
            self._file_path = d / f"{self._skill_id}_episodes.jsonl"
        except Exception:
            self._file_path = None

    def _load_from_disk(self) -> None:
        """从磁盘加载持久化的记忆"""
        if not self._file_path or not self._file_path.exists():
            return
        try:
            for line in self._file_path.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    item = MemoryItem(
                        id=data["id"],
                        content=data["content"],
                        importance=data.get("importance", 0.5),
                        tags=set(data.get("tags", [])),
                        created_at=data.get("created_at", 0),
                        last_accessed=data.get("last_accessed", 0),
                        access_count=data.get("access_count", 0),
                        metadata=data.get("metadata", {}),
                    )
                    self._episodes[item.id] = item
                    for tag in item.tags:
                        self._inverted_index.setdefault(tag, set()).add(item.id)
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Failed to load episodic memory: {e}")

    def _save_to_disk(self, items: list[MemoryItem] = None) -> None:
        """持久化记忆到磁盘"""
        if not self._file_path:
            return
        try:
            episodes = items if items is not None else list(self._episodes.values())
            lines = []
            for item in episodes:
                lines.append(json.dumps({
                    "id": item.id, "content": item.content,
                    "importance": item.importance, "tags": list(item.tags),
                    "created_at": item.created_at, "last_accessed": item.last_accessed,
                    "access_count": item.access_count, "metadata": item.metadata,
                }, ensure_ascii=False))
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            self._file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save episodic memory: {e}")
    
    def _tokenize(self, text: str) -> Set[str]:
        """
        简单分词：空格分隔，去停用词
        
        Args:
            text: 要分词的文本
        
        Returns:
            关键词集合
        """
        return {
            token.strip(".,!?;:\"'()[]{}").lower()
            for token in text.split()
            if token.strip(".,!?;:\"'()[]{}").lower() not in self.STOP_WORDS
            and len(token) > 1
        }
    
    async def store(self, item: MemoryItem) -> str:
        """
        存入情景记忆，同时构建倒排索引
        
        如果超过容量，自动淘汰最弱的记忆
        """
        item_id = item.id
        
        # 自动提取内容标签
        content_tags = self._tokenize(item.content)
        item.tags.update(content_tags)
        
        self._episodes[item_id] = item
        
        # 更新倒排索引
        for tag in item.tags:
            if tag not in self._inverted_index:
                self._inverted_index[tag] = set()
            self._inverted_index[tag].add(item_id)
        
        # 超过容量：淘汰最弱的
        if len(self._episodes) > self._max_items:
            await self._forget_weakest()

        self._save_to_disk()
        return item_id
    
    async def retrieve(self, query: str, top_k: int = 5) -> List[MemoryItem]:
        """
        联想检索
        
        算法：
        1. 倒排索引召回有任何标签匹配的候选
        2. 多重加权排序：标签重叠度 × 记忆强度 × 内容精确匹配加分
        3. 被命中的记忆会被激活（touch）
        """
        query_tags = self._tokenize(query)
        
        # 无关键词：返回最新的 N 条
        if not query_tags:
            return sorted(
                self._episodes.values(),
                key=lambda x: x.created_at,
                reverse=True
            )[:top_k]
        
        # 1. 召回：倒排索引找有任何标签匹配的候选
        candidate_ids: Set[str] = set()
        for tag in query_tags:
            if tag in self._inverted_index:
                candidate_ids.update(self._inverted_index[tag])
        
        if not candidate_ids:
            return []
        
        # 2. 排序：多重加权
        scored: list[tuple[MemoryItem, float]] = []
        query_lower = query.lower()
        
        for cid in candidate_ids:
            item = self._episodes[cid]
            
            # 权重1: 标签匹配重叠度
            overlap = len(item.tags & query_tags)
            tag_score = overlap / max(len(query_tags), 1)
            
            # 权重2: 记忆强度（时间衰减 + 访问频率）
            strength = item.get_strength()
            
            # 权重3: 内容包含精确查询词加分
            contains_exact = 1.5 if query_lower in item.content.lower() else 1.0
            
            # 总得分
            total_score = tag_score * strength * contains_exact
            
            scored.append((item, total_score))
            item.touch()  # 激活记忆
        
        # 3. 按得分降序排序返回
        scored.sort(key=lambda x: x[1], reverse=True)
        return [item for item, _ in scored[:top_k]]
    
    async def _forget_weakest(self) -> None:
        """
        淘汰最弱的记忆
        
        按记忆强度升序，淘汰 weakest_ratio 百分比的记忆
        """
        n_to_remove = max(1, int(len(self._episodes) * self._forget_ratio))
        
        # 按记忆强度升序，取最弱的 N 个
        sorted_items = sorted(
            self._episodes.values(),
            key=lambda x: x.get_strength()
        )
        
        for item in sorted_items[:n_to_remove]:
            await self.forget(item.id)
        
        logger.debug(
            f"EpisodicMemory overflow, forgot {n_to_remove} weakest memories"
        )
    
    async def forget(self, item_id: str) -> bool:
        """
        删除记忆，同时清理倒排索引
        """
        if item_id not in self._episodes:
            return False
        
        item = self._episodes[item_id]
        
        # 从索引中移除
        for tag in item.tags:
            if tag in self._inverted_index:
                self._inverted_index[tag].discard(item_id)
                # 标签下无内容则清理标签
                if not self._inverted_index[tag]:
                    del self._inverted_index[tag]
        
        # 删除记忆
        del self._episodes[item_id]
        self._save_to_disk()
        return True
    
    def get(self, item_id: str) -> Optional[MemoryItem]:
        """直接获取某条记忆"""
        return self._episodes.get(item_id)
    
    async def consolidate(self, ratio: float = 0.1) -> List[MemoryItem]:
        """
        记忆整合：提取高重要性的记忆，准备升华为语义记忆
        
        Args:
            ratio: 提取比例（前百分之多少）
        
        Returns:
            高重要性记忆列表
        """
        n = int(len(self._episodes) * ratio)
        if n == 0:
            return []
        
        # 按重要性降序，取前 n 个
        important = sorted(
            self._episodes.values(),
            key=lambda x: x.importance,
            reverse=True
        )[:n]
        
        logger.debug(f"Consolidated {len(important)} high-importance memories")
        return important
    
    def get_by_time(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 100,
    ) -> List[MemoryItem]:
        """按时间范围检索"""
        items = list(self._episodes.values())
        
        # 过滤时间
        if start_time is not None:
            items = [i for i in items if i.created_at >= start_time]
        if end_time is not None:
            items = [i for i in items if i.created_at <= end_time]
        
        # 按时间倒序
        items.sort(key=lambda x: x.created_at, reverse=True)
        return items[:limit]
    
    def __len__(self) -> int:
        return len(self._episodes)
    
    def get_index_stats(self) -> dict:
        """获取索引统计信息"""
        return {
            "total_memories": len(self._episodes),
            "total_tags": len(self._inverted_index),
            "avg_memories_per_tag": (
                sum(len(v) for v in self._inverted_index.values())
                / max(1, len(self._inverted_index))
            ),
        }
    
    def __repr__(self) -> str:
        stats = self.get_index_stats()
        return (
            f"EpisodicMemory(memories={stats['total_memories']}, "
            f"tags={stats['total_tags']}, "
            f"capacity={self._max_items})"
        )
