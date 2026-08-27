"""
ZenSkill - LLM Provider 抽象层

让 ZenSkill 不绑定任何特定平台：
- ✅ 作为扣子 Skill 时，调用扣子平台的 LLM
- ✅ 作为独立库时，可以注入 OpenAI/Claude
- ✅ 作为 OpenClaw 技能时，适配其 LLM 接口
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any, List, Dict

logger = logging.getLogger(__name__)


class HostedLLMRequired(Exception):
    """
    抛出此异常表示当前环境需要宿主框架执行 LLM 任务。

    当 Claude Code / Coze / Hermes 等宿主环境下，
    同步调用 llm.chat() 无法直接获得结果时抛出。

    调用方应该：
    1. 捕获此异常
    2. 从异常中获取 task/prompt 信息
    3. 交给宿主框架执行
    4. 通过 callback 写回结果
    """
    def __init__(self, task: Dict[str, Any], message: str = "需要宿主框架执行 LLM 任务"):
        self.task = task
        self.message = message
        super().__init__(message)


@dataclass
class ChatMessage:
    """聊天消息"""
    role: str  # "user", "assistant", "system"
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResponse:
    """LLM 回复"""
    content: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseLLMProvider(ABC):
    """
    LLM Provider 抽象基类
    
    所有平台都实现这个接口：
    - CozeLLMProvider: 扣子平台
    - OpenAIProvider: OpenAI
    - ClaudeProvider: Anthropic Claude
    - OpenClawProvider: OpenClaw 框架
    """
    
    @abstractmethod
    async def chat(
        self,
        messages: List[ChatMessage],
        **kwargs,
    ) -> ChatResponse:
        """
        调用 LLM 聊天
        
        Args:
            messages: 消息列表
            **kwargs: 平台特定参数
        
        Returns:
            LLM 回复
        """
        pass
    
    @abstractmethod
    def get_model_name(self) -> str:
        """获取当前使用的模型名称"""
        pass
    
    async def simple_chat(
        self,
        user_input: str,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        简单聊天接口
        
        Args:
            user_input: 用户输入
            system_prompt: 系统提示词（可选）
        
        Returns:
            LLM 回复内容
        """
        messages: List[ChatMessage] = []
        
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        
        messages.append(ChatMessage(role="user", content=user_input))
        
        response = await self.chat(messages, **kwargs)
        return response.content


class SimpleLLMProvider(BaseLLMProvider):
    """
    最简单的 LLM Provider - 用于 Demo 和无 LLM 环境
    
    只做基于模板的回复，不调用真实大模型
    用于演示 ZenSkill 的核心功能（记忆、修炼、禅思循环）
    """
    
    def __init__(self, name: str = "SimpleLLM") -> None:
        self._name = name
        self._response_templates = [
            "这是一个很好的问题！让我来为你详细解释：{user_input}",
            "关于「{user_input}」，我有一些想法...",
            "很高兴能帮到你！关于 {user_input}，我的建议是...",
            "这个问题很有意思，让我从记忆中检索相关信息...",
            "根据我的理解，{user_input} 可以从以下几个角度来看...",
        ]
    
    async def chat(
        self,
        messages: List[ChatMessage],
        **kwargs,
    ) -> ChatResponse:
        """简单的模板回复"""
        import time
        import random
        import asyncio
        
        start_time = time.time()
        
        # 获取最后一条用户消息
        user_message = ""
        for msg in reversed(messages):
            if msg.role == "user":
                user_message = msg.content
                break
        
        # 选择模板
        template = random.choice(self._response_templates)
        content = template.format(user_input=user_message[:30])
        
        # 模拟 LLM 延迟
        await asyncio.sleep(0.1)
        
        latency = (time.time() - start_time) * 1000
        
        return ChatResponse(
            content=content,
            model=self._name,
            latency_ms=latency,
        )
    
    def get_model_name(self) -> str:
        return self._name


