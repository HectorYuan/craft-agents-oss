"""
感知规则引擎 (Perception System Stage A)

基于 zenthink 知识库的程序化规则引擎。
将 zenthink 的规则/工作流/方法论映射为可执行的感知检查。
"""

from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════
# zenthink → 结构化规则
# ═══════════════════════════════════════════════════════════════

# rules/soul-core: 灵魂契约 → 感知告警
SOUL_RULES = [
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
    {
        "id": "soul-mass-delete",
        "pattern": ["git clean -fd", "git reset --hard", "find . -delete"],
        "severity": "medium",
        "message": "批量删除/重置操作 — 确认没有未保存的更改",
    },
]

# rules/tools-core: 工具能力边界 → 使用建议
TOOL_RULES = [
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
]

# rules/safeguard-core: 安全护栏 → 异常检测
SAFEGUARD_RULES = [
    {
        "id": "safeguard-fatigue",
        "condition": {"elapsed_min_gt": 90, "tool_count_gt": 50},
        "severity": "medium",
        "message": "已持续 {elapsed:.0f} 分钟/{count} 次操作，建议休息 5 分钟",
    },
    {
        "id": "safeguard-error-spike",
        "condition": {"error_rate_gt": 0.15},
        "severity": "high",
        "message": "错误率异常偏高 ({rate:.0%})，建议暂停检查问题",
    },
    {
        "id": "safeguard-unusual-hour",
        "condition": {"hour_not_in": [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]},
        "severity": "low",
        "message": "当前是深夜时段 ({hour:02d}:{minute:02d})，注意休息",
    },
]

# workflows/: 工作流模板 → 序列检测
WORKFLOW_PATTERNS = {
    "doc-edit": {
        "ideal": ["Read", "Edit", "Write"],
        "deviation": {
            "skip_read": "跳过 Read 直接 Edit — 建议先了解文件上下文",
            "no_write": "Edit 后未 Write — 可能忘记保存",
        },
    },
    "crisis": {
        "ideal": ["Read", "Bash", "Read", "Edit", "Bash"],
        "deviation": {
            "skip_verify": "修复后未验证 — 建议运行测试确认",
            "no_read_first": "未 Read 直接修改 — 建议先诊断问题",
        },
    },
    "commit": {
        "ideal": ["Edit", "Bash", "Bash"],
        "deviation": {
            "no_test": "Edit + Bash 后未运行测试 — 建议 git commit 前验证",
        },
    },
}

# methodology/pdca: PDCA 循环 → 反思触发
PDCA_TRIGGERS = {
    "plan": {"every_n_tools": 10, "message": "已完成 10 次操作 — 检查是否偏离原计划"},
    "do": {"every_n_tools": 5, "message": None},  # silent tracking
    "check": {"every_n_tools": 20, "message": "建议花 1 分钟回顾最近 20 次操作的质量"},
    "act": {"on_session_end": True, "message": "会话结束 — 生成改进建议"},
}


# ═══════════════════════════════════════════════════════════════
# 感知引擎核心
# ═══════════════════════════════════════════════════════════════

