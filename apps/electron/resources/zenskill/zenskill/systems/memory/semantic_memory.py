"""
ZenSkill - L3 语义记忆

特性：
- 三元组知识存储 (主体, 谓词, 客体)
- 实体索引加速检索
- 置信度自动更新（重复验证提升置信度）
- 知识不会被遗忘，只会降低置信度
- JSONL 持久化到磁盘
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, List, Tuple

from .memory_base import SemanticFact

logger = logging.getLogger(__name__)


class SemanticMemory:
    """
    L3 语义记忆 - 结构化知识图谱

    类似人类的语义记忆：
    - 存储关于世界的事实和知识
    - 不依赖具体情景，是抽象的知识
    - 不会被遗忘，但会有置信度衰减
    - 重复验证会提升置信度
    - store/decay 自动持久化
    """

    def __init__(self, skill_id: str = "zenskill-core") -> None:
        self._skill_id = skill_id
        self._facts: dict[str, SemanticFact] = {}
        self._entity_index: dict[str, set[str]] = {}
        self._file_path: Optional[Path] = None
        self._init_file_path()
        self._load_from_disk()
        logger.debug(f"SemanticMemory initialized, loaded={len(self._facts)}")

    def _init_file_path(self) -> None:
        try:
            from ...core.paths import get_user_data_dir
            d = get_user_data_dir() / "memory" / "semantic"
            d.mkdir(parents=True, exist_ok=True)
            self._file_path = d / f"{self._skill_id}_facts.jsonl"
        except Exception:
            self._file_path = None

    def _load_from_disk(self) -> None:
        if not self._file_path or not self._file_path.exists():
            return
        try:
            for line in self._file_path.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    fact = SemanticFact(
                        subject=data["subject"],
                        predicate=data["predicate"],
                        object=data["object"],
                        confidence=data.get("confidence", 1.0),
                        created_at=data.get("created_at", 0),
                    )
                    fact_id = fact.get_id()
                    self._facts[fact_id] = fact
                    for entity in (fact.subject, fact.object):
                        self._entity_index.setdefault(entity, set()).add(fact_id)
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Failed to load semantic memory: {e}")

    def _save_to_disk(self) -> None:
        if not self._file_path:
            return
        try:
            lines = []
            for fact in self._facts.values():
                lines.append(json.dumps({
                    "subject": fact.subject, "predicate": fact.predicate,
                    "object": fact.object, "confidence": fact.confidence,
                    "created_at": fact.created_at,
                }, ensure_ascii=False))
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            self._file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save semantic memory: {e}")
    
    async def store(
        self,
        subject: str,
        predicate: str,
        object: str,
        confidence: float = 1.0,
    ) -> str:
        """
        存入语义事实
        
        如果已存在，提升置信度（边际递增）
        
        Args:
            subject: 主体（如 "用户"）
            predicate: 谓词（如 "偏好"）
            object: 客体（如 "代码示例"）
            confidence: 初始置信度
        
        Returns:
            事实 ID
        """
        fact = SemanticFact(
            subject=subject,
            predicate=predicate,
            object=object,
            confidence=confidence,
        )
        fact_id = fact.get_id()
        
        # 已存在：提升置信度
        if fact_id in self._facts:
            old_conf = self._facts[fact_id].confidence
            # 边际递增：每次 +0.1，最多到 1.0
            new_conf = min(1.0, old_conf + 0.1)
            self._facts[fact_id].confidence = new_conf
            
            logger.debug(
                f"Semantic fact confidence updated: "
                f"({subject}, {predicate}, {object}) "
                f"{old_conf:.2f} → {new_conf:.2f}"
            )
            return fact_id
        
        # 新增事实
        self._facts[fact_id] = fact

        # 更新实体索引
        for entity in [subject, object]:
            self._entity_index.setdefault(entity, set()).add(fact_id)

        self._save_to_disk()
        logger.debug(f"Stored semantic fact: ({subject}, {predicate}, {object})")
        return fact_id
    
    async def retrieve(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object: Optional[str] = None,
        top_k: int = 10,
        min_confidence: float = 0.0,
    ) -> List[Tuple[str, str, str, float]]:
        """
        语义检索 - 模式匹配
        
        支持的模式：
        - ("用户", None, None) → 查询关于用户的所有知识
        - (None, "偏好", None) → 查询所有偏好
        - ("用户", "偏好", None) → 查询用户的偏好
        
        Args:
            subject: 主体（None 表示任意）
            predicate: 谓词（None 表示任意）
            object: 客体（None 表示任意）
            top_k: 返回数量上限
            min_confidence: 最小置信度
        
        Returns:
            (subject, predicate, object, confidence) 列表
        """
        # 第一步：召回候选
        candidate_ids: set[str] = set()
        
        if subject and subject in self._entity_index:
            candidate_ids.update(self._entity_index[subject])
        elif object and object in self._entity_index:
            candidate_ids.update(self._entity_index[object])
        else:
            candidate_ids = set(self._facts.keys())
        
        # 第二步：过滤
        results: List[Tuple[str, str, str, float]] = []
        
        for fid in candidate_ids:
            fact = self._facts[fid]
            
            # 谓词匹配
            if predicate and fact.predicate != predicate:
                continue
            
            # 置信度过滤
            if fact.confidence < min_confidence:
                continue
            
            results.append((fact.subject, fact.predicate, fact.object, fact.confidence))
        
        # 按置信度降序排序
        results.sort(key=lambda x: x[3], reverse=True)
        return results[:top_k]
    
    async def query_natural(self, query: str, top_k: int = 5) -> List[Tuple]:
        """
        自然语言查询 - 简单实体匹配
        
        从查询中提取实体，然后检索相关知识
        """
        # 简单分词提取实体
        query_entities = {
            token.strip(".,!?;:\"'()[]{}").lower()
            for token in query.split()
            if len(token) > 1
        }
        
        results: list[Tuple] = []
        
        for entity in query_entities:
            facts = await self.retrieve(subject=entity, top_k=top_k)
            results.extend(facts)
        
        # 去重（按 subject-predicate-object）
        seen = set()
        unique_results = []
        for r in results:
            key = (r[0], r[1], r[2])
            if key not in seen:
                seen.add(key)
                unique_results.append(r)
        
        return unique_results[:top_k]
    
    async def decay_all(self, decay_factor: float = 0.99) -> None:
        """
        全系统置信度衰减
        
        模拟人类的知识遗忘：很久不复习会逐渐不确信
        （但永远不会完全忘记
        
        Args:
            decay_factor: 衰减因子（0-1），默认 0.99，每次衰减 1%
        """
        decayed_count = 0
        for fact in self._facts.values():
            old_conf = fact.confidence
            # 衰减，但不低于 0.1
            fact.confidence = max(0.1, fact.confidence * decay_factor)
            if old_conf != fact.confidence:
                decayed_count += 1
        
        if decayed_count > 0:
            logger.debug(f"Decayed confidence for {decayed_count} semantic facts")
    
    async def forget_low_confidence(self, threshold: float = 0.2) -> int:
        """
        遗忘置信度过低的事实
        
        Args:
            threshold: 遗忘阈值
        
        Returns:
            被遗忘的事实数量
        """
        to_remove = [
            fid
            for fid, fact in self._facts.items()
            if fact.confidence < threshold
        ]
        
        for fid in to_remove:
            fact = self._facts[fid]
            # 从实体索引中移除
            for entity in [fact.subject, fact.object]:
                if entity in self._entity_index:
                    self._entity_index[entity].discard(fid)
                    if not self._entity_index[entity]:
                        del self._entity_index[entity]
            # 删除事实
            del self._facts[fid]
        
        if to_remove:
            logger.debug(f"Forgot {len(to_remove)} low confidence semantic facts")
        
        return len(to_remove)
    
    def get_entities(self) -> List[str]:
        """获取所有已知实体"""
        return sorted(self._entity_index.keys())
    
    def get_entity_facts(self, entity: str) -> List[Tuple]:
        """获取与某实体相关的所有事实"""
        if entity not in self._entity_index:
            return []
        
        results = []
        for fid in self._entity_index[entity]:
            fact = self._facts[fid]
            results.append((fact.subject, fact.predicate, fact.object, fact.confidence))
        
        results.sort(key=lambda x: x[3], reverse=True)
        return results
    
    def __len__(self) -> int:
        return len(self._facts)
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        avg_conf = 0.0
        if self._facts:
            avg_conf = sum(f.confidence for f in self._facts.values()) / len(self._facts)
        
        return {
            "total_facts": len(self._facts),
            "total_entities": len(self._entity_index),
            "average_confidence": avg_conf,
        }
    
    def __repr__(self) -> str:
        stats = self.get_stats()
        return (
            f"SemanticMemory(facts={stats['total_facts']}, "
            f"entities={stats['total_entities']}, "
            f"avg_conf={stats['average_confidence']:.2f})"
        )