class CozeLLMProvider(BaseLLMProvider):
    """
    扣子（Coze）平台 LLM Provider
    
    作为扣子 Skill 时使用，调用扣子平台提供的 LLM 接口
    不需要自己管理 API Key
    """
    
    def __init__(self, coze_bot_id: str = "") -> None:
        self._bot_id = coze_bot_id
        logger.info("CozeLLMProvider initialized - 不需要 API Key！")
    
    async def chat(
        self,
        messages: List[ChatMessage],
        **kwargs,
    ) -> ChatResponse:
        """
        调用扣子平台的 LLM 接口
        
        注意：实际实现需要根据扣子 Skill 的 SDK 来写
        这里是占位实现，展示架构
        """
        import time
        start_time = time.time()
        
        # ================================
        # TODO: 实际扣子 Skill SDK 调用
        # ================================
        # 实际扣子 Skill 中，会有类似：
        # from coze import Coze
        # client = Coze()
        # response = await client.chat.create(...)
        
        # 占位实现
        content = "（这是扣子平台 LLM 调用占位）"
        
        # 如果用户内容较长，加一点魔法回复
        if len(messages) > 0 and messages[-1].content:
            user_content = messages[-1].content
            content = f"收到你的问题：{user_content[:50]}...（扣子平台处理中）"
        
        latency = (time.time() - start_time) * 1000
        
        return ChatResponse(
            content=content,
            model="coze-platform-llm",
            latency_ms=latency,
        )
    
    def get_model_name(self) -> str:
        return f"Coze-{self._bot_id}" if self._bot_id else "Coze-Platform"


class OpenAILLMProvider(BaseLLMProvider):
    """
    OpenAI LLM Provider

    支持 GPT-4, GPT-4o, GPT-3.5-Turbo 等模型
    需要: pip install openai
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-3.5-turbo",
        base_url: Optional[str] = None,
    ) -> None:
        import os
        try:
            from .llm_config import llm_config
            config_api_key = llm_config.get().api_key
        except Exception:
            config_api_key = None
        self._api_key = api_key or config_api_key or os.getenv("OPENAI_API_KEY")
        self._model = model
        self._base_url = base_url
        self._client = None
        logger.info(f"OpenAILLMProvider initialized - model={model}")

    async def chat(
        self,
        messages: List[ChatMessage],
        **kwargs,
    ) -> ChatResponse:
        """调用 OpenAI Chat API"""
        import time
        start_time = time.time()

        if not messages:
            raise ValueError("messages 不能为空")

        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("使用 OpenAI Provider 需要安装 openai: pip install openai")

        if not self._api_key:
            raise ValueError("OpenAI API key not provided. Set OPENAI_API_KEY or pass api_key.")

        if self._client is None:
            client_kwargs = {"api_key": self._api_key}
            if self._base_url:
                client_kwargs["base_url"] = self._base_url
            self._client = AsyncOpenAI(**client_kwargs)

        # 转换消息格式
        chat_messages = [{"role": m.role, "content": m.content} for m in messages]

        try:
            response = await self._client.chat.completions.create(
                model=kwargs.get("model", self._model),
                messages=chat_messages,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 2000),
            )

            choice = response.choices[0]
            content = choice.message.content or ""
            usage = response.usage

            latency = (time.time() - start_time) * 1000

            return ChatResponse(
                content=content,
                model=response.model,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                latency_ms=latency,
                metadata={"finish_reason": choice.finish_reason},
            )

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    def get_model_name(self) -> str:
        return self._model


class AnthropicLLMProvider(BaseLLMProvider):
    """
    Anthropic Claude LLM Provider

    支持 Claude 3.5 Sonnet, Claude 3 Haiku 等模型
    需要: pip install anthropic
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-haiku-20240307",
        base_url: Optional[str] = None,
    ) -> None:
        import os
        try:
            from .llm_config import llm_config
            config_api_key = llm_config.get().api_key
        except Exception:
            config_api_key = None
        self._api_key = api_key or config_api_key or os.getenv("ANTHROPIC_API_KEY")
        self._model = model
        self._base_url = base_url
        self._client = None
        logger.info(f"AnthropicLLMProvider initialized - model={model}")

    async def chat(
        self,
        messages: List[ChatMessage],
        **kwargs,
    ) -> ChatResponse:
        """调用 Anthropic Claude API"""
        import time
        start_time = time.time()

        if not messages:
            raise ValueError("messages 不能为空")

        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            raise ImportError("使用 Anthropic Provider 需要安装 anthropic: pip install anthropic")

        if not self._api_key:
            raise ValueError("Anthropic API key not provided. Set ANTHROPIC_API_KEY or pass api_key.")

        if self._client is None:
            client_kwargs = {"api_key": self._api_key}
            if self._base_url:
                client_kwargs["base_url"] = self._base_url
            self._client = AsyncAnthropic(**client_kwargs)

        # 转换消息格式（Claude 要求 system 作为单独参数）
        system_prompt = None
        claude_messages = []
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                claude_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        try:
            response = await self._client.messages.create(
                model=self._model,
                messages=claude_messages,
                system=system_prompt,
                max_tokens=kwargs.get("max_tokens", 1024),
                temperature=kwargs.get("temperature", 0.7),
            )

            content = response.content[0].text if response.content else ""
            latency = (time.time() - start_time) * 1000

            return ChatResponse(
                content=content,
                model=response.model,
                prompt_tokens=response.usage.input_tokens if response.usage else 0,
                completion_tokens=response.usage.output_tokens if response.usage else 0,
                total_tokens=(response.usage.input_tokens + response.usage.output_tokens) if response.usage else 0,
                latency_ms=latency,
            )

        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise

    def get_model_name(self) -> str:
        return self._model


