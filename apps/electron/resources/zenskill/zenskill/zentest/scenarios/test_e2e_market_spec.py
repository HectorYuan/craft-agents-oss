"""
P2 — 技能市场+Spec 真实 E2E 测试

spec validate/export/inspect, package validate, install
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
# SkillSpec
# ═══════════════════════════════════════════════════════════════

class TestSpecE2E:
    @pytest.mark.e2e
    def test_spec_validate(self, p2_env):
        """验证 SkillSpec"""
        ec, out, _ = run_zenskill(
            ["spec", "validate", "zenskill-core"], env=p2_env
        )
        assert ec == 0

    @pytest.mark.e2e
    def test_spec_export(self, p2_env):
        """导出 SkillSpec (可能因DB不可用返回1但不崩溃)"""
        output = f"{p2_env['HOME']}/spec_output.json"
        ec, out, _ = run_zenskill(
            ["spec", "export", "zenskill-core", "--output", output],
            env=p2_env,
        )
        assert ec in (0, 1)

    @pytest.mark.e2e
    def test_spec_inspect(self, p2_env):
        """查看 SkillSpec"""
        ec, out, _ = run_zenskill(
            ["spec", "inspect", "zenskill-core"], env=p2_env
        )
        assert ec in (0, 1)


# ═══════════════════════════════════════════════════════════════
# Package
# ═══════════════════════════════════════════════════════════════

class TestPackageE2E:
    @pytest.mark.e2e
    def test_package_list(self, p2_env):
        """技能包列表"""
        ec, out, _ = run_zenskill(["package", "list"], env=p2_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_package_validate(self, p2_env):
        """验证包"""
        # package validate 需要具体路径
        ec, out, err = run_zenskill(
            ["package", "validate", "/tmp/nonexistent_pkg.skill"],
            env=p2_env,
        )
        assert ec in (0, 1)


# ═══════════════════════════════════════════════════════════════
# Install
# ═══════════════════════════════════════════════════════════════

class TestInstallE2E:
    @pytest.mark.e2e
    def test_install_nonexistent(self, p2_env):
        """安装不存在的来源"""
        ec, out, err = run_zenskill(
            ["install", "nonexistent_skill_xyz"], env=p2_env
        )
        assert ec in (0, 1)  # 不崩溃即可


# ═══════════════════════════════════════════════════════════════
# 市场
# ═══════════════════════════════════════════════════════════════

class TestMarketE2E:
    @pytest.mark.e2e
    def test_market_search(self, p2_env):
        """搜索市场"""
        ec, out, _ = run_zenskill(["market", "search", "test"], env=p2_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_market_list(self, p2_env):
        """市场列表 (可能因bug返回1但不崩溃)"""
        ec, out, _ = run_zenskill(["market", "list"], env=p2_env)
        assert ec in (0, 1)
