"""Coze 平台适配器 — @coze/cli 驱动 (P3 收尾)

依赖: npm install -g @coze/cli && coze auth login --oauth
能力:
- is_installed: 经 `coze auth status` 返回真实登录态
- install: 本地技能目录打包为 .skill(zip) 后 `coze code skill upload -p <projectId>`
  （.skill 为扣子个人技能包；无 project_id 时返回创建项目指引）
- execute: 结构化指引（真实挂载命令 coze code skill add）
- parse_skill_metadata: 走 skills.frontmatter 统一模块

coze CLI 不含技能商店搜索/发布；商店入站仍需开放 API（另立项）。
"""

import json
import subprocess
import zipfile
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Optional

from .base import PlatformAdapter, PlatformType, InstallResult, ExecutionResult


class CozeAdapter(PlatformAdapter):
    """Coze 平台适配器（CLI 驱动，coze 不可用时优雅降级）"""

    @property
    def platform_name(self) -> str:
        return "coze"

    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.COZE

    def _run(self, *args: str, timeout: int = 30) -> Optional[subprocess.CompletedProcess]:
        """运行 coze 命令（JSON 输出）；CLI 不存在返回 None"""
        try:
            return subprocess.run(
                ["coze", *args, "--format", "json", "--no-color"],
                capture_output=True, text=True, timeout=timeout,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def _auth(self) -> Optional[Dict[str, Any]]:
        r = self._run("auth", "status")
        if r is None or r.returncode != 0:
            return None
        try:
            data = json.loads(r.stdout)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None

    def _ready(self) -> bool:
        auth = self._auth()
        return bool(auth and auth.get("logged_in"))

    @staticmethod
    def _setup_hint() -> str:
        return (
            "coze CLI 未安装或未登录: "
            "npm install -g @coze/cli && coze auth login --oauth"
        )

    @staticmethod
    def _pack_skill_file(skill_path: Path, name: str) -> Optional[Path]:
        """把技能目录打包为 <name>.skill（zip 归档，含 SKILL.md 与附属文件）"""
        if not skill_path.is_dir():
            return skill_path if skill_path.suffix == ".skill" else None

        fd = NamedTemporaryFile(prefix=f"zenskill-{name}-", suffix=".skill", delete=False)
        fd.close()
        target = Path(fd.name)
        with zipfile.ZipFile(target, "w") as zf:
            for p in sorted(skill_path.rglob("*")):
                if p.is_file() and ".deployed" not in p.parts:
                    zf.write(p, p.relative_to(skill_path).as_posix())
        return target

    def install(
        self,
        skill_name: str,
        skill_path: str = None,
        project_id: str = None,
        **kwargs,
    ) -> InstallResult:
        """上传技能到扣子项目（coze code skill upload）

        Args:
            skill_name: 技能名称
            skill_path: 本地技能目录（含 SKILL.md）或 .skill 文件
            project_id: 目标扣子项目 ID（coze code project list 可查）
        """
        if not self._ready():
            return InstallResult(
                success=False, platform=self.platform_name,
                message=self._setup_hint(),
            )

        if not project_id:
            return InstallResult(
                success=False, platform=self.platform_name,
                message=(
                    "需要扣子项目 ID (-p)。先创建/查询项目: "
                    "coze code project create --type agent 或 coze code project list"
                ),
            )

        if not skill_path:
            return InstallResult(
                success=False, platform=self.platform_name,
                message=f"缺少 skill_path（本地技能目录或 .skill 文件）: {skill_name}",
            )

        packed = self._pack_skill_file(Path(skill_path), skill_name)
        if packed is None:
            return InstallResult(
                success=False, platform=self.platform_name,
                message=f"skill_path 既非目录也非 .skill 文件: {skill_path}",
            )

        r = self._run("code", "skill", "upload", str(packed), "-p", project_id, timeout=60)
        if r is None or r.returncode != 0:
            detail = (r.stderr if r else "" or "").strip()[:200]
            return InstallResult(
                success=False, platform=self.platform_name,
                message=f"coze skill upload 失败: {detail or 'CLI 不可用'}",
            )

        return InstallResult(
            success=True, platform=self.platform_name,
            message=f"Skill '{skill_name}' uploaded to Coze project {project_id}",
            skill_path=str(packed),
        )

    def uninstall(self, skill_name: str) -> InstallResult:
        """个人技能删除需 skillId + 项目上下文，返回操作指引"""
        return InstallResult(
            success=True, platform=self.platform_name,
            message=(
                f"请在扣子侧删除 '{skill_name}': "
                f"coze code skill delete（个人技能）或 coze code skill remove <skillId> -p <projectId>"
            ),
        )

    def execute(self, skill_name: str, task: str, project_id: str = None, **kwargs) -> ExecutionResult:
        """返回结构化挂载/触发指引（真实命令）"""
        ready = self._ready()
        pid = f" -p {project_id}" if project_id else " -p <projectId>"
        return ExecutionResult(
            success=ready,
            output={
                "ready": ready,
                "task": task,
                "steps": [
                    f"coze code skill add <skillId>{pid}  # 挂载到项目会话",
                    "coze code message send -p <projectId> --message '<task>'  # 触发",
                ],
                "setup": None if ready else self._setup_hint(),
            },
        )

    def is_installed(self, skill_name: str) -> bool:
        """平台级可用性: coze CLI 存在且已登录"""
        return self._ready()

    def get_status(self, skill_name: str) -> dict:
        status = {
            "name": skill_name,
            "platform": self.platform_name,
            "installed": False,
        }
        auth = self._auth()
        if auth:
            status["installed"] = bool(auth.get("logged_in"))
            user = auth.get("user") or {}
            status["account"] = user.get("nick_name") or user.get("user_name", "")
            status["token_expires_at"] = auth.get("token_expires_at", "")
        else:
            status["error"] = self._setup_hint()
        return status

    def parse_skill_metadata(self, skill_path: str) -> dict:
        """解析 SKILL.md 元数据"""
        skill_md = Path(skill_path) / "SKILL.md"
        if not skill_md.exists():
            return {}

        from ..skills.frontmatter import parse_skill_md

        meta, _body = parse_skill_md(skill_md)
        if meta.errors:
            return {}
        return meta.to_dict()
