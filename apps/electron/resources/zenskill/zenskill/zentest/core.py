"""
ZenTestRunner — 统一测试入口

提供 run/run_all/quick/smoke 四种执行模式，
支持按 TestCategory 过滤、多格式报告输出。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .categories import CATEGORY_SEVERITY, TestCategory, TestSeverity


# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class TestResult:
    """单条测试结果"""
    name: str
    category: TestCategory
    passed: bool
    duration_ms: float
    error: Optional[str] = None
    details: str = ""


@dataclass
class TestReport:
    """完整测试报告"""
    results: list[TestResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000

    @property
    def success_rate(self) -> float:
        if not self.results:
            return 0.0
        return self.passed_count / self.total * 100

    def by_category(self, cat: TestCategory) -> list[TestResult]:
        return [r for r in self.results if r.category == cat]

    def failed(self) -> list[TestResult]:
        return [r for r in self.results if not r.passed]

    def summary(self) -> str:
        lines = [
            f"📊 ZenTest 报告",
            f"  总计: {self.total}  |  通过: {self.passed_count}  |  失败: {self.failed_count}",
            f"  成功率: {self.success_rate:.1f}%  |  耗时: {self.duration_ms:.0f}ms",
        ]
        if self.failed_count > 0:
            lines.append("")
            lines.append("❌ 失败列表:")
            for r in self.failed():
                lines.append(f"  - [{r.category.value}] {r.name}: {r.error or '未知错误'}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# ZenTestRunner
# ═══════════════════════════════════════════════════════════════

class ZenTestRunner:
    """ZenTest 统一测试入口"""

    # 各分类对应测试模块的导入路径
    MODULE_MAP: dict[TestCategory, str] = {
        TestCategory.E2E: "zenskill.zentest.scenarios",
        TestCategory.SKILL: "zenskill.zentest.skills",
        TestCategory.PLATFORM: "zenskill.zentest.platforms",
        TestCategory.SECURITY: "zenskill.zentest.security",
    }

    # 快速 smoke 测试包含的分类
    SMOKE_CATEGORIES: set[TestCategory] = {
        TestCategory.UNIT,
        TestCategory.INTEGRATION,
    }

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    # ── 公开入口 ──────────────────────────────────────────────

    def run(
        self,
        category: Optional[TestCategory | str] = None,
        report_format: str = "text",
    ) -> TestReport:
        """运行指定分类的测试"""
        cat = self._resolve_category(category)
        report = TestReport(start_time=time.time())
        self._run_category(cat, report)
        report.end_time = time.time()
        self._print_report(report, report_format)
        return report

    def run_all(self, report_format: str = "text") -> TestReport:
        """运行全部分类"""
        report = TestReport(start_time=time.time())
        for cat in TestCategory:
            self._run_category(cat, report)
        report.end_time = time.time()
        self._print_report(report, report_format)
        return report

    def quick(self, report_format: str = "text") -> TestReport:
        """快速验证 (<30s) — 仅 unit + integration"""
        report = TestReport(start_time=time.time())
        for cat in (TestCategory.UNIT, TestCategory.INTEGRATION):
            self._run_category(cat, report)
        report.end_time = time.time()
        self._print_report(report, report_format)
        return report

    def smoke(self, report_format: str = "text") -> TestReport:
        """烟雾测试 — 极快 (<10s)"""
        return self.quick(report_format)

    # ── 内部实现 ──────────────────────────────────────────────

    def _resolve_category(
        self, category: Optional[TestCategory | str]
    ) -> TestCategory:
        if category is None:
            return TestCategory.E2E
        if isinstance(category, str):
            return TestCategory.from_str(category)
        return category

    def _run_category(
        self, cat: TestCategory, report: TestReport
    ) -> None:
        if cat in (TestCategory.UNIT, TestCategory.INTEGRATION):
            self._run_pytest_tests(cat, report)
        else:
            self._run_scenario_tests(cat, report)

    def _run_pytest_tests(
        self, cat: TestCategory, report: TestReport
    ) -> None:
        """委托 pytest 执行现有单元/集成测试"""
        if cat == TestCategory.UNIT:
            # 运行现有 tests/ 目录下的全部测试（无 -m 过滤）
            cmd = [
                sys.executable, "-m", "pytest",
                "tests/",
                "--tb=short", "-q",
            ]
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=300
                )
                passed = result.returncode == 0
                report.results.append(TestResult(
                    name="pytest:unit",
                    category=cat,
                    passed=passed,
                    duration_ms=0.0,
                    error=None if passed else result.stderr[:500],
                    details=result.stdout,
                ))
            except subprocess.TimeoutExpired:
                report.results.append(TestResult(
                    name="pytest:unit",
                    category=cat,
                    passed=False,
                    duration_ms=300_000,
                    error="超时 (300s)",
                ))
        else:
            # integration: 不额外执行，与 unit 合并
            report.results.append(TestResult(
                name="pytest:integration",
                category=cat,
                passed=True,
                duration_ms=0.0,
                details="合并到 unit 测试",
            ))

    def _run_scenario_tests(
        self, cat: TestCategory, report: TestReport
    ) -> None:
        """运行 scenario/skill/platform/security 子模块中的测试"""
        module_path = self.MODULE_MAP.get(cat)
        if not module_path:
            return
        cmd = [
            sys.executable, "-m", "pytest",
            "-xvs",
            "--tb=short",
            module_path.replace(".", "/"),
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600
            )
            passed = result.returncode == 0
            report.results.append(TestResult(
                name=f"zentest:{cat.value}",
                category=cat,
                passed=passed,
                duration_ms=0.0,
                error=None if passed else result.stderr[:500],
                details=result.stdout,
            ))
        except subprocess.TimeoutExpired:
            report.results.append(TestResult(
                name=f"zentest:{cat.value}",
                category=cat,
                passed=False,
                duration_ms=600_000,
                error="超时 (600s)",
            ))

    def _print_report(
        self, report: TestReport, fmt: str = "text"
    ) -> None:
        if fmt == "json":
            import json
            data = {
                "total": report.total,
                "passed": report.passed_count,
                "failed": report.failed_count,
                "success_rate": round(report.success_rate, 1),
                "duration_ms": round(report.duration_ms),
                "results": [
                    {
                        "name": r.name,
                        "category": r.category.value,
                        "passed": r.passed,
                        "error": r.error,
                    }
                    for r in report.results
                ],
            }
            print(json.dumps(data, indent=2, ensure_ascii=False))
        elif fmt == "silent":
            pass
        else:
            print(report.summary())

    # ── 退出码 ────────────────────────────────────────────────

    def exit_code(self, report: TestReport) -> int:
        """根据报告决定进程退出码"""
        for r in report.results:
            cat_severity = CATEGORY_SEVERITY.get(r.category, TestSeverity.MEDIUM)
            if not r.passed and cat_severity in (
                TestSeverity.CRITICAL, TestSeverity.HIGH
            ):
                return 1
        return 0 if report.failed_count == 0 else 1
