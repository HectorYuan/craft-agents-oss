"""
工作流模式识别 (Phase 9D)

从 events.jsonl 和 history.jsonl 中识别用户的行为模式：
- 工具序列链（编码→测试→提交）
- 工作时间段分布
- 深度工作检测
- 项目切换频率
- 工作流模式分类（编码-测试-重构、研究-写作-修订等）
- 瓶颈检测（停顿、卡点）
- 优化建议
- 习惯养成追踪

CLI 命令：
    zenskill workflow patterns      # 发现工作流模式
    zenskill workflow bottlenecks    # 查看工作流瓶颈
    zenskill workflow optimize       # 获取工作流优化建议
"""

import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── 已知工作流模式定义 ──

WORKFLOW_PATTERNS: Dict[str, Dict[str, Any]] = {
    "编码-测试-重构": {
        "chain": ["Edit", "Bash", "Read"],
        "description": "经典开发循环：编写代码 → 运行测试 → 检查结果",
        "tags": ["development", "testing", "iteration"],
        "efficiency": "high",
    },
    "学习-实现": {
        "chain": ["Read", "Write", "Bash"],
        "description": "学习新知识：阅读文档 → 编写代码 → 运行验证",
        "tags": ["learning", "implementation"],
        "efficiency": "medium",
    },
    "调试-修复": {
        "chain": ["Bash", "Read", "Edit"],
        "description": "排查问题：运行查看错误 → 阅读代码 → 修改修复",
        "tags": ["debugging", "fixing"],
        "efficiency": "high",
    },
    "探索-分析": {
        "chain": ["Read", "Bash", "Read"],
        "description": "探索代码库：阅读源码 → 运行观察 → 深入分析",
        "tags": ["exploration", "analysis"],
        "efficiency": "medium",
    },
    "研究-写作": {
        "chain": ["Read", "Write", "Read"],
        "description": "研究性写作：阅读资料 → 撰写内容 → 复查修订",
        "tags": ["research", "writing", "documentation"],
        "efficiency": "high",
    },
    "自动化-验证": {
        "chain": ["Edit", "Write", "Bash"],
        "description": "编写自动化脚本 → 记录结果 → 执行验证",
        "tags": ["automation", "testing"],
        "efficiency": "high",
    },
}

# ── 工作流模式置信度阈值 ──
PATTERN_MATCH_THRESHOLD = 0.3


