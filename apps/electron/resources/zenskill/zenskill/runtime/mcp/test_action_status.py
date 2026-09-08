"""
action_status 批量状态查询工具测试

覆盖：
- 注册为读工具（不命中 action_ 写前缀误判，TTL 缓存可用）
- 多 id 批量映射 + 状态回读
- 缺失 id（已删除/不存在）落入 missing
- 空/非法入参防御
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from zenskill.runtime.mcp.registry import ServerToolRegistry, build_default_registry


def call_json(registry: ServerToolRegistry, name: str, args: dict) -> dict:
    """registry.call 返回 JSON 字符串，统一解包为 dict"""
    return json.loads(registry.call(name, args))


@pytest.fixture
def isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def registry():
    return build_default_registry()


class TestActionStatusRegistration:
    def test_is_read_tool(self):
        # action_ 前缀默认命中写工具误判；显式登记后必须判定为读
        assert ServerToolRegistry.is_write_tool("action_status") is False

    def test_registered_with_schema(self, registry):
        assert registry.has("action_status")
        spec = next(t for t in registry.list_specs() if t["name"] == "action_status")
        assert spec["inputSchema"]["required"] == ["ids"]
        assert spec["inputSchema"]["properties"]["ids"]["type"] == "array"


class TestActionStatusQuery:
    def test_batch_mapping_after_done(self, registry, isolated_home):
        add_a = call_json(registry, "action_add", {"title": "写周报"})
        add_b = call_json(registry, "action_add", {"title": "回复邮件"})
        id_a, id_b = add_a["id"], add_b["id"]

        call_json(registry, "action_done", {"action_id": id_a, "energy_invested": 3})

        result = call_json(registry, "action_status", {"ids": [id_a, id_b]})
        by_id = {i["id"]: i for i in result["items"]}
        assert by_id[id_a]["status"] == "done"
        assert by_id[id_b]["status"] == "pending"
        assert by_id[id_b]["title"] == "回复邮件"
        assert result["missing"] == []

    def test_missing_id_reported(self, registry, isolated_home):
        add = call_json(registry, "action_add", {"title": "存在的行动"})
        ghost_id = "act_999999999999999_999"

        result = call_json(registry, "action_status", {"ids": [add["id"], ghost_id]})
        assert [i["id"] for i in result["items"]] == [add["id"]]
        assert result["missing"] == [ghost_id]

    def test_empty_and_invalid_ids(self, registry, isolated_home):
        result = call_json(registry, "action_status", {"ids": []})
        assert result["count"] == 0 and result["items"] == []
        result = call_json(registry, "action_status", {})
        assert result["count"] == 0 and result["items"] == []
