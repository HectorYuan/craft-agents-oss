"""
P1 — 禅思反思 + 医生诊断 真实 E2E 测试

reflect trigger/issues/consolidate/insight/purify
doctor state/snapshot/repair/diagnostics
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
# Reflect
# ═══════════════════════════════════════════════════════════════

class TestReflectE2E:
    @pytest.mark.e2e
    def test_reflect_issues(self, p1_env):
        """自我诊断"""
        ec, out, _ = run_zenskill(["reflect", "issues"], env=p1_env)
        assert ec == 0
        assert "诊断" in out or "issue" in out.lower()

    @pytest.mark.e2e
    def test_reflect_trigger(self, p1_env):
        """触发反思（可能因无 LLM 失败，但不崩溃）"""
        ec, out, err = run_zenskill(
            ["reflect", "trigger", "--hosted"],
            env=p1_env,
        )
        # --hosted 模式生成任务描述，不调用 LLM
        assert ec in (0, 1)
        assert out or err

    @pytest.mark.e2e
    def test_reflect_consolidate(self, p1_env):
        """记忆巩固"""
        ec, out, _ = run_zenskill(["reflect", "consolidate"], env=p1_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_reflect_insight(self, p1_env):
        """洞见生成"""
        ec, out, _ = run_zenskill(["reflect", "insight"], env=p1_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_reflect_purify(self, p1_env):
        """记忆净化"""
        ec, out, _ = run_zenskill(["reflect", "purify"], env=p1_env)
        assert ec == 0


# ═══════════════════════════════════════════════════════════════
# Doctor
# ═══════════════════════════════════════════════════════════════

class TestDoctorE2E:
    @pytest.mark.e2e
    def test_doctor_state(self, p1_env):
        """状态扫描"""
        ec, out, _ = run_zenskill(["doctor", "state"], env=p1_env)
        assert ec == 0
        assert "健康" in out or "State" in out

    @pytest.mark.e2e
    def test_doctor_diagnostics(self, p1_env):
        """诊断日志"""
        ec, out, _ = run_zenskill(["doctor", "diagnostics"], env=p1_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_doctor_snapshot(self, p1_env):
        """创建快照"""
        ec, out, _ = run_zenskill(["doctor", "snapshot"], env=p1_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_doctor_snapshot_list(self, p1_env):
        """快照列表"""
        run_zenskill(["doctor", "snapshot"], env=p1_env)
        ec, out, _ = run_zenskill(["doctor", "snapshot", "list"], env=p1_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_doctor_migrate(self, p1_env):
        """schema 迁移（dry-run）"""
        ec, out, _ = run_zenskill(
            ["doctor", "migrate", "--all"],
            env=p1_env,
        )
        assert ec in (0, 1)


# ═══════════════════════════════════════════════════════════════
# 跨模块工作流：成长 → 反思 → 诊断
# ═══════════════════════════════════════════════════════════════

class TestGrowthReflectDoctorWorkflowE2E:
    @pytest.mark.e2e
    def test_growth_goal_reflect_doctor(self, p1_env):
        """
        跨模块工作流:
        成长状态 → 设置目标 → 反思诊断 → 医生检查
        """
        # 1. 成长状态
        ec1, out1, _ = run_zenskill(["growth", "status"], env=p1_env)
        assert ec1 == 0

        # 2. 设置目标
        ec2, _, _ = run_zenskill(
            ["goal", "set", "--dimension", "proficiency",
             "--target", "50"],
            env=p1_env,
        )
        assert ec2 == 0

        # 3. 推荐任务
        ec3, _, _ = run_zenskill(["task", "recommend"], env=p1_env)
        assert ec3 == 0

        # 4. 反思诊断
        ec4, _, _ = run_zenskill(["reflect", "issues"], env=p1_env)
        assert ec4 == 0

        # 5. 医生检查
        ec5, _, _ = run_zenskill(["doctor", "state"], env=p1_env)
        assert ec5 == 0

        # 6. 查看增长里程碑
        ec6, _, _ = run_zenskill(["growth", "milestones"], env=p1_env)
        assert ec6 == 0