class WorkflowAnalyzer:
    """工作流模式分析器"""

    def __init__(self):
        self._events_file = Path.home() / ".zenskill" / "mirroring" / "events.jsonl"
        self._history_file = Path.home() / ".claude" / "history.jsonl"

    def analyze(self) -> Dict[str, Any]:
        """全量分析，返回工作流画像"""
        events = self._load_events()
        history = self._load_history()

        return {
            "tool_chains": self._detect_tool_chains(events),
            "work_segments": self._detect_work_segments(history),
            "deep_work": self._detect_deep_work(history),
            "project_rhythm": self._detect_project_rhythm(history),
        }

    # ── 数据加载 ──

    def _load_events(self) -> List[Dict]:
        events = []
        if self._events_file.exists():
            for line in open(self._events_file):
                try:
                    events.append(json.loads(line.strip()))
                except Exception:
                    pass
        return events

    def _load_history(self) -> List[Dict]:
        entries = []
        if self._history_file.exists():
            for line in open(self._history_file):
                try:
                    entries.append(json.loads(line.strip()))
                except Exception:
                    pass
        return entries

    # ── 模式检测 ──

    def _detect_tool_chains(self, events: List[Dict]) -> Dict[str, Any]:
        """检测工具使用序列链

        识别常见模式：
        - Edit → Bash → Read (测试验证)
        - Read → Write → Bash (学习实现)
        - Bash → Read → Edit (调试修复)
        """
        if not events:
            return {"chains": [], "top_chain": "none"}

        # 从事件中提取工具序列
        tools = []
        for e in events[-200:]:
            signal = e.get("signal", {})
            source = e.get("source", "")
            if source == "claude_code_history":
                continue
            # 从 signal keys 推断工具类型
            tool = self._infer_tool(signal)
            if tool:
                tools.append(tool)

        if len(tools) < 3:
            return {"chains": [], "top_chain": "insufficient_data"}

        # 滑动窗口：找 2-gram 和 3-gram 模式
        bigrams = Counter()
        trigrams = Counter()
        for i in range(len(tools) - 1):
            bigrams[(tools[i], tools[i + 1])] += 1
        for i in range(len(tools) - 2):
            trigrams[(tools[i], tools[i + 1], tools[i + 2])] += 1

        top_bigrams = bigrams.most_common(5)
        top_trigrams = trigrams.most_common(3)

        return {
            "total_tools": len(set(tools)),
            "total_actions": len(tools),
            "top_transitions": [
                {"from": a, "to": b, "count": c}
                for (a, b), c in top_bigrams
            ],
            "top_chains": [
                {"steps": list(steps), "count": c}
                for steps, c in top_trigrams if c >= 2
            ],
            "top_chain": " → ".join(top_trigrams[0][0]) if top_trigrams else "none",
        }

    def _infer_tool(self, signal: Dict) -> Optional[str]:
        """从信号推断工具类型"""
        # 检查信号中的已知字段
        for key in signal:
            if isinstance(signal[key], (int, float)):
                continue
            k = str(key).lower()
            v = str(signal[key]).lower() if not isinstance(signal[key], (dict, list)) else ""
            if "edit" in k or "edit" in v:
                return "Edit"
            if "read" in k or "read" in v:
                return "Read"
            if "bash" in k or "bash" in v or "command" in k:
                return "Bash"
            if "write" in k or "write" in v:
                return "Write"
            if "agent" in k or "agent" in v:
                return "Agent"
        return None

    def _detect_work_segments(self, history: List[Dict]) -> Dict[str, Any]:
        """检测工作时间段分布

        将一天分为 4 段，分析各时段的工作特征
        """
        if not history:
            return {}

        segments: Dict[str, Counter] = {
            "深夜(0-6)": Counter(),
            "上午(6-12)": Counter(),
            "下午(12-18)": Counter(),
            "晚上(18-24)": Counter(),
        }

        for entry in history:
            ts = entry.get("timestamp", 0)
            if not ts:
                continue
            try:
                hour = datetime.fromtimestamp(float(ts) / 1000).hour
            except Exception:
                continue

            project = Path(entry.get("project", "")).name or "unknown"
            if 0 <= hour < 6:
                segments["深夜(0-6)"][project] += 1
            elif 6 <= hour < 12:
                segments["上午(6-12)"][project] += 1
            elif 12 <= hour < 18:
                segments["下午(12-18)"][project] += 1
            else:
                segments["晚上(18-24)"][project] += 1

        total = sum(sum(c.values()) for c in segments.values()) or 1

        return {
            segment: {
                "count": sum(c.values()),
                "pct": round(sum(c.values()) / total * 100, 1),
                "top_project": c.most_common(1)[0][0] if c else "none",
            }
            for segment, c in segments.items()
        }

    def _detect_deep_work(self, history: List[Dict]) -> Dict[str, Any]:
        """检测深度工作时间段

        深度工作 = 连续 30 分钟以上无项目切换
        """
        if not history:
            return {}

        sessions: Dict[str, List[Tuple[float, str]]] = defaultdict(list)
        for entry in history:
            sid = entry.get("sessionId", "")
            ts = entry.get("timestamp", 0)
            proj = Path(entry.get("project", "")).name or "unknown"
            if sid and ts:
                sessions[sid].append((float(ts) / 1000, proj))

        deep_sessions = 0
        total_duration = 0.0
        for sid, events in sorted(sessions.items()):
            if len(events) < 3:
                continue
            events.sort()
            duration = events[-1][0] - events[0][0]
            if duration > 1800:  # 30 分钟
                deep_sessions += 1
                total_duration += duration

        return {
            "deep_sessions": deep_sessions,
            "total_deep_minutes": round(total_duration / 60, 0),
            "deep_work_ratio": round(deep_sessions / max(len(sessions), 1) * 100, 1),
            "total_sessions": len(sessions),
        }

    def _detect_project_rhythm(self, history: List[Dict]) -> Dict[str, Any]:
        """检测项目切换节奏

        分析用户在项目间切换的频率和模式
        """
        if not history:
            return {}

        projects = []
        switches = 0
        for entry in history:
            proj = Path(entry.get("project", "")).name or "unknown"
            if not projects or projects[-1] != proj:
                projects.append(proj)
                if len(projects) > 1 and projects[-1] != projects[-2]:
                    switches += 1

        proj_counts = Counter()
        for p in projects:
            proj_counts[p] += 1

        return {
            "total_switches": switches,
            "unique_projects": len(proj_counts),
            "top_projects": dict(proj_counts.most_common(3)),
            "switch_frequency": round(switches / max(len(projects), 1) * 100, 1),
            "style": "focus" if switches < len(projects) * 0.3 else
                     "balanced" if switches < len(projects) * 0.6 else "multitask",
        }

    # ── 9D 新增：工作流模式分类 ──

    def detect_patterns(self) -> Dict[str, Any]:
        """
        将检测到的工具链与已知工作流模式匹配，返回匹配结果

        Returns:
            {
                "patterns": [匹配到的工作流模式列表],
                "dominant": "最主要的工作流模式",
                "pattern_distribution": {模式名: 占比},
                "total_matched": 总匹配次数,
            }
        """
        events = self._load_events()
        tools = self._extract_tool_sequence(events)
        if len(tools) < 3:
            return {"patterns": [], "dominant": "none", "pattern_distribution": {}, "total_matched": 0}

        # 滑动窗口提取所有 3-gram
        trigrams = []
        for i in range(len(tools) - 2):
            trigrams.append((tools[i], tools[i + 1], tools[i + 2]))

        total_windows = len(trigrams)
        if total_windows == 0:
            return {"patterns": [], "dominant": "none", "pattern_distribution": {}, "total_matched": 0}

        # 匹配已知模式
        pattern_matches: Dict[str, int] = {}
        for pattern_name, pattern_def in WORKFLOW_PATTERNS.items():
            target = tuple(pattern_def["chain"])
            count = sum(1 for t in trigrams if t == target)
            if count > 0:
                pattern_matches[pattern_name] = count

        # 计算分布
        total_matched = sum(pattern_matches.values())
        distribution = {}
        for name, count in pattern_matches.items():
            distribution[name] = round(count / total_windows * 100, 1)

        # 找出主导模式
        dominant = max(pattern_matches, key=pattern_matches.get) if pattern_matches else "none"

        # 丰富结果信息
        patterns_with_meta = []
        for name, count in sorted(pattern_matches.items(), key=lambda x: -x[1]):
            pdef = WORKFLOW_PATTERNS.get(name, {})
            patterns_with_meta.append({
                "name": name,
                "count": count,
                "pct": round(count / total_windows * 100, 1),
                "description": pdef.get("description", ""),
                "tags": pdef.get("tags", []),
                "efficiency": pdef.get("efficiency", "medium"),
            })

        return {
            "patterns": patterns_with_meta,
            "dominant": dominant,
            "pattern_distribution": distribution,
            "total_matched": total_matched,
            "total_windows": total_windows,
            "unknown_ratio": round((total_windows - total_matched) / total_windows * 100, 1),
        }

    def _extract_tool_sequence(self, events: List[Dict]) -> List[str]:
        """从事件中提取工具序列"""
        tools = []
        for e in events[-500:]:
            signal = e.get("signal", {})
            source = e.get("source", "")
            if source == "claude_code_history":
                continue
            tool = self._infer_tool(signal)
            if tool:
                tools.append(tool)
        return tools


