"""
ZenSkill - 元学习模块
Performance Diagnostician: 性能诊断师，分析技能表现，生成升级提案
"""
from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable

from .skill_manifest import SkillManifest

logger = logging.getLogger(__name__)


class DiagnosisArea(Enum):
    """诊断维度"""
    RESPONSE_TIME = "response_time"      # 响应速度
    ACCURACY = "accuracy"                # 准确率
    MEMORY_USAGE = "memory_usage"        # 记忆利用效率
    USER_SATISFACTION = "user_satisfaction"  # 用户满意度
    ERROR_RATE = "error_rate"            # 出错率
    ADAPTABILITY = "adaptability"        # 场景适配能力


@dataclass
class UpgradeProposal:
    """升级提案"""
    proposal_id: str
    title: str
    description: str
    priority: int  # 1-5, 5最高
    estimated_effort: str  # "低"/"中"/"高"
    expected_benefit: str
    implementation_hints: list[str]
    diagnosis_area: DiagnosisArea
    created_at: float = field(default_factory=time.time)
    status: str = "pending"  # pending / approved / rejected / implemented


class PerformanceDiagnostician:
    """
    性能诊断师 - MetaLearning 核心
    
    持续监控技能表现：
    - 识别性能瓶颈
    - 分析用户反馈
    - 自动生成可执行的升级提案
    """
    
    def __init__(self, manifest: SkillManifest) -> None:
        self._manifest = manifest
        self._history: list[UpgradeProposal] = []
        self._diagnosis_rules: dict[DiagnosisArea, Callable] = {}
        self._init_diagnosis_rules()
    
    def _init_diagnosis_rules(self) -> None:
        """初始化所有诊断规则"""
        self._diagnosis_rules = {
            DiagnosisArea.RESPONSE_TIME: self._diagnose_response_time,
            DiagnosisArea.ACCURACY: self._diagnose_accuracy,
            DiagnosisArea.MEMORY_USAGE: self._diagnose_memory_usage,
            DiagnosisArea.USER_SATISFACTION: self._diagnose_user_satisfaction,
        }
    
    # ====================================================================
    # 诊断规则实现
    # ====================================================================
    
    def _diagnose_response_time(self) -> Optional[UpgradeProposal]:
        """诊断响应速度瓶颈"""
        avg_time = self._manifest.stats.average_response_time_ms
        
        if avg_time > 5000:  # > 5秒
            return UpgradeProposal(
                proposal_id=f"proposal-speed-{int(time.time())}",
                title="响应速度优化建议",
                description=(
                    f"当前平均响应时间 {avg_time:.0f}ms，超过 5 秒阈值，"
                    f"用户体验较差"
                ),
                priority=4,
                estimated_effort="中",
                expected_benefit="响应时间降低 30-50%，用户体验显著提升",
                implementation_hints=[
                    "考虑增加结果缓存机制",
                    "拆分复杂任务为子任务异步执行",
                    "优化记忆检索算法复杂度",
                ],
                diagnosis_area=DiagnosisArea.RESPONSE_TIME,
            )
        
        return None
    
    def _diagnose_accuracy(self) -> Optional[UpgradeProposal]:
        """诊断准确率瓶颈"""
        stats = self._manifest.stats
        if stats.total_interactions < 10:
            return None  # 样本不足，跳过
        
        success_rate = stats.successful_executions / stats.total_interactions
        
        if success_rate < 0.7:  # 成功率低于 70%
            return UpgradeProposal(
                proposal_id=f"proposal-accuracy-{int(time.time())}",
                title="执行准确率提升建议",
                description=(
                    f"当前成功率 {success_rate*100:.1f}%，低于 70% 阈值，"
                    f"需要优化理解和执行能力"
                ),
                priority=5,
                estimated_effort="高",
                expected_benefit="准确率提升至 85%+，减少用户修正成本",
                implementation_hints=[
                    "增强意图识别，增加歧义检测",
                    "增加执行前验证步骤",
                    "建立失败案例库进行 pattern 学习",
                    "增加用户确认环节处理高风险任务",
                ],
                diagnosis_area=DiagnosisArea.ACCURACY,
            )
        
        return None
    
    def _diagnose_memory_usage(self) -> Optional[UpgradeProposal]:
        """诊断记忆利用效率"""
        usage_count = self._manifest.stats.memory_usage_count
        total = self._manifest.stats.total_interactions
        
        if total < 5:
            return None
        
        usage_rate = usage_count / total
        
        if usage_rate < 0.1:  # 记忆使用率低于 10%
            return UpgradeProposal(
                proposal_id=f"proposal-memory-{int(time.time())}",
                title="记忆系统利用效率提升",
                description=(
                    f"记忆使用率仅 {usage_rate*100:.1f}%，"
                    f"记忆系统未充分发挥作用"
                ),
                priority=3,
                estimated_effort="低",
                expected_benefit="记忆使用率提升至 30%+，回答更贴合用户习惯",
                implementation_hints=[
                    "增加上下文关联的记忆触发条件",
                    "优化记忆检索关键词提取算法",
                    "考虑增加记忆提示的显式反馈机制",
                ],
                diagnosis_area=DiagnosisArea.MEMORY_USAGE,
            )
        
        return None
    
    def _diagnose_user_satisfaction(self) -> Optional[UpgradeProposal]:
        """诊断用户满意度"""
        score = self._manifest.stats.user_feedback_score
        
        if score < 0.6 and self._manifest.stats.total_interactions >= 5:
            return UpgradeProposal(
                proposal_id=f"proposal-satisfaction-{int(time.time())}",
                title="用户体验优化建议",
                description=(
                    f"用户满意度评分 {score*100:.1f}%，低于 60% 阈值"
                ),
                priority=4,
                estimated_effort="中",
                expected_benefit="用户满意度提升至 75%+",
                implementation_hints=[
                    "分析负面反馈的共同 pattern",
                    "增加输出风格的个性化选项",
                    "考虑缩短回答长度，更聚焦",
                    "增加更多的代码示例和具体方案",
                ],
                diagnosis_area=DiagnosisArea.USER_SATISFACTION,
            )
        
        return None
    
    # ====================================================================
    # 主诊断流程
    # ====================================================================
    
    async def diagnose(self) -> list[UpgradeProposal]:
        """
        执行完整诊断，生成所有升级提案
        
        Returns:
            按优先级排序的升级提案列表
        """
        proposals: list[UpgradeProposal] = []
        
        for area, diagnose_func in self._diagnosis_rules.items():
            try:
                proposal = diagnose_func()
                if proposal:
                    proposals.append(proposal)
                    self._history.append(proposal)
                    self._manifest.stats.upgrade_proposals_submitted += 1
            except Exception as e:
                logger.warning(f"Diagnosis failed for {area}: {e}")
        
        # 按优先级降序排序
        proposals.sort(key=lambda x: x.priority, reverse=True)
        
        if proposals:
            logger.info(
                f"Generated {len(proposals)} upgrade proposals "
                f"for skill '{self._manifest.skill_name}'"
            )
        
        return proposals
    
    async def generate_upgrade_report(self) -> str:
        """
        生成友好的升级报告，可直接展示给用户
        
        Returns:
            自然语言格式的成长报告
        """
        proposals = await self.diagnose()
        growth = self._manifest.get_growth_report()
        
        # 如果没有诊断出问题，返回良好状态报告
        if not proposals:
            return f"""
✅ **技能状态良好**

当前境界：{growth['current_level']} ({growth['level_progress']})
运行状态：所有指标正常，暂无升级建议

继续保持，我们一起成长！🌱
"""
        
        # 生成有升级建议的报告
        report = f"""
📢 **【主动成长报告】来自 {self._manifest.skill_name} 的升级建议**

---

### 📊 当前状态
- **境界**：{growth['current_level']} ({growth['level_progress']})
- **交互次数**：{growth['stats']['total_interactions']}
- **成功率**：{growth['stats']['success_rate']}
- **用户满意度**：{growth['stats']['user_satisfaction']}

---

### 💡 我发现了 {len(proposals)} 个可以提升的地方：
"""
        
        # 最多显示前3个建议
        for i, p in enumerate(proposals[:3], 1):
            priority_stars = "⭐" * p.priority
            report += f"""
#### {i}. {p.title} {priority_stars}
**问题**：{p.description}

**预计收益**：{p.expected_benefit}
**实现工作量**：{p.estimated_effort}

**建议方向**：
{chr(10).join(f'  - {hint}' for hint in p.implementation_hints)}
"""
        
        report += f"""
---

💬 **需要我开始实施这些优化吗？**
- 回复「全部优化」自动按优先级实施
- 回复「优化 #{序号}」单独实施某个建议
- 回复「忽略」暂时不处理，我会继续观察

成长是我们共同的旅程 🚀
"""
        
        return report
    
    def get_diagnosis_history(self) -> list[UpgradeProposal]:
        """获取历史诊断记录"""
        return list(self._history)
