"""部署型平台适配器 (P1-1)

把 core/skill_executor.py 的四个 PLATFORM_GENERATORS 收敛为
DeployAdapter 基类 + 四个子类，统一注册进 SkillInstaller.ADAPTERS，
消除「platforms 出站适配器 / skill_executor deploy / 入站安装」三套割裂。

部署目标目录解析优先级（应对各平台 CLI 目录随版本变化）:
1. 实例化参数 deploy_root / skills_dir（测试与程序化注入）
2. ~/.zenskill/platforms.yaml 的 deploy.<platform>.target_dir
3. 各平台 default_deploy_root()
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .base import ExecutionResult, InstallResult, PlatformAdapter, PlatformType
from ..skills.skillmd_converter import generate_platform_manifest

DEPLOY_CONFIG_PATH = Path.home() / ".zenskill" / "platforms.yaml"


def load_deploy_config() -> Dict[str, Any]:
    """读取 ~/.zenskill/platforms.yaml 部署配置，缺失/非法返回空 dict"""
    try:
        raw = yaml.safe_load(DEPLOY_CONFIG_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def get_skills_dir() -> Path:
    """技能源目录 ~/.zenskill/skills/"""
    return Path.home() / ".zenskill" / "skills"


def discover_skill(skill_id: str, skills_dir: Optional[Path] = None) -> Optional[Path]:
    """发现技能目录: ~/.zenskill/skills/{id}/ → ./zenskill/skills/{id}/ → {id}.py"""
    base = Path(skills_dir) if skills_dir else get_skills_dir()

    skill_path = base / skill_id
    if skill_path.exists() and skill_path.is_dir():
        return skill_path

    local_path = Path("zenskill/skills") / skill_id
    if local_path.exists() and local_path.is_dir():
        return local_path

    single_file = base / f"{skill_id}.py"
    if single_file.exists():
        return single_file

    return None


def load_skill_manifest(skill_path: Path) -> Dict[str, Any]:
    """加载技能清单: manifest.json → __init__.py 推断 → SKILL.md frontmatter"""
    manifest_path = skill_path / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    init_path = skill_path / "__init__.py"
    if init_path.exists():
        return {
            "id": skill_path.name,
            "name": skill_path.name.replace("_", " ").title(),
            "description": f"Skill from {skill_path}",
            "version": "1.0.0",
            "entry_point": "__init__.py",
        }

    skill_md = skill_path / "SKILL.md"
    if skill_md.exists():
        from ..skills.frontmatter import parse_skill_md

        meta, _body = parse_skill_md(skill_md)
        if meta.name:
            return {
                "id": skill_path.name,
                "name": meta.name,
                "description": meta.description,
                "version": meta.version or "0.1.0",
                "tags": meta.tags,
            }

    return {}


class DeployAdapter(PlatformAdapter):
    """部署型适配器基类: 平台 manifest 生成 + 技能源文件复制

    子类只需声明 platform_key / platform_type / generate_manifest，
    可选覆盖 default_deploy_root 对接平台真实目录。
    """

    platform_key: str = ""
    trigger_hint: str = ""

    def __init__(
        self,
        skills_dir: Optional[Path] = None,
        deploy_root: Optional[Path] = None,
    ):
        self._skills_dir = Path(skills_dir) if skills_dir else get_skills_dir()
        self._deploy_root = Path(deploy_root) if deploy_root else None

    @property
    def platform_name(self) -> str:
        return self.platform_key

    def default_deploy_root(self) -> Path:
        return self._skills_dir / ".deployed" / self.platform_key

    def deploy_root(self) -> Path:
        if self._deploy_root is not None:
            return self._deploy_root
        cfg = load_deploy_config()
        override = (cfg.get("deploy", {}).get(self.platform_key) or {}).get("target_dir")
        if override:
            return Path(override).expanduser()
        return self.default_deploy_root()

    def target_dir(self, skill_id: str) -> Path:
        # skill_id 可能来自注册表/CLI，构造上阻断路径分量注入
        from ..core.paths import safe_child_path

        return safe_child_path(self.deploy_root(), skill_id)

    def generate_manifest(self, skill_id: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
        """按 skillmd_converter.PLATFORM_MANIFEST_MAPS 投影字段（唯一字段映射源）"""
        return generate_platform_manifest(self.platform_key, skill_id, manifest)

    def get_installed_manifest(self, skill_id: str) -> Optional[Dict[str, Any]]:
        manifest_file = self.target_dir(skill_id) / "manifest.json"
        if manifest_file.exists():
            with open(manifest_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    # ── PlatformAdapter 接口 ──

    def install(self, skill_name: str, skill_path: str = None, **kwargs) -> InstallResult:
        source = Path(skill_path) if skill_path else discover_skill(skill_name, self._skills_dir)
        if source is None or not source.exists():
            return InstallResult(
                success=False,
                platform=self.platform_name,
                message=f"Skill not found: {skill_name}",
            )

        manifest = load_skill_manifest(source)
        if not manifest:
            return InstallResult(
                success=False,
                platform=self.platform_name,
                message=f"Failed to load skill manifest: {skill_name}",
            )

        platform_manifest = self.generate_manifest(skill_name, manifest)
        target = self.target_dir(skill_name)
        target.mkdir(parents=True, exist_ok=True)

        with open(target / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(platform_manifest, f, indent=2, ensure_ascii=False)

        if source.is_dir():
            dest = target / "skill"
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(
                source,
                dest,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".deployed"),
            )
        else:
            shutil.copy2(source, target / source.name)

        return InstallResult(
            success=True,
            platform=self.platform_name,
            message=f"Skill '{skill_name}' deployed to {self.platform_key}",
            skill_path=str(target),
        )

    def uninstall(self, skill_name: str) -> InstallResult:
        target = self.target_dir(skill_name)
        if not target.exists():
            return InstallResult(
                success=False,
                platform=self.platform_name,
                message=f"No deployment found for {skill_name} on {self.platform_key}",
            )
        shutil.rmtree(target)
        return InstallResult(
            success=True,
            platform=self.platform_name,
            message=f"Skill '{skill_name}' removed from {self.platform_key}",
        )

    def execute(self, skill_name: str, task: str, **kwargs) -> ExecutionResult:
        """部署型适配器不伪装执行: 返回部署位置 + 触发方式"""
        target = self.target_dir(skill_name)
        installed = (target / "manifest.json").exists()
        return ExecutionResult(
            success=installed,
            output={
                "deployed": installed,
                "deploy_path": str(target),
                "trigger": self.trigger_hint or f"restart {self.platform_key} to activate",
                "task": task,
            },
        )

    def is_installed(self, skill_name: str) -> bool:
        return (self.target_dir(skill_name) / "manifest.json").exists()


class LocalDeployAdapter(DeployAdapter):
    platform_key = "local"
    trigger_hint = "本地部署 — zenskill deploy-skill --platform local 后经 test-skill 自检"

    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.LOCAL


class CodexAdapter(DeployAdapter):
    platform_key = "codex"
    trigger_hint = "重启 Codex CLI 后技能生效"

    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.CODEX

    def default_deploy_root(self) -> Path:
        return Path.home() / ".codex" / "skills"


class CursorDeployAdapter(DeployAdapter):
    """Cursor 真实目录机制未定，默认 .deployed，经 platforms.yaml 配置 target_dir"""

    platform_key = "cursor"
    trigger_hint = "在 Cursor 中导入部署目录下的 manifest.json"

    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.CURSOR


class OpencodeDeployAdapter(DeployAdapter):
    platform_key = "opencode"
    trigger_hint = "重启 OpenCode 后技能生效"

    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.OPENCODE

    def default_deploy_root(self) -> Path:
        return Path.home() / ".config" / "opencode" / "skills"


DEPLOY_ADAPTERS: Dict[str, type] = {
    "local": LocalDeployAdapter,
    "codex": CodexAdapter,
    "cursor": CursorDeployAdapter,
    "opencode": OpencodeDeployAdapter,
}


def get_deploy_adapter(platform: str, **kwargs) -> DeployAdapter:
    """按平台名取部署适配器实例，未知平台抛 KeyError"""
    if platform not in DEPLOY_ADAPTERS:
        raise KeyError(
            f"Unsupported platform: {platform}. "
            f"Supported: {sorted(DEPLOY_ADAPTERS.keys())}"
        )
    return DEPLOY_ADAPTERS[platform](**kwargs)