class BottleneckDetector:
    """
    工作流瓶颈检测器

    识别工作流中的停顿和卡点：
    - 高频错误工具：某工具失败率异常高
    - 长时间停留：在某个步骤停留时间过长
    - 重复循环：反复执行同一序列而未推进
    - 中断频率：工作中断后恢复的耗时
    - 项目切换代价：切换项目后的适应期
    """

    def __init__(self):
        self._events_file = Path.home() / ".zenskill" / "mirroring" / "events.jsonl"
        self._history_file = Path.home() / ".claude" / "history.jsonl"
        self._analyzer = WorkflowAnalyzer()

    def detect_all(self) -> Dict[str, Any]:
        """全量瓶颈检测"""
        events = self._analyzer._load_events()
        history = self._analyzer._load_history()

        return {
            "high_error_tools": self._detect_high_error_tools(events),
            "long_stalls": self._detect_long_stalls(history),
            "repetitive_loops": self._detect_repetitive_loops(events),
            "interruption_cost": self._detect_interruption_cost(history),
            "project_switch_cost": self._detect_project_switch_cost(history),
            "overall_score": self._compute_overall_score(events, history),
        }

    def _detect_high_error_tools(self, events: List[Dict]) -> Dict[str, Any]:
        """检测高频错误工具"""
        tool_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "fail": 0})
        for e in events:
            signal = e.get("signal", {})
            tool = self._analyzer._infer_tool(signal)
            if not tool:
                continue
            tool_stats[tool]["total"] += 1
            if not e.get("success", True):
                tool_stats[tool]["fail"] += 1

        problem_tools = []
        for tool, stats in sorted(tool_stats.items(), key=lambda x: -x[1]["fail"]):
            total = stats["total"]
            if total < 3:
                continue
            fail_rate = stats["fail"] / total
            if fail_rate >= 0.3:
                problem_tools.append({
                    "tool": tool,
                    "fail_rate": round(fail_rate, 2),
                    "fails": stats["fail"],
                    "total": total,
                    "severity": "high" if fail_rate >= 0.5 else "medium",
                })

        return {
            "problem_tools": problem_tools,
            "total_tools_checked": len(tool_stats),
            "has_bottleneck": len(problem_tools) > 0,
        }

    def _detect_long_stalls(self, history: List[Dict]) -> Dict[str, Any]:
        """检测长时间停留（会话内长时间无操作间隔）"""
        if not history:
            return {"stalls": [], "has_bottleneck": False}

        sessions: Dict[str, List[float]] = defaultdict(list)
        for entry in history:
            sid = entry.get("sessionId", "")
            ts = entry.get("timestamp", 0)
            if sid and ts:
                sessions[sid].append(float(ts) / 1000)

        all_gaps = []
        for sid, timestamps in sessions.items():
            if len(timestamps) < 3:
                continue
            timestamps.sort()
            for i in range(1, len(timestamps)):
                gap = timestamps[i] - timestamps[i - 1]
                if gap > 300:  # 5 分钟以上视为停顿
                    all_gaps.append({"session": sid, "gap_min": round(gap / 60, 1), "time": timestamps[i]})

        long_stalls = [g for g in all_gaps if g["gap_min"] > 15]
        return {
            "stalls": long_stalls[-10:],  # 最近 10 条
            "total_stalls": len(all_gaps),
            "long_stalls_count": len(long_stalls),
            "avg_gap_min": round(sum(g["gap_min"] for g in all_gaps) / len(all_gaps), 1) if all_gaps else 0,
            "has_bottleneck": len(long_stalls) >= 3,
        }

    def _detect_repetitive_loops(self, events: List[Dict]) -> Dict[str, Any]:
        """检测重复循环（反复执行同一工具序列）"""
        tools = self._analyzer._extract_tool_sequence(events)
        if len(tools) < 6:
            return {"loops": [], "has_bottleneck": False}

        # 检查 2-gram 是否过度集中
        bigrams = Counter()
        for i in range(len(tools) - 1):
            bigrams[(tools[i], tools[i + 1])] += 1

        total_bigrams = sum(bigrams.values())
        if total_bigrams == 0:
            return {"loops": [], "has_bottleneck": False}

        repetitive = []
        for (a, b), count in bigrams.most_common(3):
            ratio = count / total_bigrams
            if ratio >= 0.4:  # 某个转换占 40%+ 视为重复
                repetitive.append({
                    "transition": f"{a} → {b}",
                    "count": count,
                    "ratio": round(ratio, 2),
                })

        return {
            "loops": repetitive,
            "total_bigrams": total_bigrams,
            "has_bottleneck": len(repetitive) > 0,
        }

    def _detect_interruption_cost(self, history: List[Dict]) -> Dict[str, Any]:
        """检测中断成本（会话中断后恢复的耗时）"""
        if not history:
            return {"cost_min": 0, "has_bottleneck": False}

        sessions: Dict[str, List[float]] = defaultdict(list)
        for entry in history:
            sid = entry.get("sessionId", "")
            ts = entry.get("timestamp", 0)
            if sid and ts:
                sessions[sid].append(float(ts) / 1000)

        recovery_times = []
        for sid, timestamps in sessions.items():
            if len(timestamps) < 4:
                continue
            timestamps.sort()
            for i in range(1, len(timestamps)):
                gap = timestamps[i] - timestamps[i - 1]
                if gap > 1800:  # 中断 > 30 分钟
                    recovery_times.append(gap / 60)

        avg_recovery = round(sum(recovery_times) / len(recovery_times), 1) if recovery_times else 0
        return {
            "cost_min": avg_recovery,
            "interruptions": len(recovery_times),
            "has_bottleneck": avg_recovery > 10,
        }

    def _detect_project_switch_cost(self, history: List[Dict]) -> Dict[str, Any]:
        """检测项目切换代价"""
        if not history:
            return {"cost": "unknown", "has_bottleneck": False}

        # 分析切换后的工作效率（通过后续事件密度判断）
        project_switches = 0
        sessions: Dict[str, List[Dict]] = defaultdict(list)
        for entry in history:
            sid = entry.get("sessionId", "")
            if sid:
                sessions[sid].append(entry)

        for sid, entries in sessions.items():
            projects_seen = set()
            for e in entries:
                proj = Path(e.get("project", "")).name or "unknown"
                projects_seen.add(proj)
            if len(projects_seen) >= 2:
                project_switches += len(projects_seen) - 1

        return {
            "cost": "high" if project_switches > 20 else "medium" if project_switches > 10 else "low",
            "total_switches": project_switches,
            "has_bottleneck": project_switches > 20,
        }

    def _compute_overall_score(self, events: List[Dict], history: List[Dict]) -> Dict[str, Any]:
        """计算整体工作流健康度评分"""
        scores = {}

        # 工具错误分
        err_tools = self._detect_high_error_tools(events)
        scores["tool_errors"] = max(0, 100 - len(err_tools.get("problem_tools", [])) * 30)

        # 停顿分
        stalls = self._detect_long_stalls(history)
        scores["stalls"] = max(0, 100 - stalls.get("long_stalls_count", 0) * 15)

        # 深度工作分
        deep = self._analyzer._detect_deep_work(history)
        scores["deep_work"] = min(100, int(deep.get("deep_work_ratio", 0) * 1.5))

        # 节奏分
        rhythm = self._analyzer._detect_project_rhythm(history)
        style = rhythm.get("style", "balanced")
        scores["rhythm"] = {"focus": 85, "balanced": 65, "multitask": 40}.get(style, 60)

        overall = round(sum(scores.values()) / len(scores))
        return {
            "overall": overall,
            "details": scores,
            "grade": "A" if overall >= 85 else "B" if overall >= 70 else "C" if overall >= 55 else "D",
        }


