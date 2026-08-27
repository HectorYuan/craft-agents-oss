"""
市场适配器 — ClawHub / npm / PyPI → SkillSpec (Phase U4A-B)

每个适配器实现 BaseMarketAdapter 接口:
  - search()   — 在市场内搜索
  - install()  — 安装到本地 ZenSkill

用法:
    from zenskill.skills.market_adapters import ClawHubAdapter, NpmAdapter, PyPIAdapter

    adapter = NpmAdapter()
    results = adapter.search("react")
    adapter.install("react")
"""

from __future__ import annotations

import json
import logging
import os

import requests
from typing import Any, Dict, List, Optional

from .universal_installer import BaseMarketAdapter, MarketSkillEntry

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# U4A: ClawHubAdapter
# ═══════════════════════════════════════════════════════════════

class ClawHubAdapter(BaseMarketAdapter):
    """ClawHub 技能市场适配器

    ClawHub 是 Claude Code 的技能注册中心。
    API: https://registry.clawhub.io/api/v1
    """

    REGISTRY_URL = "https://registry.clawhub.io/api/v1"

    @property
    def market_name(self) -> str:
        return "clawhub"

    @property
    def market_display(self) -> str:
        return "ClawHub"

    @property
    def market_icon(self) -> str:
        return "🦞"

    def search(self, query: str, top_k: int = 10, **filters) -> List[MarketSkillEntry]:
        try:
            resp = requests.get(
                f"{self.REGISTRY_URL}/skills",
                params={"q": query, "limit": top_k},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                skills = data.get("skills", data.get("results", []))
                return [
                    MarketSkillEntry(
                        skill_id=s.get("id", s.get("name", "")),
                        name=s.get("name", s.get("id", "")),
                        description=s.get("description", ""),
                        category=s.get("category", "general"),
                        tags=s.get("tags", []),
                        author=s.get("author", ""),
                        version=s.get("version", "0.1.0"),
                        market="clawhub",
                        rating=s.get("rating", 0.0),
                        downloads=s.get("downloads", 0),
                    )
                    for s in skills[:top_k]
                ]
        except Exception as e:
            logger.debug(f"ClawHub search failed: {e}")
        return []

    def fetch_meta(self, skill_id: str) -> Optional[MarketSkillEntry]:
        try:
            resp = requests.get(
                f"{self.REGISTRY_URL}/skills/{skill_id}",
                timeout=10,
            )
            if resp.status_code == 200:
                s = resp.json()
                return MarketSkillEntry(
                    skill_id=s.get("id", skill_id),
                    name=s.get("name", skill_id),
                    description=s.get("description", ""),
                    category=s.get("category", "general"),
                    tags=s.get("tags", []),
                    author=s.get("author", ""),
                    version=s.get("version", "0.1.0"),
                    market="clawhub",
                    url=s.get("url", ""),
                    rating=s.get("rating", 0.0),
                    downloads=s.get("downloads", 0),
                )
        except Exception as e:
            logger.debug(f"ClawHub fetch failed: {e}")
        return None

    def install(self, skill_id: str, **options) -> Dict[str, Any]:
        try:
            from zenskill.core.skill_dao import SkillDAO
            from zenskill.core.skill_spec import SkillSpec

            # 获取元数据
            meta = self.fetch_meta(skill_id)
            if meta:
                spec = SkillSpec(
                    id=f"clawhub-{skill_id}",
                    name=meta.name,
                    description=meta.description,
                    category=meta.category,
                    tags=meta.tags,
                    author=meta.author,
                    version=meta.version,
                    source="market",
                    source_market="clawhub",
                    source_url=meta.url or f"clawhub://{skill_id}",
                )
                spec.save()
                return {"success": True, "skill_id": spec.id, "method": "clawhub"}
            else:
                # 基础注册
                sid = f"clawhub-{skill_id}"
                SkillDAO.upsert(sid, name=skill_id, source="market",
                               source_market="clawhub", is_active=1)
                return {"success": True, "skill_id": sid, "method": "clawhub",
                        "message": f"Registered {skill_id} from ClawHub"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# U4B: NpmAdapter
# ═══════════════════════════════════════════════════════════════

class NpmAdapter(BaseMarketAdapter):
    """npm 包市场适配器

    通过 npm registry API 搜索和安装 npm 包为技能。
    API: https://registry.npmjs.org/-/v1/search
    """

    REGISTRY_URL = "https://registry.npmjs.org/-/v1/search"

    @property
    def market_name(self) -> str:
        return "npm"

    @property
    def market_display(self) -> str:
        return "npm"

    @property
    def market_icon(self) -> str:
        return "📦"

    def search(self, query: str, top_k: int = 10, **filters) -> List[MarketSkillEntry]:
        try:
            resp = requests.get(
                self.REGISTRY_URL,
                params={"text": query, "size": top_k},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                objects = data.get("objects", [])
                results = []
                for obj in objects[:top_k]:
                    pkg = obj.get("package", {})
                    results.append(MarketSkillEntry(
                        skill_id=pkg.get("name", ""),
                        name=pkg.get("name", ""),
                        description=pkg.get("description", ""),
                        category="dev",
                        tags=pkg.get("keywords", []),
                        author=pkg.get("publisher", {}).get("username", ""),
                        version=pkg.get("version", "0.1.0"),
                        market="npm",
                        url=pkg.get("links", {}).get("npm", ""),
                        rating=0.0,
                        downloads=0,
                    ))
                return results
        except Exception as e:
            logger.debug(f"npm search failed: {e}")

        # Fallback: 使用 npx adapter
        try:
            from .npx_adapter import NpxAdapter
            na = NpxAdapter()
            info = na.resolve(query)
            return [MarketSkillEntry(
                skill_id=info.name,
                name=info.name,
                description=info.description,
                category="dev",
                tags=info.keywords,
                author=info.author,
                version=info.version,
                market="npm",
                url=f"npm://{info.name}",
            )]
        except Exception:
            pass
        return []

    def install(self, skill_id: str, **options) -> Dict[str, Any]:
        try:
            # 委托给 npx adapter (完整 SkillSpec 构建)
            from .npx_adapter import NpxAdapter
            adapter = NpxAdapter()
            return adapter.install_from_uri(f"npx://{skill_id}")
        except Exception as e:
            return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# U4B: PyPIAdapter
# ═══════════════════════════════════════════════════════════════

class PyPIAdapter(BaseMarketAdapter):
    """PyPI 包市场适配器

    通过 PyPI JSON API 搜索和安装 Python 包为技能。
    API: https://pypi.org/pypi/{package}/json
    """

    SEARCH_URL = "https://pypi.org/pypi"

    @property
    def market_name(self) -> str:
        return "pypi"

    @property
    def market_display(self) -> str:
        return "PyPI"

    @property
    def market_icon(self) -> str:
        return "🐍"

    def search(self, query: str, top_k: int = 10, **filters) -> List[MarketSkillEntry]:
        # 精确搜索单个包
        try:
            resp = requests.get(
                f"{self.SEARCH_URL}/{query}/json",
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                info = data.get("info", {})
                return [MarketSkillEntry(
                    skill_id=info.get("name", query),
                    name=info.get("name", query),
                    description=(info.get("summary") or "")[:200],
                    category="dev",
                    tags=[c.strip() for c in (info.get("classifiers") or []) if "Topic" in c][:5],
                    author=info.get("author", ""),
                    version=info.get("version", "0.1.0"),
                    market="pypi",
                    url=info.get("project_url", ""),
                    rating=0.0,
                    downloads=0,
                )]
        except Exception as e:
            logger.debug(f"PyPI search failed for {query}: {e}")
        return []

    def install(self, skill_id: str, **options) -> Dict[str, Any]:
        try:
            from zenskill.core.skill_spec import SkillSpec, CapabilitySpec
            from zenskill.core.skill_types import SkillType

            # 获取 PyPI 元数据
            meta = self.fetch_meta(skill_id)

            spec = SkillSpec(
                id=f"pypi-{skill_id}",
                name=skill_id,
                description=meta.description if meta else f"PyPI package: {skill_id}",
                category="dev",
                skill_type=SkillType.EXECUTION,
                tags=meta.tags if meta else [],
                author=meta.author if meta else "",
                version=meta.version if meta else "0.1.0",
                source="market",
                source_market="pypi",
                source_url=f"pypi://{skill_id}",
                source_format="setup.py/pyproject.toml",
                runtime_deps=[skill_id],
                requires={"python": ">=3.9"},
                capabilities=[CapabilitySpec(
                    name=skill_id,
                    description=meta.description if meta else f"pip install {skill_id}",
                    proficiency=0.7,
                    keywords=[skill_id, "python"],
                )],
            )
            spec.save()
            return {"success": True, "skill_id": spec.id, "method": "pypi"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def fetch_meta(self, skill_id: str) -> Optional[MarketSkillEntry]:
        results = self.search(skill_id, top_k=1)
        return results[0] if results else None


# ═══════════════════════════════════════════════════════════════
# P3-2: SkillsShAdapter — skills.sh (Agent Skills Directory)
# ═══════════════════════════════════════════════════════════════

class SkillsShAdapter(BaseMarketAdapter):
    """skills.sh 市场适配器 (https://skills.sh)

    API v1: /api/v1/skills/search、/api/v1/skills?view=、/api/v1/skills/{id}
    匿名访问受限速约束；401/403 时静默返回空，
    可经 SKILLS_SH_TOKEN 环境变量注入 Bearer token。
    安装委托 GitHub 安装管线（skills.sh 条目均源自 GitHub 仓库）。
    """

    BASE_URL = "https://skills.sh/api/v1"

    @property
    def market_name(self) -> str:
        return "skillssh"

    @property
    def market_display(self) -> str:
        return "skills.sh"

    @property
    def market_icon(self) -> str:
        return "🌐"

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        token = os.environ.get("SKILLS_SH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _to_entry(s: Dict[str, Any]) -> MarketSkillEntry:
        source = s.get("source", "")
        return MarketSkillEntry(
            skill_id=s.get("id", ""),
            name=s.get("slug") or s.get("name", ""),
            description=f"GitHub: {source}" if source else "",
            author=source.split("/")[0] if source else "",
            market="skillssh",
            url=s.get("url") or s.get("installUrl", ""),
            downloads=int(s.get("installs", 0) or 0),
        )

    def search(self, query: str, top_k: int = 10, **filters) -> List[MarketSkillEntry]:
        if len(query.strip()) < 2:
            return []
        try:
            resp = requests.get(
                f"{self.BASE_URL}/skills/search",
                params={"q": query, "limit": min(top_k, 200)},
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code in (401, 403):
                logger.warning("skills.sh search rejected (HTTP %s); set SKILLS_SH_TOKEN", resp.status_code)
                return []
            if resp.status_code != 200:
                return []
            data = resp.json().get("data", [])
            return [self._to_entry(s) for s in data[:top_k]]
        except Exception as e:
            logger.debug(f"skills.sh search failed: {e}")
            return []

    def trending(self, view: str = "trending", top_k: int = 20) -> List[MarketSkillEntry]:
        """排行榜（all-time / trending / hot）"""
        try:
            resp = requests.get(
                f"{self.BASE_URL}/skills",
                params={"view": view, "per_page": min(top_k, 500)},
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code != 200:
                return []
            data = resp.json().get("data", [])
            return [self._to_entry(s) for s in data[:top_k]]
        except Exception as e:
            logger.debug(f"skills.sh trending failed: {e}")
            return []

    def fetch_meta(self, skill_id: str) -> Optional[MarketSkillEntry]:
        try:
            resp = requests.get(
                f"{self.BASE_URL}/skills/{skill_id}",
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            entry = self._to_entry(data)
            files = data.get("files") or []
            if files:
                entry.description += f"（{len(files)} 个文件）"
            return entry
        except Exception as e:
            logger.debug(f"skills.sh fetch_meta failed: {e}")
            return None

    def install(self, skill_id: str, **options) -> Dict[str, Any]:
        parts = skill_id.split("/")
        if len(parts) < 2:
            return {"success": False, "error": f"Invalid skills.sh id: {skill_id}"}
        from .github_installer import install_github_skill

        return install_github_skill(parts[0], parts[1])


# ═══════════════════════════════════════════════════════════════
# P3-2: GitHubSearchAdapter — GitHub 技能仓库搜索
# ═══════════════════════════════════════════════════════════════

class GitHubSearchAdapter(BaseMarketAdapter):
    """GitHub 技能仓库搜索 (api.github.com/search/repositories)

    搜索优先 agent-skills topic，其次 claude-skills topic，最后全站；
    安装复用 github_installer 完整分析管线。
    可经 GITHUB_TOKEN 环境变量提升速率限额。
    """

    API_URL = "https://api.github.com/search/repositories"
    TOPICS = ["agent-skills", "claude-skills"]

    @property
    def market_name(self) -> str:
        return "github"

    @property
    def market_display(self) -> str:
        return "GitHub"

    @property
    def market_icon(self) -> str:
        return "🐙"

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def search(self, query: str, top_k: int = 10, **filters) -> List[MarketSkillEntry]:
        queries = [f"{query} topic:{t}" for t in self.TOPICS] + [query]
        seen: set = set()
        entries: List[MarketSkillEntry] = []

        for q in queries:
            if len(entries) >= top_k:
                break
            try:
                resp = requests.get(
                    self.API_URL,
                    params={"q": q, "sort": "stars", "per_page": top_k},
                    headers=self._headers(),
                    timeout=10,
                )
                if resp.status_code != 200:
                    continue
                for item in resp.json().get("items", []):
                    full_name = item.get("full_name", "")
                    if not full_name or full_name in seen:
                        continue
                    seen.add(full_name)
                    entries.append(MarketSkillEntry(
                        skill_id=full_name,
                        name=item.get("name", full_name),
                        description=(item.get("description") or "")[:200],
                        category="dev",
                        author=item.get("owner", {}).get("login", ""),
                        market="github",
                        url=item.get("html_url", ""),
                        downloads=int(item.get("stargazers_count", 0) or 0),
                    ))
            except Exception as e:
                logger.debug(f"github search failed ({q}): {e}")

        return entries[:top_k]

    def fetch_meta(self, skill_id: str) -> Optional[MarketSkillEntry]:
        results = self.search(skill_id.split("/")[-1] if "/" in skill_id else skill_id, top_k=5)
        for r in results:
            if r.skill_id.lower() == skill_id.lower():
                return r
        return None

    def install(self, skill_id: str, **options) -> Dict[str, Any]:
        parts = skill_id.split("/")
        if len(parts) != 2:
            return {"success": False, "error": f"Invalid GitHub repo: {skill_id}"}
        from .github_installer import install_github_skill

        return install_github_skill(parts[0], parts[1])


# ═══════════════════════════════════════════════════════════════
# SkillHubAdapter — skillhub.cn（专为中国用户优化的 AI 技能社区）
# ═══════════════════════════════════════════════════════════════

class SkillHubAdapter(BaseMarketAdapter):
    """skillhub.cn 市场适配器

    后端: https://api.skillhub.cn（可经 SKILLHUB_API_BASE 覆盖）
    公开列表/详情匿名可用；SKILLHUB_TOKEN 可选注入 Bearer（登录态/配额）。
    凭据只从环境变量读取，源码/测试不含凭据字面量。

    条目为「技能集」(skillset)，自带完整 SKILL.md 内容（content 字段），
    安装时落地为本地技能目录并经 from_skill_md 转换注册。
    """

    DEFAULT_BASE = "https://api.skillhub.cn"

    @property
    def market_name(self) -> str:
        return "skillhub"

    @property
    def market_display(self) -> str:
        return "SkillHub"

    @property
    def market_icon(self) -> str:
        return "⭐"

    def _base(self) -> str:
        return os.environ.get("SKILLHUB_API_BASE", self.DEFAULT_BASE).rstrip("/")

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        token = os.environ.get("SKILLHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _to_entry(s: Dict[str, Any]) -> MarketSkillEntry:
        slug = s.get("slug", "")
        tags = [s["subScene"]] if s.get("subScene") else []
        return MarketSkillEntry(
            skill_id=slug,
            name=s.get("displayName") or slug,
            description=(s.get("summary") or s.get("summaryEn") or "")[:200],
            category=s.get("scene", "general"),
            tags=tags,
            author="SkillHub",
            version="0.1.0",
            market="skillhub",
            url=f"https://skillhub.cn/skills/{slug}" if slug else "",
            downloads=int(s.get("skillCount") or 0),
        )

    def search(self, query: str, top_k: int = 10, **filters) -> List[MarketSkillEntry]:
        params: Dict[str, Any] = {"page": 1, "pageSize": min(top_k, 50)}
        if query.strip():
            params["keyword"] = query.strip()
        try:
            resp = requests.get(
                f"{self._base()}/api/v1/skillsets",
                params=params,
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code != 200:
                return []
            data = resp.json().get("skillSets", [])
            return [self._to_entry(s) for s in data[:top_k]]
        except Exception as e:
            logger.debug(f"skillhub search failed: {e}")
            return []

    def top(self, top_k: int = 20) -> List[MarketSkillEntry]:
        """榜单（skillhub 精选，按站点排序）"""
        return self.search("", top_k=top_k)

    def fetch_meta(self, skill_id: str) -> Optional[MarketSkillEntry]:
        slug = skill_id.split("/")[-1]
        try:
            resp = requests.get(
                f"{self._base()}/api/v1/skillsets/{slug}",
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            entry = self._to_entry(resp.json())
            entry.description = (resp.json().get("summary") or entry.description)[:200]
            return entry
        except Exception as e:
            logger.debug(f"skillhub fetch_meta failed: {e}")
            return None

    def fetch_content(self, slug: str) -> Optional[str]:
        """拉取技能集的完整 SKILL.md 内容"""
        try:
            resp = requests.get(
                f"{self._base()}/api/v1/skillsets/{slug}",
                headers=self._headers(),
                timeout=15,
            )
            if resp.status_code != 200:
                return None
            content = resp.json().get("content") or ""
            return content or None
        except Exception as e:
            logger.debug(f"skillhub fetch_content failed: {e}")
            return None

    def install(self, skill_id: str, **options) -> Dict[str, Any]:
        if "/" in skill_id or skill_id in ("", ".", ".."):
            return {"success": False, "error": f"Invalid SkillHub slug: {skill_id}"}
        slug = skill_id
        content = self.fetch_content(slug)
        if not content:
            return {"success": False, "error": f"SkillHub content unavailable: {skill_id}"}

        from pathlib import Path

        from ..core.paths import safe_child_path
        from .skillmd_converter import from_skill_md

        skills_dir = Path.home() / ".zenskill" / "skills"
        target = safe_child_path(skills_dir, f"skillhub-{slug}")
        target.mkdir(parents=True, exist_ok=True)
        (target / "SKILL.md").write_text(content, encoding="utf-8")

        spec = from_skill_md(target)
        if spec is None:
            return {"success": False, "error": f"Invalid SKILL.md content from SkillHub: {slug}"}
        spec.source = "market"
        spec.source_market = "skillhub"
        spec.source_url = f"https://skillhub.cn/skills/{slug}"
        spec.save()

        return {
            "success": True,
            "skill_id": spec.id,
            "method": "skillhub-content",
            "path": str(target),
        }


# ═══════════════════════════════════════════════════════════════
# CozeMarketAdapter — 扣子技能目录（@coze/cli 桥接）
# ═══════════════════════════════════════════════════════════════

class CozeMarketAdapter(BaseMarketAdapter):
    """扣子市场适配器（账号作用域，经官方 @coze/cli）

    发现: coze code skill list -p <projectId> 返回项目可用技能目录
          （含 skill_id/name/description/is_installed），按关键词过滤。
    安装: coze code skill add <skillId> -p <projectId>（挂载到扣子项目会话）。
    上下文: project_id 参数 > COZE_PROJECT_ID 环境变量 > 第一个项目。
    认证: 复用 coze CLI 的 OAuth 登录态（无额外凭据字面量）。
    边界: CLI 无技能内容导出——商店技能的 SKILL.md 反向拉取不可用，
          待官方开放 API（见 docs/skill_optimization_plan_v2.md P3-2）。
    """

    network_lazy = True  # 子进程+账号网络，不参与 all 聚合，仅显式 --market coze

    def __init__(self):
        from ..platforms.coze import CozeAdapter

        self._cli = CozeAdapter()

    @property
    def market_name(self) -> str:
        return "coze"

    @property
    def market_display(self) -> str:
        return "Coze 扣子"

    @property
    def market_icon(self) -> str:
        return "🎯"

    def _resolve_project(self, project_id: Optional[str] = None) -> Optional[str]:
        if project_id:
            return project_id
        env_pid = os.environ.get("COZE_PROJECT_ID")
        if env_pid:
            return env_pid

        r = self._cli._run("code", "project", "list", timeout=30)
        if r is None or r.returncode != 0:
            return None
        try:
            projects = json.loads(r.stdout)
            if isinstance(projects, list) and projects:
                return str(projects[0].get("id", ""))
        except json.JSONDecodeError:
            pass
        return None

    def _list_catalog(self, project_id: str) -> List[Dict[str, Any]]:
        r = self._cli._run("code", "skill", "list", "-p", project_id, timeout=30)
        if r is None or r.returncode != 0:
            return []
        try:
            data = json.loads(r.stdout)
            items = data.get("items", data) if isinstance(data, dict) else data
            return items if isinstance(items, list) else []
        except json.JSONDecodeError:
            return []

    @staticmethod
    def _to_entry(s: Dict[str, Any], project_id: str) -> MarketSkillEntry:
        return MarketSkillEntry(
            skill_id=str(s.get("skill_id", "")),
            name=s.get("name", ""),
            description=(s.get("description") or "")[:200],
            category="coze",
            tags=["installed"] if s.get("is_installed") else [],
            author="Coze",
            market="coze",
            url=f"https://www.coze.cn/skills",
            rating=1.0 if s.get("is_installed") else 0.0,
        )

    def search(self, query: str, top_k: int = 10, project_id: str = None, **filters) -> List[MarketSkillEntry]:
        if not self._cli._ready():
            logger.warning("coze 市场不可用: npm i -g @coze/cli && coze auth login --oauth")
            return []

        pid = self._resolve_project(project_id)
        if not pid:
            logger.warning("coze 市场需要项目上下文: 设置 COZE_PROJECT_ID 或先创建项目")
            return []

        q = query.strip().lower()
        entries = []
        for s in self._list_catalog(pid):
            if not s.get("skill_id"):
                continue
            if q:
                name = (s.get("name") or "").lower()
                desc = (s.get("description") or "").lower()
                if q not in name and q not in desc:
                    continue
            entries.append(self._to_entry(s, pid))
            if len(entries) >= top_k:
                break
        return entries

    def catalog(self, top_k: int = 30, project_id: str = None) -> List[MarketSkillEntry]:
        """项目完整技能目录（含已装标记）"""
        return self.search("", top_k=top_k, project_id=project_id)

    def fetch_meta(self, skill_id: str) -> Optional[MarketSkillEntry]:
        pid = self._resolve_project()
        if not pid:
            return None
        for s in self._list_catalog(pid):
            if str(s.get("skill_id")) == str(skill_id):
                return self._to_entry(s, pid)
        return None

    def install(self, skill_id: str, project_id: str = None, **options) -> Dict[str, Any]:
        if not self._cli._ready():
            return {"success": False,
                    "error": "coze CLI 未安装或未登录: npm i -g @coze/cli && coze auth login --oauth"}

        pid = self._resolve_project(project_id)
        if not pid:
            return {"success": False, "error": "缺少扣子项目上下文（COZE_PROJECT_ID 或 project_id）"}

        r = self._cli._run("code", "skill", "add", str(skill_id), "-p", pid, timeout=60)
        if r is None or r.returncode != 0:
            detail = (r.stderr if r else "").strip()[:200]
            return {"success": False, "error": f"coze skill add 失败: {detail or 'CLI 不可用'}"}

        return {
            "success": True,
            "skill_id": str(skill_id),
            "method": "coze-skill-add",
            "project_id": pid,
        }
