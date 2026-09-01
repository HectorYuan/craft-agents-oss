"""
ZenSkill 统一路径管理

实现三层数据架构 + Profile 多用户隔离：
1. 用户数据目录：~/.zenskill/profiles/{profile}/ （优先级最高，跨项目共享）
2. 全局共享目录：~/.zenskill/global/ （采集器配置、平台适配等）
3. 项目数据目录：.zenskill/ （项目内，可选）
4. 技能模板目录：platforms/*/skills/ （内置模板，只读）

Profile 机制：
- 默认 profile: "default"（向后兼容）
- 激活 profile 记录在 ~/.zenskill/active_profile
- 每个 profile 拥有独立的 states/gtd/mirroring/memory/zenloop/cultivation 等
- 全局共享数据（采集器配置等）放在 global/ 目录
"""

import json
import os
import shutil
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional

try:
    import fcntl
except ImportError:  # Windows: POSIX 文件锁不可用
    fcntl = None

# ============================================================
# Profile 管理常量
# ============================================================

DEFAULT_PROFILE = "default"
ACTIVE_PROFILE_FILE = "active_profile"
GLOBAL_DIR_NAME = "global"
PROFILES_DIR_NAME = "profiles"


# 锁超时等级
LOCK_CRITICAL = 5.0    # 关键写入：状态保存、修复、迁移
LOCK_NORMAL = 2.0      # 普通读写
LOCK_TELEMETRY = 1.0   # 遥测写入：事件采集、指标采样


