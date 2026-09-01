"""
上下文感知预测器 + 异常检测器 (Phase 9E.2)

基于 PatternMiner 的模式数据，实现：
- ContextVector: 7 维上下文编码
- NextActionPredictor: 三级策略预测下一步行动
- AnomalyDetector: Z-score 偏离检测
- 预测结果缓存 + 实时上下文接入
"""

import json
import math
import os
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .pattern_miner import StatisticalPatternMiner, PatternProfile


# ── 预测缓存 ──
PREDICTION_CACHE_TTL = 300  # 5 分钟缓存有效


@dataclass
class ContextVector:
    """7 维上下文编码"""
    hour_sin: float           # sin(hour * 2π / 24) — 循环时间编码
    hour_cos: float           # cos(hour * 2π / 24)
    weekday: int              # 0=Mon ... 6=Sun
    recent_tools: List[str]   # 最近 3 个工具
    active_project: str       # 当前活跃项目
    session_duration_min: float  # 当前会话已持续分钟数
    tool_density: float       # 每分钟工具调用次数

    def similarity(self, other: "ContextVector") -> float:
        """余弦相似度"""
        # 时间部分相似度（循环距离）
        time_sim = (
            self.hour_sin * other.hour_sin + self.hour_cos * other.hour_cos
        )
        # 工具部分相似度（Jaccard）
        s_tools = set(self.recent_tools)
        o_tools = set(other.recent_tools)
        tool_sim = len(s_tools & o_tools) / max(len(s_tools | o_tools), 1)
        # 项目部分
        proj_sim = 1.0 if self.active_project == other.active_project else 0.0

        return (time_sim * 0.4 + tool_sim * 0.4 + proj_sim * 0.2)


def _read_session_cache() -> Dict[str, Any]:
    """从会话缓存文件读取实时上下文数据"""
    cache_file = Path.home() / ".zenskill" / "session" / "current.json"
    if not cache_file.exists():
        return {}
    try:
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _detect_project_from_cwd() -> str:
    """从当前工作目录推断活跃项目"""
    try:
        cwd = os.getcwd()
        # 取项目根目录名
        for marker in (".git", "pyproject.toml", "package.json", "Cargo.toml"):
            marker_path = os.path.join(cwd, marker)
            if os.path.exists(marker_path):
                return os.path.basename(cwd)
        # 回退：取当前目录名
        return os.path.basename(cwd)
    except Exception:
        return ""