class HostedLLMProvider(BaseLLMProvider):
    """
    宿主感知的 LLM Provider - 智能复用运行环境的 LLM 能力

    自动探测当前运行环境，选择最佳的 LLM 调用方式：

    探测逻辑：
    1. 检查 Claude Code 环境 → 通过工具回调，把 LLM 任务还给宿主 Claude
    2. 检查 Coze 环境 → 调用 Coze 平台内置 LLM 接口
    3. 检查 OpenClaw 环境 → 调用框架提供的 LLM 服务
    4. CLI 模式 → 检查配置，降级到 Anthropic/OpenAI Provider
    """

    def __init__(self, force_provider: Optional[str] = None) -> None:
        self._force_provider = force_provider
        self._active_provider: Optional[BaseLLMProvider] = None
        self._detect_and_init()

    @staticmethod
    def _load_config() -> dict:
        """加载配置文件"""
        import json
        from pathlib import Path

        config_path = Path.home() / ".zenskill" / "config.json"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load config: {e}")
        return {}

    def _detect_and_init(self) -> None:
        """探测运行环境并初始化对应的 Provider"""
        import os
        from .llm_config import llm_config

        # 加载配置文件
        config = llm_config.get()

        # 强制指定 Provider（用于调试）
        if self._force_provider:
            self._init_forced_provider()
            return

        # 1. 检测 Claude Code 环境
        if self._is_claude_code_env():
            logger.info("Detected Claude Code environment, using host LLM")
            # Claude Code 环境下，返回特殊的代理 Provider，把任务交还给宿主
            self._active_provider = ClaudeCodeHostedProvider()
            return

        # 2. 检测 Coze 环境
        if os.environ.get("COZE_ENV") or os.environ.get("COZE_BOT_ID"):
            logger.info("Detected Coze environment, using platform LLM")
            self._active_provider = CozeLLMProvider(coze_bot_id=os.environ.get("COZE_BOT_ID", ""))
            return

        # 3. 根据配置选择 Provider
        provider_type = config.provider

        # 国产模型优先
        if provider_type == "deepseek" or os.environ.get("DEEPSEEK_API_KEY"):
            logger.info("Using DeepSeek LLM")
            self._active_provider = DeepSeekLLMProvider(model=config.model)
            return

        if provider_type == "volc" or os.environ.get("ARK_API_KEY"):
            logger.info("Using VolcEngine Doubao LLM")
            self._active_provider = VolcEngineLLMProvider(model=config.model)
            return

        if provider_type == "qwen" or os.environ.get("DASHSCOPE_API_KEY"):
            logger.info("Using Qwen LLM")
            self._active_provider = QwenLLMProvider(model=config.model)
            return

        # 4. CLI 独立模式：尝试从配置或环境读取 API Key
        # 4.1 尝试初始化 Anthropic
        anthropic_key = config.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if provider_type == "anthropic" or anthropic_key:
            self._active_provider = AnthropicLLMProvider(api_key=anthropic_key, model=config.model)
            logger.info(f"Using Anthropic LLM (model: {config.model})")
            return

        # 4.2 尝试 OpenAI
        openai_key = config.api_key or os.environ.get("OPENAI_API_KEY")
        if provider_type == "openai" or openai_key:
            self._active_provider = OpenAILLMProvider(api_key=openai_key, model=config.model)
            logger.info(f"Using OpenAI LLM (model: {config.model})")
            return

        # 检测 OpenClaw 环境
        if os.environ.get("OPENCLAW_ENV"):
            logger.info("Detected OpenClaw environment, using framework LLM")
            self._active_provider = SimpleLLMProvider(name="OpenClaw-Hosted")
            return

    def _is_claude_code_env(self) -> bool:
        """检测是否在 Claude Code 环境中运行"""
        import os
        return (
            os.environ.get("CLAUDE_ENV") is not None
            or os.environ.get("CLAUDE_PLUGIN") is not None
            or os.environ.get("CLAUDE_CODE") is not None
        )

    def _init_forced_provider(self) -> None:
        """强制使用指定 Provider（用于调试）"""
        from .llm_config import llm_config
        import os

        config = llm_config.get()
        provider = self._force_provider.lower()

        provider_map = {
            "anthropic": lambda: AnthropicLLMProvider(
                api_key=config.api_key or os.environ.get("ANTHROPIC_API_KEY"),
                model=config.model,
            ),
            "openai": lambda: OpenAILLMProvider(
                api_key=config.api_key or os.environ.get("OPENAI_API_KEY"),
                model=config.model,
            ),
            "deepseek": lambda: DeepSeekLLMProvider(
                api_key=config.api_key or os.environ.get("DEEPSEEK_API_KEY"),
                model=config.model,
            ),
            "volc": lambda: VolcEngineLLMProvider(
                api_key=config.api_key or os.environ.get("ARK_API_KEY"),
                model=config.model,
            ),
            "qwen": lambda: QwenLLMProvider(
                api_key=config.api_key or os.environ.get("DASHSCOPE_API_KEY"),
                model=config.model,
            ),
            "coze": lambda: CozeLLMProvider(),
            "simple": lambda: SimpleLLMProvider(),
        }

        if provider in provider_map:
            self._active_provider = provider_map[provider]()
        else:
            logger.warning(f"Unknown forced provider: {self._force_provider}, using SimpleLLM")
            self._active_provider = SimpleLLMProvider()

    async def chat(
        self,
        messages: List[ChatMessage],
        **kwargs,
    ) -> ChatResponse:
        """转发到当前激活的 Provider"""
        if self._active_provider is None:
            self._detect_and_init()

        return await self._active_provider.chat(messages, **kwargs)

    def has_stream(self) -> bool:
        """检查底层 Provider 是否支持流式"""
        if self._active_provider is None:
            self._detect_and_init()
        return hasattr(self._active_provider, "stream_chat")

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        **kwargs,
    ):
        """流式对话 — 转发到激活的 Provider"""
        if self._active_provider is None:
            self._detect_and_init()
        if hasattr(self._active_provider, "stream_chat"):
            async for chunk in self._active_provider.stream_chat(messages, **kwargs):
                yield chunk
        else:
            # 非流式回退：一次性返回
            resp = await self._active_provider.chat(messages, **kwargs)
            yield {"type": "content", "content": resp.content}

    def get_model_name(self) -> str:
        """获取当前激活 Provider 的模型名"""
        if self._active_provider is None:
            self._detect_and_init()

        return self._active_provider.get_model_name() if self._active_provider else "Unknown"

    def get_active_provider(self) -> Optional[BaseLLMProvider]:
        """获取当前激活的 Provider"""
        return self._active_provider

    def reload(self) -> None:
        """重新加载配置并重建 Provider（配置保存后调用）"""
        from .llm_config import llm_config
        llm_config.reload()
        self._active_provider = None
        self._detect_and_init()
        logger.info(f"LLM Provider reloaded: {self.get_model_name()}")


