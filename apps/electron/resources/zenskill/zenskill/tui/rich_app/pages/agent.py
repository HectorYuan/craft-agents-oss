"""Agent Engine 页面 -- /agent 命令或快捷键 7。

展示 agent 状态：模型/会话/工具/能力/最近执行。
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


class AgentPage:
    """Agent Engine 状态页面。"""

    def __init__(self, console: Console, data=None):
        self.console = console
        self.data = data
        # 搜索状态
        self._search_mode = False
        self._search_input = ""
        self._search_results = []
        self._selected_index = -1
        # 会话切换请求标记：app.py 主循环检测此字段并执行实际切换
        self._pending_session_switch: str | None = None

    def handle_key(self, key: str) -> bool:
        """处理键盘输入。返回 True 表示事件已消费。"""
        if not self._search_mode:
            if key == "/":
                self._search_mode = True
                self._selected_index = 0
                return True
            return False
        if key == "/":
            return True
        if key == "tab":
            if self._search_results:
                self._selected_index = (self._selected_index + 1) % len(self._search_results)
            return True
        if key == "enter":
            if self._search_results and 0 <= self._selected_index < len(self._search_results):
                result = self._search_results[self._selected_index]
                self._pending_session_switch = result.get("session_id")
                self._search_mode = False
                return True
            elif self._search_input.strip():
                # 无选中但有输入：执行搜索
                self.do_search(self._search_input)
                return True
            return True
        if key == "escape":
            self._search_mode = False
            self._search_input = ""
            self._search_results = []
            self._selected_index = 0
            return True
        if key == "backspace":
            self._search_input = self._search_input[:-1]
            return True
        if len(key) == 1 and key.isprintable():
            self._search_input += key
            self._selected_index = 0
            return True
        return False

    def get_selected_session(self) -> str | None:
        """返回当前选中的搜索结果会话 ID。"""
        if self._search_results and 0 <= self._selected_index < len(self._search_results):
            return self._search_results[self._selected_index].get("session_id")
        return None

    def do_search(self, query: str, limit: int = 20) -> None:
        """执行会话搜索，结果存入 _search_results。"""
        if not query.strip():
            return
        try:
            from zenskill.runtime.agent.session import SessionManager
            manager = SessionManager()
            results = []
            query_lower = query.lower()
            for s_info in manager.list_sessions():
                sid = s_info["id"]
                try:
                    sess = manager.load(sid)
                except Exception:
                    continue
                for entry in sess.entries:
                    if entry.type != "message":
                        continue
                    msg_dict = entry.data.get("message") or {}
                    content = msg_dict.get("content")
                    if content is None:
                        continue
                    texts = []
                    if isinstance(content, str):
                        texts.append(content)
                    elif isinstance(content, list):
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "text":
                                texts.append(b.get("text", ""))
                    full = " ".join(texts)
                    if query_lower not in full.lower():
                        continue
                    results.append({
                        "session_id": sid,
                        "entry_id": entry.id,
                        "preview": full[:100].replace("\n", " "),
                    })
                    if len(results) >= limit:
                        break
                if len(results) >= limit:
                    break
            self._search_results = results
            self._selected_index = 0 if results else -1
        except Exception:
            self._search_results = []

    def render(self, agent_session=None, **kwargs) -> None:
        """渲染 agent 状态。"""
        if agent_session is None:
            self.console.print("[yellow]Agent engine 未初始化[/yellow]")
            return

        # 搜索模式：输入框 + 结果列表
        if self._search_mode:
            self._render_search()
            return

        info = agent_session.session_info()

        # 1. 基本状态
        self._render_status(info)

        # 2. 工具列表
        self._render_tools(agent_session)

        # 3. 能力列表
        self._render_capabilities(info)

        # 4. 成长面板（T4）
        self._render_growth()

        # 5. 工具日志（X7）
        self._render_tool_log(agent_session)

    def _render_status(self, info: dict) -> None:
        """渲染模型/会话状态。"""
        table = Table(title="Agent Status", show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="bold cyan", width=14)
        table.add_column("Value")

        initialized = info.get("initialized", False)
        table.add_row("Status", "[green]Ready[/green]" if initialized else "[red]Not Ready[/red]")
        table.add_row("Model", info.get("model", "unknown"))
        table.add_row("Provider", info.get("provider", "unknown"))

        sid = info.get("session_id", "")
        table.add_row("Session", sid[:16] + "..." if len(sid) > 16 else sid)
        table.add_row("Messages", str(info.get("message_count", 0)))
        table.add_row("Tools", str(info.get("tool_count", 0)))
        table.add_row("Thinking", info.get("thinking_level", "medium"))

        error = info.get("error")
        if error:
            table.add_row("Warning", f"[yellow]{error}[/yellow]")

        self.console.print(Panel(table, title="[bold]🧠 Agent Engine[/bold]", border_style="blue"))

    def _render_tools(self, agent_session) -> None:
        """渲染已加载工具列表。"""
        if not agent_session._tools:
            return

        table = Table(title="Loaded Tools", show_lines=False)
        table.add_column("Name", style="bold", width=16)
        table.add_column("Type", width=10)
        table.add_column("Description")

        for tool in agent_session._tools:
            name = tool.name
            if name.startswith("skill_"):
                tool_type = "[dim]skill[/dim]"
            elif name.startswith("memory_"):
                tool_type = "[cyan]cap[/cyan]"
            else:
                tool_type = "[green]core[/green]"
            desc = (tool.description or "")[:80]
            table.add_row(name, tool_type, desc)

        self.console.print(Panel(table, border_style="dim"))

    def _render_capabilities(self, info: dict) -> None:
        """渲染能力列表。"""
        caps = info.get("capabilities", [])
        if not caps:
            return

        cap_styles = {
            "task_type": ("📋", "Task Type"),
            "memory": ("💾", "Memory"),
            "reflection": ("🪞", "Reflection"),
            "summary": ("📝", "Summary"),
        }

        items = []
        for cap in caps:
            icon, label = cap_styles.get(cap, ("•", cap))
            items.append(f"{icon} {label}")

        self.console.print(
            Panel(
                "  ".join(items),
                title="Capabilities",
                border_style="dim",
            )
        )

    def _render_growth(self) -> None:
        """T4 成长面板：能量（境界上限联动）/ 成就进度 / episodes 计数。"""
        try:
            from ....core.paths import SkillStateManager
            from ....systems.gtd.energy import EnergyEngine
            from ....systems.active.achievement_system import AchievementSystem

            skill_id = "zenskill-core"
            energy = EnergyEngine().status()
            ach = AchievementSystem(skill_id).evaluate()
            state = SkillStateManager(skill_id).load()
            episodes = state.get("episodes", [])
            agent_sessions = sum(1 for e in episodes if e.get("action") == "agent_session")

            filled = int(min(energy.get("pct") or 0, 1) * 20)
            bar = "█" * filled + "░" * (20 - filled)
            icon = {"critical": "🔴", "low": "🟠", "medium": "🟡", "high": "🟢"}.get(
                energy.get("level"), "🟡")

            lines = [
                f"{icon} 能量  [bold]{energy.get('current_energy')}/{energy.get('max_energy')}[/bold]  {bar}"
                f"   境界 [bold]{state.get('level', '?')}[/bold]（{state.get('usage_count', 0)} 次使用）",
                f"🏆 成就  [bold]{ach.get('count', 0)}/{ach.get('total', 0)}[/bold]"
                f"   会话回流 episodes: [bold]{agent_sessions}[/bold]",
            ]
            self.console.print(Panel(
                "\n".join(lines),
                title="Growth",
                border_style="dim",
            ))
        except Exception:
            pass  # 成长数据失败不影响 agent 页核心信息

    def _render_tool_log(self, agent_session) -> None:
        """X7 工具日志：从 session 收集最近 10 条工具执行记录。"""
        try:
            if not agent_session._session:
                return
            entries = agent_session._session.entries
            tool_logs = []
            for e in reversed(entries):
                if e.type == "custom" and e.data.get("tool_name"):
                    tool_logs.append(e)
                    if len(tool_logs) >= 10:
                        break
            if not tool_logs:
                return

            table = Table(title="Tool Log (recent)", show_lines=False)
            table.add_column("Tool", style="bold", width=16)
            table.add_column("Status", width=8)
            table.add_column("Result", max_width=60)

            # 工具类型→颜色/图标映射（X2）
            tool_styles = {
                "read": ("📖", "[blue]read[/blue]"),
                "write": ("✏️", "[green]write[/green]"),
                "edit": ("✏️", "[green]edit[/green]"),
                "bash": ("⚡", "[yellow]bash[/yellow]"),
                "grep": ("🔍", "[cyan]grep[/cyan]"),
                "find": ("🔍", "[cyan]find[/cyan]"),
                "ls": ("📂", "[blue]ls[/blue]"),
                "web_fetch": ("🌐", "[magenta]web_fetch[/magenta]"),
                "web_search": ("🌐", "[magenta]web_search[/magenta]"),
                "git": ("🔧", "[yellow]git[/yellow]"),
                "delegate": ("🤖", "[red]delegate[/red]"),
            }

            for log in tool_logs:
                name = log.data.get("tool_name", "?")
                success = log.data.get("success", True)
                icon, styled = tool_styles.get(name, ("🔧", name))
                status = f"{icon} ✓" if success else "✗"
                result = str(log.data.get("result", ""))[:60]
                table.add_row(styled, status, result)

            self.console.print(Panel(table, border_style="dim"))
        except Exception:
            pass  # 日志失败不影响 agent 页核心信息

    def _render_search(self) -> None:
        """渲染会话搜索界面。"""
        # 执行搜索（输入变化时）
        self.do_search(self._search_input)
        # 输入框
        self.console.print(
            Panel(f"[bold]🔍 搜索会话[/bold]  输入关键词，Tab 选择，Enter 切换，Esc 退出",
                  border_style="yellow"))
        self.console.print(f"  搜索: {self._search_input}_")
        # 结果列表
        if self._search_results:
            for i, r in enumerate(self._search_results):
                mark = "▸" if i == self._selected_index else " "
                sid = r.get("session_id", "")[:12]
                preview = r.get("preview", "")[:60]
                self.console.print(f"  {mark} [{sid}] {preview}")
        elif self._search_input.strip():
            self.console.print("  [dim]未找到匹配结果[/dim]")
        else:
            self.console.print("  [dim]输入关键词开始搜索...[/dim]")
