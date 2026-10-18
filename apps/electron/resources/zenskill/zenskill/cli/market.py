"""market 源管理子命令（W1，方案 7.2）：list / add / remove / enable / disable。

`zenskill market search` 仍由 __main__ 的 cmd_market_search 提供；
本模块只管源生命周期（读+写 ~/.zenskill/markets.yaml，经 MarketSourceRegistry）。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import yaml

from ..cli_utils import output as cli_output
from ..render import table


def _registry():
    from ..skills.market_registry import get_default_registry

    return get_default_registry()


def _fail(args: argparse.Namespace, errors: list[str]) -> None:
    lines = "\n".join(f"  - {e}" for e in errors)
    cli_output({"ok": False, "errors": errors}, args,
               text=lambda: f"失败:\n{lines}")
    raise SystemExit(1)


def _load_config_arg(raw: str) -> Dict[str, Any]:
    """支持 YAML 文件路径 / 内联 JSON / 内联 YAML 单源配置"""
    path = Path(raw)
    if path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        text = raw.strip()
        if not text:
            raise ValueError("配置为空")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = yaml.safe_load(text)
    if isinstance(data, dict) and "sources" in data and "name" not in data:
        sources = data.get("sources")
        if isinstance(sources, list) and len(sources) == 1:
            data = sources[0]
        else:
            raise ValueError("一次只能添加一个源（sources 列表请拆成单条）")
    if not isinstance(data, dict):
        raise ValueError(f"源配置必须是对象: {raw[:80]}")
    return data


# ── 子命令 ──


def cmd_market_list(args: argparse.Namespace) -> None:
    reg = _registry()
    sources = reg.list_sources()
    with_health = bool(getattr(args, "health", False))
    if with_health:
        health = {h["name"]: h for h in reg.health_check()}
        for s in sources:
            if s["name"] in health:
                s["health"] = health[s["name"]]

    def _text() -> str:
        headers = ["源", "类型", "启用", "token", "来源"]
        if with_health:
            headers += ["可达", "延迟", "认证"]
        rows = []
        for s in sources:
            token = s.get("token_env") or "—"
            if s.get("token_env"):
                token += "（已设置）" if s.get("token_set") else "（未设置）"
            row = [s["name"], s["type"], "是" if s["enable"] else "否",
                   token, s["origin"]]
            if with_health:
                h = s.get("health") or {}
                row += [
                    "是" if h.get("reachable") else "否",
                    f"{h['latency_ms']}ms" if h.get("latency_ms") is not None else "—",
                    h.get("auth", "—"),
                ]
            rows.append(row)
        table(headers, rows, title="市场源")
        if with_health:
            print("  探测口径: 内置源 HEAD 官方端点 / 配置源空查询搜索（5s 超时）")
        return ""

    cli_output({"count": len(sources), "sources": sources}, args, text=_text)


def cmd_market_add(args: argparse.Namespace) -> None:
    from ..skills.market_registry import MarketSourceError

    try:
        config = _load_config_arg(args.config)
    except ValueError as e:
        _fail(args, [f"配置解析失败: {e}"])
        return
    try:
        info = _registry().add_source(config)
    except MarketSourceError as e:
        _fail(args, e.errors)
        return
    except Exception as e:
        _fail(args, [f"{type(e).__name__}: {e}"])
        return
    cli_output(
        {"ok": True, **info}, args,
        text=lambda: f"已添加市场源 {info['name']}（写入 ~/.zenskill/markets.yaml）")


def cmd_market_remove(args: argparse.Namespace) -> None:
    from ..skills.market_registry import MarketSourceError

    try:
        info = _registry().remove_source(args.name)
    except MarketSourceError as e:
        _fail(args, e.errors)
        return
    except Exception as e:
        _fail(args, [f"{type(e).__name__}: {e}"])
        return
    cli_output({"ok": True, **info}, args,
               text=lambda: f"已移除市场源 {args.name}")


def cmd_market_enable(args: argparse.Namespace) -> None:
    _cmd_toggle(args, True)


def cmd_market_disable(args: argparse.Namespace) -> None:
    _cmd_toggle(args, False)


def _cmd_toggle(args: argparse.Namespace, enable: bool) -> None:
    from ..skills.market_registry import MarketSourceError

    action = "启用" if enable else "停用"
    try:
        info = _registry().set_enable(args.name, enable)
    except MarketSourceError as e:
        _fail(args, e.errors)
        return
    except Exception as e:
        _fail(args, [f"{type(e).__name__}: {e}"])
        return
    cli_output({"ok": True, **info}, args,
               text=lambda: f"已{action}市场源 {args.name}（enable={info['enable']}）")


def register_market_admin(market_sub) -> None:
    """注册 market 源管理子命令（由 __main__ 的 market 命令组调用）"""
    list_p = market_sub.add_parser("list", help="列出市场源（内置/配置/运行时）")
    list_p.add_argument("--health", action="store_true",
                        help="逐源健康探测（内置源 HEAD 端点、配置源空查询，5s 超时）")
    list_p.set_defaults(func=cmd_market_list)

    add_p = market_sub.add_parser(
        "add", help="添加市场源（generic-http）：YAML 文件路径或内联 JSON/YAML")
    add_p.add_argument("config", help="源配置（YAML 文件路径或内联 JSON 字符串）")
    add_p.set_defaults(func=cmd_market_add)

    remove_p = market_sub.add_parser("remove", help="移除配置源（内置源仅可 disable）")
    remove_p.add_argument("name", help="源名称")
    remove_p.set_defaults(func=cmd_market_remove)

    enable_p = market_sub.add_parser("enable", help="启用市场源")
    enable_p.add_argument("name", help="源名称")
    enable_p.set_defaults(func=cmd_market_enable)

    disable_p = market_sub.add_parser("disable",
                                      help="停用市场源（内置源用此命令代替删除）")
    disable_p.add_argument("name", help="源名称")
    disable_p.set_defaults(func=cmd_market_disable)
