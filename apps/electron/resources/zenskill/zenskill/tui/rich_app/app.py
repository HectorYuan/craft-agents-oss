"""ZenRichTUI 主类 -- Rich + prompt_toolkit 实现。

参照 AgentSwarm SwarmTUI 的 while(true) + prompt_toolkit + Rich 设计。
核心循环: while(true) + prompt_toolkit 输入 + Rich.Live 流式输出。
"""

from __future__ import annotations

import asyncio
import logging
import importlib
import os
from datetime import datetime
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
    "/help", "/clear", "/quit", "/version", "/history", "/agent",
    "/diff", "/export", "/review", "/thinking", "/compact", "/theme", "/status",
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
    "7": "agent",
    "8": "knowledge",
    "9": "mirror",
}


def _tool_style(text: str) -> tuple:
    """X2: 按工具名返回 (icon, color_prefix)。"""
    if "[read" in text or "read" in text[:10]:
        return "📖", "[blue]"
    elif "[write" in text or "write" in text[:10]:
        return "✏️", "[green]"
    elif "[edit" in text or "edit" in text[:10]:
        return "✏️", "[green]"
    elif "[bash" in text or "bash" in text[:10]:
        return "⚡", "[yellow]"
    elif "[grep" in text or "grep" in text[:10]:
        return "🔍", "[cyan]"
    elif "[find" in text or "find" in text[:10]:
        return "🔍", "[cyan]"
    elif "[ls" in text or "ls" in text[:10]:
        return "📂", "[blue]"
    elif "web_fetch" in text or "web_search" in text:
        return "🌐", "[magenta]"
    elif "[git" in text or "git" in text[:10]:
        return "🔧", "[yellow]"
    elif "[delegate" in text or "delegate" in text[:10]:
        return "🤖", "[red]"
    elif "[skill" in text or "skill" in text[:10]:
        return "📚", "[magenta]"
    return "🔧", "[dim]"


