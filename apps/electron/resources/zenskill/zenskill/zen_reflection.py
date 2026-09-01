"""
禅思反思引擎 (ZenLoop L4+L5)

基于 zenthink ZenLoop 五层闭环:
- L4 反思 (Reflect): 生成结构化禅思报告
- L5 改进 (Improve): 生成可执行改进建议并追踪
"""

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional


class ZenReflectionEngine:
    """禅思反思引擎"""

    # PDCA 触发阈值
    PDCA_TRIGGERS = {
        "check": 20,   # 每 20 次操作 → PDCA Check
        "reflect": 50,  # 每 50 次操作 → 深度反思
        "improve": 100, # 每 100 次操作 → 改进建议
    }

    def __init__(self):
        self._reflection_dir = Path.home() / ".zenskill" / "zenloop"
        self._improvement_file = Path.home() / ".zenskill" / "zenloop" / "improvements.json"

    # ═══════════════════════════════════════════════════════════════
    # L4 反思 (Reflect)
    # ═══════════════════════════════════════════════════════════════

    def should_trigger(self, tool_count: int, elapsed_min: float,
                       session_end: bool = False) -> Optional[str]:
        """判断是否应触发反思, 返回触发类型或 None"""
        if session_end and tool_count > 5:
            return "session_end"
        for trigger, threshold in self.PDCA_TRIGGERS.items():
            if tool_count > 0 and tool_count % threshold == 0:
                return trigger
        return None

    def generate_reflection(self, session_data: Dict) -> str:
        """生成禅思反思报告 (L4)

        Args:
            session_data: {tool_count, elapsed_min, recent_tools, pipeline_insights, ...}

        Returns:
            格式化的禅思反思报告
        """
        tc = session_data.get("tool_count", 0)
        elapsed = session_data.get("elapsed_min", 0)
        recent = session_data.get("recent_tools", [])
        insights = session_data.get("pipeline_insights", [])
        anomalies = session_data.get("anomalies", [])

        lines = [
            "🧘 禅思反思报告",
            "═══════════════════════════════════════════════════════",
            "",
            f"📊 会话统计: {tc} 次操作, {elapsed:.0f} 分钟",
            f"🕐 生成时间: {time.strftime('%Y-%m-%d %H:%M')}",
            "",
        ]

        # 1. 工具使用回顾
        if recent:
            tool_counter = Counter(recent)
            lines.append("## 🔧 工具使用分布")
            for tool, count in tool_counter.most_common(5):
                bar = "█" * min(count, 20)
                lines.append(f"  {tool:10s} {bar} {count}")
            lines.append("")

        # 2. 模式洞察
        if insights:
            lines.append("## 💡 今日洞察")
            for ins in insights[:3]:
                lines.append(f"  • {ins}")
            lines.append("")

        # 3. 异常回顾
        if anomalies:
            lines.append("## ⚠️ 异常检测")
            for a in anomalies[:3]:
                lines.append(f"  • {a}")
            lines.append("")

        # 4. 禅思问题
        lines.append("## 🧘 禅思三问")
        lines.append("  1. 本次会话最大的收获是什么？")
        lines.append("  2. 有没有可以做得更好的地方？")
        lines.append("  3. 下次会话应该重点关注什么？")
        lines.append("")

        # 5. 保存
        self._save_reflection("\n".join(lines))

        return "\n".join(lines)

    def _save_reflection(self, content: str) -> None:
        """保存反思报告"""
        self._reflection_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        report_file = self._reflection_dir / f"reflection_{ts}.md"
        report_file.write_text(content, encoding="utf-8")
        # 更新 latest
        latest = self._reflection_dir / "latest_reflection.md"
        latest.write_text(content, encoding="utf-8")

    # ═══════════════════════════════════════════════════════════════
    # L5 改进 (Improve)
    # ═══════════════════════════════════════════════════════════════

    def generate_improvements(self, session_data: Dict) -> List[Dict]:
        """生成改进建议 (L5)

        Returns:
            [{area, suggestion, priority, actionable}]
        """
        improvements = []
        tc = session_data.get("tool_count", 0)
        elapsed = session_data.get("elapsed_min", 0)
        anomalies = session_data.get("anomalies", [])
        gaps = session_data.get("skill_gaps", [])

        # 1. 疲劳管理
        if elapsed > 90 and tc > 50:
            improvements.append({
                "area": "健康管理",
                "suggestion": "会话超过 90 分钟，建议设置番茄钟 (25min 专注 + 5min 休息)",
                "priority": "high",
                "actionable": "使用 zenskill doctor 设置定时提醒",
            })

        # 2. 工具均衡
        recent = session_data.get("recent_tools", [])
        read_only = all(t in ("Read",) for t in recent[-5:]) if recent else False
        if read_only and tc > 10:
            improvements.append({
                "area": "工具使用",
                "suggestion": "最近 5 次全是 Read，缺少 Edit/Write 实操，建议动手修改代码",
                "priority": "medium",
                "actionable": "选择一个问题直接用 Edit 修改",
            })

        # 3. 技能缺口
        if gaps:
            for g in gaps[:2]:
                improvements.append({
                    "area": "技能成长",
                    "suggestion": g.get("suggestion", f"关注 {g.get('domain', '')} 领域"),
                    "priority": "medium",
                    "actionable": f"运行 zenskill skill info 查看进度",
                })

        # 4. 异常处理
        if len(anomalies) > 2:
            improvements.append({
                "area": "系统健康",
                "suggestion": f"检测到 {len(anomalies)} 个异常，建议运行系统诊断",
                "priority": "high",
                "actionable": "运行 zenskill doctor",
            })

        # 5. 保存
        self._save_improvements(improvements)

        return improvements

    def _save_improvements(self, improvements: List[Dict]) -> None:
        """保存改进建议到追踪文件"""
        self._reflection_dir.mkdir(parents=True, exist_ok=True)

        existing = []
        if self._improvement_file.exists():
            try:
                existing = json.loads(self._improvement_file.read_text())
            except Exception:
                pass

        for imp in improvements:
            imp["timestamp"] = time.time()
            imp["implemented"] = False
            existing.append(imp)

        # 只保留最近 50 条
        existing = existing[-50:]
        self._improvement_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False))

    def get_last_improvements(self, unimplemented_only: bool = True) -> List[Dict]:
        """获取上次的改进建议 (供下次会话使用)"""
        if not self._improvement_file.exists():
            return []

        try:
            all_imps = json.loads(self._improvement_file.read_text())
        except Exception:
            return []

        if unimplemented_only:
            return [i for i in all_imps if not i.get("implemented", False)]
        return all_imps

    def mark_improvement_done(self, index: int) -> bool:
        """标记改进为已实现"""
        if not self._improvement_file.exists():
            return False
        try:
            imps = json.loads(self._improvement_file.read_text())
            if 0 <= index < len(imps):
                imps[index]["implemented"] = True
                imps[index]["implemented_at"] = time.time()
                self._improvement_file.write_text(json.dumps(imps, indent=2, ensure_ascii=False))
                return True
        except Exception:
            pass
        return False
