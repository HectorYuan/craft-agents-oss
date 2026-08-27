"""
PlainTUI — 零依赖终端界面 (Phase R2)

当 Textual 和 Rich 都不可用时，提供基于纯 ANSI 转义码的交互界面。

用法:
    from zenskill.tui.plain_mode import PlainTUI
    PlainTUI().run()
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional


class PlainTUI:
    """零依赖 TUI — 顶部状态栏 + 内容区 + 底部快捷键

    界面:
        ╔══ ZenSkill v2.6.0 | 📊 Dashboard | 📦 12 skills | c 对话 | q 退出 ══╗
        ║                                                                       ║
        ║  [页面内容区]                                                          ║
        ║                                                                       ║
        ╚═════════════════════════════════════════════════════════════════════════╝
          1-8 页面  ↑↓←→ jk 导航  c 对话  / 搜索  q 退出
    """

    PAGES = [
        ("d", "📊", "Dashboard"),
        ("c", "💬", "Chat"),
        ("g", "📈", "Growth"),
        ("m", "🪞", "Mirror"),
        ("s", "📦", "Skills"),
        ("x", "⚙️", "System"),
    ]

    def __init__(self):
        self._width = self._term_width()
        self._running = True
        self._pages: Dict[str, callable] = {}
        self._current_page: Optional[str] = None
        self._register_pages()

    def _term_width(self) -> int:
        try:
            return os.get_terminal_size().columns
        except Exception:
            return 80

    def _register_pages(self):
        self._pages = {
            "d": self._page_vm("dashboard"),
            "g": self._page_vm("growth"),
            "s": self._page_vm("skills"),
            "m": self._page_vm("memory"),
            "t": self._page_vm("gtd"),
            "i": self._page_vm("insights"),
            "f": self._page_vm("search"),
            "x": self._page_vm("settings"),
            "c": self._chat_session,
        }
        self._page_names = {p[0]: (p[1], p[2]) for p in self.PAGES}

    def _page_vm(self, vm_name: str):
        """创建 ViewModel 驱动的页面渲染器"""
        def render():
            try:
                from .views import get_viewmodel
                vm_cls = get_viewmodel(vm_name)
                if vm_cls:
                    vm = vm_cls.load()
                    output = vm.render_l1()
                    if output.strip():
                        print(output)
                    else:
                        print(f"  (暂无数据)")
                else:
                    print(f"  (页面 {vm_name} 开发中...)")
            except Exception as e:
                print(f"  ⚠️ 渲染失败: {e}")
        return render

    def _chat_session(self):
        """AI 对话"""
        from .views.chat import ChatSession
        cs = ChatSession(rich=False)
        cs.run()

    def _page_fallback(self, name: str, label: str):
        """占位页面"""
        def render():
            tips = {
                "insights": "洞察功能: 使用 CLI `zenskill insight unread`",
                "search": "搜索: 使用 CLI `zenskill search <关键词>`",
                "settings": "设置: 暂无 GUI 配置，使用 CLI `zenskill config`",
            }
            print(f"  ℹ️ {label}")
            print(f"  {tips.get(name, '页面开发中...')}")
        return render

    def _clear(self):
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

    def _color(self, code: int, text: str) -> str:
        return f"\033[{code}m{text}\033[0m"

    def _top_bar(self, page_name: str = "") -> str:
        """顶部状态栏 — 版本 + 当前模块 + 模型 + 技能数"""
        from zenskill import __version__
        from .context import get_context_info
        ctx = get_context_info()

        try:
            from zenskill.core.skill_profile import SkillProfile
            total = len(SkillProfile.list_all(limit=100))
        except Exception:
            total = "?"

        w = min(self._width - 2, 78)
        if page_name:
            left = f" ZenSkill v{__version__} | {page_name}"
        else:
            left = f" ZenSkill v{__version__} | 主菜单"

        model_info = f"{ctx['provider']}/{ctx['model']}" if ctx['model'] != '—' else ctx['provider']
        right = f"🤖 {model_info} | 📦 {total} skills | c 对话 | q 退出 "
        pad = max(0, w - len(left) - len(right) - 2)
        bar = left + " " * pad + right

        top = self._color(36, "╔" + "═" * w + "╗")
        mid = self._color(36, "║") + self._color(37, bar[:w]) + self._color(36, "║")
        bot = self._color(36, "╠" + "═" * w + "╣")
        return f"{top}\n{mid}\n{bot}"

    def _bottom_bar(self) -> str:
        """底部快捷键栏"""
        w = min(self._width - 2, 78)
        keys = "d/g/s/m/t/i/f/x 页面 | ↑↓←→ jk 导航 | c 对话 | / 搜索 | q 退出"
        pad = max(0, w - len(keys))
        bar = keys + " " * pad
        bot = self._color(36, "╚" + "═" * w + "╝")
        hint = f"  {self._color(90, bar[:w])}"
        return f"{bot}\n{hint}"

    def _main_menu(self) -> str:
        """主页菜单"""
        w = min(self._width - 2, 78)
        lines = [self._top_bar()]

        for key, icon, label in self.PAGES:
            desc = {"Dashboard": "技能概览", "Growth": "五维成长", "Skills": "技能列表",
                    "Memory": "记忆管理", "GTD": "任务管理", "Insights": "洞察反思",
                    "Search": "搜索技能", "Settings": "系统设置", "Chat": "AI 对话"}.get(label, "")
            lines.append(f"  ║  [{key}] {icon} {label:<12s} {self._color(90, desc)}" + " " * max(0, w - 32 - len(desc)) + "║")

        lines.append(f"  ║" + " " * w + "║")
        lines.append(self._bottom_bar())
        return "\n".join(lines)

    def run(self):
        """主循环 — 顶部状态栏 + 快捷键驱动"""
        self._clear()
        print(self._main_menu())

        while self._running:
            try:
                key = self._read_key()
            except (EOFError, KeyboardInterrupt):
                print("\n  再见!")
                break

            # 退出
            if key in ("q", "Q"):
                print("  再见!")
                break

            # 返回主页
            if key in ("b", "B", "esc") and self._current_page:
                self._current_page = None
                self._clear()
                print(self._main_menu())
                continue

            # ESC 主页无操作
            if key in ("esc",) and not self._current_page:
                continue

            # 刷新
            if key == "r" and self._current_page:
                self._clear()
                self._render_page(self._current_page)
                continue

            # 搜索
            if key == "/":
                self._do_search()
                continue

            # 字母快捷键切换页面
            page_keys = {p[0]: p for p in self.PAGES}
            if key.lower() in page_keys:
                pg = page_keys[key.lower()]
                self._current_page = key.lower()
                self._clear()
                self._render_page(key.lower())
                continue

            # 方向键翻页
            if key in ("right", "j", "down"):
                self._nav_page(1)
                continue
            if key in ("left", "k", "up"):
                self._nav_page(-1)
                continue

    def _render_page(self, page_key: str):
        """渲染指定页面"""
        _, icon, label = next(p for p in self.PAGES if p[0] == page_key)
        print(self._top_bar(page_name=f"{icon} {label}"))
        if page_key in self._pages:
            self._pages[page_key]()
        print(self._bottom_bar())

    def _nav_page(self, direction: int):
        """方向键翻页"""
        keys = [p[0] for p in self.PAGES]
        if self._current_page and self._current_page in keys:
            idx = keys.index(self._current_page)
            new_idx = (idx + direction) % len(keys)
            self._current_page = keys[new_idx]
        else:
            self._current_page = keys[0]
        self._clear()
        self._render_page(self._current_page)

    def _read_key(self) -> str:
        """读取按键 — 支持方向键"""
        from .keyboard import read_key, Key
        key = read_key()

        # 映射到字符串
        mapping = {
            Key.UP: "up", Key.DOWN: "down", Key.LEFT: "left", Key.RIGHT: "right",
            Key.ENTER: "enter", Key.ESC: "esc",
            Key.Q: "q", Key.R: "r", Key.B: "b",
            Key.J: "j", Key.K: "k", Key.C: "c",
            Key.D: "d", Key.G: "g", Key.M: "m", Key.T: "t",
            Key.I: "i", Key.F: "f", Key.X: "x",
            Key.SLASH: "/", Key.QUESTION: "?",
            Key.SPACE_CHAR: " ",
        }
        return mapping.get(key, "?")

    def _do_search(self):
        """/ 搜索 — 命令面板 (U1B)"""
        try:
            query = input("  🔍 ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not query:
            return

        # 尝试命令匹配
        commands = [
            ("install", "安装技能", "zenskill install <来源>"),
            ("uninstall", "卸载技能", "zenskill uninstall <id>"),
            ("search", "搜索技能", "zenskill search <关键词>"),
            ("spec", "查看技能详情", "zenskill spec inspect <id>"),
            ("gtd", "GTD 仪表盘", "zenskill gtd dashboard"),
            ("growth", "成长状态", "zenskill growth status"),
            ("memory", "记忆管理", "zenskill memory list"),
            ("theme", "切换主题", "暂不支持 Plain 主题切换"),
            ("help", "帮助", "显示帮助信息"),
        ]

        matches = [c for c in commands if query.lower() in c[0].lower() or query.lower() in c[1].lower()]
        if matches:
            print(f"\n  🔍 匹配命令:")
            for i, (cmd, desc, usage) in enumerate(matches[:10], 1):
                print(f"  {i}. {cmd:12s} — {desc}")
                print(f"     {self._color(90, usage)}")
        else:
            # 尝试技能搜索
            try:
                from zenskill.skills.search_engine import SkillSearchEngine
                engine = SkillSearchEngine()
                engine.build_index()
                results = engine.search(query, top_k=8)
                if results:
                    print(f"\n  🔍 技能搜索: {query}")
                    for i, r in enumerate(results, 1):
                        star = f"⭐{r.rating:.1f}" if r.rating > 0 else "-"
                        print(f"  {i:2d}. {r.name:25s} [{r.category}] {star}")
                else:
                    print(f"  📭 未找到: {query}")
            except Exception:
                print(f"  📭 未找到: {query}")


# ── 便捷入口 ──

def run_plain_tui():
    """启动 PlainTUI"""
    PlainTUI().run()
