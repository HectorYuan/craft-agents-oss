"""跨协议路由适配 (PROP-20260712-093)

将 MCP/A2A/HTTP 外部能力适配为 SkillHandler，参与统一路由。

用法:
    from zenskill.core.protocol_adapter import ProtocolAdapterRegistry

    registry = ProtocolAdapterRegistry()
    registry.register("mcp", McpAdapter(server_info))
    registry.register("a2a", A2aAdapter(agent_card))

    handler = registry.get_handler("mcp", "tool-name")
    confidence = handler.can_handle("执行任务")
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .protocols import RoutingContext, SkillHandler


@dataclass
class ProtocolCapability:
    """协议能力描述"""
    name: str
    description: str
    protocol: str  # mcp / a2a / http
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "protocol": self.protocol,
            "metadata": self.metadata,
        }


class ProtocolAdapter(ABC):
    """协议适配器基类

    将外部协议能力适配为 SkillHandler Protocol，
    参与 can_handle 路由。
    """

    @property
    @abstractmethod
    def protocol_name(self) -> str:
        """协议名称（mcp/a2a/http）"""
        ...

    @abstractmethod
    def discover_capabilities(self) -> List[ProtocolCapability]:
        """发现可用能力"""
        ...

    @abstractmethod
    def get_handler(self, capability_name: str) -> Optional[SkillHandler]:
        """获取能力处理器"""
        ...

    def can_handle(self, capability_name: str, task: str) -> float:
        """默认能力匹配逻辑"""
        return 0.5  # 子类可覆盖


class SkillHandlerAdapter:
    """将 ProtocolCapability 适配为 SkillHandler"""

    def __init__(self, capability: ProtocolCapability, adapter: ProtocolAdapter):
        self._capability = capability
        self._adapter = adapter

    def can_handle(self, task: str, context: Optional[RoutingContext] = None) -> float:
        """基于能力描述匹配任务"""
        task_lower = task.lower()
        desc_lower = self._capability.description.lower()
        name_lower = self._capability.name.lower()

        # 简单关键词匹配
        score = 0.0
        if name_lower in task_lower:
            score += 0.4
        if any(word in task_lower for word in desc_lower.split()):
            score += 0.3

        # 如果有上下文，考虑协议来源
        if context and context.extra.get("preferred_protocol"):
            if context.extra["preferred_protocol"] == self._capability.protocol:
                score += 0.2

        return min(score, 1.0)


# ═══════════════════════════════════════════════════════════════
# MCP 适配器
# ═══════════════════════════════════════════════════════════════

class McpAdapter(ProtocolAdapter):
    """MCP 协议适配器

    将 MCP server 的 tools 适配为 SkillHandler。
    """

    def __init__(self, server_info: Optional[Dict[str, Any]] = None):
        self._server_info = server_info or {}
        self._capabilities: List[ProtocolCapability] = []
        self._handlers: Dict[str, SkillHandlerAdapter] = {}

    @property
    def protocol_name(self) -> str:
        return "mcp"

    def discover_capabilities(self) -> List[ProtocolCapability]:
        """发现 MCP server 的 tools"""
        # 实际实现需要连接 MCP server 获取 tool schema
        # 这里提供框架
        if self._capabilities:
            return self._capabilities

        # 从 server_info 提取 capabilities
        tools = self._server_info.get("tools", [])
        for tool in tools:
            cap = ProtocolCapability(
                name=tool.get("name", "unknown"),
                description=tool.get("description", ""),
                protocol="mcp",
                metadata={
                    "input_schema": tool.get("inputSchema", {}),
                    "server": self._server_info.get("name", ""),
                },
            )
            self._capabilities.append(cap)

        return self._capabilities

    def get_handler(self, capability_name: str) -> Optional[SkillHandler]:
        """获取 MCP tool 的处理器"""
        if capability_name in self._handlers:
            return self._handlers[capability_name]

        # 查找 capability
        for cap in self._capabilities:
            if cap.name == capability_name:
                handler = SkillHandlerAdapter(cap, self)
                self._handlers[capability_name] = handler
                return handler

        return None

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行 MCP tool（实际调用需要 MCP client）"""
        # 框架实现，实际需要连接 MCP server
        return {
            "tool": tool_name,
            "arguments": arguments,
            "status": "pending",
            "message": "MCP execution requires server connection",
        }


# ═══════════════════════════════════════════════════════════════
# A2A 适配器
# ═══════════════════════════════════════════════════════════════

