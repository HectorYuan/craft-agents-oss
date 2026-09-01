"""
SkillSpec — 技能全生命周期统一规范 (Phase S1)

单一真相源 (SSOT): 所有其他技能表示类型均从此投影。

用法:
    from zenskill.core.skill_spec import SkillSpec, CapabilitySpec

    # 定义
    spec = SkillSpec(id="my-skill", name="My Skill", category="dev")
    spec.save()

    # 阶段投影
    definition = spec.to_definition()
    package = spec.to_package_meta()
    profile = spec.to_profile()
    entry = spec.to_search_entry()
    caps = spec.to_capabilities()

    # TOML 序列化
    spec.to_toml("skill.toml")
    spec2 = SkillSpec.from_toml("skill.toml")

    # 验证
    errors = spec.validate()
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .skill_types import SkillType

if TYPE_CHECKING:
    from ..skill_dsl import SkillDefinition
    from ..skill_package import SkillPackageMeta
    from ..skill_router import SkillCapability
    from ..skills.search_engine import SkillIndexEntry

logger = logging.getLogger(__name__)

# ── TOML 支持 (可选依赖) ──
try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

try:
    import tomli_w
except ImportError:
    tomli_w = None


# ═══════════════════════════════════════════════════════════════
# CapabilitySpec — 能力规格
# ═══════════════════════════════════════════════════════════════

@dataclass
class CapabilitySpec:
    """技能的单个能力描述"""
    name: str                                    # 能力名称
    description: str = ""                        # 能力描述
    proficiency: float = 0.5                     # 熟练度 0-1
    keywords: List[str] = field(default_factory=list)  # 匹配关键词
    examples: List[str] = field(default_factory=list)  # 使用示例

    def to_capability(self) -> "SkillCapability":
        """转换为 SkillRouter 的能力对象"""
        from ..skill_router import SkillCapability as SC
        return SC(
            name=self.name,
            description=self.description,
            proficiency=self.proficiency,
            keywords=self.keywords,
            examples=self.examples,
        )

    @classmethod
    def from_capability(cls, cap: "SkillCapability") -> "CapabilitySpec":
        return cls(
            name=cap.name,
            description=cap.description,
            proficiency=cap.proficiency,
            keywords=cap.keywords,
            examples=cap.examples,
        )

    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════
# SkillSpec — 技能全生命周期统一规范
# ═══════════════════════════════════════════════════════════════

@dataclass
class SkillSpec:
    """技能全生命周期统一规范 (49 字段 · 9 分组)

    这是唯一的权威技能表示。所有其他类型 (SkillDefinition,
    SkillPackageMeta, SkillProfile, SkillIndexEntry, SkillCapability)
    都是 SkillSpec 在不同阶段的有损投影。
    """

    # ═══════════════════════════════════════════════════════════
    # 🆔 Identity (5) — 必填: id, name
    # ═══════════════════════════════════════════════════════════
    id: str = ""
    name: str = ""
    display_name: str = ""
    icon: str = "📚"
    description: str = ""

    # ═══════════════════════════════════════════════════════════
    # 📦 Version (4)
    # ═══════════════════════════════════════════════════════════
    version: str = "0.1.0"
    zenskill_min: str = ">=1.19.0"
    format_version: str = "1"
    spec_version: str = "1.0"

    # ═══════════════════════════════════════════════════════════
    # 🏷️ Classification (5)
    # ═══════════════════════════════════════════════════════════
    category: str = "general"
    skill_type: SkillType = SkillType.GENERAL
    difficulty: str = "beginner"
    tags: List[str] = field(default_factory=list)
    topic: str = ""

    # ═══════════════════════════════════════════════════════════
    # 👤 Authorship (5)
    # ═══════════════════════════════════════════════════════════
    author: str = ""
    author_email: str = ""
    author_url: str = ""
    license: str = ""
    copyright: str = ""

    # ═══════════════════════════════════════════════════════════
    # 🔗 Source (7)
    # ═══════════════════════════════════════════════════════════
    source: str = "unknown"
    source_market: str = ""
    source_url: str = ""
    source_format: str = ""
    source_ref: str = ""
    content_hash: str = ""
    verified: bool = False

    # ═══════════════════════════════════════════════════════════
    # 🔗 Dependencies (5)
    # ═══════════════════════════════════════════════════════════
    prerequisites: List[str] = field(default_factory=list)
    runtime_deps: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    platforms: List[str] = field(default_factory=list)
    requires: Dict[str, str] = field(default_factory=dict)

    # ═══════════════════════════════════════════════════════════
    # 🌱 Cultivation (9)
    # ═══════════════════════════════════════════════════════════
    level: str = "NOVICE"
    proficiency_weight: float = 0.2
    stability_weight: float = 0.2
    satisfaction_weight: float = 0.2
    responsiveness_weight: float = 0.2
    memory_weight: float = 0.2
    success_rate: float = 0.0
    usage_count: int = 0
    last_used: str = ""

    # ═══════════════════════════════════════════════════════════
    # 📚 Learning (4)
    # ═══════════════════════════════════════════════════════════
    practice_tasks: List[Dict[str, str]] = field(default_factory=list)
    success_metrics: List[str] = field(default_factory=list)
    key_concepts: List[str] = field(default_factory=list)
    reflection_prompts: List[str] = field(default_factory=list)

    # ═══════════════════════════════════════════════════════════
    # ⚡ Runtime (5)
    # ═══════════════════════════════════════════════════════════
    adapter: str = ""
    entry_point: str = ""
    capabilities: List[CapabilitySpec] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)

    # ── 元数据 (非规范字段) ──
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""
    installed_at: str = ""

    # ═══════════════════════════════════════════════════════════
    # Factory Methods
    # ═══════════════════════════════════════════════════════════

    @classmethod
    def from_dict(cls, d: dict) -> "SkillSpec":
        """从字典构造 SkillSpec"""
        # 处理 skill_type 枚举
        st = d.get("skill_type", "general")
        if isinstance(st, str):
            try:
                st = SkillType(st)
            except ValueError:
                st = SkillType.GENERAL
        elif isinstance(st, SkillType):
            pass
        else:
            st = SkillType.GENERAL

        # 处理 capabilities
        caps_raw = d.get("capabilities", [])
        capabilities = []
        for c in caps_raw:
            if isinstance(c, CapabilitySpec):
                capabilities.append(c)
            elif isinstance(c, dict):
                capabilities.append(CapabilitySpec(**c))

        return cls(
            # Identity
            id=d.get("id", d.get("skill_id", "")),
            name=d.get("name", ""),
            display_name=d.get("display_name", ""),
            icon=d.get("icon", "📚"),
            description=d.get("description", ""),
            # Version
            version=d.get("version", "0.1.0"),
            zenskill_min=d.get("zenskill_min", ">=1.19.0"),
            format_version=d.get("format_version", "1"),
            spec_version=d.get("spec_version", "1.0"),
            # Classification
            category=d.get("category", "general"),
            skill_type=st,
            difficulty=d.get("difficulty", "beginner"),
            tags=d.get("tags", []),
            topic=d.get("topic", ""),
            # Authorship
            author=d.get("author", ""),
            author_email=d.get("author_email", ""),
            author_url=d.get("author_url", ""),
            license=d.get("license", ""),
            copyright=d.get("copyright", ""),
            # Source
            source=d.get("source", "unknown"),
            source_market=d.get("source_market", ""),
            source_url=d.get("source_url", ""),
            source_format=d.get("source_format", ""),
            source_ref=d.get("source_ref", ""),
            content_hash=d.get("content_hash", ""),
            verified=d.get("verified", False),
            # Dependencies
            prerequisites=d.get("prerequisites", d.get("dependencies", [])),
            runtime_deps=d.get("runtime_deps", []),
            tools=d.get("tools", []),
            platforms=d.get("platforms", []),
            requires=d.get("requires", {}),
            # Cultivation
            level=d.get("level", "NOVICE"),
            proficiency_weight=d.get("proficiency_weight", 0.2),
            stability_weight=d.get("stability_weight", 0.2),
            satisfaction_weight=d.get("satisfaction_weight", 0.2),
            responsiveness_weight=d.get("responsiveness_weight", 0.2),
            memory_weight=d.get("memory_weight", 0.2),
            success_rate=d.get("success_rate", 0.0),
            usage_count=d.get("usage_count", 0),
            last_used=d.get("last_used", ""),
            # Learning
            practice_tasks=d.get("practice_tasks", []),
            success_metrics=d.get("success_metrics", []),
            key_concepts=d.get("key_concepts", []),
            reflection_prompts=d.get("reflection_prompts", []),
            # Runtime
            adapter=d.get("adapter", ""),
            entry_point=d.get("entry_point", ""),
            capabilities=capabilities,
            keywords=d.get("keywords", []),
            examples=d.get("examples", []),
            # Meta
            is_active=d.get("is_active", True),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            installed_at=d.get("installed_at", ""),
        )

    @classmethod
    def from_toml(cls, path: str | Path) -> "SkillSpec":
        """从 TOML 文件加载 SkillSpec

        Args:
            path: skill.toml 文件路径

        Returns:
            SkillSpec 实例

        Raises:
            ImportError: 如果 tomllib/tomli 不可用
            FileNotFoundError: 如果文件不存在
        """
        if tomllib is None:
            raise ImportError("tomllib/tomli not available. Install with: pip install tomli")

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"SkillSpec file not found: {path}")

        with open(path, "rb") as f:
            data = tomllib.load(f)

        # 展平 TOML 子表
        # [cultivation] → 顶层字段
        for section in ("cultivation",):
            if section in data:
                for k, v in data[section].items():
                    data[k] = v

        # [[capabilities]] → capabilities 列表
        caps_list = []
        for cap in data.get("capabilities", []):
            caps_list.append(CapabilitySpec(
                name=cap.get("name", ""),
                description=cap.get("description", ""),
                proficiency=cap.get("proficiency", 0.5),
                keywords=cap.get("keywords", []),
                examples=cap.get("examples", []),
            ))
        data["capabilities"] = caps_list

        return cls.from_dict(data)

    @classmethod
    def from_db(cls, skill_id: str) -> Optional["SkillSpec"]:
        """从 SQLite 加载 SkillSpec（通过 SkillProfile）"""
        from .skill_profile import SkillProfile
        profile = SkillProfile.load(skill_id)
        if profile is None:
            return None
        return profile.to_spec()

    # ═══════════════════════════════════════════════════════════
    # Stage Projections (Spec → 专用类型)
    # ═══════════════════════════════════════════════════════════

    def to_definition(self) -> "SkillDefinition":
        """投影到 SkillDefinition (DSL 层)"""
        from ..skill_dsl import SkillDefinition as SD
        return SD(
            name=self.name,
            description=self.description,
            category=self.category,
            difficulty=self.difficulty,
            proficiency_weight=self.proficiency_weight,
            stability_weight=self.stability_weight,
            satisfaction_weight=self.satisfaction_weight,
            responsiveness_weight=self.responsiveness_weight,
            memory_weight=self.memory_weight,
            prerequisites=list(self.prerequisites),
            tools=list(self.tools),
            practice_tasks=[dict(t) for t in self.practice_tasks],
            success_metrics=list(self.success_metrics),
        )

    def to_package_meta(self) -> "SkillPackageMeta":
        """投影到 SkillPackageMeta (打包层)"""
        from ..skill_package import SkillPackageMeta as PM
        now = datetime.now(timezone.utc).isoformat()[:19]
        return PM(
            name=self.name,
            version=self.version,
            description=self.description,
            author=self.author,
            category=self.category,
            tags=list(self.tags),
            difficulty=self.difficulty,
            zenskill_version=self.zenskill_min,
            dependencies=list(self.prerequisites),
            source_market=self.source_market,
            source_url=self.source_url,
            source_format=self.source_format,
            license=self.license,
            content_hash=self.content_hash,
            installed_at=self.installed_at or now,
            install_method=f"{self.source}:{self.adapter}" if self.adapter else self.source,
        )

    def to_profile(self) -> "SkillProfile":
        """投影到 SkillProfile (存储聚合层)"""
        from .skill_profile import SkillProfile as SP
        return SP(
            skill_id=self.id,
            name=self.name,
            display_name=self.display_name,
            description=self.description,
            icon=self.icon,
            source=self.source,
            source_market=self.source_market,
            source_url=self.source_url,
            source_format=self.source_format,
            license=self.license,
            author=self.author,
            version=self.version,
            category=self.category,
            difficulty=self.difficulty,
            tags=list(self.tags),
            level=self.level,
            level_progress=0.0,
            total_interactions=self.usage_count,
            success_count=int(self.usage_count * self.success_rate),
            fail_count=int(self.usage_count * (1 - self.success_rate)),
            success_rate=self.success_rate,
            last_interaction_at=self.last_used,
            proficiency=self.proficiency_weight,
            stability=self.stability_weight,
            satisfaction=self.satisfaction_weight,
            responsiveness=self.responsiveness_weight,
            memory=self.memory_weight,
            rating_overall=0.0,
            star_level="Experimental",
            star_icon="⭐",
            user_rating_avg=0.0,
            user_rating_count=0,
            is_active=self.is_active,
            verified=self.verified,
            created_at=self.created_at,
            updated_at=self.updated_at,
            installed_at=self.installed_at,
        )

    def to_search_entry(self) -> "SkillIndexEntry":
        """投影到 SkillIndexEntry (搜索层)"""
        from ..skills.search_engine import SkillIndexEntry as SE
        return SE(
            skill_id=self.id,
            name=self.name,
            description=self.description,
            category=self.category,
            difficulty=self.difficulty,
            tags=list(self.tags),
            author=self.author,
            version=self.version,
            source=self.source,
            source_market=self.source_market,
            source_url=self.source_url,
            source_format=self.source_format,
            usage_count=self.usage_count,
            level=self.level,
            success_rate=self.success_rate,
            last_used=self.last_used,
            prerequisites=list(self.prerequisites),
            dependencies=list(self.prerequisites),
            rating=0.0,
            trending_score=0.0,
            license=self.license,
            has_ci=False,
            verified=self.verified,
            key_concepts=list(self.key_concepts),
            reflection_questions=list(self.reflection_prompts),
        )

    def to_capabilities(self) -> List["SkillCapability"]:
        """投影到 SkillCapability 列表 (调用层)"""
        return [c.to_capability() for c in self.capabilities]

    # ═══════════════════════════════════════════════════════════
    # Reverse Bridges (专用类型 → Spec)
    # ═══════════════════════════════════════════════════════════

    @classmethod
    def from_definition(cls, sd: "SkillDefinition") -> "SkillSpec":
        """从 SkillDefinition 升级到 SkillSpec"""
        return SkillSpec(
            id=sd.name.lower().replace(" ", "-"),
            name=sd.name,
            description=sd.description,
            category=sd.category,
            difficulty=sd.difficulty,
            proficiency_weight=sd.proficiency_weight,
            stability_weight=sd.stability_weight,
            satisfaction_weight=sd.satisfaction_weight,
            responsiveness_weight=sd.responsiveness_weight,
            memory_weight=sd.memory_weight,
            prerequisites=list(sd.prerequisites),
            tools=list(sd.tools),
            practice_tasks=[dict(t) for t in sd.practice_tasks],
            success_metrics=list(sd.success_metrics),
        )

    @classmethod
    def from_package_meta(cls, pm: "SkillPackageMeta") -> "SkillSpec":
        """从 SkillPackageMeta 升级到 SkillSpec"""
        return SkillSpec(
            id=pm.name.lower().replace(" ", "-"),
            name=pm.name,
            description=pm.description,
            version=pm.version,
            zenskill_min=pm.zenskill_version,
            format_version=pm.package_format_version,
            author=pm.author,
            category=pm.category,
            difficulty=pm.difficulty,
            tags=list(pm.tags),
            source="package",
            source_market=pm.source_market,
            source_url=pm.source_url,
            source_format=pm.source_format,
            license=pm.license,
            content_hash=pm.content_hash,
            prerequisites=list(pm.dependencies),
            installed_at=pm.installed_at,
            created_at=pm.created_at,
        )

    @classmethod
    def from_index_entry(cls, ie: "SkillIndexEntry") -> "SkillSpec":
        """从 SkillIndexEntry 升级到 SkillSpec"""
        return SkillSpec(
            id=ie.skill_id,
            name=ie.name,
            description=ie.description,
            category=ie.category,
            difficulty=ie.difficulty,
            tags=list(ie.tags),
            author=ie.author,
            version=ie.version,
            source=ie.source,
            source_market=ie.source_market,
            source_url=ie.source_url,
            source_format=ie.source_format,
            license=ie.license,
            verified=ie.verified,
            usage_count=ie.usage_count,
            level=ie.level,
            success_rate=ie.success_rate,
            last_used=ie.last_used or "",
            prerequisites=list(ie.prerequisites),
            key_concepts=list(ie.key_concepts),
            reflection_prompts=list(ie.reflection_questions),
        )

    # ═══════════════════════════════════════════════════════════
    # Serialization
    # ═══════════════════════════════════════════════════════════

    def to_dict(self) -> dict:
        """转为字典（skill_type 转为字符串，capabilities 展开）"""
        d = asdict(self)
        d["skill_type"] = self.skill_type.value if isinstance(self.skill_type, SkillType) else str(self.skill_type)
        # capabilities 已通过 asdict 展开为 dict 列表
        return d

    def to_toml(self, path: str | Path) -> None:
        """写入 TOML 文件

        Args:
            path: 输出路径

        Raises:
            ImportError: 如果 tomli_w 不可用
        """
        if tomli_w is None:
            raise ImportError("tomli_w not available. Install with: pip install tomli-w")

        d = self.to_dict()

        # 分离出子表: cultivation
        cultivation_keys = {
            "level", "proficiency_weight", "stability_weight",
            "satisfaction_weight", "responsiveness_weight", "memory_weight",
            "success_rate", "usage_count", "last_used",
        }
        cultivation = {k: d.pop(k) for k in cultivation_keys if k in d}

        # 移除不需要持久化的字段
        for k in ("is_active", "created_at", "updated_at", "installed_at", "id"):
            d.pop(k, None)

        # 组装输出
        output = {
            "id": self.id,
            "name": self.name,
            # ... all flat fields from d
        }
        output.update(d)
        output["cultivation"] = cultivation

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            tomli_w.dump(output, f)
        logger.info(f"SkillSpec written to {path}")

    def to_json(self, indent: int = 2) -> str:
        """导出为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    # ═══════════════════════════════════════════════════════════
    # Validation
    # ═══════════════════════════════════════════════════════════

    def validate(self, stage: str = "define") -> List[str]:
        """按阶段校验必填字段，返回错误列表

        Args:
            stage: "define" | "package" | "install" | "search" | "invoke" | "full"

        Returns:
            错误消息列表，空列表表示通过
        """
        errors = []

        # 所有阶段: id 和 name 必填
        if not self.id:
            errors.append("[Identity] id is required")
        if not self.name:
            errors.append("[Identity] name is required")
        if self.id and " " in self.id:
            errors.append(f"[Identity] id contains spaces: '{self.id}' (use kebab-case)")

        if stage in ("define",):
            return errors

        # package 阶段: version + author
        if stage in ("package", "install", "search", "invoke", "full"):
            if not self.version:
                errors.append("[Version] version is required for packaging")
            if not self.author:
                errors.append("[Authorship] author is required for packaging")

        # install 阶段: source
        if stage in ("install", "search", "invoke", "full"):
            if self.source == "unknown":
                errors.append("[Source] source should not be 'unknown' for installation")

        # invoke 阶段: adapter + capabilities
        if stage in ("invoke", "full"):
            if not self.adapter:
                errors.append("[Runtime] adapter is required for invocation (inline/process/agent/npx)")
            if not self.capabilities:
                errors.append("[Runtime] at least one capability is required for invocation")

        return errors

    # ═══════════════════════════════════════════════════════════
    # Persistence
    # ═══════════════════════════════════════════════════════════

    def save(self) -> bool:
        """保存到 SQLite (通过 SkillDAO.upsert_spec)

        这是推荐的持久化方式。同时写入 skill.toml 到技能目录。
        """
        try:
            from .skill_dao import SkillDAO
            from .paths import get_user_data_dir

            # 全量持久化
            SkillDAO.upsert_spec(self)

            # 写入 TOML 到技能目录
            skills_dir = get_user_data_dir() / "skills" / self.id
            skills_dir.mkdir(parents=True, exist_ok=True)
            try:
                self.to_toml(skills_dir / "skill.toml")
            except ImportError:
                pass  # TOML 可选

            self.updated_at = datetime.now(timezone.utc).isoformat()[:19]
            logger.info(f"SkillSpec saved: {self.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save SkillSpec {self.id}: {e}")
            return False

    # ═══════════════════════════════════════════════════════════
    # Utility
    # ═══════════════════════════════════════════════════════════

    @property
    def is_empty(self) -> bool:
        """是否为空 SkillSpec（仅有默认值）"""
        return not self.id

    @property
    def stage(self) -> str:
        """推断当前 SkillSpec 所处的生命周期阶段"""
        if not self.id or not self.name:
            return "empty"
        if not self.version or not self.author:
            return "define"
        if self.source == "unknown":
            return "package"
        if not self.adapter or not self.capabilities:
            return "install"
        return "invoke"

    def __repr__(self) -> str:
        return f"SkillSpec(id='{self.id}', name='{self.name}', stage='{self.stage}')"

    def __str__(self) -> str:
        caps = len(self.capabilities)
        return f"{self.icon} {self.name} ({self.id}) v{self.version} [{self.stage}] · {caps} capabilities"
