"""ZenRichTUI 主类 -- Rich + prompt_toolkit 实现。

参照 AgentSwarm SwarmTUI 的 while(true) + prompt_toolkit + Rich 设计。
核心循环: while(true) + prompt_toolkit 输入 + Rich.Live 流式输出。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# Toast 通知样式
TOAST_STYLES = {
    "success": ("✅", "green"),
    "error": ("❌", "red"),
    "warning": ("⚠️", "yellow"),
    "info": ("ℹ️", "blue"),
}

from ..core import (
    ChatSession,
    ParsedCommand,
    classify_input,
    extract_at_references,
    format_cost,
    parse_command,
    stream_from_llm,
)

logger = logging.getLogger(__name__)


# 命令列表用于自动补全
COMMAND_LIST = [
    "/dashboard", "/chat", "/growth", "/skills", "/mirror",
    "/knowledge", "/system", "/doctor", "/llm",
    "/help", "/clear", "/quit", "/version", "/history",
    "/d", "/c", "/g", "/s", "/m", "/k", "/h", "/q",
    "/skills list", "/growth report", "/growth compare",
    "/growth replay", "/growth errors", "/growth feedback",
    "/doctor run", "/doctor state", "/doctor repair",
    "/llm list", "/llm show", "/llm set", "/llm test",
]


# 数字键 -> 页面映射
PAGE_SHORTCUTS = {
    "1": "dashboard",
    "2": "growth",
    "3": "skills",
    "4": "gtd",
    "5": "settings",
    "6": "help",
}


class ZenRichTUI:
    """ZenSkill Rich TUI 主类。

    核心循环: while(true) + prompt_toolkit 输入 + rich 输出。
    """

    def __init__(self, console: Optional[Console] = None, skill_id: str = "zenskill-core"):
        self.console = console or Console()
        self.session = ChatSession(skill_id=skill_id)
        self.data = None  # lazy init
        self._running = False
        self._current_page = "dashboard"
        self._pages: Dict[str, object] = {}
        self._total_cost = 0.0

    def _get_data(self):
        if self.data is None:
            from ..data import TuiDataAdapter
            self.data = TuiDataAdapter()
        return self.data

    def _init_pages(self):
        """懒加载页面组件。"""
        from .pages.dashboard import DashboardPage
        from .pages.skills import SkillsPage
        from .pages.growth import GrowthPage
        from .pages.gtd import GTDPage
        from .pages.knowledge import KnowledgePage
        from .pages.mirror import MirrorPage
        from .pages.search import SearchPage
        from .pages.settings import SettingsPage
        from .pages.skills import SkillsPage
        from .pages.status import StatusPage
        from .pages.help import HelpPage

        data = self._get_data()
        self._pages = {
            "dashboard": DashboardPage(self.console, data),
            "skills": SkillsPage(self.console, data),
            "growth": GrowthPage(self.console, data),
            "gtd": GTDPage(self.console, data),
            "knowledge": KnowledgePage(self.console, data),
            "mirror": MirrorPage(self.console, data),
            "search": SearchPage(self.console, data),
            "settings": SettingsPage(self.console, data),
            "status": StatusPage(self.console, data),
            "help": HelpPage(self.console, data),
        }

    # ═══════════════════════════════════════════════════════════════
    # 主循环
    # ═══════════════════════════════════════════════════════════════

    async def run(self):
        """主循环 -- 参照 AgentSwarm 的 while(true) + yield。"""
        self._running = True
        self._init_pages()

        # 显示 Landing Page
        self._show_landing()

        # 加载历史
        history = self.session.load_history()
        if history:
            self.session.messages = history
            self.console.print(f"[dim]已加载 {len(history)} 条历史消息[/dim]")

        # 显示状态栏
        self._show_status_bar()

        while self._running:
            try:
                user_input = await self._get_input()

                if not user_input:
                    continue

                # 数字键快捷导航: 1-5 切页面
                if user_input in PAGE_SHORTCUTS:
                    self._current_page = PAGE_SHORTCUTS[user_input]
                    self._render_page()
                    self._show_status_bar()
                    continue

                category = classify_input(user_input)

                if category == "command":
                    await self._handle_command(user_input)
                elif category == "file_ref":
                    await self._handle_file_ref(user_input)
                else:
                    await self._handle_chat(user_input)

                # 更新状态栏
                self._show_status_bar()

            except KeyboardInterrupt:
                self.console.print("\n[yellow]已中断[/yellow]")
                continue
            except EOFError:
                self.console.print("\n[dim]再见！[/dim]")
                break
            except Exception as e:
                logger.error("主循环异常: %s", e, exc_info=True)
                self.console.print(f"[red]错误: {e}[/red]")

    # ═══════════════════════════════════════════════════════════════
    # 输入处理 (带命令补全)
    # ═══════════════════════════════════════════════════════════════

    async def _get_input(self) -> str:
        """获取用户输入 -- prompt_toolkit + 命令自动补全 + 历史。"""
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.completion import WordCompleter
            from prompt_toolkit.patch_stdout import patch_stdout
            from prompt_toolkit.history import FileHistory

            # 从 CommandRegistry 获取完整命令列表
            all_commands = self._get_all_commands()

            command_completer = WordCompleter(
                all_commands,
                ignore_case=True,
                match_middle=True,
            )

            # 持久化历史到 ~/.zenskill/tui_history
            history_path = Path.home() / ".zenskill" / "tui_history"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history = FileHistory(str(history_path))

            prompt = PromptSession(history=history)

            with patch_stdout():
                user_input = await prompt.prompt_async(
                    "❯ ",
                    completer=command_completer,
                )
            return user_input.strip()

        except ImportError:
            # fallback 到基础输入
            return input("❯ ").strip()

    def _get_all_commands(self) -> list:
        """从 CommandRegistry 导出所有命令名用于自动补全。"""
        try:
            from ..commands import CommandRegistry
            registry = CommandRegistry()
            commands = [f"/{e.qualified_name}" for e in registry.all()]
            # 加上内置命令
            commands.extend([
                "/help", "/clear", "/quit", "/version", "/history",
                "/d", "/c", "/g", "/s", "/m", "/k", "/h", "/q",
            ])
            return sorted(set(commands))
        except Exception:
            return COMMAND_LIST

    # ═══════════════════════════════════════════════════════════════
    # 状态栏
    # ═══════════════════════════════════════════════════════════════

    def _show_status_bar(self):
        """显示状态栏。"""
        model = self.session.model
        skill = self.session.current_skill_id
        turns = self.session.turn_count

        model_status = (
            f"[green]●[/green] {model}"
            if self.session.llm_available
            else f"[red]●[/red] {model}"
        )

        status_parts = [
            f"[cyan]{skill}[/cyan]",
            model_status,
            f"💬 {turns}",
        ]

        if self._total_cost > 0:
            status_parts.append(f"💰 {format_cost(self._total_cost)}")

        status_text = " │ ".join(status_parts)

        self.console.print(Rule(title=status_text, style="dim"))

    # ═══════════════════════════════════════════════════════════════
    # 命令处理
    # ═══════════════════════════════════════════════════════════════

    async def _handle_command(self, raw: str):
        """处理斜杠命令。"""
        parsed = parse_command(raw)

        if not parsed.is_valid:
            self.console.print(f"[red]无效命令: {raw}[/red]")
            return

        # 内置命令
        if parsed.resource == "help":
            self._current_page = "help"
            self._render_page()
            return

        if parsed.resource in ("quit", "exit"):
            self._running = False
            return

        if parsed.resource == "clear":
            self.session.clear()
            self.console.clear()
            self._show_landing()
            self._toast("对话已清除", "success")
            return

        if parsed.resource == "status":
            page = self._pages.get("status")
            if page:
                page.render()
            return

        if parsed.resource == "history":
            self._show_history()
            return

        if parsed.resource == "search":
            query = " ".join(parsed.args) if parsed.args else ""
            page = self._pages.get("search")
            if page:
                page.render(query=query)
            return

        if parsed.resource == "theme":
            theme_name = parsed.args[0] if parsed.args else "rich"
            self._run_theme(theme_name)
            return

        if parsed.resource == "version":
            self._show_version()
            return

        # 页面导航命令
        if parsed.is_nav:
            page_name = parsed.resource
            if page_name in self._pages:
                self._current_page = page_name
                self._render_page()
            elif page_name == "chat":
                self.console.print("[dim]直接输入消息即可开始对话[/dim]")
            elif page_name in ("doctor", "llm",
                               "system", "ecosystem", "experiment",
                               "inbox", "calendar"):
                # 无独立页面的导航命令 -> 委托给 CLI handler
                self._execute_registry_command(raw)
            else:
                self.console.print(f"[yellow]未知页面: {page_name}[/yellow]")
            return

        # 业务命令 -- 委托给 CommandRegistry
        self._execute_registry_command(raw)

    def _execute_registry_command(self, raw: str):
        """通过 CommandRegistry 执行命令 -- 直接调用 handler 函数。"""
        try:
            from ..commands import CommandRegistry
            registry = CommandRegistry()

            # 解析命令: /doctor state -> qualified_name = "doctor state"
            parts = raw.lstrip("/").split()
            if not parts:
                return

            # 尝试精确匹配 (如 "doctor state")
            qualified = " ".join(parts)
            entry = registry.get(qualified)

            # 尝试单参数匹配 (如 "doctor")
            if not entry and len(parts) == 1:
                entry = registry.get(parts[0])

            # 模糊搜索
            if not entry:
                results = registry.search(parts[0])
                if results:
                    entry = results[0]

            if not entry:
                self.console.print(f"[yellow]未匹配到命令: {raw}[/yellow]")
                self.console.print("[dim]输入 /help 查看可用命令[/dim]")
                return

            if not entry.handler_name:
                self.console.print(f"[dim]/{entry.qualified_name} -- {entry.help}[/dim]")
                return

            # 导入 handler 函数
            import zenskill.__main__ as cli_module
            handler = getattr(cli_module, entry.handler_name, None)
            if not handler:
                self.console.print(f"[red]Handler {entry.handler_name} 不存在[/red]")
                return

            # 构造 args Namespace
            import argparse
            args = argparse.Namespace(
                skill_id=self.session.current_skill_id,
                debug=False,
                profile=None,
                json_output=False,
                n=10,
                output=None,
                dry_run=False,
            )
            # 从命令参数中提取额外字段
            if len(parts) > 1:
                args.extra_args = parts[1:]

            # 捕获 stdout 输出
            import io
            import sys
            old_stdout = sys.stdout
            sys.stdout = captured = io.StringIO()
            try:
                handler(args)
            except SystemExit:
                pass
            finally:
                sys.stdout = old_stdout

            output = captured.getvalue().strip()
            if output:
                self.console.print(Panel(
                    output,
                    border_style="blue",
                    title=f"/{entry.qualified_name}",
                ))
            else:
                self.console.print(f"[dim]/{entry.qualified_name} 执行完成 (无输出)[/dim]")

        except Exception as e:
            self.console.print(f"[red]命令执行失败: {e}[/red]")

    # ═══════════════════════════════════════════════════════════════
    # 文件引用
    # ═══════════════════════════════════════════════════════════════

    async def _handle_file_ref(self, raw: str):
        """处理 @ 文件引用。"""
        cleaned, refs = extract_at_references(raw)

        if not refs:
            self.console.print("[yellow]未找到文件引用[/yellow]")
            return

        from pathlib import Path
        file_content = ""
        for ref in refs:
            path = Path(ref)
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                    file_content += f"\n\n文件 {ref}:\n```\n{content[:2000]}\n```"
                except Exception as e:
                    file_content += f"\n\n文件 {ref}: 读取失败 - {e}"
            else:
                file_content += f"\n\n文件 {ref}: 不存在"

        full_message = cleaned + file_content if cleaned else f"请分析这些文件:{file_content}"
        await self._handle_chat(full_message)

    # ═══════════════════════════════════════════════════════════════
    # 聊天 (流式输出)
    # ═══════════════════════════════════════════════════════════════

    async def _handle_chat(self, user_input: str):
        """处理普通对话 -- Rich.Live 流式输出。"""
        self.console.print(f"\n[bold blue]❯[/bold blue] {user_input}")

        # 保存用户消息
        self.session.send(user_input)

        # 上下文大小检查
        ctx_chars = sum(len(m.content) for m in self.session.messages)
        if ctx_chars > 50000:
            self.console.print("[yellow]⚠ 对话历史较长，建议 /clear 清除后开始新话题[/yellow]")

        # 思考进度
        self.console.print("[dim]▸ 理解意图 → 搜索信息 → 生成回复[/dim]")

        # 组装 LLM 消息
        llm_messages = self.session.assemble_llm_messages(user_input)
        # 去掉最后一条 (assemble 已包含 user_input)
        # 实际上 assemble_llm_messages 已经包含了 system + history + user_input

        full_content = ""
        reasoning_content = ""
        cancelled = False

        try:
            with Live(console=self.console, refresh_per_second=10) as live:
                async for chunk in stream_from_llm(messages=llm_messages):
                    if cancelled:
                        break

                    ctype = chunk["type"]
                    ctext = chunk["content"]

                    if ctype == "reasoning":
                        reasoning_content += ctext
                        display = f"[dim italic]💭 {reasoning_content[-200:]}[/dim italic]"
                        if full_content:
                            display = f"[dim italic]💭 {reasoning_content[-100:]}[/dim italic]\n\n{full_content}"
                        live.update(Markdown(display))

                    elif ctype == "content":
                        full_content += ctext
                        display = full_content
                        if reasoning_content:
                            display = f"[dim italic]💭 思考完成[/dim italic]\n\n{full_content}"
                        live.update(Markdown(display))

                    elif ctype == "error":
                        live.update(f"[red]{ctext}[/red]")

                    elif ctype == "done":
                        break

                    elif ctype == "error":
                        live.update(f"[red]{ctext}[/red]")

                    elif ctype == "done":
                        break

            # 保存回复
            if full_content:
                self.session.receive("assistant", full_content)
                self._total_cost += self._estimate_turn_cost(user_input, full_content)

        except KeyboardInterrupt:
            cancelled = True
            if full_content:
                self.session.receive("assistant", full_content + "\n\n[已中断]")
            self._toast("流式输出已中断", "warning")

        except Exception as e:
            self.console.print(f"\n[red]❌ 对话失败: {e}[/red]")

    def _estimate_turn_cost(self, user_input: str, response: str) -> float:
        """粗略估算本轮成本。"""
        from ..core.cost import estimate_cost, estimate_tokens_from_text
        prompt_tokens = estimate_tokens_from_text(user_input) + 500  # system prompt
        completion_tokens = estimate_tokens_from_text(response)
        return estimate_cost(self.session.model, prompt_tokens, completion_tokens)

    # ═══════════════════════════════════════════════════════════════
    # 页面渲染
    # ═══════════════════════════════════════════════════════════════

    def _render_page(self):
        """渲染当前页面。"""
        page = self._pages.get(self._current_page)
        if page:
            self.console.print()
            page.render()
        else:
            self.console.print(f"[yellow]页面 {self._current_page} 未实现[/yellow]")

    # ═══════════════════════════════════════════════════════════════
    # 特殊页面
    # ═══════════════════════════════════════════════════════════════

    def _show_landing(self):
        """显示 Landing Page。"""
        self.console.print()
        self.console.print(Panel(
            Text("🧘 ZenSkill TUI", style="bold cyan", justify="center") +
            "\n\n" +
            Text("技能成长引擎 · AI 助手", style="dim", justify="center") +
            "\n" +
            Text("输入消息开始对话，或输入 / 查看命令", style="dim", justify="center") +
            "\n" +
            Text("1=仪表盘 2=成长 3=技能 4=GTD 5=设置 6=帮助", style="dim", justify="center"),
            title="[bold cyan]ZenSkill[/bold cyan]",
            border_style="cyan",
        ))

    def _show_version(self):
        """显示版本信息。"""
        try:
            from zenskill import __version__
            ver = __version__
        except Exception:
            ver = "dev"

        self.console.print(Panel(
            f"ZenSkill v{ver}\n"
            f"模型: {self.session.model}\n"
            f"Provider: {self.session.provider_name}\n"
            f"技能: {self.session.current_skill_id}\n"
            f"轮次: {self.session.turn_count}\n"
            f"成本: {format_cost(self._total_cost)}",
            title="版本信息",
            border_style="green",
        ))

    def _show_history(self):
        """显示对话历史。"""
        messages = self.session.get_history(n=20)
        if not messages:
            self.console.print("[dim]暂无对话历史[/dim]")
            return

        table = Table(title=f"📜 对话历史 (最近 {len(messages)} 条)", show_lines=False)
        table.add_column("角色", width=10)
        table.add_column("内容", width=60)

        for msg in messages:
            role_icon = {"user": "👤", "assistant": "🧘", "system": "⚙️"}.get(msg.role, "")
            content = msg.content[:80] + ("..." if len(msg.content) > 80 else "")
            table.add_row(f"{role_icon} {msg.role}", content)

        self.console.print(table)

    def _toast(self, message: str, style: str = "info"):
        """显示 Toast 通知（2 秒后消失效果用 Rich markup 模拟）。"""
        icon, color = TOAST_STYLES.get(style, TOAST_STYLES["info"])
        self.console.print(f"[{color}]{icon} {message}[/{color}]")

    def _run_theme(self, theme_name: str):
        """切换主题（当前仅提示，Rich 主题通过 CONSOLE_THEME 设置）。"""
        valid = ["clean", "rich"]
        if theme_name not in valid:
            self.console.print(f"[yellow]未知主题: {theme_name}，可用: {', '.join(valid)}[/yellow]")
            return
        # 保存到配置
        try:
            from ..themes import save_theme
            save_theme(theme_name)
            self._toast(f"主题已切换为 {theme_name}", "success")
        except Exception as e:
            self._toast(f"主题切换失败: {e}", "error")

    def _run_doctor(self):
        """运行诊断。"""
        try:
            from zenskill.core.doctor import run_doctor
            skill_id = self.session.current_skill_id
            result = run_doctor(skill_id)
            self.console.print(Panel(
                result if result else "系统健康",
                title="🩺 诊断结果",
                border_style="green" if result else "yellow",
            ))
        except Exception as e:
            self.console.print(f"[red]诊断失败: {e}[/red]")

    def _show_llm_info(self):
        """显示 LLM 信息。"""
        try:
            from zenskill.core.llm_provider import get_llm_provider
            from zenskill.core.providers import get_providers

            provider = get_llm_provider()
            providers = get_providers()

            table = Table(title="LLM Provider 列表")
            table.add_column("Provider", style="cyan")
            table.add_column("模型")
            table.add_column("状态")

            for p in providers:
                status = "[green]● 活跃[/green]" if p.name == type(provider).__name__.replace("LLMProvider", "") else "[dim]○[/dim]"
                models = ", ".join(p.models[:3]) if p.models else "-"
                table.add_row(p.name, models, status)

            self.console.print(table)
        except Exception as e:
            self.console.print(f"[red]获取 LLM 信息失败: {e}[/red]")


# ═══════════════════════════════════════════════════════════════
# 入口函数
# ═══════════════════════════════════════════════════════════════


async def run_tui(skill_id: str = "zenskill-core"):
    """运行 Rich TUI。"""
    app = ZenRichTUI(skill_id=skill_id)
    await app.run()


def main(skill_id: str = "zenskill-core"):
    """主入口。"""
    asyncio.run(run_tui(skill_id))
