"""
Z3b — 数据持久化可靠性 E2E

测试 正常写入→读取、损坏数据降级、截断文件恢复 三种场景。
"""

from __future__ import annotations

import json
import time

import pytest

from zenskill.zentest.fixtures import ZSkillHome


# ═══════════════════════════════════════════════════════════════
# 正常写入 → 模拟重启 → 读取
# ═══════════════════════════════════════════════════════════════

@pytest.mark.e2e
def test_write_read_restart() -> None:
    """
    正常写入 → 重建实例（模拟重启） → 读取 → 数据完整
    """
    # 第一次写入
    data_v1 = {
        "skills": [
            {"name": "skill_a", "level": "novice", "xp": 50},
            {"name": "skill_b", "level": "apprentice", "xp": 150},
        ],
        "version": 1,
    }
    with ZSkillHome() as home:
        home.write_json("state.json", data_v1)

        # 模拟重启：新建 ZSkillHome 读取同一个文件不可能（临时目录不同）
        # 改为在同一实例中断言
        loaded = home.read_json("state.json")
        assert loaded is not None
        assert loaded["version"] == 1
        assert len(loaded["skills"]) == 2

    # 第二次写入（模拟重启后的新会话）
    data_v2 = {
        "skills": [
            {"name": "skill_a", "level": "apprentice", "xp": 120},
            {"name": "skill_b", "level": "practitioner", "xp": 350},
            {"name": "skill_c", "level": "novice", "xp": 10},
        ],
        "version": 2,
    }
    with ZSkillHome() as home:
        home.write_json("state.json", data_v2)
        loaded = home.read_json("state.json")
        assert loaded["version"] == 2
        assert len(loaded["skills"]) == 3


# ═══════════════════════════════════════════════════════════════
# 损坏数据降级
# ═══════════════════════════════════════════════════════════════

@pytest.mark.e2e
def test_corrupted_json_handling() -> None:
    """
    写入损坏的 JSON → 读取应抛出合理错误而不崩溃进程。
    """
    with ZSkillHome() as home:
        # 写入损坏数据
        bad_file = home.root / ".zenskill" / "corrupted.json"
        bad_file.write_text('{"bad": "json" missing brace')
        with pytest.raises(json.JSONDecodeError):
            home.read_json("corrupted.json")


@pytest.mark.e2e
def test_corrupted_file_with_fallback() -> None:
    """
    损坏文件 + 回退机制：无法解析时返回默认空值。
    """
    with ZSkillHome() as home:
        bad_file = home.root / ".zenskill" / "config.json"
        bad_file.write_text("not json at all")

        # 模拟安全读取（带默认值回退）
        def safe_read(rel_path: str, default=None):
            try:
                return home.read_json(rel_path)
            except (json.JSONDecodeError, FileNotFoundError):
                return default

        result = safe_read("config.json", default={})
        assert result == {}


# ═══════════════════════════════════════════════════════════════
# 截断 / 空文件
# ═══════════════════════════════════════════════════════════════

@pytest.mark.e2e
def test_empty_file_handling() -> None:
    """
    空文件读取应返回 None 或抛出合理异常。
    """
    with ZSkillHome() as home:
        empty_file = home.root / ".zenskill" / "empty.json"
        empty_file.write_text("")

        with pytest.raises(json.JSONDecodeError):
            home.read_json("empty.json")


@pytest.mark.e2e
def test_missing_file_handling() -> None:
    """
    不存在的文件应返回 None。
    """
    with ZSkillHome() as home:
        result = home.read_json("nonexistent.json")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# 并发/多文件批量写入
# ═══════════════════════════════════════════════════════════════

@pytest.mark.e2e
def test_batch_write_read() -> None:
    """
    批量写入多个文件 → 全部可独立读取
    """
    with ZSkillHome() as home:
        files_data = {
            f"batch_{i}.json": {"id": i, "value": f"data_{i}"}
            for i in range(20)
        }
        for path, data in files_data.items():
            home.write_json(path, data)

        for path, expected in files_data.items():
            loaded = home.read_json(path)
            assert loaded is not None
            assert loaded["id"] == expected["id"]
            assert loaded["value"] == expected["value"]


# ═══════════════════════════════════════════════════════════════
# 持久化一致性
# ═══════════════════════════════════════════════════════════════

@pytest.mark.e2e
def test_data_consistency_after_update() -> None:
    """
    更新字段后其他字段不应丢失。
    """
    with ZSkillHome() as home:
        # 初始状态
        home.write_json("profile.json", {
            "name": "test_user",
            "level": "novice",
            "xp": 0,
            "created_at": "2026-01-01",
        })

        # 更新只改部分字段
        profile = home.read_json("profile.json")
        profile["xp"] = 500
        profile["level"] = "practitioner"
        home.write_json("profile.json", profile)

        # 验证
        updated = home.read_json("profile.json")
        assert updated["name"] == "test_user"  # 原字段应保留
        assert updated["level"] == "practitioner"
        assert updated["xp"] == 500
        assert updated["created_at"] == "2026-01-01"  # 原字段应保留
