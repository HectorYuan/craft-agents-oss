"""llm 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

from ..cli_utils import output as cli_output

def cmd_llm_list(args: argparse.Namespace) -> None:
    """列出所有支持的模型"""
    from ..core.llm_config import get_available_models

    models = get_available_models()

    providers: Dict[str, List[str]] = {}
    for model, info in models.items():
        provider = info["provider"]
        if provider not in providers:
            providers[provider] = []
        providers[provider].append(model)

    result = {
        "model_count": len(models),
        "providers": list(providers.keys()),
        "models": {p: model_list for p, model_list in providers.items()},
    }

    def _text():
        lines = []
        lines.append("")
        lines.append("🤖 可用模型列表")
        lines.append("=" * 80)
        lines.append("")

        for provider, model_list in providers.items():
            lines.append(f"📦 {provider.upper()}")
            for model in model_list:
                desc = models[model]["description"]
                lines.append(f"   • {model:35s} - {desc}")
            lines.append("")

        lines.append("💡 使用方法:")
        lines.append("   zenskill llm set <model-name>      # 设置默认模型")
        lines.append("   zenskill chat <message>             # 使用默认模型对话")
        lines.append("   zenskill chat --model <model> <msg> # 临时使用指定模型")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_llm_show(args: argparse.Namespace) -> None:
    """显示当前 LLM 配置"""
    from ..core.llm_config import llm_config
    import os

    config = llm_config.get()

    env_keys = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ARK_API_KEY",
                "DASHSCOPE_API_KEY", "DEEPSEEK_API_KEY"]
    env_info = {k: bool(os.getenv(k)) for k in env_keys}

    result = {
        "provider": config.provider,
        "model": config.model,
        "base_url": config.base_url,
        "api_key_set": bool(config.api_key),
        "timeout": config.timeout,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "env_vars": env_info,
    }

    def _text():
        lines = []
        lines.append("")
        lines.append("⚙️  当前 LLM 配置")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"   服务商:    {config.provider}")
        lines.append(f"   模型:      {config.model}")
        lines.append(f"   Base URL:  {config.base_url or '(默认)'}")
        lines.append(f"   API Key:   {'***' if config.api_key else '(未设置，使用环境变量)'}")
        lines.append(f"   超时:      {config.timeout}s")
        lines.append(f"   温度:      {config.temperature}")
        lines.append(f"   Max Tokens:{config.max_tokens}")
        lines.append("")

        lines.append("🔍 已配置的环境变量:")
        for key in env_keys:
            if os.getenv(key):
                lines.append(f"   ✓ {key}")
            else:
                lines.append(f"   ✗ {key}")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_llm_set(args: argparse.Namespace) -> None:
    """设置默认模型"""
    from ..core.llm_config import llm_config

    model = args.model

    if args.provider:
        llm_config.set_model(model, args.provider)
    else:
        llm_config.set_model(model)

    if args.base_url:
        llm_config.set_base_url(args.base_url)

    config = llm_config.get()

    result = {
        "model": model,
        "provider": config.provider,
        "base_url": args.base_url,
    }
    cli_output(result, args, text=lambda: (
        f"\n✅ 已设置默认模型: {model}\n"
        f"   服务商: {config.provider}"
        + (f"\n   API 地址: {args.base_url}" if args.base_url else "")
        + f"\n\n💡 现在可以直接使用对话命令:\n"
        f"   zenskill chat '你好，请介绍一下自己'"
    ))


def cmd_llm_status(args: argparse.Namespace) -> None:
    """检查 LLM 服务状态"""
    from ..core.llm_config import llm_config
    import os

    config = llm_config.get()

    # 检查 LMService 端口状态
    lm_service_status = None
    if config.provider == "lm-service":
        try:
            import httpx
            r = httpx.get(f"http://localhost:{config.service_port}/api/v1/health", timeout=2)
            lm_service_status = "running" if r.status_code == 200 else f"error_{r.status_code}"
        except Exception:
            lm_service_status = "not_running"

    # 检查 API Key
    env_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "volc": "ARK_API_KEY",
        "qwen": "DASHSCOPE_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
    }
    env_key = env_map.get(config.provider)
    api_key_set = bool(env_key and os.getenv(env_key))

    result = {
        "provider": config.provider,
        "model": config.model,
        "lm_service_status": lm_service_status,
        "api_key_set": api_key_set,
    }

    def _text():
        lines = []
        lines.append("")
        lines.append("🔍 LLM 服务状态检查")
        lines.append("=" * 80)
        lines.append("")

        if config.provider == "mock":
            lines.append("✅ 模式: Mock 模式（不消耗 API）")
            lines.append("   适合开发调试和功能测试")
        elif config.provider == "lm-service":
            if lm_service_status == "running":
                lines.append("✅ LMService: 运行中")
            elif lm_service_status and lm_service_status.startswith("error"):
                lines.append(f"⚠️  LMService 响应异常: HTTP {lm_service_status.split('_')[1]}")
            else:
                lines.append("⚠️  LMService 未启动（首次调用自动启动）")
        else:
            lines.append(f"✅ 模式: 直连 API ({config.provider})")
            if env_key:
                if api_key_set:
                    lines.append(f"✅ {env_key}: 已设置")
                else:
                    lines.append(f"⚠️  {env_key}: 未设置")

        lines.append("")
        lines.append(f"当前模型: {config.model}")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_llm_test(args: argparse.Namespace) -> None:
    """测试当前模型"""
    import asyncio
    from ..core.llm_provider import get_llm_provider

    prompt = args.prompt

    try:
        provider = get_llm_provider()
        provider_name = provider.get_model_name()
        response = asyncio.run(provider.simple_chat(prompt))

        result = {
            "ok": True,
            "prompt": prompt,
            "provider": provider_name,
            "response": response,
        }
        cli_output(result, args, text=lambda: (
            f"\n🧪 测试 LLM 模型\n"
            f"{'=' * 80}\n"
            f"\nPrompt: {prompt}\n"
            f"\n使用 Provider: {provider_name}\n"
            f"\n🤖 响应:\n"
            f"{'-' * 80}\n"
            f"{response}\n"
            f"{'-' * 80}\n"
            f"\n✅ 测试成功！\n"
        ))

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        print()
        print("💡 可能的原因:")
        print("   1. API Key 未设置")
        print("   2. 网络连接问题")
        print("   3. 模型名称错误")
        print()



def register_llm_parser(subparsers) -> None:
    """注册 llm 子命令组。"""
    llm_parser = subparsers.add_parser("llm", help="大模型服务管理（Phase 9C）")
    llm_parser.set_defaults(func=cmd_llm_status)  # llm 默认为 status
    llm_subparsers = llm_parser.add_subparsers(dest="subcommand", help="LLM 操作")

    # llm list
    llm_list_parser = llm_subparsers.add_parser("list", help="列出所有支持的模型")
    llm_list_parser.set_defaults(func=cmd_llm_list)

    # llm show
    llm_show_parser = llm_subparsers.add_parser("show", help="显示当前 LLM 配置")
    llm_show_parser.set_defaults(func=cmd_llm_show)

    # llm set
    llm_set_parser = llm_subparsers.add_parser("set", help="设置默认模型")
    llm_set_parser.add_argument("model", help="模型名称")
    llm_set_parser.add_argument("--base-url", help="自定义 API 地址")
    llm_set_parser.add_argument("--provider", help="强制指定服务商")
    llm_set_parser.set_defaults(func=cmd_llm_set)

    # llm status
    llm_status_parser = llm_subparsers.add_parser("status", help="检查 LLM 服务状态")
    llm_status_parser.set_defaults(func=cmd_llm_status)

    # llm test
    llm_test_parser = llm_subparsers.add_parser("test", help="测试当前模型")
    llm_test_parser.add_argument("prompt", nargs="?", default="请简单介绍一下你自己", help="测试提示词")
    llm_test_parser.set_defaults(func=cmd_llm_test)

    # chat 命令（对话）