class PerceptionEngine:
    """感知规则引擎 — 评估当前上下文是否触发 zenthink 规则

    v1.3: 支持从 ZenThinkLoader 动态加载规则，硬编码规则作为 fallback。
    """

    def __init__(self, use_zenthink: bool = True):
        self._use_zenthink = use_zenthink
        self._load_rules()

    def _load_rules(self) -> None:
        """加载规则: ZenThink 优先，硬编码 fallback"""
        loaded = False
        if self._use_zenthink:
            try:
                from .zenthink_loader import get_zenthink_loader
                loader = get_zenthink_loader()
                if loader.available:
                    rules = loader.get_rules()
                    self.soul_rules = rules["soul_rules"]
                    self.tool_rules = rules["tool_rules"]
                    self.safeguard_rules = rules["safeguard_rules"]
                    self.workflows = rules["workflow_patterns"]
                    self.pdca = rules["pdca_triggers"]
                    loaded = True
            except Exception:
                pass

        if not loaded:
            self.soul_rules = SOUL_RULES
            self.tool_rules = TOOL_RULES
            self.safeguard_rules = SAFEGUARD_RULES
            self.workflows = WORKFLOW_PATTERNS
            self.pdca = PDCA_TRIGGERS

    def reload_rules(self) -> bool:
        """强制从 ZenThink 重载规则 (CLI --reload-rules)"""
        try:
            from .zenthink_loader import get_zenthink_loader
            loader = get_zenthink_loader()
            if loader.available:
                rules = loader.get_rules(force_reload=True)
                self.soul_rules = rules["soul_rules"]
                self.tool_rules = rules["tool_rules"]
                self.safeguard_rules = rules["safeguard_rules"]
                self.workflows = rules["workflow_patterns"]
                self.pdca = rules["pdca_triggers"]
                return True
        except Exception:
            pass
        return False

    @property
    def rule_source(self) -> str:
        """当前规则来源"""
        try:
            from .zenthink_loader import get_zenthink_loader
            loader = get_zenthink_loader()
            if loader.available and self._use_zenthink:
                return f"zenthink ({loader._dir})"
        except Exception:
            pass
        return "built-in (hardcoded)"

    def evaluate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """全量评估: 检查所有规则

        context = {
            "tool_count": int,
            "elapsed_min": float,
            "recent_tools": [str],
            "current_hour": int,
            "last_command": str,
            "error_rate": float,
            "session_id": str,
        }
        """
        return {
            "alerts": self._check_soul(context) + self._check_safeguard(context),
            "suggestions": self._check_tools(context),
            "workflow": self._check_workflow(context),
            "pdca": self._check_pdca(context),
        }

    def _check_soul(self, ctx: Dict) -> List[Dict]:
        """检查灵魂契约规则（危险操作）"""
        alerts = []
        last_cmd = ctx.get("last_command", "")
        for rule in self.soul_rules:
            for pattern in rule["pattern"]:
                if pattern in last_cmd:
                    alerts.append({
                        "id": rule["id"],
                        "severity": rule["severity"],
                        "message": rule["message"],
                        "source": "soul-core",
                    })
                    break
        return alerts

    def _check_safeguard(self, ctx: Dict) -> List[Dict]:
        """检查安全护栏规则（疲劳/错误/异常时段）"""
        alerts = []
        for rule in self.safeguard_rules:
            cond = rule["condition"]
            # 疲劳检测
            if "elapsed_min_gt" in cond and "tool_count_gt" in cond:
                if ctx.get("elapsed_min", 0) > cond["elapsed_min_gt"] and \
                   ctx.get("tool_count", 0) > cond["tool_count_gt"]:
                    alerts.append({
                        "id": rule["id"],
                        "severity": rule["severity"],
                        "message": rule["message"].format(
                            elapsed=ctx.get("elapsed_min", 0),
                            count=ctx.get("tool_count", 0),
                        ),
                        "source": "safeguard-core",
                    })
            # 错误率异常
            if "error_rate_gt" in cond:
                if ctx.get("error_rate", 0) > cond["error_rate_gt"]:
                    alerts.append({
                        "id": rule["id"],
                        "severity": rule["severity"],
                        "message": rule["message"].format(rate=ctx.get("error_rate", 0)),
                        "source": "safeguard-core",
                    })
            # 异常时段
            if "hour_not_in" in cond:
                hour = ctx.get("current_hour", 12)
                if hour not in cond["hour_not_in"]:
                    alerts.append({
                        "id": rule["id"],
                        "severity": rule["severity"],
                        "message": rule["message"].format(
                            hour=hour, minute=ctx.get("current_minute", 0)),
                        "source": "safeguard-core",
                    })
        return alerts

    def _check_tools(self, ctx: Dict) -> List[Dict]:
        """检查工具使用规则"""
        suggestions = []
        recent = ctx.get("recent_tools", [])
        tc = ctx.get("tool_count", 0)
        for rule in self.tool_rules:
            cond = rule["condition"]
            if "recent_tools_match" in cond:
                pattern = cond["recent_tools_match"]
                if len(recent) >= len(pattern):
                    if recent[-len(pattern):] == pattern:
                        suggestions.append({
                            "id": rule["id"], "suggestion": rule["suggestion"],
                            "source": "tools-core",
                        })
            if "tool_count_gt" in cond and "tools_missing" in cond:
                if tc > cond["tool_count_gt"]:
                    missing = [t for t in cond["tools_missing"] if t not in recent]
                    if missing:
                        suggestions.append({
                            "id": rule["id"], "suggestion": rule["suggestion"],
                            "source": "tools-core",
                        })
        return suggestions

    def _check_workflow(self, ctx: Dict) -> Dict:
        """检测工作流偏差"""
        recent = ctx.get("recent_tools", [])
        result = {"current_workflow": None, "deviations": []}

        best_match = None
        best_score = 0
        for wf_name, wf in self.workflows.items():
            ideal = wf["ideal"]
            score = self._sequence_similarity(recent[-len(ideal):], ideal)
            if score > best_score:
                best_score = score
                best_match = wf_name

        if best_match and best_score > 0.5:
            result["current_workflow"] = best_match
            # 检测偏差
            wf = self.workflows[best_match]
            if best_match == "doc-edit":
                if "Edit" in recent[-3:] and "Read" not in recent[-4:-1]:
                    result["deviations"].append(wf["deviation"]["skip_read"])
            elif best_match == "crisis":
                if "Edit" in recent[-2:] and "Bash" not in recent[-3:]:
                    result["deviations"].append(wf["deviation"]["skip_verify"])
            elif best_match == "commit":
                if "Edit" in recent[-3:] and "Bash" in recent[-2:]:
                    result["deviations"].append(wf["deviation"]["no_test"])

        return result

    def _check_pdca(self, ctx: Dict) -> List[Dict]:
        """检查 PDCA 触发条件"""
        results = []
        tc = ctx.get("tool_count", 0)
        for phase, trigger in self.pdca.items():
            n = trigger.get("every_n_tools")
            if n and tc > 0 and tc % n == 0 and trigger.get("message"):
                results.append({
                    "phase": phase,
                    "message": trigger["message"],
                    "source": "pdca",
                })
        return results

    def context_card(self, ctx: Dict) -> str:
        """生成感知上下文卡片（注入到 Claude 对话）"""
        result = self.evaluate(ctx)
        parts = ["[ZenSkill Perception]"]

        # 工作流状态
        wf = result.get("workflow", {})
        if wf.get("current_workflow"):
            parts.append(f"Workflow: {wf['current_workflow']}")
            for dev in wf.get("deviations", []):
                parts.append(f"⚠️ {dev}")

        # 告警
        for alert in result.get("alerts", [])[:2]:
            sev = {"critical": "🚨", "high": "🔴", "medium": "🟡", "low": "🔵"}
            icon = sev.get(alert["severity"], "⚪")
            parts.append(f"{icon} {alert['message']}")

        # 建议
        for sug in result.get("suggestions", [])[:1]:
            parts.append(f"💡 {sug['suggestion']}")

        # PDCA
        for p in result.get("pdca", [])[:1]:
            parts.append(f"🔄 [{p['phase']}] {p['message']}")

        return " | ".join(parts)

    @staticmethod
    def _sequence_similarity(actual: List[str], ideal: List[str]) -> float:
        """计算工具序列与理想工作流的相似度"""
        if not actual or not ideal:
            return 0.0
        matches = sum(1 for a, b in zip(actual, ideal) if a == b)
        return matches / max(len(ideal), 1)
