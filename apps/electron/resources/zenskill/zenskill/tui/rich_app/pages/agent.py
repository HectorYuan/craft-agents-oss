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

    def render(self, agent_session=None, **kwargs) -> None:
        """渲染 agent 状态。"""
        if agent_session is None:
            self.console.print("[yellow]Agent engine 未初始化[/yellow]")
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
