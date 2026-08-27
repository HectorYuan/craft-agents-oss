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

    def estimate_cost(self, usage: Usage) -> float:
        return (
            usage.input / 1_000_000 * self.cost_input_per_m
            + usage.output / 1_000_000 * self.cost_output_per_m
        )


_REGISTRY: Dict[str, Dict[str, Any]] = {
    "deepseek": {
        "api": "openai-completions",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-v4-flash",
        "model_env": "DEEPSEEK_MODEL",
    },
    "anthropic": {
        "api": "anthropic-messages",
        "base_url": "https://api.anthropic.com",
        "api_key_env": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-5",
        "model_env": "ANTHROPIC_MODEL",
        "supports_vision": True,
    },
    "openai": {
        "api": "openai-completions",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4o-mini",
        "model_env": "OPENAI_MODEL",
        "supports_vision": True,
    },
    "volc": {
        "api": "openai-completions",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_key_env": "ARK_API_KEY",
        "default_model": "doubao-pro-32k",
        "model_env": "ARK_MODEL",
    },
    "qwen": {
        "api": "openai-completions",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "default_model": "qwen-plus",
        "model_env": "DASHSCOPE_MODEL",
    },
    "mimo": {
        "api": "anthropic-messages",
        "base_url": "https://token-plan-cn.xiaomimimo.com/anthropic",
        "api_key_env": "MIMO_API_KEY",
        "default_model": "mimo-v2.5-pro",
        "model_env": "MIMO_MODEL",
    },
}

_ENV_DETECT_ORDER = ["deepseek", "anthropic", "openai", "volc", "qwen", "mimo"]


def build_model_config(provider: str, model_id: Optional[str] = None,
                       api_key: Optional[str] = None) -> ModelConfig:
    entry = _REGISTRY[provider]
    resolved_model = model_id or os.getenv(entry["model_env"]) or entry["default_model"]
    resolved_key = api_key or os.getenv(entry["api_key_env"])
    # DeepSeek key 兼容：model-switcher 存为 DEEPSEEK_ANTHROPIC_AUTH_TOKEN
    if not resolved_key and provider == "deepseek":
        resolved_key = os.getenv("DEEPSEEK_ANTHROPIC_AUTH_TOKEN")
    return ModelConfig(
        id=resolved_model,
        api=entry["api"],
        provider=provider,
        base_url=entry["base_url"],
        api_key=resolved_key,
        api_key_env=entry["api_key_env"],
        supports_vision=bool(entry.get("supports_vision", False)),
        supports_json=bool(entry.get("supports_json", True)),
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
    if name:
        provider = _provider_for_model_name(name)
        if provider is not None:
            model_id = name.split("/", 1)[1] if "/" in name else name
            return build_model_config(provider, model_id)
        # 未知模型名：按 OpenAI-compatible 兜底（自定义网关/自托管）
        return ModelConfig(
            id=name,
            api="openai-completions",
            provider="openai",
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.getenv("OPENAI_API_KEY"),
            api_key_env="OPENAI_API_KEY",
        )
    explicit = os.getenv("ZENSKILL_AGENT_MODEL")
    if explicit:
        return resolve_model(explicit)
    for provider in _ENV_DETECT_ORDER:
        env_name = _REGISTRY[provider]["api_key_env"]
        if os.getenv(env_name):
            return build_model_config(provider)
    # 兜底：~/.zenskill/llm_config.json 中已配置的云厂商凭据
    # （lm-service 为自定义协议，agent 引擎暂不支持，见 docs/runtime_pi_reference_plan.md）
    try:
        from zenskill.core.llm_config import llm_config
        config = llm_config.get()
        if config.provider in _REGISTRY:
            env_name = _REGISTRY[config.provider]["api_key_env"]
            if config.api_key or os.getenv(env_name):
                return build_model_config(config.provider, config.model, config.api_key)
    except Exception:
        pass
    raise RuntimeError(
        "未找到可用的 LLM 凭据。请设置 DEEPSEEK_API_KEY / ANTHROPIC_API_KEY / "
        "OPENAI_API_KEY / ARK_API_KEY / DASHSCOPE_API_KEY，或用 --model 指定模型。"
    )


def create_stream(model: ModelConfig) -> Callable[..., Any]:
    if model.api == "anthropic-messages":
        from .anthropic_messages import anthropic_stream
        return anthropic_stream
    from .openai_completions import openai_completions_stream
    return openai_completions_stream
