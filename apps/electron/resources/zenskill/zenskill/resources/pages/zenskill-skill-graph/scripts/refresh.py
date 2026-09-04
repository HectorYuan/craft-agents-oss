#!/usr/bin/env python3
"""ZenSkill 技能图谱 Pages 刷新脚本（craft Pages python3 runtime）。

由宿主 cron（page.json refresh spec，每日 04:00）调度执行，数据获取两级策略：
- 第一级（engine）：进程内直接 import 依赖图引擎
  ``zenskill.systems.collaboration.dependency_graph.SkillDependencyGraph``
  （无参构造即自动从 ~/.zenskill/graph/ 加载），节点取 skill_id/name/
  level/category/interaction_count，边取 from_skill/to_skill/relation_type/
  strength 原始关系；节点为空视为图未建立
- 第二级（fallback）：引擎不可用/图为空时，经 registry 双层降级链路
  （进程内 build_default_registry().call() → 子进程重试）取
  growth_dashboard（每技能节点）+ skill_browse（补 name/category），
  边用同 category 两两共现生成弱关联（type=co_occurrence，固定低强度）
- 组装 PageDataSnapshot（version 1，kv；series 本页无时间序列，恒为空）写入
  pages/{slug}/data/snapshot.json（tmp + os.replace 原子写）

snapshot 是唯一跨进程数据契约；本脚本只写 data/ 目录，
绝不触碰 page.json / index.html（page.json 由宿主作为完成标记写）。
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

logger = logging.getLogger("zenskill.pages.skill_graph.refresh")

# 页面目录：{workspace_root}/pages/{slug}/（脚本被播种到 scripts/ 子目录）
PAGE_DIR = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = PAGE_DIR / "data" / "snapshot.json"

# fallback 时 skill_browse 每分类返回上限（取足够大以覆盖全部技能）
_FALLBACK_BROWSE_LIMIT = 100
# fallback 共现弱关联的固定强度（远低于引擎阈值 0.3，仅作布局连线）
_FALLBACK_EDGE_STRENGTH = 0.2

# 工具调用超时（秒）——refresh spec 的 timeoutMs（60s）之内必须完成
_TOOL_TIMEOUT_S = 30.0

_SUBPROCESS_SNIPPET = (
    "import json, sys; "
    "from zenskill.runtime.mcp.registry import build_default_registry; "
    "print(build_default_registry().call(sys.argv[1], json.loads(sys.argv[2])))"
)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _call_tool_inprocess(name: str, args: dict) -> dict:
    """进程内调用 ZenSkill 工具（与 MCP server 同一 registry）"""
    from zenskill.runtime.mcp.registry import build_default_registry

    registry = build_default_registry()
    if not registry.has(name):
        raise RuntimeError(f"tool not registered: {name}")
    return json.loads(registry.call(name, args))


def _call_tool_subprocess(name: str, args: dict) -> dict:
    """降级第二层：当前解释器 import 失败时换子进程再试一次。

    说明：zen. CLI 目前没有 growth_dashboard 等只读工具的子命令面，
    这里直接复用 registry 调用面（sys.executable 与本脚本同解释器）。
    """
    proc = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_SNIPPET, name, json.dumps(args or {})],
        capture_output=True,
        text=True,
        timeout=_TOOL_TIMEOUT_S,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"subprocess exit {proc.returncode}: {proc.stderr.strip()[:200]}")
    return json.loads(proc.stdout)


def _call_tool(name: str, args: dict | None = None) -> dict | None:
    """防御性工具调用：两层链路任选其一，全失败返回 None（字段级降级）"""
    args = args or {}
    for attempt, caller in enumerate((_call_tool_inprocess, _call_tool_subprocess), start=1):
        try:
            result = caller(name, args)
            return result if isinstance(result, dict) else None
        except Exception as exc:  # noqa: BLE001 — 任何失败都降级为缺数据
            logger.warning("tool %s attempt %d failed: %s", name, attempt, exc)
    return None


# ============================================================
# 第一级：引擎直采（与 registry 同进程 import）
# ============================================================

def _strength_01(raw) -> float:
    """边强度 clamp 0-1（引擎语义：越接近 1 越强）"""
    try:
        return round(min(max(float(raw or 0), 0.0), 1.0), 3)
    except (TypeError, ValueError):
        return 0.0


def _usage_int(raw) -> int:
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


def _engine_graph() -> dict | None:
    """直接 import SkillDependencyGraph 取节点与边；图未建立（无节点）返回 None"""
    try:
        from zenskill.systems.collaboration.dependency_graph import SkillDependencyGraph

        graph = SkillDependencyGraph()
        nodes = []
        for node in graph.get_all_skills():
            if not node.skill_id:
                continue
            nodes.append({
                "id": node.skill_id,
                "name": node.name or node.skill_id,
                "level": node.level or "NOVICE",
                "category": node.category or "general",
                "usage": _usage_int(node.interaction_count),
            })
        if not nodes:
            logger.info("dependency graph has no nodes yet; falling back")
            return None
        edges = [
            {
                "from": rel.from_skill,
                "to": rel.to_skill,
                "type": rel.relation_type or "co_occurrence",
                "strength": _strength_01(rel.strength),
            }
            for rel in graph.relations
            if rel.from_skill and rel.to_skill
        ]
        return {"nodes": nodes, "edges": edges, "source": "engine"}
    except Exception as exc:  # noqa: BLE001 — 引擎不可用即走 fallback
        logger.warning("dependency graph engine unavailable: %s", exc)
        return None


# ============================================================
# 第二级：registry 降级（growth_dashboard + skill_browse + 同分类共现）
# ============================================================

def _fallback_graph() -> dict:
    """registry 工具拼装弱图：节点来自 growth_dashboard，分类/名称来自
    skill_browse，边为同 category 两两共现弱关联（节点可能不全，尽力而为）"""
    dashboard = _call_tool("growth_dashboard")
    browse = _call_tool("skill_browse", {"limit": _FALLBACK_BROWSE_LIMIT})

    meta: dict[str, dict] = {}
    for cat in (browse or {}).get("categories") or []:
        if not isinstance(cat, dict):
            continue
        for s in cat.get("skills") or []:
            if isinstance(s, dict) and s.get("skill_id"):
                meta[s["skill_id"]] = {
                    "name": s.get("name") or s["skill_id"],
                    "category": s.get("category") or "general",
                }

    nodes = []
    for s in (dashboard or {}).get("skills") or []:
        if not isinstance(s, dict) or not s.get("skill_id"):
            continue
        info = meta.get(s["skill_id"]) or {}
        nodes.append({
            "id": s["skill_id"],
            "name": info.get("name") or s["skill_id"],
            "level": s.get("level") or "NOVICE",
            "category": info.get("category") or "general",
            "usage": _usage_int(s.get("usage_count")),
        })

    by_category: dict[str, list[str]] = {}
    for n in nodes:
        by_category.setdefault(n["category"], []).append(n["id"])
    edges = []
    for members in by_category.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                edges.append({
                    "from": members[i],
                    "to": members[j],
                    "type": "co_occurrence",
                    "strength": _FALLBACK_EDGE_STRENGTH,
                })
    return {"nodes": nodes, "edges": edges, "source": "fallback"}


# ============================================================
# snapshot 原子写
# ============================================================

def _atomic_write_json(path: Path, data: dict) -> None:
    """tmp + os.replace 原子写（不依赖 zenskill 包，降级路径也可用）"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def build_snapshot() -> dict:
    """收集数据并组装 PageDataSnapshot（两级策略，必产出一个合法快照）"""
    graph = _engine_graph() or _fallback_graph()
    nodes = graph["nodes"]
    edges = graph["edges"]

    now_ms = int(time.time() * 1000)
    kv = {
        "nodes": nodes,
        "edges": edges,
        "stats": {"node_count": len(nodes), "edge_count": len(edges)},
        "source": graph["source"],
        "generated_at": now_ms,
    }
    return {
        "version": 1,
        "generatedAt": now_ms,
        "kv": kv,
        "series": {},
    }


def main() -> int:
    _setup_logging()
    try:
        snapshot = build_snapshot()
        _atomic_write_json(SNAPSHOT_PATH, snapshot)
        logger.info("snapshot written: %s", SNAPSHOT_PATH)
        return 0
    except Exception as exc:  # noqa: BLE001 — 刷新失败必须让宿主感知
        logger.exception("refresh failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
