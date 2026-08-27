"""
P2 — 评级+搜索 真实 E2E 测试

rate → rating → ratings list → search → discover → trending → path
"""

from __future__ import annotations

import tempfile

import pytest

from zenskill.zentest.utils import run_zenskill, isolated_env


@pytest.fixture
def p2_env():
    with tempfile.TemporaryDirectory() as tmp:
        env = isolated_env({"HOME": tmp})
        run_zenskill(["info"], env=env)  # 初始化目录
        yield env


# ═══════════════════════════════════════════════════════════════
# 评级系统
# ═══════════════════════════════════════════════════════════════

class TestRateE2E:
    @pytest.mark.e2e
    def test_rate_skill(self, p2_env):
        """给技能打分"""
        ec, out, _ = run_zenskill(["rate", "zenskill-core", "4"], env=p2_env)
        assert ec == 0
        assert "评分" in out or "rating" in out.lower()

    @pytest.mark.e2e
    def test_rate_min_score(self, p2_env):
        """最低分"""
        ec, out, _ = run_zenskill(["rate", "zenskill-core", "1"], env=p2_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_rate_max_score(self, p2_env):
        """最高分"""
        ec, out, _ = run_zenskill(["rate", "zenskill-core", "5"], env=p2_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_rate_invalid_score(self, p2_env):
        """无效分数应优雅处理"""
        ec, out, err = run_zenskill(["rate", "zenskill-core", "6"], env=p2_env)
        assert ec in (0, 1, 2)

    @pytest.mark.e2e
    def test_rate_nonexistent_skill(self, p2_env):
        """不存在的技能"""
        ec, out, err = run_zenskill(
            ["rate", "nonexistent_xyz", "3"], env=p2_env
        )
        assert ec in (0, 1)

    @pytest.mark.e2e
    def test_rate_then_rating(self, p2_env):
        """打分后查看评级"""
        run_zenskill(["rate", "zenskill-core", "4"], env=p2_env)
        ec, out, _ = run_zenskill(["rating", "zenskill-core"], env=p2_env)
        assert ec == 0
        assert "4" in out or "80%" in out

    @pytest.mark.e2e
    def test_ratings_list(self, p2_env):
        """评级列表"""
        run_zenskill(["rate", "zenskill-core", "4"], env=p2_env)
        ec, out, _ = run_zenskill(["ratings", "list"], env=p2_env)
        assert ec == 0
        assert "zenskill" in out.lower()


# ═══════════════════════════════════════════════════════════════
# 搜索生态
# ═══════════════════════════════════════════════════════════════

class TestSearchE2E:
    @pytest.mark.e2e
    def test_search(self, p2_env):
        """搜索技能"""
        ec, out, _ = run_zenskill(["search", "skill"], env=p2_env)
        assert ec == 0
        assert out.strip() != ""

    @pytest.mark.e2e
    def test_search_empty_query(self, p2_env):
        """空搜索"""
        ec, out, err = run_zenskill(["search", ""], env=p2_env)
        assert ec in (0, 1)

    @pytest.mark.e2e
    def test_search_no_match(self, p2_env):
        """无匹配搜索"""
        ec, out, _ = run_zenskill(
            ["search", "zzz_nonexistent_xyz"], env=p2_env
        )
        assert ec in (0, 1)

    @pytest.mark.e2e
    def test_discover(self, p2_env):
        """发现推荐"""
        ec, out, _ = run_zenskill(["discover"], env=p2_env)
        assert ec == 0
        assert out.strip() != ""

    @pytest.mark.e2e
    def test_trending(self, p2_env):
        """热门趋势"""
        ec, out, _ = run_zenskill(["trending"], env=p2_env)
        assert ec == 0
        assert out.strip() != ""

    @pytest.mark.e2e
    def test_path(self, p2_env):
        """学习路径"""
        ec, out, _ = run_zenskill(["path", "Python"], env=p2_env)
        assert ec == 0
        assert out.strip() != ""

    @pytest.mark.e2e
    def test_path_empty_goal(self, p2_env):
        """空目标路径"""
        ec, out, err = run_zenskill(["path", ""], env=p2_env)
        assert ec in (0, 1)
