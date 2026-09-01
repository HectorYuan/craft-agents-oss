"""
跨会话记忆关联引擎 (Phase 10J)

将不同 session 的知识自动连接成知识网络：
- 多 session 记忆图谱自动更新
- 跨会话话题关联（相似内容自动链接）
- "3 天前你讨论过类似问题"智能提醒
- 知识网络可视化（按主题/按时间/按项目）

数据存储：
- ~/.zenskill/memory/sessions/sessions_index.json  — 会话索引
- ~/.zenskill/memory/sessions/topic_clusters.json  — 话题聚类
- ~/.zenskill/memory/sessions/session_links.jsonl  — 跨会话链接
"""

import json
import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ── 数据模型 ──

@dataclass
class SessionRecord:
    """单个会话记录"""
    session_id: str
    project: str
    started_at: float
    ended_at: float
    tool_count: int
    message_count: int
    top_intent: str
    top_domain: str
    keywords: List[str]
    summary: str

    @property
    def duration_min(self) -> float:
        return (self.ended_at - self.started_at) / 60

    @property
    def date_str(self) -> str:
        return datetime.fromtimestamp(self.started_at).strftime("%Y-%m-%d")


@dataclass
class TopicCluster:
    """话题聚类"""
    topic_id: str
    label: str
    keywords: List[str]
    domain: str
    session_ids: List[str]
    first_seen: float
    last_seen: float
    mention_count: int
    related_clusters: List[str]  # cluster_id list


@dataclass
class SessionLink:
    """跨会话链接"""
    link_id: str
    source_session: str
    target_session: str
    similarity: float
    matched_keywords: List[str]
    link_type: str  # "topic_recurrence" | "project_continuation" | "tool_pattern"
    linked_at: float


