"""
Skill Wrapper - 将任意技能包装成 ZenSkill 可管理的形态
零侵入式整合，不需要修改原有技能代码
"""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, Optional
from dataclasses import dataclass, field

from ..core.llm_provider import get_llm_provider
from ..systems.memory import MetaMemory
from ..systems.cultivating import CultivatingSystem
from ..systems.zenloop import ZenLoopSystem

logger = logging.getLogger(__name__)


@dataclass
class SkillExecutionContext:
    """技能执行上下文"""
    task: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    success: bool = True
    error: Optional[Exception] = None
    result: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_ms(self) -> int:
        if self.end_time is None:
            return 0
        return int((self.end_time - self.start_time) * 1000)


class SkillWrapper:
    """
    技能包装器基类
    
    为任意技能注入 ZenSkill 能力：
    - 🧠 三层记忆系统（工作记忆 → 情景记忆 → 语义记忆）
    - 🏆 五重境界修炼体系
    - 🧘 四大禅思循环（反思/整合/洞见/净化）
    """
    
    def __init__(
        self,
        skill_id: str,
        skill_name: str,
        description: str = "",
        author: str = "",
        version: str = "1.0.0",
        enable_memory: bool = True,
        enable_cultivating: bool = True,
        enable_zenloop: bool = True
    ):
        self.skill_id = skill_id
        self.skill_name = skill_name
        self.description = description
        self.author = author
        self.version = version
        
        # 初始化 ZenSkill 子系统
        self.llm = get_llm_provider()
        
        if enable_memory:
            self.memory = MetaMemory()
        else:
            self.memory = None
        
        if enable_cultivating:
            self.cultivating = CultivatingSystem()
        else:
            self.cultivating = None
        
        if enable_zenloop and enable_memory and enable_cultivating:
            self.zenloop = ZenLoopSystem()
            self.zenloop.bind_memory(self.memory)
            self.zenloop.bind_cultivating(self.cultivating)
        else:
            self.zenloop = None
        
        # 钩子注册
        self._before_hooks = []
        self._after_hooks = []
        self._error_hooks = []
        
        # 执行统计
        self._total_executions = 0
        self._success_count = 0
        self._total_duration_ms = 0
    
    def register_before_hook(self, hook: Callable):
        """注册执行前钩子"""
        self._before_hooks.append(hook)
    
    def register_after_hook(self, hook: Callable):
        """注册执行后钩子"""
        self._after_hooks.append(hook)
    
    def register_error_hook(self, hook: Callable):
        """注册错误钩子"""
        self._error_hooks.append(hook)
    
    async def execute(self, task: str, **kwargs) -> Any:
        """
        统一执行接口
        
        包装原有技能的执行逻辑，自动触发 ZenSkill 各子系统
        """
        ctx = SkillExecutionContext(task=task, metadata=kwargs)
        
        try:
            # 1. 前置钩子：检索记忆、准备上下文
            await self._run_before_hooks(ctx)
            await self._before_execute(ctx)
            
            # 2. 调用实际技能执行（子类实现）
            result = await self._execute_skill(task, **kwargs)
            
            ctx.result = result
            ctx.success = True
            
            # 3. 后置钩子：记录记忆、更新修炼、触发反思
            await self._after_execute(ctx)
            await self._run_after_hooks(ctx)
            
            return result
            
        except Exception as e:
            ctx.success = False
            ctx.error = e
            
            # 4. 错误钩子：记录失败、触发认知净化
            await self._on_error(ctx)
            await self._run_error_hooks(ctx)
            
            raise
    
    async def _execute_skill(self, task: str, **kwargs) -> Any:
        """
        实际技能执行逻辑
        
        子类必须实现此方法，调用原有技能的 execute 方法
        """
        raise NotImplementedError("子类必须实现 _execute_skill 方法")
    
    async def _before_execute(self, ctx: SkillExecutionContext):
        """执行前：从记忆系统检索相关经验"""
        if not self.memory:
            return
        try:
            memories = await self.memory.retrieve(ctx.task, top_k=3)
            if memories:
                ctx.metadata["memory_context"] = [
                    getattr(m, "content", None) or str(m) for m in memories
                ]
        except Exception:
            pass
    
    async def _after_execute(self, ctx: SkillExecutionContext):
        """执行后：记录记忆 + 更新修炼 + 触发反思"""
        ctx.end_time = time.time()
        
        # 更新统计
        self._total_executions += 1
        self._success_count += 1
        self._total_duration_ms += ctx.duration_ms
        
        # 1. 写入工作记忆（三层记忆架构：Working → Episodic → Semantic）
        if self.memory:
            memory_id = f"{self.skill_id}:{int(time.time() * 1000)}"
            await self.memory.working.add(
                memory_id=memory_id,
                content=f"任务: {ctx.task}\n结果: {str(ctx.result)}",
                metadata={
                    "skill_id": self.skill_id,
                    "task": ctx.task,
                    "duration_ms": ctx.duration_ms,
                    "success": ctx.success,
                    "timestamp": time.time(),
                    **ctx.metadata
                }
            )
        
        # 2. 异步触发反思循环（不阻塞）
        if self.zenloop:
            asyncio.create_task(
                self._safe_trigger_reflection(ctx)
            )

        # 3. 记录事件到镜像系统（采集失败不阻塞执行）
        try:
            from ..mirroring.event_collector import EventCollector
            collector = EventCollector()
            collector.record_skill_execution(
                skill_id=self.skill_id,
                task=ctx.task,
                success=ctx.success,
                duration_ms=ctx.duration_ms,
                context={"result_preview": str(ctx.result)[:200]} if ctx.result else {},
            )
        except Exception:
            pass
    
    async def _safe_trigger_reflection(self, ctx: SkillExecutionContext):
        """安全触发反思循环（捕获异常不影响主流程）"""
        if not self.zenloop:
            return
        try:
            results = await self.zenloop.on_interaction_complete(
                query=ctx.task,
                response=str(ctx.result),
                skill_id=self.skill_id,
                success=ctx.success,
                duration_ms=ctx.duration_ms,
            )
            if results:
                logger.debug(
                    f"Reflection triggered for {self.skill_id}: {len(results)} loop(s)"
                )
        except Exception:
            pass
    
    async def _on_error(self, ctx: SkillExecutionContext):
        """错误时：记录失败"""
        ctx.end_time = time.time()
        self._total_executions += 1
        
        # 记录失败记忆（也写入工作记忆）
        if self.memory:
            memory_id = f"{self.skill_id}:error:{int(time.time() * 1000)}"
            await self.memory.working.add(
                memory_id=memory_id,
                content=f"任务失败: {ctx.task}\n错误: {str(ctx.error)}",
                metadata={
                    "skill_id": self.skill_id,
                    "task": ctx.task,
                    "error": str(ctx.error),
                    "success": False,
                    "timestamp": time.time(),
                    **ctx.metadata
                }
            )

        # 记录错误事件到镜像系统
        try:
            from ..mirroring.event_collector import EventCollector
            collector = EventCollector()
            collector.record_error(
                skill_id=self.skill_id,
                error_msg=str(ctx.error) if ctx.error else "unknown",
                context={"task": ctx.task},
            )
        except Exception:
            pass
    
    async def _run_before_hooks(self, ctx: SkillExecutionContext):
        for hook in self._before_hooks:
            try:
                await hook(ctx)
            except Exception:
                pass
    
    async def _run_after_hooks(self, ctx: SkillExecutionContext):
        for hook in self._after_hooks:
            try:
                await hook(ctx)
            except Exception:
                pass
    
    async def _run_error_hooks(self, ctx: SkillExecutionContext):
        for hook in self._error_hooks:
            try:
                await hook(ctx)
            except Exception:
                pass
    
    def _assess_complexity(self, task: str) -> int:
        """评估任务复杂度（1-10）"""
        length = len(task)
        keywords = ["分析", "设计", "架构", "优化", "重构", "研究", "调研", "整合"]
        
        score = min(10, length // 50)
        for kw in keywords:
            if kw in task:
                score += 1
        
        return min(10, score)
    
    # ========== 修炼状态查询 ==========
    
    @property
    def current_level(self) -> str:
        """当前境界（简化版）"""
        if self._total_executions < 5:
            return "NOVICE"
        elif self._total_executions < 20:
            return "APPRENTICE"
        elif self._total_executions < 50:
            return "ADEPT"
        elif self._total_executions < 100:
            return "EXPERT"
        else:
            return "MASTER"
    
    @property
    def progress_percentage(self) -> float:
        """当前境界进度百分比"""
        # 各境界所需的最低执行次数
        thresholds = {
            "NOVICE": 0,       # 0-4
            "APPRENTICE": 5,   # 5-19
            "ADEPT": 20,       # 20-49
            "EXPERT": 50,      # 50-99
            "MASTER": 100      # 100+
        }
        levels = ["NOVICE", "APPRENTICE", "ADEPT", "EXPERT", "MASTER"]
        
        current = self.current_level
        current_idx = levels.index(current)
        
        if current == "MASTER":
            return 100.0
        
        next_idx = current_idx + 1
        current_threshold = thresholds[current]
        next_threshold = thresholds[levels[next_idx]]
        
        # 计算当前境界内的进度
        range_size = next_threshold - current_threshold
        if range_size == 0:
            return 100.0
        
        progress_in_level = self._total_executions - current_threshold
        progress = (progress_in_level / range_size) * 100
        return min(100, max(0, progress))
    
    @property
    def total_executions(self) -> int:
        """总执行次数"""
        return self._total_executions
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self._total_executions == 0:
            return 100.0
        return self._success_count / self._total_executions * 100
    
    @property
    def avg_duration_ms(self) -> float:
        """平均执行耗时"""
        if self._total_executions == 0:
            return 0.0
        return self._total_duration_ms / self._total_executions
    
    async def get_upgrade_proposals(self) -> list:
        """获取技能升级建议"""
        proposals = []
        
        # 基于成功率的建议
        if self.success_rate < 80:
            proposals.append({
                "title": "提升任务成功率",
                "priority": "HIGH" if self.success_rate < 70 else "MEDIUM",
                "estimated_effort": "中等",
                "description": f"当前成功率 {self.success_rate:.1f}%，建议增加错误处理和输入校验"
            })
        
        # 基于性能的建议
        if self.avg_duration_ms > 2000:
            proposals.append({
                "title": "优化执行性能",
                "priority": "HIGH" if self.avg_duration_ms > 5000 else "MEDIUM",
                "estimated_effort": "较大",
                "description": f"平均耗时 {self.avg_duration_ms:.0f}ms，建议优化算法或增加缓存"
            })
        
        # 基于执行量的建议（更合理的阈值）
        if self._total_executions >= 5:
            proposals.append({
                "title": "增加任务类型支持",
                "priority": "LOW",
                "estimated_effort": "较小",
                "description": f"已执行 {self._total_executions} 次任务，建议扩展技能的能力边界"
            })
        
        # 基于成长阶段的建议
        if self.current_level == "NOVICE":
            proposals.append({
                "title": "积累实战经验",
                "priority": "MEDIUM",
                "estimated_effort": "持续",
                "description": "当前处于新手阶段，建议多执行不同类型的任务以快速成长"
            })
        
        if self.current_level == "APPRENTICE" and self.progress_percentage > 50:
            proposals.append({
                "title": "准备晋升到熟练阶段",
                "priority": "LOW",
                "estimated_effort": "中等",
                "description": "即将从学徒晋升为熟手，建议开始总结经验模式"
            })
        
        return proposals
    
    def get_status_summary(self) -> str:
        """获取技能状态摘要"""
        return f"""
🏆 {self.skill_name} 成长状态
────────────────────────────────
境界: {self.current_level}
进度: {self.progress_percentage:.1f}%
执行: {self.total_executions} 次
成功率: {self.success_rate:.1f}%
平均耗时: {self.avg_duration_ms:.0f}ms
"""


def wrap_skill(
    skill_instance: Any,
    skill_id: str,
    skill_name: str,
    description: str = "",
    execute_method_name: str = "execute",
    **kwargs
) -> SkillWrapper:
    """
    快捷函数：包装任意技能实例
    
    使用示例:
        from omniagent import OmniAgent
        agent = wrap_skill(
            skill_instance=OmniAgent(),
            skill_id="omniagent",
            skill_name="OmniAgent 全能执行代理"
        )
    """
    
    class DynamicSkillWrapper(SkillWrapper):
        async def _execute_skill(self, task: str, **skill_kwargs):
            execute_method = getattr(skill_instance, execute_method_name)
            if asyncio.iscoroutinefunction(execute_method):
                return await execute_method(task, **skill_kwargs)
            else:
                return execute_method(task, **skill_kwargs)
    
    return DynamicSkillWrapper(
        skill_id=skill_id,
        skill_name=skill_name,
        description=description,
        **kwargs
    )
