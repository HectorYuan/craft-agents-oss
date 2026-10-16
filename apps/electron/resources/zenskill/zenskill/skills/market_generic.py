"""
GenericHTTPAdapter — 配置驱动的通用 HTTP 市场源适配器（W1，方案 3.2）

markets.yaml 中 type: generic-http 的源零代码接入：
  search_url 模板（{query}/{top_k} 占位）GET → field_mapping 解析为 MarketSkillEntry，
  download 走 download_url 模板。

SSRF/token 防护（安全评审补强 S2，docs/skill_market_integration_plan.md 第四章）：
  - assert_public_http_url: host 全地址解析（getaddrinfo），任一命中私网/环回/
    链路本地（含 169.254.169.254）/IPv6 ULA/::1 即拒绝；仅允许 http(s)
  - 重定向不自动跟随（封住跳私网的主要变体）；每个 URL 每次请求前独立校验
  - token 仅附加到配置登记的 host:port（search/meta/download URL 的 netloc
    集合；同 host 不同端口的外部端点也拿不到 token）
  - token_env 指向高价值凭据变量（OPENAI_API_KEY/GITHUB_TOKEN 等）直接拒绝

用法:
    from zenskill.skills.market_generic import GenericHTTPAdapter
    adapter = GenericHTTPAdapter(config_dict)
    entries = adapter.search("pdf", top_k=10)
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlsplit

import requests

from .universal_installer import BaseMarketAdapter, MarketSkillEntry

logger = logging.getLogger(__name__)


class MarketSSRFError(ValueError):
    """SSRF 防护拦截（评审 S2）：非 http(s) 或私网/环回/链路本地目标"""


class TokenEnvForbiddenError(ValueError):
    """token_env 非法或指向高价值凭据变量（评审 S2）"""


class MarketRequestError(RuntimeError):
    """市场源请求失败（网络/状态码/解析）；聚合层捕获后标 degraded"""


# 高价值凭据拒绝清单：这些变量属于宿主/云凭据，被诱导外发给任意市场源
# 即凭据泄漏，token_env 引用直接拒绝（评审 S2）
FORBIDDEN_TOKEN_ENVS = frozenset({
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    "AWS_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID", "AWS_SESSION_TOKEN",
    "GITHUB_TOKEN", "GH_TOKEN",
    "GOOGLE_API_KEY", "GEMINI_API_KEY",
    "AZURE_CLIENT_SECRET", "AZURE_STORAGE_KEY",
    "SLACK_TOKEN", "HF_TOKEN", "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY", "ZHIPU_API_KEY", "MOONSHOT_API_KEY",
})

_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def check_token_env(token_env: str) -> str:
    """校验 token_env：合法变量名且不在高价值凭据拒绝清单"""
    name = str(token_env or "").strip()
    if not _ENV_NAME_RE.match(name):
        raise TokenEnvForbiddenError(f"非法 token_env 变量名: {name!r}")
    if name.upper() in FORBIDDEN_TOKEN_ENVS:
        raise TokenEnvForbiddenError(
            f"token_env {name} 属于高价值凭据拒绝清单"
            f"（OPENAI_API_KEY/GITHUB_TOKEN/AWS_SECRET_ACCESS_KEY 等），"
            f"禁止用于市场源；请为该源单独申请专用 token 变量")
    return name


def _normalize_netloc(url: str) -> str:
    """归一化为 host:port（默认端口补全），供 token 附着的登记匹配"""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:
        port = None
    if port is None:
        port = 443 if parts.scheme == "https" else 80
    return f"{host}:{port}"


def _banned_ip_reason(ip: Any) -> Optional[str]:
    if ip.version == 6 and getattr(ip, "ipv4_mapped", None) is not None:
        return _banned_ip_reason(ip.ipv4_mapped)
    if ip.is_loopback:
        return "环回地址（127/8、::1）"
    if ip.is_link_local:
        return "链路本地地址（169.254/16、fe80::/10，含云元数据端点 169.254.169.254）"
    if ip.is_private:
        return "私网地址（10/8、172.16/12、192.168/16、IPv6 ULA fc00::/7）"
    if ip.is_reserved:
        return "保留地址"
    if ip.is_multicast:
        return "组播地址"
    if ip.is_unspecified:
        return "未指定地址"
    if ip.version == 4 and ip in ipaddress.ip_network("0.0.0.0/8"):
        return "保留段 0.0.0.0/8"
    return None


def assert_public_http_url(url: str, *, allow_private: bool = False) -> None:
    """SSRF 防护（评审 S2）：仅 http(s)；host 全地址解析，任一命中封禁段即拒绝。

    - 域名经 socket.getaddrinfo 解析出全部地址逐一校验（多 A/AAAA 记录任一
      命中私网即拒绝，防 DNS 混杂）
    - allow_private 仅供本地测试 fixture 构造源使用；markets.yaml 配置路径
      永远以 False 调用（validate_source_config 白名单字段不含该开关）
    - 已知边界：requests 发起请求时会再次 DNS 解析，存在理论上的 rebinding
      窗口；W1 不做 IP pinning，重定向已禁用以封住主要跳变路径
    """
    try:
        parts = urlsplit(url)
    except ValueError as e:
        raise MarketSSRFError(f"URL 解析失败: {url!r} ({e})") from e
    if parts.scheme not in ("http", "https"):
        raise MarketSSRFError(
            f"仅允许 http(s) 协议: {parts.scheme or '(空)'} ({url})")
    host = parts.hostname
    if not host:
        raise MarketSSRFError(f"URL 缺少 host: {url}")
    try:
        port = parts.port
    except ValueError as e:
        raise MarketSSRFError(f"URL 端口非法: {url}") from e

    candidates: List[Any] = []
    try:
        candidates = [ipaddress.ip_address(host)]  # 字面 IP 直判
    except ValueError:
        try:
            infos = socket.getaddrinfo(
                host, port or 0, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise MarketSSRFError(f"host 解析失败: {host} ({e})") from e
        for info in infos:
            try:
                candidates.append(ipaddress.ip_address(info[4][0]))
            except ValueError:
                continue

    for ip in candidates:
        reason = _banned_ip_reason(ip)
        if reason and not allow_private:
            raise MarketSSRFError(
                f"目标 {ip}（{host}）为{reason}，拒绝请求（SSRF 防护，评审 S2）")


class GenericHTTPAdapter(BaseMarketAdapter):
    """配置即源的通用 HTTP 市场适配器（markets.yaml type: generic-http）

    config 字段（schema 校验见 market_registry.validate_source_config）:
      name/display/search_url/meta_url/download_url/field_mapping/auth
    """

    REQUEST_TIMEOUT = 8.0
    MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024  # 方案 ②fetch 资源上限对齐

    def __init__(self, config: Dict[str, Any], *, allow_private: bool = False):
        self._config = dict(config)
        self._name = str(config["name"])
        self._allow_private = allow_private

        fm = config.get("field_mapping") or {}
        self._fm_results = str(fm.get("results", "results") or "results")
        self._fm = {
            "skill_id": str(fm.get("skill_id", "id") or "id"),
            "name": str(fm.get("name", "name") or "name"),
            "description": str(fm.get("description", "description") or "description"),
            "tags": str(fm.get("tags", "tags") or "tags"),
        }

        self._auth = config.get("auth") or None
        if self._auth:
            check_token_env(str(self._auth.get("token_env", "")))

        # token 仅发往配置登记的 host:port（search/meta/download URL 的
        # netloc 集合；同 host 不同端口的外部端点也拿不到 token）
        self._auth_netlocs = {
            _normalize_netloc(u)
            for u in (
                config.get("search_url") or "",
                config.get("meta_url") or "",
                config.get("download_url") or "",
            ) if u
        }

    @property
    def market_name(self) -> str:
        return self._name

    @property
    def market_display(self) -> str:
        return str(self._config.get("display") or self._name)

    @property
    def market_icon(self) -> str:
        return "🔌"

    # ── 内部工具 ──

    def _render_url(self, template: str, **params: Any) -> str:
        values: Dict[str, Any] = {"query": "", "top_k": 10, "id": ""}
        for k, v in params.items():
            values[k] = quote(str(v), safe="") if k == "query" else v
        try:
            url = str(template).format(**values)
        except (KeyError, IndexError, ValueError) as e:
            raise MarketRequestError(f"URL 模板渲染失败: {template!r} ({e})") from e
        assert_public_http_url(url, allow_private=self._allow_private)
        return url

    def _token_headers(self, url: str) -> Dict[str, str]:
        if not self._auth:
            return {}
        if _normalize_netloc(url) not in self._auth_netlocs:
            return {}
        token = os.environ.get(str(self._auth["token_env"]), "")
        if not token:
            return {}
        if str(self._auth.get("type", "bearer")) == "header":
            return {str(self._auth.get("header") or "X-Auth-Token"): token}
        return {"Authorization": f"Bearer {token}"}

    def _request(self, url: str, *, stream: bool = False) -> requests.Response:
        try:
            resp = requests.get(
                url,
                headers={"Accept": "application/json", **self._token_headers(url)},
                timeout=self.REQUEST_TIMEOUT,
                allow_redirects=False,
                stream=stream,
            )
        except requests.RequestException as e:
            raise MarketRequestError(
                f"请求失败: {type(e).__name__}: {e}"[:300]) from e
        if 300 <= resp.status_code < 400:
            location = resp.headers.get("Location", "")
            raise MarketRequestError(
                f"HTTP {resp.status_code} 重定向不自动跟随"
                f"（Location: {location}）；如需该源请在配置登记最终域名")
        if resp.status_code != 200:
            raise MarketRequestError(f"HTTP {resp.status_code} ({url})")
        return resp

    def _to_entry(self, item: Any) -> Optional[MarketSkillEntry]:
        if not isinstance(item, dict):
            return None
        skill_id = str(item.get(self._fm["skill_id"], "") or "")
        if not skill_id:
            return None
        raw_tags = item.get(self._fm["tags"]) or []
        if not isinstance(raw_tags, list):
            raw_tags = [raw_tags]
        return MarketSkillEntry(
            skill_id=skill_id,
            name=str(item.get(self._fm["name"], "") or skill_id),
            description=str(item.get(self._fm["description"], "") or "")[:200],
            tags=[str(t) for t in raw_tags],
            market=self.market_name,
            url=str(item.get("url", "") or ""),
        )

    # ── BaseMarketAdapter 接口 ──

    def search(self, query: str, top_k: int = 10, **filters) -> List[MarketSkillEntry]:
        url = self._render_url(str(self._config["search_url"]),
                               query=query, top_k=int(top_k))
        resp = self._request(url)
        try:
            data = resp.json()
        except ValueError as e:
            raise MarketRequestError(f"响应非 JSON: {e}") from e
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get(self._fm_results, [])
        else:
            items = []
        if not isinstance(items, list):
            raise MarketRequestError(
                f"字段映射 results→{self._fm_results} 命中的不是列表")
        entries = [self._to_entry(it) for it in items[: int(top_k)]]
        return [e for e in entries if e is not None]

    def fetch_meta(self, skill_id: str) -> Optional[MarketSkillEntry]:
        template = self._config.get("meta_url")
        if template:
            resp = self._request(self._render_url(str(template), id=skill_id))
            try:
                item = resp.json()
            except ValueError as e:
                raise MarketRequestError(f"meta 响应非 JSON: {e}") from e
            return self._to_entry(item)
        for entry in self.search(skill_id, top_k=5):
            if entry.skill_id.lower() == str(skill_id).lower():
                return entry
        return None

    def download(self, skill_id: str, dest_dir: Optional[Path] = None) -> Path:
        """按 download_url 模板下载到本地（流式 + 50MB 上限）"""
        template = self._config.get("download_url")
        if not template:
            raise MarketRequestError("源未配置 download_url")
        url = self._render_url(str(template), id=skill_id)
        resp = self._request(url, stream=True)
        dest_root = (Path(dest_dir) if dest_dir
                     else Path.home() / ".zenskill" / "cache" / "markets")
        dest_root.mkdir(parents=True, exist_ok=True)
        dest = dest_root / f"{self.market_name}-{self.resolve_skill_id(skill_id)}.download"
        size = 0
        try:
            with open(dest, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > self.MAX_DOWNLOAD_BYTES:
                        raise MarketRequestError(
                            f"下载数据超过 {self.MAX_DOWNLOAD_BYTES // (1024 * 1024)}MB 上限，已中止")
                    fh.write(chunk)
        except Exception:
            dest.unlink(missing_ok=True)
            raise
        return dest

    def install(self, skill_id: str, **options) -> Dict[str, Any]:
        try:
            meta = self.fetch_meta(skill_id)
            from zenskill.core.skill_dao import SkillDAO
            sid = f"{self.market_name}-{self.resolve_skill_id(skill_id)}"
            SkillDAO.upsert(
                sid,
                name=(meta.name if meta else skill_id),
                source="market",
                source_market=self.market_name,
                source_url=(meta.url if meta else f"{self.market_name}://{skill_id}"),
                is_active=1,
            )
            return {"success": True, "skill_id": sid, "method": "generic-http",
                    "message": f"Registered {skill_id} from {self.market_display}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
