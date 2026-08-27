"""
ZenSkill - 有生命、会成长的技能系统

SkillAgent: 主类，整合所有核心系统
- 🧠 MetaMemory: 三层仿生记忆系统
- 🏆 Cultivating: 修炼体系 + 元学习自我诊断
- 🧘 ZenLoop: 禅思循环认知引擎
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Any

from ..core.registry import registry, SystemConfig
from ..core.base import SystemType
from ..core.llm_provider import (
    get_llm_provider,
    BaseLLMProvider,
    ChatMessage,
)

from ..systems.memory import MetaMemory
from ..systems.cultivating import CultivatingSystem
from ..systems.zenloop import ZenLoopSystem

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Agent 配置"""
    # 记忆系统配置
    working_memory_size: int = 20
    episodic_memory_size: int = 1000
    
    # 修炼体系配置
    auto_growth_report: bool = True
    growth_report_interval: int = 20  # 每 20 次交互发一次成长报告
    
    # ZenLoop 配置
    enable_zenloop: bool = True
    enable_background_worker: bool = True
    
    # 调试
    log_level: str = "INFO"


@dataclass
class InteractionResult:
    """一次用户交互的完整结果"""
    response: str
    growth_info: dict[str, Any]
    memories_used: list[Any]
    loop_results: list[Any]
    upgrade_suggestions: list[str]


