"""
学习曲线可视化 + 遗忘曲线检测 (Phase 7Q + 7S)

7Q: 基于历史数据的 ASCII 学习曲线 + 拐点标记
7S: 艾宾浩斯遗忘曲线 — 长时间未使用的技能退化预测
"""

import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


class LearningCurveViz:
    """7Q: 学习曲线可视化"""

    @staticmethod
    def plot(history: List[Dict[str, Any]], dim: str = "proficiency",
             width: int = 40, height: int = 12, title: str = "") -> str:
        """生成 ASCII 学习曲线

        Args:
            history: [{timestamp, ability_scores: {dim: score}}]
            dim: 维度名称
            width: 图宽度(字符)
            height: 图高度(字符)

        Returns:
            ASCII 学习曲线字符串
        """
        vals = []
        dates = []
        for snap in history:
            scores = snap.get("ability_scores", snap.get("dimension_scores", snap))
            if isinstance(scores, dict):
                v = scores.get(dim, 0)
                if v > 0:
                    vals.append(v)
                    ts = snap.get("timestamp", "")
                    dates.append(ts[:10] if ts else "")

        if len(vals) < 2:
            return f"  [dim]数据不足 ({len(vals)} 点), 需要 2+ 采样[/dim]"

        # 归一化到 0-100
        v_min, v_max = max(min(vals) - 5, 0), min(max(vals) + 5, 100)
        v_range = max(v_max - v_min, 1)

        # 采样到 width 个点
        step = max(len(vals) // width, 1)
        sampled = vals[::step] + [vals[-1]]
        sampled_dates = dates[::step] + [dates[-1]]
        sampled = sampled[-width:]

        # 绘制
        lines = []
        if title:
            lines.append(f"  {title}")
        lines.append(f"  {'─' * width} {v_max:.0f}")

        for row in range(height - 1, -1, -1):
            y = v_min + (row / (height - 1)) * v_range
            line = "  │"
            for i, val in enumerate(sampled):
                x = i * width // max(len(sampled) - 1, 1)
                if val >= y:
                    # 检查是否是拐点(增长率突变)
                    prev_val = sampled[i - 1] if i > 0 else val
                    growth = val - prev_val
                    prev_growth = sampled[i - 1] - sampled[i - 2] if i > 1 else growth
                    if growth > prev_growth * 2 and growth > 3:
                        line = line[:x + 2] + "▲" + line[x + 3:]
                    elif x >= len(line) - 2:
                        line += "●"
                    elif len(line) <= x + 2:
                        line += "█" * (x + 3 - len(line))
                    else:
                        line = line[:x + 2] + "█" + line[x + 3:]
            lines.append(line)

        lines.append(f"  {'─' * width} {v_min:.0f}")
        # 日期标签
        if sampled_dates:
            labels = [sampled_dates[0], sampled_dates[len(sampled_dates)//2], sampled_dates[-1]]
            label_line = "   " + "  ".join(labels)
            lines.append(label_line)

        # 拐点说明
        inflection_points = LearningCurveViz._find_inflections(vals)
        if inflection_points:
            lines.append(f"  ▲ 拐点: {len(inflection_points)} 个增长加速点")

        return "\n".join(lines)

    @staticmethod
    def _find_inflections(vals: List[float]) -> List[int]:
        """找增长率突增的拐点"""
        if len(vals) < 4:
            return []
        inflections = []
        for i in range(2, len(vals)):
            prev_g = vals[i - 1] - vals[i - 2]
            curr_g = vals[i] - vals[i - 1]
            if curr_g > prev_g * 2 and curr_g > 2:
                inflections.append(i)
        return inflections


class ForgettingCurveDetector:
    """7S: 艾宾浩斯遗忘曲线检测"""

    # 简化的遗忘曲线参数: S(t) = S0 * e^(-t/tau)
    # tau ≈ 30 天 (半衰期约 21 天)
    TAU_DAYS = 30.0

    def check_skills(self) -> List[Dict[str, Any]]:
        """检查所有技能的遗忘状态"""
        import json
        from pathlib import Path

        states_dir = Path.home() / ".zenskill" / "states"
        if not states_dir.exists():
            return []

        now = time.time()
        at_risk = []

        for state_file in states_dir.glob("*.json"):
            if state_file.name.endswith(".history.jsonl"):
                continue

            try:
                state = json.loads(state_file.read_text())
                sid = state.get("skill_id", state_file.stem)
                last_used_str = state.get("last_used", "")
                level = state.get("level", "NOVICE")
                uc = state.get("usage_count", 0)

                if not last_used_str:
                    continue

                # 解析最后使用时间
                from datetime import datetime
                try:
                    last_used = datetime.fromisoformat(last_used_str).timestamp()
                except Exception:
                    continue

                days_inactive = (now - last_used) / 86400

                if days_inactive < 1:
                    continue  # 活跃技能，跳过

                # 遗忘程度
                import math
                retention = math.exp(-days_inactive / self.TAU_DAYS)
                decay_pct = (1 - retention) * 100

                if decay_pct > 10:  # 衰减 > 10% 才提醒
                    level_bonus = {"NOVICE": 10, "APPRENTICE": 30, "ADEPT": 50,
                                   "EXPERT": 70, "MASTER": 90}.get(level, 10)
                    estimated_score = level_bonus * retention

                    at_risk.append({
                        "skill_id": sid,
                        "level": level,
                        "days_inactive": round(days_inactive, 1),
                        "retention": round(retention * 100, 1),
                        "decay_pct": round(decay_pct, 1),
                        "estimated_score": round(estimated_score, 1),
                        "last_used": last_used_str[:10],
                    })
            except Exception:
                continue

        return sorted(at_risk, key=lambda x: x["decay_pct"], reverse=True)

    def get_review_plan(self) -> List[str]:
        """生成复习计划"""
        at_risk = self.check_skills()
        if not at_risk:
            return []

        suggestions = []
        for skill in at_risk[:3]:
            suggestions.append(
                f"{skill['skill_id']} ({skill['level']}): "
                f"已 {skill['days_inactive']:.0f} 天未使用, "
                f"熟练度保留 {skill['retention']:.0f}%, "
                f"建议本周复习"
            )
        return suggestions
