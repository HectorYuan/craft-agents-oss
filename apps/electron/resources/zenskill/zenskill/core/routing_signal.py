"""路由信号源协议与内置实现 (PROP-20260712-089)

定义 RoutingSignalProvider Protocol，提供可插拔的路由信号源。
内置 3 个信号源：关键词、语义、历史。

用法:
    from zenskill.core.routing_signal import (
        RoutingSignalProvider,
        KeywordRoutingSignal,
        SemanticRoutingSignal,
        HistoryRoutingSignal,
    )

    # 注册信号源
    signal = KeywordRoutingSignal(weight=0.3)
    score = signal.score("分析数据", context)
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

from .protocols import RoutingContext


@runtime_checkable
class RoutingSignalProvider(Protocol):
    """路由信号源协议

    每个信号源返回 (signal_name, confidence) 对，
    confidence 范围 0.0-1.0。
    """

    @property
    def signal_name(self) -> str:
        """信号源名称"""
        ...

    @property
    def weight(self) -> float:
        """权重（0.0-1.0，用于融合时的加权）"""
        ...

    def score(self, task: str, context: Optional[RoutingContext] = None) -> float:
        """评估任务得分

        Args:
            task: 任务描述
            context: 路由上下文

        Returns:
            置信度 0.0-1.0
        """
        ...


@dataclass
class SignalScore:
    """信号评分结果"""
    signal_name: str
    raw_score: float
    weighted_score: float
    weight: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_name": self.signal_name,
            "raw_score": round(self.raw_score, 4),
            "weighted_score": round(self.weighted_score, 4),
            "weight": self.weight,
        }


# ═══════════════════════════════════════════════════════════════
# 内置信号源
# ═══════════════════════════════════════════════════════════════

class KeywordRoutingSignal:
    """关键词路由信号源

    基于关键词匹配评分，复用 SkillRouter 的 keyword_index。
    """

    def __init__(self, weight: float = 0.3, keyword_index: Optional[Dict[str, List[str]]] = None):
        self._weight = weight
        self._keyword_index = keyword_index or {}

    @property
    def signal_name(self) -> str:
        return "keyword"

    @property
    def weight(self) -> float:
        return self._weight

    def score(self, task: str, context: Optional[RoutingContext] = None) -> float:
        """关键词匹配评分"""
        if not self._keyword_index:
            return 0.0

        task_lower = task.lower()
        matches = 0
        total_keywords = len(self._keyword_index)

        if total_keywords == 0:
            return 0.0

        for keyword in self._keyword_index:
            if keyword.lower() in task_lower:
                matches += 1

        return min(matches / max(total_keywords * 0.1, 1), 1.0)

    def update_index(self, keyword_index: Dict[str, List[str]]) -> None:
        """更新关键词索引"""
        self._keyword_index = keyword_index


class SemanticRoutingSignal:
    """语义路由信号源 (P3-1 升级)

    优先 embedding 语义相似度（sentence-transformers 可选依赖，
    向量缓存到 ~/.zenskill/routing_vectors.db）；模型不可用时
    回退到关键词簇近似（原实现，行为不变）。
    """

    # 语义关键词簇
    _clusters = {
        "analysis": ["分析", "数据", "统计", "报告", "图表", "可视化", "analysis", "data"],
        "creation": ["写", "创建", "生成", "设计", "编写", "创作", "write", "create"],
        "execution": ["执行", "运行", "部署", "安装", "配置", "执行", "run", "deploy"],
        "coordination": ["协调", "调度", "管理", "组织", "规划", "安排", "manage", "plan"],
        "knowledge": ["知识", "文档", "学习", "教程", "指南", "参考", "knowledge", "doc"],
    }

    _VECTOR_DB = Path.home() / ".zenskill" / "routing_vectors.db"
    _MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self, weight: float = 0.3, use_embedding: bool = True):
        self._weight = weight
        self._use_embedding = use_embedding
        self._model: Any = None  # None=未尝试, False=不可用
        self._cluster_vecs: Dict[str, Optional[List[float]]] = {}

    @property
    def signal_name(self) -> str:
        return "semantic"

    @property
    def weight(self) -> float:
        return self._weight

    def _model_cached(self) -> bool:
        """模型是否已在本地 HF 缓存（不触发网络请求的判定）。"""
        hf_home = os.environ.get("HF_HOME") or str(Path.home() / ".cache" / "huggingface")
        hub_cache = os.environ.get("HF_HUB_CACHE") or os.path.join(hf_home, "hub")
        cache_name = "models--" + self._MODEL_NAME.replace("/", "--")
        return (Path(hub_cache) / cache_name).is_dir()

    def _ensure_model(self) -> Any:
        if self._model is None:
            if not self._use_embedding:
                self._model = False
            elif (
                not self._model_cached()
                and os.environ.get("ZENSKILL_EMBED_DOWNLOAD", "").lower() not in ("1", "true", "yes")
            ):
                # 模型未缓存时不自动在线下载：受限网络下 huggingface 下载会无限
                # 挂起（TCP SYN_SENT 无超时），直接走关键词簇回退；首次下载需
                # 显式 ZENSKILL_EMBED_DOWNLOAD=1
                self._model = False
            else:
                try:
                    from sentence_transformers import SentenceTransformer

                    self._model = SentenceTransformer(
                        self._MODEL_NAME,
                        local_files_only=self._model_cached(),
                    )
                except Exception:
                    self._model = False
        return self._model

    def _cache_get(self, key: str) -> Optional[List[float]]:
        try:
            import sqlite3

            with sqlite3.connect(self._VECTOR_DB) as conn:
                row = conn.execute(
                    "SELECT vector FROM embeddings WHERE hash = ?", (key,)
                ).fetchone()
            if row:
                return json.loads(row[0])
        except Exception:
            pass
        return None

    def _cache_put(self, key: str, vector: List[float]) -> None:
        try:
            import sqlite3

            self._VECTOR_DB.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self._VECTOR_DB) as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS embeddings "
                    "(hash TEXT PRIMARY KEY, vector TEXT NOT NULL)"
                )
                conn.execute(
                    "INSERT OR REPLACE INTO embeddings (hash, vector) VALUES (?, ?)",
                    (key, json.dumps(vector)),
                )
        except Exception:
            pass

    def _embed(self, text: str) -> Optional[List[float]]:
        model = self._ensure_model()
        if model is False:
            return None

        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        try:
            vector = [float(x) for x in model.encode(text).tolist()]
        except Exception:
            return None
        self._cache_put(key, vector)
        return vector

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def _score_embedding(self, task: str) -> Optional[float]:
        """embedding 语义评分；模型不可用返回 None（走关键词簇回退）"""
        task_vec = self._embed(task)
        if task_vec is None:
            return None

        best = -1.0
        for name, keywords in self._clusters.items():
            cluster_vec = self._cluster_vecs.get(name)
            if cluster_vec is None:
                cluster_vec = self._embed(" ".join(keywords))
                self._cluster_vecs[name] = cluster_vec
            if cluster_vec is None:
                return None
            best = max(best, self._cosine(task_vec, cluster_vec))
        return best

    def score(self, task: str, context: Optional[RoutingContext] = None) -> float:
        """语义相似度评分（embedding 优先，关键词簇回退）"""
        if self._use_embedding:
            cos = self._score_embedding(task)
            if cos is not None:
                return max(0.0, min(1.0, cos))

        task_lower = task.lower()
        best_cluster_score = 0.0

        for cluster_name, keywords in self._clusters.items():
            matches = sum(1 for kw in keywords if kw in task_lower)
            if matches > 0:
                cluster_score = matches / len(keywords)
                best_cluster_score = max(best_cluster_score, cluster_score)

        # 如果有 skill_type 上下文，加成匹配
        if context and context.skill_type:
            type_name = context.skill_type.value
            if type_name in self._clusters:
                type_keywords = self._clusters[type_name]
                type_matches = sum(1 for kw in type_keywords if kw in task_lower)
                if type_matches > 0:
                    best_cluster_score = min(best_cluster_score + 0.2, 1.0)

        return best_cluster_score


class HistoryRoutingSignal:
    """历史路由信号源

    基于执行历史记录评分（成功率、使用频率）。
    """

    def __init__(self, weight: float = 0.2, history: Optional[List[Dict[str, Any]]] = None):
        self._weight = weight
        self._history = history or []

    @property
    def signal_name(self) -> str:
        return "history"

    @property
    def weight(self) -> float:
        return self._weight

    def score(self, task: str, context: Optional[RoutingContext] = None) -> float:
        """历史成功率评分"""
        # 合并内置历史和 context 历史
        all_history = list(self._history)
        if context and context.history:
            all_history.extend(context.history)

        if not all_history:
            return 0.5  # 无历史数据时返回中性分数

        # 计算整体成功率
        successes = sum(1 for h in all_history if h.get("success", False))
        return successes / len(all_history)

    def update_history(self, history: List[Dict[str, Any]]) -> None:
        """更新历史记录"""
        self._history = history


class LoadRoutingSignal:
    """系统负载信号源

    基于系统负载评分（负载越低越好）。
    """

    def __init__(self, weight: float = 0.2):
        self._weight = weight

    @property
    def signal_name(self) -> str:
        return "load"

    @property
    def weight(self) -> float:
        return self._weight

    def score(self, task: str, context: Optional[RoutingContext] = None) -> float:
        """负载评分（负载越低分越高）"""
        if not context:
            return 0.5
        # 负载 0.0 → 评分 1.0，负载 1.0 → 评分 0.0
        return 1.0 - context.load_level
