"""自定义工具加载器（Phase 2.2）。

扫描 ~/.zenskill/tools/ 目录下的 .py 文件，动态加载为 AgentTool。
每个 .py 文件需定义：name, description, parameters, async run(tool_call_id, params, on_update)

用法：
    tools = create_default_tools(".") + load_custom_tools()
    # 或指定目录
    tools = create_default_tools(".") + load_custom_tools("/path/to/tools")
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import List, Optional

from .types import AgentTool, AgentToolResult, TextContent

DEFAULT_TOOLS_DIR = Path.home() / ".zenskill" / "tools"


def load_custom_tools(tools_dir: Optional[str] = None) -> List[AgentTool]:
    """扫描目录，加载所有 .py 文件为 AgentTool。"""
    tools: List[AgentTool] = []
    root = Path(tools_dir) if tools_dir else DEFAULT_TOOLS_DIR
    if not root.is_dir():
        return tools

    for py_file in sorted(root.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            tool = _load_tool_from_file(py_file)
            if tool is not None:
                tools.append(tool)
        except Exception as e:
            print(f"[custom-tools] 跳过 {py_file.name}: {e}", file=sys.stderr)
    return tools


def _load_tool_from_file(path: Path) -> Optional[AgentTool]:
    """从单个 .py 文件加载一个 AgentTool。"""
    spec = importlib.util.spec_from_file_location(f"custom_tool_{path.stem}", str(path))
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        raise RuntimeError(f"加载失败: {e}")

    # 提取必要属性
    name = getattr(mod, "name", None) or path.stem
    description = getattr(mod, "description", "") or f"Custom tool from {path.name}"
    parameters = getattr(mod, "parameters", None) or {"type": "object", "properties": {}}
    run_fn = getattr(mod, "run", None)
    if run_fn is None:
        raise RuntimeError("缺少 run 函数")

    # 构建 AgentTool
    class _CustomTool(AgentTool):
        pass

    tool = _CustomTool()
    tool.name = name
    tool.description = description
    tool.parameters = parameters
    tool.run = run_fn  # type: ignore[method-assign]
    return tool
