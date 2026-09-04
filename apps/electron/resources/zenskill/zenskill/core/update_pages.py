"""Pages 页面包播种机制（craft Pages 系统）。

见 docs/repo_management_and_gui_plan_v3.md 1.4 节：把主仓库
zenskill/resources/pages/{slug}/ 播种到 {workspace_root}/pages/{slug}/，
供 craft 宿主按 PageConfig（page.json）加载渲染与 cron 刷新。

规则（与 update_guide.py 同一批 workspace 播种先例保持一致）：
- 命名空间隔离：只管理 ``zenskill-`` 前缀 slug，幂等覆盖；
  用户自建页面（非该前缀）绝不触碰
- 升级：覆盖 zenskill- 页面时保留用户在 page.json 里关闭的
  refresh.enabled=false 开关
- 写入顺序：index.html / scripts/ 先落盘，page.json 最后写
  （craft 约定：page.json 是刷新完成标记，watcher 以它触发 pages:changed）
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# 系统管理命名空间：仅播种/覆盖该前缀的 slug
MANAGED_SLUG_PREFIX = "zenskill-"

# 播种文件类型：全部按 UTF-8 文本处理（Pages 包只含 json/html/py）
_ENCODING = "utf-8"


def _pages_resource_dir() -> Path:
    """定位主仓库 Pages 资源目录（打包/开发双模式兼容）。

    打包模式：zenskill 作为 wheel 安装时 resources 随包携带，
    优先走 importlib.resources；开发模式回退到仓库相对路径。
    """
    try:
        from importlib import resources

        packaged = resources.files("zenskill") / "resources" / "pages"
        packaged_path = Path(str(packaged))
        if packaged_path.is_dir():
            return packaged_path
    except Exception:  # noqa: BLE001 — 未打包/无 resources 时走开发路径
        pass
    return Path(__file__).resolve().parent.parent / "resources" / "pages"


def _atomic_write_text(path: Path, content: str) -> None:
    """tmp + os.replace 原子写（与 core.paths.atomic_write_text 同语义，
    独立实现避免播种路径依赖 zenskill 数据目录初始化）"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=_ENCODING) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _load_page_json(path: Path) -> dict | None:
    """防御性读取 page.json；缺失/损坏返回 None"""
    try:
        data = json.loads(path.read_text(encoding=_ENCODING))
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _is_refresh_disabled(config: dict | None) -> bool:
    """用户是否显式关闭了定时刷新（refresh.enabled === false）"""
    if not config:
        return False
    refresh = config.get("refresh")
    return isinstance(refresh, dict) and refresh.get("enabled") is False


def _seed_page(source_dir: Path, target_dir: Path) -> str:
    """播种单个页面，返回 'seeded'（有变化）或 'unchanged'（幂等命中）。

    content/scripts 先写、page.json 最后写；page.json 覆盖时
    保留目标已有且 contentDigest/lastRefresh 等宿主管理字段不动
    （直接以源为准，宿主会在下一次内容保存时重建）。
    """
    changed = False

    def _sync_file(rel: Path, content: str) -> None:
        nonlocal changed
        target = target_dir / rel
        if target.is_file() and target.read_text(encoding=_ENCODING) == content:
            return
        _atomic_write_text(target, content)
        changed = True

    # 1) 内容与脚本（page.json 之外的所有文本文件，含子目录）
    for src_file in sorted(source_dir.rglob("*")):
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(source_dir)
        if rel.parts[0] == "data":  # 运行时数据目录归刷新脚本所有，不播种
            continue
        if rel.name == "page.json":
            continue
        _sync_file(rel, src_file.read_text(encoding=_ENCODING))

    # 2) page.json 最后写（完成标记语义）
    source_config = _load_page_json(source_dir / "page.json")
    if source_config is None:
        raise ValueError(f"invalid page.json in {source_dir}")
    target_config_path = target_dir / "page.json"
    if _is_refresh_disabled(_load_page_json(target_config_path)):
        source_config.setdefault("refresh", {})["enabled"] = False
        logger.info("preserved user disabled refresh for %s", source_config.get("slug"))
    _sync_file(Path("page.json"), json.dumps(source_config, ensure_ascii=False, indent=2) + "\n")

    return "seeded" if changed else "unchanged"


def sync_pages(workspace_root: Path, source_dir: Path | None = None) -> dict:
    """把 zenskill- 前缀页面包播种到 workspace 的 pages/ 目录。

    Args:
        workspace_root: craft workspace 根目录（pages/ 的父目录）
        source_dir: 资源目录覆写（测试用）；默认 _pages_resource_dir()

    Returns:
        摘要 dict：{"workspace_root", "discovered", "seeded",
                    "unchanged", "failed"}，均为 slug 列表（failed 为
                    [{"slug", "error"}]），资源目录缺失时 discovered 为空、不报错。
    """
    workspace_root = Path(workspace_root).expanduser()
    source_dir = Path(source_dir) if source_dir else _pages_resource_dir()

    summary: dict = {
        "workspace_root": str(workspace_root),
        "discovered": [],
        "seeded": [],
        "unchanged": [],
        "failed": [],
    }

    # 资源目录缺失 / 为空：安静返回（宁缺勿滥，不抛错）
    if not source_dir.is_dir():
        logger.info("pages resource dir not found: %s", source_dir)
        return summary

    pages_root = workspace_root / "pages"
    for child in sorted(source_dir.iterdir()):
        slug = child.name
        # 命名空间隔离：非 zenskill- 前缀的目录不是我们的页面包
        if not child.is_dir() or not slug.startswith(MANAGED_SLUG_PREFIX):
            continue
        if not (child / "page.json").is_file():
            continue
        summary["discovered"].append(slug)

        target_dir = pages_root / slug
        try:
            result = _seed_page(child, target_dir)
            summary[result].append(slug)
            logger.info("pages sync %s -> %s (%s)", slug, target_dir, result)
        except Exception as exc:  # noqa: BLE001 — 单页失败不影响其他页
            summary["failed"].append({"slug": slug, "error": str(exc)})
            logger.warning("pages sync failed for %s: %s", slug, exc)

    return summary


def resolve_active_workspace_root() -> Path | None:
    """从 craft config.json 解析活跃 workspace 根目录（跟随 update_guide.py）"""
    config_path = Path.home() / ".zenskill" / "craft" / "config.json"
    try:
        cfg = json.loads(config_path.read_text(encoding=_ENCODING))
        active_id = cfg.get("activeWorkspaceId", "")
        for ws in cfg.get("workspaces", []):
            if ws.get("id") == active_id:
                return Path(ws["rootPath"]).expanduser()
    except Exception:  # noqa: BLE001 — 无配置时返回 None 由调用方兜底
        pass
    return None