@contextmanager
def file_lock(path: Path, timeout: float = LOCK_NORMAL) -> Iterator[None]:
    lock_path = Path(path).with_suffix(Path(path).suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        while True:
            if fcntl is None:
                break
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() - start >= timeout:
                    from .diagnostics import log_diagnostic
                    log_diagnostic("lock_timeout", path=str(path), timeout=timeout)
                    raise TimeoutError(f"获取文件锁超时: {lock_path}")
                time.sleep(0.05)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with open(temp_path, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
        _fsync_dir(path.parent)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def atomic_write_json(path: Path, data: Any, indent: int = 2) -> None:
    atomic_write_text(path, json.dumps(data, indent=indent, ensure_ascii=False))


def append_jsonl_unlocked(path: Path, record: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def append_jsonl_locked(path: Path, record: Any, timeout: float = LOCK_TELEMETRY) -> None:
    path = Path(path)
    with file_lock(path, timeout=timeout):
        append_jsonl_unlocked(path, record)


def rewrite_jsonl_locked(path: Path, lines: list[str], timeout: float = 5.0) -> None:
    path = Path(path)
    with file_lock(path, timeout=timeout):
        content = "\n".join(lines)
        if content:
            content += "\n"
        atomic_write_text(path, content)


def safe_child_path(base: Path, *parts: str) -> Path:
    """安全拼接 base/parts：拒绝绝对分量与父目录穿越（..），防路径注入

    用于「数据目录 + 内部 ID/文件名」的拼接场景。分量只允许普通文件名
    （不含 / .. 与空串），从构造上杜绝逃逸 base。
    """
    base = Path(base)
    for p in parts:
        if not isinstance(p, str) or not p or p in (".", ".."):
            raise ValueError(f"Unsafe path component: {p!r}")
        if "/" in p or "\\" in p or Path(p).is_absolute():
            raise ValueError(f"Unsafe path component: {p!r}")
    return base.joinpath(*parts)


# ============================================================
# Profile 激活状态管理
# ============================================================

def _get_zenskill_root() -> Path:
    """获取 ~/.zenskill/ 根目录"""
    root = Path.home() / ".zenskill"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _read_active_profile() -> str:
    """读取当前激活的 profile 名称"""
    af_path = _get_zenskill_root() / ACTIVE_PROFILE_FILE
    if af_path.exists():
        try:
            name = af_path.read_text(encoding="utf-8").strip()
            if name and _profile_exists(name):
                return name
        except (OSError, UnicodeDecodeError):
            pass
    return DEFAULT_PROFILE


def _write_active_profile(name: str) -> None:
    """写入激活的 profile 名称"""
    af_path = _get_zenskill_root() / ACTIVE_PROFILE_FILE
    af_path.write_text(name.strip(), encoding="utf-8")


def _profile_exists(name: str) -> bool:
    """检查 profile 是否存在"""
    return (_get_zenskill_root() / PROFILES_DIR_NAME / name).is_dir()


def get_active_profile() -> str:
    """
    获取当前激活的 profile 名称

    优先级：
    1. 环境变量 ZENSKILL_PROFILE
    2. ~/.zenskill/active_profile 文件
    3. 默认 "default"
    """
    env_profile = os.environ.get("ZENSKILL_PROFILE", "").strip()
    if env_profile:
        return env_profile
    return _read_active_profile()


def set_active_profile(name: str) -> None:
    """
    设置当前激活的 profile

    Args:
        name: profile 名称
    """
    _write_active_profile(name)


def get_profile_dir(profile: Optional[str] = None) -> Path:
    """
    获取指定 profile 的数据目录

    Args:
        profile: profile 名称，None 表示使用当前激活的 profile

    Returns:
        ~/.zenskill/profiles/{profile}/
    """
    name = profile if profile is not None else get_active_profile()
    profile_dir = _get_zenskill_root() / PROFILES_DIR_NAME / name
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def get_global_dir() -> Path:
    """
    获取全局共享数据目录

    用于存储跨 profile 的共享数据：采集器配置、平台适配配置等

    Returns:
        ~/.zenskill/global/
    """
    global_dir = _get_zenskill_root() / GLOBAL_DIR_NAME
    global_dir.mkdir(parents=True, exist_ok=True)
    return global_dir


def list_profiles() -> list[str]:
    """
    列出所有已存在的 profile

    Returns:
        profile 名称列表，按名称排序
    """
    profiles_root = _get_zenskill_root() / PROFILES_DIR_NAME
    if not profiles_root.is_dir():
        return []
    names = []
    for entry in profiles_root.iterdir():
        if entry.is_dir():
            names.append(entry.name)
    return sorted(names)


def create_profile(name: str) -> Path:
    """
    创建新的 profile

    Args:
        name: profile 名称（只能包含字母、数字、下划线、连字符）

    Returns:
        新 profile 的数据目录路径

    Raises:
        ValueError: 名称无效或已存在
    """
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        raise ValueError(f"Profile 名称只能包含字母、数字、下划线和连字符: {name}")
    if _profile_exists(name):
        raise ValueError(f"Profile 已存在: {name}")

    profile_dir = get_profile_dir(name)
    ensure_data_dirs(profile_dir)
    return profile_dir


def delete_profile(name: str) -> None:
    """
    删除 profile 及其所有数据

    Args:
        name: profile 名称

    Raises:
        ValueError: 不能删除 default profile 或当前激活的 profile
    """
    if name == DEFAULT_PROFILE:
        raise ValueError("不能删除 default profile")
    if name == get_active_profile():
        raise ValueError(f"不能删除当前激活的 profile: {name}。请先切换到其他 profile。")
    if not _profile_exists(name):
        raise ValueError(f"Profile 不存在: {name}")

    profile_dir = get_profile_dir(name)
    shutil.rmtree(profile_dir)


def get_user_data_dir() -> Path:
    """
    获取用户数据目录（向后兼容）

    跨项目共享，不会提交到 Git
    位置：~/.zenskill/profiles/{active_profile}/

    如需指定特定 profile，使用 get_profile_dir(profile)
    """
    return get_profile_dir()


def get_project_root() -> Optional[Path]:
    """
    自动探测项目根目录

    向上查找包含 SKILL.md 或 zenskill/ 目录的位置
    """
    cwd = Path.cwd()
    for path in [cwd, *cwd.parents]:
        if (path / "SKILL.md").exists() or (path / "zenskill").exists():
            return path
    return None


def normalize_tags(tags: Any) -> str:
    """
    统一 tags 字段类型（str/list/None → str）

    解决 episode 中 tags 字段类型不一致的问题：
    - 某些模块用 list: ["hook", "general"]
    - 某些模块用 str:  "hook,general"
    - 某些模块用 None

    Returns:
        统一后的 tags 字符串，空格分隔
    """
    if tags is None:
        return ""
    if isinstance(tags, list):
        return " ".join(str(t) for t in tags)
    return str(tags)


def get_project_data_dir() -> Optional[Path]:
    """
    获取项目内数据目录

    项目内的本地数据，可选提交
    位置：<项目根目录>/.zenskill/
    """
    root = get_project_root()
    if root:
        project_dir = root / ".zenskill"
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir
    return None


def get_skill_template_dir(skill_id: str) -> Optional[Path]:
    """
    获取技能模板目录（只读）

    位置：platforms/claude_code/skills/<skill_id>/
    """
    root = get_project_root()
    if root:
        template_dir = root / "platforms" / "claude_code" / "skills" / skill_id
        if template_dir.exists():
            return template_dir
    return None


def get_state_path(skill_id: str, autocreate: bool = True) -> Path:
    """
    获取状态文件路径

    优先级：
    1. 用户目录 ~/.zenskill/states/<skill_id>.json
    2. 项目目录 .zenskill/states/<skill_id>.json（如果存在）

    Args:
        skill_id: 技能 ID
        autocreate: 是否自动创建目录

    Returns:
        状态文件的路径（可能不存在）
    """
    # 优先用户目录
    user_dir = get_user_data_dir()
    states_dir = user_dir / "states"
    if autocreate:
        states_dir.mkdir(parents=True, exist_ok=True)
    return states_dir / f"{skill_id}.json"


def get_state_history_path(skill_id: str, autocreate: bool = True) -> Path:
    """
    获取状态历史文件路径

    Args:
        skill_id: 技能 ID
        autocreate: 是否自动创建目录

    Returns:
        历史文件路径
    """
    user_dir = get_user_data_dir()
    states_dir = user_dir / "states"
    if autocreate:
        states_dir.mkdir(parents=True, exist_ok=True)
    return states_dir / f"{skill_id}.history.jsonl"


def get_memory_dir(memory_type: str = "episodic", autocreate: bool = True) -> Path:
    """
    获取记忆存储目录

    Args:
        memory_type: 'episodic' | 'semantic' | 'working'
        autocreate: 是否自动创建目录

    Returns:
        记忆目录路径
    """
    user_dir = get_user_data_dir()
    memory_dir = user_dir / "memory" / memory_type
    if autocreate:
        memory_dir.mkdir(parents=True, exist_ok=True)
    return memory_dir


def get_zenloop_dir(autocreate: bool = True) -> Path:
    """获取禅思循环数据目录"""
    user_dir = get_user_data_dir()
    zenloop_dir = user_dir / "zenloop"
    if autocreate:
        zenloop_dir.mkdir(parents=True, exist_ok=True)
    return zenloop_dir


def get_cultivation_dir(autocreate: bool = True) -> Path:
    """获取修炼系统数据目录"""
    user_dir = get_user_data_dir()
    cultivation_dir = user_dir / "cultivation"
    if autocreate:
        cultivation_dir.mkdir(parents=True, exist_ok=True)
    return cultivation_dir


def get_metrics_dir(autocreate: bool = True) -> Path:
    """获取指标历史数据目录"""
    user_dir = get_user_data_dir()
    metrics_dir = user_dir / "metrics"
    if autocreate:
        metrics_dir.mkdir(parents=True, exist_ok=True)
    return metrics_dir


def get_mirroring_dir(autocreate: bool = True) -> Path:
    """获取用户镜像数据目录"""
    user_dir = get_user_data_dir()
    mirroring_dir = user_dir / "mirroring"
    if autocreate:
        mirroring_dir.mkdir(parents=True, exist_ok=True)
    return mirroring_dir


def get_ceremony_dir(autocreate: bool = True) -> Path:
    """获取境界突破仪式历史目录"""
    cultivation_dir = get_cultivation_dir(autocreate)
    ceremony_dir = cultivation_dir / "ceremonies"
    if autocreate:
        ceremony_dir.mkdir(parents=True, exist_ok=True)
    return ceremony_dir


def ensure_data_dirs(base_dir: Optional[Path] = None) -> None:
    """
    确保所有必要的数据目录都已创建

    Args:
        base_dir: 数据根目录，None 表示使用当前激活 profile 的目录
    """
    ud = base_dir if base_dir is not None else get_user_data_dir()
    ud.mkdir(parents=True, exist_ok=True)
    # 子系统目录 — 确保在使用前存在
    for sub in ["states", "memory/episodic", "memory/semantic", "memory/working",
                "zenloop", "cultivation", "mirroring", "metrics",
                "goals", "tasks", "insights", "graph", "meta",
                "session", "experiments", "snapshots", "growth",
                "cross_insights", "gtd", "gtd/projects"]:
        (ud / sub).mkdir(parents=True, exist_ok=True)

    # 同时确保全局目录存在
    gd = get_global_dir()
    gd.mkdir(parents=True, exist_ok=True)
    for sub in ["mirroring"]:
        (gd / sub).mkdir(parents=True, exist_ok=True)


def migrate_old_state(skill_id: str, old_state_path: Path) -> bool:
    """
    迁移旧的状态文件到新位置

    Args:
        skill_id: 技能 ID
        old_state_path: 旧的 state.json 路径

    Returns:
        是否成功迁移
    """
    if not old_state_path.exists():
        return False

    new_path = get_state_path(skill_id)

    # 如果新位置已经有文件，不覆盖
    if new_path.exists():
        return False

    # 复制文件
    shutil.copy2(old_state_path, new_path)
    return True


def get_data_layout() -> dict:
    """
    获取当前数据布局信息

    用于诊断和调试
    """
    return {
        "user_data_dir": str(get_user_data_dir()),
        "profile_root": str(get_profile_dir()),
        "active_profile": get_active_profile(),
        "all_profiles": list_profiles(),
        "global_dir": str(get_global_dir()),
        "project_data_dir": str(get_project_data_dir()) if get_project_data_dir() else None,
        "project_root": str(get_project_root()) if get_project_root() else None,
        "memory_episodic": str(get_memory_dir("episodic", autocreate=False)),
        "memory_semantic": str(get_memory_dir("semantic", autocreate=False)),
        "zenloop": str(get_zenloop_dir(autocreate=False)),
        "cultivation": str(get_cultivation_dir(autocreate=False)),
        "mirroring": str(get_mirroring_dir(autocreate=False)),
    }


class SkillStateManager:
    """
    技能状态管理器 (Phase D5A: 逐步迁移到 SQLite)

    负责从用户数据目录加载和保存技能状态
    实现三层回退：SQLite → 用户目录 → 项目目录 → 内置模板

    Deprecated: 新代码请使用 SkillProfile + SkillDAO
    """

    _db_checked: bool = False
    _db_available: bool = False

    def __init__(self, skill_id: str):
        self.skill_id = skill_id
        self.state_path = get_state_path(skill_id)
        self.history_path = get_state_history_path(skill_id)
        self.template_path = self._get_template_path()
        self.last_load_recovered = False
        self.last_load_recovery_failed = False
        if not SkillStateManager._db_checked:
            try:
                from zenskill.core.database import db as _db
                SkillStateManager._db_available = _db.table_exists("skill_registry")
            except Exception:
                SkillStateManager._db_available = False
            SkillStateManager._db_checked = True

    def _get_template_path(self) -> Optional[Path]:
        """获取模板文件路径"""
        template_dir = get_skill_template_dir(self.skill_id)
        if template_dir:
            return template_dir / "state.template.json"
        return None

    # 级别阈值（与 SkillManifest 一致）
    _LEVEL_THRESHOLDS = {0: "NOVICE", 10: "APPRENTICE", 50: "ADEPT", 200: "EXPERT", 500: "MASTER"}

    # 当前 schema 版本
    CURRENT_SCHEMA_VERSION = 1

    # 迁移注册表：{from_version: callable(state) -> state}
    _MIGRATIONS: dict[int, Any] = {
        # 0 -> 1: 初始版本化（添加 schema_version 字段）
        0: lambda s: {**s, "schema_version": 1},
    }

    @staticmethod
    def _recalc_level(usage_count: int) -> str:
        """根据 usage_count 重算级别"""
        level = "NOVICE"
        for threshold, name in sorted(SkillStateManager._LEVEL_THRESHOLDS.items()):
            if usage_count >= threshold:
                level = name
        return level

    def load(self) -> dict[str, Any]:
        """
        加载技能状态 (Phase D5A: 优先 SQLite)

        优先级：
        1. SQLite (SkillProfile) — Phase D
        2. 用户目录 ~/.zenskill/states/<skill_id>.json — 遗留
        3. 模板文件（作为初始状态）
        """
        # Phase D: 优先从 SQLite 加载
        if SkillStateManager._db_available:
            try:
                from zenskill.core.skill_profile import SkillProfile
                profile = SkillProfile.load(self.skill_id)
                if profile:
                    # 从 JSON 文件加载 episodes（SQLite 不存储 episodes）
                    json_episodes = []
                    if self.state_path.exists():
                        try:
                            with open(self.state_path, "r", encoding="utf-8") as f:
                                json_state = json.load(f)
                                json_episodes = json_state.get("episodes", [])
                        except (json.JSONDecodeError, OSError):
                            pass

                    return {
                        "schema_version": self.CURRENT_SCHEMA_VERSION,
                        "skill_id": self.skill_id,
                        "skill_name": profile.name,
                        "level": profile.level,
                        "usage_count": profile.total_interactions,
                        "success_count": profile.success_count,
                        "total_duration_ms": 0,
                        "last_used": profile.last_interaction_at,
                        "level_up_at": None,
                        "episodes": json_episodes,
                        "milestones": [],
                        "metrics": {
                            "total_executions": profile.total_interactions,
                            "successful_executions": profile.success_count,
                            "total_duration_ms": 0,
                            "avg_duration_ms": 0,
                            "success_rate": profile.success_rate,
                        },
                    }
            except Exception:
                pass

        # Fallback: 文件系统
        with file_lock(self.state_path, timeout=LOCK_CRITICAL):
            return self._load_unlocked(recover=True)

    def _load_unlocked(self, recover: bool = True) -> dict[str, Any]:
        state = None
        self.last_load_recovered = False
        self.last_load_recovery_failed = False

        if self.state_path.exists():
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
            except (json.JSONDecodeError, UnicodeDecodeError):
                if recover:
                    state = self._recover_state_unlocked()
                    if state is None:
                        self.last_load_recovery_failed = True
                    else:
                        self.last_load_recovered = True

        if state is None and self.template_path and self.template_path.exists():
            with open(self.template_path, "r", encoding="utf-8") as f:
                state = json.load(f)

        if state is None:
            state = self._default_state()

        self._normalize_level(state)
        state = self._run_migrations(state)
        return state

    def _run_migrations(self, state: dict[str, Any]) -> dict[str, Any]:
        current = state.get("schema_version", 0)
        if current >= self.CURRENT_SCHEMA_VERSION:
            return state
        for v in range(current, self.CURRENT_SCHEMA_VERSION):
            if v in self._MIGRATIONS:
                state = self._MIGRATIONS[v](state)
        state["schema_version"] = self.CURRENT_SCHEMA_VERSION
        return state

    def needs_migration(self) -> bool:
        state = self.load()
        return state.get("schema_version", 0) < self.CURRENT_SCHEMA_VERSION

    def get_migration_info(self) -> dict[str, Any]:
        # 直接读文件判断版本，避免 load() 的内存迁移干扰
        if not self.state_path.exists():
            return {
                "skill_id": self.skill_id,
                "current_version": None,
                "target_version": self.CURRENT_SCHEMA_VERSION,
                "needs_migration": False,
            }
        file_version = 0
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            file_version = raw.get("schema_version", 0)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            file_version = -1
        return {
            "skill_id": self.skill_id,
            "current_version": file_version,
            "target_version": self.CURRENT_SCHEMA_VERSION,
            "needs_migration": 0 <= file_version < self.CURRENT_SCHEMA_VERSION,
        }

    def migrate(self, dry_run: bool = False) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"skill_id": self.skill_id, "migrated": False, "reason": "no_file"}
        with file_lock(self.state_path, timeout=LOCK_CRITICAL):
            # 跳过 _run_migrations，先读原始版本
            state = self._load_unlocked(recover=True)
            # _load_unlocked 已执行 _run_migrations，但 state 中的 schema_version
            # 已被更新。从文件重新读取原始版本号。
            old_version = 0
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    old_version = json.load(f).get("schema_version", 0)
            except Exception:
                old_version = state.get("schema_version", self.CURRENT_SCHEMA_VERSION)
            if old_version >= self.CURRENT_SCHEMA_VERSION:
                return {"skill_id": self.skill_id, "migrated": False, "version": old_version}
            if not dry_run:
                self._save_unlocked(state, action="migrate", write_history=True)
                from .diagnostics import log_diagnostic
                log_diagnostic("migrate", skill_id=self.skill_id, from_version=old_version, to_version=self.CURRENT_SCHEMA_VERSION)
            return {
                "skill_id": self.skill_id,
                "migrated": not dry_run,
                "dry_run": dry_run,
                "from_version": old_version,
                "to_version": self.CURRENT_SCHEMA_VERSION,
            }

    def _default_state(self) -> dict[str, Any]:
        return {
            "schema_version": self.CURRENT_SCHEMA_VERSION,
            "skill_id": self.skill_id,
            "name": self.skill_id,
            "level": "NOVICE",
            "usage_count": 0,
            "success_count": 0,
            "total_duration_ms": 0,
            "last_used": None,
            "level_up_at": None,
            "episodes": [],
            "milestones": [],
            "metrics": {
                "total_executions": 0,
                "successful_executions": 0,
                "total_duration_ms": 0,
                "avg_duration_ms": 0,
                "success_rate": 0.0,
            },
        }

    def _normalize_level(self, state: dict[str, Any]) -> None:
        uc = state.get("usage_count", 0)
        recalculated = self._recalc_level(uc)
        if recalculated != state.get("level"):
            state["_old_level"] = state.get("level")
            state["level"] = recalculated

    def _recover_state_unlocked(self) -> Optional[dict[str, Any]]:
        try:
            raw = self.state_path.read_bytes()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup = self.state_path.with_name(f"{self.state_path.name}.corrupted.{timestamp}.{os.getpid()}")
            backup.write_bytes(raw)
            from .diagnostics import log_diagnostic
            log_diagnostic("corrupted_backup", path=str(backup), skill_id=self.skill_id, size=len(raw))
            content = raw.decode("utf-8", errors="ignore")
            decoder = json.JSONDecoder()
            obj, end = decoder.raw_decode(content)
            if not isinstance(obj, dict):
                log_diagnostic("recovery_failed", skill_id=self.skill_id, reason="root_not_dict")
                return None
            valid = content[:end]
            atomic_write_text(self.state_path, valid)
            log_diagnostic("recovery_success", skill_id=self.skill_id, recovered_bytes=len(valid), original_bytes=len(raw))
            return obj
        except Exception as e:
            from .diagnostics import log_diagnostic
            log_diagnostic("recovery_failed", skill_id=self.skill_id, error=str(e)[:100])
            return None

    def _write_history(self, action: str, delta: dict, state: dict) -> None:
        """
        写入历史记录

        Args:
            action: 操作类型
            delta: 变更内容
            state: 完整状态快照
        """
        record = {
            "version": 1,
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "delta": delta,
            "snapshot": state,
        }

        append_jsonl_locked(self.history_path, record)

    def save(self, state: dict[str, Any], action: str = "save", write_history: bool = True) -> None:
        """
        保存技能状态到用户目录

        Args:
            state: 状态字典
            action: 操作类型
            write_history: 是否写入历史记录
        """
        with file_lock(self.state_path, timeout=LOCK_CRITICAL):
            self._save_unlocked(state, action=action, write_history=write_history)

    def _save_unlocked(self, state: dict[str, Any], action: str = "save", write_history: bool = True) -> None:
        state["last_updated"] = datetime.now().isoformat()
        self._normalize_level(state)
        atomic_write_json(self.state_path, state)

        if write_history:
            self._write_history(action, {"updated": True}, state)

    def record_episode(self, action: str, content: str, success: bool = True,
                       duration_ms: float = 0) -> None:
        """
        记录一条使用事件 (Phase D5A: 双写到 SQLite + JSON)

        Args:
            action: 操作类型
            content: 内容描述
            success: 是否成功
            duration_ms: 执行时长（毫秒）
        """
        # Phase D: 同步写入 SQLite
        if SkillStateManager._db_available:
            try:
                from zenskill.core.skill_dao import SkillDAO
                SkillDAO.record_event(
                    self.skill_id, action, content,
                    success=success, duration_ms=duration_ms,
                )
            except Exception:
                pass

        # 保留 JSON 写入 (向后兼容)
        with file_lock(self.state_path, timeout=LOCK_CRITICAL):
            state = self._load_unlocked(recover=True)
            state["usage_count"] = state.get("usage_count", 0) + 1
            state["last_used"] = datetime.now().isoformat()

            metrics = state.get("metrics", {})
            metrics["total_executions"] = metrics.get("total_executions", 0) + 1
            if success:
                metrics["successful_executions"] = metrics.get("successful_executions", 0) + 1
            metrics["total_duration_ms"] = metrics.get("total_duration_ms", 0) + duration_ms

            total = metrics["total_executions"]
            success_total = metrics["successful_executions"]
            total_dur = metrics["total_duration_ms"]

            metrics["avg_duration_ms"] = total_dur / total if total > 0 else 0
            metrics["success_rate"] = success_total / total if total > 0 else 0.0

            state["metrics"] = metrics

            if "episodes" not in state:
                state["episodes"] = []

            state["episodes"].append({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "action": action,
                "content": content,
                "success": success,
                "duration_ms": duration_ms,
            })

            self._save_unlocked(state, action=action)

        self._auto_sample_metrics(state)

    def _auto_sample_metrics(self, state: dict) -> None:
        """
        自动采样指标（每 5 次交互记录一次）

        Args:
            state: 当前技能状态
        """
        usage_count = state.get("usage_count", 0)

        # 每 5 次交互采样一次
        if usage_count % 5 == 0:
            try:
                from zenskill.systems.visualization.metrics_store import MetricsStore
                store = MetricsStore(self.skill_id)
                # 检查是否已采样过
                latest = store.get_latest_snapshot()
                if latest is None or latest.interaction_count < usage_count:
                    store.record_snapshot(state)
            except Exception as e:
                # 采样失败不影响主流程
                pass

    def get_level(self) -> str:
        """获取当前境界"""
        state = self.load()
        return state.get("level", "NOVICE")

    def get_usage_count(self) -> int:
        """获取使用次数"""
        state = self.load()
        return state.get("usage_count", 0)

    def get_metrics(self) -> dict:
        """获取使用指标"""
        state = self.load()
        return state.get("metrics", {
            "total_executions": 0,
            "successful_executions": 0,
            "total_duration_ms": 0,
            "avg_duration_ms": 0,
            "success_rate": 0.0,
        })

    def get_history(self, limit: int = 10) -> list[dict]:
        """
        获取历史记录

        Args:
            limit: 获取最近 N 条

        Returns:
            历史记录列表
        """
        if not self.history_path.exists():
            return []

        records = []
        with open(self.history_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return records[-limit:]

    def rollback(self, n: int = 1) -> bool:
        """
        回滚到前 N 个版本

        Args:
            n: 回滚步数

        Returns:
            是否回滚成功
        """
        history = self.get_history(limit=n + 1)
        if len(history) <= n:
            return False

        # 获取目标版本快照
        target = history[-(n + 1)]
        if "snapshot" not in target:
            return False

        # 恢复快照
        snapshot = target["snapshot"]
        self.save(snapshot, action=f"rollback_{n}", write_history=True)
        return True

    def get_history_summary(self) -> dict:
        """获取历史记录摘要"""
        history = self.get_history(limit=1000)
        return {
            "total_versions": len(history),
            "first_version": history[0]["timestamp"] if history else None,
            "last_version": history[-1]["timestamp"] if history else None,
        }

    def record_success(self, duration_ms: float = 0) -> None:
        """记录一次成功执行"""
        self.record_episode("execute", "执行成功", success=True, duration_ms=duration_ms)

    def record_failure(self, duration_ms: float = 0) -> None:
        """记录一次失败执行"""
        self.record_episode("execute", "执行失败", success=False, duration_ms=duration_ms)

    # ── 8W+8X: 命名快照与版本控制 ──

    def list_snapshots(self, limit: int = 50) -> list[dict]:
        """列出历史快照（最新优先）"""
        history = self.get_history(limit=limit)
        result = []
        for i, record in enumerate(reversed(history)):
            snapshot = record.get("snapshot", {})
            result.append({
                "index": len(history) - 1 - i,
                "version": i + 1,
                "timestamp": record.get("timestamp", ""),
                "action": record.get("action", "save"),
                "level": snapshot.get("level", ""),
                "usage_count": snapshot.get("usage_count", 0),
                "named": record.get("snapshot_name"),
            })
        return result

    def create_named_snapshot(self, name: str) -> dict:
        """创建命名快照"""
        state = self.load()
        self.save(state, action="snapshot", write_history=True)
        # 在最新的 history 记录上打标记
        history = self.get_history(limit=1)
        if history:
            last = history[-1]
            last["snapshot_name"] = name
            # 重写最后一行
            import tempfile, shutil
            with file_lock(self.history_path):
                lines = []
                if self.history_path.exists():
                    with open(self.history_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                if lines:
                    lines[-1] = json.dumps(last, ensure_ascii=False) + "\n"
                    tmp_path = self.history_path.with_suffix(".tmp")
                    with open(tmp_path, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                    shutil.move(str(tmp_path), str(self.history_path))
                    _fsync_dir(self.history_path.parent)
            return {"ok": True, "name": name, "timestamp": last.get("timestamp")}
        return {"ok": False, "error": "no_history"}

    def restore_snapshot(self, name: str) -> dict:
        """恢复到命名快照"""
        history = self.get_history(limit=200)
        target = None
        for record in reversed(history):
            if record.get("snapshot_name") == name:
                target = record
                break
        if not target or "snapshot" not in target:
            return {"ok": False, "error": f"snapshot '{name}' not found"}
        snapshot = target["snapshot"]
        self.save(snapshot, action=f"restore_{name}", write_history=True)
        return {
            "ok": True, "name": name,
            "timestamp": target.get("timestamp"),
            "level": snapshot.get("level"),
            "usage_count": snapshot.get("usage_count"),
        }

    def diff_states(self, v1: int, v2: int) -> dict:
        """对比两个历史版本"""
        history = self.get_history(limit=max(v1, v2) + 2)
        if v1 < 0 or v2 < 0 or v1 >= len(history) or v2 >= len(history):
            return {"ok": False, "error": "version out of range", "history_len": len(history)}

        s1 = history[v1].get("snapshot", {})
        s2 = history[v2].get("snapshot", {})
        changes = {}
        all_keys = set(s1.keys()) | set(s2.keys())
        for key in sorted(all_keys):
            if key in ("survey_data", "last_updated", "last_used", "episodes", "milestones"):
                continue
            old_val = s1.get(key)
            new_val = s2.get(key)
            if old_val != new_val:
                changes[key] = {"from": old_val, "to": new_val}

        return {
            "ok": True,
            "v1": {"index": v1, "timestamp": history[v1].get("timestamp"), "action": history[v1].get("action")},
            "v2": {"index": v2, "timestamp": history[v2].get("timestamp"), "action": history[v2].get("action")},
            "changes": changes,
            "episode_diff": {
                "v1_count": len(s1.get("episodes", [])),
                "v2_count": len(s2.get("episodes", [])),
            },
        }

    # ── 8W: 分支管理 ──

    def create_branch(self, branch_name: str) -> dict:
        """基于当前状态创建学习分支"""
        import shutil
        from .paths import get_state_path
        main_path = self.state_path
        if not main_path.exists():
            return {"ok": False, "error": "no state to branch"}

        branch_path = main_path.parent / f"{self.skill_id}.{branch_name}.json"
        shutil.copy2(str(main_path), str(branch_path))
        # 标记分支元数据
        state = self.load()
        branch_meta = {
            "branch": branch_name,
            "created_at": __import__("datetime").datetime.now().isoformat(),
            "source_version": state.get("usage_count", 0),
            "source_level": state.get("level", "NOVICE"),
        }
        meta_path = main_path.parent / f"{self.skill_id}.{branch_name}.meta.json"
        atomic_write_json(meta_path, branch_meta)
        return {"ok": True, "branch": branch_name, "path": str(branch_path), "meta": branch_meta}

    @staticmethod
    def list_branches(skill_id: str) -> list[dict]:
        """列出技能的所有分支"""
        from .paths import get_user_data_dir
        states_dir = get_user_data_dir() / "states"
        branches = []
        for f in sorted(states_dir.glob(f"{skill_id}.*.json")):
            name = f.stem
            if ".meta" in name or ".history" in name:
                continue
            branch_name = name.replace(f"{skill_id}.", "")
            meta_path = states_dir / f"{skill_id}.{branch_name}.meta.json"
            meta = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                except Exception:
                    pass
            branches.append({
                "branch": branch_name,
                "path": str(f),
                "size": f.stat().st_size,
                "created_at": meta.get("created_at", ""),
                "source_level": meta.get("source_level", ""),
            })
        return branches


# ============================================================
# Profile 数据迁移
# ============================================================

def migrate_to_profile_structure(dry_run: bool = False, backup: bool = True) -> dict:
    """
    将旧版扁平结构 (~/.zenskill/*) 迁移到新的 Profile 结构

    迁移逻辑：
    1. 备份：将当前 ~/.zenskill/ 数据完整备份
    2. 将 states/memory/zenloop/cultivation/... 等数据目录
       移动到 ~/.zenskill/profiles/default/
    3. 保留 global/ 目录用于跨 profile 共享
    4. 设置 default 为激活 profile
    5. 验证完整性

    Args:
        dry_run: 仅预览，不实际执行
        backup: 是否在迁移前创建备份

    Returns:
        {"migrated": bool, "dry_run": bool, "backup_path": str, "details": dict}
    """
    root = _get_zenskill_root()
    profiles_root = root / PROFILES_DIR_NAME
    default_profile_dir = profiles_root / DEFAULT_PROFILE
    global_dir = root / GLOBAL_DIR_NAME

    # 如果已经迁移过，跳过
    if default_profile_dir.exists() and any(default_profile_dir.iterdir()):
        return {
            "migrated": False,
            "dry_run": dry_run,
            "reason": "already_migrated",
            "profile_dir": str(default_profile_dir),
        }

    # 收集用户数据子目录（这些需要迁移到 profile 下）
    user_subs = {
        "states", "memory", "zenloop", "cultivation", "mirroring",
        "metrics", "goals", "tasks", "insights", "graph", "meta",
        "session", "experiments", "snapshots", "growth",
        "cross_insights", "gtd",
    }

    # 收集全局数据子目录（这些不需要迁移，留在原地）
    global_subs = {"global"}

    # 收集需要忽略的文件
    ignore_files = {ACTIVE_PROFILE_FILE}

    # 扫描并分类
    to_migrate = []
    to_skip = []
    for entry in root.iterdir():
        if entry.name in ignore_files:
            continue
        if entry.name == PROFILES_DIR_NAME:
            # profiles 目录本身
            entries = list(entry.iterdir())
            if any(e.name == DEFAULT_PROFILE for e in entries):
                continue
            to_skip.append(("profiles_dir", str(entry)))
        elif entry.name in user_subs:
            to_migrate.append(("user_data", entry.name, str(entry)))
        elif entry.name in global_subs:
            to_skip.append(("global_data", entry.name, str(entry)))
        elif entry.is_dir():
            # 未知目录，也迁移
            to_migrate.append(("user_data", entry.name, str(entry)))
        else:
            to_skip.append(("root_file", entry.name, str(entry)))

    result = {
        "migrated": False,
        "dry_run": dry_run,
        "backup_path": None,
        "to_migrate": [{"type": t, "name": n, "path": p} for t, n, p in to_migrate],
        "to_skip": [{"type": t, "name": n, "path": p} for t, n, p in to_skip],
        "details": {},
    }

    if not to_migrate:
        result["reason"] = "nothing_to_migrate"
        return result

    if dry_run:
        return result

    # 创建备份
    if backup:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = root.parent / f".zenskill.backup.{timestamp}"
        try:
            # 排除 profiles 目录本身避免循环
            shutil.copytree(
                root, backup_path,
                ignore=shutil.ignore_patterns(PROFILES_DIR_NAME, ".lock", "*.tmp"),
                dirs_exist_ok=True,
            )
            result["backup_path"] = str(backup_path)
        except Exception as e:
            result["error"] = f"备份失败: {e}"
            return result

    # 执行迁移
    migrated_count = 0
    for item_type, name, src_path in to_migrate:
        src = Path(src_path)
        dst = default_profile_dir / name
        try:
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            migrated_count += 1
            result["details"][name] = "ok"
        except Exception as e:
            result["details"][name] = f"error: {e}"

    # 创建 profile 的额外子目录
    ensure_data_dirs(default_profile_dir)

    # 设置激活 profile
    _write_active_profile(DEFAULT_PROFILE)

    result["migrated"] = True
    result["migrated_count"] = migrated_count
    result["profile"] = DEFAULT_PROFILE
    result["profile_dir"] = str(default_profile_dir)

    return result