class A2aAdapter(ProtocolAdapter):
    """A2A 协议适配器

    将 A2A agent 的 capabilities 适配为 SkillHandler。
    """

    def __init__(self, agent_card: Optional[Dict[str, Any]] = None):
        self._agent_card = agent_card or {}
        self._capabilities: List[ProtocolCapability] = []
        self._handlers: Dict[str, SkillHandlerAdapter] = {}

    @property
    def protocol_name(self) -> str:
        return "a2a"

    def discover_capabilities(self) -> List[ProtocolCapability]:
        """发现 A2A agent 的 capabilities"""
        if self._capabilities:
            return self._capabilities

        # 从 agent_card 提取 capabilities
        caps = self._agent_card.get("capabilities", [])
        for cap_data in caps:
            cap = ProtocolCapability(
                name=cap_data.get("name", "unknown"),
                description=cap_data.get("description", ""),
                protocol="a2a",
                metadata={
                    "agent": self._agent_card.get("name", ""),
                    "url": self._agent_card.get("url", ""),
                },
            )
            self._capabilities.append(cap)

        return self._capabilities

    def get_handler(self, capability_name: str) -> Optional[SkillHandler]:
        """获取 A2A capability 的处理器"""
        if capability_name in self._handlers:
            return self._handlers[capability_name]

        for cap in self._capabilities:
            if cap.name == capability_name:
                handler = SkillHandlerAdapter(cap, self)
                self._handlers[capability_name] = handler
                return handler

        return None

    def send_task(self, agent_url: str, task: Dict[str, Any]) -> Any:
        """发送任务到 A2A agent（实际调用需要 HTTP client）"""
        return {
            "agent": agent_url,
            "task": task,
            "status": "pending",
            "message": "A2A execution requires HTTP connection",
        }


# ═══════════════════════════════════════════════════════════════
# HTTP 适配器
# ═══════════════════════════════════════════════════════════════

class HttpAdapter(ProtocolAdapter):
    """HTTP API 适配器

    将 REST API endpoints 适配为 SkillHandler。
    """

    def __init__(self, api_info: Optional[Dict[str, Any]] = None):
        self._api_info = api_info or {}
        self._capabilities: List[ProtocolCapability] = []
        self._handlers: Dict[str, SkillHandlerAdapter] = {}

    @property
    def protocol_name(self) -> str:
        return "http"

    def discover_capabilities(self) -> List[ProtocolCapability]:
        """发现 HTTP API endpoints"""
        if self._capabilities:
            return self._capabilities

        endpoints = self._api_info.get("endpoints", [])
        for ep in endpoints:
            cap = ProtocolCapability(
                name=ep.get("path", "unknown"),
                description=ep.get("description", ""),
                protocol="http",
                metadata={
                    "method": ep.get("method", "GET"),
                    "url": self._api_info.get("base_url", ""),
                },
            )
            self._capabilities.append(cap)

        return self._capabilities

    def get_handler(self, capability_name: str) -> Optional[SkillHandler]:
        """获取 HTTP endpoint 的处理器"""
        if capability_name in self._handlers:
            return self._handlers[capability_name]

        for cap in self._capabilities:
            if cap.name == capability_name:
                handler = SkillHandlerAdapter(cap, self)
                self._handlers[capability_name] = handler
                return handler

        return None


# ═══════════════════════════════════════════════════════════════
# 适配器注册表
# ═══════════════════════════════════════════════════════════════

class ProtocolAdapterRegistry:
    """协议适配器注册表

    管理所有协议适配器，提供统一的能力发现和路由。
    """

    def __init__(self) -> None:
        self._adapters: Dict[str, ProtocolAdapter] = {}
        self._all_capabilities: List[ProtocolCapability] = []

    def register(self, protocol: str, adapter: ProtocolAdapter) -> None:
        """注册协议适配器"""
        self._adapters[protocol] = adapter
        # 发现能力
        caps = adapter.discover_capabilities()
        self._all_capabilities.extend(caps)

    def unregister(self, protocol: str) -> bool:
        """注销协议适配器"""
        if protocol in self._adapters:
            adapter = self._adapters.pop(protocol)
            # 移除该协议的能力
            self._all_capabilities = [
                c for c in self._all_capabilities if c.protocol != protocol
            ]
            return True
        return False

    def get_handler(
        self, protocol: str, capability_name: str
    ) -> Optional[SkillHandler]:
        """获取指定协议的能力处理器"""
        adapter = self._adapters.get(protocol)
        if adapter:
            return adapter.get_handler(capability_name)
        return None

    def find_handlers(self, task: str) -> List[tuple[str, SkillHandler, float]]:
        """查找所有匹配任务的处理器

        Returns:
            [(protocol:skill_id, handler, confidence), ...]
        """
        results = []
        for protocol, adapter in self._adapters.items():
            caps = adapter.discover_capabilities()
            for cap in caps:
                handler = adapter.get_handler(cap.name)
                if handler:
                    confidence = handler.can_handle(task)
                    if confidence > 0.1:
                        results.append((f"{protocol}:{cap.name}", handler, confidence))

        # 按置信度排序
        results.sort(key=lambda x: x[2], reverse=True)
        return results

    def list_capabilities(self) -> List[Dict[str, Any]]:
        """列出所有能力"""
        return [c.to_dict() for c in self._all_capabilities]

    def list_adapters(self) -> List[Dict[str, str]]:
        """列出所有适配器"""
        return [
            {"protocol": p, "type": type(a).__name__}
            for p, a in self._adapters.items()
        ]


# 全局单例
protocol_adapter_registry = ProtocolAdapterRegistry()
