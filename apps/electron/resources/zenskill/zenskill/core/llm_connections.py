"""Server Mode LLM 连接存储层（docs/server_mode_llm_provider_plan.md W1）

三层分工（路线 A，自有轻量存储，不碰 desktop 的 credentials.enc）：
- 元数据  ~/.zenskill/llm_connections.json  连接列表 + 全局默认 slug（非机密）
- API key ~/.zenskill/llm-secrets.json      keyring 按 slug 存，0600（含 env_provider）
- 激活态  ~/.zenskill/llm_config.json       引擎 resolve_model 直接消费（provider/model/base_url/api_key）

GUI DTO 对齐 vendor LlmConnection / LlmConnectionWithStatus / LlmConnectionSetup。
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Optional, Tuple
from urllib.parse import urlparse

from . import llm_keyring
from .llm_config import LLMConfig, llm_config

# GUI piAuthProvider/preset key → 引擎注册表 provider
_ALIAS = {
    "google": "gemini",
    "openai-eu": "openai",
    "openai-us": "openai",
    "ollama-local": "ollama",
    "custom": "openai",
    "manifest": "openai",
}

# Server Mode 静态模型目录（C3）：模型选择器读 connection.models，连接无
# models 时按此回填（对齐 desktop backfillAllConnectionModels 语义）。
# deepseek 对齐前端 models-zenskill.ts；anthropic/openai 对齐 submit-helpers
# 的 COMPAT_*_DEFAULTS；mimo/volc/qwen/gemini/ollama 对齐引擎注册表与
# PREDEFINED_MODELS。全部走探活/真实请求验证，目录只影响 GUI 展示。
_MODEL_CATALOG: dict[str, list[str]] = {
    "deepseek": ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat",
                 "deepseek-reasoner"],
    "anthropic": ["claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-4-6",
                  "claude-haiku-4-5"],
    "openai": ["gpt-5.2-codex", "gpt-5.1-codex-mini", "gpt-4o", "gpt-4o-mini"],
    "volc": ["doubao-pro-32k", "doubao-lite-32k"],
    "qwen": ["qwen-max", "qwen-plus", "qwen-turbo"],
    "mimo": ["mimo-v2.5-pro", "mimo-v2.5"],
    "gemini": ["gemini-2.5-pro", "gemini-2.0-flash"],
    "ollama": ["llama3.2"],
}


def catalog_models(provider: Optional[str]) -> list[str]:
    """provider 的静态目录（provider/model 形式）；未知 provider 返回空。"""
    if not provider:
        return []
    return [f"{provider}/{m}" for m in _MODEL_CATALOG.get(provider, [])]


# 特殊认证/协议 preset：引擎无对应实现，setup 阶段显式拒绝（C4，探活诚实报错
# 的前置改进——用户在保存前就知道原因）
_UNSUPPORTED_PROVIDERS = {
    "amazon-bedrock": ("Server Mode 暂不支持 Amazon Bedrock（IAM 签名认证），"
                       "请改用 OpenAI/Anthropic 兼容网关端点"),
    "azure-openai-responses": ("Server Mode 暂不支持 Azure Responses 协议，"
                               "请改用 OpenAI 兼容网关端点"),
}


def _connections_path() -> Path:
    # 动态 HOME（同 llm_config/llm_keyring 教训），测试 autouse 隔离依赖此
    return Path.home() / ".zenskill" / "llm_connections.json"


def _registry() -> dict:
    from ..runtime.agent.providers import _REGISTRY
    return _REGISTRY


# A3 读缓存：path → (st_mtime_ns, st_size, data)。单请求链多次 load_store
# （list/get/setDefault/delete/refresh 各读一次）全量读 JSON 属浪费；stat
# 比对命中即返（copy 隔离——调用方 load 后 mutate 再 save 是既有约定，
# 返回同一对象会让未 save 的 mutate 污染缓存）。写路径同步更新缓存。
_STORE_CACHE: dict[str, tuple[int, int, dict]] = {}


def _empty_store() -> dict:
    return {"version": 1, "default": None, "connections": []}


def load_store() -> dict:
    import copy as _copy
    path = _connections_path()
    try:
        st = path.stat()
        key = str(path)
        cached = _STORE_CACHE.get(key)
        if cached is not None and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
            return _copy.deepcopy(cached[2])
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not a dict")
        data.setdefault("version", 1)
        data.setdefault("default", None)
        data.setdefault("connections", [])
        _STORE_CACHE[key] = (st.st_mtime_ns, st.st_size, data)
        return _copy.deepcopy(data)
    except FileNotFoundError:
        return _empty_store()
    except Exception:
        return _empty_store()


def _save_store(store: dict) -> None:
    import copy as _copy
    path = _connections_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    payload = json.dumps(store, indent=2, ensure_ascii=False)
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)
    try:
        st = path.stat()
        _STORE_CACHE[str(path)] = (st.st_mtime_ns, st.st_size, _copy.deepcopy(store))
    except OSError:
        _STORE_CACHE.pop(str(path), None)


# ─────────────────────────── CRUD ───────────────────────────

def list_connections() -> list[dict]:
    return list(load_store()["connections"])


def get_connection(slug: str) -> Optional[dict]:
    if not slug:
        return None
    for conn in load_store()["connections"]:
        if conn.get("slug") == slug:
            return conn
    return None


def get_default_slug() -> Optional[str]:
    return load_store().get("default")


def upsert_connection(conn: dict) -> Tuple[bool, Optional[str]]:
    slug = (conn.get("slug") or "").strip()
    if not slug:
        return False, "缺少连接标识 slug"
    store = load_store()
    existing = next((c for c in store["connections"] if c.get("slug") == slug), None)
    now = int(time.time() * 1000)
    if existing is not None:
        # 元数据更新（改名/模型列表等）：保留引擎解析结果，除非提供新解析输入
        for key in ("name", "models", "defaultModel", "baseUrl", "authType",
                    "customEndpoint", "modelSelectionMode", "piAuthProvider"):
            if key in conn and conn[key] is not None:
                existing[key] = conn[key]
        if any(k in conn for k in ("piAuthProvider", "baseUrl", "defaultModel", "customEndpoint")):
            engine = resolve_engine(conn)
            if engine.get("provider"):
                existing["engineProvider"] = engine["provider"]
                if engine.get("base_url") is not None:
                    existing["baseUrl"] = engine["base_url"]
        existing["updatedAt"] = now
    else:
        engine = resolve_engine(conn)
        record = {
            "slug": slug,
            "name": conn.get("name") or slug,
            "providerType": "zenskill",
            "authType": conn.get("authType") or "api_key",
            "engineProvider": engine.get("provider"),
            "baseUrl": engine.get("base_url") if engine.get("base_url") is not None
            else conn.get("baseUrl") or None,
            "models": conn.get("models") or [],
            "defaultModel": conn.get("defaultModel") or None,
            "customEndpoint": conn.get("customEndpoint") or None,
            "piAuthProvider": conn.get("piAuthProvider") or None,
            "modelSelectionMode": conn.get("modelSelectionMode") or None,
            "createdAt": now,
            "updatedAt": now,
        }
        store["connections"].append(record)
        if not store.get("default"):
            store["default"] = slug
    _save_store(store)
    return True, None


def delete_connection(slug: str) -> Tuple[bool, Optional[str]]:
    store = load_store()
    idx = next((i for i, c in enumerate(store["connections"]) if c.get("slug") == slug), None)
    if idx is None:
        return False, "连接不存在"
    if len(store["connections"]) <= 1:
        return False, "至少保留一条连接"
    store["connections"].pop(idx)
    llm_keyring.forget(slug)
    if store.get("default") == slug:
        store["default"] = store["connections"][0]["slug"]
        _activate(store["default"])
    _save_store(store)
    return True, None


def set_default(slug: str) -> Tuple[bool, Optional[str]]:
    store = load_store()
    if not any(c.get("slug") == slug for c in store["connections"]):
        return False, "连接不存在"
    store["default"] = slug
    _save_store(store)
    _activate(slug)
    return True, None


def mask_key(key: Optional[str]) -> Optional[str]:
    """对齐 desktop GET_API_KEY 掩码：前 7 + •••••••• + 后 4。"""
    if not key:
        return None
    if len(key) > 15:
        return key[:7] + "••••••••" + key[-4:]
    return "••••••••"


# ─────────────────────── 引擎 provider 解析 ───────────────────────

def _normalize_base(base: str, api: str) -> str:
    base = (base or "").strip().rstrip("/")
    if api == "openai-completions":
        parsed = urlparse(base)
        if not parsed.path or parsed.path == "/":
            base = base + "/v1"
    else:  # anthropic-messages：引擎拼 /v1/messages，剥用户多给的 /v1
        if base.endswith("/v1"):
            base = base[:-3].rstrip("/")
    return base


def _api_for(provider: str) -> Optional[str]:
    entry = _registry().get(provider)
    return entry.get("api") if entry else None


def _provider_for_base(base: str) -> Optional[str]:
    """base URL host/path 匹配注册表 → provider（anthropic_api_key 方法不带
    piAuthProvider，只能靠 baseUrl 识别官方端点，否则 api.anthropic.com 会被
    路径启发误判成 openai-compat）。"""
    reg = _registry()
    host = (urlparse(base).hostname or "").lower()
    path = urlparse(base).path.rstrip("/")
    for prov, entry in reg.items():
        reg_host = (urlparse(entry["base_url"]).hostname or "").lower()
        if host and reg_host and host == reg_host:
            return prov
    # 官方 anthropic 端点变体（带子路径）
    if "anthropic" in host or path.endswith("/anthropic"):
        return "anthropic"
    return None


def resolve_engine(setup: dict) -> dict:
    """GUI LlmConnectionSetup → {provider, base_url, api} 或 {error}。

    - 特殊认证 preset（Bedrock IAM / Azure Responses）显式 unsupported（C4）
    - customEndpoint 显式协议优先（baseUrl 必填）
    - 否则 piAuthProvider/模型前缀/baseUrl host 映射注册表；注册表 provider
      用注册表 base（除非用户改过 baseUrl 且 host 不同 → 视为网关覆写）
    - 非注册表 + baseUrl：路径含 /anthropic → anthropic 协议，否则 openai-compat
    """
    raw_pi = (setup.get("piAuthProvider") or "").strip().lower()
    unsupported = _UNSUPPORTED_PROVIDERS.get(raw_pi)
    if unsupported:
        return {"error": unsupported}

    custom = setup.get("customEndpoint") or {}
    api = custom.get("api")
    base = (setup.get("baseUrl") or "").strip()

    if api in ("anthropic-messages", "openai-completions"):
        if not base:
            return {"error": "自定义端点必须填写 baseUrl"}
        prov = "anthropic" if api == "anthropic-messages" else "openai"
        return {"provider": prov, "base_url": _normalize_base(base, api), "api": api}

    pi = raw_pi
    pi = _ALIAS.get(pi, pi)
    # 载荷兼容：LlmConnectionSetup 用 defaultModel/models，TestLlmConnectionParams 用 model
    model = (setup.get("defaultModel") or setup.get("model") or "").strip()
    if not model:
        models = setup.get("models") or []
        model = models[0] if models and isinstance(models[0], str) else ""
    prefix = model.split("/", 1)[0].lower() if "/" in model else ""

    reg = _registry()
    if pi in reg:
        prov = pi
    elif prefix in reg:
        prov = prefix
    elif base and (host_prov := _provider_for_base(base)):
        prov = host_prov
    elif base:
        if "/anthropic" in urlparse(base).path or base.endswith("/anthropic"):
            prov, api = "anthropic", "anthropic-messages"
        else:
            prov, api = "openai", "openai-completions"
    else:
        return {"error": f"Server Mode 暂不支持该提供商：{pi or model or 'unknown'}"}

    reg_api = _api_for(prov)
    if reg_api is None:
        reg_api = api or "openai-completions"
    if not base:
        return {"provider": prov, "base_url": None, "api": reg_api}

    normalized = _normalize_base(base, reg_api)
    # 注册表 provider + 用户 base 与注册表同 host → 视为预设默认值，用注册表完整路径
    reg_base = (reg.get(prov) or {}).get("base_url") or ""
    if reg_base and urlparse(reg_base).netloc == urlparse(normalized).netloc:
        normalized = None  # 引擎走注册表默认
    return {"provider": prov, "base_url": normalized, "api": reg_api}


# ─────────────────────── setup / 激活 ───────────────────────

def env_conflict_warning() -> Optional[str]:
    conflicts = [k for k in ("LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL")
                 if os.environ.get(k)]
    if conflicts:
        return (f"环境变量 {', '.join(conflicts)} 优先级高于文件配置，"
                f"下次启动仍会覆盖本次保存")
    return None


def _is_loopback(base: Optional[str]) -> bool:
    if not base:
        return False
    try:
        host = urlparse(base).hostname or ""
    except Exception:
        return False
    return host in ("localhost", "127.0.0.1", "::1", "0.0.0.0")


def _activate(slug: str) -> None:
    """连接 → llm_config 激活态 + 进程内 env 注入（引擎 resolve_model 消费）。"""
    conn = get_connection(slug)
    if not conn or not conn.get("engineProvider"):
        return
    provider = conn["engineProvider"]
    if provider not in _registry():
        return
    secret = llm_keyring.get_secret(slug) or {}
    key = secret.get("api_key")
    model = (conn.get("defaultModel") or "").strip()
    if "/" in model and model.split("/", 1)[0].lower() == provider:
        model = model.split("/", 1)[1]
    cfg = llm_config.load()
    cfg.provider = provider
    cfg.model = model or cfg.model
    cfg.base_url = conn.get("baseUrl") or None
    cfg.api_key = key
    llm_config.save(cfg)
    if key:
        os.environ[llm_keyring.env_name_for(provider)] = key


def setup_connection(setup: dict, slug_override: Optional[str] = None) -> dict:
    """settings:setupLlmConnection 实现：落盘 key + 元数据 + 首连/更新默认时激活。"""
    slug = (slug_override or setup.get("slug") or "").strip()
    engine = resolve_engine(setup)
    if engine.get("error"):
        return {"success": False, "error": engine["error"]}
    provider = engine["provider"]
    base = engine.get("base_url")

    credential = (setup.get("credential") or "").strip()
    loopback = _is_loopback(setup.get("baseUrl") or base)
    existing_key = ((llm_keyring.get_secret(slug) or {}).get("api_key")
                    if slug else None)

    if not credential and not loopback and not existing_key:
        return {"success": False, "error": "请填写 API Key"}
    if setup.get("updateOnly") and not any(
            c.get("slug") == slug for c in load_store()["connections"]):
        return {"success": False, "error": "连接不存在"}
    if not slug:
        return {"success": False, "error": "缺少连接标识 slug"}

    if credential:
        llm_keyring.set_secret(slug, credential, base_url=base,
                               model=setup.get("defaultModel"), env_provider=provider)

    record = {
        "slug": slug,
        "name": setup.get("name") or _default_name(provider, setup),
        "authType": "none" if loopback and not credential else "api_key",
        "piAuthProvider": setup.get("piAuthProvider") or None,
        "customEndpoint": setup.get("customEndpoint") or None,
        "defaultModel": setup.get("defaultModel") or None,
        "models": setup.get("models") or [],
        "engineProvider": provider,
        "baseUrl": base,
    }
    ok, err = upsert_connection(record)
    if not ok:
        return {"success": False, "error": err}

    # 首个连接或更新的是当前默认 → 激活
    store = load_store()
    if store.get("default") in (slug, None):
        _activate(slug)

    result: dict = {"success": True}
    warning = env_conflict_warning()
    if warning:
        result["warning"] = warning
    return result


def _default_name(provider: str, setup: dict) -> str:
    custom = setup.get("customEndpoint") or {}
    if custom.get("api") == "anthropic-messages":
        return "Custom Anthropic-Compatible"
    if custom.get("api") == "openai-completions" or (
            setup.get("baseUrl") and provider == "openai"):
        return "Custom OpenAI-Compatible"
    return {
        "anthropic": "Anthropic (API Key)",
        "deepseek": "DeepSeek",
        "openai": "OpenAI",
        "gemini": "Google AI Studio",
        "mimo": "Mimo",
        "ollama": "Ollama (Local)",
    }.get(provider, provider.title())


async def test_connection_params(params: dict) -> dict:
    """settings:testLlmConnectionSetup 实现（真探活，见 probe）。

    载荷键对齐前端 TestLlmConnectionParams：{provider, apiKey, baseUrl, model,
    piAuthProvider, customEndpoint}。
    """
    key = (params.get("apiKey") or "").strip()
    base = (params.get("baseUrl") or "").strip()
    engine = resolve_engine(params)
    if engine.get("error"):
        return {"success": False, "error": engine["error"]}
    loopback = _is_loopback(base)
    if not key and not loopback:
        return {"success": False, "error": "请填写 API Key"}
    model = ((params.get("model") or params.get("defaultModel") or "").strip()
             or None)
    cfg = _build_config(engine["provider"], model, key, engine.get("base_url"))
    ok, err = await probe(cfg)
    return {"success": True} if ok else {"success": False, "error": err}


def _build_config(provider: str, model: Optional[str], key: Optional[str],
                   base: Optional[str]):
    from ..runtime.agent.providers import build_model_config
    if not key and _is_loopback(base):
        key = "local"
    if provider == "ollama" and not key:
        key = "ollama"
    return build_model_config(provider, model, api_key=key or None, base_url=base)


def model_config_for_connection(slug: str, model_override: Optional[str] = None):
    """连接（+可选模型覆盖）→ 引擎 ModelConfig；无连接/无引擎 provider → None。"""
    conn = get_connection(slug) if slug else None
    if not conn or not conn.get("engineProvider"):
        return None
    provider = conn["engineProvider"]
    if provider not in _registry():
        return None
    secret = llm_keyring.get_secret(slug) or {}
    key = secret.get("api_key")
    model = (model_override or conn.get("defaultModel") or "").strip()
    if "/" in model and model.split("/", 1)[0].lower() == provider:
        model = model.split("/", 1)[1]
    return _build_config(provider, model or None, key, conn.get("baseUrl"))


async def probe(cfg, timeout: float = 20.0) -> Tuple[bool, Optional[str]]:
    """最小请求真探活：首事件 StreamStart → 成功；StreamError → 失败原因。"""
    from ..runtime.agent.providers import create_stream
    from ..runtime.agent.types import Context, StreamError, StreamDone, UserMessage

    if not cfg.api_key:
        return False, f"缺少 API Key：请设置 {cfg.api_key_env}"
    cfg.max_output_tokens = 16

    async def _run():
        stream_fn = create_stream(cfg)
        ctx = Context(messages=[UserMessage(content="ping")])
        async for ev in stream_fn(cfg, ctx, None):
            if isinstance(ev, StreamError):
                msg = getattr(ev.error, "error_message", None) or ev.reason
                return False, str(msg)
            # StreamStart / 任意非错误首事件 = HTTP 层 + 鉴权通过
            return True, None
        return False, "返回流为空"

    try:
        return await asyncio.wait_for(_run(), timeout=timeout)
    except asyncio.TimeoutError:
        return False, f"探活超时（{timeout}s）"
    except Exception as e:  # 网络层异常（流契约"永不抛"之外的边界）
        return False, str(e)


async def test_stored_connection(slug: str) -> dict:
    """LLM_Connection:test 实现：用已存凭据探活。"""
    conn = get_connection(slug)
    if not conn:
        return {"success": False, "error": "连接不存在"}
    cfg = model_config_for_connection(slug)
    if cfg is None:
        return {"success": False, "error": "连接缺少可解析的引擎提供商"}
    ok, err = await probe(cfg)
    return {"success": True} if ok else {"success": False, "error": err}


# refreshModels 外呼结果的进程级缓存：slug → (ts, models)。GUI 显式刷新
# 才外呼（list 不打网络），缓存挡住连续点击/多视图重复外呼。
_REFRESH_CACHE: dict[str, tuple[float, list[str]]] = {}
_REFRESH_TTL = 600.0  # 10min


def _static_models(conn: dict) -> list[str]:
    """静态目录兜底：_MODEL_CATALOG 优先，非注册表 provider 用
    PREDEFINED_MODELS + 连接自带列表合并。"""
    provider = conn.get("engineProvider")
    models = catalog_models(provider)
    if models:
        return models
    from .llm_config import PREDEFINED_MODELS
    models = list(conn.get("models") or [])
    for name, info in PREDEFINED_MODELS.items():
        if provider and info.get("provider") != provider:
            continue
        candidate = f"{provider}/{name}" if provider else name
        if candidate not in models:
            models.append(candidate)
    return models


async def _fetch_remote_models(conn: dict) -> Optional[list[str]]:
    """外呼 provider /models（P2-1 真实拉取，desktop getModelRefreshService
    对等物）。协议：openai-compat `GET {base}/models` → data[].id；
    anthropic `GET {base}/v1/models` → data[].id；ollama `GET {root}/api/tags`
    → models[].name。8s 超时；任何失败（网络/401/形状异常）返回 None 由
    调用方降级静态目录——刷新失败不阻断选择器可用性。"""
    import aiohttp
    provider = conn.get("engineProvider")
    secret = llm_keyring.get_secret(conn.get("slug") or "") or {}
    key = secret.get("api_key")
    api = _api_for(provider) or "openai-completions"
    base = (conn.get("baseUrl") or "").strip().rstrip("/")
    if not base:
        base = ((_registry().get(provider) or {}).get("base_url") or "").rstrip("/")
    if not base:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if provider == "ollama":
                root = base[:-3] if base.endswith("/v1") else base
                url, headers = f"{root}/api/tags", {}
            elif api == "anthropic-messages":
                url = f"{base}/v1/models"
                headers = {"x-api-key": key or "",
                           "anthropic-version": "2023-06-01"}
            else:
                url = f"{base}/models"
                headers = {"Authorization": f"Bearer {key}"} if key else {}
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
    except Exception:
        return None
    raw: list[str] = []
    if provider == "ollama":
        for m in (data.get("models") or []) if isinstance(data, dict) else []:
            name = m.get("name") or m.get("model")
            if name:
                raw.append(name if "/" in name else f"ollama/{name}")
    elif isinstance(data, dict):
        for m in data.get("data") or []:
            mid = m.get("id") if isinstance(m, dict) else None
            if mid:
                raw.append(mid if "/" in mid else f"{provider}/{mid}")
    # 去重保序
    seen: set = set()
    models = [m for m in raw if not (m in seen or seen.add(m))]
    return models or None


async def refresh_models(slug: str) -> dict:
    """LLM_Connection:refreshModels：真实拉取 provider /models（8s 超时），
    失败降级静态目录；进程级缓存 10min。回写连接（模型选择器读
    connection.models），返回 source=remote|cache|catalog 供前端/排障区分。"""
    conn = get_connection(slug)
    if not conn:
        return {"success": False, "error": "连接不存在"}
    cached = _REFRESH_CACHE.get(slug)
    if cached and time.time() - cached[0] < _REFRESH_TTL:
        models, source = cached[1], "cache"
    else:
        models = await _fetch_remote_models(conn)
        if models:
            _REFRESH_CACHE[slug] = (time.time(), models)
            source = "remote"
        else:
            # 外呼失败/超时/401 → 静态目录兜底（选择器永不空）
            models = _static_models(conn)
            source = "catalog"
    store = load_store()
    for c in store["connections"]:
        if c.get("slug") == slug:
            c["models"] = models
            break
    _save_store(store)
    return {"success": True, "models": models, "source": source}


def has_credentials() -> bool:
    """onboarding authState 用：keyring / 连接存储 / llm_config / env 任一有凭据。

    连接存储非空也算已配置——loopback（Ollama 等）连接无 key 但确实可用。
    """
    try:
        if any((llm_keyring.get_secret(s) or {}).get("api_key")
               for s in llm_keyring.stored_providers()):
            return True
        if list_connections():
            return True
        cfg = llm_config.load()
        if cfg.api_key and cfg.provider != "mock":
            return True
        return any(os.environ.get(e["api_key_env"])
                   for e in _registry().values())
    except Exception:
        return False
