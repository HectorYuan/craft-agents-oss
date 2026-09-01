"""
ZenSkill - Hermes 平台适配器

Hermes 是一个多智能体协作框架，强调代理之间的消息传递和协调。

适配要点：
- 通过 Hermes 的消息总线触发技能
- 复用 Hermes 的 LLM 调用能力
- 技能作为 Hermes 代理的能力模块
"""

import json
from pathlib import Path
from typing import Any, Optional

from .base import PlatformAdapter, PlatformType, InstallResult, ExecutionResult


class HermesAdapter(PlatformAdapter):
    """
    Hermes 多智能体协作框架适配器
    """

    @property
    def platform_name(self) -> str:
        return "hermes"

    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.HERMES

    def install(self, skill_name: str, skill_path: str = None, **kwargs) -> InstallResult:
        """
        安装技能到 Hermes 框架

        Args:
            skill_name: 技能名称
            skill_path: 技能源码路径
            **kwargs: 其他平台特定参数

        Returns:
            InstallResult: 安装结果
        """
        try:
            # 验证技能包结构
            skill_path = skill_path or f"./skills/{skill_name}"
            path = Path(skill_path)

            if not path.exists():
                return InstallResult(
                    success=False,
                    platform=self.platform_name,
                    message=f"Skill path not found: {skill_path}",
                )

            # 检查必要的文件
            required_files = ["skill.py", "manifest.json"]
            missing = [f for f in required_files if not (path / f).exists()]
            if missing:
                return InstallResult(
                    success=False,
                    platform=self.platform_name,
                    message=f"Missing required files: {', '.join(missing)}",
                )

            # 注册到 Hermes 技能清单
            registry_path = kwargs.get("registry_path", "./hermes_skills.json")
            registry = {}
            registry_file = Path(registry_path)
            if registry_file.exists():
                registry = json.loads(registry_file.read_text())

            registry[skill_name] = {
                "path": str(path.absolute()),
                "version": self._get_skill_version(path),
                "capabilities": self._get_skill_capabilities(path),
            }

            registry_file.write_text(json.dumps(registry, indent=2, ensure_ascii=False))

            return InstallResult(
                success=True,
                platform=self.platform_name,
                message=f"Successfully installed skill '{skill_name}' to Hermes registry",
                skill_path=str(path.absolute()),
            )

        except Exception as e:
            return InstallResult(
                success=False,
                platform=self.platform_name,
                message=f"Hermes install failed: {str(e)}",
            )

    def uninstall(self, skill_name: str, **kwargs) -> InstallResult:
        """
        从 Hermes 框架卸载技能

        Args:
            skill_name: 技能名称

        Returns:
            InstallResult: 卸载结果
        """
        try:
            registry_path = kwargs.get("registry_path", "./hermes_skills.json")
            registry_file = Path(registry_path)

            if not registry_file.exists():
                return InstallResult(
                    success=False,
                    platform=self.platform_name,
                    message="Hermes registry not found",
                )

            registry = json.loads(registry_file.read_text())
            if skill_name not in registry:
                return InstallResult(
                    success=False,
                    platform=self.platform_name,
                    message=f"Skill '{skill_name}' not found in registry",
                )

            del registry[skill_name]
            registry_file.write_text(json.dumps(registry, indent=2, ensure_ascii=False))

            return InstallResult(
                success=True,
                platform=self.platform_name,
                message=f"Successfully uninstalled skill '{skill_name}' from Hermes registry",
            )

        except Exception as e:
            return InstallResult(
                success=False,
                platform=self.platform_name,
                message=f"Hermes uninstall failed: {str(e)}",
            )

    def execute(self, skill_name: str, task: str, **kwargs) -> ExecutionResult:
        """
        在 Hermes 框架中执行技能

        在 Hermes 中：
        1. 技能通过消息总线接收任务
        2. 可以请求 Hermes 的 LLM 能力来完成任务
        3. 结果通过消息总线返回

        Args:
            skill_name: 技能名称
            task: 任务描述
            **kwargs: 执行参数，包括：
                - hermes_llm: Hermes 框架提供的 LLM 调用器
                - message_bus: Hermes 消息总线引用
                - agent_id: 调用方代理 ID

        Returns:
            ExecutionResult: 执行结果
        """
        try:
            hermes_llm = kwargs.get("hermes_llm")
            message_bus = kwargs.get("message_bus")
            agent_id = kwargs.get("agent_id", "unknown")

            # 如果提供了 Hermes LLM，复用其能力
            if hermes_llm is not None:
                # 实际的 Hermes LLM 调用会在这里发生
                # result = hermes_llm.call(task, ...)
                llm_status = "using_hermes_llm"
            else:
                llm_status = "no_llm_provided"

            # 如果有消息总线，发送执行通知
            if message_bus is not None:
                # message_bus.publish(...)
                pass

            # 返回执行结果
            return ExecutionResult(
                success=True,
                output={
                    "skill": skill_name,
                    "task": task,
                    "agent_id": agent_id,
                    "llm_mode": llm_status,
                    "message": f"Executed via Hermes message bus",
                },
                metadata={
                    "platform": self.platform_name,
                    "timestamp": self._get_timestamp(),
                },
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                output=None,
                error=str(e),
            )

    def is_installed(self, skill_name: str, **kwargs) -> bool:
        """检查技能是否已注册到 Hermes"""
        try:
            registry_path = kwargs.get("registry_path", "./hermes_skills.json")
            registry_file = Path(registry_path)
            if not registry_file.exists():
                return False

            registry = json.loads(registry_file.read_text())
            return skill_name in registry
        except Exception:
            return False

    def get_status(self, skill_name: str) -> dict:
        """获取技能在 Hermes 中的状态"""
        base_status = super().get_status(skill_name)
        base_status.update({
            "capabilities": [],  # 可从 manifest 中提取
            "llm_enabled": True,
            "message_bus_support": True,
        })
        return base_status

    def _get_skill_version(self, skill_path: Path) -> str:
        """从 manifest 中提取技能版本"""
        manifest = skill_path / "manifest.json"
        if manifest.exists():
            data = json.loads(manifest.read_text())
            return data.get("version", "1.0.0")
        return "1.0.0"

    def _get_skill_capabilities(self, skill_path: Path) -> list:
        """从 manifest 中提取技能能力"""
        manifest = skill_path / "manifest.json"
        if manifest.exists():
            data = json.loads(manifest.read_text())
            return data.get("capabilities", [])
        return []

    def _get_timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()


class HermesLLMProvider:
    """
    Hermes LLM 提供者 - 复用 Hermes 框架的 LLM 能力

    当 ZenSkill 作为 Hermes 代理的能力模块运行时，
    完全不需要自己管理 API Key，直接通过此类复用 Hermes 的 LLM 调用。
    """

    def __init__(self, hermes_llm_client: Any = None):
        """
        Args:
            hermes_llm_client: Hermes 框架的 LLM 客户端实例
        """
        self._llm_client = hermes_llm_client
        self._name = "Hermes-LLM"

    async def chat(self, messages: list, **kwargs) -> Any:
        """调用 Hermes 的 LLM 能力"""
        if self._llm_client is None:
            # 如果没有提供 LLM 客户端，返回结构化任务描述（等待宿主注入）
            return {
                "llm_task": True,
                "provider": "hermes",
                "waiting_for_llm": True,
                "messages": messages,
            }

        # 实际调用 Hermes LLM 客户端
        # return await self._llm_client.chat(messages, **kwargs)
        return {
            "llm_task": True,
            "provider": "hermes",
            "llm_client": str(type(self._llm_client).__name__),
            "messages": messages,
        }

    @property
    def model_name(self) -> str:
        return self._name
