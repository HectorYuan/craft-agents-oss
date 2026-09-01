"""
ChatVM + 终端对话循环 (Phase T+ · U0A 流式输出)

用法:
    from zenskill.tui.views.chat import ChatSession
    ChatSession().run()           # Plain 模式 (流式)
    ChatSession(rich=True).run()  # Rich 模式 (流式)
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Any, Dict, List, Optional


class ChatSession:
    """终端对话会话 — 流式输出 + 智能上下文"""

    def __init__(self, rich: bool = False):
        self.rich = rich
        self.history: List[Dict[str, str]] = []
        self._running = True

    def run(self):
        """主循环 — ESC / Ctrl+C 退出"""
        self._print_welcome()
        while self._running:
            try:
                user_input = self._read_input()
            except (EOFError, KeyboardInterrupt):
                self._print_goodbye()
                break

            if user_input is None:
                # ESC → 退出对话
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            if user_input.lower() in ("/quit", "/exit", "/q"):
                self._print_goodbye()
                break

            if user_input.lower() == "/clear":
                self.history = []
                self._print_info("对话已清除")
                continue

            if user_input.lower() == "/history":
                self._print_history()
                continue

            self._print_user(user_input)
            self.history.append({"role": "user", "content": user_input})
            self._print_assistant_stream(user_input)

    def _read_input(self) -> Optional[str]:
        """读取用户输入 — Plain 模式支持 ESC 退出

        Returns:
            str 用户输入
            None ESC 键按下 (退出)
        """
        if self.rich:
            try:
                s = input(self._prompt())
                return s
            except Exception:
                return None
        else:
            sys.stdout.write(self._prompt())
            sys.stdout.flush()
            chars = []
            while True:
                try:
                    from ...tui.keyboard import _getch
                    ch = _getch(timeout=0.3)
                    if ch == "\x1b":
                        return None
                    if ch == "\n" or ch == "\r":
                        sys.stdout.write("\n")
                        return "".join(chars)
                    if ch == "\x7f":
                        if chars:
                            chars.pop()
                            sys.stdout.write("\b \b")
                            sys.stdout.flush()
                    elif ch and ch.isprintable():
                        chars.append(ch)
                        sys.stdout.write(ch)
                        sys.stdout.flush()
                except Exception:
                    return None

    def _prompt(self) -> str:
        if self.rich:
            return "\n[bold green]▶[/bold green] "
        return "\n▶ "

    def _get_response(self, user_input: str) -> str:
        """调用 LLM 获取完整回复"""
        try:
            from zenskill.core.llm_provider import get_llm_provider
            provider = get_llm_provider()
            messages = [{"role": "system", "content": self._build_context()}]
            messages.extend(self.history[-10:])
            return asyncio.run(provider.chat(messages))
        except Exception as e:
            return f"(AI 不可用: {e})\n请使用 CLI 命令操作，或设置 API Key。"

    def _print_assistant_stream(self, user_input: str):
        """流式输出 AI 回复 (U0A)"""
        response = self._get_response(user_input)
        if not response:
            return

        # 角色标签
        if self.rich:
            sys.stdout.write("\n[bold blue]ZenSkill:[/bold blue] ")
        else:
            sys.stdout.write("\n\033[34mZenSkill:\033[0m ")
        sys.stdout.flush()

        # 逐字输出
        delay = 0.008
        in_code_block = False
        code_lang = ""
        code_buf = ""

        for i, char in enumerate(response):
            # 代码块边界
            if response[i:i+3] == "```" and (i == 0 or response[i-1] == "\n"):
                if in_code_block:
                    if self.rich and code_buf.strip():
                        sys.stdout.write("\n")
                        sys.stdout.flush()
                        self._print_highlighted(code_buf, code_lang)
                    elif not self.rich:
                        sys.stdout.write(f"\n{self._dim('└' + '─' * 20)}\n")
                        sys.stdout.flush()
                    in_code_block = False
                    code_buf = ""
                    code_lang = ""
                    continue
                else:
                    in_code_block = True
                    end = response.find("\n", i+3)
                    code_lang = response[i+3:end].strip() if end > 0 else ""
                    if not self.rich:
                        sys.stdout.write(f"\n{self._dim('┌─ ' + (code_lang or 'code') + ' ─')}\n")
                    sys.stdout.flush()
                    continue

            if in_code_block:
                code_buf += char
                if not self.rich:
                    sys.stdout.write(char)
                    sys.stdout.flush()
            else:
                sys.stdout.write(char)
                sys.stdout.flush()
            time.sleep(delay)

        # 未闭合的代码块
        if in_code_block and code_buf.strip():
            if self.rich:
                sys.stdout.write("\n")
                sys.stdout.flush()
                self._print_highlighted(code_buf, code_lang)
            else:
                sys.stdout.write(f"\n{self._dim('└' + '─' * 20)}\n")

        sys.stdout.write("\n")
        sys.stdout.flush()

        self.history.append({"role": "assistant", "content": response})

    def _dim(self, text: str) -> str:
        if self.rich:
            return f"[dim]{text}[/dim]"
        return f"\033[90m{text}\033[0m"

    def _print_highlighted(self, code: str, lang: str):
        """Rich 语法高亮代码块 (U1C)"""
        try:
            from rich.syntax import Syntax
            from rich.console import Console
            console = Console()
            syntax = Syntax(code.strip(), lang or "text", theme="monokai",
                           line_numbers=False, word_wrap=True)
            console.print(syntax)
        except Exception:
            print(f"  {code.strip()}")

    def _build_context(self) -> str:
        """构建智能上下文提示词"""
        ctx = "你是 ZenSkill AI 助手，帮助用户管理技能、成长和知识。回答简洁、实用，用中文。\n\n"

        # 注入技能信息
        try:
            from zenskill.core.skill_profile import SkillProfile
            profiles = SkillProfile.list_all(limit=10)
            if profiles:
                ctx += "## 当前已安装技能\n"
                for p in profiles[:8]:
                    icon = {"NOVICE": "🌱", "APPRENTICE": "🌿", "JOURNEYMAN": "🌳",
                            "EXPERT": "⭐", "MASTER": "👑"}.get(p.level, "")
                    ctx += f"- {icon} {p.name} [{p.category}] Lv.{p.level} 调用{p.total_interactions}次\n"
        except Exception:
            pass

        # 注入 GTD 状态
        try:
            from zenskill.core.database import db
            rows = db.execute("SELECT count(*) as c FROM gtd_actions WHERE status != 'done'")
            pending = rows[0]["c"] if rows else 0
            if pending:
                ctx += f"\n## GTD 状态\n- 待处理 Actions: {pending} 个\n"
        except Exception:
            pass

        ctx += "\n用户可以:\n"
        ctx += "- 查看技能: CLI `zenskill spec inspect <id>` 或 TUI 按 3\n"
        ctx += "- 安装技能: CLI `zenskill install npx://<pkg>`\n"
        ctx += "- 管理 GTD: CLI `zenskill gtd dashboard` 或 TUI 按 5\n"
        ctx += "- 搜索技能: CLI `zenskill search <关键词>` 或 TUI 按 /\n"

        return ctx

    def _print_welcome(self):
        if self.rich:
            print("[bold blue]╭─ ZenSkill Chat ─────────────────────────────╮[/bold blue]")
            print("[bold blue]│[/bold blue]  终端对话模式 — 类似 Claude Code       [bold blue]│[/bold blue]")
            print("[bold blue]│[/bold blue]  /quit 退出  /clear 清除  /history 历史 [bold blue]│[/bold blue]")
            print("[bold blue]╰──────────────────────────────────────────╯[/bold blue]")
        else:
            print("\033[36m┌─ ZenSkill Chat ─────────────────────────────┐\033[0m")
            print("\033[36m│\033[0m  终端对话模式 — /quit /clear /history  \033[36m│\033[0m")
            print("\033[36m└──────────────────────────────────────────────┘\033[0m")

    def _print_goodbye(self):
        if self.rich:
            print("[dim]再见 👋[/dim]")
        else:
            print("再见 👋")

    def _print_user(self, text: str):
        if self.rich:
            print(f"\n[bold green]You:[/bold green] {text}")
        else:
            print(f"\n\033[32mYou:\033[0m {text}")

    def _print_assistant(self, text: str):
        if self.rich:
            print(f"\n[bold blue]ZenSkill:[/bold blue] {text}")
        else:
            print(f"\n\033[34mZenSkill:\033[0m {text}")

    def _print_info(self, text: str):
        if self.rich:
            print(f"[dim]{text}[/dim]")
        else:
            print(f"\033[90m{text}\033[0m")

    def _print_history(self):
        if not self.history:
            self._print_info("(暂无对话历史)")
            return
        for msg in self.history:
            role = msg["role"]
            content = msg["content"][:100]
            if role == "user":
                self._print_user(content)
            else:
                self._print_assistant(content)
