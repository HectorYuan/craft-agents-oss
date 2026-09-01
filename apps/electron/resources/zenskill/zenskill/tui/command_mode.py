"""
命令模式（简洁模式）

基于 Rich Console 的轻量即时渲染，支持单字符快捷键和斜杠命令。
适合开发者快速查看状态和执行命令。
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .commands import CommandRegistry, CATEGORIES
from .data import TuiDataAdapter
from .themes import get_theme, load_saved_theme, ZenTheme

if TYPE_CHECKING:
    pass


HELP_TEXT = """[bold]快捷键[/bold]
  1-4     切换页面 (仪表盘/目标/洞察/镜像)
  r       刷新当前页面
  q       退出
  ?       显示帮助
  /       斜杠命令模式

[bold]斜杠命令[/bold]
  /<命名空间> <命令> [参数]
  例如: /growth trend --dimension proficiency
        /doctor
        /info

[bold]主题[/bold]
  /theme clean    切换到简洁主题
  /theme rich     切换到华丽主题"""


class CommandMode:
    """Rich 命令模式 — ViewModel 驱动 (Phase T2)"""

    # 页面注册: 键 → ViewModel 名称 (6 核心)
    PAGES = {
        "1": ("dashboard", "仪表盘"),
        "2": ("chat", "对话"),
        "3": ("growth", "成长"),
        "4": ("mirror", "镜像"),
        "5": ("skills", "技能"),
        "6": ("settings", "系统"),
    }

    def __init__(self):
        self.console = Console()
        self.data = TuiDataAdapter()
        self.registry = CommandRegistry()
        self.theme: ZenTheme = get_theme(load_saved_theme())
        self.current_page = "dashboard"
        self.skill_id = "zenskill-core"
        self._page_cache: dict = {}

        # 初始化技能
        skills = self.data.list_skills()
        if skills:
            self.skill_id = skills[0]["skill_id"]

    def run(self):
        """主循环"""
        self._render_page()
        self._prompt()

    def _prompt(self):
        """键盘驱动主循环 — 支持方向键"""
        from .keyboard import read_key_rich, Key

        self.console.print("\n[dim]方向键/数字/jk 导航 | / 命令 | ? 帮助 | q 退出[/dim]")

        while True:
            try:
                key = read_key_rich()
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[dim]再见[/dim]")
                break

            # 退出
            if key in (Key.Q, Key.ESC):
                self.console.print("[dim]再见[/dim]")
                break

            # 刷新
            elif key == Key.R:
                self._page_cache = {}
                self._render_page()
            # Chat 页面
            elif key == Key.C:
                self.current_page = "chat"
                self._render_page()
            # 分栏布局 (U2A)
            elif key == Key.S:
                self._split_mode = not getattr(self, '_split_mode', False)
                self._render_page()

            # 帮助
            elif key == Key.QUESTION:
                self._render_help()

            # 搜索
            elif key == Key.SLASH:
                self._slash_mode()

            # 数字页面切换
            elif key in (Key.N1, Key.N2, Key.N3, Key.N4,
                        Key.N5, Key.N6, Key.N7, Key.N8):
                num = {Key.N1: "1", Key.N2: "2", Key.N3: "3", Key.N4: "4",
                       Key.N5: "5", Key.N6: "6", Key.N7: "7", Key.N8: "8"}[key]
                self.current_page = self.PAGES[num][0]
                self._render_page()

            # 方向键页面切换 (左右切换页面组, 上下在同页内滚动概念)
            elif key == Key.RIGHT:
                # 下一页
                pages = list(self.PAGES.keys())
                cur = next((k for k, v in self.PAGES.items() if v[0] == self.current_page), "1")
                idx = pages.index(cur)
                nxt = pages[(idx + 1) % len(pages)]
                self.current_page = self.PAGES[nxt][0]
                self._render_page()
            elif key == Key.LEFT:
                pages = list(self.PAGES.keys())
                cur = next((k for k, v in self.PAGES.items() if v[0] == self.current_page), "1")
                idx = pages.index(cur)
                prev = pages[(idx - 1) % len(pages)]
                self.current_page = self.PAGES[prev][0]
                self._render_page()

            # j/k 也可以切换页面
            elif key == Key.J:
                self._page_next()
            elif key == Key.K:
                self._page_prev()

            # 回车刷新
            elif key == Key.ENTER:
                self._render_page()

            else:
                pass  # 忽略未映射按键

    def _page_next(self):
        pages = list(self.PAGES.keys())
        cur = next((k for k, v in self.PAGES.items() if v[0] == self.current_page), "1")
        idx = pages.index(cur)
        nxt = pages[(idx + 1) % len(pages)]
        self.current_page = self.PAGES[nxt][0]
        self._render_page()

    def _page_prev(self):
        pages = list(self.PAGES.keys())
        cur = next((k for k, v in self.PAGES.items() if v[0] == self.current_page), "1")
        idx = pages.index(cur)
        prev = pages[(idx - 1) % len(pages)]
        self.current_page = self.PAGES[prev][0]
        self._render_page()

    def _slash_mode(self):
        """斜杠命令输入模式"""
        from .keyboard import read_key_rich, Key
        self.console.print("\n[bold]  / [/bold]", end="")
        try:
            cmd = input().strip()
        except (EOFError, KeyboardInterrupt):
            return
        if cmd:
            self._execute_slash(cmd)

    def _execute_slash(self, cmdline: str):
        """解析并执行斜杠命令"""
        parts = cmdline.split()
        if not parts:
            return

        # 特殊: search 和 theme
        if parts[0] == "search":
            query = " ".join(parts[1:])
            self._do_search(query)
            return
        if parts[0] == "theme":
            if len(parts) >= 2 and parts[1] in ("clean", "rich"):
                self.theme = get_theme(parts[1])
                from .themes import save_theme
                save_theme(parts[1])
                self.console.print(f"[green]已切换到 {self.theme.display_name} 主题[/green]")
                self._render_page()
            else:
                self.console.print("[yellow]用法: /theme clean|rich[/yellow]")
            return

        # 查找命令
        qualified = " ".join(parts)
        entry = self.registry.get(qualified)
        if not entry:
            # 尝试模糊匹配
            results = self.registry.search(qualified)
            if results:
                entry = results[0]
            else:
                self.console.print(f"[red]未知命令: {qualified}[/red]")
                return

        self.registry.record_usage(entry.qualified_name)

        if entry.action_type == "screen":
            self.current_page = entry.target
            self._render_page()
        else:
            self._execute_cli_command(entry)

    def _do_search(self, query: str):
        """/search 命令处理"""
        if not query:
            self.console.print("[yellow]用法: /search <关键词>[/yellow]")
            return
        try:
            from zenskill.skills.search_engine import SkillSearchEngine
            engine = SkillSearchEngine()
            engine.build_index()
            results = engine.search(query, top_k=10)
            if results:
                from rich.table import Table
                table = Table(title=f"搜索: {query}", show_header=True)
                table.add_column("#")
                table.add_column("名称")
                table.add_column("分类")
                table.add_column("评分")
                for i, r in enumerate(results, 1):
                    table.add_row(str(i), r.name, r.category,
                                 f"⭐{r.rating:.1f}" if r.rating > 0 else "-")
                self.console.print(table)
            else:
                self.console.print(f"[dim]未找到匹配: {query}[/dim]")
        except Exception as e:
            self.console.print(f"[red]搜索失败: {e}[/red]")

    def _execute_cli_command(self, entry):
        """执行 CLI 命令并输出"""
        import argparse
        from io import StringIO
        import sys

        args = argparse.Namespace(
            skill_id=self.skill_id,
            debug=False,
            n=20,
        )
        for flag in entry.flags:
            if flag.default is not None:
                setattr(args, flag.name, flag.default)
        for arg in entry.args:
            if arg.default is not None:
                setattr(args, arg.name, arg.default)

        old_stdout = sys.stdout
        sys.stdout = buffer = StringIO()
        try:
            import zenskill.__main__ as cli_module
            handler = getattr(cli_module, entry.handler_name, None)
            if handler:
                handler(args)
                output = buffer.getvalue()
            else:
                output = f"命令 {entry.qualified_name} 暂未实现"
        except Exception as e:
            output = f"执行失败: {e}"
        finally:
            sys.stdout = old_stdout

        if output.strip():
            self.console.print(Panel(output, title=f"{entry.icon} {entry.display_name}", border_style="blue"))

    def _render_page(self):
        """渲染当前页面 — ViewModel 驱动 + 分栏支持"""
        self.console.clear()

        # Chat 是交互式会话
        if self.current_page == "chat":
            self._render_chat()
            return

        # 分栏模式 (U2A)
        if getattr(self, '_split_mode', False):
            self._render_split()
            return

        self._render_header()

        vm_name = self.current_page
        try:
            # 尝试从 views 加载
            from .views import get_viewmodel
            vm_cls = get_viewmodel(vm_name)
            if vm_cls:
                vm = vm_cls.load()
                output = vm.render_l2()
                if output.strip():
                    self.console.print(output)
                else:
                    self.console.print(f"[dim]暂无数据[/dim]")
            else:
                self._render_fallback(vm_name)
        except Exception as e:
            self.console.print(f"[yellow]页面渲染失败: {e}[/yellow]")

        # 底部快捷键 + 状态栏 (U0B)
        self.console.print()
        self._render_status_bar()

    def _render_split(self):
        """渲染分栏布局 (U2A)"""
        from .views import get_viewmodel
        from .layout import render_split_view

        vm_name = self.current_page
        detail = ""
        try:
            vm_cls = get_viewmodel(vm_name)
            if vm_cls:
                vm = vm_cls.load()
                detail = vm.render_l2()
        except Exception:
            detail = f"[dim]页面 {vm_name} 渲染失败[/dim]"

        page_label = self.PAGES.get(
            next((k for k, v in self.PAGES.items() if v[0] == self.current_page), "1"),
            ("?", "?"))[1]

        render_split_view(self.console, title=page_label, detail=detail or "")
        self._render_status_bar()
        self.console.print("[dim]s 切换分栏 | 1-8 页面 | c 对话 | q 退出[/dim]")

    def _render_status_bar(self):
        """底部状态栏 — 模型/上下文/Agent"""
        from .context import get_context_info
        ctx = get_context_info()

        page_label = self.PAGES.get(
            next((k for k, v in self.PAGES.items() if v[0] == self.current_page), "1"),
            ("?", "?"))[1]

        try:
            from zenskill.core.skill_profile import SkillProfile
            total = len(SkillProfile.list_all(limit=100))
        except Exception:
            total = "?"

        status_parts = [
            f"📄 {page_label}",
            f"📦 {total} skills",
            f"🤖 {ctx['provider']}/{ctx['model']}" if ctx['model'] != '—' else f"🤖 {ctx['provider']}",
            f"🖥 {ctx['backend']}",
        ]
        status = "  |  ".join(status_parts)
        self.console.print(f"[reverse] {status} [/reverse]")

    def _render_chat(self):
        """启动终端对话会话"""
        from .views.chat import ChatSession
        self.console.clear()
        cs = ChatSession(rich=True)
        cs.run()
        # 对话结束后返回主界面
        self._render_page()

    def _render_fallback(self, page: str):
        """未实现 ViewModel 的页面降级 (全部已实现, 保留兼容)"""
        pass

    def _render_help(self):
        """帮助页面"""
        help_text = "[bold]快捷键[/bold]\n"
        for k, v in self.PAGES.items():
            help_text += f"  {k}        {v[1]}\n"
        help_text += "  r       刷新当前页面\n"
        help_text += "  q       退出\n"
        help_text += "  ?       显示帮助\n"
        help_text += "  /       斜杠命令模式\n\n"
        help_text += "[bold]斜杠命令[/bold]\n"
        help_text += "  /search <关键词>    搜索技能\n"
        help_text += "  /theme clean|rich   切换主题\n"
        self.console.print(Panel(help_text, title="帮助", border_style="blue"))

    def _render_header(self):
        """渲染标题栏"""
        state = self.data.get_skill_state(self.skill_id)
        scores = self.data.get_ability_scores(self.skill_id)

        level = state.get("level", "NOVICE")
        usage = state.get("usage_count", 0)
        composite = scores.composite if scores else 0

        level_icons = {
            "NOVICE": "🌱", "APPRENTICE": "📗",
            "ADEPT": "📘", "EXPERT": "📙", "MASTER": "📕",
        }
        icon = level_icons.get(level, "❓")

        header = Text()
        header.append(f"  {icon} ", style="bold")
        header.append(f"{self.skill_id}", style="bold cyan")
        header.append(f"  |  等级: {level}", style="white")
        header.append(f"  |  使用: {usage} 次", style="white")
        header.append(f"  |  综合能力: {composite}", style="bold green")

        self.console.print(Panel(header, border_style="blue"))
