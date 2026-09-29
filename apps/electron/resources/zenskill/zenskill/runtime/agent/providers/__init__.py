"""Provider 层：ModelConfig、模型解析与 StreamFn 分发。

一条 OpenAI-compatible 代码路径覆盖 deepseek/openai/volc/qwen（对齐 pi 的
洞察：底层 API 只有四种），Anthropic Messages 单独一条。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ..types import Usage


@dataclass
class ModelConfig:
    id: str
    api: str                 # "openai-completions" | "anthropic-messages"
    provider: str            # deepseek/openai/anthropic/volc/qwen/faux
    base_url: str
    api_key: Optional[str] = None
    api_key_env: str = ""
    max_output_tokens: int = 8192
    cost_input_per_m: float = 0.0   # $/1M input tokens
    cost_output_per_m: float = 0.0  # $/1M output tokens
    supports_vision: bool = False    # 是否支持图片输入（P1-2）
    supports_json: bool = True       # 是否支持 response_format json_object（P1-2）
    supports_thinking_control: bool = False  # 是否支持 thinking 参数开关（成本优化）
    sock_read_timeout: int = 600     # SSE 流空闲读超时（秒），按模型/网关可调（O7）

    def estimate_cost(self, usage: Usage) -> float:
        return (
            usage.input / 1_000_000 * self.cost_input_per_m
            + usage.output / 1_000_000 * self.cost_output_per_m
        )


_REGISTRY: Dict[str, Dict[str, Any]] = {
    "deepseek": {
        "api": "openai-completions",
        "base_url": "https://api.deepseek.com/v1",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "api_key_env": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-v4-flash",
        "model_env": "DEEPSEEK_MODEL",
        "thinking_control": True,
    },
    "anthropic": {
        "api": "anthropic-messages",
        "base_url": "https://api.anthropic.com",
        "base_url_env": "ANTHROPIC_BASE_URL",
        "api_key_env": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-5",
        "model_env": "ANTHROPIC_MODEL",
        "supports_vision": True,
    },
    "openai": {
        "api": "openai-completions",
        "base_url": "https://api.openai.com/v1",
        "base_url_env": "OPENAI_BASE_URL",
        "api_key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4o-mini",
        "model_env": "OPENAI_MODEL",
        "supports_vision": True,
    },
    "volc": {
        "api": "openai-completions",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "base_url_env": "ARK_BASE_URL",
        "api_key_env": "ARK_API_KEY",
        "default_model": "doubao-pro-32k",
        "model_env": "ARK_MODEL",
    },
    "qwen": {
        "api": "openai-completions",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "base_url_env": "DASHSCOPE_BASE_URL",
        "api_key_env": "DASHSCOPE_API_KEY",
        "default_model": "qwen-plus",
        "model_env": "DASHSCOPE_MODEL",
    },
    # MiMo 开放平台（OpenAI 兼容端点 api.xiaomimimo.com/v1）。
    # 注意：token-plan-cn.xiaomimimo.com/anthropic 是另一套鉴权体系，
    # 开放平台 key 在该端点 401 —— 不要混用（2026-09-29 实测）。
    "mimo": {
        "api": "openai-completions",
        "base_url": "https://api.xiaomimimo.com/v1",
        "base_url_env": "MIMO_BASE_URL",
        "api_key_env": "MIMO_API_KEY",
        "default_model": "mimo-v2.6-flash",
        "model_env": "MIMO_MODEL",
    },
    "gemini": {
        "api": "openai-completions",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "base_url_env": "GEMINI_BASE_URL",
        "api_key_env": "GEMINI_API_KEY",
        "default_model": "gemini-2.0-flash",
        "model_env": "GEMINI_MODEL",
        "supports_vision": True,
    },
    "ollama": {
        "api": "openai-completions",
        "base_url": "http://localhost:11434/v1",
        "base_url_env": "OLLAMA_HOST",
        "api_key_env": "OLLAMA_API_KEY",
        "default_model": "llama3.2",
        "model_env": "OLLAMA_MODEL",
    },
}

_ENV_DETECT_ORDER = ["deepseek", "anthropic", "openai", "volc", "qwen", "gemini", "mimo", "ollama"]

SUSPECT_MODELS = {"test-model", "mock-gpt", "mock", "unknown", "未配置", ""}


def sanitize_model_name(name: Optional[str]) -> Optional[str]:
    """过滤占位/占位模型名，返回 None 表示应走环境变量/DB 探测路径。"""
    if not name or name.strip().lower() in SUSPECT_MODELS:
        return None
    return name


def _config_base_url(provider: str) -> Optional[str]:
    """llm_config 显式 base_url（且 provider 匹配）→ 注册表网关覆写来源。"""
    try:
        from zenskill.core.llm_config import llm_config
        cfg = llm_config.get()
        if cfg.provider == provider and cfg.base_url:
            return cfg.base_url.rstrip("/")
    except Exception:
        pass
    return None


def build_model_config(provider: str, model_id: Optional[str] = None,
                       api_key: Optional[str] = None,
                       base_url: Optional[str] = None) -> ModelConfig:
    entry = _REGISTRY[provider]
    resolved_model = model_id or os.getenv(entry["model_env"]) or entry["default_model"]
    resolved_key = api_key or os.getenv(entry["api_key_env"])
    # DeepSeek key 兼容：model-switcher 存为 DEEPSEEK_ANTHROPIC_AUTH_TOKEN
    if not resolved_key and provider == "deepseek":
        resolved_key = os.getenv("DEEPSEEK_ANTHROPIC_AUTH_TOKEN")
    # Gemini key 兼容：GOOGLE_API_KEY 是官方文档常见别名
    if not resolved_key and provider == "gemini":
        resolved_key = os.getenv("GOOGLE_API_KEY")
    # base_url 覆写链：显式参数（含 llm_config）> base_url_env 环境变量 > 注册表默认
    resolved_base = (base_url or "").strip().rstrip("/")
    if not resolved_base:
        base_env = entry.get("base_url_env")
        if base_env:
            resolved_base = os.getenv(base_env, "").strip().rstrip("/")
    if not resolved_base:
        resolved_base = entry["base_url"]
    if provider == "ollama" and not base_url:
        # Ollama 本地服务无需真实 key；OLLAMA_HOST 支持远程/自定义端口
        resolved_key = resolved_key or "ollama"
        host = os.getenv("OLLAMA_HOST", "").strip()
        if host:
            if not host.startswith(("http://", "https://")):
                host = "http://" + host
            resolved_base = host.rstrip("/") + ("/v1" if not host.rstrip("/").endswith("/v1") else "")
    if provider == "ollama":
        resolved_key = resolved_key or "ollama"
    return ModelConfig(
        id=resolved_model,
        api=entry["api"],
        provider=provider,
        base_url=resolved_base,
        api_key=resolved_key,
        api_key_env=entry["api_key_env"],
        supports_vision=bool(entry.get("supports_vision", False)),
        supports_json=bool(entry.get("supports_json", True)),
        supports_thinking_control=bool(entry.get("thinking_control", False)),
    )


def _provider_for_model_name(name: str) -> Optional[str]:
    if "/" in name:
        provider = name.split("/", 1)[0].strip().lower()
        if provider in _REGISTRY:
            return provider
    try:
        from zenskill.core.llm_config import get_model_info
        info = get_model_info(name)
    except Exception:
        return None
    if isinstance(info, dict):
        provider = str(info.get("provider", "")).lower()
        if provider in _REGISTRY:
            return provider
    return None


def resolve_model(name: Optional[str] = None) -> ModelConfig:
    """解析模型配置：provider/model 形式 > core.llm_config 目录 > 环境变量探测。"""
    name = sanitize_model_name(name)
    if name:
        provider = _provider_for_model_name(name)
        if provider is not None:
            model_id = name.split("/", 1)[1] if "/" in name else name
            # 注册表 provider + llm_config 显式 base_url（同 provider）→ 用户网关覆写
            return build_model_config(provider, model_id, base_url=_config_base_url(provider))
        # 未知模型名：按 OpenAI-compatible 兜底（自定义网关/自托管）
        return ModelConfig(
            id=name,
            api="openai-completions",
            provider="openai",
            base_url=os.getenv("OPENAI_BASE_URL") or _config_base_url("openai")
            or "https://api.openai.com/v1",
            api_key=os.getenv("OPENAI_API_KEY"),
            api_key_env="OPENAI_API_KEY",
        )
    explicit = os.getenv("ZENSKILL_AGENT_MODEL")
    if explicit:
        return resolve_model(explicit)
    # 用户显式配置（zenskill llm set / llm_config 切换）先于环境变量探测：
    # GUI 会把连接凭据注入为 DEEPSEEK_API_KEY 等环境变量，那是凭据载体而非
    # provider 选择信号，不应覆盖 llm_config 的显式 provider 切换
    try:
        from zenskill.core.llm_config import llm_config
        config = llm_config.get()
        if config.provider in _REGISTRY and config.api_key:
            return build_model_config(config.provider, config.model, config.api_key,
                                      base_url=config.base_url)
    except Exception:
        pass
    for provider in _ENV_DETECT_ORDER:
        env_name = _REGISTRY[provider]["api_key_env"]
        if os.getenv(env_name):
            return build_model_config(provider)
    # 兜底：llm_config 已配置 provider 但未显式存 key → 看该 provider 的环境变量
    # （lm-service 为自定义协议，agent 引擎暂不支持，见 docs/runtime_pi_reference_plan.md）
    try:
        from zenskill.core.llm_config import llm_config
        config = llm_config.get()
        if config.provider in _REGISTRY:
            env_name = _REGISTRY[config.provider]["api_key_env"]
            if config.api_key or os.getenv(env_name):
                return build_model_config(config.provider, config.model, config.api_key,
                                          base_url=config.base_url)
    except Exception:
        pass
    raise RuntimeError(
        "未找到可用的 LLM 凭据。请设置 DEEPSEEK_API_KEY / ANTHROPIC_API_KEY / "
        "OPENAI_API_KEY / ARK_API_KEY / DASHSCOPE_API_KEY，或用 --model 指定模型。"
    )


def apply_connection_env_overrides(cfg: ModelConfig) -> ModelConfig:
    """Desktop 连接级网关覆写：TS spawn 注入 ZENSKILL_AGENT_BASE_URL /
    ZENSKILL_AGENT_API（单引擎进程单连接，env 即连接作用域）。Server Mode
    不设这两个 env，路径不受影响。"""
    base = (os.getenv("ZENSKILL_AGENT_BASE_URL") or "").strip().rstrip("/")
    if base:
        cfg.base_url = base
    api = (os.getenv("ZENSKILL_AGENT_API") or "").strip()
    if api in ("openai-completions", "anthropic-messages") and api != cfg.api:
        cfg.api = api
    return cfg


def create_stream(model: ModelConfig) -> Callable[..., Any]:
    if model.api == "anthropic-messages":
        from .anthropic_messages import anthropic_stream
        return anthropic_stream
    from .openai_completions import openai_completions_stream
    return openai_completions_stream
