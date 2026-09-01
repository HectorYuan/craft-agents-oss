"""
Skill Exposure - 技能暴露为 MCP 工具


将 ZenSkill 技能暴露为 MCP 工具，支持 Claude Code tool_use。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .mcp_client import MCPTool, ToolResult

__stable_api__ = "1.0"  # SkillExposure/SkillTool 公开方法（register/get_tools/call_tool/expose_skill） 为外部消费方稳定面（docs/agentswarm_integration_plan.md I2）


@dataclass
class SkillTool:
    """技能工具定义"""
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]
    skill_id: str = ""
    tags: list[str] = field(default_factory=list)

    def to_mcp_tool(self) -> MCPTool:
        """转换为 MCP 工具"""
        return MCPTool(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
        )


@dataclass
class ExposureResult:
    """暴露结果"""
    success: bool
    tool_count: int
    tools: list[SkillTool]
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "tool_count": self.tool_count,
            "tools": [
                {"name": t.name, "description": t.description, "skill_id": t.skill_id}
                for t in self.tools
            ],
            "error": self.error,
        }


class SkillExposure:
    """
    技能暴露为 MCP 工具

    将 ZenSkill 技能暴露为 MCP 工具，支持 Claude Code tool_use。

    使用方式：
        exposure = SkillExposure()
        exposure.register("read_file", "读取文件", handler=read_file_func)
        tools = exposure.get_tools()
    """

    def __init__(self):
        self._tools: dict[str, SkillTool] = {}

    def register(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
        input_schema: dict[str, Any] | None = None,
        skill_id: str = "",
        tags: list[str] | None = None,
    ) -> None:
        """
        注册技能工具

        Args:
            name: 工具名称
            description: 工具描述
            handler: 处理函数
            input_schema: 输入 schema
            skill_id: 技能 ID
            tags: 标签
        """
        self._tools[name] = SkillTool(
            name=name,
            description=description,
            input_schema=input_schema or {"type": "object", "properties": {}},
            handler=handler,
            skill_id=skill_id,
            tags=tags or [],
        )

    def unregister(self, name: str) -> bool:
        """
        取消注册工具

        Args:
            name: 工具名称

        Returns:
            是否成功
        """
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get_tools(self) -> list[SkillTool]:
        """获取所有注册的工具"""
        return list(self._tools.values())

    def get_mcp_tools(self) -> list[MCPTool]:
        """获取 MCP 格式的工具列表"""
        return [tool.to_mcp_tool() for tool in self._tools.values()]

    def get_tool(self, name: str) -> SkillTool | None:
        """获取指定工具"""
        return self._tools.get(name)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """
        调用工具

        Args:
            name: 工具名称
            arguments: 参数

        Returns:
            工具结果
        """
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool not found: {name}",
                is_error=True,
            )

        try:
            result = await tool.handler(**arguments)
            return ToolResult(success=True, content=result)
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                is_error=True,
            )

    def expose_skill(
        self,
        skill_id: str,
        skill_name: str,
        capabilities: list[dict[str, Any]],
    ) -> ExposureResult:
        """
        暴露整个技能

        Args:
            skill_id: 技能 ID
            skill_name: 技能名称
            capabilities: 能力列表

        Returns:
            暴露结果
        """
        tools = []

        for cap in capabilities:
            name = f"{skill_id}_{cap.get('name', 'unknown')}"
            description = cap.get("description", "")
            handler = cap.get("handler")
            input_schema = cap.get("input_schema", {})

            if handler:
                self.register(
                    name=name,
                    description=description,
                    handler=handler,
                    input_schema=input_schema,
                    skill_id=skill_id,
                    tags=[skill_name],
                )
                tools.append(self._tools[name])

        return ExposureResult(
            success=True,
            tool_count=len(tools),
            tools=tools,
        )

    def clear(self) -> None:
        """清空所有注册的工具"""
        self._tools.clear()

    @property
    def tool_count(self) -> int:
        """工具数量"""
        return len(self._tools)
