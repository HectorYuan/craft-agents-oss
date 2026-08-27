"""
P0 — GTD 真实 E2E 测试

通过 subprocess 调用真实 zenskill CLI，验证 GTD 完整工作流：
inbox→action→project→energy→calendar
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from zenskill.zentest.utils import run_zenskill, isolated_env


@pytest.fixture
def gtd_env():
    """每个测试使用隔离的 HOME 目录"""
    with tempfile.TemporaryDirectory() as tmp:
        env = isolated_env({"HOME": tmp})
        yield env


# ═══════════════════════════════════════════════════════════════
# Inbox 工作流
# ═══════════════════════════════════════════════════════════════

class TestInboxE2E:
    @pytest.mark.e2e
    def test_inbox_add(self, gtd_env):
        """添加 inbox 项"""
        ec, out, _ = run_zenskill(["inbox", "add", "测试事项"], env=gtd_env)
        assert ec == 0
        assert "Inbox" in out
        assert "测试事项" in out

    @pytest.mark.e2e
    def test_inbox_add_empty(self, gtd_env):
        """添加空标题应优雅处理"""
        ec, out, err = run_zenskill(["inbox", "add", ""], env=gtd_env)
        assert ec == 0 or ec == 1
        assert out or err  # 不应崩溃

    @pytest.mark.e2e
    def test_inbox_add_multiple_then_list(self, gtd_env):
        """添加多条后 list 应全部显示"""
        for item in ["事项A", "事项B", "事项C"]:
            ec, _, _ = run_zenskill(["inbox", "add", item], env=gtd_env)
            assert ec == 0
        ec, out, _ = run_zenskill(["inbox", "list"], env=gtd_env)
        assert ec == 0
        assert "事项A" in out
        assert "事项B" in out
        assert "事项C" in out
        assert "3 items" in out or "3" in out

    @pytest.mark.e2e
    def test_inbox_list_empty(self, gtd_env):
        """空 inbox 应显示无项目"""
        ec, out, _ = run_zenskill(["inbox", "list"], env=gtd_env)
        assert ec == 0
        assert "Inbox" in out

    @pytest.mark.e2e
    def test_inbox_process(self, gtd_env):
        """处理 inbox 命令可调用"""
        run_zenskill(["inbox", "add", "待处理事项"], env=gtd_env)
        ec, out, _ = run_zenskill(
            ["inbox", "process", "1", "--type", "action"],
            env=gtd_env,
        )
        # 成功处理或提示未找到都算通过（不崩溃即可）
        assert ec in (0, 1)


# ═══════════════════════════════════════════════════════════════
# Action 工作流
# ═══════════════════════════════════════════════════════════════

class TestActionE2E:
    @pytest.mark.e2e
    def test_action_add(self, gtd_env):
        """添加 action"""
        ec, out, _ = run_zenskill(["action", "add", "买牛奶"], env=gtd_env)
        assert ec == 0
        assert "Action" in out
        assert "买牛奶" in out

    @pytest.mark.e2e
    def test_action_add_multiple(self, gtd_env):
        """添加多条 action 后 list 应全部显示"""
        items = ["买牛奶", "写报告", "开会", "发邮件"]
        for item in items:
            ec, _, _ = run_zenskill(["action", "add", item], env=gtd_env)
            assert ec == 0
        ec, out, _ = run_zenskill(["action", "list"], env=gtd_env)
        assert ec == 0
        for item in items:
            assert item in out, f"列表中缺少: {item}"

    @pytest.mark.e2e
    def test_action_list_empty(self, gtd_env):
        """空 action 列表"""
        ec, out, _ = run_zenskill(["action", "list"], env=gtd_env)
        assert ec == 0
        assert "Actions" in out or "action" in out.lower()

    @pytest.mark.e2e
    def test_action_done(self, gtd_env):
        """完成 action"""
        run_zenskill(["action", "add", "可完成的任务"], env=gtd_env)
        ec, out, _ = run_zenskill(["action", "done", "1"], env=gtd_env)
        assert ec == 0
        assert ec == 0

    @pytest.mark.e2e
    def test_action_done_invalid_id(self, gtd_env):
        """无效的 action ID 应优雅处理"""
        ec, out, err = run_zenskill(["action", "done", "999"], env=gtd_env)
        assert ec in (0, 1, 2)
        assert out or err

    @pytest.mark.e2e
    def test_action_delete(self, gtd_env):
        """删除 action"""
        run_zenskill(["action", "add", "待删除任务"], env=gtd_env)
        ec, out, _ = run_zenskill(["action", "delete", "1"], env=gtd_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_action_workflow(self, gtd_env):
        """完整 action 工作流: add → list → done → list"""
        run_zenskill(["action", "add", "工作流任务"], env=gtd_env)
        ec1, out1, _ = run_zenskill(["action", "list"], env=gtd_env)
        assert ec1 == 0
        assert "工作流任务" in out1

        run_zenskill(["action", "done", "1"], env=gtd_env)
        ec2, out2, _ = run_zenskill(["action", "list"], env=gtd_env)
        assert ec2 == 0


# ═══════════════════════════════════════════════════════════════
# Project 工作流
# ═══════════════════════════════════════════════════════════════

class TestProjectE2E:
    @pytest.mark.e2e
    def test_project_create(self, gtd_env):
        """创建 project"""
        ec, out, _ = run_zenskill(["project", "create", "学习计划"], env=gtd_env)
        assert ec == 0
        assert "Project" in out or "project" in out.lower()

    @pytest.mark.e2e
    def test_project_create_multiple(self, gtd_env):
        """创建多个 project"""
        for p in ["项目A", "项目B", "项目C"]:
            ec, _, _ = run_zenskill(["project", "create", p], env=gtd_env)
            assert ec == 0
        ec, out, _ = run_zenskill(["project", "list"], env=gtd_env)
        assert ec == 0
        for p in ["项目A", "项目B", "项目C"]:
            assert p in out

    @pytest.mark.e2e
    def test_project_list_empty(self, gtd_env):
        """空 project 列表"""
        ec, out, _ = run_zenskill(["project", "list"], env=gtd_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_project_show(self, gtd_env):
        """查看 project 详情（命令可调用即可）"""
        run_zenskill(["project", "create", "我的项目"], env=gtd_env)
        ec, out, _ = run_zenskill(["project", "show", "1"], env=gtd_env)
        assert ec in (0, 1)

    @pytest.mark.e2e
    def test_project_templates(self, gtd_env):
        """列出项目模板"""
        ec, out, _ = run_zenskill(["project", "templates"], env=gtd_env)
        assert ec == 0
        assert out.strip() != ""


# ═══════════════════════════════════════════════════════════════
# Energy
# ═══════════════════════════════════════════════════════════════

class TestEnergyE2E:
    @pytest.mark.e2e
    def test_energy_status(self, gtd_env):
        """能量状态应返回数值"""
        ec, out, _ = run_zenskill(["energy", "status"], env=gtd_env)
        assert ec == 0
        assert "%" in out or "Energy" in out

    @pytest.mark.e2e
    def test_energy_advise(self, gtd_env):
        """能量建议应返回内容"""
        ec, out, _ = run_zenskill(["energy", "advise"], env=gtd_env)
        assert ec == 0
        assert out.strip() != ""


# ═══════════════════════════════════════════════════════════════
# Calendar
# ═══════════════════════════════════════════════════════════════

class TestCalendarE2E:
    @pytest.mark.e2e
    def test_calendar_today(self, gtd_env):
        """今日日程"""
        ec, out, _ = run_zenskill(["calendar", "today"], env=gtd_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_calendar_week(self, gtd_env):
        """本周日程"""
        ec, out, _ = run_zenskill(["calendar", "week"], env=gtd_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_calendar_add(self, gtd_env):
        """添加日程"""
        ec, out, _ = run_zenskill(
            ["calendar", "add", "2026-06-08", "团队周会", "--time", "10:00"],
            env=gtd_env,
        )
        assert ec == 0
        assert "团队周会" in out


# ═══════════════════════════════════════════════════════════════
# 跨模块 GTD 工作流
# ═══════════════════════════════════════════════════════════════

class TestGTDWorkflowE2E:
    @pytest.mark.e2e
    def test_inbox_to_action_to_done(self, gtd_env):
        """完整 GTD 流程: inbox add → process → action list → done"""
        # Step 1: 添加 inbox
        run_zenskill(["inbox", "add", "准备周报"], env=gtd_env)
        ec1, out1, _ = run_zenskill(["inbox", "list"], env=gtd_env)
        assert ec1 == 0
        assert "准备周报" in out1

        # Step 2: 添加 action
        run_zenskill(["action", "add", "准备周报"], env=gtd_env)
        ec2, out2, _ = run_zenskill(["action", "list"], env=gtd_env)
        assert ec2 == 0
        assert "准备周报" in out2

        # Step 3: 创建项目
        run_zenskill(["project", "create", "周报项目"], env=gtd_env)
        ec3, out3, _ = run_zenskill(["project", "list"], env=gtd_env)
        assert ec3 == 0
        assert "周报项目" in out3

        # Step 4: 完成 action
        ec4, _, _ = run_zenskill(["action", "done", "1"], env=gtd_env)
        assert ec4 == 0

    @pytest.mark.e2e
    def test_gtd_dashboard(self, gtd_env):
        """GTD 仪表盘"""
        # 先创建一些数据
        run_zenskill(["inbox", "add", "仪表盘测试"], env=gtd_env)
        run_zenskill(["action", "add", "仪表盘任务"], env=gtd_env)
        run_zenskill(["project", "create", "仪表盘项目"], env=gtd_env)
        ec, out, _ = run_zenskill(["gtd", "dashboard"], env=gtd_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_gtd_stats(self, gtd_env):
        """GTD 统计"""
        run_zenskill(["action", "add", "统计任务"], env=gtd_env)
        ec, out, _ = run_zenskill(["gtd", "stats"], env=gtd_env)
        assert ec == 0

    @pytest.mark.e2e
    def test_gtd_idempotent(self, gtd_env):
        """GTD 操作幂等性: 重复操作不崩溃"""
        for _ in range(3):
            ec, _, _ = run_zenskill(["action", "add", "幂等测试"], env=gtd_env)
            assert ec == 0
        ec, out, _ = run_zenskill(["action", "list"], env=gtd_env)
        assert ec == 0
        assert "幂等测试" in out