class ClaudeCodeHostedProvider(BaseLLMProvider):
    """
    Claude Code 宿主环境的 LLM Provider

    设计理念：不直接调用 LLM，而是作为 LLM 任务的收集器和格式化器。
    1. 收集上下文，组装成高质量的 prompt
    2. 返回结构化的任务描述，由 CLI/插件 把任务交还给宿主 Claude
    3. 宿主完成思考后，ZenSkill 负责解析和存储结果

    这是正确的架构：ZenSkill 作为技能，不应该自己管 API Key，而是复用宿主的 LLM 能力。
    """

    def __init__(self) -> None:
        self._name = "Claude-Code-Hosted"
        self._task_id = 0
        logger.info("ClaudeCodeHostedProvider initialized - delegating LLM tasks to host")

    async def chat(
        self,
        messages: List[ChatMessage],
        **kwargs,
    ) -> ChatResponse:
        """
        返回结构化的 LLM 任务描述。

        默认行为（同步调用）：抛出 HostedLLMRequired 异常，
        通知调用方需要宿主框架执行此 LLM 任务。

        如果调用方明确知道如何处理宿主任务，可以设置 throw_if_hosted=False
        直接获取 ChatResponse（CLI 的 --hosted 模式使用）。
        """
        import time
        start_time = time.time()
        self._task_id += 1

        # 构建完整的 prompt
        prompt = self._format_messages_to_prompt(messages)
        latency = (time.time() - start_time) * 1000

        # 构建任务描述
        task = {
            "llm_task": True,
            "task_id": self._task_id,
            "prompt": prompt,
            "expected_format": kwargs.get("expected_format", "markdown"),
            "storage_callback": {
                "command": "python -m zenskill reflect store",
                "stdin_json": True,
                "result_key": "reflection_content",
            },
        }

        # 默认抛出异常，让调用方知道这是宿主环境
        if kwargs.get("throw_if_hosted", True):
            raise HostedLLMRequired(
                task=task,
                message="当前运行在 Claude Code 宿主环境，请让宿主执行 LLM 任务后通过 reflect store 写回结果"
            )

        # 只有明确设置 throw_if_hosted=False 时才返回空响应
        # （供 CLI --hosted 模式使用）
        return ChatResponse(
            content="",
            model=self._name,
            latency_ms=latency,
            metadata=task,
        )

    def _format_messages_to_prompt(self, messages: List[ChatMessage]) -> str:
        """将消息列表格式化为完整的 prompt 字符串"""
        parts = []
        for msg in messages:
            if msg.role == "system":
                parts.append(f"<system>\n{msg.content}\n</system>")
            elif msg.role == "user":
                parts.append(f"<user>\n{msg.content}\n</user>")
            elif msg.role == "assistant":
                parts.append(f"<assistant>\n{msg.content}\n</assistant>")
            else:
                parts.append(f"<{msg.role}>\n{msg.content}\n</{msg.role}>")
        return "\n\n".join(parts)

    def format_reflection_prompt(
        self,
        interaction_history: List[dict],
        memories: List[dict],
        skill_state: dict,
    ) -> str:
        """专为禅思反思生成高质量 prompt"""
        from datetime import datetime

        state_summary = f"""
境界：{skill_state.get('level', 'NOVICE')}
使用次数：{skill_state.get('usage_count', 0)}
当前时间：{datetime.now().isoformat()}
"""

        history_summary = ""
        if interaction_history:
            items = [f"- {item.get('action', '')}: {item.get('content', '')[:100]}"
                     for item in interaction_history[-10:]]
            history_summary = "\n".join(items)

        memory_summary = ""
        if memories:
            items = [f"- {mem.get('content', '')[:100]}" for mem in memories[-20:]]
            memory_summary = "\n".join(items)

        return f"""你是 ZenSkill 的禅思大师，一位善于深度思考和总结的智能体。

## 技能状态

{state_summary}

## 最近交互历史

{history_summary or '（无）'}

## 记忆库摘要

{memory_summary or '（无）'}

## 你的任务

请进行一次深度禅思，从以下维度分析：

1. **观察到的模式**：从最近的交互中，你观察到了什么用户行为模式、偏好、习惯？
2. **本次优点**：最近的执行中有哪些做得好的地方？
3. **改进空间**：有哪些可以提升的地方？
4. **行动建议**：给出 2-3 条具体可执行的建议。
5. **洞见与发现**：跨记忆关联，发现隐藏的规律或机会。

请用结构化 Markdown 输出，清晰、简洁、有深度。
"""

    def get_model_name(self) -> str:
        return self._name


