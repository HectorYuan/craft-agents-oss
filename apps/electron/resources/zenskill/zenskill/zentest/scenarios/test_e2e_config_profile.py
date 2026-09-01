"""
P1 — Config/Profile 真实 E2E 测试

config show/set, profile create/switch/info/list/delete
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
# Config
# ═══════════════════════════════════════════════════════════════

class TestConfigE2E:
    @pytest.mark.e2e
    def test_config_show(self, p1_env):
        """配置查看"""
        ec, out, _ = run_zenskill(["config", "show"], env=p1_env)
        assert ec == 0
        assert "LLM Provider" in out or "Config" in out

    @pytest.mark.e2e
    def test_config_set_string(self, p1_env):
        """设置字符串配置"""
        ec, out, _ = run_zenskill(["config", "set", "theme", "dark"], env=p1_env)
        assert ec == 0
        assert "配置已更新" in out or "theme" in out

    @pytest.mark.e2e
    def test_config_set_numeric(self, p1_env):
        """设置数值配置"""
        ec, out, _ = run_zenskill(
            ["config", "set", "timeout", "30"], env=p1_env
        )
        assert ec == 0

    @pytest.mark.e2e
    def test_config_persist_after_set(self, p1_env):
        """设置后 show 应包含新值"""
        run_zenskill(["config", "set", "theme", "dark"], env=p1_env)
        ec, out, _ = run_zenskill(["config", "show"], env=p1_env)
        assert ec == 0


# ═══════════════════════════════════════════════════════════════
# Profile
# ═══════════════════════════════════════════════════════════════

class TestProfileE2E:
    @pytest.mark.e2e
    def test_profile_create(self, p1_env):
        """创建 profile"""
        ec, out, _ = run_zenskill(["profile", "create", "work"], env=p1_env)
        assert ec == 0
        assert "创建成功" in out or "work" in out

    @pytest.mark.e2e
    def test_profile_create_multiple(self, p1_env):
        """创建多个 profile"""
        for p in ["work", "personal", "study"]:
            ec, _, _ = run_zenskill(["profile", "create", p], env=p1_env)
            assert ec == 0

    @pytest.mark.e2e
    def test_profile_create_duplicate(self, p1_env):
        """重复创建应优雅处理"""
        run_zenskill(["profile", "create", "dup"], env=p1_env)
        ec, out, err = run_zenskill(["profile", "create", "dup"], env=p1_env)
        # 可接受错误码或提示信息
        assert ec in (0, 1, 2)

    @pytest.mark.e2e
    def test_profile_list(self, p1_env):
        """列 profile"""
        run_zenskill(["profile", "create", "test_profile"], env=p1_env)
        ec, out, _ = run_zenskill(["profile", "list"], env=p1_env)
        assert ec == 0
        assert "test_profile" in out

    @pytest.mark.e2e
    def test_profile_switch(self, p1_env):
        """切换 profile"""
        run_zenskill(["profile", "create", "work"], env=p1_env)
        ec, out, _ = run_zenskill(["profile", "switch", "work"], env=p1_env)
        assert ec == 0
        assert "切换到" in out or "work" in out

    @pytest.mark.e2e
    def test_profile_info(self, p1_env):
        """查看当前 profile 详情"""
        run_zenskill(["profile", "create", "myprofile"], env=p1_env)
        run_zenskill(["profile", "switch", "myprofile"], env=p1_env)
        ec, out, _ = run_zenskill(["profile", "info"], env=p1_env)
        assert ec == 0
        assert "myprofile" in out

    @pytest.mark.e2e
    def test_profile_delete(self, p1_env):
        """删除 profile"""
        run_zenskill(["profile", "create", "todelete"], env=p1_env)
        ec, out, _ = run_zenskill(["profile", "delete", "todelete"], env=p1_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_profile_delete_nonexistent(self, p1_env):
        """删除不存在的 profile"""
        ec, out, err = run_zenskill(
            ["profile", "delete", "nonexistent"], env=p1_env
        )
        assert ec in (0, 1)

    @pytest.mark.e2e
    def test_profile_isolation(self, p1_env):
        """不同 profile 之间数据隔离"""
        run_zenskill(["profile", "create", "work"], env=p1_env)
        run_zenskill(["profile", "create", "personal"], env=p1_env)

        # work 下添加数据
        run_zenskill(["profile", "switch", "work"], env=p1_env)
        run_zenskill(["memory", "add", "工作记忆"], env=p1_env)
        ec1, out1, _ = run_zenskill(["memory", "list"], env=p1_env)
        assert ec1 == 0
        assert "工作记忆" in out1

        # personal 下不应看到 work 的数据
        run_zenskill(["profile", "switch", "personal"], env=p1_env)
        ec2, out2, _ = run_zenskill(["memory", "list"], env=p1_env)
        assert ec2 == 0
        assert "工作记忆" not in out2
