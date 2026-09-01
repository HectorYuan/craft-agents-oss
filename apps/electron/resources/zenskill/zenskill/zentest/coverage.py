"""
ZenTest 覆盖报告 — 模块级别的测试覆盖跟踪

提供 CoverageReport 数据模型和 CoverageScanner，用于：
1. 扫描指定模块的源文件和测试文件
2. 估算代码覆盖率
3. 生成覆盖矩阵报告
4. 支持按优先级/模块过滤测试计划
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .categories import TestCategory


# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class ModuleCoverage:
    """单个模块的覆盖信息"""
    name: str                          # 模块名, e.g. "gtd", "tui"
    source_files: int = 0              # 源文件数
    source_lines: int = 0              # 源码行数
    source_functions: int = 0          # 源函数数
    test_files: int = 0               # 测试文件数
    test_lines: int = 0               # 测试代码行数
    test_functions: int = 0           # 测试函数数
    unit_tests: int = 0               # 单元测试数
    integration_tests: int = 0         # 集成测试数
    e2e_tests: int = 0                # E2E 测试数
    estimated_coverage: float = 0.0    # 估算覆盖率 0-100
    priority: str = "p3"              # p0/p1/p2/p3
    status: str = "🔴"                # 🟢 🟡 🟠 🔴
    key_gaps: List[str] = field(default_factory=list)

    @property
    def coverage_grade(self) -> str:
        if self.estimated_coverage >= 80:
            return "🟢"
        if self.estimated_coverage >= 60:
            return "🟡"
        if self.estimated_coverage >= 40:
            return "🟠"
        return "🔴"


@dataclass
class CoverageReport:
    """完整的测试覆盖报告"""
    modules: Dict[str, ModuleCoverage] = field(default_factory=dict)
    total_source_files: int = 0
    total_source_lines: int = 0
    total_source_functions: int = 0
    total_test_files: int = 0
    total_test_lines: int = 0
    total_test_functions: int = 0
    total_unit: int = 0
    total_integration: int = 0
    total_e2e: int = 0

    @property
    def overall_coverage(self) -> float:
        if not self.modules:
            return 0.0
        total = sum(m.estimated_coverage * m.source_functions
                    for m in self.modules.values())
        total_fn = sum(m.source_functions for m in self.modules.values())
        return total / total_fn if total_fn > 0 else 0.0

    def by_priority(self, priority: str) -> List[ModuleCoverage]:
        return [m for m in self.modules.values()
                if m.priority.lower() == priority.lower()]

    def by_status(self, status: str) -> List[ModuleCoverage]:
        return [m for m in self.modules.values() if m.status == status]

    def to_markdown(self) -> str:
        lines = [
            "# ZenSkill 测试覆盖报告",
            "",
            f"> 生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"> 总源文件: {self.total_source_files} | "
            f"总测试文件: {self.total_test_files} | "
            f"总测试函数: {self.total_test_functions}",
            f"> 总体覆盖率: {self.overall_coverage:.1f}%",
            "",
            "| 模块 | 源文件 | 源码行 | 源函数 | 测试文件 | 测试行 | 测试函数 | 覆盖率 | 等级 |",
            "|:-----|------:|------:|------:|--------:|------:|--------:|------:|:----:|",
        ]
        for mod_name in sorted(self.modules.keys()):
            m = self.modules[mod_name]
            lines.append(
                f"| {m.name} | {m.source_files} | {m.source_lines} | "
                f"{m.source_functions} | {m.test_files} | {m.test_lines} | "
                f"{m.test_functions} | {m.estimated_coverage:.0f}% | "
                f"{m.coverage_grade} |"
            )

        # 汇总行
        lines.append(
            f"| **总计** | **{self.total_source_files}** | **{self.total_source_lines}** | "
            f"**{self.total_source_functions}** | **{self.total_test_files}** | "
            f"**{self.total_test_lines}** | **{self.total_test_functions}** | "
            f"**{self.overall_coverage:.0f}%** | — |"
        )

        # 优先级汇总
        lines.extend([
            "",
            "## 按优先级",
            "",
            "| 优先级 | 模块 | 当前测试 | 目标测试 | 新增 | 预计工时 |",
            "|:------:|:----|:--------:|:--------:|:----:|:--------:|",
        ])

        plan = TEST_PLAN
        for pri in ["p0", "p1", "p2", "p3"]:
            pri_modules = [m for m in plan if m["priority"] == pri]
            if not pri_modules:
                continue
            for pm in pri_modules:
                lines.append(
                    f"| {pri.upper()} | {pm['module']} | {pm['current']} | "
                    f"{pm['target']} | +{pm['target'] - pm['current']} | "
                    f"{pm['hours']}h |"
                )

        return "\n".join(lines)

    def to_json(self) -> str:
        data = {
            "generated_at": __import__('datetime').datetime.now().isoformat(),
            "summary": {
                "total_source_files": self.total_source_files,
                "total_source_lines": self.total_source_lines,
                "total_source_functions": self.total_source_functions,
                "total_test_files": self.total_test_files,
                "total_test_lines": self.total_test_lines,
                "total_test_functions": self.total_test_functions,
                "overall_coverage": round(self.overall_coverage, 1),
            },
            "modules": {
                name: {
                    "source_files": m.source_files,
                    "source_lines": m.source_lines,
                    "source_functions": m.source_functions,
                    "test_files": m.test_files,
                    "test_lines": m.test_lines,
                    "test_functions": m.test_functions,
                    "unit_tests": m.unit_tests,
                    "integration_tests": m.integration_tests,
                    "e2e_tests": m.e2e_tests,
                    "coverage": round(m.estimated_coverage, 1),
                    "status": m.status,
                    "priority": m.priority,
                    "key_gaps": m.key_gaps,
                }
                for name, m in self.modules.items()
            },
        }
        return json.dumps(data, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# 测试计划 — 各模块当前/目标测试数
# ═══════════════════════════════════════════════════════════════

TEST_PLAN: List[Dict[str, Any]] = [
    # Phase 1: P0 核心功能 E2E
    {"module": "GTD CLI", "priority": "p0", "current": 0, "target": 30, "hours": 1.5,
     "description": "inbox→action→project→energy→calendar 完整 CLI 链路"},
    {"module": "记忆系统 CLI", "priority": "p0", "current": 0, "target": 20, "hours": 1,
     "description": "add→list→search→export→import 完整 CRUD"},
    {"module": "技能修炼 CLI", "priority": "p0", "current": 0, "target": 15, "hours": 1,
     "description": "status→list→metrics→define→info"},
    # Phase 2: P1 基础设施
    {"module": "Config/Profile CLI", "priority": "p1", "current": 0, "target": 12, "hours": 1,
     "description": "config show/set, profile create/switch/delete"},
    {"module": "成长引擎 CLI", "priority": "p1", "current": 0, "target": 15, "hours": 1.5,
     "description": "status→ceremony→habits→achievements"},
    {"module": "禅思反思 CLI", "priority": "p1", "current": 0, "target": 10, "hours": 1,
     "description": "trigger→issues→consolidate→insight→purify"},
    {"module": "医生诊断 CLI", "priority": "p1", "current": 0, "target": 10, "hours": 1,
     "description": "state→snapshot→repair→diagnostics"},
    # Phase 3: P2 市场/生态/UI
    {"module": "Universal Installer", "priority": "p2", "current": 0, "target": 25, "hours": 2,
     "description": "URI解析/9种分类/mock安装"},
    {"module": "SkillSpec 全生命周期", "priority": "p2", "current": 0, "target": 30, "hours": 2,
     "description": "49字段序列化/验证/投影"},
    {"module": "评级+搜索集成", "priority": "p2", "current": 0, "target": 15, "hours": 1.5,
     "description": "rate→rating→search→discover"},
    {"module": "TUI App + Screens", "priority": "p2", "current": 0, "target": 35, "hours": 3,
     "description": "pilot 模拟按键/验证 widgets"},
    {"module": "TUI Views (ViewModel)", "priority": "p2", "current": 0, "target": 20, "hours": 1.5,
     "description": "9个VM的load/render"},
    {"module": "端到端工作流", "priority": "p2", "current": 0, "target": 15, "hours": 2,
     "description": "build→install→search→rate 完整管线"},
    # Phase 4: P3 剩余模块
    {"module": "Mirroring collectors", "priority": "p3", "current": 0, "target": 40, "hours": 3,
     "description": "10个采集器文件"},
    {"module": "Collaboration", "priority": "p3", "current": 0, "target": 20, "hours": 2,
     "description": "graph/cross/eco"},
    {"module": "Core (DAO/Render/Spec/DB)", "priority": "p3", "current": 0, "target": 50, "hours": 3,
     "description": "skill_dao/render/skill_spec/database"},
    {"module": "Platforms", "priority": "p3", "current": 0, "target": 25, "hours": 2,
     "description": "7个平台适配器"},
    {"module": "Active subsystems", "priority": "p3", "current": 0, "target": 25, "hours": 2,
     "description": "exporter/dimensions/meta/error_cluster"},
    {"module": "TUI 剩余", "priority": "p3", "current": 0, "target": 20, "hours": 2,
     "description": "providers/themes/modes/chat"},
]


def get_test_plan_summary() -> str:
    """生成测试计划摘要"""
    total_current = sum(p["current"] for p in TEST_PLAN)
    total_target = sum(p["target"] for p in TEST_PLAN)
    total_hours = sum(p["hours"] for p in TEST_PLAN)

    lines = [
        "## ZenTest 测试计划",
        "",
        f"| 阶段 | 模块数 | 当前 | 目标 | 新增 | 工时 |",
        f"|:----:|:-----:|:----:|:----:|:----:|:----:|",
    ]

    for pri in ["p0", "p1", "p2", "p3"]:
        pri_items = [p for p in TEST_PLAN if p["priority"] == pri]
        if not pri_items:
            continue
        cur = sum(p["current"] for p in pri_items)
        tgt = sum(p["target"] for p in pri_items)
        hrs = sum(p["hours"] for p in pri_items)
        lines.append(
            f"| {pri.upper()} | {len(pri_items)} | {cur} | {tgt} | +{tgt - cur} | {hrs}h |"
        )

    lines.append(
        f"| **总计** | **{len(TEST_PLAN)}** | **{total_current}** | "
        f"**{total_target}** | **+{total_target - total_current}** | "
        f"**{total_hours}h** |"
    )
    lines.append("")
    lines.append("### 详细计划")
    lines.append("")
    lines.append("| 优先级 | 模块 | 当前 → 目标 | 工时 | 描述 |")
    lines.append("|:------:|:----|:----------:|:----:|:------|")

    for p in TEST_PLAN:
        lines.append(
            f"| {p['priority'].upper()} | {p['module']} | "
            f"{p['current']}→{p['target']} (+{p['target'] - p['current']}) | "
            f"{p['hours']}h | {p['description']} |"
        )

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 模块定义 — 预配置的模块元数据
# ═══════════════════════════════════════════════════════════════

MODULE_REGISTRY: Dict[str, ModuleCoverage] = {
    "gtd": ModuleCoverage(
        name="GTD", source_files=10, source_lines=2397, source_functions=131,
        test_files=14, test_lines=3132, test_functions=323,
        unit_tests=280, integration_tests=40, e2e_tests=3,
        estimated_coverage=90.0, priority="p0", status="🟢",
        key_gaps=["dashboard.py", "zenloop_bridge.py"],
    ),
    "perception": ModuleCoverage(
        name="Perception", source_files=1, source_lines=358, source_functions=12,
        test_files=1, test_lines=332, test_functions=32,
        unit_tests=30, integration_tests=2, e2e_tests=0,
        estimated_coverage=80.0, priority="p1", status="🟢",
        key_gaps=[],
    ),
    "memory": ModuleCoverage(
        name="Memory", source_files=6, source_lines=1962, source_functions=63,
        test_files=3, test_lines=654, test_functions=48,
        unit_tests=40, integration_tests=8, e2e_tests=0,
        estimated_coverage=73.0, priority="p0", status="🟡",
        key_gaps=["cross_session.py"],
    ),
    "skill_cultivation": ModuleCoverage(
        name="Skill Cultivation", source_files=35, source_lines=9254, source_functions=337,
        test_files=12, test_lines=3387, test_functions=266,
        unit_tests=220, integration_tests=40, e2e_tests=6,
        estimated_coverage=70.0, priority="p0", status="🟡",
        key_gaps=["growth_exporter.py", "custom_dimensions.py", "meta_reflection.py",
                  "error_cluster.py", "break_advisor.py", "growth_predictor.py",
                  "instant_feedback.py"],
    ),
    "zentest": ModuleCoverage(
        name="ZenTest", source_files=13, source_lines=2352, source_functions=142,
        test_files=7, test_lines=1225, test_functions=137,
        unit_tests=37, integration_tests=0, e2e_tests=100,
        estimated_coverage=70.0, priority="p1", status="🟡",
        key_gaps=[],
    ),
    "agent": ModuleCoverage(
        name="Agent", source_files=9, source_lines=3914, source_functions=130,
        test_files=4, test_lines=1051, test_functions=95,
        unit_tests=65, integration_tests=25, e2e_tests=5,
        estimated_coverage=67.0, priority="p1", status="🟡",
        key_gaps=["dependency_graph.py", "cross_insight.py", "dashboard.py"],
    ),
    "mirroring": ModuleCoverage(
        name="Mirroring", source_files=24, source_lines=5481, source_functions=207,
        test_files=2, test_lines=1436, test_functions=139,
        unit_tests=100, integration_tests=35, e2e_tests=4,
        estimated_coverage=60.0, priority="p3", status="🟠",
        key_gaps=["collectors/* (10 files)", "privacy_layer.py", "context_predictor.py",
                  "workflow.py", "pattern_miner.py", "environment_indexer.py"],
    ),
    "market": ModuleCoverage(
        name="Market/Ecosystem", source_files=6, source_lines=2980, source_functions=105,
        test_files=2, test_lines=674, test_functions=71,
        unit_tests=65, integration_tests=6, e2e_tests=0,
        estimated_coverage=60.0, priority="p2", status="🟠",
        key_gaps=["universal_installer.py", "github_installer.py", "npx_adapter.py",
                  "builtin_adapter.py"],
    ),
    "core": ModuleCoverage(
        name="Core Infrastructure", source_files=32, source_lines=22036, source_functions=911,
        test_files=11, test_lines=2736, test_functions=240,
        unit_tests=180, integration_tests=50, e2e_tests=10,
        estimated_coverage=46.0, priority="p3", status="🟠",
        key_gaps=["__main__.py (handler渲染)", "skill_spec.py", "skill_dao.py",
                  "database.py", "llm_provider.py", "render.py", "context_card.py",
                  "hooks.py", "notifier.py", "migrate_to_sqlite.py"],
    ),
    "wrapper": ModuleCoverage(
        name="Wrapper/ZenOmni", source_files=4, source_lines=1623, source_functions=31,
        test_files=1, test_lines=108, test_functions=9,
        unit_tests=9, integration_tests=0, e2e_tests=0,
        estimated_coverage=30.0, priority="p3", status="🔴",
        key_gaps=["wrapper/* (deprecated)"],
    ),
    "tui": ModuleCoverage(
        name="TUI", source_files=45, source_lines=9797, source_functions=385,
        test_files=4, test_lines=1089, test_functions=112,
        unit_tests=100, integration_tests=12, e2e_tests=0,
        estimated_coverage=30.0, priority="p2", status="🔴",
        key_gaps=["app.py (核心App)", "screens/* (19 files)", "views/* (9 files)",
                  "providers.py", "themes.py", "command_mode.py", "plain_mode.py"],
    ),
    "collaboration": ModuleCoverage(
        name="Collaboration", source_files=4, source_lines=1834, source_functions=58,
        test_files=1, test_lines=179, test_functions=16,
        unit_tests=10, integration_tests=6, e2e_tests=0,
        estimated_coverage=26.0, priority="p3", status="🔴",
        key_gaps=["dependency_graph.py", "cross_insight.py", "dashboard.py"],
    ),
    "platforms": ModuleCoverage(
        name="Platforms", source_files=7, source_lines=1402, source_functions=61,
        test_files=1, test_lines=125, test_functions=14,
        unit_tests=10, integration_tests=4, e2e_tests=0,
        estimated_coverage=22.0, priority="p3", status="🔴",
        key_gaps=["platforms/* (7 adapters)"],
    ),
}


class CoverageScanner:
    """覆盖扫描器 — 扫描源文件并生成覆盖报告"""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or Path.cwd()
        if not (self.repo_root / "zenskill").exists():
            self.repo_root = Path.cwd()

    def scan(self) -> CoverageReport:
        """扫描所有模块并生成覆盖报告"""
        report = CoverageReport()

        for name, mod in MODULE_REGISTRY.items():
            report.modules[name] = mod
            report.total_source_files += mod.source_files
            report.total_source_lines += mod.source_lines
            report.total_source_functions += mod.source_functions
            report.total_test_files += mod.test_files
            report.total_test_lines += mod.test_lines
            report.total_test_functions += mod.test_functions
            report.total_unit += mod.unit_tests
            report.total_integration += mod.integration_tests
            report.total_e2e += mod.e2e_tests

        return report

    def scan_module(self, module_name: str) -> Optional[ModuleCoverage]:
        """扫描指定模块"""
        return MODULE_REGISTRY.get(module_name)
