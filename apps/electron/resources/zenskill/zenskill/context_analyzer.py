"""
对话上下文分析引擎 (Phase 10I)

从 Claude Code 对话历史中实时分析：
- 意图分类 (debug/build/refactor/explore)
- 话题追踪 (连续消息主题聚类)
- 疲劳/情绪检测 (消息长度变化/错误频率)
- 上下文预加载建议

集成点：
- PerceptionEngine.evaluate() → conversation 维度
- CLI: zenskill perceive context
"""

import json
import math
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── 意图关键词 ──

INTENT_PATTERNS: Dict[str, List[str]] = {
    "debug": ["fix", "bug", "修复", "错误", "crash", "崩溃", "debug", "调试",
              "fail", "失败", "error", "exception", "issue", "问题", "不对",
              "报错", "坏了", "不工作"],
    "build": ["create", "build", "实现", "新建", "添加", "add", "implement",
              "feat", "feature", "新增", "开发", "写一个", "实现一个"],
    "refactor": ["refactor", "重构", "重写", "rewrite", "optimize", "优化",
                 "improve", "clean", "simplify", "整理", "改进"],
    "explore": ["explore", "探索", "了解", "查看", "检查", "check", "look",
                "find", "search", "搜索", "怎么", "如何", "什么是", "解释"],
    "plan": ["plan", "计划", "设计", "design", "architect", "架构", "规划",
             "方案", "思路", "怎么设计"],
    "config": ["config", "配置", "setup", "安装", "install", "设置", "环境"],
    "review": ["review", "审查", "code review", "audit", "检查代码", "评审"],
    "learn": ["learn", "学习", "教程", "tutorial", "文档", "documentation",
              "guide", "指南", "入门", "基础"],
}

# ── 领域关键词（用于话题聚类） ──

DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "frontend": ["react", "vue", "angular", "css", "html", "javascript",
                 "typescript", "ui", "组件", "页面", "样式"],
    "backend": ["api", "fastapi", "flask", "django", "spring", "redis",
                "postgres", "mysql", "mongodb", "数据库", "接口"],
    "devops": ["docker", "kubernetes", "ci", "cd", "deploy", "部署",
               "nginx", "aws", "cloud", "云服务"],
    "data": ["pandas", "spark", "etl", "数据", "分析", "pipeline",
             "numpy", "dataframe", "dataset", "数据集"],
    "ai_ml": ["llm", "gpt", "claude", "model", "prompt", "agent",
              "机器学习", "深度学习", "训练", "推理"],
    "cli_tui": ["cli", "tui", "textual", "terminal", "命令行", "终端",
                "bash", "shell", "脚本"],
}

# ── 疲劳信号阈值 ──
FATIGUE_MSG_LENGTH_DROP = 0.5      # 消息长度下降 50% 视为疲劳信号
FATIGUE_ERROR_RATE_THRESHOLD = 0.2 # 错误率超 20%
FATIGUE_SHORT_MSG_THRESHOLD = 20   # 消息 < 20 字符视为过短