class ContextPredictor:
    """上下文感知预测器"""

    def __init__(self, profile: Optional[PatternProfile] = None):
        self._miner = StatisticalPatternMiner()
        self._profile = profile or self._miner.mine()
        self._cache_file = Path.home() / ".zenskill" / "mirroring" / "predictions.json"

    def predict(self, context: Optional[ContextVector] = None,
                use_cache: bool = True) -> List[Dict]:
        """
        预测下一步最可能的行动（Top-3 + 置信度 + 解释）

        Args:
            context: 上下文向量，为 None 时自动构建
            use_cache: 是否使用缓存（默认 True，5 分钟内有效）

        Returns:
            [{"action", "confidence", "source", "explanation"}, ...]
        """
        # 缓存检查
        if use_cache:
            cached = self._load_cache()
            if cached is not None:
                return cached

        if context is None:
            context = self._current_context()

        predictions = []

        # 策略 1: 如果有最近工具 + 充足数据 → 用转移矩阵
        if context.recent_tools and len(self._profile.dominant_tools) >= 3:
            matrix_preds = self._predict_from_matrix(context)
            predictions.extend(matrix_preds)

        # 策略 2: 用时段分布补充
        hour_preds = self._predict_from_hour(context)
        predictions.extend(hour_preds)

        # 合并去重，保留 Top-3
        seen = set()
        unique = []
        for p in sorted(predictions, key=lambda x: x["confidence"], reverse=True):
            if p["action"] not in seen:
                seen.add(p["action"])
                unique.append(p)
            if len(unique) >= 3:
                break

        # 写入缓存
        if use_cache:
            self._save_cache(unique)

        return unique

    def _current_context(self) -> ContextVector:
        """从当前状态和会话缓存构建上下文向量"""
        now = datetime.now()
        hour = now.hour + now.minute / 60
        session = _read_session_cache()

        # 从会话缓存读取实时数据
        recent_tools = session.get("recent_tools", [])
        session_started = session.get("started", 0)
        tool_count = session.get("tool_count", 0)

        # 会话持续时间
        duration_min = 0
        if session_started:
            duration_min = (time.time() - session_started) / 60

        # 工具密度
        tool_density = tool_count / max(duration_min, 1)

        # 从 cwd 检测项目
        active_project = _detect_project_from_cwd()

        return ContextVector(
            hour_sin=math.sin(hour * 2 * math.pi / 24),
            hour_cos=math.cos(hour * 2 * math.pi / 24),
            weekday=now.weekday(),
            recent_tools=recent_tools[-3:] if recent_tools else [],
            active_project=active_project,
            session_duration_min=round(duration_min, 1),
            tool_density=round(tool_density, 2),
        )

    def _load_cache(self) -> Optional[List[Dict]]:
        """加载预测缓存（5 分钟内有效）"""
        if not self._cache_file.exists():
            return None
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
            cached_at = data.get("cached_at", 0)
            if time.time() - cached_at < PREDICTION_CACHE_TTL:
                return data.get("predictions", [])
        except Exception:
            pass
        return None

    def _save_cache(self, predictions: List[Dict]) -> None:
        """保存预测缓存"""
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(
                json.dumps({
                    "predictions": predictions,
                    "cached_at": time.time(),
                }, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _predict_from_matrix(self, context: ContextVector) -> List[Dict]:
        """策略 1: 基于马尔可夫转移矩阵"""
        matrix = self._profile.transition_matrix
        results = []

        for current_tool in context.recent_tools[:1]:  # 最近 1 个工具
            if current_tool not in matrix:
                continue
            row = matrix[current_tool]
            for next_tool, prob in row.items():
                if prob > 0.15:  # 置信度阈值
                    results.append({
                        "action": next_tool,
                        "confidence": round(prob, 3),
                        "source": "transition_matrix",
                        "explanation": f"基于历史: {current_tool} → {next_tool} 概率 {prob:.0%}",
                    })

        return results

    def _predict_from_hour(self, context: ContextVector) -> List[Dict]:
        """策略 2: 基于时段分布"""
        import time as _time
        from datetime import datetime

        hour = datetime.fromtimestamp(_time.time()).hour
        dist = self._profile.hourly_distribution.get(hour, {})

        results = []
        for tool, prob in dist.items():
            if prob > 0.05:
                results.append({
                    "action": tool,
                    "confidence": round(prob * 0.7, 3),  # 时段权重 70%
                    "source": "time_pattern",
                    "explanation": f"此时段 ({hour}:00) 常用: {tool} ({prob:.0%})",
                })

        return results


class AnomalyDetector:
    """异常检测器 — 标记偏离常规模式的行为"""

    def __init__(self, profile: Optional[PatternProfile] = None):
        self._miner = StatisticalPatternMiner()
        self._profile = profile or self._miner.mine()
        self._baseline = self._compute_baseline()

    def _compute_baseline(self) -> Dict[str, Any]:
        """计算基准线（均值 + 标准差）"""
        profile = self._profile
        rhythm = profile.session_rhythm

        density = rhythm.get("tool_density", 0)
        switch = rhythm.get("switch_rate", 0)

        return {
            "tool_density_mean": density,
            "tool_density_std": density * 0.5,   # 标准差估计为均值的 50%
            "switch_rate_mean": switch,
            "switch_rate_std": switch * 0.5,
            "dominant_tools": set(profile.dominant_tools),
            "peak_hours": set(profile.peak_hours),
        }

    def detect(self, context: Optional[ContextVector] = None) -> List[Dict]:
        """检测异常，返回异常项列表"""
        if context is None:
            return []

        anomalies = []
        baseline = self._baseline

        # 检查工具密度异常
        density = context.tool_density
        if density > 0:
            mean_d = baseline["tool_density_mean"]
            std_d = max(baseline["tool_density_std"], 0.01)
            z_density = (density - mean_d) / std_d
            if abs(z_density) > 2.0:
                direction = "高" if z_density > 0 else "低"
                anomalies.append({
                    "type": "tool_density",
                    "severity": "high" if abs(z_density) > 3 else "medium",
                    "z_score": round(z_density, 1),
                    "message": (
                        f"工具密度异常偏{direction} (当前 {density:.1f}/min, "
                        f"均值 {mean_d:.1f}/min, z={z_density:.1f})"
                    ),
                })

        # 检查是否在非常规时段活跃
        if context.recent_tools:
            import time as _time
            from datetime import datetime
            hour = datetime.fromtimestamp(_time.time()).hour
            peak_hours = baseline["peak_hours"]
            if peak_hours and hour not in peak_hours:
                anomalies.append({
                    "type": "timing",
                    "severity": "low",
                    "z_score": 0,
                    "message": (
                        f"当前时段 {hour}:00 不在你通常的活跃时段 "
                        f"({', '.join(f'{h}:00' for h in sorted(peak_hours))})"
                    ),
                })

        return anomalies
