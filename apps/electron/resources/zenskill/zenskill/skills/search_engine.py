"""
Skill Search Engine (Phase 9U)

基于语义的技能搜索引擎，支持自然语言搜索、发现推荐、热门趋势和学习路径。

数据源:
- ~/.zenskill/skills/*.py — 已安装的技能代码
- ~/.zenskill/packages/*/manifest.json — 已安装的技能包元数据
- SkillStateManager — 技能使用状态和指标
- 内置技能模板 (platforms/claude_code/skills/)
- SkillDefinition DSL — NL 定义的技能
"""

from __future__ import annotations

import json
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class SkillIndexEntry:
    """搜索索引中的技能条目"""
    skill_id: str
    name: str
    description: str = ""
    category: str = "general"
    difficulty: str = "beginner"
    tags: List[str] = field(default_factory=list)
    author: str = ""
    version: str = "0.1.0"

    # 来源
    source: str = "unknown"          # installed / package / builtin / github / market / content
    source_market: str = ""          # clawhub / npm / pypi / github
    source_url: str = ""             # 原始 URL
    source_format: str = ""          # clawhub.toml / package.json / README

    # 使用统计（从 SkillStateManager 采集）
    usage_count: int = 0
    level: str = "NOVICE"
    success_rate: float = 0.0
    last_used: Optional[str] = None

    # 依赖
    prerequisites: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)

    # 排名
    rating: float = 0.0              # 0-5 用户评分
    trending_score: float = 0.0      # 热度分

    # Phase E1B: 扩展字段
    license: str = ""                # MIT / GPL / Apache-2.0
    has_ci: bool = False             # 是否有 CI/CD
    verified: bool = False           # 安全审计状态
    key_concepts: List[str] = field(default_factory=list)
    reflection_questions: List[str] = field(default_factory=list)

    def to_spec(self) -> "SkillSpec":
        """升级到 SkillSpec (Phase S)"""
        from zenskill.core.skill_spec import SkillSpec
        return SkillSpec.from_index_entry(self)

    @property
    def keywords(self) -> List[str]:
        """提取关键词用于搜索匹配"""
        words = set()
        for text in [self.name, self.description, self.category, self.skill_id]:
            # 中文分词：单字 + 双字组合
            for ch in text:
                if '\u4e00' <= ch <= '\u9fff':
                    words.add(ch)
            # 英文 token
            for token in re.findall(r'[a-zA-Z_][a-zA-Z0-9_-]*', text):
                words.add(token.lower())
        for tag in self.tags:
            words.add(tag.lower())
        return list(words)


@dataclass
class SearchResult:
    """搜索结果"""
    skill: SkillIndexEntry
    score: float = 0.0
    matched_terms: List[str] = field(default_factory=list)

    def __lt__(self, other: "SearchResult") -> bool:
        return self.score < other.score


@dataclass
class LearningPathStep:
    """学习路径中的一个步骤"""
    skill_id: str
    name: str
    difficulty: str
    estimated_interactions: int = 10
    description: str = ""


# ═══════════════════════════════════════════════════════════════
# 搜索引擎
# ═══════════════════════════════════════════════════════════════

