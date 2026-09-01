"""
LLM 配置管理

优先级：环境变量 → ~/.zenskill/llm_config.json → config/llm.yaml → 默认值
"""

import json
import os
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


@dataclass
class LLMConfig:
    """LLM 服务配置"""

    # 服务商
    provider: str = "mock"  # mock / lm-service / openai / anthropic / deepseek / volc / qwen
    model: str = "mock-gpt"

    # 服务配置
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    timeout: int = 30

    # 生成参数
    temperature: float = 0.7
    max_tokens: int = 2000

    # LMService 配置
    auto_start_service: bool = True  # 自动启动本地服务
    service_port: int = 8006

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMConfig":
        valid_keys = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid_keys})


def _resolve_env_var(value: Any) -> Any:
    """解析 ${ENV_VAR} 格式的环境变量引用"""
    if not isinstance(value, str):
        return value
    if value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1]
        return os.environ.get(env_name)
    return value


def _load_yaml_config() -> Dict[str, Any]:
    """加载 config/llm.yaml（项目根目录）"""
    if yaml is None:
        return {}
    yaml_path = Path(__file__).parent.parent.parent / "config" / "llm.yaml"
    if not yaml_path.exists():
        return {}
    try:
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        return data or {}
    except Exception:
        return {}


class LLMConfigManager:
    """LLM 配置管理器（多来源优先链）"""

    def __init__(self):
        self._config_dir = Path.home() / ".zenskill"
        self._config_file = self._config_dir / "llm_config.json"
        self._config: Optional[LLMConfig] = None

    def _ensure_dir(self) -> None:
        """确保配置目录存在"""
        self._config_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> LLMConfig:
        """
        多来源配置加载，优先级：
        1. 环境变量 LLM_API_KEY / LLM_BASE_URL / LLM_PROVIDER
        2. ~/.zenskill/llm_config.json
        3. config/llm.yaml
        4. 默认值
        """
        if self._config is not None:
            return self._config

        # 默认值
        config_dict: Dict[str, Any] = {
            "provider": "mock",
            "model": "mock-gpt",
        }

        # 3. YAML 配置
        yaml_config = _load_yaml_config()
        llm_section = yaml_config.get("llm", {})
        for key in ["provider", "model", "api_key", "base_url", "temperature", "max_tokens"]:
            if key in llm_section:
                config_dict[key] = _resolve_env_var(llm_section[key])

        # 2. 用户配置文件
        if self._config_file.exists():
            try:
                with open(self._config_file, "r", encoding="utf-8") as f:
                    user_data = json.load(f)
                for key, value in user_data.items():
                    config_dict[key] = value
            except Exception:
                pass

        # 1. 环境变量（最高优先级）
        env_api_key = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
        if env_api_key:
            config_dict["api_key"] = env_api_key
        env_base_url = os.environ.get("LLM_BASE_URL")
        if env_base_url:
            config_dict["base_url"] = env_base_url
        env_provider = os.environ.get("LLM_PROVIDER")
        if env_provider:
            config_dict["provider"] = env_provider

        self._config = LLMConfig.from_dict(config_dict)
        return self._config

    def reload(self) -> LLMConfig:
        """重新加载配置（清除缓存）"""
        self._config = None
        return self.load()

    def save(self, config: Optional[LLMConfig] = None) -> None:
        """保存配置"""
        self._ensure_dir()

        if config is not None:
            self._config = config

        if self._config is None:
            self._config = LLMConfig()

        with open(self._config_file, "w", encoding="utf-8") as f:
            json.dump(self._config.to_dict(), f, indent=2, ensure_ascii=False)

    def get(self) -> LLMConfig:
        """获取当前配置"""
        return self.load()

    def get_config_source(self) -> str:
        """获取当前配置的来源说明"""
        if os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY"):
            return "环境变量"
        if self._config_file.exists():
            return "~/.zenskill/llm_config.json"
        yaml_path = Path(__file__).parent.parent.parent / "config" / "llm.yaml"
        if yaml_path.exists():
            return "config/llm.yaml"
        return "默认值"

    def set_provider(self, provider: str) -> None:
        """设置服务商"""
        config = self.load()
        config.provider = provider
        self.save()

    def set_model(self, model: str, provider: Optional[str] = None) -> None:
        """设置模型（自动推断服务商）"""
        config = self.load()
        config.model = model

        if provider is None:
            # 自动推断服务商
            provider = self._detect_provider_from_model(model)
        config.provider = provider

        self.save()

    def set_base_url(self, base_url: str) -> None:
        """设置 API 地址"""
        config = self.load()
        config.base_url = base_url
        self.save()

    def set_api_key(self, api_key: str) -> None:
        """设置 API Key（注意：只建议在开发环境使用）"""
        config = self.load()
        config.api_key = api_key
        self.save()

    def _detect_provider_from_model(self, model: str) -> str:
        """根据模型名推断服务商"""
        model_lower = model.lower()

        if any(x in model_lower for x in ["gpt", "openai"]):
            return "openai"
        elif any(x in model_lower for x in ["claude", "anthropic"]):
            return "anthropic"
        elif any(x in model_lower for x in ["deepseek"]):
            return "deepseek"
        elif any(x in model_lower for x in ["doubao", "volc", "ark", "ep-"]):
            return "volc"
        elif any(x in model_lower for x in ["qwen", "dashscope", "tongyi", "千问"]):
            return "qwen"
        elif any(x in model_lower for x in ["mock"]):
            return "mock"
        else:
            # 默认用 LMService，让服务端路由
            return "lm-service"


# 全局配置管理器
llm_config = LLMConfigManager()


# 预定义模型列表
PREDEFINED_MODELS: Dict[str, Dict[str, str]] = {
    # Mock 测试
    "mock-gpt": {"provider": "mock", "description": "Mock 模拟模式（无 API 消耗）"},

    # OpenAI
    "gpt-4o-mini": {"provider": "openai", "description": "OpenAI GPT-4o 迷你（性价比高）"},
    "gpt-4o": {"provider": "openai", "description": "OpenAI GPT-4o（最强模型）"},

    # Anthropic
    "claude-3-haiku-20240307": {"provider": "anthropic", "description": "Claude 3 Haiku（快速）"},
    "claude-3-sonnet-20240229": {"provider": "anthropic", "description": "Claude 3 Sonnet（均衡）"},

    # DeepSeek
    "deepseek-chat": {"provider": "deepseek", "description": "DeepSeek Chat V3"},
    "deepseek-coder": {"provider": "deepseek", "description": "DeepSeek Coder V3"},
    "deepseek-v4-flash": {"provider": "deepseek", "description": "DeepSeek V4 Flash（快速）"},
    "deepseek-v4-pro": {"provider": "deepseek", "description": "DeepSeek V4 Pro（最强）"},

    # 火山·豆包
    "doubao-pro-32k": {"provider": "volc", "description": "豆包 Pro 32K（火山引擎）"},
    "doubao-lite-32k": {"provider": "volc", "description": "豆包 Lite 32K（快速）"},

    # 阿里·千问
    "qwen-max": {"provider": "qwen", "description": "通义千问 Max（最强）"},
    "qwen-plus": {"provider": "qwen", "description": "通义千问 Plus（性价比）"},
    "qwen-turbo": {"provider": "qwen", "description": "通义千问 Turbo（快速）"},
}


def get_available_models() -> Dict[str, Dict[str, str]]:
    """获取所有可用模型"""
    return PREDEFINED_MODELS


def get_model_info(model: str) -> Optional[Dict[str, str]]:
    """获取指定模型信息"""
    return PREDEFINED_MODELS.get(model)
