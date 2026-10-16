"""
MarketSourceRegistry — 市场源注册表（W1，方案第三章 A）

三层来源:
  builtin  内置六源（skillhub/github/skillssh/npm/pypi/clawhub，映射到
           market_adapters 现有适配器类；enable 可经 markets.yaml 覆盖）
  config   ~/.zenskill/markets.yaml 用户配置源（generic-http → GenericHTTPAdapter）
  runtime  代码注册（register()，兼容 UniversalSkillInstaller.register_adapter）

安全（评审 S2）:
  - add_source schema 白名单校验；明文 token 字段（token/api_key/...）直接拒绝，
    提示改用 auth.token_env
  - search/meta/download URL 过 SSRF 校验（assert_public_http_url）
  - token_env 引用高价值凭据变量（OPENAI_API_KEY 等）拒绝

首次 load 时 markets.yaml 不存在则写入内置六源默认配置（clawhub 默认 disable，
方案 1.3：端点持续不可达）。健康检查结果仅内存返回，不落库。

用法:
    from zenskill.skills.market_registry import get_default_registry
    reg = get_default_registry()
    reg.list_sources()
    reg.add_source({...})
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .universal_installer import BaseMarketAdapter

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 内置六源（enable 按方案 1.3 市场源真实状态表）
# ═══════════════════════════════════════════════════════════════

BUILTIN_SOURCES: List[Dict[str, Any]] = [
    {"name": "skillhub", "enable": True, "display": "SkillHub"},    # 主力源
    {"name": "github", "enable": True, "display": "GitHub"},        # 主力源
    {"name": "skillssh", "enable": True, "display": "skills.sh"},   # 可选，需 token
    {"name": "npm", "enable": True, "display": "npm"},              # 保留
    {"name": "pypi", "enable": True, "display": "PyPI"},            # 保留
    # ClawHub 端点持续不可达 → 默认禁用，保留降级链（可 enable 恢复）
    {"name": "clawhub", "enable": False, "display": "ClawHub"},
]
BUILTIN_SOURCE_NAMES = frozenset(s["name"] for s in BUILTIN_SOURCES)

# 内置源 token 环境变量（展示健康状态用；凭据本身由各适配器自行读取）
_BUILTIN_TOKEN_ENV: Dict[str, str] = {
    "skillhub": "SKILLHUB_TOKEN",
    "skillssh": "SKILLS_SH_TOKEN",
    "github": "GITHUB_TOKEN",
}

# 健康探测端点（HEAD，5s 超时；任何 HTTP 应答即视为可达）
_BUILTIN_PROBE_URLS: Dict[str, str] = {
    "skillhub": "https://api.skillhub.cn",
    "github": "https://api.github.com",
    "skillssh": "https://skills.sh",
    "npm": "https://registry.npmjs.org",
    "pypi": "https://pypi.org",
    "clawhub": "https://registry.clawhub.io",
}

# ═══════════════════════════════════════════════════════════════
# schema 校验
# ═══════════════════════════════════════════════════════════════

_SOURCE_KEYS = frozenset({
    "name", "type", "enable", "display",
    "search_url", "meta_url", "download_url", "field_mapping", "auth",
})
_AUTH_KEYS = frozenset({"type", "token_env", "header"})
_FIELD_MAPPING_KEYS = frozenset({"results", "skill_id", "name", "description", "tags"})
# 明文凭据字段黑名单：出现即拒收，提示改 token_env（评审 S2）
_PLAINTEXT_TOKEN_KEYS = frozenset({
    "token", "token_value", "api_key", "secret", "password",
    "client_secret", "access_token",
})
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class MarketSourceError(ValueError):
    """市场源配置/操作错误；errors 携带结构化错误列表（MCP/CLI 透传）"""

    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors: List[str] = list(errors) if errors else [message]


def validate_source_config(config: Any, *, allow_private: bool = False) -> List[str]:
    """generic-http 源配置 schema 校验，返回错误列表（空即通过）"""
    from .market_generic import (
        MarketSSRFError,
        TokenEnvForbiddenError,
        assert_public_http_url,
        check_token_env,
    )

    errors: List[str] = []
    if not isinstance(config, dict):
        return ["源配置必须为对象（dict）"]

    unknown = set(config) - _SOURCE_KEYS
    if unknown:
        errors.append(f"未支持字段: {sorted(unknown)}（允许: {sorted(_SOURCE_KEYS)}）")

    for key in sorted(set(config) & _PLAINTEXT_TOKEN_KEYS):
        errors.append(
            f"检测到明文 token 字段「{key}」: 配置禁止存明文凭据，"
            f"请改用 auth.token_env 引用环境变量")

    auth = config.get("auth")
    if auth is not None:
        if not isinstance(auth, dict):
            errors.append("auth 必须为对象（type/token_env/header）")
        else:
            for key in sorted(set(auth) & _PLAINTEXT_TOKEN_KEYS):
                errors.append(
                    f"auth.{key} 为明文 token: 请改用 auth.token_env 引用环境变量")
            auth_unknown = set(auth) - _AUTH_KEYS
            if auth_unknown:
                errors.append(
                    f"auth 未支持字段: {sorted(auth_unknown)}（允许: {sorted(_AUTH_KEYS)}）")
            if auth.get("type") not in ("bearer", "header"):
                errors.append("auth.type 必须为 bearer 或 header")
            token_env = auth.get("token_env")
            if not token_env:
                errors.append("auth.token_env 必填（token 只认环境变量引用）")
            else:
                try:
                    check_token_env(str(token_env))
                except TokenEnvForbiddenError as e:
                    errors.append(str(e))
                except ValueError as e:
                    errors.append(str(e))

    name = config.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name or ""):
        errors.append("name 必填，格式: 字母/数字开头，仅含字母数字/_/-（≤64 字符）")
    elif name in BUILTIN_SOURCE_NAMES:
        errors.append(
            f"内置源 {name} 不可经 add_source 添加/覆盖，请用 enable/disable 或健康检查管理")

    if config.get("type", "generic-http") != "generic-http":
        errors.append("type 必须为 generic-http")

    search_url = config.get("search_url")
    if not search_url:
        errors.append("search_url 必填（http(s) 模板，支持 {query}/{top_k} 占位）")
    elif isinstance(search_url, str):
        if "{query}" not in search_url and "{top_k}" not in search_url:
            errors.append("search_url 应包含 {query} 或 {top_k} 占位符")

    for ukey in ("search_url", "meta_url", "download_url"):
        url = config.get(ukey)
        if url is None:
            continue
        if not isinstance(url, str):
            errors.append(f"{ukey} 必须为字符串 URL 模板")
            continue
        try:
            assert_public_http_url(url, allow_private=allow_private)
        except MarketSSRFError as e:
            errors.append(f"{ukey} SSRF 校验失败: {e}")

    if config.get("enable") is not None and not isinstance(config.get("enable"), bool):
        errors.append("enable 必须为布尔值")

    fm = config.get("field_mapping")
    if fm is not None:
        if not isinstance(fm, dict):
            errors.append("field_mapping 必须为对象（results/skill_id/name/description/tags）")
        else:
            bad_keys = set(fm) - _FIELD_MAPPING_KEYS
            if bad_keys:
                errors.append(
                    f"field_mapping 未支持字段: {sorted(bad_keys)}"
                    f"（允许: {sorted(_FIELD_MAPPING_KEYS)}）")
            for k, v in fm.items():
                if k in _FIELD_MAPPING_KEYS and (not isinstance(v, str) or not v.strip()):
                    errors.append(f"field_mapping.{k} 必须为非空字符串（响应字段名）")

    return errors


# ═══════════════════════════════════════════════════════════════
# MarketSourceRegistry
# ═══════════════════════════════════════════════════════════════

class MarketSourceRegistry:
    """市场源注册表：内置源 + markets.yaml 配置源 + 运行时注册"""

    HEALTH_TIMEOUT = 5.0

    def __init__(self, config_path: Optional[Path] = None, *,
                 allow_private: bool = False,
                 include_builtin: bool = True):
        self._path = (Path(config_path) if config_path
                      else Path.home() / ".zenskill" / "markets.yaml")
        # allow_private 仅供本地 fixture 测试；配置路径恒为 False（评审 S2）
        self._allow_private = allow_private
        # include_builtin=False 仅用于测试隔离（聚合测试不得真实外呼内置源）
        self._include_builtin = include_builtin
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._runtime: Dict[str, BaseMarketAdapter] = {}
        self._adapter_cache: Dict[str, BaseMarketAdapter] = {}
        self._loaded = False

    # ── 加载/持久化 ──

    def load(self) -> None:
        """读 markets.yaml + 内置默认；文件不存在时写入内置六源默认配置"""
        entries: Dict[str, Dict[str, Any]] = {}
        if self._include_builtin:
            for s in BUILTIN_SOURCES:
                entries[s["name"]] = {
                    "name": s["name"], "display": s["display"], "type": "builtin",
                    "enable": bool(s["enable"]), "origin": "builtin", "config": {},
                }

        data: Dict[str, Any] = {}
        if self._path.exists():
            try:
                raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
                if isinstance(raw, dict):
                    data = raw
            except yaml.YAMLError as e:
                logger.warning("markets.yaml 解析失败，回退内置默认: %s", e)
        else:
            self._write_yaml(entries=entries)
            logger.info("已生成默认市场源配置: %s", self._path)

        for item in (data.get("sources") or []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name or not _NAME_RE.match(name):
                logger.warning("markets.yaml 跳过非法源条目: %r", item.get("name"))
                continue
            if name in BUILTIN_SOURCE_NAMES:
                # 内置源条目仅允许覆盖 enable/display
                if name not in entries:
                    continue
                if item.get("enable") is not None:
                    entries[name]["enable"] = bool(item.get("enable"))
                if item.get("display"):
                    entries[name]["display"] = str(item["display"])
                continue
            errors = validate_source_config(item, allow_private=self._allow_private)
            entries[name] = {
                "name": name,
                "display": str(item.get("display") or name),
                "type": str(item.get("type", "generic-http")),
                "enable": bool(item.get("enable", True)),
                "origin": "config",
                "config": item,
                "error": "; ".join(errors) or None,
            }
            if errors:
                logger.warning("markets.yaml 源 %s 配置无效（已停用）: %s", name, entries[name]["error"])

        self._entries = entries
        self._loaded = True

    def _write_yaml(self, entries: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        """原子写回 markets.yaml：内置六源（enable 覆盖）+ 配置源全量"""
        entries = entries if entries is not None else self._entries
        sources: List[Dict[str, Any]] = []
        for s in BUILTIN_SOURCES:
            entry = entries.get(s["name"], {})
            item: Dict[str, Any] = {
                "name": s["name"],
                "enable": bool(entry.get("enable", s["enable"])),
            }
            if entry.get("display") and entry["display"] != s["display"]:
                item["display"] = entry["display"]
            sources.append(item)
        for entry in entries.values():
            if entry.get("origin") == "config":
                cfg = dict(entry.get("config") or {})
                cfg["enable"] = bool(entry.get("enable", True))
                sources.append(cfg)
        payload = {"sources": sources}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".yaml.tmp")
        tmp.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        tmp.replace(self._path)

    # ── 源管理 ──

    def register(self, adapter: BaseMarketAdapter) -> None:
        """代码注册（运行时源；兼容 UniversalSkillInstaller.register_adapter）"""
        name = adapter.market_name
        self._runtime[name] = adapter
        self._entries[name] = {
            "name": name,
            "display": getattr(adapter, "market_display", name),
            "type": "runtime", "enable": True, "origin": "runtime", "config": {},
        }
        self._adapter_cache[name] = adapter

    def add_source(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """热添加 generic-http 源 → 校验 → 写回 yaml（明文 token/SSRF 不过即拒绝）"""
        if not self._loaded:
            self.load()
        errors = validate_source_config(config, allow_private=self._allow_private)
        if errors:
            raise MarketSourceError(
                "市场源配置校验失败: " + "; ".join(errors), errors)
        name = str(config["name"])
        if name in self._entries:
            raise MarketSourceError(
                f"市场源已存在: {name}（如需更新请先 remove）",
                [f"name 冲突: {name}"])

        from .market_generic import GenericHTTPAdapter
        try:
            GenericHTTPAdapter(dict(config), allow_private=self._allow_private)
        except Exception as e:
            raise MarketSourceError(f"适配器构建失败: {e}", [str(e)]) from e

        entry = {
            "name": name,
            "display": str(config.get("display") or name),
            "type": "generic-http",
            "enable": bool(config.get("enable", True)),
            "origin": "config",
            "config": dict(config),
            "error": None,
        }
        self._entries[name] = entry
        self._write_yaml()
        return {"name": name, "enable": entry["enable"],
                "type": "generic-http", "origin": "config"}

    def remove_source(self, name: str) -> Dict[str, Any]:
        """移除配置源；内置源只允许 disable 不可删"""
        if not self._loaded:
            self.load()
        entry = self._entries.get(name)
        if entry is None:
            raise MarketSourceError(f"市场源不存在: {name}")
        if entry.get("origin") == "builtin":
            raise MarketSourceError(
                f"内置源 {name} 不可删除，仅可停用: zenskill market disable {name}",
                [f"内置源仅支持 enable/disable（当前 enable={entry.get('enable')}）"])
        origin = entry.get("origin")
        del self._entries[name]
        self._runtime.pop(name, None)
        self._adapter_cache.pop(name, None)
        if origin == "config":
            self._write_yaml()
        return {"removed": name, "origin": origin}

    def set_enable(self, name: str, enable: bool) -> Dict[str, Any]:
        """启停源；内置源写覆盖条目到 yaml，配置源更新其 enable 字段"""
        if not self._loaded:
            self.load()
        entry = self._entries.get(name)
        if entry is None:
            raise MarketSourceError(f"市场源不存在: {name}")
        if entry.get("origin") == "runtime":
            raise MarketSourceError(
                f"运行时源 {name} 随代码注册，不支持 enable/disable")
        entry["enable"] = bool(enable)
        self._adapter_cache.pop(name, None)
        self._write_yaml()
        return {"name": name, "enable": bool(enable)}

    # ── 查询/适配器 ──

    def get(self, name: str) -> Optional[BaseMarketAdapter]:
        """取源适配器；禁用/配置错误的源返回 None"""
        entry = self._entries.get(name)
        if entry is None:
            return None
        if not entry.get("enable") or entry.get("error"):
            return None
        if name in self._adapter_cache:
            return self._adapter_cache[name]
        adapter = self._build_adapter(entry)
        if adapter is not None:
            self._adapter_cache[name] = adapter
        return adapter

    def _build_adapter(self, entry: Dict[str, Any]) -> Optional[BaseMarketAdapter]:
        if entry.get("origin") == "runtime":
            return self._runtime.get(entry["name"])
        if entry.get("type") == "builtin":
            from . import market_adapters as ma
            cls = {
                "clawhub": ma.ClawHubAdapter,
                "npm": ma.NpmAdapter,
                "pypi": ma.PyPIAdapter,
                "skillssh": ma.SkillsShAdapter,
                "github": ma.GitHubSearchAdapter,
                "skillhub": ma.SkillHubAdapter,
            }.get(entry["name"])
            return cls() if cls else None
        from .market_generic import GenericHTTPAdapter
        return GenericHTTPAdapter(entry.get("config") or {},
                                  allow_private=self._allow_private)

    def adapters(self) -> Dict[str, BaseMarketAdapter]:
        """全部启用且配置有效源的适配器（名称 → adapter）"""
        out: Dict[str, BaseMarketAdapter] = {}
        for name, entry in self._entries.items():
            if not entry.get("enable") or entry.get("error"):
                continue
            try:
                adapter = self.get(name)
            except Exception as e:
                logger.warning("市场源 %s 适配器构建失败: %s", name, e)
                continue
            if adapter is not None:
                out[name] = adapter
        return out

    def _token_env(self, entry: Dict[str, Any]) -> Optional[str]:
        if entry.get("origin") == "builtin":
            return _BUILTIN_TOKEN_ENV.get(entry["name"])
        auth = (entry.get("config") or {}).get("auth") or {}
        return auth.get("token_env") if isinstance(auth, dict) else None

    def list_sources(self) -> List[Dict[str, Any]]:
        """源清单：名称/类型/enable/token 状态/来源（builtin|config|runtime）"""
        out: List[Dict[str, Any]] = []
        ordered = sorted(
            self._entries.values(),
            key=lambda e: (e.get("origin") != "builtin", e["name"]))
        for entry in ordered:
            token_env = self._token_env(entry)
            item = {
                "name": entry["name"],
                "display": entry.get("display", entry["name"]),
                "type": entry.get("type", "generic-http"),
                "enable": bool(entry.get("enable")),
                "origin": entry.get("origin", "config"),
                "token_env": token_env,
                "token_set": bool(token_env and os.environ.get(token_env)),
            }
            if entry.get("error"):
                item["error"] = entry["error"]
            out.append(item)
        return out

    def health_check(self, name: Optional[str] = None) -> List[Dict[str, Any]]:
        """逐源健康探测（5s 超时）：内置源 HEAD 探测端点，配置/运行时源空查询搜索。

        结果仅内存返回，不落库。内置源探测真实网络，测试环境慎用无参全量调用。
        """
        if not self._loaded:
            self.load()
        if name is not None and name not in self._entries:
            raise MarketSourceError(f"市场源不存在: {name}")
        targets = ([self._entries[name]] if name
                   else [e for e in self._entries.values() if e.get("enable")])
        return [self._probe(entry) for entry in targets]

    def _probe(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "name": entry["name"],
            "enable": bool(entry.get("enable")),
            "reachable": False,
            "latency_ms": None,
            "auth": "anonymous",
        }
        token_env = self._token_env(entry)
        if token_env:
            result["auth"] = "authorized" if os.environ.get(token_env) else "anonymous"

        start = time.time()
        try:
            if entry.get("type") == "builtin" and entry.get("origin") == "builtin":
                import requests
                url = _BUILTIN_PROBE_URLS.get(entry["name"])
                if not url:
                    result["error"] = "无探测端点"
                    return result
                requests.head(url, timeout=self.HEALTH_TIMEOUT,
                              allow_redirects=False)
            else:
                adapter = self.get(entry["name"])
                if adapter is None:
                    result["error"] = "适配器不可用（源禁用或配置错误）"
                    return result
                adapter.search("", top_k=1)
        except Exception as e:
            result["latency_ms"] = int((time.time() - start) * 1000)
            result["error"] = f"{type(e).__name__}: {e}"[:200]
            return result
        result["reachable"] = True
        result["latency_ms"] = int((time.time() - start) * 1000)
        return result


# ═══════════════════════════════════════════════════════════════
# 进程级默认注册表 + 聚合搜索（MCP market_search / CLI 共用）
# ═══════════════════════════════════════════════════════════════

_DEFAULT_REGISTRY: Optional[MarketSourceRegistry] = None


def get_default_registry() -> MarketSourceRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = MarketSourceRegistry()
        _DEFAULT_REGISTRY.load()
    return _DEFAULT_REGISTRY


def reset_default_registry() -> None:
    """测试辅助：清空进程级默认注册表单例（HOME 隔离场景下重载）"""
    global _DEFAULT_REGISTRY
    _DEFAULT_REGISTRY = None


def _entry_payload(e: Any) -> Dict[str, Any]:
    return {
        "skill_id": e.skill_id,
        "name": e.name,
        "description": (e.description or "")[:120],
        "market": e.market,  # 市场徽章
        "url": getattr(e, "url", ""),
        "downloads": getattr(e, "downloads", 0),
        "rating": getattr(e, "rating", 0.0),
        "tags": list(getattr(e, "tags", None) or [])[:5],
    }


def search_markets_aggregated(
    query: str,
    market: str = "all",
    top_k: int = 10,
    timeout: float = 8.0,
    registry: Optional[MarketSourceRegistry] = None,
) -> Dict[str, Any]:
    """跨市场聚合搜索（方案 7.1 market_search）。

    每源并行、单源 timeout 秒上限——最慢源只标 degraded 不拖垮整体；
    单源异常/超时计入 sources_status，绝不抛错。
    """
    import concurrent.futures

    reg = registry if registry is not None else get_default_registry()
    sources = {s["name"]: s for s in reg.list_sources()}
    aggregate_all = market in ("all", "", None)

    if not aggregate_all:
        if market not in sources:
            return {"ok": False, "error": f"未知市场源: {market}",
                    "available": sorted(sources)}
        names = [market]
    else:
        names = [n for n, s in sources.items()
                 if s["enable"] and not s.get("error")]

    status: Dict[str, Any] = {}
    adapters: Dict[str, BaseMarketAdapter] = {}
    for n in names:
        s = sources[n]
        if not s["enable"]:
            status[n] = {"status": "disabled",
                         "message": "源已停用（zenskill market enable 启用）"}
            continue
        try:
            adapter = reg.get(n)
        except Exception as e:
            status[n] = {"status": "degraded",
                         "error": f"{type(e).__name__}: {e}"[:200]}
            continue
        if adapter is None:
            status[n] = {"status": "unavailable",
                         "error": s.get("error") or "适配器不可用"}
            continue
        if aggregate_all and getattr(type(adapter), "network_lazy", False) is True:
            status[n] = {"status": "skipped",
                         "message": "network_lazy 源不参与聚合，请显式指定 market"}
            continue
        adapters[n] = adapter

    entries: List[Any] = []
    if adapters:
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=len(adapters))
        try:
            futures = {n: pool.submit(a.search, query, top_k)
                       for n, a in adapters.items()}
            for n, fut in futures.items():
                try:
                    found = fut.result(timeout=timeout) or []
                    entries.extend(found)
                    status[n] = {"status": "ok", "count": len(found)}
                except concurrent.futures.TimeoutError:
                    fut.cancel()
                    status[n] = {"status": "degraded",
                                 "error": f"单源超时（>{timeout:g}s）"}
                except Exception as e:
                    status[n] = {"status": "degraded",
                                 "error": f"{type(e).__name__}: {e}"[:200]}
        finally:
            # 不等待悬挂线程（单源内部超时兜底会自行结束）
            pool.shutdown(wait=False)

    entries.sort(key=lambda e: (getattr(e, "rating", 0.0) or 0.0,
                                getattr(e, "downloads", 0) or 0), reverse=True)
    top = entries[: int(top_k)]
    return {
        "ok": True,
        "query": query,
        "market": market or "all",
        "count": len(top),
        "results": [_entry_payload(e) for e in top],
        "sources_status": status,
    }
