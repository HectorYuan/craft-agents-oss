"""
AgentVM — Agent 状态 + 会话搜索 ViewModel (Phase T+/P2)

提供:
- AgentVM: Agent 引擎状态展示
- 会话搜索能力：在 /agent 页底部集成搜索功能
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import ViewModel, register_viewmodel


@register_viewmodel("agent")
@dataclass
class AgentVM(ViewModel):
    """Agent 状态 ViewModel -- 搜索历史会话。"""

    title: str = "Agent"
    icon: str = "🧠"

    # 会话搜索字段
    search_query: str = ""
    search_results: List[Dict[str, Any]] = field(default_factory=list)
    show_search: bool = False
    recent_sessions: List[Dict[str, Any]] = field(default_factory=list)

    # Agent 状态字段
    model: str = "unknown"
    provider: str = "unknown"
    session_id: str = ""
    message_count: int = 0
    tool_count: int = 0
    initialized: bool = False
    error: str = ""

    _searcher: Any = field(default=None, repr=False)

    def _get_searcher(self):
        """懒加载 SessionSearcher。"""
        if self._searcher is None:
            from ..core.search import SessionSearcher
            self._searcher = SessionSearcher()
        return self._searcher

    def do_search(self, query: str) -> None:
        """执行搜索并更新结果。"""
        self.search_query = query
        searcher = self._get_searcher()
        if query.strip():
            self.search_results = searcher.search(query)
        else:
            self.search_results = []
            self.recent_sessions = searcher.get_recent_sessions()

    def select_search_result(self, session_id: str) -> None:
        """选中搜索结果，切换会话。

        注意：实际的会话切换由页面层处理，此处只更新 ViewModel 状态。
        """
        self.show_search = False
        self.search_query = ""
        self.search_results = []

    @classmethod
    def load(cls) -> "AgentVM":
        """加载 Agent 状态。"""
        vm = cls()
        try:
            # 尝试从 AgentServerSession 获取状态
            from ..core.agent_server_session import AgentServerSession
            agent = AgentServerSession()
            if agent._initialized:
                info = agent.session_info()
                vm.model = info.get("model", "unknown")
                vm.provider = info.get("provider", "unknown")
                vm.session_id = info.get("session_id", "")
                vm.message_count = info.get("message_count", 0)
                vm.tool_count = info.get("tool_count", 0)
                vm.initialized = True
            else:
                vm.error = "Agent engine 未初始化"
        except Exception as e:
            vm.error = str(e)

        # 加载最近会话列表
        try:
            vm.recent_sessions = vm._get_searcher().get_recent_sessions()
        except Exception:
            pass

        return vm

    def render_l1(self) -> str:
        """Plain ANSI 渲染。"""
        if self.error:
            return f"  [!] {self.error}"

        lines = [
            f"  Model: {self.model}",
            f"  Provider: {self.provider}",
            f"  Session: {self.session_id[:16]}..." if len(self.session_id) > 16 else f"  Session: {self.session_id}",
            f"  Messages: {self.message_count}",
            f"  Tools: {self.tool_count}",
        ]

        if self.show_search:
            lines.append("")
            lines.append(f"  Search: {self.search_query or '(enter query)'}")
            if self.search_results:
                for r in self.search_results[:5]:
                    msg = r.get("content", "")[:50]
                    ts = r.get("timestamp", 0)
                    lines.append(f"    -> [{ts}] {msg}")
                lines.append(f"    ({len(self.search_results)} matches)")
            elif self.search_query:
                lines.append("    (no matches)")

        return "\n".join(lines)

    def render_l2(self) -> str:
        """Rich 渲染。"""
        if self.error:
            return f"[yellow]Agent engine 未初始化[/yellow]"

        lines = [
            f"[bold]Model:[/bold] {self.model}",
            f"[bold]Provider:[/bold] {self.provider}",
            f"[bold]Session:[/bold] {self.session_id[:16]}..." if len(self.session_id) > 16 else f"[bold]Session:[/bold] {self.session_id}",
            f"[bold]Messages:[/bold] {self.message_count}",
            f"[bold]Tools:[/bold] {self.tool_count}",
        ]

        if self.show_search:
            lines.append("")
            lines.append(f"[dim]Search: {self.search_query or '(enter query)'}[/dim]")
            if self.search_results:
                for r in self.search_results[:5]:
                    msg = r.get("content", "")[:50]
                    role = r.get("role", "?")
                    lines.append(f"  [cyan]{role}[/cyan] {msg}")
                lines.append(f"  [dim]{len(self.search_results)} matches[/dim]")
            elif self.search_query:
                lines.append("  [dim]no matches[/dim]")

        return "\n".join(lines)