class ConversationContextAnalyzer:
    """
    对话上下文分析器

    读取 Claude Code history.jsonl，分析最近的对话上下文：
    - 当前意图 (最近 3 条消息)
    - 当前话题 (滑动窗口主题聚类)
    - 疲劳度评估
    - 上下文预加载建议
    """

    def __init__(self):
        self._history_file = Path.home() / ".claude" / "history.jsonl"

    # ── 公开 API ──

    def analyze(self, window: int = 10) -> Dict[str, Any]:
        """
        分析最近 N 条消息的对话上下文

        Args:
            window: 分析窗口（最近 N 条消息）

        Returns:
            {
                "intent": 当前主导意图,
                "intent_distribution": {意图: 次数},
                "topic": 当前话题标签,
                "topic_keywords": [关键词列表],
                "topic_domain": 所属领域,
                "fatigue": 疲劳度评分 (0-100),
                "fatigue_signals": [疲劳信号列表],
                "message_count": 总消息数,
                "session_count": 会话数,
                "context_preloads": [上下文预加载建议],
                "analyzed_at": 分析时间戳,
            }
        """
        history = self._load_history()
        if not history:
            return self._empty_result()

        recent = history[-window:]

        # 意图分析
        intents = self._classify_intents(recent)
        dominant_intent = max(intents, key=intents.get) if intents else "unknown"

        # 话题追踪
        topic_info = self._track_topic(recent)

        # 疲劳检测
        fatigue = self._detect_fatigue(recent, history)

        # 上下文预加载建议
        preloads = self._suggest_preloads(dominant_intent, topic_info, fatigue)

        return {
            "intent": dominant_intent,
            "intent_distribution": intents,
            "topic": topic_info["topic"],
            "topic_keywords": topic_info["keywords"],
            "topic_domain": topic_info["domain"],
            "fatigue": fatigue["score"],
            "fatigue_signals": fatigue["signals"],
            "message_count": len(history),
            "session_count": self._count_sessions(history),
            "context_preloads": preloads,
            "analyzed_at": time.time(),
        }

    def context_alerts(self, window: int = 10) -> List[Dict]:
        """
        生成可供 PerceptionEngine 使用的上下文告警

        Returns:
            [{"id", "severity", "message", "source"}, ...]
        """
        analysis = self.analyze(window)
        alerts = []

        # 疲劳告警
        fatigue_score = analysis.get("fatigue", 0)
        if fatigue_score >= 70:
            alerts.append({
                "id": "ctx-fatigue-high",
                "severity": "high",
                "message": f"对话疲劳度 {fatigue_score}/100 — 建议休息或切换任务",
                "source": "context-analyzer",
            })
        elif fatigue_score >= 50:
            alerts.append({
                "id": "ctx-fatigue-medium",
                "severity": "medium",
                "message": f"对话疲劳度 {fatigue_score}/100 — 注意工作效率",
                "source": "context-analyzer",
            })

        # 意图单一告警
        intent_dist = analysis.get("intent_distribution", {})
        dominant = analysis.get("intent", "")
        if len(intent_dist) <= 1 and dominant not in ("unknown",) and analysis.get("message_count", 0) >= 5:
            alerts.append({
                "id": "ctx-single-intent",
                "severity": "low",
                "message": f"当前会话主要集中在「{dominant}」— 可尝试其他类型任务",
                "source": "context-analyzer",
            })

        # 话题切换频繁告警
        fatigue_signals = analysis.get("fatigue_signals", [])
        if "frequent_topic_switches" in str(fatigue_signals):
            alerts.append({
                "id": "ctx-topic-switch",
                "severity": "low",
                "message": "话题切换频繁 — 建议聚焦当前任务",
                "source": "context-analyzer",
            })

        return alerts

    def context_preload_hint(self, window: int = 10) -> Optional[str]:
        """
        生成上下文预加载提示（一句话）

        Returns:
            "你可能需要查阅之前的 XX 讨论" 或 None
        """
        analysis = self.analyze(window)
        preloads = analysis.get("context_preloads", [])
        if preloads:
            return preloads[0]
        return None

    # ── 数据加载 ──

    def _load_history(self) -> List[Dict]:
        """加载 Claude Code 对话历史"""
        entries = []
        if not self._history_file.exists():
            return entries
        for line in open(self._history_file, encoding="utf-8"):
            try:
                entries.append(json.loads(line.strip()))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        return entries

    # ── 意图分类 ──

    def _classify_intents(self, messages: List[Dict]) -> Dict[str, int]:
        """
        对最近消息进行意图分类计数

        Returns:
            {"debug": 3, "build": 1, ...}
        """
        counts: Counter = Counter()
        for msg in messages:
            display = msg.get("display", "") or msg.get("user_input", "") or ""
            text = str(display)
            if not text:
                continue

            # 斜杠命令优先
            if text.startswith("/"):
                cmd = text.split()[0][1:].lower()
                if cmd in ("fix", "doctor", "debug"):
                    counts["debug"] += 1
                elif cmd in ("plan", "agents"):
                    counts["plan"] += 1
                elif cmd in ("commit", "pr"):
                    counts["review"] += 1
                continue

            text_lower = text.lower()
            best_intent = "explore"
            best_score = 0

            for intent, keywords in INTENT_PATTERNS.items():
                score = sum(1 for kw in keywords if kw in text_lower)
                if score > best_score:
                    best_score = score
                    best_intent = intent

            counts[best_intent] += 1

        return dict(counts)

    # ── 话题追踪 ──

    def _track_topic(self, messages: List[Dict]) -> Dict[str, Any]:
        """
        话题追踪：从最近消息中提取主题关键词并聚类

        Returns:
            {"topic": "话题标签", "keywords": [...], "domain": "所属领域"}
        """
        all_text = []
        for msg in messages:
            display = msg.get("display", "") or msg.get("user_input", "") or ""
            all_text.append(str(display))

        # 提取关键词（按词频 + 长度过滤）
        words: Counter = Counter()
        for text in all_text:
            # 中文/英文分词
            tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
            words.update(tokens)

        # 过滤停用词
        stopwords = {"the", "this", "that", "and", "for", "with", "from",
                     "how", "what", "why", "can", "get", "use", "using",
                     "need", "want", "like", "just", "not", "一个", "这个",
                     "那个", "什么", "怎么", "可以", "需要", "使用"}
        keywords = [w for w in words if w not in stopwords]
        top_keywords = [w for w, _ in Counter(keywords).most_common(5)]

        # 领域匹配
        domain = self._match_domain(top_keywords)

        # 生成话题标签
        topic = self._generate_topic_label(top_keywords, domain)

        return {
            "topic": topic,
            "keywords": top_keywords,
            "domain": domain,
        }

    def _match_domain(self, keywords: List[str]) -> str:
        """从关键词匹配领域"""
        domain_scores: Counter = Counter()
        for kw in keywords:
            for domain, domain_kws in DOMAIN_KEYWORDS.items():
                if kw in domain_kws:
                    domain_scores[domain] += 2
                # 部分匹配
                if any(dk in kw for dk in domain_kws):
                    domain_scores[domain] += 1

        if domain_scores:
            return domain_scores.most_common(1)[0][0]
        return "通用"

    def _generate_topic_label(self, keywords: List[str], domain: str) -> str:
        """生成可读的话题标签"""
        if not keywords:
            return "未识别话题"

        if domain != "通用":
            return f"{domain} — {keywords[0]}" if keywords else domain

        # 从意图推测
        return keywords[0] if keywords else "通用"

    # ── 疲劳检测 ──

    def _detect_fatigue(self, recent: List[Dict],
                        full_history: List[Dict]) -> Dict[str, Any]:
        """
        疲劳检测：消息长度变化 + 错误频率 + 话题切换

        Returns:
            {"score": 0-100, "signals": [信号列表]}
        """
        signals = []
        score = 0

        if len(recent) < 3:
            return {"score": 0, "signals": []}

        # 信号1: 消息长度骤降
        lengths = []
        for msg in recent:
            display = msg.get("display", "") or msg.get("user_input", "") or ""
            lengths.append(len(str(display)))

        if len(lengths) >= 3:
            recent_avg = sum(lengths[-3:]) / 3
            older_avg = sum(lengths[:3]) / 3
            if older_avg > 20 and recent_avg < older_avg * FATIGUE_MSG_LENGTH_DROP:
                signals.append("message_length_drop")
                score += 30

        # 信号2: 短消息比例
        short_count = sum(1 for l in lengths if l < FATIGUE_SHORT_MSG_THRESHOLD)
        if len(lengths) > 2 and short_count / len(lengths) > 0.5:
            signals.append("high_short_message_ratio")
            score += 20

        # 信号3: 错误/失败关键词频率
        error_count = 0
        for msg in recent:
            display = str(msg.get("display", "") or "")
            if any(kw in display.lower() for kw in ("fail", "error", "❌", "失败", "报错", "不对")):
                error_count += 1

        error_rate = error_count / len(recent)
        if error_rate >= FATIGUE_ERROR_RATE_THRESHOLD:
            signals.append(f"high_error_rate_{error_rate:.0%}")
            score += int(error_rate * 100)

        # 信号4: 话题切换检测
        topics_seen = set()
        for msg in recent:
            display = str(msg.get("display", "") or "")
            tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]{2,}", display.lower())
            for token in tokens:
                for domain_kws in DOMAIN_KEYWORDS.values():
                    if token in domain_kws:
                        topics_seen.add(token)
                        break

        if len(topics_seen) >= 4:
            signals.append("frequent_topic_switches")
            score += 15

        # 信号5: 连续对话时长估算
        timestamps = []
        for msg in recent:
            ts = msg.get("timestamp", 0)
            if ts:
                try:
                    timestamps.append(float(ts))
                except (ValueError, TypeError):
                    pass
        if timestamps and len(timestamps) >= 2:
            duration_hours = (timestamps[-1] - timestamps[0]) / 3600
            if duration_hours > 2:
                signals.append(f"long_session_{duration_hours:.1f}h")
                score += min(25, int(duration_hours * 10))

        return {
            "score": min(100, score),
            "signals": signals,
        }

    # ── 上下文预加载建议 ──

    def _suggest_preloads(self, intent: str, topic_info: Dict[str, Any],
                          fatigue: Dict[str, Any]) -> List[str]:
        """
        基于当前上下文生成预加载建议

        Returns:
            ["建议1", "建议2", ...]
        """
        suggestions = []

        # 基于意图的建议
        intent_suggestions = {
            "debug": "当前在调试，可能需要查阅之前的错误记录或相关 issue",
            "build": "正在构建新功能，建议参考类似模块的设计模式",
            "refactor": "重构中，建议先查看代码的测试覆盖率和相关依赖",
            "explore": "探索阶段，建议了解相关模块的架构文档和已有接口",
            "learn": "学习阶段，建议查看官方文档和最佳实践示例",
        }
        if intent in intent_suggestions:
            suggestions.append(intent_suggestions[intent])

        # 基于话题的建议
        domain = topic_info.get("domain", "")
        if domain and domain != "通用":
            suggestions.append(f"当前话题涉及「{domain}」领域，可查阅之前的 {domain} 相关讨论")

        # 基于疲劳度的建议
        fatigue_score = fatigue.get("score", 0)
        if fatigue_score >= 50:
            suggestions.append("检测到疲劳信号，建议暂停休息或切换到不同类型的任务")

        # 限制最多 3 条
        return suggestions[:3]

    # ── 辅助方法 ──

    def _count_sessions(self, history: List[Dict]) -> int:
        """估算会话数"""
        sids = set()
        for entry in history:
            sid = entry.get("sessionId", "")
            if sid:
                sids.add(sid)
        return len(sids) if sids else 1

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "intent": "unknown",
            "intent_distribution": {},
            "topic": "none",
            "topic_keywords": [],
            "topic_domain": "通用",
            "fatigue": 0,
            "fatigue_signals": [],
            "message_count": 0,
            "session_count": 0,
            "context_preloads": [],
            "analyzed_at": time.time(),
        }
