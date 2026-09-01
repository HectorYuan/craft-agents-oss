"""
ZenSkill - Claude Code 平台适配器

支持 Claude Code (claude.ai) 的插件安装与管理
"""

import subprocess
import json
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

from .base import PlatformAdapter, PlatformType, InstallResult, ExecutionResult


class ClaudeAdapter(PlatformAdapter):
    """
    Claude Code 平台适配器

    Claude Code 使用 Plugin 系统
    安装命令: claude plugins install {name or path}
    """

    @property
    def platform_name(self) -> str:
        return "claude"

    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.CLAUDE

    def install(self, skill_name: str, tool_path: str = None, from_path: bool = False, **kwargs) -> InstallResult:
        """
        安装 Claude Code 插件

        Args:
            skill_name: 插件名称或本地路径
            tool_path: 工具包路径（备用）
            from_path: 是否从本地路径安装

        Returns:
            InstallResult: 安装结果
        """
        try:
            # 验证本地路径安装时的插件结构
            if from_path:
                validate_result = self.validate_plugin_structure(skill_name)
                if not validate_result["valid"]:
                    return InstallResult(
                        success=False,
                        platform=self.platform_name,
                        message=f"Plugin structure validation failed: {validate_result['error']}",
                    )

            # Claude Code CLI 安装命令
            result = subprocess.run(
                ["claude", "plugins", "install", skill_name],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                return InstallResult(
                    success=True,
                    platform=self.platform_name,
                    message=f"Successfully installed plugin '{skill_name}'",
                    skill_path=skill_name if from_path else None,
                )
            else:
                return InstallResult(
                    success=False,
                    platform=self.platform_name,
                    message=f"claude plugins install failed: {result.stderr}",
                )

        except FileNotFoundError:
            return InstallResult(
                success=False,
                platform=self.platform_name,
                message="Claude CLI not found. Install from: https://claude.ai/code",
            )
        except Exception as e:
            return InstallResult(
                success=False,
                platform=self.platform_name,
                message=f"Installation failed: {str(e)}",
            )

    def install_from_path(self, plugin_path: str) -> InstallResult:
        """
        从本地路径安装插件

        Args:
            plugin_path: 插件目录路径

        Returns:
            InstallResult: 安装结果
        """
        return self.install(plugin_path, from_path=True)

    def uninstall(self, skill_name: str) -> InstallResult:
        """卸载 Claude Code 插件"""
        try:
            result = subprocess.run(
                ["claude", "plugins", "remove", skill_name],
                capture_output=True,
                text=True,
                timeout=30,
            )

            return InstallResult(
                success=result.returncode == 0,
                platform=self.platform_name,
                message=result.stdout if result.returncode == 0 else result.stderr,
            )

        except Exception as e:
            return InstallResult(
                success=False,
                platform=self.platform_name,
                message=f"Uninstall failed: {str(e)}",
            )

    def execute(self, skill_name: str, task: str, **kwargs) -> ExecutionResult:
        """执行 Claude Code 插件技能"""
        try:
            # Claude Code 插件通过对话调用
            return ExecutionResult(
                success=True,
                output={
                    "message": f"Use plugin '{skill_name}' in Claude Code conversation",
                    "task": task,
                    "tip": "Claude Code plugins are called via @plugin-name in conversation",
                },
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output=None,
                error=str(e),
            )

    def is_installed(self, skill_name: str) -> bool:
        """检查插件是否已安装"""
        try:
            result = subprocess.run(
                ["claude", "plugins", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                plugins = json.loads(result.stdout)
                return any(p.get("name") == skill_name for p in plugins)
            return False
        except Exception:
            return False

    def get_status(self, skill_name: str) -> Dict[str, Any]:
        """
        获取插件详细状态信息

        Args:
            skill_name: 插件名称

        Returns:
            包含名称、平台、安装状态、版本、描述等信息的字典
        """
        try:
            result = subprocess.run(
                ["claude", "plugins", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                plugins = json.loads(result.stdout)
                for plugin in plugins:
                    if plugin.get("name") == skill_name:
                        return {
                            "name": skill_name,
                            "platform": self.platform_name,
                            "installed": True,
                            "version": plugin.get("version", "unknown"),
                            "description": plugin.get("description", ""),
                            "author": plugin.get("author", {}).get("name", ""),
                        }
            return {"name": skill_name, "platform": self.platform_name, "installed": False}
        except Exception as e:
            return {
                "name": skill_name,
                "platform": self.platform_name,
                "installed": None,
                "error": str(e),
            }

    def validate_plugin_structure(self, plugin_path: str) -> Dict[str, Any]:
        """
        验证插件目录结构是否符合 Claude Code 规范

        Args:
            plugin_path: 插件目录路径

        Returns:
            包含验证结果的字典: {valid: bool, error: str|None}
        """
        try:
            plugin_dir = Path(plugin_path)

            if not plugin_dir.exists():
                return {"valid": False, "error": f"Plugin path not found: {plugin_path}"}

            if not plugin_dir.is_dir():
                return {"valid": False, "error": f"Plugin path is not a directory: {plugin_path}"}

            # 检查必需的 .claude-plugin 目录
            claude_plugin_dir = plugin_dir / ".claude-plugin"
            if not claude_plugin_dir.exists() or not claude_plugin_dir.is_dir():
                return {"valid": False, "error": "Missing required .claude-plugin directory"}

            # 检查必需的 plugin.json 文件
            plugin_json = claude_plugin_dir / "plugin.json"
            if not plugin_json.exists():
                return {"valid": False, "error": "Missing required .claude-plugin/plugin.json file"}

            # 验证 plugin.json 格式
            try:
                manifest = json.loads(plugin_json.read_text())
            except json.JSONDecodeError as e:
                return {"valid": False, "error": f"Invalid plugin.json: {str(e)}"}

            # 检查必需字段
            required_fields = ["name", "version", "description"]
            for field in required_fields:
                if field not in manifest:
                    return {"valid": False, "error": f"Missing required field in plugin.json: {field}"}

            # 检查 skills 目录（推荐但非必需）
            skills_dir = plugin_dir / "skills"
            has_skills = skills_dir.exists() and skills_dir.is_dir()

            return {
                "valid": True,
                "error": None,
                "has_skills": has_skills,
                "manifest": manifest,
            }

        except Exception as e:
            return {"valid": False, "error": f"Validation error: {str(e)}"}

    def parse_manifest(self, manifest_path: str) -> Dict[str, Any]:
        """
        解析 plugin.json（原 manifest.json）

        Args:
            manifest_path: 插件目录路径

        Returns:
            插件元数据字典
        """
        plugin_dir = Path(manifest_path)
        manifest_file = plugin_dir / ".claude-plugin" / "plugin.json"
        if manifest_file.exists():
            try:
                return json.loads(manifest_file.read_text())
            except json.JSONDecodeError:
                pass
        return {}

    def list_plugins(self) -> list:
        """
        列出所有已安装的插件

        Returns:
            插件列表
        """
        try:
            result = subprocess.run(
                ["claude", "plugins", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
            return []
        except Exception:
            return []
