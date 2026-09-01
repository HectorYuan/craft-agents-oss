"""
内容管道 — 文本/URL/文件 → SkillSpec (Phase U3A-C)

7 步管线:
  1. 清洗 (去 HTML/代码块/多余空白)
  2. 标题提取 (## 标题 + 首段)
  3. 概念提取 (TF-IDF 中英文)
  4. 分类推断 (关键词匹配)
  5. 反思生成 (概念模板)
  6. 练习生成 (难度分层)
  7. → SkillSpec + save()

用法:
    from zenskill.skills.content_extractor import ContentToSkillConverter

    converter = ContentToSkillConverter()
    spec = converter.convert_from_text(content, title="My Article")
    spec.save()

    # 从 URL
    spec = converter.convert_from_url("https://example.com/article")
"""

from __future__ import annotations

import logging
import re
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# U3B: TF-IDF 概念提取
# ═══════════════════════════════════════════════════════════════

# 中文停用词
CN_STOP_WORDS: Set[str] = {
    "的", "了", "是", "在", "和", "也", "就", "都", "而", "及",
    "与", "着", "或", "一个", "没有", "我们", "你们", "他们", "她们",
    "这个", "那个", "这些", "那些", "自己", "什么", "哪", "怎么",
    "可以", "因为", "所以", "但是", "如果", "虽然", "然后", "已经",
    "很", "非常", "比较", "更", "最", "太", "还", "又", "再",
    "能", "会", "要", "想", "可能", "应该", "需要", "必须",
    "不", "没", "别", "勿", "未", "从", "到", "让", "把", "被",
    "对", "向", "往", "朝", "沿", "以", "为", "为了",
    "上", "下", "中", "内", "外", "前", "后", "左", "右",
    "这", "那", "每", "各", "某", "该", "其", "本", "之",
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
    "百", "千", "万", "亿",
}

# 英文停用词
EN_STOP_WORDS: Set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "having", "do", "does", "did",
    "doing", "will", "would", "shall", "should", "may", "might",
    "must", "can", "could", "i", "me", "my", "we", "us", "our",
    "you", "your", "he", "him", "his", "she", "her", "it", "its",
    "they", "them", "their", "this", "that", "these", "those",
    "and", "or", "but", "not", "no", "nor", "so", "for", "yet",
    "with", "without", "at", "by", "from", "in", "into", "of",
    "on", "onto", "to", "up", "down", "out", "off", "over",
    "about", "above", "after", "before", "between", "under",
    "all", "any", "both", "each", "few", "more", "most", "other",
    "some", "such", "only", "own", "same", "than", "too", "very",
    "just", "because", "as", "until", "while", "if", "when",
    "where", "how", "what", "which", "who", "whom",
}


def extract_keywords_tfidf(
    text: str,
    top_k: int = 10,
    cn_min_len: int = 2,
    cn_max_len: int = 8,
    en_min_len: int = 3,
) -> List[Tuple[str, float]]:
    """TF-IDF 概念提取 (中英文混合)

    中文: 滑动窗口 (cn_min_len..cn_max_len 字)
    英文: 分词 (en_min_len+ 字母 token)
    去停用词 + 词频排序 → Top K

    Returns:
        [(concept, score), ...] 按分数降序
    """
    # 分离中英文
    cn_text = "".join(re.findall(r'[\u4e00-\u9fff]+', text))
    en_text = " ".join(re.findall(r'[a-zA-Z_][a-zA-Z0-9_-]*', text))

    # 中文 n-gram
    cn_grams: Counter = Counter()
    for window in range(cn_min_len, cn_max_len + 1):
        for i in range(len(cn_text) - window + 1):
            gram = cn_text[i:i + window]
            if gram not in CN_STOP_WORDS:
                cn_grams[gram] += 1

    # 英文 token
    en_tokens: Counter = Counter()
    for token in en_text.lower().split():
        token = token.strip("_ -")
        if len(token) >= en_min_len and token not in EN_STOP_WORDS:
            en_tokens[token] += 1

    # 合并并计算 TF-IDF 近似分数
    total_cn = sum(cn_grams.values())
    total_en = sum(en_tokens.values())
    total = total_cn + total_en

    if total == 0:
        return []

    scores: Dict[str, float] = {}

    # 中文分数 (TF × log(N/DF) 近似)
    for gram, count in cn_grams.most_common(100):
        tf = count / max(total_cn, 1)
        # IDF 近似: 越长的词越稀有
        idf_bonus = math.log(len(gram)) * 0.5
        scores[gram] = tf * (1 + idf_bonus)

    # 英文分数
    for token, count in en_tokens.most_common(50):
        tf = count / max(total_en, 1)
        scores[token] = tf

    # 排序取 Top K
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked[:top_k]


# ═══════════════════════════════════════════════════════════════
# U3A: 文本清洗 + 标题提取
# ═══════════════════════════════════════════════════════════════

