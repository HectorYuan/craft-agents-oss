"""
npx Adapter — 基于 SkillSpec 的 npx 技能安装/调用 (Phase S5)

用法:
    from zenskill.skills.npx_adapter import NpxAdapter

    adapter = NpxAdapter()
    spec = adapter.resolve("tsx")
    spec.save()

    # 从 URI 直接安装
    result = adapter.install_from_uri("npx://tsx")
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class NpmPackageInfo:
    """npm 包元数据"""
    name: str
    description: str = ""
    version: str = "latest"
    license: str = ""
    keywords: List[str] = field(default_factory=list)
    homepage: str = ""
    repository: str = ""
    author: str = ""
    dependencies: Dict[str, str] = field(default_factory=dict)
    engines: Dict[str, str] = field(default_factory=dict)
    bin: Dict[str, str] = field(default_factory=dict)


class NpxAdapter:
    """npx 技能适配器

    生命周期:
    1. resolve(pkg) → NpmPackageInfo (从 npm registry)
    2. to_spec(info) → SkillSpec
    3. install(spec) → 持久化 + 注册到路由
    4. execute(spec, args) → subprocess npx ...
    """

    # 已知的 npx 工具 → 技能映射
    KNOWN_TOOLS = {
        "tsx": {"category": "dev", "description": "TypeScript executor"},
        "ts-node": {"category": "dev", "description": "TypeScript execution environment"},
        "create-react-app": {"category": "dev", "description": "React project scaffolding"},
        "create-next-app": {"category": "dev", "description": "Next.js project scaffolding"},
        "vite": {"category": "dev", "description": "Frontend build tool"},
        "eslint": {"category": "dev", "description": "JavaScript linter"},
        "prettier": {"category": "dev", "description": "Code formatter"},
        "typescript": {"category": "dev", "description": "TypeScript compiler"},
        "prisma": {"category": "dev", "description": "ORM and database toolkit"},
        "vitest": {"category": "dev", "description": "Unit test framework"},
        "playwright": {"category": "dev", "description": "Browser testing framework"},
        "turbo": {"category": "ops", "description": "Monorepo build orchestrator"},
        "vercel": {"category": "ops", "description": "Deployment platform CLI"},
        "netlify-cli": {"category": "ops", "description": "Netlify deployment CLI"},
        "firebase-tools": {"category": "ops", "description": "Firebase CLI"},
        "supabase": {"category": "ops", "description": "Supabase CLI"},
        "degit": {"category": "dev", "description": "Git repository downloader"},
        "zx": {"category": "dev", "description": "Shell scripting with JavaScript"},
        "bun": {"category": "dev", "description": "JavaScript runtime and toolkit"},
        "pnpm": {"category": "dev", "description": "Fast package manager"},
    }

    def resolve(self, package_name: str, version: Optional[str] = None) -> NpmPackageInfo:
        """解析 npm 包信息

        优先使用本地缓存 (npm view)，失败时用内置数据库。
        """
        # 先查内置数据库
        known = self.KNOWN_TOOLS.get(package_name, {})
        info = NpmPackageInfo(
            name=package_name,
            description=known.get("description", ""),
            version=version or "latest",
        )

        # 尝试 npm view
        try:
            cmd = ["npm", "view", package_name,
                   "--json",
                   "name", "description", "version",
                   "keywords", "license", "homepage",
                   "repository.url", "author", "bin", "engines"]
            if version and version != "latest":
                cmd.insert(3, f"{package_name}@{version}")

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
                env={**__import__('os').environ, "NODE_NO_WARNINGS": "1"},
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                # npm view --json 可能返回数组或单对象
                if isinstance(data, list):
                    data = data[0]

                info = NpmPackageInfo(
                    name=data.get("name", package_name),
                    description=data.get("description", ""),
                    version=data.get("version", version or "latest"),
                    license=data.get("license", ""),
                    keywords=data.get("keywords", []),
                    homepage=data.get("homepage", ""),
                    repository=data.get("repository", {}).get("url", "") if isinstance(data.get("repository"), dict) else data.get("repository", ""),
                    author=_extract_author(data.get("author", "")),
                    engines=data.get("engines", {}),
                    bin=data.get("bin", {}),
                )
                logger.info(f"npm view resolved: {package_name}@{info.version}")
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
            logger.debug(f"npm view failed for {package_name}: {e}, using builtin data")

        # 用已知数据补充
        if not info.description and known.get("description"):
            info.description = known["description"]
        if not info.keywords:
            info.keywords = [package_name]

        return info

    def to_spec(self, info: NpmPackageInfo) -> "SkillSpec":
        """将 npm 包信息转换为 SkillSpec"""
        from zenskill.core.skill_spec import SkillSpec, CapabilitySpec
        from zenskill.core.skill_types import SkillType

        skill_id = f"npx-{info.name}"
        known = self.KNOWN_TOOLS.get(info.name, {})
        category = known.get("category", "dev")

        # 推断 node 版本要求
        requires = {}
        if info.engines:
            if "node" in info.engines:
                requires["node"] = info.engines["node"]

        # 能力: 每个 bin entry 或包名本身
        capabilities = []
        if info.bin:
            for bin_name, _ in info.bin.items():
                capabilities.append(CapabilitySpec(
                    name=bin_name,
                    description=f"npx {info.name} → {bin_name}",
                    proficiency=0.8,
                    keywords=[bin_name, info.name, "npx"],
                    examples=[f"npx {info.name} --help"],
                ))
        else:
            capabilities.append(CapabilitySpec(
                name=info.name,
                description=info.description or f"npx {info.name}",
                proficiency=0.7,
                keywords=[info.name, "npx"] + (info.keywords or []),
                examples=[f"npx {info.name} --help"],
            ))

        return SkillSpec(
            id=skill_id,
            name=info.name,
            display_name=f"npx {info.name}",
            icon="📦",
            description=info.description,
            version=info.version,
            category=category,
            skill_type=SkillType.EXECUTION,
            tags=info.keywords or [info.name],
            author=info.author or "npm",
            license=info.license or "",
            source="market",
            source_market="npm",
            source_url=f"npm://{info.name}",
            source_format="package.json",
            source_ref=info.version,
            runtime_deps=[info.name],
            requires=requires,
            adapter="npx",
            entry_point=info.name,
            capabilities=capabilities,
            keywords=info.keywords or [info.name],
            examples=[f"npx {info.name}"],
        )

    def install_from_uri(self, uri: str) -> Dict[str, Any]:
        """从 npx:// URI 安装技能

        Args:
            uri: "npx://tsx" 或 "npx://tsx@4.x"

        Returns:
            {"success": bool, "skill_id": str, ...}
        """
        # 解析 URI
        m = re.match(r'npx://([^@]+)(?:@(.+))?', uri)
        if not m:
            return {"success": False, "error": f"Invalid npx URI: {uri}"}

        pkg_name = m.group(1)
        version = m.group(2)

        try:
            info = self.resolve(pkg_name, version)
            spec = self.to_spec(info)

            if spec.save():
                return {
                    "success": True,
                    "skill_id": spec.id,
                    "source": "npm",
                    "name": spec.name,
                    "version": info.version,
                    "method": "npx",
                }
            else:
                return {"success": False, "error": f"Failed to save skill: {spec.id}"}
        except Exception as e:
            logger.error(f"npx install failed: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def check_available() -> bool:
        """检查 npx 是否可用"""
        try:
            result = subprocess.run(
                ["npx", "--version"], capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False


def _extract_author(author_raw) -> str:
    """从 npm author 字段提取名称"""
    if isinstance(author_raw, dict):
        return author_raw.get("name", "")
    if isinstance(author_raw, str):
        # "Name <email>" → "Name"
        m = re.match(r'^([^<]+)', author_raw)
        return m.group(1).strip() if m else author_raw.strip()
    return ""


# ── 便捷函数 ──

def install_npx_skill(uri: str) -> Dict[str, Any]:
    """一行安装 npx 技能"""
    adapter = NpxAdapter()
    return adapter.install_from_uri(uri)


def list_known_npx_tools() -> List[Dict[str, str]]:
    """列出已知的 npx 工具"""
    return [
        {"name": k, "category": v["category"], "description": v["description"]}
        for k, v in NpxAdapter.KNOWN_TOOLS.items()
    ]