class ZenRichTUI:
    """ZenSkill Rich TUI 主类。

    核心循环: while(true) + prompt_toolkit 输入 + rich 输出。
    """

    def __init__(self, console: Optional[Console] = None, skill_id: str = "zenskill-core", use_agent: Optional[bool] = None):
        self.console = console or Console()
        self.session = ChatSession(skill_id=skill_id)
        self.data = None  # lazy init
        self._running = False
        self._current_page = "dashboard"
        self._pages: Dict[str, object] = {}
        self._total_cost = 0.0
        self._agent_session = None  # lazy AgentChatSession
        self._use_agent = use_agent
        self._last_feedback = ("", 0.0)  # T3 微反馈频控 (text, timestamp)
        self._shown_milestones = 0  # T5 已展示的 level_up 里程碑游标
        self._dirty_pages: set = set()  # X3: 需要重渲染的页面

    def _get_agent_session(self):
        """懒加载 AgentSession（优先 AgentServerSession，fallback AgentChatSession）。"""
        if self._agent_session is None:
            model = self.session.model if self.session.model != "未配置" else None
            try:
                from ..core.agent_server_session import AgentServerSession
                self._agent_session = AgentServerSession(
                    model=model, with_memory=True, with_skills=True,
                )
            except Exception:
                try:
                    from ..core.agent_session import AgentChatSession
                    self._agent_session = AgentChatSession(
                        model=model, with_memory=True, with_skills=True,
                    )
                except Exception as e:
                    self.console.print(f"[yellow]Agent engine 不可用: {e}，使用直接 LLM 路径[/yellow]")
                    return None
            # 会话健康检查提示（仅首次加载时触发一次）
            self._show_session_health_hints()
        return self._agent_session

    def _show_session_health_hints(self):
        """检查 sessions 目录健康状态并打印清理提示（首次启动时一次）。"""
        try:
            from ...runtime.agent.session import SessionManager, session_health_hints
            manager = SessionManager()
            for hint in session_health_hints(manager):
                self.console.print(f"[yellow]提示: {hint}[/yellow]")
        except Exception:
            pass

    def _get_data(self):
        if self.data is None:
            from ..data import TuiDataAdapter
            self.data = TuiDataAdapter()
        return self.data

    def mark_dirty(self, pages: list = None) -> None:
        """X3: 写操作后标记页面脏（下次输入前重渲染）。"""
        self._dirty_pages.update(pages or ["dashboard"])

    def _check_and_refresh(self) -> None:
        """X3: 输入间隙检查脏页面并重渲染。"""
        if not self._dirty_pages or self._current_page not in self._dirty_pages:
            return
        try:
            self._render_page()
        except Exception:
            pass
        self._dirty_pages.clear()

    def _init_pages(self):
        """懒加载页面组件。"""
        from .pages.dashboard import DashboardPage
        from .pages.diff import DiffPage
        from .pages.doctor import DoctorPage
        from .pages.review import ReviewPage
        from .pages.skills import SkillsPage
        from .pages.growth import GrowthPage
        from .pages.gtd import GTDPage
        from .pages.knowledge import KnowledgePage
        from .pages.mirror import MirrorPage
        from .pages.search import SearchPage
        from .pages.settings import SettingsPage
        from .pages.status import StatusPage
        from .pages.help import HelpPage
        from .pages.agent import AgentPage

        data = self._get_data()
        self._pages = {
            "dashboard": DashboardPage(self.console, data),
            "diff": DiffPage(self.console, data),
            "doctor": DoctorPage(self.console, data),
            "review": ReviewPage(self.console, data),
            "skills": SkillsPage(self.console, data),
            "growth": GrowthPage(self.console, data),
            "gtd": GTDPage(self.console, data),
            "knowledge": KnowledgePage(self.console, data),
            "mirror": MirrorPage(self.console, data),
            "search": SearchPage(self.console, data),
            "settings": SettingsPage(self.console, data),
            "status": StatusPage(self.console, data),
            "help": HelpPage(self.console, data),
            "agent": AgentPage(self.console, data),
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
                    # X3: chat 完成后标记脏页面 + 检查刷新
                    self.mark_dirty(["dashboard", "gtd", "growth", "agent"])
                    self._check_and_refresh()

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
                "/help", "/clear", "/quit", "/version", "/history", "/agent",
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
            if self._agent_session:
                sid = self._agent_session.clear()
                self.console.print(f"[dim]新 session: {sid[:12]}...[/dim]" if sid else "")
            self.console.clear()
            self._show_landing()
            self._toast("对话已清除", "success")
            return

        if parsed.resource == "status":
            page = self._pages.get("status")
            if page:
                page.render()
            return

        if parsed.resource == "growth" and parsed.action == "achievements":
            page = self._pages.get("growth")
            if page:
                page.render(action="achievements")
            return

        if parsed.resource == "history":
            self._show_history()
            return

        if parsed.resource == "agent":
            await self._handle_agent_command(parsed)
            return

        if parsed.resource == "export":
            self._export_history()
            self.mark_dirty(["dashboard"])
            return

        if parsed.resource == "search":
            query = " ".join(parsed.args) if parsed.args else ""
            page = self._pages.get("search")
            if page:
                page.render(query=query)
            return

        if parsed.resource == "diff":
            page = self._pages.get("diff")
            if page:
                file_path = parsed.args[0] if parsed.args else ""
                page.render(file_path=file_path)
            return

        if parsed.resource == "review":
            page = self._pages.get("review")
            if page:
                scope = parsed.action or parsed.args[0] if parsed.args else ""
                base = parsed.args[1] if len(parsed.args) > 1 else ""
                page.render(scope=scope, base=base)
            return

        if parsed.resource == "thinking":
            self._run_thinking(parsed)
            return

        if parsed.resource == "compact":
            self._run_compact()
            return

        if parsed.resource == "theme":
            # "/theme zen" 时主题名落在 action；"/theme set zen" 时落在 args
            theme_name = parsed.args[0] if parsed.args else (parsed.action or "rich")
            self._run_theme(theme_name)
            self.mark_dirty(["settings"])
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

            # 导入 handler 函数：优先 __main__，miss 后回退 cli/ 拆分模块
            # （CLI 渐进拆分后 graph/gtd/workflow 等 handler 在 zenskill/cli/*）
            import zenskill.__main__ as cli_module
            handler = getattr(cli_module, entry.handler_name, None)
            if not handler:
                import pkgutil
                import zenskill.cli as cli_pkg
                for mod_info in pkgutil.iter_modules(cli_pkg.__path__):
                    try:
                        mod = importlib.import_module(f"zenskill.cli.{mod_info.name}")
                    except Exception:
                        continue
                    handler = getattr(mod, entry.handler_name, None)
                    if handler:
                        break
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
        """处理普通对话 -- 默认走 Agent Engine，失败时降级到直接 LLM。"""
        self.console.print(f"\n[bold blue]❯[/bold blue] {user_input}")

        # 保存用户消息
        self.session.send(user_input)

        # 上下文大小检查
        ctx_chars = sum(len(m.content) for m in self.session.messages)
        if ctx_chars > 50000:
            self.console.print("[yellow]⚠ 对话历史较长，建议 /clear 清除后开始新话题[/yellow]")

        # 选择 LLM 路径：agent engine（默认）或直接 provider
        if self._use_agent is False:
            await self._handle_chat_direct(user_input)
        else:
            agent = self._get_agent_session()
            if agent is not None:
                await self._handle_chat_agent(user_input)
            else:
                await self._handle_chat_direct(user_input)

    async def _handle_chat_agent(self, user_input: str):
        """Agent Engine 路径：工具执行 + 能力注入 + 会话持久化。"""
        agent = self._get_agent_session()
        if agent is None:
            await self._handle_chat_direct(user_input)
            return

        self.console.print("[dim]▸ agent engine 处理中...[/dim]")

        full_content = ""
        reasoning_content = ""
        cancelled = False
        last_render = 0.0
        tool_status = ""

        def _md_render(force: bool = False):
            nonlocal last_render
            import time as _time

            now = _time.monotonic()
            if not force and now - last_render < 0.1:
                return
            last_render = now
            display = full_content
            if reasoning_content and not full_content:
                display = f"[dim italic]💭 {reasoning_content[-200:]}[/dim italic]"
            elif reasoning_content:
                display = f"[dim italic]💭 思考完成[/dim italic]\n\n{full_content}"
            if tool_status:
                display = f"{display}\n\n{tool_status}" if display else tool_status
            live.update(Markdown(display) if display else "")

        try:
            with Live(console=self.console, refresh_per_second=10) as live:
                async for chunk in agent.chat(user_input):
                    if cancelled:
                        break

                    ctype = chunk["type"]
                    ctext = chunk["content"]

                    if ctype == "reasoning":
                        reasoning_content += ctext
                        _md_render()

                    elif ctype == "content":
                        full_content += ctext
                        _md_render()

                    elif ctype == "tool_start":
                        icon, color = _tool_style(ctext)
                        tool_status = f"[dim]{icon} {ctext}[/dim]"
                        _md_render(force=True)

                    elif ctype == "tool_progress":
                        # 实时进度：截断显示最后 80 字符
                        tail = ctext[-80:] if len(ctext) > 80 else ctext
                        tool_status = f"[dim]{icon} {tail}[/dim]"
                        _md_render(force=True)

                    elif ctype == "tool_end":
                        icon, color = _tool_style(ctext)
                        tool_status = f"[dim]{icon} {ctext}[/dim]"
                        _md_render(force=True)

                    elif ctype == "error":
                        live.update(f"[red]{ctext}[/red]")

                    elif ctype == "done":
                        break

                _md_render(force=True)

            # 保存回复到 TUI session（兼容旧路径）
            if full_content:
                self.session.receive("assistant", full_content)
                self._total_cost += self._estimate_turn_cost(user_input, full_content)

            # T3 微反馈（5 分钟同文频控）+ T5 升级仪式
            self._post_chat_companion()

        except KeyboardInterrupt:
            cancelled = True
            agent.abort()
            if full_content:
                self.session.receive("assistant", full_content + "\n\n[已中断]")
            self._toast("流式输出已中断", "warning")

        except Exception as e:
            self.console.print(f"\n[red]❌ Agent engine 错误: {e}[/red]")
            # 降级到直接 LLM 路径
            self.console.print("[dim]降级到直接 LLM 路径...[/dim]")
            await self._handle_chat_direct(user_input)

    def _post_chat_companion(self):
        """T3 微反馈 + T5 升级仪式——均为尽力而为，静默失败。"""
        import time as _time

        # T3: 一句话微反馈，同一内容 5 分钟内不重复
        try:
            from ..data import TuiDataAdapter
            data = self._get_data()
            if not isinstance(data, TuiDataAdapter):
                data = TuiDataAdapter()
                self.data = data
            fb = data.get_instant_feedback_line("zenskill-core").strip()
            if fb:
                text, ts = self._last_feedback
                if fb != text or (_time.time() - ts) > 300:
                    self.console.print(f"[dim]{fb}[/dim]")
                    self._last_feedback = (fb, _time.time())
        except Exception:
            pass

        # T5: 境界突破仪式（新里程碑出现时展示一次）
        try:
            from ...core.paths import SkillStateManager
            milestones = SkillStateManager("zenskill-core").load().get("milestones", [])
            level_ups = [m for m in milestones if m.get("type") == "level_up"]
            if len(level_ups) > self._shown_milestones:
                self._shown_milestones = len(level_ups)
                from ...systems.visualization.level_up_ceremony import LevelUpCeremony
                text = LevelUpCeremony("zenskill-core").get_latest_ceremony()
                if text:
                    self.console.print(text)
        except Exception:
            pass

    async def _handle_agent_command(self, parsed):
        """处理 /agent 子命令。"""
        action = parsed.args[0] if parsed.args else "status"

        if action == "status":
            agent = self._get_agent_session()
            if agent is None:
                self.console.print("[yellow]Agent engine 未初始化[/yellow]")
                return
            page = self._pages.get("agent")
            if page:
                page.render(agent_session=agent)
            else:
                # fallback: 直接打印
                info = agent.session_info()
                self.console.print(f"Model: {info.get('model', '?')}")
                self.console.print(f"Session: {info.get('session_id', '?')[:16]}...")
                self.console.print(f"Tools: {info.get('tool_count', 0)}")

        elif action == "compact":
            agent = self._get_agent_session()
            if agent is None:
                self.console.print("[yellow]Agent engine 未初始化[/yellow]")
                return
            self.console.print("[dim]Compaction 需要 LLM 调用，将在下次 chat 时自动触发[/dim]")

        elif action == "session":
            agent = self._get_agent_session()
            if agent is None:
                self.console.print("[yellow]Agent engine 未初始化[/yellow]")
                return
            info = agent.session_info()
            self.console.print(f"Session ID: {info.get('session_id', '?')}")
            self.console.print(f"Messages: {info.get('message_count', 0)}")

        elif action == "model":
            agent = self._get_agent_session()
            if agent is None:
                self.console.print("[yellow]Agent engine 未初始化[/yellow]")
                return
            model_name = parsed.args[1] if len(parsed.args) > 1 else None
            if not model_name:
                self.console.print(f"当前模型: {agent.session_info().get('model', '?')}")
                self.console.print("[dim]用法: /agent model <model-name>[/dim]")
                return
            result = agent.switch_model(model_name)
            self.console.print(f"模型已切换: {result}")

        elif action == "tools":
            agent = self._get_agent_session()
            if agent is None:
                self.console.print("[yellow]Agent engine 未初始化[/yellow]")
                return
            info = agent.session_info()
            self.console.print(f"已加载 {info.get('tool_count', 0)} 个工具")
            if agent._tools:
                from rich.table import Table
                t = Table(title="Loaded Tools")
                t.add_column("Name", style="bold")
                t.add_column("Description")
                for tool in agent._tools:
                    desc = tool.description[:80] if tool.description else ""
                    t.add_row(tool.name, desc)
                self.console.print(t)

        else:
            self.console.print(f"[yellow]未知子命令: {action}[/yellow]")
            self.console.print("[dim]可用: status, compact, session, model, tools[/dim]")

    async def _handle_chat_direct(self, user_input: str):
        """直接 LLM 路径（原始行为）。"""
        # 思考进度
        self.console.print("[dim]▸ 理解意图 → 搜索信息 → 生成回复[/dim]")

        # 组装 LLM 消息
        llm_messages = self.session.assemble_llm_messages(user_input)

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

    def _companion_line(self) -> str:
        """T1 启动陪伴问候：动态一行（失败返回空，永不阻塞启动）。"""
        try:
            data = self._get_data().get_companion_summary()
            energy = data.get("energy") or {}
            icon = {"critical": "🔴", "low": "🟠", "medium": "🟡", "high": "🟢"}.get(
                energy.get("level"), "🟡")
            line = (f"{data.get('greeting', '')}——{data.get('mood', '')}"
                    f"  {icon} {energy.get('current', 0)}/{energy.get('max', 0)}")
            return line
        except Exception:
            return ""

    def _show_landing(self):
        """显示 Landing Page。"""
        self.console.print()
        body = Text("🧘 ZenSkill TUI", style="bold cyan", justify="center") + "\n\n"
        # T1 陪伴问候：动态一行（认识你），失败静默降级
        companion = self._companion_line()
        if companion:
            body += Text(companion, style="magenta", justify="center") + "\n\n"
        # X8: 续聊提示
        last_sid = None
        try:
            from ..core.agent_session import _load_last_session_id
            last_sid = _load_last_session_id()
        except Exception:
            pass
        if last_sid:
            body += Text(
                f"  ↩ 上次对话 session: {last_sid[:8]}…（输入 /clear 开始新对话）",
                style="dim yellow", justify="center") + "\n"

        body += (
            Text("技能成长引擎 · AI 助手", style="dim", justify="center") +
            "\n" +
            Text("输入消息开始对话，或输入 / 查看命令", style="dim", justify="center") +
            "\n" +
            Text("1=仪表盘 2=成长 3=技能 4=GTD 5=设置 6=帮助 7=Agent 8=知识 9=镜像", style="dim", justify="center")
        )
        self.console.print(Panel(
            body,
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

    def _export_history(self):
        """导出对话历史到文件。"""
        messages = self.session.get_history()
        if not messages:
            self._toast("无对话历史可导出", "warning")
            return

        # 生成 Markdown 格式
        lines = [f"# ZenSkill 对话导出 ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n"]
        for msg in messages:
            role = "用户" if msg.role == "user" else "助手"
            lines.append(f"## {role}\n")
            lines.append(f"{msg.content}\n")

        content = "\n".join(lines)

        # 保存到文件
        export_path = Path.home() / ".zenskill" / "export"
        export_path.mkdir(parents=True, exist_ok=True)
        filename = export_path / f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        filename.write_text(content, encoding="utf-8")

        self._toast(f"已导出到 {filename}", "success")

    def _toast(self, message: str, style: str = "info"):
        """显示 Toast 通知（2 秒后消失效果用 Rich markup 模拟）。"""
        icon, color = TOAST_STYLES.get(style, TOAST_STYLES["info"])
        self.console.print(f"[{color}]{icon} {message}[/{color}]")

    def _run_theme(self, theme_name: str):
        """切换主题：保存配置、应用 accent 色到 console 并刷新当前页面。"""
        from rich.theme import Theme as RichTheme

        from ..themes import get_theme, list_themes, save_theme

        valid = list_themes()
        if theme_name not in valid:
            self.console.print(f"[yellow]未知主题: {theme_name}，可用: {', '.join(valid)}[/yellow]")
            return
        # 保存到配置
        try:
            save_theme(theme_name)
            theme = get_theme(theme_name)
            # 替换上次 push 的主题，避免样式栈累积
            if getattr(self, "_theme_pushed", False):
                self.console.pop_theme()
            styles = dict(theme.rich_styles)
            if "background" in styles:
                # 映射为命名样式 [background]，使 markup 可绘制背景色
                styles["background"] = f"on {styles['background']}"
            self.console.push_theme(RichTheme(styles))
            self._theme_pushed = True
            self._render_page()
            self._toast(f"主题已切换为 {theme_name}", "success")
        except Exception as e:
            self._toast(f"主题切换失败: {e}", "error")

    def _run_thinking(self, parsed):
        """切换 thinking level。"""
        level = parsed.args[0] if parsed.args else (parsed.action or "medium")
        valid_levels = ("low", "medium", "high")
        if level not in valid_levels:
            self._toast(f"无效 thinking level: {level}，可选: {', '.join(valid_levels)}", "warning")
            return
        try:
            self._thinking_level = level
            agent = getattr(self, "_agent_session", None)
            if agent and hasattr(agent, "switch_thinking"):
                result = agent.switch_thinking(level)
                self._toast(f"thinking level → {result}", "success")
            else:
                self._toast(f"thinking level → {level}", "success")
        except Exception as e:
            self._toast(f"thinking level 设置失败: {e}", "error")

    def _run_compact(self):
        """手动压缩当前 agent 会话上下文。"""
        try:
            import asyncio
            asyncio.create_task(self._do_compact())
        except Exception as e:
            self._toast(f"compact 失败: {e}", "error")

    async def _do_compact(self):
        """执行 compact（代理模式下委托 agent session；否则 CLI 透传）。"""
        try:
            agent = getattr(self, "_agent_session", None)
            if agent and hasattr(agent, "compact"):
                result = await agent.compact()
                self._toast(f"compact: {result}", "success")
            else:
                # CLI 透传
                self._execute_registry_command("/compact")
        except Exception as e:
            self._toast(f"compact 失败: {e}", "error")

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