# 全局 LLM Provider 实例
_global_llm_provider: Optional[BaseLLMProvider] = None


def set_llm_provider(provider: BaseLLMProvider) -> None:
    """
    设置全局 LLM Provider
    
    在应用初始化时调用：
    
    # 扣子部署
    set_llm_provider(CozeLLMProvider())
    
    # 独立部署
    set_llm_provider(OpenAILLMProvider(api_key="..."))
    
    # Demo 模式
    set_llm_provider(SimpleLLMProvider())
    """
    global _global_llm_provider
    _global_llm_provider = provider
    logger.info(f"Global LLM Provider set: {provider.get_model_name()}")


def get_llm_provider() -> BaseLLMProvider:
    """
    获取全局 LLM Provider

    默认使用 HostedLLMProvider（宿主感知，自动探测运行环境）
    """
    global _global_llm_provider

    if _global_llm_provider is None:
        _global_llm_provider = HostedLLMProvider()
        logger.info(
            f"Using auto-detected LLM Provider: {_global_llm_provider.get_model_name()}"
        )

    return _global_llm_provider


def reload_global_provider() -> None:
    """重新加载全局 LLM Provider（配置保存后调用）"""
    global _global_llm_provider
    if _global_llm_provider is not None and isinstance(_global_llm_provider, HostedLLMProvider):
        _global_llm_provider.reload()
    else:
        _global_llm_provider = HostedLLMProvider()
    logger.info(f"Global LLM Provider reloaded: {_global_llm_provider.get_model_name()}")