def clean_text(text: str) -> str:
    """清洗文本: 去 HTML / 代码块 / 多余空白"""
    # 去 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)
    # 去 Markdown 代码块 (保留语言标记作为 context)
    text = re.sub(r'```[\s\S]*?```', ' [代码块] ', text)
    # 去行内代码
    text = re.sub(r'`[^`]+`', ' ', text)
    # 去链接 (保留文本)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # 去 URL
    text = re.sub(r'https?://\S+', '', text)
    # 统一空白
    text = re.sub(r'\r\n|\r', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


def extract_title_and_sections(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """提取标题 + 段落

    Returns:
        (title, [(heading, body), ...])
    """
    lines = text.split("\n")
    title = ""
    sections: List[Tuple[str, str]] = []
    current_heading = ""
    current_body: List[str] = []

    for line in lines:
        # H1 → title
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        # H2/H3 → new section
        if re.match(r'^#{1,3}\s+', line):
            if current_body or current_heading:
                sections.append((current_heading, "\n".join(current_body).strip()))
            current_heading = line.lstrip("#").strip()
            current_body = []
            continue
        current_body.append(line)

    # last section
    if current_body or current_heading:
        sections.append((current_heading, "\n".join(current_body).strip()))

    # 如果没提取到标题，用第一段前 50 字
    if not title and sections:
        first_body = sections[0][1][:50]
        title = first_body.strip()

    return title, sections


# ═══════════════════════════════════════════════════════════════
# U3C: 反思 + 练习生成
# ═══════════════════════════════════════════════════════════════

REFLECTION_TEMPLATES = [
    "今天的学习中，有哪些体现了「{concept}」？",
    "关于「{concept}」，我还需要深入理解什么？",
    "「{concept}」和我已有的知识有什么联系？",
    "在实际项目中，我如何应用「{concept}」？",
    "如果向别人解释「{concept}」，我会怎么说？",
]

PRACTICE_TEMPLATES = {
    "beginner": [
        "阅读 {concept} 的官方文档入门部分",
        "完成 {concept} 的 Hello World 示例",
        "理解 {concept} 的核心概念和术语",
    ],
    "intermediate": [
        "使用 {concept} 实现一个实际功能",
        "对比 {concept} 与同类工具的优劣",
        "阅读 {concept} 的进阶教程/源码",
    ],
    "advanced": [
        "优化 {concept} 的性能或架构",
        "为 {concept} 贡献代码或文档",
        "设计基于 {concept} 的解决方案",
    ],
}


def generate_reflections(concepts: List[str], count: int = 3) -> List[str]:
    """基于概念生成反思提示词"""
    reflections = []
    for concept in concepts[:5]:
        for tmpl in REFLECTION_TEMPLATES[:count]:
            reflections.append(tmpl.format(concept=concept))
    return reflections[:count * 2]


def generate_practice_tasks(
    concepts: List[str],
    difficulty: str = "beginner",
    count: int = 3,
) -> List[Dict[str, str]]:
    """基于概念和难度生成练习任务"""
    templates = PRACTICE_TEMPLATES.get(difficulty, PRACTICE_TEMPLATES["beginner"])
    tasks = []
    for concept in concepts[:5]:
        for tmpl in templates[:count]:
            tasks.append({
                "level": difficulty,
                "description": tmpl.format(concept=concept),
                "expected": f"掌握 {concept} 的{difficulty}级别应用",
            })
    return tasks[:count * 2]


# ═══════════════════════════════════════════════════════════════
# U3A: ContentToSkillConverter 核心
# ═══════════════════════════════════════════════════════════════

# 分类关键词映射
CATEGORY_KEYWORDS = {
    "dev": ["编程", "开发", "代码", "python", "javascript", "rust", "go", "api",
            "web", "后端", "前端", "框架", "库", "算法", "数据库"],
    "design": ["设计", "ui", "ux", "界面", "视觉", "原型", "figma", "css",
              "布局", "配色", "字体"],
    "data": ["数据", "分析", "统计", "machine learning", "ai", "pandas", "sql",
            "可视化", "大数据", "模型", "训练"],
    "ops": ["运维", "部署", "docker", "kubernetes", "ci", "cd", "云", "监控",
           "自动化", "pipeline", "基础设施"],
    "writing": ["写作", "文档", "blog", "翻译", "编辑", "markdown", "出版"],
}


def infer_category(text: str, keywords: List[str]) -> str:
    """从文本和关键词推断分类"""
    text_lower = text.lower()
    scores: Dict[str, int] = {}
    for cat, kws in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in kws if kw.lower() in text_lower)
        # 关键词匹配加成
        for kw in keywords:
            if any(ck in kw.lower() for ck in kws):
                score += 2
        if score > 0:
            scores[cat] = score

    if scores:
        return max(scores, key=scores.get)
    return "general"


def infer_difficulty(text: str) -> str:
    """从文本推断难度"""
    text_lower = text.lower()
    advanced = ["进阶", "advanced", "深入", "原理", "架构", "源码", "优化", "高级"]
    intermediate = ["实战", "项目", "应用", "practice", "指南", "教程"]
    beginner = ["入门", "beginner", "基础", "初学", "新手", "快速上手"]

    if any(kw in text_lower for kw in advanced):
        return "advanced"
    if any(kw in text_lower for kw in intermediate):
        return "intermediate"
    return "beginner"


class ContentToSkillConverter:
    """文本/URL/文件 → SkillSpec 转换器"""

    def convert_from_text(self, content: str, title: str = "",
                          source_url: str = "") -> "SkillSpec":
        """从文本内容创建 SkillSpec

        7 步管线:
          清洗 → 标题 → 概念 → 分类 → 反思 → 练习 → SkillSpec
        """
        from zenskill.core.skill_spec import SkillSpec, CapabilitySpec
        from zenskill.core.skill_types import SkillType

        # 1. 清洗
        cleaned = clean_text(content)

        # 2. 标题 + 段落
        extracted_title, sections = extract_title_and_sections(cleaned)
        if not title:
            title = extracted_title or "未命名技能"

        # 3. 概念提取
        keywords = extract_keywords_tfidf(cleaned, top_k=10)
        concepts = [k for k, _ in keywords[:8]]
        tags = [k for k, _ in keywords[:5]]

        # 4. 分类推断
        category = infer_category(cleaned, concepts)
        difficulty = infer_difficulty(cleaned)

        # 5. 反思生成
        reflections = generate_reflections(concepts)

        # 6. 练习生成
        practice_tasks = generate_practice_tasks(concepts, difficulty)

        # 7. → SkillSpec
        skill_id = re.sub(r'[^a-z0-9-]', '', title.lower().replace(" ", "-"))[:40]
        if not skill_id:
            skill_id = "content-skill"

        description = cleaned[:200].replace("\n", " ")

        # 能力: 每个主要段落一个能力
        capabilities = []
        for heading, body in sections[:5]:
            if heading and body:
                caps = CapabilitySpec(
                    name=re.sub(r'[^a-z_]', '_', heading.lower())[:30],
                    description=heading,
                    proficiency=0.5,
                    keywords=concepts[:5],
                    examples=[body[:100]],
                )
                capabilities.append(caps)

        if not capabilities:
            capabilities.append(CapabilitySpec(
                name="general",
                description=title,
                proficiency=0.5,
                keywords=concepts[:5],
            ))

        return SkillSpec(
            id=skill_id,
            name=title,
            description=description,
            category=category,
            skill_type=SkillType.KNOWLEDGE,
            difficulty=difficulty,
            tags=tags,
            source="content",
            source_url=source_url,
            source_format="text",
            key_concepts=concepts,
            reflection_prompts=reflections,
            practice_tasks=practice_tasks,
            capabilities=capabilities,
            keywords=concepts,
        )

    def convert_from_url(self, url: str) -> Optional["SkillSpec"]:
        """从 URL 获取内容并转换

        SSRF 防护: 仅 http/https、阻断私网/环回/链路本地/保留地址、禁自动重定向
        """
        import ipaddress
        import socket
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            logger.error(f"Rejected non-http(s) URL: {url}")
            return None
        hostname = parsed.hostname
        if not hostname:
            logger.error(f"Rejected URL without host: {url}")
            return None

        try:
            addr_infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror as e:
            logger.error(f"DNS resolution failed for {hostname}: {e}")
            return None
        target_ip = addr_infos[0][4][0] if addr_infos else None
        try:
            ip = ipaddress.ip_address(target_ip)
        except ValueError:
            ip = None
        if ip is not None and (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified
        ):
            logger.error(f"Blocked non-public target {hostname} ({target_ip})")
            return None

        try:
            import requests
            resp = requests.get(
                url,
                timeout=15,
                allow_redirects=False,
                headers={"User-Agent": "ZenSkill/2.5 (Content Extractor)"},
            )
            if resp.status_code in (301, 302, 303, 307, 308):
                logger.error("Redirect blocked for SSRF safety")
                return None
            resp.raise_for_status()

            # 尝试从 <title> 提取
            title = ""
            m = re.search(r'<title>([^<]+)</title>', resp.text, re.IGNORECASE)
            if m:
                title = m.group(1).strip()

            return self.convert_from_text(resp.text, title=title, source_url=url)
        except Exception as e:
            logger.error(f"Failed to convert from URL {url}: {e}")
            return None

    def convert_from_file(self, path: str) -> Optional["SkillSpec"]:
        """从本地文件转换"""
        p = Path(path)
        if not p.exists():
            logger.error(f"File not found: {path}")
            return None

        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            return self.convert_from_text(content, title=p.stem, source_url=f"file://{p.absolute()}")
        except Exception as e:
            logger.error(f"Failed to convert from file {path}: {e}")
            return None


# ── 便捷函数 ──

_converter = ContentToSkillConverter()


def content_to_skill(content: str, title: str = "", url: str = "") -> Optional["SkillSpec"]:
    """一行将内容转为技能"""
    return _converter.convert_from_text(content, title=title, source_url=url)
