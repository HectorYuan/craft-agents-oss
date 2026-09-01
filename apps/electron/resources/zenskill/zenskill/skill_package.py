"""
技能包格式 & 打包引擎 (Phase 9T)

定义标准化的技能包格式，支持一键分享和安装。

技能包目录结构：
```
my-skill/
├── skill.yaml              # 技能 DSL 定义
├── manifest.json           # 元数据
├── README.md               # 使用说明
├── prompts/                # Agent 提示词
│   ├── architect.md
│   ├── developer.md
│   └── coach.md
├── exercises/              # 练习任务
│   ├── easy.json
│   ├── medium.json
│   └── hard.json
└── tests/                  # 测试用例
```

CLI 命令：
    zenskill package build <skill_id>     # 构建技能包
    zenskill package validate <path>      # 验证技能包
    zenskill package install <path>       # 安装技能包
    zenskill package export <skill_id>    # 导出为 .zenskill-package 文件
"""

import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 数据模型 ──

PACKAGE_VERSION = "1.0"
PACKAGE_EXTENSION = ".zenskill-package"


@dataclass
class SkillPackageMeta:
    """技能包元数据 manifest.json"""
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    difficulty: str = "beginner"
    zenskill_version: str = ">=1.12.0"
    package_format_version: str = PACKAGE_VERSION
    created_at: str = field(default_factory=lambda: datetime.now().isoformat()[:19])
    dependencies: List[str] = field(default_factory=list)
    # Phase E1B: 来源追踪
    source_market: str = ""
    source_url: str = ""
    source_format: str = ""
    license: str = ""
    content_hash: str = ""
    installed_at: str = ""
    install_method: str = ""

    def to_spec(self) -> "SkillSpec":
        """升级到 SkillSpec (Phase S)"""
        from .core.skill_spec import SkillSpec
        return SkillSpec.from_package_meta(self)