# ====================================================================
# 国产模型 Provider
# ====================================================================

class DeepSeekLLMProvider(BaseLLMProvider):
    """
    DeepSeek 大模型 Provider
    """

    BASE_URL = "https://api.deepseek.com/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "deepseek-chat",
        base_url: Optional[str] = None,
    ) -> None:
        import os
        try:
            from .llm_config import llm_config
            config_api_key = llm_config.get().api_key
        except Exception:
            config_api_key = None
        self._api_key = api_key or config_api_key or os.getenv("DEEPSEEK_API_KEY")
        self._model = model
        self._base_url = base_url or self.BASE_URL
        self._session = None

    @staticmethod
    def _ensure_chinese_thinking(messages: List[ChatMessage]) -> List[ChatMessage]:
        """确保 DeepSeek V4 用中文思考。无 system 消息时自动注入。"""
        has_system = any(m.role == "system" for m in messages)
        if not has_system:
            return [ChatMessage(role="system", content="请使用中文思考和回答。")] + list(messages)
        return messages

    async def chat(
        self,
        messages: List[ChatMessage],
        **kwargs,
    ) -> ChatResponse:
        import time
        import aiohttp

        messages = self._ensure_chinese_thinking(messages)
        start_time = time.time()

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": kwargs.get("model", self._model),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2000),
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=kwargs.get("timeout", 30),
            ) as resp:
                data = await resp.json()

                if resp.status != 200:
                    raise Exception(f"DeepSeek API error: {resp.status} - {data}")

                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                # V4 推理模型: content 可能为空，取 reasoning_content 作为回退
                content = message.get("content", "") or message.get("reasoning_content", "")
                finish = choice.get("finish_reason", "stop")
                usage = data.get("usage", {})

                latency = (time.time() - start_time) * 1000

                return ChatResponse(
                    content=content,
                    model=data.get("model", self._model),
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    latency_ms=latency,
                    metadata=data,
                )

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        **kwargs,
    ):
        """流式对话 — 异步生成器，逐 token 产出

        用法:
            async for chunk in provider.stream_chat(messages):
                print(chunk, end="", flush=True)
        """
        import json as _json
        import aiohttp

        messages = self._ensure_chinese_thinking(messages)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": kwargs.get("model", self._model),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2000),
            "stream": True,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=kwargs.get("timeout", 60),
            ) as resp:
                if resp.status != 200:
                    data = await resp.text()
                    raise Exception(f"DeepSeek stream error: {resp.status} - {data[:200]}")

                async for line in resp.content:
                    text = line.decode("utf-8").strip()
                    if not text or text == "data: [DONE]":
                        continue
                    if text.startswith("data: "):
                        text = text[6:]
                    try:
                        chunk = _json.loads(text)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        reasoning = delta.get("reasoning_content", "")
                        content = delta.get("content", "")
                        # 推理模型：先 reasoning，后 content
                        if reasoning:
                            yield {"type": "reasoning", "content": reasoning}
                        elif content:
                            yield {"type": "content", "content": content}
                    except Exception:
                        continue

    def get_model_name(self) -> str:
        return f"DeepSeek/{self._model}"


