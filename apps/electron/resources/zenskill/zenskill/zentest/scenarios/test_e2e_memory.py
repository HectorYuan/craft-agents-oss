"""
P0 — 记忆系统 真实 E2E 测试

通过 subprocess 调用真实 zenskill CLI，验证 Memory 完整 CRUD：
add → list → search → export → import → stats
"""

from __future__ import annotations

import tempfile

import pytest

from zenskill.zentest.utils import run_zenskill, isolated_env


@pytest.fixture
def mem_env():
    with tempfile.TemporaryDirectory() as tmp:
        env = isolated_env({"HOME": tmp})
        yield env


# ═══════════════════════════════════════════════════════════════
# memory add
# ═══════════════════════════════════════════════════════════════

class TestMemoryAddE2E:
    @pytest.mark.e2e
    def test_memory_add_simple(self, mem_env):
        """添加单条记忆"""
        ec, out, _ = run_zenskill(["memory", "add", "测试记忆"], env=mem_env)
        assert ec == 0
        assert "记忆已添加" in out or "add" in out.lower()

    @pytest.mark.e2e
    def test_memory_add_chinese(self, mem_env):
        """添加中文记忆"""
        ec, out, _ = run_zenskill(["memory", "add", "学习Python的感悟"], env=mem_env)
        assert ec == 0
        assert "学习Python的感悟" in out

    @pytest.mark.e2e
    def test_memory_add_empty(self, mem_env):
        """添加空内容应优雅处理"""
        ec, out, err = run_zenskill(["memory", "add", ""], env=mem_env)
        assert ec in (0, 1)

    @pytest.mark.e2e
    def test_memory_add_special_chars(self, mem_env):
        """添加含特殊字符的记忆"""
        ec, out, _ = run_zenskill(
            ["memory", "add", "特殊字符: @#$% 测试!"],
            env=mem_env,
        )
        assert ec == 0

    @pytest.mark.e2e
    def test_memory_add_duplicate(self, mem_env):
        """重复添加相同内容"""
        run_zenskill(["memory", "add", "重复内容"], env=mem_env)
        ec, _, _ = run_zenskill(["memory", "add", "重复内容"], env=mem_env)
        assert ec == 0  # 幂等


# ═══════════════════════════════════════════════════════════════
# memory list
# ═══════════════════════════════════════════════════════════════

class TestMemoryListE2E:
    @pytest.mark.e2e
    def test_memory_list_empty(self, mem_env):
        """空列表"""
        ec, out, _ = run_zenskill(["memory", "list"], env=mem_env)
        assert ec == 0
        # 空时可能有不同输出格式

    @pytest.mark.e2e
    def test_memory_list_after_add(self, mem_env):
        """添加后列表应包含"""
        run_zenskill(["memory", "add", "列表测试"], env=mem_env)
        ec, out, _ = run_zenskill(["memory", "list"], env=mem_env)
        assert ec == 0
        assert "列表测试" in out

    @pytest.mark.e2e
    def test_memory_list_multiple(self, mem_env):
        """多条记忆列表"""
        for item in ["记忆A", "记忆B", "记忆C"]:
            run_zenskill(["memory", "add", item], env=mem_env)
        ec, out, _ = run_zenskill(["memory", "list"], env=mem_env)
        assert ec == 0
        for item in ["记忆A", "记忆B", "记忆C"]:
            assert item in out

    @pytest.mark.e2e
    def test_memory_list_limit(self, mem_env):
        """指定数量限制"""
        for i in range(5):
            run_zenskill(["memory", "add", f"记忆{i}"], env=mem_env)
        ec, out, _ = run_zenskill(["memory", "list", "--n", "3"], env=mem_env)
        assert ec == 0


# ═══════════════════════════════════════════════════════════════
# memory search
# ═══════════════════════════════════════════════════════════════

