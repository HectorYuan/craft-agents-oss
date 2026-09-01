"""
ZenThink Profile Reader — 统一读取接口

封装 zenthink/ 知识库的 profile/readers/，提供 soul/user/tools/memory
的结构化数据读取。供 mirror profile 和 skill info 命令使用。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class ProfileReader:
    """ZenThink 知识库统一读取器"""

    def __init__(self, zenthink_dir: Optional[str] = None):
        if zenthink_dir:
            self._dir = Path(zenthink_dir)
        else:
            candidates = [
                Path(__file__).parent.parent / "zenthink",
                Path.cwd() / "zenthink",
            ]
            self._dir = next((c for c in candidates if c.exists()), None)

    @property
    def available(self) -> bool:
        return self._dir is not None and self._dir.exists()

    def read_soul(self) -> Dict[str, Any]:
        """读取灵魂契约 (rules/soul-core.md) → 结构化数据"""
        soul_file = self._dir / "rules" / "soul-core.md"
        if not soul_file.exists():
            return {}
        content = soul_file.read_text()

        data = {"source": str(soul_file)}

        # 提取本体论
        onto = re.search(r'##\s*一、本体论\s*\n(.*?)(?=##)', content, re.DOTALL)
        if onto:
            data["ontology"] = onto.group(1).strip()[:300]

        # 提取修炼体系
        stages = re.findall(
            r'\|\s*([一二三四五六])[··](.+?)\s*\|\s*(.+?)\s*\|\s*(\d+)次',
            content
        )
        if stages:
            data["cultivation"] = [
                {"rank": s[0], "name": s[1].strip(), "title": s[2].strip(), "threshold": int(s[3])}
                for s in stages
            ]

        # 提取公理
        axioms = re.findall(r'\d+\.\s*\*?\*?([^*\n]+)\*?\*?\s*[：:]\s*(.+)', content)
        if axioms:
            data["axioms"] = [{"name": a[0].strip(), "description": a[1].strip()[:200]} for a in axioms]

        # 提取三层记忆
        mem_match = re.search(r'##\s*三、识海架构.*?\n(.*?)(?=##)', content, re.DOTALL)
        if mem_match:
            layers = re.findall(r'\|\s*(L[123])\s*\|\s*(.+?)\s*\|', mem_match.group(1))
            if layers:
                data["memory_architecture"] = [{"layer": l[0], "name": l[1].strip()} for l in layers]

        return data

    def read_tools(self) -> Dict[str, Any]:
        """读取工具定义 (rules/tools-core.md) → 结构化数据"""
        tools_file = self._dir / "rules" / "tools-core.md"
        if not tools_file.exists():
            return {}
        content = tools_file.read_text()

        data = {"source": str(tools_file)}

        # 提取工具名称
        tool_names = re.findall(r'###\s+`?([A-Za-z_]+)`?', content)
        if tool_names:
            data["covered_tools"] = tool_names

        # 提取方法论
        sections = re.findall(r'##\s+(.+?)\n(.*?)(?=##|\Z)', content, re.DOTALL)
        for title, body in sections:
            key = title.strip().replace(" ", "_").lower()
            # 取前200字作为摘要
            data[key] = body.strip()[:200]

        return data

    def read_safeguard(self) -> Dict[str, Any]:
        """读取安全护栏 (rules/safeguard-core.md) → 结构化数据"""
        sg_file = self._dir / "rules" / "safeguard-core.md"
        if not sg_file.exists():
            return {}
        content = sg_file.read_text()

        data = {"source": str(sg_file)}

        # 提取防御层级
        levels = re.findall(r'##\s+(.+?防御.*?|.+?检测.*?)\n(.*?)(?=##|\Z)', content, re.DOTALL)
        for title, body in levels:
            key = title.strip().replace(" ", "_").lower()
            data[key] = body.strip()[:200]

        return data

    def read_memory(self) -> Dict[str, Any]:
        """读取记忆状态 (调用 SkillStateManager)"""
        try:
            from zenskill.core.paths import SkillStateManager
            sm = SkillStateManager("zenskill-core")
            ss = sm.load()
            episodes = ss.get("episodes", [])
            return {
                "total_episodes": len(episodes),
                "level": ss.get("level", "NOVICE"),
                "usage_count": ss.get("usage_count", 0),
            }
        except Exception:
            return {}

    def read_all(self) -> Dict[str, Any]:
        """读取全部 profile"""
        return {
            "soul": self.read_soul(),
            "tools": self.read_tools(),
            "safeguard": self.read_safeguard(),
            "memory": self.read_memory(),
        }

    def get_summary(self) -> str:
        """生成可读摘要"""
        parts = []
        soul = self.read_soul()
        if soul.get("ontology"):
            # 提取核心身份
            id_match = re.search(r'\*\*我[是为是]\s*(.+?)\*\*', soul["ontology"])
            if id_match:
                parts.append(f"本体: {id_match.group(1)}")
        if soul.get("cultivation"):
            stages = soul["cultivation"]
            parts.append(f"修炼: {len(stages)} 重境界")

        tools = self.read_tools()
        if tools.get("covered_tools"):
            parts.append(f"工具: {', '.join(tools['covered_tools'][:5])}")

        mem = self.read_memory()
        if mem.get("total_episodes"):
            parts.append(f"记忆: {mem['total_episodes']} 条 | 等级: {mem.get('level', '?')}")

        return " | ".join(parts) if parts else "ZenThink profile (无数据)"
