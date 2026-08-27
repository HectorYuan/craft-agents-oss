"""
统计模式挖掘引擎 (Phase 9E.1)

从 events.jsonl + history.jsonl 中提取量化行为模式：
- 一阶马尔可夫转移矩阵 (P(next_action | current_action))
- 时序分布 (action | hour)
- 项目关联 (project | hour, weekday)
- 会话节奏 (时长/密度/切换速率)
"""

import json
import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PatternProfile:
    """挖掘出的模式画像"""
    transition_matrix: Dict[str, Dict[str, float]]    # tool → {next_tool → prob}
    hourly_distribution: Dict[int, Dict[str, float]]  # hour → {tool → prob}
    project_hourly: Dict[int, Dict[str, float]]       # hour → {project → prob}
    project_weekday: Dict[int, Dict[str, float]]      # weekday → {project → prob}
    session_rhythm: Dict[str, float]                  # avg_duration_min, tool_density, switch_rate
    dominant_tools: List[str]                         # 使用最多的工具 Top-5
    peak_hours: List[int]                             # 活跃时段 Top-3
    total_events: int
    total_sessions: int
    computed_at: float


class StatisticalPatternMiner:
    """统计模式挖掘器"""

    ACTION_PATTERNS = {
        "debug": ["fix", "bug", "修复", "错误", "crash", "崩溃", "debug", "调试",
                  "fail", "失败", "error"],
        "build": ["create", "build", "实现", "新建", "添加", "add", "implement",
                  "feat", "feature", "新增"],
        "refactor": ["refactor", "重构", "重写", "rewrite", "optimize", "优化",
                     "improve", "clean", "simplify"],
        "explore": ["explore", "探索", "了解", "查看", "检查", "check", "look",
                    "find", "search", "搜索"],
        "plan": ["plan", "计划", "设计", "design", "architect", "架构", "规划"],
        "commit": ["commit", "提交", "push", "merge", "pr", "pull request"],
        "config": ["config", "配置", "setup", "安装", "install", "设置"],
        "review": ["review", "审查", "检查", "audit", "test", "测试"],
    }

    def __init__(self):
        self._events_file = Path.home() / ".zenskill" / "mirroring" / "events.jsonl"
        self._history_file = Path.home() / ".claude" / "history.jsonl"
        self._cache_file = Path.home() / ".zenskill" / "mirroring" / "patterns.json"

    def mine(self, force: bool = False) -> PatternProfile:
        """挖掘模式（结果缓存到 patterns.json）"""
        if not force and self._cache_file.exists():
            try:
                cached = json.loads(self._cache_file.read_text())
                if time.time() - cached.get("computed_at", 0) < 3600:
                    return PatternProfile(**cached)
            except Exception:
                pass

        profile = self._compute()
        self._cache_file.write_text(
            json.dumps(asdict(profile), indent=2, ensure_ascii=False)
        )
        return profile

    def _compute(self) -> PatternProfile:
        """执行完整的模式挖掘"""
        history = self._load_history()
        events = self._load_events()

        # 1. 提取动作序列（按 session 分组）
        session_sequences = self._build_action_sequences(history)

        # 2. 转移矩阵
        transition_matrix = self._build_transition_matrix(session_sequences)

        # 3. 时序分布
        hourly_dist = self._build_hourly_distribution(history)

        # 4. 项目关联
        proj_hourly, proj_weekday = self._build_project_associations(history)

        # 5. 会话节奏
        rhythm = self._compute_session_rhythm(history)

        # 6. 衍生统计
        all_actions = [a for seq in session_sequences for a in seq]
        tool_counter = Counter(all_actions)
        dominant = [t for t, _ in tool_counter.most_common(5)]

        hour_counter = Counter()
        for entry in history:
            ts = entry.get("timestamp", 0)
            if ts:
                try:
                    from datetime import datetime
                    h = datetime.fromtimestamp(float(ts) / 1000).hour
                    hour_counter[h] += 1
                except Exception:
                    pass
        peak_hours = [h for h, _ in hour_counter.most_common(3)]

        return PatternProfile(
            transition_matrix=transition_matrix,
            hourly_distribution=hourly_dist,
            project_hourly=proj_hourly,
            project_weekday=proj_weekday,
            session_rhythm=rhythm,
            dominant_tools=dominant,
            peak_hours=peak_hours,
            total_events=len(events),
            total_sessions=len(session_sequences),
            computed_at=time.time(),
        )

    # ── 数据加载 ──

    def _load_history(self) -> List[Dict]:
        entries = []
        if self._history_file.exists():
            for line in open(self._history_file):
                try:
                    entries.append(json.loads(line.strip()))
                except Exception:
                    pass
        return entries

    def _load_events(self) -> List[Dict]:
        events = []
        if self._events_file.exists():
            for line in open(self._events_file):
                try:
                    events.append(json.loads(line.strip()))
                except Exception:
                    pass
        return events

    # ── 动作序列构建 ──

    def _build_action_sequences(self, history: List[Dict]) -> List[List[str]]:
        """按 session 分组构建动作序列"""
        sessions: Dict[str, List[Tuple[float, str]]] = defaultdict(list)

        for entry in history:
            sid = entry.get("sessionId", "")
            ts = entry.get("timestamp", 0)
            display = entry.get("display", "")
            if sid and ts and display:
                action = self._classify_action(display)
                sessions[sid].append((float(ts) / 1000, action))

        # 按时间排序，提取纯动作序列
        sequences = []
        for sid, events in sessions.items():
            events.sort()
            # 合并连续相同动作
            merged = []
            for _, action in events:
                if not merged or merged[-1] != action:
                    merged.append(action)
            if len(merged) >= 2:
                sequences.append(merged)

        return sequences

    def _classify_action(self, text: str) -> str:
        """将用户输入分类为动作类型"""
        text_lower = text.lower()

        # 斜杠命令优先
        if text_lower.startswith("/"):
            cmd = text_lower.split()[0][1:]
            if cmd in ("commit", "pr", "review"):
                return "commit"
            if cmd in ("plan", "agents", "todo"):
                return "plan"
            if cmd in ("fix", "doctor", "debug"):
                return "debug"
            return "explore"

        # 关键词匹配
        for action, keywords in self.ACTION_PATTERNS.items():
            for kw in keywords:
                if kw in text_lower:
                    return action

        return "explore"  # 默认探索

    # ── 转移矩阵 ──

    def _build_transition_matrix(
        self, sequences: List[List[str]]
    ) -> Dict[str, Dict[str, float]]:
        """构建一阶马尔可夫转移矩阵"""
        # 计数
        trans_counts: Dict[str, Counter] = defaultdict(Counter)
        out_counts: Counter = Counter()

        for seq in sequences:
            for i in range(len(seq) - 1):
                a, b = seq[i], seq[i + 1]
                trans_counts[a][b] += 1
                out_counts[a] += 1

        # 转换为概率（加 Laplace 平滑 α=0.1）
        alpha = 0.1
        all_actions = list(set(a for seq in sequences for a in seq))
        n_actions = len(all_actions) or 1

        matrix: Dict[str, Dict[str, float]] = {}
        for a in all_actions:
            row: Dict[str, float] = {}
            total = out_counts.get(a, 0) + alpha * n_actions
            for b in all_actions:
                raw = trans_counts[a].get(b, 0)
                row[b] = round((raw + alpha) / total, 4)
            matrix[a] = row

        return matrix

    # ── 时序分布 ──

    def _build_hourly_distribution(
        self, history: List[Dict]
    ) -> Dict[int, Dict[str, float]]:
        """构建每小时的行动分布"""
        hourly_counts: Dict[int, Counter] = defaultdict(Counter)

        for entry in history:
            ts = entry.get("timestamp", 0)
            display = entry.get("display", "")
            if not ts or not display:
                continue
            try:
                from datetime import datetime
                hour = datetime.fromtimestamp(float(ts) / 1000).hour
                action = self._classify_action(display)
                hourly_counts[hour][action] += 1
            except Exception:
                pass

        hourly_dist: Dict[int, Dict[str, float]] = {}
        for hour, counter in hourly_counts.items():
            total = sum(counter.values()) or 1
            hourly_dist[hour] = {
                a: round(c / total, 4) for a, c in counter.most_common(5)
            }

        return hourly_dist

    # ── 项目关联 ──

    def _build_project_associations(
        self, history: List[Dict]
    ) -> Tuple[Dict[int, Dict[str, float]], Dict[int, Dict[str, float]]]:
        """构建项目关联矩阵 P(project | hour) + P(project | weekday)"""
        proj_hourly: Dict[int, Counter] = defaultdict(Counter)
        proj_weekday: Dict[int, Counter] = defaultdict(Counter)

        for entry in history:
            ts = entry.get("timestamp", 0)
            proj = Path(entry.get("project", "")).name or "unknown"
            if not ts:
                continue
            try:
                from datetime import datetime
                dt = datetime.fromtimestamp(float(ts) / 1000)
                proj_hourly[dt.hour][proj] += 1
                proj_weekday[dt.weekday()][proj] += 1
            except Exception:
                pass

        def _normalize(d: Dict[int, Counter]) -> Dict[int, Dict[str, float]]:
            return {
                k: {p: round(c / sum(v.values()), 4) for p, c in v.most_common(3)}
                for k, v in d.items()
            }

        return _normalize(proj_hourly), _normalize(proj_weekday)

    # ── 会话节奏 ──

    def _compute_session_rhythm(self, history: List[Dict]) -> Dict[str, float]:
        """计算会话节奏指标"""
        sessions: Dict[str, List[float]] = defaultdict(list)

        for entry in history:
            sid = entry.get("sessionId", "")
            ts = entry.get("timestamp", 0)
            if sid and ts:
                sessions[sid].append(float(ts) / 1000)

        if not sessions:
            return {"avg_duration_min": 0, "tool_density": 0, "switch_rate": 0}

        durations = []
        densities = []
        for sid, timestamps in sessions.items():
            timestamps.sort()
            if len(timestamps) >= 2:
                dur = (timestamps[-1] - timestamps[0]) / 60
                durations.append(dur)
                densities.append(len(timestamps) / max(dur, 1))

        return {
            "avg_duration_min": round(sum(durations) / len(durations), 1) if durations else 0,
            "tool_density": round(sum(densities) / len(densities), 2) if densities else 0,
            "switch_rate": round(len(sessions) / max(len(history), 1), 4),
        }
