"""
Provider 知识库 — 内置厂商/模型信息 (参考 ModelSwitcher providers.yaml)

用法:
    from zenskill.core.providers import get_providers, get_provider, get_all_models
    providers = get_providers()
    models = get_all_models()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ModelInfo:
    """模型信息"""
    name: str
    display: str = ""
    provider: str = ""
    tier: str = "standard"  # premium / standard / free
    capabilities: List[str] = field(default_factory=list)
    context_window: int = 0

    @property
    def display_name(self) -> str:
        return self.display or self.name


@dataclass
class ProviderInfo:
    """厂商信息"""
    name: str
    display: str = ""
    base_url: str = ""
    api_key_env: str = ""
    api_key_prefix: str = "Bearer"
    docs_url: str = ""
    models: List[ModelInfo] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.display or self.name

    def get_api_key_hint(self) -> str:
        key = os.environ.get(self.api_key_env) if self.api_key_env else None
        if key:
            return f"{key[:8]}...{key[-4:]}"
        return "(未设置)"

    def get_model_names(self) -> List[str]:
        return [m.name for m in self.models]

    def find_model(self, name_or_alias: str) -> Optional[ModelInfo]:
        for m in self.models:
            if m.name == name_or_alias:
                return m
        return None


# ═══════════════════════════════════════════════════════════════
# 内置厂商知识库 (只读)
# ═══════════════════════════════════════════════════════════════

_BUILTIN_PROVIDERS: List[ProviderInfo] = [
    ProviderInfo(
        name="openai",
        display="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        docs_url="https://platform.openai.com/api-keys",
        tags=["cloud"],
        models=[
            ModelInfo("gpt-4o", "GPT-4o", "openai", "premium",
                     ["chat", "vision", "coding"], 128000),
            ModelInfo("gpt-4o-mini", "GPT-4o Mini", "openai", "standard",
                     ["chat", "vision"], 128000),
            ModelInfo("gpt-4-turbo", "GPT-4 Turbo", "openai", "premium",
                     ["chat", "coding"], 128000),
            ModelInfo("gpt-3.5-turbo", "GPT-3.5 Turbo", "openai", "standard",
                     ["chat"], 16385),
        ],
    ),
    ProviderInfo(
        name="anthropic",
        display="Anthropic (Claude)",
        base_url="https://api.anthropic.com",
        api_key_env="ANTHROPIC_API_KEY",
        docs_url="https://console.anthropic.com/",
        tags=["cloud"],
        models=[
            ModelInfo("claude-sonnet-4-20250514", "Claude Sonnet 4", "anthropic", "premium",
                     ["chat", "coding", "reasoning", "vision"], 200000),
            ModelInfo("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet", "anthropic", "premium",
                     ["chat", "coding", "vision"], 200000),
            ModelInfo("claude-3-5-haiku-20241022", "Claude 3.5 Haiku", "anthropic", "standard",
                     ["chat", "fast"], 200000),
            ModelInfo("claude-opus-4-20250514", "Claude Opus 4", "anthropic", "premium",
                     ["chat", "coding", "reasoning"], 200000),
        ],
    ),
    ProviderInfo(
        name="deepseek",
        display="DeepSeek",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        docs_url="https://platform.deepseek.com/api-keys",
        tags=["cloud"],
        models=[
            ModelInfo("deepseek-chat", "DeepSeek V3", "deepseek", "standard",
                     ["chat", "coding"], 64000),
            ModelInfo("deepseek-reasoner", "DeepSeek R1", "deepseek", "premium",
                     ["reasoning", "coding"], 64000),
            ModelInfo("deepseek-v4-pro", "DeepSeek V4 Pro", "deepseek", "premium",
                     ["reasoning", "coding", "analysis"], 128000),
        ],
    ),
    ProviderInfo(
        name="volcengine",
        display="火山引擎 (豆包)",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key_env="ARK_API_KEY",
        docs_url="https://console.volcengine.com/ark",
        tags=["cloud"],
        models=[
            ModelInfo("doubao-pro-32k", "豆包 Pro 32K", "volcengine", "premium",
                     ["chat", "coding"], 32000),
            ModelInfo("doubao-pro-128k", "豆包 Pro 128K", "volcengine", "premium",
                     ["chat", "coding"], 128000),
            ModelInfo("doubao-lite-32k", "豆包 Lite 32K", "volcengine", "standard",
                     ["chat"], 32000),
        ],
    ),
    ProviderInfo(
        name="qwen",
        display="通义千问 (Qwen)",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
        docs_url="https://help.aliyun.com/zh/model-studio/",
        tags=["cloud"],
        models=[
            ModelInfo("qwen-plus", "Qwen Plus", "qwen", "standard",
                     ["chat", "coding"], 131072),
            ModelInfo("qwen-max", "Qwen Max", "qwen", "premium",
                     ["chat", "coding", "reasoning"], 32000),
            ModelInfo("qwen-turbo", "Qwen Turbo", "qwen", "standard",
                     ["chat", "fast"], 131072),
        ],
    ),
    ProviderInfo(
        name="ollama",
        display="Ollama (本地)",
        base_url="http://localhost:11434/v1",
        api_key_env="",
        docs_url="https://ollama.com",
        tags=["local"],
        models=[
            ModelInfo("llama3.2", "Llama 3.2", "ollama", "free",
                     ["chat", "local"], 128000),
            ModelInfo("qwen2.5", "Qwen 2.5", "ollama", "free",
                     ["chat", "local"], 32000),
            ModelInfo("deepseek-r1", "DeepSeek R1 (本地)", "ollama", "free",
                     ["reasoning", "local"], 128000),
        ],
    ),
]


def get_providers() -> List[ProviderInfo]:
    """获取所有厂商"""
    return _BUILTIN_PROVIDERS


def get_provider(name: str) -> Optional[ProviderInfo]:
    """按名称查找厂商"""
    for p in _BUILTIN_PROVIDERS:
        if p.name == name:
            return p
    return None


def get_all_models() -> List[ModelInfo]:
    """获取所有内置模型"""
    models = []
    for p in _BUILTIN_PROVIDERS:
        models.extend(p.models)
    return models


def find_model(name: str) -> Optional[ModelInfo]:
    """按名称查找模型（跨厂商）"""
    for p in _BUILTIN_PROVIDERS:
        m = p.find_model(name)
        if m:
            return m
    return None


import os  # noqa: needed for get_api_key_hint