class WorkflowOptimizer:
    """
    工作流优化建议引擎

    基于检测到的瓶颈和模式，生成可执行的优化建议。
    """

    def __init__(self):
        self._analyzer = WorkflowAnalyzer()
        self._bottlenecks = BottleneckDetector()

    def generate_advice(self) -> Dict[str, Any]:
        """生成完整的优化建议报告"""
        patterns = self._analyzer.detect_patterns()
        raw_analyze = self._analyzer.analyze()
        bottlenecks = self._bottlenecks.detect_all()

        suggestions = []

        # ── 基于工具错误给出建议 ──
        err_tools = bottlenecks.get("high_error_tools", {})
        for pt in err_tools.get("problem_tools", []):
            suggestions.append({
                "category": "tool_error",
                "priority": "high" if pt["severity"] == "high" else "medium",
                "message": f"工具 `{pt['tool']}` 失败率高达 {pt['fail_rate']:.0%}（{pt['fails']}/{pt['total']} 次）",
                "action": f"检查 {pt['tool']} 相关的工作流程，考虑使用替代工具或优化操作方式",
            })

        # ── 基于重复循环给出建议 ──
        loops = bottlenecks.get("repetitive_loops", {})
        for loop in loops.get("loops", []):
            suggestions.append({
                "category": "repetitive_loop",
                "priority": "medium",
                "message": f"发现重复循环 `{loop['transition']}` 占比 {loop['ratio']:.0%}",
                "action": "考虑将重复步骤自动化，或整理为可复用的脚本/命令",
            })

        # ── 基于深度工作给出建议 ──
        deep = raw_analyze.get("deep_work", {})
        deep_ratio = deep.get("deep_work_ratio", 0)
        if deep_ratio < 30 and deep.get("total_sessions", 0) >= 5:
            suggestions.append({
                "category": "deep_work",
                "priority": "high",
                "message": f"深度工作占比仅 {deep_ratio}%，低于建议的 30%",
                "action": "尝试使用番茄工作法（25分钟专注 + 5分钟休息），减少多任务切换",
            })

        # ── 基于项目切换给出建议 ──
        rhythm = raw_analyze.get("project_rhythm", {})
        if rhythm.get("style") == "multitask":
            suggestions.append({
                "category": "context_switching",
                "priority": "high",
                "message": f"你处于多任务模式，在 {rhythm.get('unique_projects', 0)} 个项目间频繁切换",
                "action": "建议按天/半天分配项目时间，减少切换次数可提升 20-40% 效率",
            })

        # ── 基于中断成本给出建议 ──
        interrupt = bottlenecks.get("interruption_cost", {})
        cost = interrupt.get("cost_min", 0)
        if cost > 10:
            suggestions.append({
                "category": "interruption",
                "priority": "medium",
                "message": f"中断后平均需要 {cost} 分钟才能恢复工作状态",
                "action": "尝试使用「不要中断」标记或专注模式，减少非紧急打断",
            })

        # ── 基于长时间停顿给出建议 ──
        stalls = bottlenecks.get("long_stalls", {})
        if stalls.get("avg_gap_min", 0) > 10:
            suggestions.append({
                "category": "stalls",
                "priority": "low",
                "message": f"工作间隔平均 {stalls['avg_gap_min']} 分钟",
                "action": "规划任务时预留缓冲时间，避免连续高强度工作导致疲劳",
            })

        # ── 基于工作流模式给出建议 ──
        dominant = patterns.get("dominant")
        if dominant and dominant in WORKFLOW_PATTERNS:
            pdef = WORKFLOW_PATTERNS[dominant]
            if pdef.get("efficiency") == "medium":
                suggestions.append({
                    "category": "pattern_optimization",
                    "priority": "low",
                    "message": f"主导工作流模式「{dominant}」效率评级为中等",
                    "action": f"尝试在 {dominant} 流程中增加自动化步骤或优化中间环节",
                })

        # 排序：高优先级在前
        priority_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda s: priority_order.get(s["priority"], 99))

        overall_grade = bottlenecks.get("overall_score", {}).get("grade", "N/A")

        return {
            "suggestions": suggestions,
            "total": len(suggestions),
            "high_priority": sum(1 for s in suggestions if s["priority"] == "high"),
            "overall_grade": overall_grade,
            "overall_score": bottlenecks.get("overall_score", {}).get("overall", 0),
        }

    def estimate_automation_potential(self) -> Dict[str, Any]:
        """
        评估可自动化的重复步骤

        Returns:
            {
                "automation_candidates": [...],
                "estimated_time_saving": "每周约 X 分钟",
            }
        """
        patterns = self._analyzer.detect_patterns()
        loops = self._bottlenecks._detect_repetitive_loops(self._analyzer._load_events())

        candidates = []
        # 重复循环是可自动化的主要候选
        for loop in loops.get("loops", []):
            candidates.append({
                "pattern": loop["transition"],
                "frequency": loop["count"],
                "suggestion": f"将 `{loop['transition']}` 封装为自动化脚本或别名",
            })

        # 高占比模式也是候选
        for p in patterns.get("patterns", []):
            if p["pct"] >= 20 and p["efficiency"] != "high":
                candidates.append({
                    "pattern": p["name"],
                    "frequency": p["count"],
                    "suggestion": f"优化「{p['name']}」流程中的手动步骤",
                })

        # 去重
        seen = set()
        unique_candidates = []
        for c in candidates:
            key = c["pattern"]
            if key not in seen:
                seen.add(key)
                unique_candidates.append(c)

        estimated_minutes = len(unique_candidates) * 30  # 每个候选每周可节省约 30 分钟
        return {
            "automation_candidates": unique_candidates,
            "estimated_time_saving": f"每周约 {estimated_minutes} 分钟",
            "candidate_count": len(unique_candidates),
        }


