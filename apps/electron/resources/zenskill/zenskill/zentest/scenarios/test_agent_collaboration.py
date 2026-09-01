"""
Z4 — 多 Agent 协作场景 E2E

模拟 Coordinator 分解任务 → 多 Agent 各司其职 → 提案协商 → 表决 → 执行 → 结果。
"""

from __future__ import annotations

import pytest

from zenskill.zentest.fixtures import zskill_bus


@pytest.mark.e2e
def test_agent_registration() -> None:
    """所有 7 个 Agent 应按预期注册"""
    bus = zskill_bus()
    assert len(bus.agents) == 7

    expected_roles = {
        "coordinator", "architect", "developer", "analyzer",
        "tester", "reviewer", "documenter",
    }
    assert set(bus.agents.keys()) == expected_roles


@pytest.mark.e2e
def test_agent_status_default() -> None:
    """所有 Agent 初始状态应为 idle"""
    bus = zskill_bus()
    for role, info in bus.agents.items():
        assert info["status"] == "idle", f"{role} should be idle"


@pytest.mark.e2e
def test_agent_skills() -> None:
    """每个 Agent 至少有 role 对应的技能"""
    bus = zskill_bus()
    for role, info in bus.agents.items():
        assert role in info["skills"], f"{role} should have skill '{role}'"
        assert "communication" in info["skills"], "all should have communication"


@pytest.mark.e2e
def test_agent_priority_unique() -> None:
    """Agent 优先级应唯一（无重复）"""
    bus = zskill_bus()
    priorities = [a["priority"] for a in bus.agents.values()]
    assert len(priorities) == len(set(priorities)), "priorities must be unique"


@pytest.mark.e2e
def test_message_sending() -> None:
    """Agent 之间可发送消息"""
    bus = zskill_bus()

    bus.send("coordinator", "architect", "request", {"task": "设计系统架构"})
    assert len(bus.messages) == 1

    msg = bus.messages[0]
    assert msg["from"] == "coordinator"
    assert msg["to"] == "architect"
    assert msg["type"] == "request"
    assert msg["payload"]["task"] == "设计系统架构"
    assert msg["id"].startswith("msg_")


@pytest.mark.e2e
def test_multi_agent_collaboration_flow() -> None:
    """
    完整协作流程:
    Coordinator → 分解任务 → Architect 提案 → Developer 实现
    → Tester 验证 → Reviewer 审查 → Documenter 记录
    """
    bus = zskill_bus()

    # Phase 1: Coordinator 分解任务
    bus.send("coordinator", "architect", "decompose", {
        "task": "实现用户登录模块",
        "subtasks": ["设计API", "实现后端", "编写测试", "编写文档"],
    })
    assert bus.count_by_type("decompose") == 1

    # Phase 2: Architect 提案
    bus.send("architect", "developer", "proposal", {
        "component": "login_api",
        "endpoints": ["POST /login", "POST /register", "POST /logout"],
        "auth": "JWT",
    })
    assert bus.count_by_type("proposal") == 1

    # Phase 3: Developer 实现
    bus.send("developer", "tester", "implementation", {
        "component": "login_api",
        "files": ["auth.py", "routes.py", "models.py"],
        "status": "completed",
    })
    assert bus.count_by_type("implementation") == 1

    # Phase 4: Tester 验证
    bus.send("tester", "reviewer", "test_report", {
        "total_tests": 15,
        "passed": 14,
        "failed": 1,
        "coverage": 87.5,
    })
    assert bus.count_by_type("test_report") == 1

    # Phase 5: Reviewer 审查
    review_msg = {
        "component": "login_api",
        "issues": [
            {"severity": "minor", "file": "auth.py", "line": 42},
        ],
        "approved": True,
    }
    bus.send("reviewer", "coordinator", "review", review_msg)
    assert bus.count_by_type("review") == 1

    # Phase 6: Documenter 记录
    bus.send("documenter", "coordinator", "documentation", {
        "component": "login_api",
        "docs": ["api_spec.md", "deployment.md"],
    })
    assert bus.count_by_type("documentation") == 1

    # 验证总消息数
    assert len(bus.messages) == 6


@pytest.mark.e2e
def test_message_ordering() -> None:
    """消息应按发送顺序分配递增 ID"""
    bus = zskill_bus()
    bus.send("a", "b", "type1", {})
    bus.send("c", "d", "type2", {})
    bus.send("e", "f", "type3", {})

    ids = [m["id"] for m in bus.messages]
    assert ids == ["msg_0000", "msg_0001", "msg_0002"]


@pytest.mark.e2e
def test_message_bus_isolation() -> None:
    """不同 MessageBus 实例之间应完全隔离"""
    bus1 = zskill_bus()
    bus2 = zskill_bus()

    bus1.send("coordinator", "architect", "request", {"task": "A"})
    assert len(bus1.messages) == 1
    assert len(bus2.messages) == 0

    bus2.send("developer", "tester", "request", {"task": "B"})
    assert len(bus1.messages) == 1
    assert len(bus2.messages) == 1


@pytest.mark.e2e
def test_unknown_agent_message() -> None:
    """发送给未注册的 Agent 不应阻止消息记录"""
    bus = zskill_bus()
    # 即使 recipient 不在 agents 中，消息仍应被记录
    bus.send("coordinator", "unknown_agent", "request", {"task": "secret"})
    assert len(bus.messages) == 1
    assert bus.messages[0]["to"] == "unknown_agent"
