"""技能依赖解析器 (P2-2)

对 skill_dependencies 存储（SkillDAO）补齐求解层:
- Kahn 拓扑排序（安装顺序）
- 循环依赖检测
- 未注册（缺失）依赖报告
- semver 版本约束校验（>=, <=, >, <, =, ^, ~，逗号组合）

纯算法与 DAO 装载分离: resolve() 只吃边集合，
load_graph() 从 SQLite 取数 — 两者都可单测。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

_VERSION_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")
_CONSTRAINT_RE = re.compile(r"^(>=|<=|>|<|=|\^|~)?\s*(\d+(?:\.\d+){0,2})$")


def parse_version(version: str) -> Optional[Tuple[int, int, int]]:
    m = _VERSION_RE.match(version.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0))


def check_constraint(version: str, constraint: str) -> bool:
    """校验 version 是否满足 constraint（空约束 = 任意；非法输入宽松放行）"""
    constraint = (constraint or "").strip()
    if not constraint:
        return True

    v = parse_version(version)
    if v is None:
        return False

    for part in constraint.split(","):
        part = part.strip()
        if not part:
            continue
        m = _CONSTRAINT_RE.match(part)
        if not m:
            continue
        op, target_str = m.group(1) or "=", m.group(2)
        target = parse_version(target_str)
        if target is None:
            continue

        if op == ">=" and not v >= target:
            return False
        if op == "<=" and not v <= target:
            return False
        if op == ">" and not v > target:
            return False
        if op == "<" and not v < target:
            return False
        if op == "=" and v != target:
            return False
        if op == "^" and not (v[0] == target[0] and v >= target):
            return False
        if op == "~" and not (v[:2] == target[:2] and v >= target):
            return False
    return True


@dataclass
class ResolveResult:
    order: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    cycles: List[List[str]] = field(default_factory=list)
    conflicts: List[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.cycles and not self.conflicts


def resolve(
    edges: List[Tuple[str, str, str]],
    installed: Dict[str, str],
) -> ResolveResult:
    """求解依赖图

    Args:
        edges: (skill_id, dep_id, constraint) 三元组列表
        installed: 已注册技能 {skill_id: version}

    Returns:
        ResolveResult: 拓扑序 + 缺失 + 环 + 版本冲突
    """
    result = ResolveResult()

    nodes: set = set()
    for skill_id, dep_id, _ in edges:
        nodes.add(skill_id)
        nodes.add(dep_id)
    nodes |= set(installed.keys())

    deps_of: Dict[str, List[Tuple[str, str]]] = {n: [] for n in nodes}
    in_degree: Dict[str, int] = {n: 0 for n in nodes}
    for skill_id, dep_id, constraint in edges:
        deps_of[skill_id].append((dep_id, constraint))
        in_degree[skill_id] += 1

    # 缺失依赖
    for skill_id, dep_id, _ in edges:
        if dep_id not in installed:
            if dep_id not in result.missing:
                result.missing.append(dep_id)

    # 版本冲突（依赖已装但版本不满足约束）
    for skill_id, dep_id, constraint in edges:
        if dep_id in installed and not check_constraint(
            installed[dep_id], constraint
        ):
            result.conflicts.append({
                "skill": skill_id,
                "dep": dep_id,
                "constraint": constraint,
                "installed_version": installed[dep_id],
            })

    # Kahn 拓扑排序（依赖在前 = 安装顺序）
    queue = sorted(n for n, d in in_degree.items() if d == 0)
    dependents: Dict[str, List[str]] = {n: [] for n in nodes}
    for skill_id, dep_id, _ in edges:
        dependents[dep_id].append(skill_id)

    while queue:
        node = queue.pop(0)
        result.order.append(node)
        for child in sorted(dependents[node]):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    # 环检测: 排序后仍有入度的节点成环（沿环内依赖边走）
    cyclic = {n for n, d in in_degree.items() if d > 0}
    if cyclic:
        visited: set = set()
        for node in sorted(cyclic):
            if node in visited:
                continue
            cycle: List[str] = []
            cursor = node
            while cursor not in visited:
                visited.add(cursor)
                cycle.append(cursor)
                nxt = [dep for dep, _ in deps_of[cursor] if dep in cyclic]
                cursor = nxt[0]
            result.cycles.append(cycle)

    return result


def load_graph(
    skill_id: str,
    dao: Optional[type] = None,
) -> Tuple[List[Tuple[str, str, str]], Dict[str, str]]:
    """从 SQLite 装载 skill_id 的传递依赖闭包

    Returns:
        (edges, installed_versions)
    """
    from .skill_dao import SkillDAO

    dao = dao or SkillDAO

    edges: List[Tuple[str, str, str]] = []
    installed: Dict[str, str] = {}
    seen: set = set()
    frontier = [skill_id]

    while frontier:
        current = frontier.pop(0)
        if current in seen:
            continue
        seen.add(current)

        row = dao.get(current)
        if row:
            installed[current] = row.get("version", "0.0.0")
            for dep in dao.get_dependencies_raw(current):
                dep_id = dep.get("dep_skill_id", "")
                if dep_id:
                    edges.append((current, dep_id, dep.get("dep_version", "")))
                    frontier.append(dep_id)

    return edges, installed


def resolve_skill(skill_id: str, dao: Optional[type] = None) -> ResolveResult:
    """求解单个技能的完整依赖状态"""
    edges, installed = load_graph(skill_id, dao)
    return resolve(edges, installed)
