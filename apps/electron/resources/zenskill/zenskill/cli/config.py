"""config 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse

def cmd_config_show(args: argparse.Namespace) -> None:
    """显示当前配置和探测到的宿主环境"""
    import os
    from pathlib import Path

    from zenskill.core.llm_provider import get_llm_provider, HostedLLMProvider
    provider = get_llm_provider()

    config_path = Path.home() / ".zenskill" / "config.json"
    config_data = {}
    config_status = "not_exists"
    config_error = ""
    if config_path.exists():
        import json
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            config_status = "loaded"
        except Exception as e:
            config_status = "error"
            config_error = str(e)

    env_data = {}
    env_keys = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY",
                "ARK_API_KEY", "DASHSCOPE_API_KEY", "CLAUDE_ENV", "CLAUDE_CODE"]
    for key in env_keys:
        value = os.environ.get(key)
        if value:
            masked = value[:8] + "..." + value[-4:] if len(str(value)) > 12 else "已设置"
            env_data[key] = "set"
        else:
            env_data[key] = "not_set"

    provider_name = provider.get_model_name()
    active_provider = ""
    if isinstance(provider, HostedLLMProvider):
        active = provider.get_active_provider()
        if active:
            active_provider = active.__class__.__name__

    result = {
        "provider": provider_name,
        "active_provider": active_provider or None,
        "env": env_data,
        "config_path": str(config_path),
        "config_status": config_status,
        "config": {k: ("***" if "key" in str(k).lower() else v) for k, v in config_data.items()} if config_status == "loaded" else {},
        "config_error": config_error or None,
    }

    def _text():
        _ = config_data  # captured from outer scope (original reference for rendering)
        lines = []
        lines.append(f"  ⚙️  ZenSkill 配置信息")
        lines.append(f"  ══════════════════════════════════════════════════════════════")
        lines.append("")

        lines.append(f"  ┌─ 📡 LLM Provider ──────────────────────────────────────────")
        lines.append(f"  │  类型:  {provider_name}")
        if active_provider:
            lines.append(f"  │  激活:  {active_provider}")
        lines.append(f"  └───────────────────────────────────────────────────────────")

        lines.append("")
        lines.append(f"  ┌─ 🔍 环境变量 ────────────────────────────────────────────")
        for key in env_keys:
            value = os.environ.get(key)
            if value:
                masked = value[:8] + "..." + value[-4:] if len(str(value)) > 12 else "已设置"
                lines.append(f"  │  🟢 {key}: {masked}")
            else:
                lines.append(f"  │  ⚪ {key}")
        lines.append(f"  └───────────────────────────────────────────────────────────")

        lines.append("")
        lines.append(f"  ┌─ 📄 配置文件 ────────────────────────────────────────────")
        lines.append(f"  │  路径:  {config_path}")
        if config_status == "loaded":
            lines.append(f"  │  状态:  🟢 已加载")
            for k, v in config_data.items():
                if "key" in str(k).lower():
                    v = str(v)[:8] + "***"
                lines.append(f"  │  • {k}: {v}")
        elif config_status == "error":
            lines.append(f"  │  状态:  🔴 读取失败: {config_error}")
        else:
            lines.append(f"  │  状态:  ⚪ 不存在（首次设置时自动创建）")
        lines.append(f"  └───────────────────────────────────────────────────────────")
        lines.append("")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_config_set(args: argparse.Namespace) -> None:
    """设置配置项"""
    import json
    from pathlib import Path

    config_dir = Path.home() / ".zenskill"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.json"

    # 读取现有配置
    config = {}
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            pass

    # 设置新值
    old_value = config.get(args.key, "(未设置)")
    config[args.key] = args.value

    # 保存配置
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    result = {"ok": True, "key": args.key, "config_path": str(config_path)}

    def _text():
        is_sensitive = "key" in args.key.lower() or "secret" in args.key.lower()
        lines = [f"✅ 配置已更新",
                 f"   - 键: {args.key}"]
        if is_sensitive:
            old_masked = old_value[:8] + "..." + old_value[-4:] if len(str(old_value)) > 12 else old_value
            new_masked = args.value[:8] + "..." + args.value[-4:] if len(str(args.value)) > 12 else "已设置"
            lines.append(f"   - 原值: {old_masked}")
            lines.append(f"   - 新值: {new_masked}")
        else:
            lines.append(f"   - 原值: {old_value}")
            lines.append(f"   - 新值: {args.value}")
        lines.append(f"   - 配置文件: {config_path}")
        return "\n".join(lines)

    cli_output(result, args, text=_text)


def cmd_config_model(args: argparse.Namespace) -> None:
    """查看/配置 LLM 模型信息"""
    from .render import section, card, ok, li
    from .tui.context import get_context_info

    ctx = get_context_info()
    section("LLM 模型配置", icon="🤖")

    card("当前状态", [
        ("Provider", ctx["provider"]),
        ("Model", ctx["model"]),
        ("Backend", ctx["backend"]),
    ])

    card("配置方式", [
        ("环境变量", "ZENSKILL_API_KEY + ZENSKILL_PROVIDER"),
        ("配置文件", "~/zenskill/config.json"),
        ("CLI 命令", "zenskill config set <key> <value>"),
        ("可用 Provider", "openai / anthropic / deepseek / volcengine / qwen"),
    ])

    li(["配置 API Key: zenskill config set api_key sk-xxx",
        "配置 Provider: zenskill config set provider anthropic",
        "配置 Model:   zenskill config set model claude-sonnet-4-20250514",
        "查看当前:     zenskill config show"], icon="info")

    ok("配置后重启 TUI 生效")



def register_config_parser(subparsers) -> None:
    """注册 config 子命令组。"""
    config_parser = subparsers.add_parser("config", help="配置管理")
    config_subparsers = config_parser.add_subparsers(dest="subcommand", help="配置操作")

    # config show
    show_parser = config_subparsers.add_parser("show", help="显示当前配置和探测到的宿主环境")
    show_parser.set_defaults(func=cmd_config_show)

    # config set
    set_parser = config_subparsers.add_parser("set", help="设置配置项 (key value)")
    set_parser.add_argument("key", help="配置项键名 (如: provider, api_key, model)")
    set_parser.add_argument("value", help="配置项值")
    set_parser.set_defaults(func=cmd_config_set)

    # config model
    model_parser = config_subparsers.add_parser("model", help="查看/配置 LLM 模型信息")
    model_parser.set_defaults(func=cmd_config_model)

    # ═══════════════════════════════════════════════════════
    # model 命令 — 模型切换与管理 (参考 ModelSwitcher)
    # ═══════════════════════════════════════════════════════
    model_sub = subparsers.add_parser("model", help="LLM 模型管理 (list/switch/info)")
    model_parsers = model_sub.add_subparsers(dest="model_action", help="模型操作")

    model_list = model_parsers.add_parser("list", help="列出所有可用模型")
    model_list.add_argument("--provider", help="按厂商过滤")
    model_list.set_defaults(func=cmd_model_list)

    model_switch = model_parsers.add_parser("switch", help="切换模型")
    model_switch.add_argument("model", help="模型名称 (如: claude-sonnet-4-20250514)")
    model_switch.add_argument("--provider", help="指定厂商 (如: anthropic)")
    model_switch.set_defaults(func=cmd_model_switch)

    model_info = model_parsers.add_parser("info", help="查看厂商/模型详情")
    model_info.add_argument("name", help="厂商或模型名称")
    model_info.set_defaults(func=cmd_model_info)

    model_setup = model_parsers.add_parser("setup", help="交互式配置模型")
    model_setup.set_defaults(func=cmd_model_setup)

    model_sub.set_defaults(func=cmd_model_list)

    # growth 命令组（成长可视化）

def cmd_model_list(args: argparse.Namespace) -> None:
    """列出所有可用模型"""
    from .render import section, table, ok
    from .core.providers import get_providers

    section("可用模型", icon="🤖")

    for provider in get_providers():
        if args.provider and provider.name != args.provider:
            continue
        rows = []
        for m in provider.models:
            caps = ", ".join(m.capabilities[:3])
            api_key = os.environ.get(provider.api_key_env, "")
            key_status = "✅" if api_key else "❌"
            rows.append([m.name, m.display_name, m.tier, caps, key_status])

        if rows:
            table(["模型", "显示名", "等级", "能力", "KEY"],
                  rows, title=f"{provider.display_name} ({provider.name})")

    ok("使用 `zenskill model switch <name>` 切换")



def cmd_model_switch(args: argparse.Namespace) -> None:
    """切换模型"""
    from .render import section, card, ok, fail as print_fail
    from .core.providers import find_model, get_provider
    from .core.llm_config import llm_config

    model_name = args.model
    provider_name = getattr(args, 'provider', None)

    # 查找模型
    info = find_model(model_name)
    if not info and not provider_name:
        print_fail("模型未找到", f"未找到 {model_name}，使用 --provider 指定厂商")
        return

    if info:
        provider_name = info.provider
        provider = get_provider(provider_name)

        # 检查 API Key
        if provider and provider.api_key_env:
            key = os.environ.get(provider.api_key_env, "")
            if not key:
                print(f"  ⚠️ 环境变量 {provider.api_key_env} 未设置")
                print(f"     设置: export {provider.api_key_env}=sk-xxx")
                print(f"     或:   zenskill config set api_key sk-xxx")

        # 写入配置
        llm_config.set_model(model_name, provider_name)
        section("已切换模型", icon="🤖")
        card(f"{info.display_name}", [
            ("Provider", provider_name),
            ("Model", model_name),
            ("Tier", info.tier),
            ("Capabilities", ", ".join(info.capabilities)),
        ])
        ok("配置已更新", "重启 TUI 生效")
    else:
        # 直接用用户指定
        llm_config.set_model(model_name, provider_name or "custom")
        ok("模型已设置", f"{model_name} ({provider_name})")



def cmd_model_info(args: argparse.Namespace) -> None:
    """查看厂商/模型详情"""
    from .render import section, card, table
    from .core.providers import get_provider, find_model, get_providers

    name = args.name

    # 可能是厂商名
    provider = get_provider(name.lower())
    if provider:
        section(f"{provider.display_name}", icon="🤖")
        card("厂商信息", [
            ("名称", provider.name),
            ("URL", provider.base_url),
            ("KEY 环境变量", provider.api_key_env),
            ("文档", provider.docs_url),
        ])
        if provider.models:
            table(["模型", "显示名", "等级", "能力"],
                  [[m.name, m.display_name, m.tier, ", ".join(m.capabilities[:3])]
                   for m in provider.models],
                  title="可用模型")
        return

    # 可能是模型名
    info = find_model(name)
    if info:
        p = get_provider(info.provider)
        section(info.display_name, icon="🤖")
        card("模型信息", [
            ("名称", info.name),
            ("厂商", info.provider),
            ("等级", info.tier),
            ("能力", ", ".join(info.capabilities)),
            ("上下文", f"{info.context_window:,} tokens" if info.context_window else "N/A"),
        ])
        if p:
            ok(f"切换: zenskill model switch {info.name}")
        return

    from .render import fail as print_fail
    print_fail("未找到", f"未找到 {name}")



def cmd_model_setup(args: argparse.Namespace) -> None:
    """交互式配置模型"""
    from .render import section, li, card, ok
    from .core.providers import get_providers

    section("交互式模型配置", icon="🤖")
    card("支持的厂商", [
        (p.display_name, f"KEY: {p.api_key_env} → {p.base_url}")
        for p in get_providers()
    ])
    li(["1. export ANTHROPIC_API_KEY=sk-ant-xxx   # 设置 API Key",
        "2. zenskill model switch claude-sonnet-4  # 切换模型",
        "3. zenskill model list                    # 查看可用模型",
        "4. zenskill config show                   # 查看配置"], icon="info")
    ok("或使用 .env 文件: echo 'ANTHROPIC_API_KEY=sk-xxx' > ~/.zenskill/.env")


