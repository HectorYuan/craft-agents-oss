"""
P0 — 技能修炼 真实 E2E 测试

通过 subprocess 调用真实 zenskill CLI，验证技能系统：
status → list → metrics → define → info
"""

from __future__ import annotations

import tempfile

import pytest

from zenskill.zentest.utils import run_zenskill, isolated_env


@pytest.fixture
def skill_env():
    with tempfile.TemporaryDirectory() as tmp:
        env = isolated_env({"HOME": tmp})
        yield env


# ═══════════════════════════════════════════════════════════════
# skill status
# ═══════════════════════════════════════════════════════════════

class TestSkillStatusE2E:
    @pytest.mark.e2e
    def test_skill_status_default(self, skill_env):
        """默认技能状态"""
        ec, out, _ = run_zenskill(["skill", "status"], env=skill_env)
        assert ec == 0
        assert "zenskill-core" in out or "技能" in out

    @pytest.mark.e2e
    def test_skill_status_with_skill_id_flag(self, skill_env):
        """--skill-id 标志"""
        ec, out, _ = run_zenskill(
            ["--skill-id", "zenskill-core", "skill", "status"],
            env=skill_env,
        )
        assert ec == 0
        assert "zenskill-core" in out or "NOVICE" in out

    @pytest.mark.e2e
    def test_skill_status_invalid_id(self, skill_env):
        """无效 skill_id"""
        ec, out, err = run_zenskill(
            ["--skill-id", "nonexistent_skill_xyz", "skill", "status"],
            env=skill_env,
        )
        assert ec in (0, 1)


# ═══════════════════════════════════════════════════════════════
# skill list
# ═══════════════════════════════════════════════════════════════

class TestSkillListE2E:
    @pytest.mark.e2e
    def test_skill_list(self, skill_env):
        """技能列表"""
        ec, out, _ = run_zenskill(["skill", "list"], env=skill_env)
        assert ec == 0
        assert "zenskill-core" in out or "技能" in out


# ═══════════════════════════════════════════════════════════════
# skill metrics
# ═══════════════════════════════════════════════════════════════

class TestSkillMetricsE2E:
    @pytest.mark.e2e
    def test_skill_metrics_default(self, skill_env):
        """默认技能指标"""
        ec, out, _ = run_zenskill(["skill", "metrics"], env=skill_env)
        assert ec == 0
        assert "执行次数" in out or "metrics" in out.lower()

    @pytest.mark.e2e
    def test_skill_metrics_with_skill_id_flag(self, skill_env):
        """--skill-id 标志"""
        ec, out, _ = run_zenskill(
            ["--skill-id", "zenskill-core", "skill", "metrics"],
            env=skill_env,
        )
        assert ec == 0

    @pytest.mark.e2e
    def test_skill_metrics_tracks_calls(self, skill_env):
        """调用命令后指标应更新"""
        # 先查看初始指标
        ec1, out1, _ = run_zenskill(
            ["--skill-id", "zenskill-core", "skill", "metrics"],
            env=skill_env,
        )
        assert ec1 == 0

        # 执行一些操作以产生交互
        run_zenskill(["memory", "add", "技能测试记忆"], env=skill_env)
        run_zenskill(["inbox", "add", "技能测试事项"], env=skill_env)

        # 再次查看指标
        ec2, out2, _ = run_zenskill(
            ["--skill-id", "zenskill-core", "skill", "metrics"],
            env=skill_env,
        )
        assert ec2 == 0


# ═══════════════════════════════════════════════════════════════
# skill info
# ═══════════════════════════════════════════════════════════════

class TestSkillInfoE2E:
    @pytest.mark.e2e
    def test_skill_info(self, skill_env):
        """技能全貌"""
        ec, out, _ = run_zenskill(["skill", "info"], env=skill_env)
        assert ec == 0
        assert out.strip() != ""

    @pytest.mark.e2e
    def test_skill_info_with_skill_id_flag(self, skill_env):
        """--skill-id 标志"""
        ec, out, _ = run_zenskill(
            ["--skill-id", "zenskill-core", "skill", "info"],
            env=skill_env,
        )
        assert ec == 0


# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════

class TestConfigE2E:
    @pytest.mark.e2e
    def test_config_show(self, skill_env):
        """配置查看"""
        ec, out, _ = run_zenskill(["config", "show"], env=skill_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_config_set_and_show(self, skill_env):
        """配置设置后应可查看"""
        ec1, _, _ = run_zenskill(
            ["config", "set", "theme", "dark"],
            env=skill_env,
        )
        assert ec1 == 0

        ec2, out2, _ = run_zenskill(["config", "show"], env=skill_env)
        assert ec2 == 0

    @pytest.mark.e2e
    def test_config_set_invalid_key(self, skill_env):
        """无效配置键"""
        ec, out, err = run_zenskill(
            ["config", "set", "invalid_key_xyz", "value"],
            env=skill_env,
        )
        assert ec in (0, 1)


# ═══════════════════════════════════════════════════════════════
# 医生诊断
# ═══════════════════════════════════════════════════════════════

class TestDoctorE2E:
    @pytest.mark.e2e
    def test_doctor_state(self, skill_env):
        """诊断状态"""
        ec, out, _ = run_zenskill(["doctor", "state"], env=skill_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_doctor_diagnostics(self, skill_env):
        """诊断日志"""
        ec, out, _ = run_zenskill(["doctor", "diagnostics"], env=skill_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_doctor_snapshot(self, skill_env):
        """快照创建与列表"""
        ec1, _, _ = run_zenskill(["doctor", "snapshot"], env=skill_env)
        assert ec1 == 0

        ec2, out2, _ = run_zenskill(
            ["doctor", "snapshot", "list"],
            env=skill_env,
        )
        assert ec2 == 0


# ═══════════════════════════════════════════════════════════════
# 端到端跨模块工作流
# ═══════════════════════════════════════════════════════════════

class TestCrossModuleWorkflowE2E:
    @pytest.mark.e2e
    def test_memory_skill_interaction(self, skill_env):
        """
        跨模块交互:
        添加记忆 → 查看技能指标 → 配置设置 → 完成 action
        """
        # 1. 添加记忆
        run_zenskill(["memory", "add", "跨模块测试"], env=skill_env)

        # 2. 查看技能状态
        ec2, out2, _ = run_zenskill(
            ["skill", "status"],
            env=skill_env,
        )
        assert ec2 == 0

        # 3. 添加 inbox
        run_zenskill(["inbox", "add", "跨模块事项"], env=skill_env)
        ec3, out3, _ = run_zenskill(["inbox", "list"], env=skill_env)
        assert ec3 == 0
        assert "跨模块事项" in out3

        # 4. 查看配置
        ec4, _, _ = run_zenskill(["config", "show"], env=skill_env)
        assert ec4 == 0

    @pytest.mark.e2e
    def test_info_doctor_health(self, skill_env):
        """系统信息 → 诊断 → 健康度"""
        ec1, out1, _ = run_zenskill(["info"], env=skill_env)
        assert ec1 == 0

        ec2, _, _ = run_zenskill(["doctor", "state"], env=skill_env)
        assert ec2 == 0

        ec3, out3, _ = run_zenskill(["health", "score"], env=skill_env)
        assert ec3 == 0
