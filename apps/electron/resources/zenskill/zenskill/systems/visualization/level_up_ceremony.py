"""
ZenSkill - 境界突破仪式系统（增强版）

为技能境界提升生成有仪式感的祝贺文案，
包含：精美 ASCII 边框、能力变化对比、成长历程回顾、解锁能力展示

支持仪式持久化和历史查询。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from zenskill.core.paths import get_ceremony_dir
from zenskill.systems.visualization.ability_calculator import AbilityCalculator

if TYPE_CHECKING:
    from zenskill.systems.cultivating.skill_manifest import (
        SkillManifest,
        SkillLevel,
    )


class LevelUpCeremony:
    """境界突破仪式系统（增强版）"""

    # 各境界的祝贺风格
    CELEBRATION_STYLES = {
        "APPRENTICE": {
            "emojis": "🎉✨🌟",
            "title": "初露锋芒",
            "description": "从 0 到 1 的跨越，你已不再是新手",
        },
        "ADEPT": {
            "emojis": "🏆💫⭐",
            "title": "渐入佳境",
            "description": "技能日渐纯熟，开始形成自己的风格",
        },
        "EXPERT": {
            "emojis": "👑🚀🎖️",
            "title": "登堂入室",
            "description": "专家级水准，能处理复杂场景",
        },
        "MASTER": {
            "emojis": "🏯👨‍🎓🌟",
            "title": "炉火纯青",
            "description": "大师境界，收放自如，游刃有余",
        },
    }

    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id
        self.ceremony_dir = get_ceremony_dir()

    def generate_ceremony(
        self,
        manifest: SkillManifest,
        old_level: SkillLevel,
        new_level: SkillLevel,
        prev_ability_scores: Optional[Dict[str, int]] = None,
    ) -> str:
        """
        生成完整的境界突破仪式文案（增强版）

        Args:
            manifest: SkillManifest 实例
            old_level: 旧境界
            new_level: 新境界
            prev_ability_scores: 升级前的能力得分（可选，用于对比变化）

        Returns:
            格式化的仪式文案
        """
        # 边界检查
        if manifest is None:
            return "❌ 境界突破仪式：缺少技能状态"

        # 计算当前能力得分
        calc = AbilityCalculator()
        try:
            current_scores = calc.calculate_from_skill_manifest(manifest)
            current_scores_dict = {
                "proficiency": current_scores.proficiency,
                "stability": current_scores.stability,
                "satisfaction": current_scores.satisfaction,
                "responsiveness": current_scores.responsiveness,
                "memory": current_scores.memory,
                "composite": current_scores.composite,
            }
        except Exception:
            # 计算失败时使用默认值
            current_scores_dict = {
                "proficiency": 0,
                "stability": 0,
                "satisfaction": 0,
                "responsiveness": 0,
                "memory": 0,
                "composite": 0,
            }

        lines = []
        width = 58

        # ╔════════════════════════════════════════════════════╗
        # ║          🎉🎉🎉 恭喜！境界突破！🎉🎉🎉              ║
        # ╠════════════════════════════════════════════════════╣
        # ║                                                    ║
        # ║     【NOVICE】新手  →  【APPRENTICE】学徒          ║
        # ║                                                    ║

        # 顶部边框
        lines.append(f"╔{'═' * width}╗")

        # 标题
        style = self.CELEBRATION_STYLES.get(new_level.name, self.CELEBRATION_STYLES["APPRENTICE"])
        title_text = f"{style['emojis']} 恭喜！境界突破！{style['emojis']}"
        centered_title = title_text.center(width)
        lines.append(f"║{centered_title}║")

        # 分隔线
        lines.append(f"╠{'═' * width}╣")
        lines.append(f"║{' ' * width}║")

        # 副标题和描述
        subtitle = f"【{style['title']}】- {style['description']}"
        centered_sub = subtitle.center(width)
        lines.append(f"║{centered_sub}║")
        lines.append(f"║{' ' * width}║")

        # 境界变化
        level_change = f"【{old_level.name}】 → 【{new_level.name}】"
        centered_level = level_change.center(width)
        lines.append(f"║{centered_level}║")
        lines.append(f"║{' ' * width}║")

        # 分隔线 - 装饰
        decor_line = "  " + "─" * (width - 4) + "  "
        lines.append(f"║{decor_line}║")
        lines.append(f"║{' ' * width}║")

        # 成长历程回顾
        lines.append(f"║  📊 能力变化对比:{' ' * (width - 16)}║")
        comparison_lines = self._generate_ability_comparison(
            prev_ability_scores, current_scores_dict, width
        )
        for cl in comparison_lines:
            lines.append(f"║  {cl}{' ' * (width - len(cl) - 2)}║")

        lines.append(f"║{' ' * width}║")

        # 成长统计
        stats_lines = self._generate_journey_summary(manifest, width)
        for sl in stats_lines:
            lines.append(f"║  {sl}{' ' * (width - len(sl) - 2)}║")

        lines.append(f"║{' ' * width}║")

        # 解锁能力展示
        lines.append(f"║  🔓 解锁新能力:{' ' * (width - 15)}║")
        ability_lines = self._generate_unlocked_abilities(manifest, new_level, width)
        for al in ability_lines:
            lines.append(f"║     {al}{' ' * (width - len(al) - 5)}║")

        lines.append(f"║{' ' * width}║")

        # 下一目标
        next_goal_lines = self._generate_next_goal(manifest, width)
        for ngl in next_goal_lines:
            lines.append(f"║  {ngl}{' ' * (width - len(ngl) - 2)}║")

        lines.append(f"║{' ' * width}║")

        # 底部边框
        lines.append(f"╚{'═' * width}╝")

        # 结束祝福
        closing_msg = "💪 继续加油，向着更高的境界前进！"
        centered_closing = closing_msg.center(width + 2)
        lines.append(centered_closing)

        return "\n".join(lines)

    def _generate_ability_comparison(
        self,
        prev_scores: Optional[Dict[str, int]],
        curr_scores: Dict[str, int],
        width: int,
    ) -> List[str]:
        """生成能力变化对比行"""
        lines = []

        dim_names = {
            "proficiency": "熟练度",
            "stability": "稳定性",
            "satisfaction": "满意度",
            "responsiveness": "响应力",
            "memory": "记忆力",
            "composite": "综合分",
        }

        # 只显示几个关键维度
        show_dims = ["proficiency", "stability", "composite"]

        for dim in show_dims:
            curr = curr_scores.get(dim, 0)
            if prev_scores:
                prev = prev_scores.get(dim, 0)
                change = curr - prev
                change_str = f"+{change}" if change >= 0 else str(change)
                arrow = "▲" if change > 0 else "▼" if change < 0 else "─"

                # 生成迷你进度条
                bar_len = 15
                filled = round(curr / 100 * bar_len)
                bar = "█" * filled + "░" * (bar_len - filled)

                line = f"{dim_names[dim]}: {prev:2d} → {curr:2d}  {bar} {arrow}{change_str}"
            else:
                bar_len = 15
                filled = round(curr / 100 * bar_len)
                bar = "█" * filled + "░" * (bar_len - filled)
                line = f"{dim_names[dim]}: {curr:2d}  {bar}"

            lines.append(line)

        return lines

    def _generate_journey_summary(self, manifest: SkillManifest, width: int) -> List[str]:
        """生成成长历程摘要行"""
        lines = []
        stats = manifest.stats

        lines.append("✨ 成长历程回顾:")
        lines.append(f"   • 完成了 {stats.total_interactions} 次交互")

        if stats.total_interactions > 0:
            success_rate = stats.successful_executions / stats.total_interactions
            lines.append(f"   • 成功率 {success_rate * 100:.1f}%")

        return lines

    def _generate_unlocked_abilities(
        self,
        manifest: SkillManifest,
        new_level: SkillLevel,
        width: int,
    ) -> List[str]:
        """生成解锁的能力行"""
        lines = []

        # 获取新解锁的能力
        unlocked_abilities = manifest._get_abilities_for_level(new_level)

        if unlocked_abilities:
            for ability in unlocked_abilities:
                lines.append(f"✓ {ability}")
        else:
            lines.append("此境界没有新增能力，继续精进现有技能吧！")

        return lines

    def _generate_next_goal(self, manifest: SkillManifest, width: int) -> List[str]:
        """生成下一阶段目标行"""
        next_goal = manifest._get_next_milestone()
        lines = []
        lines.append("🎯 下一目标:")
        lines.append(f"   {next_goal}")
        return lines

    def save_ceremony(
        self,
        ceremony_content: str,
        old_level: str,
        new_level: str,
    ) -> str:
        """
        保存仪式内容到文件

        Args:
            ceremony_content: 仪式内容字符串
            old_level: 旧境界
            new_level: 新境界

        Returns:
            保存的文件路径，失败返回空字符串
        """
        if not ceremony_content:
            return ""

        try:
            # 确保目录存在
            self.ceremony_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{old_level}_to_{new_level}.txt"
            file_path = self.ceremony_dir / filename

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(ceremony_content)

            return str(file_path)
        except (OSError, PermissionError):
            return ""

    def get_latest_ceremony(self) -> Optional[str]:
        """
        获取最近一次境界突破的仪式内容

        Returns:
            仪式内容字符串，没有则返回 None
        """
        try:
            ceremonies = self.list_ceremonies()
            if not ceremonies:
                return None

            latest = ceremonies[-1]
            file_path = self.ceremony_dir / latest["filename"]

            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception:
            pass
        return None

    def list_ceremonies(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        列出所有历史仪式

        Args:
            limit: 最多返回数量（非正整数返回空）

        Returns:
            仪式列表，每个包含时间、境界变化、文件名
        """
        ceremonies = []

        # 边界检查
        if not isinstance(limit, int) or limit <= 0:
            return []

        try:
            # 确保目录存在（避免 glob 报错）
            if not self.ceremony_dir.exists():
                return []

            for file_path in sorted(self.ceremony_dir.glob("*.txt")):
                filename = file_path.name

                # 解析文件名: 20260518_143022_NOVICE_to_APPRENTICE.txt
                parts = filename.replace(".txt", "").split("_")
                if len(parts) >= 5:
                    date_str = parts[0]
                    time_str = parts[1]
                    old_level = parts[2]
                    new_level = parts[4] if len(parts) > 4 else "UNKNOWN"

                    ceremonies.append({
                        "filename": filename,
                        "date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}",
                        "time": f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}",
                        "old_level": old_level,
                        "new_level": new_level,
                    })
        except (OSError, IndexError):
            pass

        return ceremonies[-limit:]

    def generate_quick_celebration(
        self,
        old_level: SkillLevel,
        new_level: SkillLevel,
    ) -> str:
        """
        生成简洁的祝贺消息（用于日志或通知）

        Args:
            old_level: 旧境界
            new_level: 新境界

        Returns:
            简洁的祝贺消息
        """
        style = self.CELEBRATION_STYLES.get(new_level.name, self.CELEBRATION_STYLES["APPRENTICE"])
        return f"{style['emojis']} 恭喜！从 {old_level.name} 晋升到 {new_level.name}！"
