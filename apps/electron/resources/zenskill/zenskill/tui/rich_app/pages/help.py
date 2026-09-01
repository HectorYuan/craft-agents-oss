"""帮助页面 -- /help 命令。"""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from ...data import TuiDataAdapter


HELP_TEXT = """
## 📝 对话
直接输入文字      与 AI 对话
@file             引用文件内容

## ⌨️ 数字键快捷导航
`1`  仪表盘        `2`  成长中心
`3`  技能列表      `4`  GTD 任务
`5`  系统设置      `6`  帮助

## 📋 命令

### 页面导航
`/dashboard`      仪表盘    `/d`            快捷键
`/growth`         成长中心   `/g`            快捷键
`/skills`         技能列表   `/s`            快捷键
`/mirror`         用户镜像   `/m`            快捷键
`/knowledge`      知识库     `/k`            快捷键

### 成长
`/growth`                 成长报告
`/growth compare`         成长对比
`/growth replay`          成长回放
`/growth errors`          错误聚类
`/growth feedback`        即时反馈

### 诊断
`/doctor`                 系统诊断
`/doctor state`           状态扫描
`/doctor repair`          自动修复

### LLM
`/llm`                    Provider 列表
`/llm show`               当前模型
`/llm set <model>`        切换模型
`/llm test`               测试连接

### 系统
`/version`                版本信息
`/clear`                  清屏
`/help`                   帮助
`/quit`                   退出

## ⌨️ 快捷键
Ctrl+C            中断当前操作
Ctrl+L            清屏
↑↓                浏览历史 (prompt_toolkit)
Tab               命令自动补全
"""


class HelpPage:
    """帮助页面。"""

    def __init__(self, console: Console, data: TuiDataAdapter):
        self.console = console
        self.data = data

    def render(self, **kwargs) -> None:
        """渲染帮助页面。"""
        self.console.print(Panel(
            Markdown(HELP_TEXT),
            title="❓ 帮助",
            border_style="blue",
        ))
