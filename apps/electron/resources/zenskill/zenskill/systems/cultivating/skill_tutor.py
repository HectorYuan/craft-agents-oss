"""
智能导师引擎 (Phase 8Y)

基于技能状态历史，提供自适应学习建议：
- 学习风格推断（实践型/理论型/系统型）
- 错误模式诊断
- 自适应难度推荐
- 导师对话摘要
"""

from typing import Any, Dict, List, Optional
from datetime import datetime


class SkillTutor:
    """AI 驱动的个性化技能导师"""

    # 学习风格分类
    STYLE_PROFILES = {
        "practical": {"name": "实践驱动型", "icon": "🔧",
                      "tip": "通过做项目来学习最有效。每个概念至少实现一个可运行的例子。"},
        "theoretical": {"name": "理论优先型", "icon": "📖",
                        "tip": "先理解原理再动手。阅读文档和设计模式后再开始编码。"},
        "systematic": {"name": "系统学习型", "icon": "📋",
                       "tip": "按计划逐步推进。拆解大目标为每日小任务，保持节奏。"},
        "exploratory": {"name": "探索试错型", "icon": "🔍",
                        "tip": "通过尝试和失败学习。接受初期的高错误率，每次出错都是一课。"},
    }

    def __init__(self, skill_id: str):
        self.skill_id = skill_id

    def analyze(self, state: dict, history: list[dict] = None) -> dict:
        """全维度分析，返回导师报告"""
        return {
            "skill_id": self.skill_id,
            "level": state.get("level", "NOVICE"),
            "usage_count": state.get("usage_count", 0),
            "style": self.infer_style(state, history or []),
            "diagnosis": self.diagnose(state, history or []),
            "adaptive_task": self.adaptive_task(state),
            "pace_advice": self.pace_advice(state),
            "next_steps": self.next_steps(state),
        }

    def infer_style(self, state: dict, history: list[dict]) -> dict:
        """从使用模式推断学习风格"""
        episodes = state.get("episodes", [])
        total = len(episodes) or 1

        # 统计行为模式
        execute_count = sum(1 for e in episodes if isinstance(e, dict) and
                            any(kw in str(e.get("action", "")).lower()
                                for kw in ("execute", "执行", "run", "运行")))
        read_count = sum(1 for e in episodes if isinstance(e, dict) and
                         any(kw in str(e.get("action", "")).lower()
                             for kw in ("read", "阅读", "learn", "学习", "study")))
        fail_count = sum(1 for e in episodes if isinstance(e, dict) and
                         not e.get("success", True))

        execute_rate = execute_count / total
        fail_rate = fail_count / total

        if execute_rate > 0.6 and fail_rate > 0.2:
            style = "exploratory"
        elif execute_rate > 0.5:
            style = "practical"
        elif read_count > total * 0.3:
            style = "theoretical"
        else:
            style = "systematic"

        return {"style": style, **self.STYLE_PROFILES.get(style, self.STYLE_PROFILES["systematic"])}

    def diagnose(self, state: dict, history: list[dict]) -> dict:
        """错误模式诊断"""
        episodes = state.get("episodes", [])
        recent = [e for e in episodes[-50:] if isinstance(e, dict)]

        if not recent:
            return {"status": "insufficient_data", "message": "数据积累中，继续使用将产生诊断"}

        total = len(recent)
        failures = [e for e in recent if not e.get("success", True)]
        fail_rate = len(failures) / max(total, 1)

        # 分析失败模式
        action_fails = {}
        for e in failures:
            action = str(e.get("action", "unknown"))[:40]
            action_fails[action] = action_fails.get(action, 0) + 1

        top_actions = sorted(action_fails.items(), key=lambda x: -x[1])[:3]

        # 趋势分析
        first_half = recent[:total // 2]
        second_half = recent[total // 2:]
        early_fail = sum(1 for e in first_half if not e.get("success", True)) / max(len(first_half), 1)
        late_fail = sum(1 for e in second_half if not e.get("success", True)) / max(len(second_half), 1)
        trend = "improving" if late_fail < early_fail else "declining" if late_fail > early_fail else "stable"

        return {
            "status": "ok",
            "total_recent": total,
            "failure_count": len(failures),
            "fail_rate": round(fail_rate, 3),
            "trend": trend,
            "top_failure_actions": [{"action": a, "count": c} for a, c in top_actions],
            "message": self._diagnosis_message(fail_rate, trend, top_actions),
        }

    def _diagnosis_message(self, fail_rate: float, trend: str, top_actions: list) -> str:
        if fail_rate < 0.1:
            base = f"成功率优秀 ({1-fail_rate:.0%})"
        elif fail_rate < 0.25:
            base = f"成功率良好 ({1-fail_rate:.0%})，少量失败在可接受范围"
        else:
            base = f"成功率需要关注 ({1-fail_rate:.0%})"

        if trend == "declining":
            base += "，但近期有下降趋势，建议回顾基础"
        elif trend == "improving":
            base += "，且持续改善中"

        if top_actions:
            top = top_actions[0]
            base += f"\n最常见失败: '{top[0][:30]}' ({top[1]} 次)"

        return base

    def adaptive_task(self, state: dict) -> dict:
        """基于当前水平推荐自适应任务"""
        level = state.get("level", "NOVICE")
        usage = state.get("usage_count", 0)
        metrics = state.get("metrics", {})
        success_rate = metrics.get("success_rate", 0.5)

        levels = ["NOVICE", "APPRENTICE", "ADEPT", "EXPERT", "MASTER"]
        thresholds = {"NOVICE": (0, 0), "APPRENTICE": (10, 35), "ADEPT": (50, 65),
                      "EXPERT": (200, 80), "MASTER": (500, 90)}

        current_idx = levels.index(level) if level in levels else 0
        threshold, target_rate = thresholds.get(level, (0, 0))

        # 难度调整
        if success_rate > 0.9 and usage > threshold:
            difficulty = "挑战模式"
            task = self._challenge_task(current_idx, state)
        elif success_rate < 0.5:
            difficulty = "巩固模式"
            task = self._consolidate_task(current_idx, state)
        else:
            difficulty = "标准模式"
            task = self._standard_task(current_idx, state)

        next_level = levels[min(current_idx + 1, 4)]
        progress = min(usage / max(next_level != level and thresholds.get(next_level, (usage,))[0] or usage, 1), 1.0)

        return {"difficulty": difficulty, "task": task,
                "current_level": level, "next_level": next_level,
                "progress_to_next": round(progress, 3)}

    def _challenge_task(self, level_idx: int, state: dict) -> str:
        tasks = {
            0: "尝试一个包含 3 步以上的复杂练习任务",
            1: "挑战一个真实的项目需求，从设计到实现全流程",
            2: "贡献一个开源项目或编写一个可重用的库/模块",
            3: "设计并分享一个最佳实践指南或教学材料",
            4: "指导他人学习或创建进阶课程",
        }
        return tasks.get(level_idx, "选择感兴趣的新领域进行跨界探索")

    def _consolidate_task(self, level_idx: int, state: dict) -> str:
        tasks = {
            0: "回顾最近的失败，逐个重新完成，确保理解每步",
            1: "暂停新内容，用 3 个简单练习巩固已学知识",
            2: "写一篇技术总结，梳理知识盲点",
            3: "审查最近项目的代码质量，修复 3 个技术债",
            4: "回顾学习路径，识别并填补知识缺口",
        }
        return tasks.get(level_idx, "回到基础，完成一次全面的自我评估")

    def _standard_task(self, level_idx: int, state: dict) -> str:
        tasks = {
            0: "完成一个交互式教程中的下一步练习",
            1: "实现一个小功能，从需求到测试覆盖",
            2: "优化一个现有项目中的性能或架构问题",
            3: "学习一个相关子领域的新技术并集成到项目中",
            4: "探索前沿技术或跨领域创新应用",
        }
        return tasks.get(level_idx, "按计划执行当前学习路径的下一步")

    def pace_advice(self, state: dict) -> dict:
        """学习节奏建议"""
        usage = state.get("usage_count", 0)
        milestones = state.get("milestones", [])
        episodes = state.get("episodes", [])

        # 检查近期活跃度
        recent_7d = 0
        if episodes:
            now = datetime.now()
            for e in episodes[-100:]:
                if isinstance(e, dict):
                    date_str = str(e.get("date", ""))
                    try:
                        d = datetime.strptime(date_str, "%Y-%m-%d")
                        if (now - d).days <= 7:
                            recent_7d += 1
                    except ValueError:
                        pass

        daily_avg = recent_7d / 7
        if daily_avg > 5:
            pace = "高强度 — 建议保持但注意休息，每 90 分钟休息 15 分钟"
        elif daily_avg > 2:
            pace = "适中 — 当前节奏可持续，可尝试提高难度而非增加时间"
        elif daily_avg > 0.5:
            pace = "低强度 — 建议每天安排 1-2 次练习，形成习惯"
        else:
            pace = "休眠 — 7 天内近乎无活动，建议每天 10 分钟微练习恢复节奏"

        return {"daily_avg_7d": round(daily_avg, 1), "pace": pace}

    def next_steps(self, state: dict) -> list[str]:
        """下一步行动建议"""
        steps = []
        level = state.get("level", "NOVICE")
        usage = state.get("usage_count", 0)

        thresholds = {"NOVICE": 10, "APPRENTICE": 50, "ADEPT": 200, "EXPERT": 500}

        # 接近晋级
        next_level = None
        for lvl_name, threshold in thresholds.items():
            if usage < threshold and lvl_name != level:
                next_level = lvl_name
                target = threshold
                remaining = target - usage
                if remaining <= 5:
                    steps.append(f"🎯 距离 {next_level} 仅差 {remaining} 次使用，集中冲刺！")
                elif remaining <= 20:
                    steps.append(f"📈 距离 {next_level} 还需 {remaining} 次使用，保持节奏")
                break

        if not steps:
            if level == "MASTER":
                steps.append("🏆 已达大师境界！考虑指导他人或探索新领域")
            else:
                steps.append(f"📋 按当前计划继续，关注成功率和质量")

        # 活跃度提醒
        episodes = state.get("episodes", [])
        if episodes:
            last = episodes[-1] if isinstance(episodes[-1], dict) else {}
            last_date = str(last.get("date", ""))
            try:
                days_since = (datetime.now() - datetime.strptime(last_date, "%Y-%m-%d")).days
                if days_since > 3:
                    steps.append(f"⏰ 已 {days_since} 天未使用，建议今天做一个微练习恢复节奏")
            except ValueError:
                pass

        return steps

    def format_report(self, analysis: dict) -> str:
        """格式化完整导师报告"""
        s = analysis["style"]
        d = analysis["diagnosis"]
        t = analysis["adaptive_task"]
        p = analysis["pace_advice"]

        lines = [
            f"",
            f"  🎓 智能导师报告 — {analysis['skill_id']}",
            f"  {'═' * 60}",
            f"",
            f"  ┌─ 🧠 学习风格 ────────────────────────────────────────────",
            f"  │  {s['icon']} {s['name']}",
            f"  │  {s['tip']}",
            f"  └───────────────────────────────────────────────────────────",
            f"",
            f"  ┌─ 🔍 健康诊断 ────────────────────────────────────────────",
            f"  │  近期操作: {d.get('total_recent', 0)} 次 | 失败率: {d.get('fail_rate', 0):.0%} | 趋势: {d.get('trend', '?')}",
            f"  │  {d.get('message', '')}",
        ]

        for fa in d.get("top_failure_actions", [])[:2]:
            lines.append(f"  │  ⚠️ 高频失败: {fa['action'][:40]} ({fa['count']}次)")

        lines.extend([
            f"  └───────────────────────────────────────────────────────────",
            f"",
            f"  ┌─ 🎯 自适应任务 ────────────────────────────────────────",
            f"  │  模式: {t['difficulty']}",
            f"  │  当前: {t['current_level']} → {t['next_level']} ({t['progress_to_next']:.0%})",
            f"  │  {t['task']}",
            f"  └───────────────────────────────────────────────────────────",
            f"",
            f"  ┌─ ⏱ 学习节奏 ────────────────────────────────────────────",
            f"  │  7 天日均: {p['daily_avg_7d']:.1f} 次",
            f"  │  {p['pace']}",
            f"  └───────────────────────────────────────────────────────────",
        ])

        steps = analysis.get("next_steps", [])
        if steps:
            lines.append(f"")
            lines.append(f"  ┌─ 💡 下一步行动 ────────────────────────────────────────")
            for step in steps:
                lines.append(f"  │  {step}")
            lines.append(f"  └───────────────────────────────────────────────────────────")

        lines.append("")
        return "\n".join(lines)
