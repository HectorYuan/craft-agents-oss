"""
ZenSkill - 修炼体系主系统

让技能拥有生命感：
1. 管理每个技能的修炼档案（SkillManifest）
2. 记录交互，推进境界成长
3. 触发 MetaLearning 诊断，生成升级提案
4. 成长报告主动推送
"""
from __future__ import annotations

import logging
from typing import Optional, Any

from ...core.base import (
    BaseSystem,
    SystemConfig,
    SystemMetadata,
    SystemType,
)

from .skill_manifest import SkillManifest, SkillLevel
from .meta_learning import PerformanceDiagnostician, UpgradeProposal

logger = logging.getLogger(__name__)


class CultivatingSystem(BaseSystem):
    """
    修炼体系系统 - ZenSkill 的灵魂
    
    核心职责：
    - 技能注册与成长档案管理
    - 记录交互，推进五重境界成长
    - 性能诊断与升级提案生成
    - 主动成长报告推送
    """
    
    def __init__(self) -> None:
        self._manifests: dict[str, SkillManifest] = {}  # skill_id -> 修炼档案
        self._diagnosticians: dict[str, PerformanceDiagnostician] = {}
        self._memory_ref: Optional[Any] = None  # 记忆系统引用
        self._zenloop_ref: Optional[Any] = None  # ZenLoop 引用
        
        # 成长报告配置
        self._report_config = {
            "auto_report_enabled": True,
            "report_every_n_interactions": 20,  # 每20次交互主动发一次成长报告
            "interaction_since_last_report": 0,
        }
    
    @property
    def system_type(self) -> SystemType:
        return SystemType.CULTIVATING
    
    @property
    def metadata(self) -> SystemMetadata:
        return SystemMetadata(
            name="cultivating-system",
            version="1.0.0",
            description="Cultivating - 修炼体系 + MetaLearning 自我成长引擎",
            priority=10,  # 高优先级，先初始化
            dependencies=[SystemType.MEMORY],
        )
    
    # ====================================================================
    # 初始化与绑定
    # ====================================================================
    
    async def initialize(self, config: SystemConfig) -> None:
        """初始化修炼体系系统"""
        await super().initialize(config)
        
        # 初始化默认的 ZenSkill 主技能档案
        if "zenskill-main" not in self._manifests:
            self.register_skill("zenskill-main", "ZenSkill 核心引擎")
        
        logger.info(
            f"Cultivating system initialized, "
            f"{len(self._manifests)} skills registered"
        )
    
    def bind_memory(self, memory_system: Any) -> None:
        """
        绑定记忆系统，用于存储修炼档案和成长记录
        
        Args:
            memory_system: MetaMemory 系统实例
        """
        self._memory_ref = memory_system
        logger.info("Cultivating system bound to MetaMemory")
    
    def bind_zenloop(self, zenloop_system: Any) -> None:
        """
        绑定 ZenLoop 系统，触发成长反思
        
        Args:
            zenloop_system: ZenLoopSystem 系统实例
        """
        self._zenloop_ref = zenloop_system
        logger.info("Cultivating system bound to ZenLoop")
    
    # ====================================================================
    # 技能管理
    # ====================================================================
    
    def register_skill(self, skill_id: str, skill_name: str) -> None:
        """
        注册一个新技能，创建对应的修炼档案
        
        Args:
            skill_id: 技能唯一标识
            skill_name: 技能名称（用于展示）
        """
        if skill_id in self._manifests:
            logger.warning(f"Skill {skill_id} already registered, skipping")
            return
        
        # 创建修炼档案
        manifest = SkillManifest(skill_id=skill_id, skill_name=skill_name)
        self._manifests[skill_id] = manifest
        
        # 创建对应的性能诊断师
        self._diagnosticians[skill_id] = PerformanceDiagnostician(manifest)
        
        logger.info(
            f"Registered skill for cultivation: "
            f"{skill_name} ({skill_id})"
        )
    
    def get_manifest(self, skill_id: str) -> Optional[SkillManifest]:
        """获取技能的修炼档案"""
        return self._manifests.get(skill_id)
    
    def list_skills(self) -> list[dict]:
        """列出所有已注册技能的状态"""
        return [
            manifest.get_growth_report()
            for manifest in self._manifests.values()
        ]
    
    # ====================================================================
    # 成长记录核心方法
    # ====================================================================
    
    async def record_interaction(
        self,
        skill_id: str,
        success: bool,
        feedback_score: float = 0.5,
        response_time_ms: float = 0.0,
        memory_used: bool = False,
    ) -> dict[str, Any]:
        """
        记录一次技能交互，推进修炼
        
        如果技能未注册，自动注册
        
        Args:
            skill_id: 技能ID
            success: 是否执行成功
            feedback_score: 用户反馈评分 0-1
            response_time_ms: 响应时间（毫秒）
            memory_used: 是否使用了记忆系统
        
        Returns:
            成长状态变化字典:
            - level_changed: 是否境界提升
            - old_level: 原境界
            - new_level: 新境界
            - progress: 当前境界进度(百分比字符串)
            - report_triggered: 是否触发了主动成长报告
        """
        if skill_id not in self._manifests:
            self.register_skill(skill_id, f"Skill-{skill_id}")
        
        manifest = self._manifests.get(skill_id)
        if not manifest:
            logger.warning(f"Skill {skill_id} not registered for cultivation")
            return {}
        
        # 记录之前的状态
        old_level = manifest.current_level
        old_progress = manifest.level_progress
        
        # 更新响应时间（移动平均，平滑处理）
        manifest.stats.average_response_time_ms = (
            manifest.stats.average_response_time_ms * 0.9
            + response_time_ms * 0.1
        )
        
        # 更新记忆使用计数
        if memory_used:
            manifest.stats.memory_usage_count += 1
        
        # 记录交互，推进境界
        manifest.record_interaction(success, feedback_score)
        
        # 检查是否触发主动成长报告
        report_triggered = await self._check_and_trigger_growth_report(skill_id)
        
        # 准备返回结果
        result = {
            "level_changed": manifest.current_level != old_level,
            "old_level": old_level.name,
            "new_level": manifest.current_level.name,
            "progress": f"{manifest.level_progress * 100:.1f}%",
            "report_triggered": report_triggered,
        }
        
        # 如果境界提升，记录到记忆
        if result["level_changed"]:
            await self._record_level_up_to_memory(manifest)
        
        # 记录成长事件到情景记忆
        if self._memory_ref:
            await self._memory_ref.store(
                content=(
                    f"技能交互记录：{'成功' if success else '失败'}，"
                    f"用户评分 {feedback_score*100:.0f}%，"
                    f"境界进度 {result['progress']}"
                ),
                memory_type="episodic",
                importance=0.4,
                tags={"成长", "修炼", skill_id},
            )
        
        # 境界提升打日志
        if result["level_changed"]:
            logger.info(
                f"🎉 Skill '{skill_id}' level up! "
                f"{result['old_level']} → {result['new_level']}"
            )
        
        return result
    
    async def _check_and_trigger_growth_report(self, skill_id: str) -> bool:
        """检查是否应该主动发起成长报告"""
        if not self._report_config["auto_report_enabled"]:
            return False
        
        self._report_config["interaction_since_last_report"] += 1
        
        n = self._report_config["interaction_since_last_report"]
        threshold = self._report_config["report_every_n_interactions"]
        
        if n >= threshold:
            self._report_config["interaction_since_last_report"] = 0
            
            # 生成并存储升级报告到记忆
            diagnostician = self._diagnosticians.get(skill_id)
            if diagnostician and self._memory_ref:
                report = await diagnostician.generate_upgrade_report()
                await self._memory_ref.store(
                    content=report,
                    memory_type="episodic",
                    importance=0.8,
                    tags={"成长报告", "升级建议", skill_id},
                )
                logger.info(f"Growth report triggered for skill '{skill_id}'")
            return True
        
        return False
    
    async def _record_level_up_to_memory(self, manifest: SkillManifest) -> None:
        """境界提升时，存入语义记忆"""
        if not self._memory_ref:
            return
        
        milestone = manifest.milestones[-1]
        
        # 存入语义记忆 - 境界提升事实
        await self._memory_ref.store(
            content="",
            memory_type="semantic",
            subject=manifest.skill_name,
            predicate="晋升至",
            object=milestone.level.name,
            importance=0.9,
        )
        
        # 记录解锁的每个能力
        for ability in milestone.unlocked_abilities:
            await self._memory_ref.store(
                content="",
                memory_type="semantic",
                subject=manifest.skill_name,
                predicate="解锁能力",
                object=ability,
                importance=0.7,
            )
    
    # ====================================================================
    # 诊断与升级提案
    # ====================================================================
    
    async def diagnose_performance(self, skill_id: str) -> list[UpgradeProposal]:
        """
        执行性能诊断，获取升级提案
        
        Args:
            skill_id: 技能ID
        
        Returns:
            升级提案列表
        """
        diagnostician = self._diagnosticians.get(skill_id)
        if not diagnostician:
            return []
        
        return await diagnostician.diagnose()
    
    async def get_growth_report(self, skill_id: str) -> str:
        """
        获取友好的成长报告（自然语言格式）
        
        Args:
            skill_id: 技能ID
        
        Returns:
            可直接展示给用户的成长报告
        """
        diagnostician = self._diagnosticians.get(skill_id)
        if not diagnostician:
            return f"技能 {skill_id} 未注册修炼体系，请先注册"
        
        return await diagnostician.generate_upgrade_report()
    
    # ====================================================================
    # 配置管理
    # ====================================================================
    
    def set_auto_report_enabled(self, enabled: bool) -> None:
        """设置是否启用主动成长报告"""
        self._report_config["auto_report_enabled"] = enabled
        logger.info(f"Auto growth report {'enabled' if enabled else 'disabled'}")
    
    def set_report_frequency(self, every_n_interactions: int) -> None:
        """设置成长报告触发频率"""
        self._report_config["report_every_n_interactions"] = max(5, every_n_interactions)
        logger.info(f"Report frequency set to every {every_n_interactions} interactions")
    
    # ====================================================================
    # 系统关闭
    # ====================================================================
    
    async def shutdown(self) -> None:
        """关闭系统，清理资源"""
        await super().shutdown()
        
        # 保存所有修炼档案（如果绑定了记忆系统）
        if self._memory_ref:
            for manifest in self._manifests.values():
                await self._memory_ref.store(
                    content=f"技能修炼档案保存：{manifest.skill_name}",
                    memory_type="episodic",
                    importance=0.5,
                    tags={"系统关闭", "存档", manifest.skill_id},
                )
        
        logger.info("Cultivating system shutdown complete")
