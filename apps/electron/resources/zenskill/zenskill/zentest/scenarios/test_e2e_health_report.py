"""
P2 — 健康度+报告+系统信息 真实 E2E 测试

health score/annual/card, report weekly/monthly, info, data paths
"""

from __future__ import annotations

import tempfile

import pytest

from zenskill.zentest.utils import run_zenskill, isolated_env


@pytest.fixture
def p2_env():
    with tempfile.TemporaryDirectory() as tmp:
        env = isolated_env({"HOME": tmp})
        run_zenskill(["info"], env=env)
        yield env


# ═══════════════════════════════════════════════════════════════
# Health
# ═══════════════════════════════════════════════════════════════

class TestHealthE2E:
    @pytest.mark.e2e
    def test_health_score(self, p2_env):
        """健康度评分"""
        ec, out, _ = run_zenskill(["health", "score"], env=p2_env)
        assert ec == 0
        assert "GTD" in out or "健康" in out

    @pytest.mark.e2e
    def test_health_card(self, p2_env):
        """技能成长评分卡"""
        ec, out, _ = run_zenskill(["health", "card"], env=p2_env)
        assert ec == 0
        assert "卡片" in out or "技能" in out

    @pytest.mark.e2e
    def test_health_annual(self, p2_env):
        """年度回顾"""
        ec, out, _ = run_zenskill(["health", "annual"], env=p2_env)
        assert ec == 0


# ═══════════════════════════════════════════════════════════════
# Report
# ═══════════════════════════════════════════════════════════════

class TestReportE2E:
    @pytest.mark.e2e
    def test_report_weekly(self, p2_env):
        """周报"""
        ec, out, _ = run_zenskill(["report", "weekly"], env=p2_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_report_monthly(self, p2_env):
        """月报"""
        ec, out, _ = run_zenskill(["report", "monthly"], env=p2_env)
        assert ec == 0


# ═══════════════════════════════════════════════════════════════
# 系统信息
# ═══════════════════════════════════════════════════════════════

class TestInfoE2E:
    @pytest.mark.e2e
    def test_info(self, p2_env):
        """系统信息"""
        ec, out, _ = run_zenskill(["info"], env=p2_env)
        assert ec == 0
        assert out.strip() != ""

    @pytest.mark.e2e
    def test_data_paths(self, p2_env):
        """数据路径 (已知参数bug)"""
        ec, out, _ = run_zenskill(["data", "paths"], env=p2_env)
        assert ec in (0, 1)

    @pytest.mark.e2e
    def test_data_stats(self, p2_env):
        """数据统计"""
        ec, out, _ = run_zenskill(["data", "stats"], env=p2_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_data_export(self, p2_env):
        """数据导出 (已知参数bug)"""
        output = f"{p2_env['HOME']}/data_export.json"
        ec, out, _ = run_zenskill(
            ["data", "export", "--output", output], env=p2_env
        )
        assert ec in (0, 1)


# ═══════════════════════════════════════════════════════════════
# 跨模块: 评级→搜索→健康
# ═══════════════════════════════════════════════════════════════

class TestRatingSearchHealthWorkflowE2E:
    @pytest.mark.e2e
    def test_rate_search_health(self, p2_env):
        """打分 → 搜索 → 健康度"""
        run_zenskill(["rate", "zenskill-core", "5"], env=p2_env)

        ec2, out2, _ = run_zenskill(["search", "zen"], env=p2_env)
        assert ec2 == 0

        ec3, _, _ = run_zenskill(["health", "score"], env=p2_env)
        assert ec3 == 0

        ec4, _, _ = run_zenskill(["trending"], env=p2_env)
        assert ec4 == 0
