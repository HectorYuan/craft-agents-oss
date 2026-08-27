"""
ZenTest 共享 Fixtures

提供 6 个标准测试环境 fixture，支持 pytest 和独立使用。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock


# ═══════════════════════════════════════════════════════════════
# zskill_home — 隔离的 ~/.zenskill 目录
# ═══════════════════════════════════════════════════════════════

class ZSkillHome:
    """隔离的测试家目录环境"""

    def __init__(self, base: Optional[Path] = None):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._setup_structure()

    def _setup_structure(self) -> None:
        """创建标准的 zenskill 目录结构"""
        dirs = [
            self.root / ".zenskill" / "skills",
            self.root / ".zenskill" / "memory",
            self.root / ".zenskill" / "config",
            self.root / ".zenskill" / "logs",
            self.root / ".zenskill" / "profiles",
            self.root / ".zenskill" / "gtd" / "projects",
            self.root / ".zenskill" / "gtd" / "actions",
            self.root / ".zenskill" / "gtd" / "inbox",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def write_json(self, rel_path: str, data: Any) -> None:
        """写入 JSON 文件到 .zenskill 下"""
        (self.root / ".zenskill" / rel_path).write_text(
            json.dumps(data, ensure_ascii=False, indent=2)
        )

    def read_json(self, rel_path: str) -> Any:
        """从 .zenskill 下读取 JSON 文件"""
        fp = self.root / ".zenskill" / rel_path
        return json.loads(fp.read_text()) if fp.exists() else None

    def cleanup(self) -> None:
        self._tmp.cleanup()

    def __enter__(self) -> "ZSkillHome":
        return self

    def __exit__(self, *args: Any) -> None:
        self.cleanup()


def zskill_home() -> ZSkillHome:
    """创建一个隔离的测试家目录"""
    return ZSkillHome()


# ═══════════════════════════════════════════════════════════════
# zskill_memory — 预填充的 MemoryStore
# ═══════════════════════════════════════════════════════════════

class ZSkillMemory:
    """预填充的记忆存储，含 Working / Episodic / Semantic 三层"""

    def __init__(self) -> None:
        self.working: Dict[str, Any] = {}
        self.episodic: List[Dict[str, Any]] = []
        self.semantic: Dict[str, Any] = {}
        self._seed()

    def _seed(self) -> None:
        self.working = {"current_goal": "test_mastery", "iteration": 3}

        self.episodic = [
            {"id": "e1", "event": "skill_upgrade", "from": "novice", "to": "apprentice",
             "timestamp": "2026-06-01T10:00:00", "score": 0.75},
            {"id": "e2", "event": "reflection", "insight": "一致性改进",
             "timestamp": "2026-06-02T14:00:00", "score": 0.60},
            {"id": "e3", "event": "skill_used", "name": "test_skill",
             "timestamp": "2026-06-03T09:00:00", "count": 5},
        ]

        self.semantic = {
            "skill_patterns": {"test": 10, "refactor": 7, "review": 4},
            "preferred_modes": ["cli", "tui"],
            "language_proficiency": {"python": 0.9, "typescript": 0.6},
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "working": self.working,
            "episodic": self.episodic,
            "semantic": self.semantic,
        }


def zskill_memory() -> ZSkillMemory:
    """创建一个预填充的记忆存储"""
    return ZSkillMemory()


# ═══════════════════════════════════════════════════════════════
# zskill_manifest — 各境界 SkillManifest
# ═══════════════════════════════════════════════════════════════

class ZSkillManifest:
    """预先生成的各境界技能清单"""

    LEVELS = ["novice", "apprentice", "practitioner", "journeyman", "master"]

    def __init__(self) -> None:
        self.manifests: Dict[str, Dict[str, Any]] = {}
        self._seed()

    def _seed(self) -> None:
        for i, level in enumerate(self.LEVELS):
            self.manifests[level] = {
                "name": f"{level}_skill",
                "level": level,
                "level_index": i,
                "xp": i * 100,
                "proficiency": round(0.3 + i * 0.15, 2),
                "stability": round(0.5 + i * 0.1, 2),
                "satisfaction": round(0.4 + i * 0.12, 2),
                "responsiveness": round(0.6 + i * 0.08, 2),
                "memory": round(0.3 + i * 0.14, 2),
                "interactions": i * 10 + 5,
            }

    def get(self, level: str) -> Dict[str, Any]:
        return self.manifests.get(level, self.manifests["novice"])


def zskill_manifest() -> ZSkillManifest:
    """创建一个预填充的技能清单"""
    return ZSkillManifest()


# ═══════════════════════════════════════════════════════════════
# zskill_bus — 带注册 Agent 的 MessageBus
# ═══════════════════════════════════════════════════════════════

class ZSkillBus:
    """模拟的 MessageBus，含 7 个预注册 Agent"""

    def __init__(self) -> None:
        self.agents: Dict[str, Dict[str, Any]] = {}
        self.messages: List[Dict[str, Any]] = []
        self._seed()

    def _seed(self) -> None:
        roles = ["coordinator", "architect", "developer", "analyzer",
                  "tester", "reviewer", "documenter"]
        for i, role in enumerate(roles):
            self.agents[role] = {
                "id": f"agent_{i:02d}",
                "role": role,
                "status": "idle",
                "skills": [role, "communication"],
                "priority": len(roles) - i,
            }

    def send(self, sender: str, recipient: str, msg_type: str,
             payload: dict) -> None:
        self.messages.append({
            "from": sender,
            "to": recipient,
            "type": msg_type,
            "payload": payload,
            "id": f"msg_{len(self.messages):04d}",
        })

    def count_by_type(self, msg_type: str) -> int:
        return sum(1 for m in self.messages if m["type"] == msg_type)


def zskill_bus() -> ZSkillBus:
    """创建一个带 7 预注册 Agent 的消息总线"""
    return ZSkillBus()


# ═══════════════════════════════════════════════════════════════
# zskill_clean_slate — 完全隔离的临时环境
# ═══════════════════════════════════════════════════════════════

class ZSkillCleanSlate:
    """完全隔离的临时环境，跨模块共享"""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root
        self.memory = ZSkillMemory()
        self.manifest = ZSkillManifest()
        self.bus = ZSkillBus()

    def cleanup(self) -> None:
        self._tmp.cleanup()

    def __enter__(self) -> "ZSkillCleanSlate":
        return self

    def __exit__(self, *args: Any) -> None:
        self.cleanup()


def zskill_clean_slate() -> ZSkillCleanSlate:
    """创建一个完全隔离的临时环境"""
    return ZSkillCleanSlate()


# ═══════════════════════════════════════════════════════════════
# zskill_mock_llm — Mock LLM 响应
# ═══════════════════════════════════════════════════════════════

class ZSkillMockLLM:
    """Mock LLM 响应，防止测试中的外部调用"""

    def __init__(self) -> None:
        self.call_count = 0
        self.history: list[dict] = []
        self.responses: dict[str, str] = {
            "reflect": "反思完成。用户当前专注于测试改进，建议继续迭代。",
            "predict": "基于近期模式分析，下一步预期为: 框架骨架测试。",
            "analyze": "分析完成: 代码结构合理，测试覆盖率待提升。",
            "greet": "您好！我是 ZenSkill 助手，有什么可以帮您的？",
        }
        self.default_response = "Mock LLM 响应。"

    def complete(self, prompt: str, **kwargs: Any) -> str:
        self.call_count += 1
        entry = {"prompt": prompt[:100], **kwargs}
        self.history.append(entry)
        # 匹配关键词
        for key, resp in self.responses.items():
            if key in prompt.lower():
                return resp
        return self.default_response

    def chat(self, messages: list[dict], **kwargs: Any) -> str:
        self.call_count += 1
        last = messages[-1]["content"][:100] if messages else ""
        self.history.append({"messages": len(messages), "last": last})
        for key, resp in self.responses.items():
            if key in last.lower():
                return resp
        return self.default_response


def zskill_mock_llm() -> ZSkillMockLLM:
    """创建一个 Mock LLM 实例"""
    return ZSkillMockLLM()