class HabitTracker:
    """
    习惯养成数据追踪

    基于工作流数据生成习惯相关的洞察。
    """

    def __init__(self):
        self._analyzer = WorkflowAnalyzer()
        self._history_file = Path.home() / ".claude" / "history.jsonl"

    def get_habits(self) -> Dict[str, Any]:
        """获取工作习惯分析"""
        history = self._analyzer._load_history()
        if not history:
            return {"habits": [], "streak_days": 0}

        # 按天统计工作频率
        daily_work: Dict[str, int] = Counter()
        for entry in history:
            ts = entry.get("timestamp", 0)
            if not ts:
                continue
            try:
                day = datetime.fromtimestamp(float(ts) / 1000).strftime("%Y-%m-%d")
                daily_work[day] += 1
            except Exception:
                continue

        # 连续工作天数
        sorted_days = sorted(daily_work.keys())
        streak = self._compute_streak(sorted_days)

        # 最活跃时间段
        hourly = Counter()
        for entry in history:
            ts = entry.get("timestamp", 0)
            if not ts:
                continue
            try:
                hour = datetime.fromtimestamp(float(ts) / 1000).hour
                hourly[hour] += 1
            except Exception:
                continue

        peak_hour = hourly.most_common(1)[0][0] if hourly else 9

        # 每日平均交互次数
        total_days = len(sorted_days) or 1
        avg_daily = round(len(history) / total_days, 1)

        # 习惯一致性评分
        consistency = min(100, int(len(history) / max(len(sorted_days), 1) * 5))

        return {
            "streak_days": streak,
            "total_work_days": len(sorted_days),
            "avg_daily_interactions": avg_daily,
            "peak_hour": peak_hour,
            "peak_hour_label": f"{peak_hour}:00-{peak_hour + 1}:00",
            "consistency_score": consistency,
            "consistency_grade": "A" if consistency >= 80 else "B" if consistency >= 60 else "C",
        }

    def _compute_streak(self, sorted_days: List[str]) -> int:
        """计算连续工作天数"""
        if not sorted_days:
            return 0
        from datetime import datetime, timedelta
        streak = 1
        for i in range(1, len(sorted_days)):
            try:
                prev = datetime.strptime(sorted_days[i - 1], "%Y-%m-%d")
                curr = datetime.strptime(sorted_days[i], "%Y-%m-%d")
                if (curr - prev).days == 1:
                    streak += 1
                else:
                    streak = 1
            except Exception:
                continue
        return streak
