"""诊断页面 -- /doctor 命令。

展示系统健康状态、依赖检查、配置验证。
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...data import TuiDataAdapter


class DoctorPage:
    """诊断页面。"""

    def __init__(self, console: Console, data: TuiDataAdapter):
        self.console = console
        self.data = data

    def render(self, **kwargs) -> None:
        """渲染诊断报告。"""
        checks = []

        # 1. Python 环境
        checks.append(self._check_python())

        # 2. 依赖状态
        checks.append(self._check_deps())

        # 3. 数据目录
        checks.append(self._check_data_dirs())

        # 4. LLM 配置
        checks.append(self._check_llm())

        # 5. 技能状态
        checks.append(self._check_skills())

        # 渲染所有检查结果
        for check in checks:
            if check:
                self.console.print(check)

        # 总结
        total = sum(1 for c in checks if c)
        self.console.print(Panel(
            f"共 {total} 项检查完成",
            title="🩺 诊断总结",
            border_style="green",
        ))

    def _check_python(self):
        """检查 Python 环境。"""
        import sys
        version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        return Panel(
            f"Python {version}  │  {sys.executable}",
            title="🐍 Python 环境",
            border_style="cyan",
        )

    def _check_deps(self):
        """检查依赖状态。"""
        deps = []
        for name in ["rich", "prompt_toolkit", "aiohttp", "pyyaml"]:
            try:
                mod = __import__(name)
                ver = getattr(mod, "__version__", "?")
                deps.append(f"  ✅ {name}: {ver}")
            except ImportError:
                deps.append(f"  ❌ {name}: 未安装")

        return Panel(
            "\n".join(deps),
            title="📦 依赖",
            border_style="yellow",
        )

    def _check_data_dirs(self):
        """检查数据目录。"""
        from pathlib import Path
        dirs = {
            "配置": Path.home() / ".zenskill" / "config.json",
            "状态": Path.home() / ".zenskill" / "states",
            "会话": Path.home() / ".zenskill" / "session",
            "记忆": Path.home() / ".zenskill" / "memory",
        }

        lines = []
        for name, path in dirs.items():
            if path.exists():
                lines.append(f"  ✅ {name}: {path}")
            else:
                lines.append(f"  ⚠️ {name}: {path} (不存在)")

        return Panel(
            "\n".join(lines),
            title="📁 数据目录",
            border_style="blue",
        )

    def _check_llm(self):
        """检查 LLM 配置。"""
        try:
            from zenskill.core.llm_provider import get_llm_provider
            provider = get_llm_provider()
            model = provider.get_model_name() if provider else "未配置"
            available = provider is not None
        except Exception as e:
            model = f"错误: {e}"
            available = False

        status = "[green]✅ 可用[/green]" if available else "[red]❌ 不可用[/red]"
        return Panel(
            f"状态: {status}  │  模型: {model}",
            title="🤖 LLM",
            border_style="green" if available else "red",
        )

    def _check_skills(self):
        """检查技能状态。"""
        skills = self.data.list_skills()
        if not skills:
            return Panel("[yellow]无已安装技能[/yellow]", title="🎯 技能", border_style="yellow")

        # 检查技能目录
        from pathlib import Path
        states_dir = Path.home() / ".zenskill" / "states"
        json_files = list(states_dir.glob("*.json")) if states_dir.exists() else []

        lines = [
            f"  技能数: {len(skills)}",
            f"  状态文件: {len(json_files)}",
        ]

        # 检查异常状态
        for s in skills[:5]:
            name = s.get("skill_id", "?")
            level = s.get("level", "NOVICE")
            usage = s.get("usage_count", 0)
            if usage == 0:
                lines.append(f"  ⚠️ {name}: 未使用")
            else:
                lines.append(f"  ✅ {name}: {level} ({usage}次)")

        return Panel(
            "\n".join(lines),
            title="🎯 技能",
            border_style="green",
        )