class VolcEngineLLMProvider(BaseLLMProvider):
    """
    火山引擎·豆包 LLM Provider
    """

    BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "doubao-pro-32k",
        base_url: Optional[str] = None,
    ) -> None:
        import os
        try:
            from .llm_config import llm_config
            config_api_key = llm_config.get().api_key
        except Exception:
            config_api_key = None
        self._api_key = api_key or config_api_key or os.getenv("ARK_API_KEY")
        self._model = model
        self._base_url = base_url or self.BASE_URL
        self._session = None

    async def chat(
        self,
        messages: List[ChatMessage],
        **kwargs,
    ) -> ChatResponse:
        import time
        import aiohttp

        start_time = time.time()

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": kwargs.get("model", self._model),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2000),
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=kwargs.get("timeout", 30),
            ) as resp:
                data = await resp.json()

                if resp.status != 200:
                    raise Exception(f"VolcEngine API error: {resp.status} - {data}")

                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                content = message.get("content", "") or message.get("reasoning_content", "")
                usage = data.get("usage", {})

                latency = (time.time() - start_time) * 1000

                return ChatResponse(
                    content=content,
                    model=data.get("model", self._model),
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    latency_ms=latency,
                    metadata=data,
                )

    def get_model_name(self) -> str:
        return f"VolcEngine/{self._model}"


class QwenLLMProvider(BaseLLMProvider):
    """
    阿里·通义千问 LLM Provider
    """

    BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "qwen-max",
        base_url: Optional[str] = None,
    ) -> None:
        import os
        try:
            from .llm_config import llm_config
            config_api_key = llm_config.get().api_key
        except Exception:
            config_api_key = None
        self._api_key = api_key or config_api_key or os.getenv("DASHSCOPE_API_KEY")
        self._model = model
        self._base_url = base_url or self.BASE_URL
        self._session = None

    async def chat(
        self,
        messages: List[ChatMessage],
        **kwargs,
    ) -> ChatResponse:
        import time
        import aiohttp

        start_time = time.time()

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": kwargs.get("model", self._model),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2000),
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=kwargs.get("timeout", 30),
            ) as resp:
                data = await resp.json()

                if resp.status != 200:
                    raise Exception(f"Qwen API error: {resp.status} - {data}")

                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                content = message.get("content", "") or message.get("reasoning_content", "")
                usage = data.get("usage", {})

                latency = (time.time() - start_time) * 1000

                return ChatResponse(
                    content=content,
                    model=data.get("model", self._model),
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    latency_ms=latency,
                    metadata=data,
                )

    def get_model_name(self) -> str:
        return f"Qwen/{self._model}"