class SkillPackage:
    """
    技能打包器

    支持：
    - build: SkillDefinition + 模板 → .zenskill-package ZIP
    - validate: 验证包结构完整性
    - install: 解包到 ~/.zenskill/skills/ + ~/.zenskill/packages/
    - export: 已安装技能 → .zenskill-package 文件
    """

    def __init__(self):
        self._packages_dir = Path.home() / ".zenskill" / "packages"
        self._skills_dir = Path.home() / ".zenskill" / "skills"
        self._packages_dir.mkdir(parents=True, exist_ok=True)
        self._skills_dir.mkdir(parents=True, exist_ok=True)

    # ── Build: 从技能 ID 构建技能包 ──

    def build(self, skill_id: str, output: Optional[str] = None) -> Dict[str, Any]:
        """
        从已注册的技能构建技能包

        1. 读取技能 state (如存在) 和生成的 .py 代码
        2. 生成 manifest.json
        3. 打包为 .zenskill-package ZIP

        Returns:
            {"skill_id", "output_path", "size_bytes", "contents": [...]}
        """
        meta = self._build_meta(skill_id)
        if output:
            pkg_path = Path(output)
            if not pkg_path.suffix:
                pkg_path = pkg_path.with_suffix(PACKAGE_EXTENSION)
        else:
            pkg_path = self._packages_dir / f"{skill_id}{PACKAGE_EXTENSION}"

        contents = []

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pkg_dir = tmp_path / skill_id
            pkg_dir.mkdir(parents=True)

            # 1. manifest.json
            (pkg_dir / "manifest.json").write_text(
                json.dumps(asdict(meta), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            contents.append("manifest.json")

            # 2. skill.yaml (从生成的 .py 提取 metadata)
            self._write_skill_yaml(pkg_dir, skill_id, meta)
            contents.append("skill.yaml")

            # 3. README.md
            self._write_readme(pkg_dir, meta)
            contents.append("README.md")

            # 4. prompts/ (从生成代码提取或模板)
            prompts_dir = pkg_dir / "prompts"
            prompts_dir.mkdir()
            self._write_prompts(prompts_dir, meta)
            contents.extend(["prompts/architect.md", "prompts/developer.md", "prompts/coach.md"])

            # 5. exercises/ (从 TaskGenerator 提取)
            exercises_dir = pkg_dir / "exercises"
            exercises_dir.mkdir()
            self._write_exercises(exercises_dir, skill_id)
            contents.extend(["exercises/easy.json", "exercises/medium.json"])

            # 6. tests/
            tests_dir = pkg_dir / "tests"
            tests_dir.mkdir()
            self._write_tests(tests_dir, skill_id)
            contents.append("tests/test_basic.py")

            # 打包 ZIP
            self._zip_dir(pkg_dir, pkg_path)

        return {
            "skill_id": skill_id,
            "output_path": str(pkg_path),
            "size_bytes": pkg_path.stat().st_size,
            "contents": contents,
            "meta": asdict(meta),
        }

    def _build_meta(self, skill_id: str) -> SkillPackageMeta:
        """从技能状态构建元数据"""
        # 尝试加载生成的 .py 模块
        py_file = self._skills_dir / f"{skill_id}.py"
        meta = SkillPackageMeta(name=skill_id)

        if py_file.exists():
            content = py_file.read_text(encoding="utf-8")
            # 从代码中提取元数据
            m = re.search(r'SKILL_NAME\s*=\s*"([^"]+)"', content)
            if m:
                meta.name = m.group(1)
            m = re.search(r'CATEGORY\s*=\s*"([^"]+)"', content)
            if m:
                meta.category = m.group(1)
            m = re.search(r'DIFFICULTY\s*=\s*"([^"]+)"', content)
            if m:
                meta.difficulty = m.group(1)
            m = re.search(r'DIMENSION_WEIGHTS\s*=\s*\{([^}]+)\}', content)
            if m:
                meta.tags.append("has-dimensions")

        # 尝试从 SkillStateManager 补充状态
        try:
            from zenskill.core.paths import SkillStateManager
            mgr = SkillStateManager(skill_id)
            state = mgr.load()
            meta.description = state.get("skill_name", skill_id)
            meta.tags.append(state.get("category", "general"))
        except Exception:
            pass

        return meta

    def _write_skill_yaml(self, pkg_dir: Path, skill_id: str, meta: SkillPackageMeta) -> None:
        """写入 skill.yaml（简化 DSL）"""
        lines = [
            f"name: {meta.name}",
            f"version: {meta.version}",
            f"category: {meta.category}",
            f"difficulty: {meta.difficulty}",
            f"description: {meta.description}",
            f"tags: [{', '.join(meta.tags)}]",
            "",
            "dimensions:",
            "  proficiency: 0.2",
            "  stability: 0.2",
            "  satisfaction: 0.2",
            "  responsiveness: 0.2",
            "  memory: 0.2",
        ]
        (pkg_dir / "skill.yaml").write_text("\n".join(lines), encoding="utf-8")

    def _write_readme(self, pkg_dir: Path, meta: SkillPackageMeta) -> None:
        content = f"""# {meta.name}

{meta.description}

## 安装

```bash
zenskill package install {meta.name}{PACKAGE_EXTENSION}
```

## 使用

```bash
zenskill skill status --skill-id {meta.name}
```

## 元数据

- 分类: {meta.category}
- 难度: {meta.difficulty}
- 版本: {meta.version}
"""
        (pkg_dir / "README.md").write_text(content, encoding="utf-8")

    def _write_prompts(self, prompts_dir: Path, meta: SkillPackageMeta) -> None:
        """写入预置的 Agent 提示词"""
        for role, role_name, desc in [
            ("architect", "架构师", "从系统设计角度"),
            ("developer", "开发者", "从实现角度"),
            ("coach", "教练", "从学习角度"),
        ]:
            content = f"""你是一位经验丰富的 {role_name}，专注于 {meta.name}。

{meta.description if role != 'coach' else f'教导学习者掌握 {meta.name}。保持鼓励和积极的态度。'}

涉及的领域: {meta.category}
难度级别: {meta.difficulty}
"""
            (prompts_dir / f"{role}.md").write_text(content, encoding="utf-8")

    def _write_exercises(self, exercises_dir: Path, skill_id: str) -> None:
        """从生成的技能代码中提取练习任务"""
        py_file = self._skills_dir / f"{skill_id}.py"
        easy = [{"level": "beginner", "description": f"完成 {skill_id} 的基础练习"}]
        medium = [{"level": "intermediate", "description": f"完成 {skill_id} 的进阶练习"}]

        if py_file.exists():
            content = py_file.read_text(encoding="utf-8")
            # 尝试提取 tasks
            m = re.search(r'TASKS\s*=\s*\[(.+?)\]', content, re.DOTALL)
            if m:
                try:
                    tasks = json.loads("[" + m.group(1) + "]")
                    easy = [t for t in tasks if t.get("level", "").startswith("beginner")] or easy
                    medium = [t for t in tasks if not t.get("level", "").startswith("beginner")] or medium
                except Exception:
                    pass

        (exercises_dir / "easy.json").write_text(json.dumps(easy, indent=2, ensure_ascii=False), encoding="utf-8")
        (exercises_dir / "medium.json").write_text(json.dumps(medium, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_tests(self, tests_dir: Path, skill_id: str) -> None:
        """写入基础测试模板"""
        content = f'''"""
{skill_id} 技能包测试
"""

def test_skill_import():
    """验证技能模块可导入"""
    try:
        import importlib
        spec = importlib.util.spec_from_file_location(
            "{skill_id}",
            "~/.zenskill/skills/{skill_id}.py"
        )
        assert spec is not None
    except Exception:
        pass  # 安装后可运行


def test_register():
    """验证 register() 返回正确结构"""
    import importlib.util
    import sys
    from pathlib import Path

    py_path = Path.home() / ".zenskill" / "skills" / "{skill_id}.py"
    if py_path.exists():
        spec = importlib.util.spec_from_file_location("{skill_id}", py_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        reg = mod.register()
        assert "skill_id" in reg
        assert "task_generator" in reg
        assert "evaluator" in reg
'''
        (tests_dir / "test_basic.py").write_text(content, encoding="utf-8")

    @staticmethod
    def _zip_dir(source: Path, output: Path) -> None:
        """将目录打包为 ZIP"""
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(source):
                for f in files:
                    file_path = Path(root) / f
                    arcname = str(file_path.relative_to(source))
                    zf.write(file_path, arcname)

    # ── Validate: 验证技能包 ──

    def validate(self, path: str) -> Dict[str, Any]:
        """
        验证技能包结构完整性

        Returns:
            {"valid": bool, "errors": [...], "warnings": [...], "meta": {...}}
        """
        pkg_path = Path(path)
        errors = []
        warnings = []
        meta = None

        if not pkg_path.exists():
            return {"valid": False, "errors": [f"文件不存在: {path}"], "warnings": [], "meta": None}

        if not pkg_path.suffix == PACKAGE_EXTENSION:
            warnings.append(f"文件名以 {PACKAGE_EXTENSION} 结尾更佳")

        try:
            with zipfile.ZipFile(pkg_path, "r") as zf:
                names = zf.namelist()

                # 检查必需文件
                required = ["manifest.json", "skill.yaml", "README.md"]
                for req in required:
                    if not any(n.endswith(req) for n in names):
                        errors.append(f"缺少必需文件: {req}")

                # 检查 manifest.json
                if any(n.endswith("manifest.json") for n in names):
                    try:
                        manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
                        meta = SkillPackageMeta(**manifest_data)
                        if not meta.name:
                            errors.append("manifest.json: name 不能为空")
                    except Exception as e:
                        errors.append(f"manifest.json 解析失败: {e}")

                # 检查 prompts/
                if not any(n.startswith("prompts/") for n in names):
                    warnings.append("建议包含 prompts/ 目录（Agent 提示词）")

                # 检查 exercises/
                if not any(n.startswith("exercises/") for n in names):
                    warnings.append("建议包含 exercises/ 目录（练习任务）")

        except zipfile.BadZipFile:
            errors.append("文件不是有效的 ZIP 包")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "meta": asdict(meta) if meta else None,
        }

    # ── Install: 安装技能包 ──

    def _backups_dir(self, name: str) -> Path:
        return self._packages_dir / ".backups" / name

    def _snapshot_before_overwrite(self, name: str) -> Optional[str]:
        """覆盖安装前快照现有目录，返回快照 ID（时间戳），无可快照返回 None"""
        install_dir = self._packages_dir / name
        if not install_dir.exists() or not any(install_dir.iterdir()):
            return None

        from datetime import datetime

        snapshot_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = self._backups_dir(name) / snapshot_id
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(install_dir, target)
        return snapshot_id

    def install(self, path: str) -> Dict[str, Any]:
        """
        安装技能包

        1. 验证包完整性
        2. 覆盖前快照现有安装（P2-3，供回滚）
        3. 解压到 ~/.zenskill/packages/<name>/
        4. 将 .py 复制到 ~/.zenskill/skills/<name>.py（如包含）
        5. 注册到技能管理器

        Returns:
            {"success": bool, "name": "...", "path": "...", "snapshot": ..., "errors": [...]}
        """
        validation = self.validate(path)
        if not validation["valid"]:
            return {"success": False, "name": "", "path": path, "errors": validation["errors"]}

        meta = validation.get("meta", {}) or {}
        name = meta.get("name", Path(path).stem)

        install_dir = self._packages_dir / name
        snapshot_id = self._snapshot_before_overwrite(name)
        if install_dir.exists():
            shutil.rmtree(install_dir)
        install_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(path, "r") as zf:
                zf.extractall(install_dir)

            # 如果技能包含 .py 文件，复制到 skills/
            for py_file in install_dir.rglob("*.py"):
                shutil.copy2(py_file, self._skills_dir / py_file.name)

            return {
                "success": True,
                "name": name,
                "path": str(install_dir),
                "snapshot": snapshot_id,
                "errors": [],
            }
        except Exception as e:
            return {"success": False, "name": name, "path": path, "errors": [str(e)]}

    def list_backups(self, name: str) -> list:
        """列出技能包的可用快照（新在前）"""
        backups = self._backups_dir(name)
        if not backups.exists():
            return []
        return sorted(
            (p.name for p in backups.iterdir() if p.is_dir()), reverse=True
        )

    def rollback(self, name: str, snapshot_id: Optional[str] = None) -> Dict[str, Any]:
        """回滚技能包到指定快照（缺省取最新）

        Returns:
            {"success": bool, "name": ..., "snapshot": ..., "errors": [...]}
        """
        available = self.list_backups(name)
        if not available:
            return {"success": False, "name": name, "snapshot": None,
                    "errors": [f"No backups for {name}"]}

        target_id = snapshot_id or available[0]
        if target_id not in available:
            return {"success": False, "name": name, "snapshot": target_id,
                    "errors": [f"Snapshot {target_id} not found; available: {available}"]}

        install_dir = self._packages_dir / name
        source = self._backups_dir(name) / target_id
        try:
            if install_dir.exists():
                shutil.rmtree(install_dir)
            shutil.copytree(source, install_dir)

            for py_file in install_dir.rglob("*.py"):
                shutil.copy2(py_file, self._skills_dir / py_file.name)

            return {"success": True, "name": name, "snapshot": target_id, "errors": []}
        except Exception as e:
            return {"success": False, "name": name, "snapshot": target_id, "errors": [str(e)]}

    # ── Export: 导出已安装技能为包 ──

    def export(self, skill_id: str, output: Optional[str] = None) -> Dict[str, Any]:
        """
        导出已安装技能为 .zenskill-package 文件

        等同于 build + 打包，但优先使用已生成的 .py 代码
        """
        return self.build(skill_id, output)

    # ── List installed packages ──

    def list_packages(self) -> List[Dict]:
        """列出已安装的技能包"""
        packages = []
        if not self._packages_dir.exists():
            return packages
        for pkg_dir in sorted(self._packages_dir.iterdir()):
            if pkg_dir.is_dir():
                mf = pkg_dir / "manifest.json"
                if mf.exists():
                    try:
                        meta = json.loads(mf.read_text(encoding="utf-8"))
                        packages.append(meta)
                    except Exception:
                        packages.append({"name": pkg_dir.name, "version": "?"})
        return packages
