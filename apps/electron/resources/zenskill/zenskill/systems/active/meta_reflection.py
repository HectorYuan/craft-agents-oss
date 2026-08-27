"""
ZenSkill - 元反思系统（Meta Reflection）

反思"反思过程"本身，持续优化反思算法的质量和效率：
- 评估反思报告的质量和深度
- 分析反思建议的实际采纳率
- 识别反思算法的盲点和偏差
- 生成反思算法的优化建议
- 跟踪优化效果，形成闭环

这是一个 P2 级别的高级功能，让 ZenSkill 具备自我进化能力。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional, Tuple

from zenskill.core.paths import get_user_data_dir


@dataclass
class ReflectionQuality:
    """反思质量评估"""
    reflection_id: str
    overall_score: float  # 0-100 综合质量评分
    dimensions: Dict[str, float]  # 各维度评分
    feedback_sources: List[str]  # 评分来源
    evaluated_at: str
    notes: str = ""


@dataclass
class ReflectionOptimization:
    """反思优化建议"""
    optimization_id: str
    target_component: str  # 哪个组件需要优化
    suggestion: str
    expected_improvement: float  # 预期提升幅度 0-1
    implementation_complexity: str  # low / medium / high
    status: str  # proposed / implementing / implemented / reverted
    created_at: str
    implemented_at: Optional[str] = None
    impact_score: Optional[float] = None  # 实际提升效果


@dataclass
class OptimizationImpact:
    """优化效果追踪"""
    optimization_id: str
    before_quality: Dict[str, float]  # 优化前质量指标
    after_quality: Dict[str, float]  # 优化后质量指标
    improvement_pct: float
    duration_days: int


QUALITY_DIMENSIONS = [
    "actionable_count",      # 可执行建议数量
    "pattern_accuracy",      # 模式识别准确率
    "insight_depth",         # 洞察深度
    "clarity",               # 表达清晰度
    "adoption_rate",         # 建议采纳率
    "relevance",             # 与用户需求的相关性
]


class MetaReflectionEngine:
    """
    元反思引擎 - 反思和优化反思过程本身

    这是一个高级自我进化组件，让 ZenSkill 能够：
    1. 评估自己生成的反思报告质量
    2. 识别反思算法的系统性偏差
    3. 生成具体的优化建议
    4. 追踪优化效果
    """

    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id
        self.meta_dir = self._get_meta_dir()
        self.quality_file = self.meta_dir / f"{skill_id}_quality.jsonl"
        self.optimizations_file = self.meta_dir / f"{skill_id}_optimizations.jsonl"
        self.impact_file = self.meta_dir / f"{skill_id}_impact.jsonl"

    def _get_meta_dir(self) -> Path:
        """获取元反思数据目录"""
        user_dir = get_user_data_dir()
        meta_dir = user_dir / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        return meta_dir

    def _generate_id(self, prefix: str = "meta") -> str:
        """生成唯一 ID"""
        timestamp = int(time.time() * 1000)
        return f"{prefix}_{timestamp}_{self.skill_id}"

    def evaluate_reflection_quality(
        self,
        reflection_content: str,
        reflection_id: Optional[str] = None,
        user_feedback: Optional[str] = None,
        action_adoption_rate: Optional[float] = None,
    ) -> ReflectionQuality:
        """
        评估单次反思报告的质量

        Args:
            reflection_content: 反思报告内容
            reflection_id: 反思 ID（自动生成）
            user_feedback: 用户对这次反思的反馈
            action_adoption_rate: 建议的实际采纳率 0-1

        Returns:
            质量评估结果
        """
        if reflection_id is None:
            reflection_id = self._generate_id("ref")

        dimensions: Dict[str, float] = {}

        # 1. 可执行建议数量 - 基于 bullet points 数量
        action_count = reflection_content.count("- ")
        dimensions["actionable_count"] = min(100.0, action_count * 20)

        # 2. 模式识别准确率 - 基于关键词丰富度
        pattern_keywords = ["模式", "偏好", "喜欢", "希望", "倾向", "观察", "发现"]
        pattern_count = sum(1 for kw in pattern_keywords if kw in reflection_content)
        dimensions["pattern_accuracy"] = min(100.0, pattern_count * 25)

        # 3. 洞察深度 - 基于章节数量和内容长度
        section_count = reflection_content.count("## ")
        content_length = len(reflection_content)
        depth_score = min(100.0, section_count * 20 + content_length / 100)
        dimensions["insight_depth"] = depth_score

        # 4. 表达清晰度 - 基于结构化程度
        structure_markers = ["##", "-", "###", "**", "1.", "2.", "3."]
        structure_count = sum(1 for marker in structure_markers if marker in reflection_content)
        dimensions["clarity"] = min(100.0, structure_count * 12)

        # 5. 建议采纳率（如果有数据）
        if action_adoption_rate is not None:
            dimensions["adoption_rate"] = action_adoption_rate * 100
        else:
            dimensions["adoption_rate"] = 50.0  # 默认中等

        # 6. 相关性 - 基于内容与用户可能需求的匹配度
        relevance_keywords = ["改进", "优化", "建议", "注意", "避免", "提升"]
        relevance_count = sum(1 for kw in relevance_keywords if kw in reflection_content)
        dimensions["relevance"] = min(100.0, relevance_count * 15)

        # 计算综合评分（加权平均）
        weights = {
            "actionable_count": 0.2,
            "pattern_accuracy": 0.15,
            "insight_depth": 0.2,
            "clarity": 0.15,
            "adoption_rate": 0.15,
            "relevance": 0.15,
        }

        overall_score = sum(
            dimensions.get(dim, 50) * weights.get(dim, 1)
            for dim in weights
        ) / sum(weights.values())

        # 收集反馈来源
        feedback_sources = ["auto_quality_analysis"]
        if user_feedback:
            feedback_sources.append("user_feedback")
        if action_adoption_rate is not None:
            feedback_sources.append("adoption_tracking")

        # 生成评估备注
        notes = self._generate_quality_notes(dimensions, overall_score)

        quality = ReflectionQuality(
            reflection_id=reflection_id,
            overall_score=round(overall_score, 1),
            dimensions={k: round(v, 1) for k, v in dimensions.items()},
            feedback_sources=feedback_sources,
            evaluated_at=datetime.now().isoformat(),
            notes=notes,
        )

        # 保存评估结果
        self._save_quality_evaluation(quality)

        return quality

    def _generate_quality_notes(self, dimensions: Dict[str, float], overall: float) -> str:
        """生成质量评估备注"""
        notes = []

        if overall >= 80:
            notes.append("高质量反思，具备良好的洞察力和可操作性")
        elif overall >= 60:
            notes.append("中等质量反思，基本可用但有提升空间")
        else:
            notes.append("反思质量偏低，需要重点优化")

        # 识别强项和弱项
        scores = [(dim, score) for dim, score in dimensions.items()]
        scores.sort(key=lambda x: x[1], reverse=True)

        strengths = [dim for dim, score in scores[:2] if score >= 70]
        if strengths:
            notes.append(f"强项维度: {', '.join(strengths)}")

        weaknesses = [dim for dim, score in scores[-2:] if score < 50]
        if weaknesses:
            notes.append(f"需要改进维度: {', '.join(weaknesses)}")

        return " | ".join(notes)

    def _save_quality_evaluation(self, quality: ReflectionQuality) -> None:
        """保存质量评估到文件"""
        with open(self.quality_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(quality), ensure_ascii=False) + "\n")

    def analyze_quality_trends(self, days: int = 30) -> Dict[str, Any]:
        """
        分析反思质量的历史趋势

        Args:
            days: 分析最近多少天的数据

        Returns:
            趋势分析结果
        """
        evaluations = self._get_recent_evaluations(days)

        if not evaluations:
            return {
                "has_data": False,
                "message": "暂无质量评估数据，继续使用反思功能后会自动生成",
            }

        # 计算综合评分趋势
        scores = [e.overall_score for e in evaluations]
        avg_score = sum(scores) / len(scores)
        trend = "stable"
        if len(scores) >= 5:
            first_half = sum(scores[:len(scores)//2]) / (len(scores)//2)
            second_half = sum(scores[len(scores)//2:]) / (len(scores) - len(scores)//2)
            if second_half - first_half > 5:
                trend = "improving"
            elif first_half - second_half > 5:
                trend = "declining"

        # 各维度平均得分
        dim_averages: Dict[str, float] = {}
        for dim in QUALITY_DIMENSIONS:
            dim_scores = [e.dimensions.get(dim, 0) for e in evaluations]
            if dim_scores:
                dim_averages[dim] = round(sum(dim_scores) / len(dim_scores), 1)

        return {
            "has_data": True,
            "total_evaluations": len(evaluations),
            "analysis_days": days,
            "average_overall_score": round(avg_score, 1),
            "score_trend": trend,
            "best_dimension": max(dim_averages.items(), key=lambda x: x[1])[0] if dim_averages else None,
            "weakest_dimension": min(dim_averages.items(), key=lambda x: x[1])[0] if dim_averages else None,
            "dimension_averages": dim_averages,
        }

    def _get_recent_evaluations(self, days: int = 30) -> List[ReflectionQuality]:
        """获取最近的质量评估"""
        if not self.quality_file.exists():
            return []

        evaluations = []
        cutoff = time.time() - days * 24 * 3600

        with open(self.quality_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    eval_time = datetime.fromisoformat(data["evaluated_at"]).timestamp()
                    if eval_time >= cutoff:
                        evaluations.append(ReflectionQuality(**data))
                except (json.JSONDecodeError, ValueError, KeyError):
                    continue

        return evaluations

    def identify_systemic_biases(self) -> List[Dict[str, Any]]:
        """
        识别反思算法的系统性偏差

        Returns:
            发现的偏差列表
        """
        evaluations = self._get_recent_evaluations(60)
        biases = []

        if len(evaluations) < 10:
            return [{
                "type": "insufficient_data",
                "severity": "low",
                "description": "数据量不足，暂时无法识别系统性偏差",
                "suggestion": "继续使用禅思功能，积累至少 10 条反思记录后即可进行分析",
            }]

        # 偏差 1: 可执行建议数量偏低
        action_scores = [e.dimensions.get("actionable_count", 0) for e in evaluations]
        avg_action = sum(action_scores) / len(action_scores)
        if avg_action < 40:
            biases.append({
                "type": "low_actionable_count",
                "severity": "medium",
                "description": "反思产生的可执行建议数量偏少，用户可能不知道如何改进",
                "suggestion": "增加建议模板库，要求每次反思至少生成 3 条具体建议",
                "data_support": {"average_score": round(avg_action, 1), "threshold": 40},
            })

        # 偏差 2: 模式识别过于泛化
        pattern_scores = [e.dimensions.get("pattern_accuracy", 0) for e in evaluations]
        avg_pattern = sum(pattern_scores) / len(pattern_scores)
        if avg_pattern < 50:
            biases.append({
                "type": "pattern_recognition_weak",
                "severity": "medium",
                "description": "模式识别准确率偏低，可能在泛化用户偏好时不够精准",
                "suggestion": "引入更具体的模式分类体系，增加用户验证机制",
                "data_support": {"average_score": round(avg_pattern, 1), "threshold": 50},
            })

        # 偏差 3: 洞察深度不足
        depth_scores = [e.dimensions.get("insight_depth", 0) for e in evaluations]
        avg_depth = sum(depth_scores) / len(depth_scores)
        if avg_depth < 50:
            biases.append({
                "type": "shallow_insights",
                "severity": "high",
                "description": "反思深度不足，可能停留在表面观察而缺乏深层次洞察",
                "suggestion": "优化反思 Prompt，增加多轮追问机制，引导 LLM 进行更深层次的分析",
                "data_support": {"average_score": round(avg_depth, 1), "threshold": 50},
            })

        # 偏差 4: 质量波动大
        score_variance = sum((s - sum(action_scores)/len(action_scores))**2 for s in action_scores) / len(action_scores)
        if score_variance > 400:
            biases.append({
                "type": "high_quality_variance",
                "severity": "medium",
                "description": "反思质量波动较大，输出一致性不足",
                "suggestion": "增加输出格式约束，使用结构化模板减少随机性",
                "data_support": {"variance": round(score_variance, 1), "threshold": 400},
            })

        if not biases:
            biases.append({
                "type": "no_significant_biases",
                "severity": "low",
                "description": "未发现明显的系统性偏差，反思算法运行良好",
                "suggestion": "继续监控，定期检查质量指标",
            })

        return biases

    def generate_optimization_suggestions(self) -> List[ReflectionOptimization]:
        """
        生成反思算法的优化建议

        Returns:
            优化建议列表
        """
        trends = self.analyze_quality_trends()
        biases = self.identify_systemic_biases()
        suggestions: List[ReflectionOptimization] = []

        # 基于最弱维度生成建议
        if trends["has_data"]:
            weakest = trends["weakest_dimension"]

            if weakest == "actionable_count":
                suggestions.append(ReflectionOptimization(
                    optimization_id=self._generate_id("opt"),
                    target_component="reflection_loop.action_extraction",
                    suggestion="增加可执行建议的模板库，确保每次反思至少生成 3 条具体、可落地的建议",
                    expected_improvement=0.3,
                    implementation_complexity="low",
                    status="proposed",
                    created_at=datetime.now().isoformat(),
                ))

            if weakest == "pattern_accuracy":
                suggestions.append(ReflectionOptimization(
                    optimization_id=self._generate_id("opt"),
                    target_component="reflection_loop.pattern_recognition",
                    suggestion="优化模式识别逻辑，引入更细粒度的用户行为分类体系",
                    expected_improvement=0.25,
                    implementation_complexity="medium",
                    status="proposed",
                    created_at=datetime.now().isoformat(),
                ))

            if weakest == "insight_depth":
                suggestions.append(ReflectionOptimization(
                    optimization_id=self._generate_id("opt"),
                    target_component="reflection_loop.llm_prompt",
                    suggestion="深度优化反思 Prompt，增加多轮追问机制，引导 LLM 进行分层级的深度分析",
                    expected_improvement=0.4,
                    implementation_complexity="high",
                    status="proposed",
                    created_at=datetime.now().isoformat(),
                ))

            if weakest == "clarity":
                suggestions.append(ReflectionOptimization(
                    optimization_id=self._generate_id("opt"),
                    target_component="reflection_loop.output_format",
                    suggestion="强化输出格式约束，使用标准化的 Markdown 结构，提升可读性",
                    expected_improvement=0.2,
                    implementation_complexity="low",
                    status="proposed",
                    created_at=datetime.now().isoformat(),
                ))

        # 基于系统性偏差生成建议
        for bias in biases:
            if bias["severity"] == "high":
                suggestions.append(ReflectionOptimization(
                    optimization_id=self._generate_id("opt"),
                    target_component=f"bias_correction.{bias['type']}",
                    suggestion=bias["suggestion"],
                    expected_improvement=0.35,
                    implementation_complexity="medium",
                    status="proposed",
                    created_at=datetime.now().isoformat(),
                ))

        # 保存建议
        for opt in suggestions:
            self._save_optimization(opt)

        return suggestions

    def _save_optimization(self, optimization: ReflectionOptimization) -> None:
        """保存优化建议"""
        with open(self.optimizations_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(optimization), ensure_ascii=False) + "\n")

    def get_all_optimizations(self, status: Optional[str] = None) -> List[ReflectionOptimization]:
        """获取所有优化建议"""
        if not self.optimizations_file.exists():
            return []

        optimizations = []
        with open(self.optimizations_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    opt = ReflectionOptimization(**data)
                    if status is None or opt.status == status:
                        optimizations.append(opt)
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue

        return optimizations

    def mark_optimization_implemented(self, optimization_id: str, impact_score: float = 0.0) -> bool:
        """标记优化建议为已实现"""
        optimizations = self.get_all_optimizations()
        found = False

        temp_file = self.optimizations_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            for opt in optimizations:
                if opt.optimization_id == optimization_id:
                    opt.status = "implemented"
                    opt.implemented_at = datetime.now().isoformat()
                    opt.impact_score = impact_score
                    found = True
                f.write(json.dumps(asdict(opt), ensure_ascii=False) + "\n")

        temp_file.rename(self.optimizations_file)
        return found

    def generate_meta_report(self) -> str:
        """
        生成元反思综合报告

        Returns:
            格式化的报告字符串
        """
        trends = self.analyze_quality_trends()
        biases = self.identify_systemic_biases()
        optimizations = self.get_all_optimizations()

        lines = []
        lines.append("🧠 元反思综合报告")
        lines.append("═" * 60)
        lines.append("")

        # 质量趋势
        lines.append("📊 反思质量趋势分析:")
        if trends["has_data"]:
            lines.append(f"   评估样本数: {trends['total_evaluations']} 次")
            lines.append(f"   分析周期: 最近 {trends['analysis_days']} 天")
            lines.append(f"   平均综合评分: {trends['average_overall_score']} / 100")

            trend_emoji = {"improving": "↗️", "stable": "➡️", "declining": "↘️"}.get(trends["score_trend"], "➡️")
            trend_text = {"improving": "提升中", "stable": "稳定", "declining": "下降中"}.get(trends["score_trend"], "未知")
            lines.append(f"   质量趋势: {trend_emoji} {trend_text}")

            if trends["best_dimension"]:
                lines.append(f"   ✅ 最强维度: {trends['best_dimension']}")
            if trends["weakest_dimension"]:
                lines.append(f"   🔧 最弱维度: {trends['weakest_dimension']}")
        else:
            lines.append(f"   {trends['message']}")
        lines.append("")

        # 系统性偏差
        lines.append("🔍 系统性偏差识别:")
        high_severity = [b for b in biases if b["severity"] == "high"]
        medium_severity = [b for b in biases if b["severity"] == "medium"]
        lines.append(f"   高优先级偏差: {len(high_severity)} 个")
        lines.append(f"   中优先级偏差: {len(medium_severity)} 个")

        for bias in biases[:3]:  # 最多显示 3 个
            severity_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(bias["severity"], "⚪")
            lines.append(f"   {severity_emoji} {bias['description']}")
        lines.append("")

        # 优化建议
        lines.append("💡 优化建议概览:")
        by_status: Dict[str, int] = {}
        for opt in optimizations:
            by_status[opt.status] = by_status.get(opt.status, 0) + 1

        for status, count in by_status.items():
            lines.append(f"   • {status}: {count} 个")

        if optimizations:
            lines.append("")
            lines.append("   优先级建议:")
            for opt in sorted(optimizations, key=lambda x: -x.expected_improvement)[:3]:
                complexity_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(opt.implementation_complexity, "⚪")
                lines.append(f"   {complexity_emoji} {opt.suggestion[:50]}...")
        lines.append("")

        lines.append("💡 使用 'python -m zenskill meta suggestions' 查看完整优化建议")
        lines.append("💡 使用 'python -m zenskill meta implement <ID>' 标记优化为已实现")

        return "\n".join(lines)
