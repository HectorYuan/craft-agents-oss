"""
NLP 信号提取器

从采集信号中提取关键词、领域、意图等语义特征。
轻量级实现：基于关键词匹配，不引入重量级 NLP 库。
"""

import re
from collections import Counter
from typing import Any, Dict, List


class NLPSignalExtractor:
    """轻量 NLP 信号提取"""

    # 技术领域关键词
    DOMAIN_KEYWORDS = {
        "ai_ml": ["llm", "gpt", "claude", "deepseek", "model", "prompt", "agent",
                  "ai", "训练", "推理", "模型", "智能体", "token", "embedding"],
        "backend": ["api", "fastapi", "flask", "django", "redis", "postgres",
                    "mysql", "grpc", "rest", "graphql", "middleware"],
        "devops": ["docker", "kubernetes", "k8s", "ci", "cd", "deploy",
                   "部署", "监控", "日志", "容器"],
        "frontend": ["react", "vue", "typescript", "javascript", "css", "html",
                     "组件", "ui", "web"],
        "data": ["pandas", "numpy", "spark", "etl", "pipeline", "数据", "分析",
                 "可视化", "dashboard"],
        "cli_tui": ["cli", "tui", "textual", "terminal", "命令", "终端", "界面"],
    }

    # 意图模式
    INTENT_PATTERNS = {
        "debug": re.compile(r"fix|bug|修复|错误|报错|crash|崩溃|exception", re.I),
        "build": re.compile(r"create|build|实现|新建|添加|新增|add|implement", re.I),
        "refactor": re.compile(r"refactor|重构|重写|rewrite|优化|improve", re.I),
        "explore": re.compile(r"explore|探索|了解|查看|看看|what|how|怎么|如何", re.I),
        "config": re.compile(r"config|配置|设置|setup|install|安装", re.I),
    }

    def extract(self, events: List[Dict]) -> Dict[str, Any]:
        """从事件列表提取语义信号"""
        all_text = self._collect_text(events)
        words = self._tokenize(all_text)

        return {
            "word_count": len(words),
            "top_keywords": self._extract_keywords(events, top_n=15),
            "domains": self._classify_domains(events),
            "intents": self._detect_intents(events),
            "tech_maturity": self._assess_tech_maturity(events),
        }

    def _collect_text(self, events: List[Dict]) -> str:
        """收集事件中的所有文本信号"""
        parts = []
        for e in events:
            signal = e.get("signal", {})
            # 从各种信号字段收集文本
            for k, v in signal.items():
                if isinstance(v, str):
                    parts.append(v)
                elif isinstance(v, dict):
                    parts.extend(str(vk) for vk in v.keys())
                    parts.extend(str(vv) for vv in v.values() if isinstance(vv, str))
                elif isinstance(v, list):
                    parts.extend(str(item) for item in v if isinstance(item, str))
        return " ".join(parts)

    def _tokenize(self, text: str) -> List[str]:
        """中文+英文混合分词"""
        # 简单分词：按空白和标点分割
        tokens = re.findall(r"[\w一-鿿]+", text.lower())
        return [t for t in tokens if len(t) > 1]

    def _extract_keywords(self, events: List[Dict], top_n: int = 15) -> List[str]:
        """提取高频关键词"""
        all_text = self._collect_text(events)
        words = self._tokenize(all_text)

        # 过滤停用词
        stop_words = {"the", "and", "for", "with", "that", "this", "from",
                      "have", "are", "was", "not", "but", "you", "all", "can",
                      "的", "是", "了", "在", "和", "也", "就", "都", "而", "及"}
        filtered = [w for w in words if w not in stop_words and len(w) > 2]

        counter = Counter(filtered)
        return [w for w, _ in counter.most_common(top_n)]

    def _classify_domains(self, events: List[Dict]) -> Dict[str, float]:
        """分类技术领域"""
        all_text = self._collect_text(events).lower()
        domain_scores: Dict[str, float] = {}

        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in all_text)
            max_score = len(keywords)
            if score > 0:
                domain_scores[domain] = min(score / max_score * 100, 100)

        return domain_scores

    def _detect_intents(self, events: List[Dict]) -> Dict[str, int]:
        """检测用户意图分布"""
        all_text = self._collect_text(events)
        intent_counts: Dict[str, int] = {}

        for intent, pattern in self.INTENT_PATTERNS.items():
            matches = len(pattern.findall(all_text))
            if matches > 0:
                intent_counts[intent] = matches

        return intent_counts

    def _assess_tech_maturity(self, events: List[Dict]) -> str:
        """评估技术成熟度"""
        all_text = self._collect_text(events).lower()
        # 简单启发式：看关键词多样性
        unique_kw = len(set(self._tokenize(all_text)))

        if unique_kw > 500:
            return "advanced"
        elif unique_kw > 200:
            return "intermediate"
        else:
            return "beginner"
