"""
ZenThink 动态规则加载器

从 zenthink/ 知识库 markdown 文件中提取结构化感知规则，
供 PerceptionEngine 使用。支持热更新（文件变更时自动重解析）。

设计原则:
- 硬编码规则作为 fallback（zenthink 目录不可用时）
- 缓存 + mtime 检测，避免重复解析
- 规则格式兼容 perception_engine.py 的 SOUL_RULES/TOOL_RULES/...
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class ZenThinkLoader:
    """zenthink 知识库 → 结构化感知规则"""

    def __init__(self, zenthink_dir: Optional[str] = None):
        if zenthink_dir:
            self._dir = Path(zenthink_dir)
        else:
            # 自动探测: 项目根/zenthink 或 zenskill 包上级
            candidates = [
                Path(__file__).parent.parent / "zenthink",
                Path.cwd() / "zenthink",
            ]
            self._dir = next((c for c in candidates if c.exists()), None)
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_mtimes: Dict[str, float] = {}

    @property
    def available(self) -> bool:
        return self._dir is not None and self._dir.exists()

    def get_rules(self, force_reload: bool = False) -> Dict[str, Any]:
        """获取所有规则（兼容 perception_engine 格式）

        Returns:
            {
                "soul_rules": [...],
                "tool_rules": [...],
                "safeguard_rules": [...],
                "workflow_patterns": {...},
                "pdca_triggers": {...},
            }
        """
        if not self.available:
            return self._fallback_rules()

        if not force_reload and self._cache and not self._needs_reload():
            return self._cache

        rules = {
            "soul_rules": self._extract_soul_rules(),
            "tool_rules": self._extract_tool_rules(),
            "safeguard_rules": self._extract_safeguard_rules(),
            "workflow_patterns": self._extract_workflow_patterns(),
            "pdca_triggers": self._extract_pdca_triggers(),
        }
        self._cache = rules
        self._cache_mtimes = self._scan_mtimes()
        return rules

    def get_zenloop_mapping(self) -> Dict[str, str]:
        """从 methodology/zenloop/ 提取 5层映射"""
        mapping = {}
        loops_dir = self._dir / "methodology" / "zenloop" / "loops"
        if loops_dir.exists():
            for f in sorted(loops_dir.glob("L[1-5]_*.md")):
                try:
                    content = f.read_text()
                    # 提取标题
                    title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
                    if title_match:
                        key = f.name.split("_", 1)[0]  # L1, L2, ...
                        mapping[key] = title_match.group(1).strip()
                except Exception:
                    pass
        return mapping

    # ═══════════════════════════════════════════════════════════════
    # Rule Extractors
    # ═══════════════════════════════════════════════════════════════

    def _extract_soul_rules(self) -> List[Dict]:
        """从 rules/soul-core.md 提取安全模式"""
        rules = list(self._fallback_rules()["soul_rules"])  # 基础规则
        soul_file = self._dir / "rules" / "soul-core.md"
        if not soul_file.exists():
            return rules

        content = soul_file.read_text()

        # 提取"公理"部分的约束
        axioms = re.findall(r'\d+\.\s*\*?\*?([^*\n]+)\*?\*?\s*[：:]\s*(.+)', content)
        for keyword, description in axioms:
            if any(w in keyword + description for w in ["德不可失", "隐私", "保护"]):
                rules.append({
                    "id": "soul-axiom-privacy",
                    "pattern": ["~/.ssh/", ".env", "credentials", "token", "secret"],
                    "severity": "high",
                    "message": "操作可能涉及敏感信息 — 请确认未泄露凭据",
                })

        # 提取修炼体系作为阈值参考
        stage_match = re.findall(r'\|\s*([一二三四五六])[··](.+?)\s*\|\s*(.+?)\s*\|\s*(\d+)次', content)
        for _, name, _, threshold in stage_match:
            # 这些是参考数据，不直接生成规则
            pass

        return rules

    def _extract_tool_rules(self) -> List[Dict]:
        """从 rules/tools-core.md 提取工具使用建议"""
        rules = list(self._fallback_rules()["tool_rules"])
        tools_file = self._dir / "rules" / "tools-core.md"
        if not tools_file.exists():
            return rules

        content = tools_file.read_text()

        # 提取工具名称和最佳实践
        tool_sections = re.findall(r'###\s+(.+?)\n(.*?)(?=###|\Z)', content, re.DOTALL)
        for tool_name, section in tool_sections:
            tool_name = tool_name.strip().strip("`")
            # 提取"不要"/"避免"/"注意"模式
            cautions = re.findall(r'[⚠️]*\s*(?:不要|避免|注意|谨慎)[：:]*\s*(.+)', section)
            if cautions and len(rules) < 15:  # 限制规则数量
                rules.append({
                    "id": f"tool-caution-{tool_name.lower().replace(' ', '-')}",
                    "condition": {"tool_name_used": tool_name},
                    "suggestion": cautions[0][:80],
                })

        return rules

    def _extract_safeguard_rules(self) -> List[Dict]:
        """从 rules/safeguard-core.md 提取安全阈值"""
        rules = list(self._fallback_rules()["safeguard_rules"])
        safeguard_file = self._dir / "rules" / "safeguard-core.md"
        if not safeguard_file.exists():
            return rules

        content = safeguard_file.read_text()

        # 提取时长/频率限制
        time_limits = re.findall(r'(\d+)\s*(?:分钟|min)', content)
        if time_limits:
            # 取最小阈值作为疲劳提醒
            min_limit = min(int(t) for t in time_limits)
            if min_limit < 120:  # 合理范围
                for i, rule in enumerate(rules):
                    if rule["id"] == "safeguard-fatigue":
                        rules[i] = {**rule, "condition": {**rule["condition"], "elapsed_min_gt": min_limit}}
                        break

        return rules

    def _extract_workflow_patterns(self) -> Dict:
        """从 workflows/*.md 提取工作流序列"""
        patterns = dict(self._fallback_rules()["workflow_patterns"])
        workflows_dir = self._dir / "workflows"
        if not workflows_dir.exists():
            return patterns

        # 从每个 workflow 文件提取步骤
        for wf_file in sorted(workflows_dir.glob("workflow-*.md")):
            try:
                content = wf_file.read_text()
                # 提取步骤列表（数字序号）
                steps = re.findall(r'^\d+\.\s+(?:`([^`]+)`|调用\s*(?:`([^`]+)`)|([A-Z][a-z]+))',
                                   content, re.MULTILINE)
                tool_seq = []
                for match in steps:
                    tool = match[0] or match[1] or match[2]
                    if tool and tool in ("Read", "Edit", "Write", "Bash", "Grep", "Glob",
                                         "Task", "Agent", "WebSearch", "WebFetch"):
                        tool_seq.append(tool)

                if len(tool_seq) >= 2:
                    wf_name = wf_file.stem.replace("workflow-", "")
                    if wf_name not in patterns:
                        patterns[wf_name] = {
                            "ideal": tool_seq,
                            "deviation": {},
                        }

                # 提取"常见错误"/"陷阱"
                pitfalls = re.findall(r'[⚠️]*\s*(?:常见错误|陷阱|注意)[：:]\s*(.+)', content)
                for pitfall in pitfalls:
                    dev_key = pitfall[:20].lower().replace(" ", "_")
                    patterns[wf_name]["deviation"][dev_key] = pitfall[:80]

            except Exception:
                pass

        return patterns

    def _extract_pdca_triggers(self) -> Dict:
        """从 methodology/pdca/ 提取 PDCA 触发点"""
        triggers = dict(self._fallback_rules()["pdca_triggers"])
        pdca_file = self._dir / "methodology" / "pdca" / "pdca-framework.md"
        if not pdca_file.exists():
            return triggers

        content = pdca_file.read_text()

        # 提取数值触发点
        check_match = re.search(r'每\s*(\d+)\s*次', content)
        if check_match:
            n = int(check_match.group(1))
            triggers["check"] = {"every_n_tools": n, "message": f"建议花 1 分钟回顾最近 {n} 次操作的质量"}

        session_match = re.search(r'会话.*?(\d+)\s*(?:分钟|min)', content)
        if session_match:
            triggers["session_mark"] = int(session_match.group(1))

        return triggers

    # ═══════════════════════════════════════════════════════════════
    # Internal
    # ═══════════════════════════════════════════════════════════════

    def _fallback_rules(self) -> Dict[str, Any]:
        """硬编码 fallback 规则（与 perception_engine.py 保持一致）"""
        return {
            "soul_rules": [
                {
                    "id": "soul-danger-command",
                    "pattern": ["rm -rf", "sudo rm", "dd if=", "mkfs.", ":(){ :|:& };:"],
                    "severity": "critical",
                    "message": "检测到潜在危险命令 — 请确认操作意图并备份数据",
                },
                {
                    "id": "soul-sensitive-path",
                    "pattern": ["/etc/", "/boot/", "~/.ssh/", "~/.gnupg/"],
                    "severity": "high",
                    "message": "操作涉及敏感系统路径 — 建议检查影响范围",
                },
            ],
            "tool_rules": [
                {
                    "id": "tool-read-heavy",
                    "condition": {"recent_tools_match": ["Read", "Read", "Read"]},
                    "suggestion": "连续 3 次 Read，如需修改可直接用 Edit",
                },
                {
                    "id": "tool-bash-heavy",
                    "condition": {"recent_tools_match": ["Bash", "Bash", "Bash"]},
                    "suggestion": "连续 3 次 Bash，考虑是否需要写脚本自动化",
                },
                {
                    "id": "tool-no-edit",
                    "condition": {"tool_count_gt": 20, "tools_missing": ["Edit", "Write"]},
                    "suggestion": "已 20 次操作但未 Edit/Write — 是否需要修改文件？",
                },
            ],
            "safeguard_rules": [
                {
                    "id": "safeguard-fatigue",
                    "condition": {"elapsed_min_gt": 90, "tool_count_gt": 50},
                    "severity": "medium",
                    "message": "已持续 {elapsed:.0f} 分钟/{count} 次操作，建议休息 5 分钟",
                },
                {
                    "id": "safeguard-unusual-hour",
                    "condition": {"hour_not_in": [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]},
                    "severity": "low",
                    "message": "当前是深夜时段 ({hour:02d}:{minute:02d})，注意休息",
                },
            ],
            "workflow_patterns": {
                "doc-edit": {
                    "ideal": ["Read", "Edit", "Write"],
                    "deviation": {
                        "skip_read": "跳过 Read 直接 Edit — 建议先了解文件上下文",
                        "no_write": "Edit 后未 Write — 可能忘记保存",
                    },
                },
                "commit": {
                    "ideal": ["Edit", "Bash", "Bash"],
                    "deviation": {
                        "no_test": "Edit + Bash 后未运行测试",
                    },
                },
            },
            "pdca_triggers": {
                "plan": {"every_n_tools": 10, "message": "已完成 10 次操作 — 检查是否偏离原计划"},
                "check": {"every_n_tools": 20, "message": "建议花 1 分钟回顾最近 20 次操作的质量"},
                "act": {"on_session_end": True, "message": "会话结束 — 生成改进建议"},
            },
        }

    def _scan_mtimes(self) -> Dict[str, float]:
        """扫描所有 zenthink 文件的修改时间"""
        mtimes = {}
        if self._dir:
            for f in self._dir.rglob("*.md"):
                try:
                    mtimes[str(f)] = f.stat().st_mtime
                except OSError:
                    pass
        return mtimes

    def _needs_reload(self) -> bool:
        """检查是否有文件变更"""
        current = self._scan_mtimes()
        return current != self._cache_mtimes


# 全局单例
_loader: Optional[ZenThinkLoader] = None


def get_zenthink_loader() -> ZenThinkLoader:
    """获取全局 ZenThinkLoader 实例"""
    global _loader
    if _loader is None:
        _loader = ZenThinkLoader()
    return _loader
