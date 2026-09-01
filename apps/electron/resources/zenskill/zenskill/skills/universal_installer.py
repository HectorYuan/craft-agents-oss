"""
Phase E1A: 技能统一标识 + 市场适配 + 智能安装路由

组件:
  SkillURI              — 统一技能标识符 (github:// / clawhub:// / npm:// / ...)
  BaseMarketAdapter     — 外部市场适配器基类
  UniversalSkillInstaller — 9种来源智能路由

用法:
    from zenskill.skills.universal_installer import install_skill
    result = install_skill("github://user/repo")
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# SkillURI — 统一技能标识符
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SkillURI:
    """统一技能标识符

    格式: <scheme>://<market>/<skill_id>[@<version>]

    示例:
      github://user/repo@v1.0
      clawhub://markdown-to-pdf
      npm://chalk@^2.0
      pypi://requests
      https://github.com/user/repo    (自动识别)
      file:///path/to/skill
    """
    scheme: str       # "github" | "clawhub" | "npm" | "pypi" | "content" | "file" | "builtin"
    market: str       # market name
    skill_id: str     # skill identifier within the market
    version: Optional[str] = None

    @classmethod
    def parse(cls, uri: str) -> "SkillURI":
        """解析技能 URI 字符串"""
        uri = uri.strip()

        # 自动识别 GitHub HTTPS URL
        m = re.match(r'https?://github\.com/([^/]+)/([^/@#\s]+)/?', uri)
        if m:
            return cls("github", "github", f"{m.group(1)}/{m.group(2)}")

        # 标准 URI: <scheme>://[<market>/]<id>[@<version>]
        m = re.match(r'(\w+)://(?:(\w+)/)?([^@]+)(?:@(.+))?', uri)
        if m:
            return cls(m.group(1), m.group(2) or m.group(1), m.group(3), m.group(4))

        # 纯 GitHub owner/repo
        m = re.match(r'^([\w.-]+)/([\w.-]+)$', uri)
        if m:
            return cls("github", "github", f"{m.group(1)}/{m.group(2)}")

        raise ValueError(f"无法解析技能 URI: {uri}")

    @property
    def full_name(self) -> str:
        return f"{self.market}:{self.skill_id}"

    @property
    def install_key(self) -> str:
        safe = self.skill_id.replace("/", "-").replace(":", "-").replace(" ", "-").lower()
        return f"{self.market}-{safe}"

    def to_dict(self) -> dict:
        return {
            "scheme": self.scheme, "market": self.market,
            "skill_id": self.skill_id, "version": self.version,
            "full_name": self.full_name,
        }


# ═══════════════════════════════════════════════════════════════
# BaseMarketAdapter — 外部市场适配器基类
# ═══════════════════════════════════════════════════════════════

@dataclass
class MarketSkillEntry:
    """市场技能条目（未安装时的元数据）"""
    skill_id: str
    name: str
    description: str = ""
    category: str = "general"
    difficulty: str = "beginner"
    tags: List[str] = field(default_factory=list)
    author: str = ""
    version: str = "0.1.0"
    market: str = ""
    url: str = ""
    rating: float = 0.0
    downloads: int = 0

    def to_skill_uri(self) -> SkillURI:
        return SkillURI(self.market, self.market, self.skill_id)


class BaseMarketAdapter(ABC):
    """外部市场 → ZenSkill 适配器基类

    与 zenskill/platforms/base.py 的 PlatformAdapter 互补:
    - PlatformAdapter: ZenSkill → 外部平台 (安装到 Claude/Coze 等)
    - BaseMarketAdapter: 外部市场 → ZenSkill (从市场获取技能)

    network_lazy = True 的适配器（账号作用域/子进程/慢网络）不参与
    search_all_markets 聚合，仅在显式指定市场时调用。
    """

    network_lazy = False

    @property
    @abstractmethod
    def market_name(self) -> str: ...

    @property
    @abstractmethod
    def market_display(self) -> str: ...

    @property
    def market_icon(self) -> str:
        return "📦"

    def search(self, query: str, top_k: int = 10, **filters) -> List[MarketSkillEntry]:
        """在市场内搜索技能 (默认返回空)"""
        return []

    def fetch_meta(self, skill_id: str) -> Optional[MarketSkillEntry]:
        """获取技能元数据"""
        return None

    @abstractmethod
    def install(self, skill_id: str, **options) -> Dict[str, Any]:
        """安装技能到本地 ZenSkill"""
        ...

    def resolve_skill_id(self, raw: str) -> str:
        return raw.replace("/", "-").replace(":", "-").replace(" ", "-").lower()


class BuiltinMarketAdapter(BaseMarketAdapter):
    """内置技能市场适配器"""

    @property
    def market_name(self) -> str:
        return "builtin"

    @property
    def market_display(self) -> str:
        return "ZenSkill 内置"

    @property
    def market_icon(self) -> str:
        return "🏠"

    def search(self, query: str, top_k: int = 10, **filters) -> List[MarketSkillEntry]:
        try:
            from zenskill.skills.search_engine import SkillSearchEngine
            engine = SkillSearchEngine()
            results = engine.search(query, top_k=top_k)
            return [
                MarketSkillEntry(
                    skill_id=r.skill.skill_id, name=r.skill.name,
                    description=r.skill.description, category=r.skill.category,
                    difficulty=r.skill.difficulty, tags=r.skill.tags,
                    market="builtin", rating=r.skill.rating,
                )
                for r in results
            ]
        except Exception:
            return []

    def install(self, skill_id: str, **options) -> Dict[str, Any]:
        return {"success": True, "skill_id": skill_id, "method": "builtin",
                "message": "内置技能无需安装"}


# ═══════════════════════════════════════════════════════════════
# UniversalSkillInstaller — 智能安装路由
# ═══════════════════════════════════════════════════════════════

class UniversalSkillInstaller:
    """统一技能安装器 — 自动识别来源并路由到正确的安装策略

    9 种来源识别:
      1. github://user/repo@version  → GitHubSkillInstaller
      2. https://github.com/...       → (同上)
      3. clawhub://skill-name        → ClawHubAdapter
      4. npm://package@version       → NpmAdapter
      5. pypi://package              → PyPIAdapter
      6. https://blog.com/post       → ContentToSkillConverter
      7. file://*.pdf / *.md         → ContentToSkillConverter
      8. file://*.zenskill-package   → SkillPackage
      9. 其他                         → 尝试所有适配器搜索
    """

    def __init__(self):
        self._adapters: Dict[str, BaseMarketAdapter] = {
            "builtin": BuiltinMarketAdapter(),
        }
        self._init_market_adapters()

    def _init_market_adapters(self):
        """延迟加载外部市场适配器"""
        try:
            from .market_adapters import (
                ClawHubAdapter,
                NpmAdapter,
                PyPIAdapter,
                SkillsShAdapter,
                GitHubSearchAdapter,
                SkillHubAdapter,
                CozeMarketAdapter,
            )
            self._adapters["clawhub"] = ClawHubAdapter()
            self._adapters["npm"] = NpmAdapter()
            self._adapters["pypi"] = PyPIAdapter()
            self._adapters["skillssh"] = SkillsShAdapter()
            self._adapters["github"] = GitHubSearchAdapter()
            self._adapters["skillhub"] = SkillHubAdapter()
            self._adapters["coze"] = CozeMarketAdapter()
        except ImportError:
            pass

    def register_adapter(self, adapter: BaseMarketAdapter) -> None:
        self._adapters[adapter.market_name] = adapter

    def install(self, source: str, **options) -> Dict[str, Any]:
        """智能安装入口

        Returns:
            {"success": bool, "skill_id": str, "source": str, "method": str, ...}
        """
        start = time.time()
        parsed = self._classify_source(source)

        try:
            result = self._dispatch(parsed, source, **options)
            self._post_install(result)
            return {
                "success": True,
                "skill_id": result.get("skill_id", ""),
                "source": source,
                "method": parsed["type"],
                "elapsed_ms": int((time.time() - start) * 1000),
                **result,
            }
        except Exception as e:
            return {"success": False, "source": source, "error": str(e)}

    def _classify_source(self, source: str) -> Dict[str, str]:
        """分类安装来源"""
        # github://user/repo[@version]
        m = re.match(r'github://([^/]+)/([^@]+)(?:@(.+))?', source)
        if m:
            return {"type": "github", "owner": m.group(1),
                    "repo": m.group(2), "version": m.group(3)}

        # https://github.com/user/repo
        m = re.match(r'https?://github\.com/([^/]+)/([^/@#\s]+)/?', source)
        if m:
            return {"type": "github", "owner": m.group(1), "repo": m.group(2)}

        # HTTP(S) URL (必须在 market:// 之前检查)
        if source.startswith(("http://", "https://")):
            return {"type": "url", "url": source}

        # <market>://<id> (clawhub:// / npm:// / npx:// / pypi:// / file://)
        m = re.match(r'(\w+)://(.+)', source)
        if m:
            market = m.group(1)
            skill_id = m.group(2)
            if market == "file":
                return {"type": "file", "subtype": "content", "path": skill_id}
            if market == "npx":
                return {"type": "market", "market": "npx", "skill_id": skill_id}
            return {"type": "market", "market": market, "skill_id": skill_id}

        # 本地文件
        if os.path.exists(source):
            ext = os.path.splitext(source)[1]
            if ext in (".pdf", ".epub", ".md", ".txt", ".html"):
                return {"type": "file", "subtype": "content", "path": source}
            if ext == ".zenskill-package":
                return {"type": "file", "subtype": "package", "path": source}
            if os.path.isdir(source):
                return {"type": "file", "subtype": "directory", "path": source}

        # owner/repo 格式
        if re.match(r'^([\w.-]+)/([\w.-]+)$', source):
            m = re.match(r'^([\w.-]+)/([\w.-]+)$', source)
            return {"type": "github", "owner": m.group(1), "repo": m.group(2)}

        return {"type": "unknown", "query": source}

    def _dispatch(self, parsed: dict, source: str, **options) -> Dict[str, Any]:
        """路由到正确的安装策略"""
        ptype = parsed["type"]

        if ptype == "github":
            return self._install_github(
                parsed["owner"], parsed["repo"], parsed.get("version"), **options
            )
        elif ptype == "market":
            # npx:// → 特殊处理
            if parsed.get("market") == "npx":
                return self._install_from_npx(parsed.get("skill_id", ""), **options)
            return self._install_from_market(parsed["market"], parsed["skill_id"], **options)
        elif ptype == "url":
            return self._install_from_url(parsed["url"], **options)
        elif ptype == "file":
            return self._install_from_file(parsed.get("path", source), parsed.get("subtype", ""), **options)
        else:
            return self._search_and_install(parsed.get("query", source), **options)

    def _install_github(self, owner: str, repo: str, version: Optional[str] = None, **opts) -> Dict[str, Any]:
        """GitHub 安装 (Phase E2: 完整管线)"""
        import time
        start = time.time()
        try:
            from .github_installer import GitHubSkillInstaller
            installer = GitHubSkillInstaller()
            result = installer.install(owner, repo, version)
            result["elapsed_ms"] = int((time.time() - start) * 1000)
            return result
        except ImportError:
            # Fallback: minimal registration
            skill_id = f"github-{owner}-{repo}"
            from zenskill.core.skill_dao import SkillDAO
            SkillDAO.upsert(skill_id, name=f"{owner}/{repo}",
                           source="github", source_url=f"https://github.com/{owner}/{repo}",
                           category="dev", is_active=1)
            return {"success": True, "skill_id": skill_id, "source": "github",
                    "message": f"Registered {owner}/{repo} (GitHubInstaller not available)"}
        except Exception as e:
            return {"error": str(e)}

    def _install_from_market(self, market: str, skill_id: str, **opts) -> Dict[str, Any]:
        adapter = self._adapters.get(market)
        if adapter:
            return adapter.install(skill_id, **opts)
        # Try builtin search as fallback
        adapter = self._adapters.get("builtin")
        if adapter:
            return adapter.install(skill_id, **opts)
        return {"error": f"Unknown market: {market}"}

    def _install_from_npx(self, skill_id: str, **opts) -> Dict[str, Any]:
        """npx 技能安装 (Phase S5)"""
        import time
        start = time.time()
        try:
            from .npx_adapter import NpxAdapter
            adapter = NpxAdapter()
            result = adapter.install_from_uri(f"npx://{skill_id}")
            result["elapsed_ms"] = int((time.time() - start) * 1000)
            return result
        except ImportError:
            return {"error": "NpxAdapter not available"}
        except Exception as e:
            return {"error": str(e)}

    def _install_from_url(self, url: str, **opts) -> Dict[str, Any]:
        skill_id = f"content-{url.split('/')[-1][:30]}"
        try:
            from zenskill.core.skill_dao import SkillDAO
            SkillDAO.upsert(skill_id, name=skill_id, source="content",
                           source_url=url, is_active=1)
            return {"skill_id": skill_id, "method": "content",
                    "message": f"Registered from URL (full extraction via Phase E3)"}
        except Exception as e:
            return {"skill_id": skill_id, "error": str(e)}

    def _install_from_file(self, path: str, subtype: str, **opts) -> Dict[str, Any]:
        basename = os.path.basename(path)
        skill_id = f"file-{os.path.splitext(basename)[0][:30]}"

        if subtype == "package":
            try:
                from zenskill.skill_package import SkillPackage
                return SkillPackage().install(path)
            except Exception as e:
                return {"skill_id": skill_id, "error": str(e)}

        try:
            from zenskill.core.skill_dao import SkillDAO
            SkillDAO.upsert(skill_id, name=basename, source="content",
                           source_url=path, is_active=1)
            return {"skill_id": skill_id, "method": "content"}
        except Exception as e:
            return {"skill_id": skill_id, "error": str(e)}

    def _search_and_install(self, query: str, **opts) -> Dict[str, Any]:
        for name, adapter in self._adapters.items():
            results = adapter.search(query, top_k=1)
            if results:
                return adapter.install(results[0].skill_id, **opts)
        return {"error": f"No skill found for: {query}"}

    def _post_install(self, result: dict) -> None:
        """安装后自动重索引"""
        if not result.get("skill_id"):
            return
        try:
            from zenskill.skills.search_engine import SkillSearchEngine
            engine = SkillSearchEngine()
            engine.build_index()
        except Exception:
            pass

    def search_all_markets(self, query: str, top_k: int = 10) -> List[MarketSkillEntry]:
        """跨市场搜索（跳过 network_lazy 的账号作用域适配器，保持聚合快速离线）

        用 `is True` 严格判断: Mock(spec=Adapter) 会把类属性暴露为真值 Mock，
        必须与字面量 True 区分。
        """
        all_results = []
        for name, adapter in self._adapters.items():
            if getattr(type(adapter), "network_lazy", False) is True:
                continue
            try:
                results = adapter.search(query, top_k=top_k)
                all_results.extend(results)
            except Exception:
                continue
        all_results.sort(key=lambda r: r.rating, reverse=True)
        return all_results[:top_k]

    def list_markets(self) -> List[Dict[str, str]]:
        return [
            {"name": a.market_name, "display": a.market_display, "icon": a.market_icon}
            for a in self._adapters.values()
        ]


# 全局单例
universal_installer = UniversalSkillInstaller()


# ── 卸载 (U0E) ──

def uninstall_skill(skill_id: str, force: bool = False) -> Dict[str, Any]:
    """卸载技能 — SQLite CASCADE + 缓存清理

    Args:
        skill_id: 技能 ID
        force: 跳过确认

    Returns:
        {"success": bool, "skill_id": str, "cleaned": list, ...}
    """
    import shutil
    from pathlib import Path

    result = {"skill_id": skill_id, "success": False, "cleaned": []}

    try:
        from zenskill.core.skill_dao import SkillDAO

        # 检查是否存在
        if not SkillDAO.exists(skill_id):
            result["error"] = f"技能不存在: {skill_id}"
            return result

        # 获取技能信息用于清理
        info = SkillDAO.get(skill_id)
        name = info.get("name", skill_id) if info else skill_id

        # SQLite CASCADE 删除
        SkillDAO.delete(skill_id)
        result["cleaned"].append("database")

        # 清理技能目录
        skills_dir = Path.home() / ".zenskill" / "skills" / skill_id
        if skills_dir.exists():
            shutil.rmtree(skills_dir, ignore_errors=True)
            result["cleaned"].append("skill_dir")

        # 清理 GitHub 缓存 (如果是 github 来源)
        source = info.get("source", "") if info else ""
        if source == "github":
            cache_dir = Path.home() / ".zenskill" / "cache" / "github"
            for d in cache_dir.glob(f"*_{skill_id.split('-')[-1]}" if "-" in skill_id else f"*{skill_id}*"):
                if d.is_dir():
                    shutil.rmtree(d, ignore_errors=True)
                    result["cleaned"].append(f"cache:{d.name}")

        result["success"] = True
        result["name"] = name
        result["message"] = f"已卸载: {name}"
        return result

    except Exception as e:
        result["error"] = str(e)
        return result


def install_skill(source: str, **options) -> Dict[str, Any]:
    """快速安装入口"""
    return universal_installer.install(source, **options)


def search_markets(query: str, top_k: int = 10) -> List[MarketSkillEntry]:
    """跨市场搜索"""
    return universal_installer.search_all_markets(query, top_k=top_k)