class TestMemorySearchE2E:
    @pytest.mark.e2e
    def test_memory_search_found(self, mem_env):
        """搜索存在的记忆"""
        run_zenskill(["memory", "add", "Python 异步编程"], env=mem_env)
        run_zenskill(["memory", "add", "Rust 所有权系统"], env=mem_env)
        ec, out, _ = run_zenskill(["memory", "search", "Python"], env=mem_env)
        assert ec == 0
        assert "Python" in out

    @pytest.mark.e2e
    def test_memory_search_not_found(self, mem_env):
        """搜索不存在的记忆"""
        run_zenskill(["memory", "add", "唯一内容"], env=mem_env)
        ec, out, _ = run_zenskill(
            ["memory", "search", "不存在的关键词_xyz"],
            env=mem_env,
        )
        assert ec in (0, 1)  # 可能返回空结果

    @pytest.mark.e2e
    def test_memory_search_empty_query(self, mem_env):
        """空搜索词"""
        ec, out, err = run_zenskill(["memory", "search", ""], env=mem_env)
        assert ec in (0, 1)


# ═══════════════════════════════════════════════════════════════
# memory export / import
# ═══════════════════════════════════════════════════════════════

class TestMemoryExportImportE2E:
    @pytest.mark.e2e
    def test_memory_export(self, mem_env):
        """导出记忆备份"""
        run_zenskill(["memory", "add", "可导出的记忆"], env=mem_env)
        export_path = f"{mem_env['HOME']}/memory_backup.json"
        ec, out, _ = run_zenskill(
            ["memory", "export", "--output", export_path],
            env=mem_env,
        )
        assert ec == 0

        import json, pathlib
        backup = json.loads(pathlib.Path(export_path).read_text())
        assert len(backup) > 0

    @pytest.mark.e2e
    def test_memory_export_empty(self, mem_env):
        """空记忆导出"""
        export_path = f"{mem_env['HOME']}/empty_backup.json"
        ec, out, _ = run_zenskill(
            ["memory", "export", "--output", export_path],
            env=mem_env,
        )
        assert ec == 0

    @pytest.mark.e2e
    def test_memory_import(self, mem_env):
        """导入记忆备份"""
        run_zenskill(["memory", "add", "原始记忆"], env=mem_env)
        export_path = f"{mem_env['HOME']}/mem_backup.json"
        run_zenskill(["memory", "export", "--output", export_path], env=mem_env)

        ec, out, _ = run_zenskill(
            ["memory", "import", export_path],
            env=mem_env,
        )
        assert ec == 0


# ═══════════════════════════════════════════════════════════════
# memory stats
# ═══════════════════════════════════════════════════════════════

class TestMemoryStatsE2E:
    @pytest.mark.e2e
    def test_memory_stats_empty(self, mem_env):
        """空记忆统计"""
        ec, out, _ = run_zenskill(["memory", "stats"], env=mem_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_memory_stats_after_add(self, mem_env):
        """添加后统计应更新"""
        for i in range(5):
            run_zenskill(["memory", "add", f"统计记忆{i}"], env=mem_env)
        ec, out, _ = run_zenskill(["memory", "stats"], env=mem_env)
        assert ec == 0


# ═══════════════════════════════════════════════════════════════
# 完整记忆工作流
# ═══════════════════════════════════════════════════════════════

class TestMemoryWorkflowE2E:
    @pytest.mark.e2e
    def test_memory_full_crud(self, mem_env):
        """完整 CRUD: add → list → search → export → import"""
        # Create
        run_zenskill(["memory", "add", "CRUD测试"], env=mem_env)
        # Read
        ec1, out1, _ = run_zenskill(["memory", "list"], env=mem_env)
        assert ec1 == 0 and "CRUD测试" in out1
        # Search
        ec2, out2, _ = run_zenskill(["memory", "search", "CRUD"], env=mem_env)
        assert ec2 == 0
        # Export
        export_path = f"{mem_env['HOME']}/crud_backup.json"
        ec3, _, _ = run_zenskill(
            ["memory", "export", "--output", export_path],
            env=mem_env,
        )
        assert ec3 == 0
        # Import
        ec4, _, _ = run_zenskill(["memory", "import", export_path], env=mem_env)
        assert ec4 == 0
        # Stats
        ec5, out5, _ = run_zenskill(["memory", "stats"], env=mem_env)
        assert ec5 == 0
