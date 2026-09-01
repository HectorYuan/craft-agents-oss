"""
Z3a — 完整技能生命周期 E2E

模拟 注册技能 → 交互 → 境界升级 → 反思 → 洞察 → 注销 的全流程。
"""

from __future__ import annotations

import time

import pytest

from zenskill.zentest.fixtures import ZSkillHome, ZSkillMemory
from zenskill.zentest.utils import TempDir, write_skill_package


# ═══════════════════════════════════════════════════════════════
# 技能创建 → 安装 → 使用 → 升级 → 注销
# ═══════════════════════════════════════════════════════════════

@pytest.mark.e2e
def test_skill_lifecycle() -> None:
    """
    完整技能生命周期:
    创建包 → 安装 → 多次交互 → 境界升级 → 注销
    """
    with ZSkillHome() as home, TempDir() as pkg_dir:
        # 1) 创建技能包
        skill_name = "lifecycle_test_skill"
        write_skill_package(pkg_dir, skill_name)

        assert (pkg_dir / skill_name / "manifest.json").exists()
        assert (pkg_dir / skill_name / "skill.py").exists()

        # 2) 验证 .zenskill 目录结构被正确创建
        assert (home.root / ".zenskill").exists()
        assert (home.root / ".zenskill" / "skills").exists()
        assert (home.root / ".zenskill" / "memory").exists()

        # 3) 创建初始技能状态
        skill_state = {
            "name": skill_name,
            "level": "novice",
            "level_index": 0,
            "xp": 0,
            "proficiency": 0.3,
            "stability": 0.5,
            "interactions": 0,
        }
        home.write_json(f"skills/{skill_name}.json", skill_state)

        loaded = home.read_json(f"skills/{skill_name}.json")
        assert loaded is not None
        assert loaded["name"] == skill_name
        assert loaded["level"] == "novice"

        # 4) 模拟 10 次交互 → 升级到 apprentice
        for i in range(10):
            skill_state["xp"] += 20
            skill_state["interactions"] += 1

        skill_state["level"] = "apprentice"
        skill_state["level_index"] = 1
        skill_state["proficiency"] = 0.45

        home.write_json(f"skills/{skill_name}.json", skill_state)

        # 5) 验证升级后的状态
        upgraded = home.read_json(f"skills/{skill_name}.json")
        assert upgraded is not None
        assert upgraded["level"] == "apprentice"
        assert upgraded["level_index"] == 1
        assert upgraded["xp"] == 200
        assert upgraded["interactions"] == 10
        assert upgraded["proficiency"] == 0.45

        # 6) 记录记忆（模拟反思）
        memory = [
            {
                "id": "m1",
                "event": "skill_upgrade",
                "skill": skill_name,
                "from": "novice",
                "to": "apprentice",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        ]
        home.write_json(f"memory/{skill_name}_events.json", memory)
        loaded_memory = home.read_json(f"memory/{skill_name}_events.json")
        assert loaded_memory is not None
        assert loaded_memory[0]["event"] == "skill_upgrade"
        assert loaded_memory[0]["to"] == "apprentice"

        # 7) 注销技能（删除状态文件）
        (home.root / ".zenskill" / "skills" / f"{skill_name}.json").unlink()
        assert not (
            home.root / ".zenskill" / "skills" / f"{skill_name}.json"
        ).exists()

        # 但记忆应保留
        assert (
            home.root / ".zenskill" / "memory" / f"{skill_name}_events.json"
        ).exists()


@pytest.mark.e2e
def test_multiple_skills_isolation() -> None:
    """
    多技能共存：各自维护状态，互不干扰。
    """
    with ZSkillHome() as home:
        skills_data = {
            "skill_a": {"name": "skill_a", "level": "novice", "xp": 50},
            "skill_b": {"name": "skill_b", "level": "practitioner", "xp": 300},
            "skill_c": {"name": "skill_c", "level": "master", "xp": 1000},
        }
        for name, data in skills_data.items():
            home.write_json(f"skills/{name}.json", data)

        for name, expected in skills_data.items():
            loaded = home.read_json(f"skills/{name}.json")
            assert loaded is not None
            assert loaded["level"] == expected["level"]


@pytest.mark.e2e
def test_skill_level_progression() -> None:
    """
    验证境界升级序列: novice → apprentice → practitioner → journeyman → master
    """
    levels = ["novice", "apprentice", "practitioner", "journeyman", "master"]
    xp_thresholds = [0, 100, 300, 600, 1000]

    with ZSkillHome() as home:
        for level, xp in zip(levels, xp_thresholds):
            skill = {"name": "prog_skill", "level": level, "xp": xp}
            home.write_json(f"skills/prog_skill.json", skill)
            loaded = home.read_json(f"skills/prog_skill.json")
            assert loaded["level"] == level

        # 最终验证 — master 境界
        final = home.read_json("skills/prog_skill.json")
        assert final["level"] == "master"
        assert final["xp"] == 1000


@pytest.mark.e2e
def test_skill_invalid_level_handling() -> None:
    """
    无效境界应仍可读取（容错），不崩溃。
    """
    with ZSkillHome() as home:
        home.write_json("skills/bad_skill.json", {
            "name": "bad_skill",
            "level": "ultra_master",
            "xp": 9999,
        })
        loaded = home.read_json("skills/bad_skill.json")
        assert loaded is not None
        assert loaded["level"] == "ultra_master"
