#!/usr/bin/env python3
"""ZenSkill 技能图谱 Pages 刷新脚本（Pages python3 runtime）。

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
_FALLBACK_BROWSE_LIMIT = 700
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
    """registry 工具拼装弱图：节点来自 skill_browse（全量技能），
    边为同 category 两两共现弱关联"""
    browse = _call_tool("skill_browse", {"limit": _FALLBACK_BROWSE_LIMIT})
    dashboard = _call_tool("growth_dashboard")

    # 从 growth_dashboard 取 usage/level/five_dims 补充信息
    growth_info: dict[str, dict] = {}
    for s in (dashboard or {}).get("skills") or []:
        if isinstance(s, dict) and s.get("skill_id"):
            growth_info[s["skill_id"]] = {
                "level": s.get("level") or "NOVICE",
                "usage": _usage_int(s.get("usage_count")),
                "five_dims": s.get("scores") or {},
            }

    nodes = []
    for cat in (browse or {}).get("categories") or []:
        if not isinstance(cat, dict):
            continue
        for s in cat.get("skills") or []:
            if not isinstance(s, dict) or not s.get("skill_id"):
                continue
            gid = growth_info.get(s["skill_id"], {})
            node = {
                "id": s["skill_id"],
                "name": s.get("name") or s["skill_id"],
                "level": gid.get("level") or "NOVICE",
                "category": s.get("category") or "general",
                "usage": gid.get("usage", _usage_int(s.get("usage_count"))),
            }
            five = gid.get("five_dims")
            if five:
                node["five_dims"] = five
            # 从 SKILL.md frontmatter 读取 tags（edge 生成需要）
            skill_dir = Path.home() / ".agents" / "skills" / s["skill_id"]
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                try:
                    import re as _re
                    content = skill_md.read_text(encoding="utf-8")
                    fm_m = _re.match(r"^---\s*\n(.*?)\n---", content, _re.DOTALL)
                    if fm_m:
                        import yaml as _yaml
                        raw = _yaml.safe_load(fm_m.group(1))
                        if isinstance(raw, dict):
                            tags = raw.get("tags") or []
                            if tags:
                                node["tags"] = [str(t) for t in tags]
                except Exception:
                    pass
            # 从 MetricsStore 读取 five_dims（如果有使用历史）
            if not node.get("five_dims"):
                try:
                    from zenskill.systems.visualization.metrics_store import MetricsStore
                    ms = MetricsStore(s["skill_id"])
                    if ms.history_file.exists():
                        lines = ms.history_file.read_text().strip().split("\n")
                        if lines:
                            last = json.loads(lines[-1])
                            scores = last.get("ability_scores", {})
                            if scores:
                                node["five_dims"] = {
                                    "proficiency": scores.get("proficiency", 0),
                                    "stability": scores.get("stability", 0),
                                    "satisfaction": scores.get("satisfaction", 0),
                                    "responsiveness": scores.get("responsiveness", 0),
                                    "memory": scores.get("memory", 0),
                                }
                except Exception:
                    pass
            nodes.append(node)

    # 边生成：基于 tag 共享 + category 同域（替代纯共现噪声）
    # 1) 同域内 usage>0 的技能两两弱连接（strength=0.15）
    # 2) 跨域：共享 ≥2 个 tag 的技能强连接（strength=0.3）
    # 3) 上限：每节点最多 15 条边，全局最多 500 条
    by_category: dict[str, list[str]] = {}
    tag_index: dict[str, set[str]] = {}  # tag → set of skill_ids
    for n in nodes:
        cat = n["category"]
        by_category.setdefault(cat, []).append(n["id"])
        # 从 meta 中提取 tags（如果有）
        for t in (n.get("tags") or []):
            tag_index.setdefault(t, set()).add(n["id"])

    edges: list[dict] = []
    edge_set: set[tuple[str, str]] = set()
    per_node: dict[str, int] = {}

    def _add_edge(a: str, b: str, etype: str, strength: float):
        key = tuple(sorted([a, b]))
        if key in edge_set:
            return
        if per_node.get(a, 0) >= 15 or per_node.get(b, 0) >= 15:
            return
        if len(edges) >= 500:
            return
        edge_set.add(key)
        per_node[a] = per_node.get(a, 0) + 1
        per_node[b] = per_node.get(b, 0) + 1
        edges.append({"from": a, "to": b, "type": etype, "strength": round(strength, 3)})

    # 同域弱连接
    for members in by_category.values():
        active = [m for m in members if any(n["id"] == m and n.get("usage", 0) > 0 for n in nodes)]
        for i in range(len(active)):
            for j in range(i + 1, min(len(active), i + 8)):
                _add_edge(active[i], active[j], "same_domain", 0.15)

    # tag 共享强连接
    for tag, skill_ids in tag_index.items():
        ids = list(skill_ids)
        for i in range(len(ids)):
            for j in range(i + 1, min(len(ids), i + 5)):
                _add_edge(ids[i], ids[j], "shared_tag", 0.3)

    return {"nodes": nodes, "edges": edges, "source": "fallback"}


# ============================================================
# 治理字段增补（B4）：governance 表只读 SELECT，缺失即默认值
# ============================================================

def _governance_rows() -> dict:
    """只读 SELECT skill_governance 全表 → slug -> 治理字段 dict。

    经 skill_governance._default_db() 解析数据库（测试可 monkeypatch）；
    只读 SELECT，不 import 任何写函数。表不存在/库不可达返回 {}，
    调用方按 active/T2/-1 兜底。
    """
    from zenskill.skills.skill_governance import _default_db

    with _default_db().connect() as conn:
        rows = conn.execute(
            "SELECT slug, state, tier, quality_score, last_used_at "
            "FROM skill_governance"
        ).fetchall()
    out: dict = {}
    for r in rows:
        try:
            quality = int(r["quality_score"])
        except (TypeError, ValueError):
            quality = -1
        out[str(r["slug"])] = {
            "state": str(r["state"] or ""),
            "tier": str(r["tier"] or ""),
            "quality_score": quality,
            "last_used_at": str(r["last_used_at"] or ""),
        }
    return out


def _apply_governance(nodes: list) -> None:
    """节点 payload 增补治理字段 tier/state/quality_score/last_used_at。

    全程 try/except 包裹：治理数据缺失（表未建/库不可达/行缺失）只降级
    为默认值（active/T2/quality -1/空时间），绝不让快照生成失败。
    """
    try:
        rows = _governance_rows()
    except Exception as exc:  # noqa: BLE001 — 治理数据缺失必须兜底
        logger.info("governance table unavailable, nodes use defaults: %s", exc)
        rows = {}
    for node in nodes:
        try:
            row = rows.get(str(node.get("id") or "")) or {}
            node["state"] = str(row.get("state") or "active")
            node["tier"] = str(row.get("tier") or "T2")
            try:
                node["quality_score"] = int(row.get("quality_score", -1))
            except (TypeError, ValueError):
                node["quality_score"] = -1
            node["last_used_at"] = str(row.get("last_used_at") or "")
        except Exception as exc:  # noqa: BLE001 — 单节点失败不影响整体
            logger.warning("governance enrich failed for %s: %s",
                           node.get("id"), exc)


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

    # 治理字段增补：失败不影响快照产出（内部已全量兜底，此处再兜一层）
    try:
        _apply_governance(nodes)
    except Exception as exc:  # noqa: BLE001 — 治理数据缺失必须兜底
        logger.warning("governance enrichment skipped: %s", exc)

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
