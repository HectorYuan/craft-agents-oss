"""
ZenSkill - Claude Code 插件集成层

在 Claude Code 插件环境中，ZenSkill 作为工具运行，完全复用宿主 Claude 的 LLM 能力。

核心机制：
1. 触发禅思反思 -> 捕获 HostedLLMRequired 异常
2. 输出结构化的 LLM 任务描述 -> Claude Code 让 Claude 看到这个 prompt
3. Claude 完成思考后 -> 调用 zenskill reflect store 写回结果
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .core.llm_provider import HostedLLMRequired


@dataclass
class HostedTaskResult:
    """宿主 LLM 任务执行结果"""
    requires_host_llm: bool
    task: Optional[Dict[str, Any]]
    output: Any
    error: Optional[str] = None


class ClaudeCodePlugin:
    """
    Claude Code 插件适配器

    负责：
    1. 捕获 HostedLLMRequired 异常，转化为宿主友好的格式
    2. 输出标准的 MCP (Model Context Protocol) 工具响应格式
    3. 管理插件状态和配置
    """

    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id
        self._task_counter = 0

    def format_mcp_response(
        self,
        content: str,
        is_markdown: bool = True,
        requires_llm_task: bool = False,
        llm_task: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        格式化 MCP (Model Context Protocol) 标准响应

        Claude Code 通过 MCP 协议与插件通信，响应需要符合特定格式。
        """
        response = {
            "content": [
                {
                    "type": "text",
                    "text": content,
                    "mime_type": "text/markdown" if is_markdown else "text/plain",
                }
            ],
            "metadata": {
                "plugin": "zenskill",
                "skill_id": self.skill_id,
            }
        }

        # 如果有 LLM 任务需要宿主执行，添加特殊标记
        if requires_llm_task and llm_task:
            response["metadata"]["requires_host_llm"] = True
            response["metadata"]["llm_task"] = llm_task

        return response

    def format_hosted_task_prompt(self, task: Dict[str, Any]) -> str:
        """
        将 LLM 任务格式化为 Claude 可以直接理解的 prompt

        这是核心机制：让宿主 Claude "看到" 我们需要它完成的思考任务。
        """
        prompt = task.get("prompt", "")
        task_type = task.get("task_type", "general")
        callback = task.get("storage_callback", {})

        # 格式化输出，让 Claude 清晰理解任务
        return f"""
## 🧘 ZenSkill 禅思反思请求

**任务类型**：{task_type}

---

### 请完成以下思考：

{prompt}

---

### ✅ 思考完成后，请将结果写回存储

请将你的反思内容以以下 JSON 格式通过 CLI 写回：

```bash
echo '{json.dumps({"reflection_content": "你的完整反思内容..."}, ensure_ascii=False)}' | python -m zenskill reflect store
```

**写回命令**：
```
{callback.get('command', 'python -m zenskill reflect store')}
```

> 重要：请保持完整的 Markdown 结构，包含所有章节。
"""

    def wrap_with_hosted_task_detection(self, func):
        """
        装饰器：包装 CLI 命令，自动检测和处理 HostedLLMRequired 异常

        使用方式：
            @plugin.wrap_with_hosted_task_detection
            def cmd_reflect_trigger(args):
                ...
        """
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                return HostedTaskResult(
                    requires_host_llm=False,
                    task=None,
                    output=result,
                )
            except HostedLLMRequired as e:
                # 捕获到宿主 LLM 任务 - 这是正常流程，不是错误
                return HostedTaskResult(
                    requires_host_llm=True,
                    task=e.task,
                    output=self.format_hosted_task_prompt(e.task),
                )
            except Exception as e:
                # 真正的错误
                return HostedTaskResult(
                    requires_host_llm=False,
                    task=None,
                    output=None,
                    error=str(e),
                )
        return wrapper


# 全局插件实例
_plugin_instance: Optional[ClaudeCodePlugin] = None


def get_plugin() -> ClaudeCodePlugin:
    """获取全局插件实例"""
    global _plugin_instance
    if _plugin_instance is None:
        _plugin_instance = ClaudeCodePlugin()
    return _plugin_instance


def run_cli_with_host_detection(cli_func, *args, **kwargs):
    """
    运行 CLI 命令，自动检测宿主环境并处理 LLM 任务

    这是插件入口的核心函数：
    - 在 Claude Code 环境下，捕获 HostedLLMRequired 并输出格式化 prompt
    - 在普通 CLI 环境下，正常执行

    使用方式：
        if __name__ == "__main__":
            run_cli_with_host_detection(main, sys.argv[1:])
    """
    plugin = get_plugin()

    # 检测是否在 Claude Code 插件环境运行
    is_claude_env = (
        Path("/.claude-plugin").exists()
        or "--claude-plugin" in sys.argv
        or "CLAUDE_ENV" in sys.modules
    )

    try:
        result = plugin.wrap_with_hosted_task_detection(cli_func)(*args, **kwargs)

        if result.error:
            print(f"❌ 错误: {result.error}")
            return 1

        if result.requires_host_llm:
            # 在宿主环境下，直接输出思考任务
            # Claude 会看到这个 prompt 并完成思考
            print(result.output)
            return 0

        # 普通输出
        if result.output:
            print(result.output)
        return 0

    except Exception as e:
        print(f"❌ 执行失败: {e}")
        return 1
