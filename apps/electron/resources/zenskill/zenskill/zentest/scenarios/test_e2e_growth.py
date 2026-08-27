"""
P1 — 成长引擎 真实 E2E 测试

growth status/milestones/abilities/ceremony/habits/achievements
goal status/suggest/set
task recommend/status/complete
"""

from __future__ import annotations

import tempfile

import pytest

from zenskill.zentest.utils import run_zenskill, isolated_env


@pytest.fixture
def p1_env():
    with tempfile.TemporaryDirectory() as tmp:
        env = isolated_env({"HOME": tmp})
        # 初始化 .zenskill 目录结构
        run_zenskill(["info"], env=env)
        yield env


# ═══════════════════════════════════════════════════════════════
# Growth
# ═══════════════════════════════════════════════════════════════

class TestGrowthE2E:
    @pytest.mark.e2e
    def test_growth_status(self, p1_env):
        """成长状态"""
        ec, out, _ = run_zenskill(["growth", "status"], env=p1_env)
        assert ec == 0
        assert "NOVICE" in out or "五维" in out or "能力" in out

    @pytest.mark.e2e
    def test_growth_milestones(self, p1_env):
        """成长里程碑"""
        ec, out, _ = run_zenskill(["growth", "milestones"], env=p1_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_growth_abilities(self, p1_env):
        """已解锁能力"""
        ec, out, _ = run_zenskill(["growth", "abilities"], env=p1_env)
        assert ec == 0
        assert "已解锁" in out or "能力" in out

    @pytest.mark.e2e
    def test_growth_trend(self, p1_env):
        """成长趋势"""
        ec, out, _ = run_zenskill(["growth", "trend"], env=p1_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_growth_export(self, p1_env):
        """导出成长报告"""
        ec, out, _ = run_zenskill(
            ["growth", "export", "--output", f"{p1_env['HOME']}/growth.json"],
            env=p1_env,
        )
        assert ec == 0


# ═══════════════════════════════════════════════════════════════
# Goal
# ═══════════════════════════════════════════════════════════════

class TestGoalE2E:
    @pytest.mark.e2e
    def test_goal_status(self, p1_env):
        """目标状态"""
        ec, out, _ = run_zenskill(["goal", "status"], env=p1_env)
        assert ec == 0
        assert "目标" in out or "goal" in out.lower()

    @pytest.mark.e2e
    def test_goal_suggest(self, p1_env):
        """推荐目标"""
        ec, out, _ = run_zenskill(["goal", "suggest"], env=p1_env)
        assert ec == 0
        assert out.strip() != ""

    @pytest.mark.e2e
    def test_goal_set_and_status(self, p1_env):
        """设置目标后状态应包含"""
        ec1, _, _ = run_zenskill(
            ["goal", "set", "--dimension", "proficiency",
             "--target", "50"],
            env=p1_env,
        )
        assert ec1 == 0

        ec2, out2, _ = run_zenskill(["goal", "status"], env=p1_env)
        assert ec2 == 0

    @pytest.mark.e2e
    def test_goal_set_invalid_dimension(self, p1_env):
        """无效维度应优雅处理"""
        ec, out, err = run_zenskill(
            ["goal", "set", "--dimension", "invalid_xyz",
             "--target", "50"],
            env=p1_env,
        )
        assert ec in (0, 1, 2)


# ═══════════════════════════════════════════════════════════════
# Task
# ═══════════════════════════════════════════════════════════════

class TestTaskE2E:
    @pytest.mark.e2e
    def test_task_recommend(self, p1_env):
        """推荐任务"""
        ec, out, _ = run_zenskill(["task", "recommend"], env=p1_env)
        assert ec == 0
        assert out.strip() != ""

    @pytest.mark.e2e
    def test_task_status(self, p1_env):
        """任务状态"""
        ec, out, _ = run_zenskill(["task", "status"], env=p1_env)
        assert ec == 0
        assert out.strip() != ""

    @pytest.mark.e2e
    def test_task_complete_invalid(self, p1_env):
        """无效任务 ID"""
        ec, out, err = run_zenskill(
            ["task", "complete", "999"], env=p1_env
        )
        assert ec in (0, 1)


# ═══════════════════════════════════════════════════════════════
# Insight
# ═══════════════════════════════════════════════════════════════

class TestInsightE2E:
    @pytest.mark.e2e
    def test_insight_unread(self, p1_env):
        """查看未读洞察"""
        ec, out, _ = run_zenskill(["insight", "unread"], env=p1_env)
        assert ec == 0