class CrossSessionMemory:
    """
    跨会话记忆关联引擎

    核心功能：
    1. 扫描 Claude Code history.jsonl，提取所有 session
    2. 为每个 session 生成摘要（意图 + 话题 + 关键词）
    3. 跨 session 话题聚类（相似内容自动合并）
    4. 检测 session 之间的链接（话题重复/项目延续/工具模式）
    5. 生成智能提醒（"3 天前你讨论过类似问题"）
    """

    def __init__(self):
        self._history_file = Path.home() / ".claude" / "history.jsonl"
        self._data_dir = Path.home() / ".zenskill" / "memory" / "sessions"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self._data_dir / "sessions_index.json"
        self._clusters_file = self._data_dir / "topic_clusters.json"
        self._links_file = self._data_dir / "session_links.jsonl"

    # ── 公开 API ──

    def build_index(self, force: bool = False) -> Dict[str, Any]:
        """
        构建完整的跨会话记忆索引

        1. 扫描历史 → 提取所有 session
        2. 为每个 session 生成摘要
        3. 话题聚类
        4. 建立跨会话链接

        Returns:
            {"sessions": n, "clusters": n, "links": n, "projects": [p1, p2, ...]}
        """
        sessions = self._extract_sessions()
        if not sessions:
            return {"sessions": 0, "clusters": 0, "links": 0, "projects": []}

        # 话题聚类
        clusters = self._cluster_topics(sessions)

        # 跨会话链接
        links = self._build_links(sessions, clusters)

        # 持久化
        self._save_index(sessions)
        self._save_clusters(clusters)
        self._save_links(links)

        projects = sorted(set(s.project for s in sessions))

        return {
            "sessions": len(sessions),
            "clusters": len(clusters),
            "links": len(links),
            "projects": projects,
            "built_at": time.time(),
        }

    def get_related_sessions(self, session_id: str, top_k: int = 5) -> List[Dict]:
        """
        获取与指定 session 最相关的其他 session

        Args:
            session_id: 会话 ID
            top_k: 返回数量

        Returns:
            [{"session_id", "similarity", "matched_keywords", "date", "summary"}, ...]
        """
        sessions = self._load_index()
        links = self._load_links()

        related = []
        for link in links:
            if link.source_session == session_id:
                target = sessions.get(link.target_session)
                if target:
                    related.append({
                        "session_id": link.target_session,
                        "similarity": link.similarity,
                        "matched_keywords": link.matched_keywords,
                        "date": target.date_str if hasattr(target, 'date_str') else "",
                        "summary": target.summary if hasattr(target, 'summary') else "",
                        "link_type": link.link_type,
                    })
            elif link.target_session == session_id:
                source = sessions.get(link.source_session)
                if source:
                    related.append({
                        "session_id": link.source_session,
                        "similarity": link.similarity,
                        "matched_keywords": link.matched_keywords,
                        "date": source.date_str if hasattr(source, 'date_str') else "",
                        "summary": source.summary if hasattr(source, 'summary') else "",
                        "link_type": link.link_type,
                    })

        related.sort(key=lambda x: x["similarity"], reverse=True)
        return related[:top_k]

    def get_reminders(self, window_days: int = 7) -> List[Dict]:
        """
        获取跨会话智能提醒

        Args:
            window_days: 回顾窗口（最近 N 天）

        Returns:
            [{"type", "message", "session_ids", "date"}, ...]
        """
        sessions = self._load_index()
        clusters = self._load_clusters()
        if not sessions or not clusters:
            return []

        now = time.time()
        cutoff = now - (window_days * 86400)
        reminders = []

        # 提醒 1: 在过去 window_days 内，某话题曾被讨论过
        session_list = list(sessions.values())
        recent_sessions = [s for s in session_list if s.started_at >= cutoff]

        # 按话题分组
        topic_sessions: Dict[str, List[SessionRecord]] = defaultdict(list)
        for cluster in clusters:
            for sid in cluster.session_ids:
                session = sessions.get(sid)
                if session and session.started_at >= cutoff:
                    topic_sessions[cluster.label].append(session)

        for label, ss in topic_sessions.items():
            if len(ss) >= 2:
                dates = [s.date_str for s in sorted(ss, key=lambda x: x.started_at)]
                reminders.append({
                    "type": "topic_recurrence",
                    "message": f"最近讨论了「{label}」{len(ss)} 次 ({', '.join(dates)})",
                    "session_ids": [s.session_id for s in ss],
                    "count": len(ss),
                })

        # 提醒 2: 3 天前的相似话题
        three_days_ago = now - (3 * 86400)
        for cluster in clusters:
            recent_in_cluster = [s for s in cluster.session_ids
                                 if sessions.get(s) and sessions[s].started_at >= three_days_ago]
            older_in_cluster = [s for s in cluster.session_ids
                                if sessions.get(s) and sessions[s].started_at < three_days_ago]
            if recent_in_cluster and older_in_cluster:
                oldest = min(sessions[s] for s in older_in_cluster)
                reminders.append({
                    "type": "past_topic",
                    "message": f"之前 ({oldest.date_str}) 讨论过类似「{cluster.label}」的话题，可查阅相关记忆",
                    "session_ids": [oldest.session_id],
                    "date": oldest.date_str,
                })

        return reminders

    def search_sessions(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        跨会话搜索

        Args:
            query: 搜索关键词
            top_k: 返回数量

        Returns:
            [{"session_id", "summary", "date", "score"}, ...]
        """
        sessions = self._load_index()
        if not sessions:
            return []

        query_lower = query.lower()
        query_tokens = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]{2,}", query_lower))

        scored = []
        for sid, s in sessions.items():
            if not s:
                continue
            score = 0.0
            # 关键词匹配
            for kw in s.keywords:
                if kw.lower() in query_lower:
                    score += 0.3
            # 摘要匹配
            if query_lower in s.summary.lower():
                score += 0.4
            # 意图匹配
            if s.top_intent and s.top_intent.lower() in query_lower:
                score += 0.2

            if score > 0:
                scored.append({
                    "session_id": sid,
                    "summary": s.summary[:100],
                    "date": s.date_str,
                    "project": s.project,
                    "top_intent": s.top_intent,
                    "score": round(score, 2),
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        self._recall_episode(query, "search", len(scored))
        return scored[:top_k]

    def get_knowledge_network(self) -> Dict[str, Any]:
        """
        生成知识网络数据（用于可视化）

        Returns:
            {
                "nodes": [{"id", "label", "type", "size"}, ...],
                "edges": [{"source", "target", "weight", "type"}, ...],
            }
        """
        sessions = self._load_index()
        clusters = self._load_clusters()
        links = self._load_links()

        nodes = []
        edges = []

        # 会话节点
        for sid, s in sessions.items():
            nodes.append({
                "id": sid,
                "label": s.date_str,
                "type": "session",
                "size": min(30, s.message_count),
                "project": s.project,
                "top_intent": s.top_intent,
            })

        # 话题节点
        for cluster in clusters:
            cluster_id = f"cluster:{cluster.topic_id}"
            nodes.append({
                "id": cluster_id,
                "label": cluster.label,
                "type": "topic",
                "size": min(20, cluster.mention_count * 3),
                "domain": cluster.domain,
            })
            # 话题 → 会话边
            for sid in cluster.session_ids:
                edges.append({
                    "source": cluster_id,
                    "target": sid,
                    "weight": 1.0,
                    "type": "belongs_to",
                })

        # 跨会话链接边
        for link in links:
            if link.similarity > 0.3:
                edges.append({
                    "source": link.source_session,
                    "target": link.target_session,
                    "weight": round(link.similarity, 2),
                    "type": link.link_type,
                })

        return {"nodes": nodes, "edges": edges}

    # ── 内部方法 ──

    def _extract_sessions(self) -> List[SessionRecord]:
        """从 history.jsonl 提取所有 session"""
        if not self._history_file.exists():
            return []

        entries = []
        for line in open(self._history_file, encoding="utf-8"):
            try:
                entries.append(json.loads(line.strip()))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        # 按 sessionId 分组
        session_groups: Dict[str, List[Dict]] = defaultdict(list)
        for e in entries:
            sid = e.get("sessionId", "")
            if sid:
                session_groups[sid].append(e)

        sessions = []
        for sid, group in session_groups.items():
            if len(group) < 2:
                continue

            timestamps = [e.get("timestamp", 0) for e in group if e.get("timestamp")]
            timestamps = [float(t) for t in timestamps if t]

            if not timestamps:
                continue

            started_at = min(timestamps)
            ended_at = max(timestamps)

            # 提取所有文本
            all_text = " ".join(str(e.get("display", "") or "") for e in group)

            # 意图分类
            intents = self._classify_intents(all_text)
            top_intent = max(intents, key=intents.get) if intents else "unknown"

            # 关键词提取
            keywords = self._extract_keywords(all_text)
            top_keywords = [k for k, _ in Counter(keywords).most_common(5)]

            # 领域检测
            domain = self._detect_domain(top_keywords)

            # 项目名
            projects = set()
            for e in group:
                p = Path(e.get("project", "")).name or ""
                if p:
                    projects.add(p)
            project = ", ".join(sorted(projects)) if projects else "unknown"

            # 摘要
            summary = self._generate_summary(all_text, top_intent, top_keywords)

            sessions.append(SessionRecord(
                session_id=sid,
                project=project,
                started_at=started_at,
                ended_at=ended_at,
                tool_count=len(group),
                message_count=len(group),
                top_intent=top_intent,
                top_domain=domain,
                keywords=top_keywords,
                summary=summary,
            ))

        return sessions

    # ── NLP 辅助 ──

    INTENT_PATTERNS = {
        "debug": ["fix", "bug", "修复", "error", "crash", "debug", "fail", "问题", "不对"],
        "build": ["create", "build", "实现", "新建", "add", "implement", "feat", "新增"],
        "refactor": ["refactor", "重构", "优化", "rewrite", "improve", "clean"],
        "explore": ["explore", "探索", "了解", "怎么", "如何", "什么是", "解释"],
        "plan": ["plan", "计划", "设计", "design", "方案", "架构"],
        "config": ["config", "配置", "setup", "安装", "install", "设置"],
        "review": ["review", "审查", "code review", "audit", "测试"],
    }

    DOMAIN_KEYWORDS = {
        "frontend": ["react", "vue", "css", "html", "javascript", "typescript", "ui", "组件"],
        "backend": ["api", "fastapi", "flask", "redis", "postgres", "数据库", "接口", "server"],
        "devops": ["docker", "kubernetes", "ci", "cd", "deploy", "部署", "nginx", "aws"],
        "data": ["pandas", "spark", "etl", "数据", "分析", "numpy", "dataframe", "pipeline"],
        "ai_ml": ["llm", "gpt", "claude", "model", "prompt", "agent", "机器学习"],
        "cli_tui": ["cli", "tui", "textual", "terminal", "命令行", "bash", "shell"],
    }

    def _classify_intents(self, text: str) -> Dict[str, int]:
        text_lower = text.lower()
        counts: Counter = Counter()
        for intent, keywords in self.INTENT_PATTERNS.items():
            for kw in keywords:
                if kw in text_lower:
                    counts[intent] += 1
        if not counts:
            counts["explore"] = 1
        return dict(counts)

    def _extract_keywords(self, text: str) -> List[str]:
        tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
        stopwords = {"the", "this", "that", "and", "for", "with", "from",
                     "how", "what", "why", "can", "get", "use", "just",
                     "一个", "这个", "那个", "什么", "怎么", "可以", "需要"}
        return [t for t in tokens if t not in stopwords and len(t) > 1]

    def _detect_domain(self, keywords: List[str]) -> str:
        scores: Counter = Counter()
        for kw in keywords:
            for domain, dkws in self.DOMAIN_KEYWORDS.items():
                if kw in dkws:
                    scores[domain] += 2
                if any(d in kw for d in dkws):
                    scores[domain] += 1
        return scores.most_common(1)[0][0] if scores else "general"

    def _generate_summary(self, text: str, top_intent: str, keywords: List[str]) -> str:
        intent_labels = {"debug": "调试", "build": "构建", "refactor": "重构",
                         "explore": "探索", "plan": "规划", "config": "配置", "review": "审查"}
        intent_label = intent_labels.get(top_intent, top_intent)
        kw_str = ", ".join(keywords[:3]) if keywords else ""
        if kw_str:
            return f"{intent_label} — {kw_str}"
        return intent_label

    # ── 话题聚类 ──

    def _cluster_topics(self, sessions: List[SessionRecord]) -> List[TopicCluster]:
        """基于关键词相似度对 session 进行话题聚类"""
        if not sessions:
            return []

        clusters: List[TopicCluster] = []
        assigned: Set[str] = set()

        # 按关键词重叠度贪心聚类
        for session in sessions:
            if session.session_id in assigned:
                continue

            cluster_kws = set(session.keywords)
            cluster_sessions = [session.session_id]
            assigned.add(session.session_id)

            # 找同话题相似 session
            for other in sessions:
                if other.session_id in assigned:
                    continue
                overlap = cluster_kws & set(other.keywords)
                if len(overlap) >= 2:
                    cluster_sessions.append(other.session_id)
                    cluster_kws.update(other.keywords)
                    assigned.add(other.session_id)

            top_kws = sorted(cluster_kws, key=lambda k: sum(k in s.summary for s in sessions), reverse=True)[:5]
            label = top_kws[0] if top_kws else "通用"
            domain = self._detect_domain(top_kws)

            cluster_sessions_sorted = sorted(cluster_sessions, key=lambda sid: (
                next((s.started_at for s in sessions if s.session_id == sid), 0)
            ))
            first = next((s.started_at for s in sessions if s.session_id == cluster_sessions_sorted[0]), 0)
            last = next((s.started_at for s in sessions if s.session_id == cluster_sessions_sorted[-1]), 0)

            clusters.append(TopicCluster(
                topic_id=f"tc-{len(clusters) + 1}",
                label=label,
                keywords=top_kws,
                domain=domain,
                session_ids=cluster_sessions_sorted,
                first_seen=first,
                last_seen=last,
                mention_count=len(cluster_sessions),
                related_clusters=[],
            ))

        # 检测集群间关联
        for i, c1 in enumerate(clusters):
            for j, c2 in enumerate(clusters):
                if i >= j:
                    continue
                overlap = set(c1.keywords) & set(c2.keywords)
                if len(overlap) >= 2:
                    c1.related_clusters.append(c2.topic_id)
                    c2.related_clusters.append(c1.topic_id)

        return clusters

    # ── 跨会话链接 ──

    def _build_links(self, sessions: List[SessionRecord],
                     clusters: List[TopicCluster]) -> List[SessionLink]:
        """建立跨会话链接"""
        links = []
        cluster_map = {c.topic_id: c for c in clusters}
        session_map = {s.session_id: s for s in sessions}

        link_id = 0

        # 链接 1: 同一话题集群内的 session 之间
        for cluster in clusters:
            sids = cluster.session_ids
            for i in range(len(sids)):
                for j in range(i + 1, len(sids)):
                    link_id += 1
                    s1 = session_map.get(sids[i])
                    s2 = session_map.get(sids[j])
                    if not s1 or not s2:
                        continue
                    # 时间越近，链接权重越高
                    time_diff = abs(s1.started_at - s2.started_at)
                    time_factor = max(0.3, 1.0 - (time_diff / (30 * 86400)))  # 30天衰减
                    overlap = set(cluster.keywords)
                    similarity = round(min(1.0, len(overlap) / 5 * time_factor), 2)
                    if similarity >= 0.4:
                        links.append(SessionLink(
                            link_id=f"link-{link_id}",
                            source_session=sids[i],
                            target_session=sids[j],
                            similarity=similarity,
                            matched_keywords=list(overlap)[:5],
                            link_type="topic_recurrence",
                            linked_at=time.time(),
                        ))

        # 链接 2: 同项目延续
        project_groups: Dict[str, List[SessionRecord]] = defaultdict(list)
        for s in sessions:
            project_groups[s.project].append(s)
        for proj, ss in project_groups.items():
            if len(ss) < 2 or proj == "unknown":
                continue
            ss.sort(key=lambda x: x.started_at)
            for i in range(len(ss) - 1):
                link_id += 1
                links.append(SessionLink(
                    link_id=f"link-{link_id}",
                    source_session=ss[i].session_id,
                    target_session=ss[i + 1].session_id,
                    similarity=0.6,
                    matched_keywords=[proj],
                    link_type="project_continuation",
                    linked_at=time.time(),
                ))

        return links

    # ── 持久化 ──

    def _save_index(self, sessions: List[SessionRecord]) -> None:
        try:
            data = {s.session_id: asdict(s) for s in sessions}
            self._index_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _load_index(self) -> Dict[str, SessionRecord]:
        if not self._index_file.exists():
            return {}
        try:
            data = json.loads(self._index_file.read_text(encoding="utf-8"))
            return {k: SessionRecord(**v) for k, v in data.items()}
        except Exception:
            return {}

    def _save_clusters(self, clusters: List[TopicCluster]) -> None:
        try:
            data = [asdict(c) for c in clusters]
            self._clusters_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _load_clusters(self) -> List[TopicCluster]:
        if not self._clusters_file.exists():
            return []
        try:
            data = json.loads(self._clusters_file.read_text(encoding="utf-8"))
            return [TopicCluster(**d) for d in data]
        except Exception:
            return []

    def _save_links(self, links: List[SessionLink]) -> None:
        try:
            lines = [json.dumps(asdict(l), ensure_ascii=False) for l in links]
            self._links_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            pass

    def _load_links(self) -> List[SessionLink]:
        if not self._links_file.exists():
            return []
        links = []
        try:
            for line in self._links_file.read_text(encoding="utf-8").strip().split("\n"):
                if line.strip():
                    links.append(SessionLink(**json.loads(line)))
        except Exception:
            pass
        return links

    # ── 情景记忆回访 ──

    def _recall_episode(self, query: str, source: str, result_count: int) -> None:
        """将搜索行为记录到情景记忆"""
        try:
            from .episodic_memory import EpisodicMemory
            from .memory_base import MemoryItem
            import uuid

            mem = EpisodicMemory()
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(mem.store(MemoryItem(
                    id=f"search-{uuid.uuid4().hex[:8]}",
                    content=f"跨会话搜索: {query} → {result_count} 条结果",
                    importance=0.4,
                    tags={"cross-session", source},
                    metadata={"query": query, "source": source, "count": result_count},
                )))
            except RuntimeError:
                pass
        except Exception:
            pass