class SkillSearchEngine:
    """
    技能搜索引擎

    支持:
    - search(query, filters) — 自然语言搜索
    - discover(skill_ids) — 基于已有技能发现推荐
    - trending() — 热门趋势
    - path(target, owned_skills) — 学习路径
    """

    # 内置技能定义（硬编码兜底，确保引擎即使无外部数据也能工作）
    _BUILTIN_SKILLS: List[Dict[str, Any]] = [
        {
            "skill_id": "zenskill-core",
            "name": "ZenSkill 核心技能",
            "description": "ZenSkill 元能力：记忆、修炼、反思、成长。系统核心技能，"
                           "管理所有其他技能的状态和进化。",
            "category": "system",
            "difficulty": "beginner",
            "tags": ["元能力", "核心", "系统"],
            "source": "builtin",
        },
        {
            "skill_id": "knowledge-base",
            "name": "知识库管理",
            "description": "管理知识库的入库、索引、校验、恢复和飞书分享。"
                           "负责知识资产的全生命周期管理。",
            "category": "writing",
            "difficulty": "intermediate",
            "tags": ["知识管理", "文档", "入库"],
            "source": "builtin",
        },
        {
            "skill_id": "python-backend",
            "name": "Python 后端开发",
            "description": "Python 后端开发技能，涵盖 FastAPI、SQLAlchemy、"
                           "Pytest、Docker 等主流技术栈。",
            "category": "dev",
            "difficulty": "intermediate",
            "tags": ["python", "后端", "api"],
            "source": "builtin",
        },
        {
            "skill_id": "technical-writing",
            "name": "技术写作",
            "description": "技术文档写作，包括 API 文档、教程、技术博客、"
                           "架构决策记录（ADR）等。",
            "category": "writing",
            "difficulty": "beginner",
            "tags": ["写作", "文档", "技术博客"],
            "source": "builtin",
        },
        {
            "skill_id": "data-analysis",
            "name": "数据分析",
            "description": "数据分析与可视化，Pandas、NumPy、Matplotlib、"
                           "Jupyter Notebook 等工具链。",
            "category": "data",
            "difficulty": "intermediate",
            "tags": ["数据", "分析", "可视化"],
            "source": "builtin",
        },
        {
            "skill_id": "devops-cicd",
            "name": "DevOps & CI/CD",
            "description": "CI/CD 流水线、Docker 容器化、Kubernetes 编排、"
                           "基础设施即代码。",
            "category": "ops",
            "difficulty": "advanced",
            "tags": ["devops", "docker", "ci/cd"],
            "source": "builtin",
        },
        {
            "skill_id": "ui-design",
            "name": "UI/UX 设计",
            "description": "用户界面与体验设计，Figma 原型、设计系统、"
                           "交互设计原则。",
            "category": "design",
            "difficulty": "beginner",
            "tags": ["设计", "ui", "ux"],
            "source": "builtin",
        },
        {
            "skill_id": "project-management",
            "name": "项目管理",
            "description": "项目管理方法论，GTD、敏捷开发、OKR 目标管理、"
                           "团队协作。",
            "category": "general",
            "difficulty": "intermediate",
            "tags": ["管理", "gtđ", "敏捷"],
            "source": "builtin",
        },
    ]

    def __init__(self):
        self._index: Dict[str, SkillIndexEntry] = {}  # skill_id → entry
        self._built = False

    # ── 索引构建 ──

    def build_index(self) -> Dict[str, Any]:
        """
        扫描所有数据源，构建搜索索引

        优先级：
        1. 内置技能 (8 个兜底) — 始终加载
        2. SQLite 数据库 (Phase D)
        3. 本地文件 + 包 (向后兼容)

        Returns:
            {"total": int, "sources": {...}, "errors": [...]}
        """
        self._index = {}
        sources = {"db": 0, "builtin": 0, "installed": 0, "package": 0}
        errors = []

        # 1. 内置技能 — 始终加载作为兜底
        for s in self._BUILTIN_SKILLS:
            entry = SkillIndexEntry(**s)
            if entry.skill_id not in self._index:
                self._index[entry.skill_id] = entry
                sources["builtin"] += 1

        # 2. SQLite 数据库 (Phase D)
        db_count = self._build_from_db()
        if db_count > 0:
            sources["db"] = db_count

        # 3. 已安装的技能文件
        skills_dir = Path.home() / ".zenskill" / "skills"
        if skills_dir.exists():
            for py_file in sorted(skills_dir.glob("*.py")):
                try:
                    entry = self._parse_skill_file(py_file)
                    if entry and entry.skill_id not in self._index:
                        self._index[entry.skill_id] = entry
                        sources["installed"] += 1
                except Exception as e:
                    errors.append(f"解析技能文件失败 {py_file.name}: {e}")

        # 4. 已安装的技能包
        packages_dir = Path.home() / ".zenskill" / "packages"
        if packages_dir.exists():
            for pkg_dir in sorted(packages_dir.iterdir()):
                if pkg_dir.is_dir():
                    mf = pkg_dir / "manifest.json"
                    if mf.exists():
                        try:
                            meta = json.loads(mf.read_text(encoding="utf-8"))
                            entry = self._meta_to_entry(meta, "package")
                            if entry and entry.skill_id not in self._index:
                                self._index[entry.skill_id] = entry
                                sources["package"] += 1
                        except Exception as e:
                            errors.append(f"解析包元数据失败 {pkg_dir.name}: {e}")

        # 5. 已安装的 SKILL.md 技能（~/.agents/skills/）
        agents_skills_dir = Path.home() / ".agents" / "skills"
        if agents_skills_dir.exists():
            for skill_dir in sorted(agents_skills_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                md_file = skill_dir / "SKILL.md"
                if not md_file.exists():
                    continue
                try:
                    entry = self._parse_skill_md(skill_dir.name, md_file)
                    if entry and entry.skill_id not in self._index:
                        self._index[entry.skill_id] = entry
                        sources["installed"] += 1
                except Exception as e:
                    errors.append(f"解析 SKILL.md 失败 {skill_dir.name}: {e}")

        # 6. 补充使用统计数据
        self._enrich_with_usage_stats()

        self._built = True
        return {
            "total": len(self._index),
            "sources": sources,
            "errors": errors,
        }

    def _build_from_db(self) -> int:
        """从 SQLite 加载技能到内存索引 (Phase D3C)"""
        try:
            from zenskill.core.skill_profile import SkillProfile
            profiles = SkillProfile.list_all(is_active=True, limit=1000)
            if not profiles:
                return 0

            for p in profiles:
                entry = SkillIndexEntry(
                    skill_id=p.skill_id,
                    name=p.name,
                    description=p.description,
                    category=p.category,
                    difficulty=p.difficulty,
                    tags=p.tags,
                    author=p.author,
                    version=p.version,
                    source=p.source,
                    source_market=p.source_market,
                    source_url=p.source_url,
                    usage_count=p.total_interactions,
                    level=p.level,
                    success_rate=p.success_rate,
                    rating=p.rating_overall,
                    last_used=p.last_interaction_at,
                    license=p.license,
                    verified=p.verified,
                )
                self._index[p.skill_id] = entry

            return len(profiles)
        except Exception:
            return 0

    def _parse_skill_file(self, py_file: Path) -> Optional[SkillIndexEntry]:
        """从 ~/.zenskill/skills/<skill_id>.py 解析技能元数据"""
        skill_id = py_file.stem
        content = py_file.read_text(encoding="utf-8")

        entry = SkillIndexEntry(
            skill_id=skill_id,
            name=skill_id,
            source="installed",
        )

        # 提取 SKILL_NAME
        m = re.search(r'SKILL_NAME\s*=\s*"([^"]+)"', content)
        if m:
            entry.name = m.group(1)

        # 提取 CATEGORY
        m = re.search(r'CATEGORY\s*=\s*"([^"]+)"', content)
        if m:
            entry.category = m.group(1)

        # 提取 DIFFICULTY
        m = re.search(r'DIFFICULTY\s*=\s*"([^"]+)"', content)
        if m:
            entry.difficulty = m.group(1)

        # 提取 DESCRIPTION / docstring
        m = re.search(r'DESCRIPTION\s*=\s*"""(.+?)"""', content, re.DOTALL)
        if m:
            entry.description = m.group(1).strip()
        else:
            m = re.search(r'"""(.*?)"""', content, re.DOTALL)
            if m:
                entry.description = m.group(1).strip()[:200]

        return entry

    def _parse_skill_md(self, skill_id: str, md_file: Path) -> Optional[SkillIndexEntry]:
        """从 ~/.agents/skills/<name>/SKILL.md 解析技能元数据"""
        content = md_file.read_text(encoding="utf-8")[:3000]

        # 解析 YAML frontmatter
        name = skill_id
        description = ""
        category = "general"
        tags: List[str] = []

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                for line in frontmatter.split("\n"):
                    line = line.strip()
                    if line.startswith("name:"):
                        name = line[5:].strip().strip('"').strip("'")
                    elif line.startswith("description:"):
                        description = line[12:].strip().strip('"').strip("'")
                    elif line.startswith("category:"):
                        category = line[9:].strip().strip('"').strip("'")
                    elif line.startswith("tags:"):
                        tag_str = line[5:].strip().strip("[]")
                        tags = [t.strip().strip('"').strip("'") for t in tag_str.split(",")]

        # 从正文第一段提取描述（如果 frontmatter 没有）
        if not description:
            lines = [l.strip() for l in content.split("\n") if l.strip() and not l.startswith("#") and not l.startswith("---")]
            if lines:
                description = lines[0][:200]

        return SkillIndexEntry(
            skill_id=skill_id,
            name=name,
            description=description,
            category=category,
            tags=tags,
            source="installed",
            source_format="SKILL.md",
        )

    def _meta_to_entry(self, meta: dict, source: str) -> Optional[SkillIndexEntry]:
        """将 manifest.json 字典转为索引条目"""
        name = meta.get("name", "")
        if not name:
            return None
        return SkillIndexEntry(
            skill_id=name.lower().replace(" ", "-"),
            name=name,
            description=meta.get("description", ""),
            category=meta.get("category", "general"),
            difficulty=meta.get("difficulty", "beginner"),
            tags=meta.get("tags", []),
            author=meta.get("author", ""),
            version=meta.get("version", "0.1.0"),
            source=source,
            dependencies=meta.get("dependencies", []),
        )

    def _enrich_with_usage_stats(self) -> None:
        """从 SkillStateManager 补充使用统计数据"""
        try:
            from zenskill.core.paths import SkillStateManager
            from zenskill.core.paths import get_user_data_dir

            states_dir = get_user_data_dir() / "states"
            if not states_dir.exists():
                return

            for state_file in states_dir.glob("*.json"):
                skill_id = state_file.stem
                if skill_id not in self._index:
                    continue
                try:
                    mgr = SkillStateManager(skill_id)
                    state = mgr.load()
                    entry = self._index[skill_id]
                    entry.usage_count = state.get("usage_count", 0)
                    entry.level = state.get("level", "NOVICE")
                    metrics = state.get("metrics", {})
                    entry.success_rate = metrics.get("success_rate", 0.0)
                    episodes = state.get("episodes", [])
                    if episodes:
                        entry.last_used = episodes[-1].get("date", "")
                except Exception:
                    pass
        except ImportError:
            pass

    # ── 搜索 ──

    def search(
        self,
        query: str,
        *,
        category: Optional[str] = None,
        difficulty: Optional[str] = None,
        tags: Optional[List[str]] = None,
        min_usage: int = 0,
        top_k: int = 10,
    ) -> List[SearchResult]:
        """
        自然语言搜索技能

        Args:
            query: 搜索关键词（支持中文/英文自然语言）
            category: 按分类过滤 (dev/design/data/ops/writing/general/system)
            difficulty: 按难度过滤 (beginner/intermediate/advanced/expert)
            tags: 按标签过滤
            min_usage: 最低使用次数
            top_k: 返回数量

        Returns:
            按相关性降序排列的搜索结果
        """
        if not self._built:
            self.build_index()

        query_lower = query.lower().strip()
        query_tokens = self._tokenize(query_lower)
        if not query_lower or not query_tokens:
            return []

        results: List[SearchResult] = []

        for entry in self._index.values():
            # 过滤
            if category and entry.category != category:
                continue
            if difficulty and entry.difficulty != difficulty:
                continue
            if tags and not any(t in entry.tags for t in tags):
                continue
            if entry.usage_count < min_usage:
                continue

            score, matched = self._score_entry(entry, query_lower, query_tokens)
            if score > 0 and matched:
                results.append(SearchResult(skill=entry, score=score, matched_terms=matched))

        results.sort(reverse=True)
        return results[:top_k]

    def _tokenize(self, text: str) -> List[str]:
        """分词：中文单字 + 英文 token + 连字符拆分子 token"""
        tokens = []
        # 中文单字
        for ch in text:
            if '\u4e00' <= ch <= '\u9fff':
                tokens.append(ch)
        # 英文 token
        for token in re.findall(r'[a-zA-Z][a-zA-Z0-9_\-]*', text):
            lower = token.lower()
            tokens.append(lower)
            # 连字符拆分：lark-approval -> ["lark", "approval"]
            parts = lower.split('-')
            if len(parts) > 1:
                tokens.extend(parts)
        return list(set(tokens))

    def _score_entry(
        self,
        entry: SkillIndexEntry,
        query_lower: str,
        query_tokens: List[str],
    ) -> Tuple[float, List[str]]:
        """
        计算技能条目与查询的相关性得分

        评分维度:
        - 名称匹配 (权重 0.4)
        - 描述匹配 (权重 0.3)
        - 标签匹配 (权重 0.2)
        - 分类匹配 (权重 0.1)
        """
        score = 0.0
        matched = []

        search_texts = [
            (entry.name.lower(), 0.4),
            (entry.description.lower(), 0.3),
            (" ".join(t.lower() for t in entry.tags), 0.2),
            (entry.category.lower(), 0.1),
            (entry.skill_id.lower(), 0.15),
        ]

        for text, weight in search_texts:
            if query_lower in text:
                score += weight * 1.0
                matched.append(text[:30])

            # Token 级别匹配
            text_tokens = self._tokenize(text)
            for qt in query_tokens:
                if len(qt) >= 2 and qt in text_tokens:
                    score += weight * 0.5
                    if qt not in matched:
                        matched.append(qt)

            # 模糊匹配（编辑距离 1 以内）
            for qt in query_tokens:
                if len(qt) >= 3:
                    for tt in text_tokens:
                        if len(tt) >= 3 and self._levenshtein(qt, tt) <= 1:
                            score += weight * 0.3
                            if qt not in matched:
                                matched.append(qt)

        # 使用频率加分（活跃技能排前面，仅在有文本匹配时）
        if matched and entry.usage_count > 0:
            score += min(entry.usage_count / 100, 0.1)

        return score, matched[:5]

    @staticmethod
    def _levenshtein(a: str, b: str) -> int:
        """计算编辑距离"""
        if len(a) < len(b):
            a, b = b, a
        if not b:
            return len(a)
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a):
            curr = [i + 1]
            for j, cb in enumerate(b):
                curr.append(min(
                    curr[j] + 1,
                    prev[j + 1] + 1,
                    prev[j] + (ca != cb),
                ))
            prev = curr
        return prev[-1]

    # ── 发现推荐 ──

    def discover(
        self,
        owned_skills: Optional[List[str]] = None,
        top_k: int = 10,
    ) -> List[SearchResult]:
        """
        基于用户已有技能发现推荐

        策略:
        1. 互补推荐：推荐与已有技能同分类但不同难度的
        2. 迁移推荐：推荐与已有技能强相关的（标签重叠）
        3. 空白推荐：推荐用户完全没有接触的分类
        4. 热门推荐：综合热度排序

        Args:
            owned_skills: 用户已有的 skill_id 列表
            top_k: 返回数量

        Returns:
            推荐列表（带推荐理由）
        """
        if not self._built:
            self.build_index()

        owned = owned_skills or []
        owned_set = set(owned)
        owned_categories: Set[str] = set()
        owned_tags: Set[str] = set()
        owned_difficulties: Set[str] = set()

        for sid in owned:
            entry = self._index.get(sid)
            if entry:
                owned_categories.add(entry.category)
                owned_tags.update(entry.tags)
                owned_difficulties.add(entry.difficulty)

        candidates: List[Tuple[float, SearchResult, str]] = []

        for entry in self._index.values():
            if entry.skill_id in owned_set:
                continue

            reasons = []
            score = 0.0

            # 互补推荐：同分类不同难度
            if entry.category in owned_categories and entry.difficulty not in owned_difficulties:
                score += 0.3
                reasons.append(f"与已有技能同属「{entry.category}」分类，但难度不同")

            # 迁移推荐：标签重叠
            tag_overlap = len(set(entry.tags) & owned_tags)
            if tag_overlap > 0:
                score += 0.25 * min(tag_overlap / 2, 1.0)
                common = list(set(entry.tags) & owned_tags)[:2]
                reasons.append(f"共有标签: {', '.join(common)}")

            # 空白推荐：未涉足的分类
            if entry.category not in owned_categories and entry.category != "system":
                score += 0.2
                reasons.append(f"探索新领域: {entry.category}")

            # 热门加分
            score += min(entry.trending_score / 10, 0.1)

            # 使用量加分
            score += min(entry.usage_count / 50, 0.1)

            if score > 0:
                sr = SearchResult(skill=entry, score=score, matched_terms=reasons)
                candidates.append((score, sr, "; ".join(reasons[:2])))

        candidates.sort(reverse=True, key=lambda x: x[0])
        return [c[1] for c in candidates[:top_k]]

    # ── 热门趋势 ──

    def trending(self, top_k: int = 10) -> List[SearchResult]:
        """
        热门趋势技能

        排名依据:
        - 使用次数（权重 0.4）
        - 成功率（权重 0.2）
        - 境界等级（权重 0.2）
        - 最近活跃度（权重 0.2）
        """
        if not self._built:
            self.build_index()

        scored: List[Tuple[float, SkillIndexEntry]] = []

        for entry in self._index.values():
            score = 0.0
            score += min(entry.usage_count / 100, 0.4)          # 使用次数
            score += entry.success_rate * 0.2                    # 成功率
            level_scores = {"NOVICE": 0, "APPRENTICE": 0.05,
                            "ADEPT": 0.1, "EXPERT": 0.15, "MASTER": 0.2}
            score += level_scores.get(entry.level, 0)            # 境界等级
            if entry.last_used:
                try:
                    days_since = (datetime.now() - datetime.fromisoformat(entry.last_used[:19])).days
                    score += max(0, 0.2 - days_since * 0.02)     # 最近活跃度
                except Exception:
                    pass
            # 兜底：至少有点击基础分
            score += 0.05

            scored.append((score, entry))

        scored.sort(reverse=True, key=lambda x: x[0])
        results = [
            SearchResult(skill=entry, score=round(score, 3))
            for score, entry in scored[:top_k]
        ]
        return results

    # ── 学习路径 ──

    def path(
        self,
        target_goal: str,
        owned_skills: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """
        为达成目标推荐学习路径

        Args:
            target_goal: 目标描述（如 "成为 Python 全栈工程师"）
            owned_skills: 用户已拥有的 skill_id 列表
            top_k: 路径步骤数

        Returns:
            {"goal": ..., "steps": [...], "estimated_total_interactions": int}
        """
        if not self._built:
            self.build_index()

        owned = set(owned_skills or [])

        # 0. 空目标
        if not target_goal or not target_goal.strip():
            return {"goal": target_goal, "steps": [], "estimated_total_interactions": 0}

        # 1. 搜索与目标相关的技能
        related = self.search(target_goal, top_k=top_k * 2)

        # 2. 按难度排序（beginner → expert）
        difficulty_order = {"beginner": 0, "intermediate": 1, "advanced": 2, "expert": 3}

        # 3. 构建路径：先排已有技能（作为起点），再按难度递增
        steps: List[LearningPathStep] = []
        seen = set()

        # 已有技能作为起点
        for sid in owned:
            entry = self._index.get(sid)
            if entry and sid not in seen:
                seen.add(sid)
                steps.append(LearningPathStep(
                    skill_id=sid,
                    name=entry.name,
                    difficulty=entry.difficulty,
                    estimated_interactions=self._estimate_interactions(entry),
                    description=f"[已有] {entry.description[:60]}",
                ))

        # 推荐的技能按难度排序
        for result in related:
            entry = result.skill
            if entry.skill_id in seen:
                continue
            seen.add(entry.skill_id)
            steps.append(LearningPathStep(
                skill_id=entry.skill_id,
                name=entry.name,
                difficulty=entry.difficulty,
                estimated_interactions=self._estimate_interactions(entry),
                description=entry.description[:80],
            ))

        # 按难度排序（已有的排在前面）
        steps.sort(key=lambda s: (1 if s.skill_id in owned else 2,
                                  difficulty_order.get(s.difficulty, 0)))

        total_interactions = sum(s.estimated_interactions for s in steps)

        return {
            "goal": target_goal,
            "steps": [{
                "skill_id": s.skill_id,
                "name": s.name,
                "difficulty": s.difficulty,
                "estimated_interactions": s.estimated_interactions,
                "description": s.description,
            } for s in steps[:top_k]],
            "estimated_total_interactions": total_interactions,
        }

    @staticmethod
    def _estimate_interactions(entry: SkillIndexEntry) -> int:
        """估算所需交互次数"""
        base = {"beginner": 10, "intermediate": 30, "advanced": 60, "expert": 100}
        return base.get(entry.difficulty, 10)

    # ── 辅助 ──

    def get_entry(self, skill_id: str) -> Optional[SkillIndexEntry]:
        """按 ID 获取索引条目"""
        if not self._built:
            self.build_index()
        return self._index.get(skill_id)

    def get_all_entries(self) -> List[SkillIndexEntry]:
        """获取所有索引条目"""
        if not self._built:
            self.build_index()
        return list(self._index.values())

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self._built:
            self.build_index()
        categories: Dict[str, int] = {}
        difficulties: Dict[str, int] = {}
        for entry in self._index.values():
            categories[entry.category] = categories.get(entry.category, 0) + 1
            difficulties[entry.difficulty] = difficulties.get(entry.difficulty, 0) + 1
        return {
            "total_skills": len(self._index),
            "categories": categories,
            "difficulties": difficulties,
            "sources": set(e.source for e in self._index.values()),
        }