class SkillAgent:
    """
    ZenSkill Agent - 有生命、会成长的智能助手
    
    核心特性：
    🧠 三层记忆系统 - 工作记忆/情景记忆/语义记忆
    🏆 五重境界修炼 - 从新手到大师，越用越懂你
    🧘 四大禅思循环 - 反思/整合/洞见/净化
    
    每次使用都在成长，像人一样思考、学习、进步
    """
    
    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        self._config = config or AgentConfig()
        self._initialized = False
        self._interaction_count = 0
        
        # 系统引用
        self._memory: Optional[MetaMemory] = None
        self._cultivating: Optional[CultivatingSystem] = None
        self._zenloop: Optional[ZenLoopSystem] = None
        
        logger.debug("SkillAgent created")
    
    async def initialize(self) -> None:
        """
        初始化 Agent，启动所有核心系统
        
        初始化顺序：
        1. 记忆系统（基础）
        2. 修炼体系（依赖记忆）
        3. ZenLoop（依赖记忆和修炼）
        """
        if self._initialized:
            logger.warning("SkillAgent already initialized")
            return
        
        logger.info("=" * 50)
        logger.info("🧘 SkillAgent 初始化开始")
        logger.info("=" * 50)
        
        # 1. 注册所有系统到 Registry
        # 记忆系统
        memory = MetaMemory(
            working_size=self._config.working_memory_size,
            episodic_size=self._config.episodic_memory_size,
        )
        registry.register(memory, SystemConfig())
        
        # 修炼体系
        cultivating = CultivatingSystem()
        registry.register(cultivating, SystemConfig())
        
        # ZenLoop
        if self._config.enable_zenloop:
            zenloop = ZenLoopSystem()
            registry.register(zenloop, SystemConfig())
        
        # 2. 初始化所有系统
        await registry.initialize_all()
        
        # 3. 获取系统实例
        self._memory = registry.get_typed(SystemType.MEMORY, MetaMemory)
        self._cultivating = registry.get_typed(
            SystemType.CULTIVATING, CultivatingSystem
        )
        if self._config.enable_zenloop:
            self._zenloop = registry.get_typed(
                SystemType.ZENLOOP, ZenLoopSystem
            )
        
        # 4. 系统间绑定
        if self._cultivating and self._memory:
            self._cultivating.bind_memory(self._memory)
        
        if self._zenloop:
            if self._memory:
                self._zenloop.bind_memory(self._memory)
            if self._cultivating:
                self._zenloop.bind_cultivating(self._cultivating)
            
            # 启动后台循环
            if self._config.enable_background_worker:
                self._zenloop.start_background()
        
        # 存入第一条记忆
        if self._memory:
            await self._memory.store(
                content="ZenSkill 系统启动，开始新的学习旅程",
                memory_type="episodic",
                importance=1.0,
                tags={"系统", "启动"},
            )
        
        self._initialized = True

        # 记录会话开始事件
        try:
            from ..mirroring.event_collector import EventCollector
            from ..mirroring.models import EventType
            self._event_collector = EventCollector()
            self._event_collector.record_session_event(
                event_type=EventType.SESSION_START,
                skill_id="zenskill-agent",
            )
        except Exception:
            self._event_collector = None
        
        logger.info("=" * 50)
        logger.info("✅ SkillAgent 初始化完成!")
        logger.info("=" * 50)
        logger.info(f"   记忆系统: {'✅' if self._memory else '❌'}")
        logger.info(f"   修炼体系: {'✅' if self._cultivating else '❌'}")
        logger.info(f"   禅思循环: {'✅' if self._zenloop else '❌'}")
    
    # ====================================================================
    # 核心交互方法
    # ====================================================================
    
    async def chat(
        self,
        user_input: str,
        context: Optional[dict[str, Any]] = None,
    ) -> InteractionResult:
        """
        和 ZenSkill 对话
        
        完整流程：
        1. 记忆检索 - 从记忆中查找相关内容
        2. 生成回复 - 基于记忆和当前输入
        3. 存入记忆 - 把这次对话存入情景记忆
        4. 触发反思 - ZenLoop 复盘这次交互
        5. 成长更新 - 更新修炼体系进度
        
        Args:
            user_input: 用户输入
            context: 额外上下文
        
        Returns:
            完整的交互结果
        """
        if not self._initialized:
            await self.initialize()
        
        self._interaction_count += 1
        context = context or {}

        logger.debug(f"Interaction #{self._interaction_count}: {user_input[:50]}...")

        # 记录用户输入事件（数据最小化：只存 hash）
        if getattr(self, '_event_collector', None):
            try:
                self._event_collector.record_user_input(
                    skill_id="zenskill-agent",
                    input_text=user_input,
                )
            except Exception:
                pass
        
        # 1. 上下文感知的记忆检索
        memories_used = []
        if self._memory:
            memories_used = await self._memory.retrieve_with_context(
                query=user_input,
                current_context=context,
                top_k=5,
            )
        
        # 2. 生成回复（通过 LLM Provider）
        response = await self._generate_response(user_input, memories_used, context)
        
        # 3. 把交互存入情景记忆
        if self._memory:
            await self._memory.store(
                content=f"用户: {user_input}\n回复: {response[:200]}...",
                memory_type="episodic",
                importance=0.6,
                tags={"用户交互"},
                **context,
            )
        
        # 4. 触发 ZenLoop 反思
        loop_results = []
        if self._zenloop:
            loop_results = await self._zenloop.on_interaction_complete(
                query=user_input,
                response=response,
                **context,
            )
        
        # 5. 更新修炼体系进度
        growth_info = {}
        upgrade_suggestions = []
        if self._cultivating:
            growth_info = await self._cultivating.record_interaction(
                skill_id="zenskill-main",
                success=True,
                feedback_score=0.8,  # 默认评分，实际可从用户反馈获取
                response_time_ms=0.0,  # 实际响应时间
                memory_used=len(memories_used) > 0,
            )
            
            # 检查是否有升级建议
            if growth_info.get("report_triggered"):
                proposals = await self._cultivating.diagnose_performance(
                    "zenskill-main"
                )
                upgrade_suggestions = [p.title for p in proposals[:3]]
        
        # 6. 返回完整结果
        return InteractionResult(
            response=response,
            growth_info=growth_info,
            memories_used=memories_used,
            loop_results=loop_results,
            upgrade_suggestions=upgrade_suggestions,
        )
    
    # ====================================================================
    # 辅助方法
    # ====================================================================
    
    async def _generate_response(
        self,
        user_input: str,
        memories: list[Any],
        context: dict[str, Any],
    ) -> str:
        """
        生成回复
        
        通过 LLM Provider 抽象层调用，不绑定任何特定平台：
        - 扣子平台 -> CozeLLMProvider
        - 独立部署 -> OpenAILLMProvider
        - Demo 模式 -> SimpleLLMProvider
        """
        llm = get_llm_provider()
        
        # 1. 构建系统提示词，注入记忆上下文
        system_prompt = self._build_system_prompt(memories)
        
        # 2. 构建消息历史
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_input),
        ]
        
        # 3. 调用 LLM（通过 Provider 抽象层，不绑定具体平台）
        response = await llm.chat(messages)
        
        # 4. 显示成长状态
        base_response = response.content
        
        if self._cultivating:
            manifest = self._cultivating.get_manifest("zenskill-main")
            if manifest:
                growth_note = (
                    f"\n\n✨ 我正在成长！当前境界: {manifest.current_level.name} "
                    f"(进度: {manifest.level_progress * 100:.1f}%)"
                )
                base_response += growth_note
        
        return base_response
    
    def _build_system_prompt(self, memories: list[Any]) -> str:
        """构建系统提示词，注入记忆上下文"""
        prompt_parts = [
            "你是 ZenSkill，一个会学习、会成长的智能助手。",
            "你有自己的记忆、修炼体系，每次交互都在进步。",
            "",
        ]
        
        # 加入记忆上下文
        if memories:
            prompt_parts.append("📝 从记忆中检索到以下相关内容供参考：")
            for i, mem in enumerate(memories[:3], 1):
                if hasattr(mem, 'content'):
                    prompt_parts.append(f"{i}. {mem.content[:100]}...")
            prompt_parts.append("")
        
        prompt_parts.append("请用友好、自然的语气回复用户。")
        
        return "\n".join(prompt_parts)
    
    # ====================================================================
    # 状态查询
    # ====================================================================
    
    def get_status(self) -> dict[str, Any]:
        """获取 Agent 完整状态"""
        memory_stats = self._memory.get_stats() if self._memory else {}
        zenloop_status = self._zenloop.get_status() if self._zenloop else {}
        
        # 获取技能成长状态
        skill_status = []
        if self._cultivating:
            skill_status = self._cultivating.list_skills()
        
        return {
            "initialized": self._initialized,
            "interaction_count": self._interaction_count,
            "memory": memory_stats,
            "zenloop": zenloop_status,
            "skills": skill_status,
        }
    
    def get_growth_report(self) -> str:
        """
        获取友好的成长报告
        
        Returns:
            格式化的成长报告字符串
        """
        if not self._cultivating:
            return "修炼系统未启用"
        
        report = self._cultivating.get_growth_report("zenskill-main")
        
        # 加上系统整体状态
        status = self.get_status()
        
        header = f"""
🌟 ZenSkill 成长报告 🌟
━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 总体状态
  ├── 总交互次数: {status['interaction_count']}
  └── 记忆总数: {status.get('memory', {}).get('episodic', {}).get('count', 0)} 条

🎯 修炼状态
"""
        
        return header + report
    
    # ====================================================================
    # 系统控制
    # ====================================================================
    
    async def shutdown(self) -> None:
        """关闭 Agent"""
        logger.info("SkillAgent shutting down...")

        # 记录会话结束事件
        if getattr(self, '_event_collector', None):
            try:
                from ..mirroring.models import EventType as _ET
                self._event_collector.record_session_event(
                    event_type=_ET.SESSION_END,
                    skill_id="zenskill-agent",
                    context={"interaction_count": self._interaction_count},
                )
            except Exception:
                pass
        
        if self._zenloop:
            self._zenloop.stop_background()
        
        # 存入最后一条记忆
        if self._memory:
            await self._memory.store(
                content=(
                    f"ZenSkill 系统关闭，"
                    f"共完成 {self._interaction_count} 次交互"
                ),
                memory_type="episodic",
                importance=0.9,
                tags={"系统", "关闭"},
            )
        
        await registry.shutdown_all()
        
        self._initialized = False
        logger.info("SkillAgent shutdown complete")
    
    def __repr__(self) -> str:
        status = self.get_status()
        level = "未初始化"
        
        if status['skills']:
            level = status['skills'][0].get('current_level', '未知')
        
        return (
            f"SkillAgent(interactions={status['interaction_count']}, "
            f"level={level})"
        )
