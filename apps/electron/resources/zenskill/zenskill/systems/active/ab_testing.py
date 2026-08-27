"""Lightweight A/B testing framework."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ...core.paths import append_jsonl_locked, get_user_data_dir


EXPERIMENTS_DIR_NAME = "experiments"
CONFIDENCE_THRESHOLD = 0.90  # 自动选择优胜者的置信度阈值


@dataclass
class Experiment:
    name: str
    description: str
    variants: list[str]
    metrics: list[str]  # 跟踪的指标名称
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "active"  # active | completed | archived

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Experiment:
        return cls(
            name=d["name"],
            description=d.get("description", ""),
            variants=d.get("variants", []),
            metrics=d.get("metrics", []),
            created=d.get("created", ""),
            status=d.get("status", "active"),
        )


@dataclass
class Trial:
    experiment: str
    variant: str
    metric_values: dict[str, float]
    user_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ABTestEngine:
    """A/B 测试引擎"""

    def __init__(self):
        self._base_dir = get_user_data_dir() / EXPERIMENTS_DIR_NAME
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _experiment_file(self, name: str) -> Path:
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        return self._base_dir / f"{slug}.json"

    def _trials_file(self, name: str) -> Path:
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        return self._base_dir / f"{slug}_trials.jsonl"

    # ---- experiment CRUD ----

    def create(self, name: str, description: str, variants: list[str], metrics: list[str]) -> Experiment:
        exp = Experiment(name=name, description=description, variants=variants, metrics=metrics)
        self._experiment_file(name).write_text(json.dumps(exp.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return exp

    def get(self, name: str) -> Optional[Experiment]:
        f = self._experiment_file(name)
        if not f.exists():
            return None
        return Experiment.from_dict(json.loads(f.read_text(encoding="utf-8")))

    def list_all(self) -> list[Experiment]:
        result = []
        for f in sorted(self._base_dir.glob("*.json")):
            if f.name.endswith("_trials.jsonl"):
                continue
            try:
                result.append(Experiment.from_dict(json.loads(f.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, KeyError, UnicodeDecodeError):
                continue
        return result

    def complete(self, name: str) -> bool:
        exp = self.get(name)
        if not exp:
            return False
        exp.status = "completed"
        self._experiment_file(name).write_text(json.dumps(exp.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return True

    # ---- assignment ----

    def assign(self, experiment_name: str, user_id: str) -> Optional[str]:
        """基于 user_id 哈希的一致分组"""
        exp = self.get(experiment_name)
        if not exp or not exp.variants:
            return None
        key = f"{experiment_name}:{user_id}"
        h = int(hashlib.md5(key.encode()).hexdigest(), 16)
        return exp.variants[h % len(exp.variants)]

    # ---- trial recording ----

    def record(self, experiment_name: str, variant: str, metric_values: dict[str, float],
               user_id: str = "") -> None:
        trial = Trial(experiment=experiment_name, variant=variant,
                      metric_values=metric_values, user_id=user_id)
        append_jsonl_locked(self._trials_file(experiment_name), trial.to_dict())

    # ---- analysis ----

    def get_trials(self, experiment_name: str) -> list[Trial]:
        f = self._trials_file(experiment_name)
        if not f.exists():
            return []
        trials = []
        with open(f, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    trials.append(Trial(
                        experiment=d["experiment"], variant=d["variant"],
                        metric_values=d.get("metric_values", {}),
                        user_id=d.get("user_id", ""), timestamp=d.get("timestamp", ""),
                    ))
                except (json.JSONDecodeError, KeyError):
                    continue
        return trials

    def analyze(self, experiment_name: str) -> dict[str, Any]:
        """分析实验结果，返回每组的统计和优胜者"""
        exp = self.get(experiment_name)
        if not exp:
            return {"error": "实验不存在"}

        trials = self.get_trials(experiment_name)
        if not trials:
            return {"experiment": experiment_name, "status": "no_data", "variants": {}}

        # 按 variant 分组
        groups: dict[str, list[dict[str, float]]] = {v: [] for v in exp.variants}
        for t in trials:
            if t.variant in groups:
                groups[t.variant].append(t.metric_values)

        variant_stats: dict[str, Any] = {}
        primary_metric = exp.metrics[0] if exp.metrics else "score"

        for variant, values in groups.items():
            if not values:
                variant_stats[variant] = {"count": 0, "mean": 0, "std": 0}
                continue
            metric_vals = [v.get(primary_metric, 0) for v in values]
            n = len(metric_vals)
            mean = sum(metric_vals) / n
            variance = sum((x - mean) ** 2 for x in metric_vals) / n if n > 1 else 0
            std = math.sqrt(variance)
            se = std / math.sqrt(n) if n > 1 else float("inf")
            variant_stats[variant] = {"count": n, "mean": round(mean, 3), "std": round(std, 3), "se": round(se, 4)}

        # 找出领先者并计算置信度
        winner, confidence = self._find_winner(variant_stats)
        auto_promote = confidence >= CONFIDENCE_THRESHOLD

        return {
            "experiment": experiment_name,
            "status": exp.status,
            "total_trials": len(trials),
            "primary_metric": primary_metric,
            "variants": variant_stats,
            "winner": winner,
            "confidence": round(confidence, 3),
            "auto_promote": auto_promote,
        }

    @staticmethod
    def _find_winner(stats: dict[str, Any]) -> tuple[Optional[str], float]:
        """找到领先者并计算粗略置信度 (Welch's t-test 近似)"""
        best_variant = None
        best_mean = -float("inf")
        for name, s in stats.items():
            if s["count"] < 2:
                continue
            if s["mean"] > best_mean:
                best_mean = s["mean"]
                best_variant = name

        if not best_variant or len(stats) < 2:
            return best_variant, 0.0

        # 与第二名比较
        others = [(n, s["mean"], s["se"]) for n, s in stats.items() if n != best_variant and s["count"] >= 2]
        if not others:
            return best_variant, 0.5

        second_name, second_mean, second_se = max(others, key=lambda x: x[1])
        best_se = stats[best_variant]["se"]
        diff = best_mean - second_mean
        pooled_se = math.sqrt(best_se ** 2 + second_se ** 2)
        if pooled_se < 1e-10:
            return best_variant, 1.0
        t_stat = diff / pooled_se
        # 粗略的 t→p 映射
        if t_stat >= 1.96:
            p = 0.975
        elif t_stat >= 1.645:
            p = 0.95
        elif t_stat >= 1.28:
            p = 0.90
        elif t_stat >= 0.84:
            p = 0.80
        elif t_stat >= 0.52:
            p = 0.70
        else:
            p = 0.50
        return best_variant, p

    # ---- format ----

    def format_report(self, experiment_name: str) -> str:
        result = self.analyze(experiment_name)
        if "error" in result:
            return f"❌ {result['error']}"

        lines = [f"📊 A/B 测试: {result['experiment']}"]
        lines.append(f"   状态: {result['status']} | 总试验: {result['total_trials']} | 指标: {result['primary_metric']}")
        lines.append("")

        for name, s in result["variants"].items():
            icon = "🏆" if name == result["winner"] else "  "
            lines.append(f"   {icon} {name}: mean={s['mean']}, n={s['count']}, σ={s['std']}")

        lines.append("")
        if result["winner"] and result["confidence"] >= 0.8:
            lines.append(f"   优胜者: {result['winner']} (置信度 {result['confidence']:.1%})")
            if result["auto_promote"]:
                lines.append(f"   ✅ 置信度超过阈值 ({CONFIDENCE_THRESHOLD:.0%})，建议自动采用")
        elif result["winner"]:
            lines.append(f"   领先者: {result['winner']} (置信度 {result['confidence']:.1%}, 数据不足)")
        else:
            lines.append(f"   数据不足以判断优胜者")

        return "\n".join(lines)


import re  # noqa: E402 (used in _experiment_file)
