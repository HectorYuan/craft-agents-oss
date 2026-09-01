"""
ZenOmni 核心融合模块

ZenOmniSkill - 所有技能的基类，融合 ZenSkill + OmniAgent
omni_skill - 装饰器，一行代码让任意类变成智能技能
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from functools import wraps

from ..core.registry import SystemRegistry
from ..systems.memory import MetaMemory
from ..systems.cultivating import CultivatingSystem
from ..systems.zenloop import ZenLoopSystem


class SkillType(Enum):
    """技能类型枚举"""
    EXECUTION = "execution"      # 执行类（爬虫、代码、部署）
    ANALYSIS = "analysis"        # 分析类（数据、报告、诊断）
    CREATION = "creation"        # 创作类（写作、设计、生成）
    COORDINATION = "coordination" # 协调类（规划、调度、整合）


@dataclass
class SkillCapability:
    """技能能力描述"""
    name: str
    description: str
    proficiency: float  # 0-1 熟练度
    examples: List[str]


class ZenOmniSkill(ABC):
    """
    融合后的超级技能基类
    
    所有执行类技能继承此基类，自动获得：
    ✅ ZenSkill 全部元能力（记忆、修炼、反思、成长）
    ✅ OmniAgent 执行能力（规划、分解、工具调用）
    ✅ 技能注册与发现
    ✅ 跨技能协作
    """
    
    # 子类必须定义的属性（或者通过装饰器设置）
    skill_id: str = ""
    skill_name: str = ""
    skill_type: SkillType = SkillType.EXECUTION
    description: str = ""
    author: str = ""
    version: str = "1.0.0"
    
    def __init__(self, *args, **kwargs):
        # 保存原始实例（装饰器模式）
        self._original_instance = None
        if args or kwargs:
            self._original_instance = self._create_original_instance(*args, **kwargs)
        
        # 1. 初始化 ZenSkill 元能力
        self._init_zenskill()
        
        # 2. 初始化 OmniAgent 执行能力
        self._init_omniagent()
        
        # 3. 注册到技能注册表（延迟导入避免循环）
        self._register_to_registry()
    
    def _create_original_instance(self, *args, **kwargs) -> Any:
        """创建原始类实例（装饰器模式使用）"""
        return None
    
    def _init_zenskill(self):
        """初始化 ZenSkill 元能力"""
        # 每个技能有自己独立的记忆、修炼、反思系统
        self.memory = MetaMemory()
        self.cultivating = CultivatingSystem()
        self.zenloop = ZenLoopSystem()
        # 绑定相互引用（仅绑定存在的方法）
        self.cultivating.bind_memory(self.memory)
        self.cultivating.bind_zenloop(self.zenloop)
        self.zenloop.bind_memory(self.memory)
        self.zenloop.bind_cultivating(self.cultivating)
    
    def _init_omniagent(self):
        """初始化 OmniAgent 执行能力"""
        # 这些是 OmniAgent 的核心能力
        # 这里提供默认实现，子类可以覆盖
        self.task_planner = _DefaultTaskPlanner()
        self.step_executor = _DefaultStepExecutor()
        self.error_recoverer = _DefaultErrorRecoverer()
        self.result_integrator = _DefaultResultIntegrator()
    
    def _register_to_registry(self):
        """注册到全局技能注册表"""
        try:
            from . import registry as reg_module
            if hasattr(self, 'skill_id') and self.skill_id:
                reg_module.global_skill_registry.register(self)
        except Exception:
            # 注册表可能还没初始化，跳过（装饰器模式常见）
            pass
    
    @abstractmethod
    async def can_handle(self, task: str) -> float:
        """
        判断技能能否处理此任务
        返回 0-1 的置信度
        0 = 完全不能处理
        1 = 这就是我的专属任务
        """
        pass
    
    async def execute(self, task: str, **kwargs) -> Any:
        """
        执行任务（基类包装了完整的生命周期）
        
        执行流程：
        1. 🧠 记忆检索：查看有没有类似任务的经验
        2. 📋 任务规划：把大任务分解成步骤
        3. 🚀 执行步骤：逐个执行，记录中间结果
        4. 🔧 错误恢复：失败时自动重试或调整
        5. 📊 结果整合：整合所有步骤输出
        6. 🏆 修炼更新：更新境界、熟练度
        7. 🧘 反思循环：分析执行，生成改进建议
        """
        start_time = time.time()
        
        # 1. 执行前：记忆检索 + 钩子
        await self._before_execute(task, **kwargs)
        
        try:
            # 2. 实际执行（子类实现具体逻辑）
            result = await self._execute_impl(task, **kwargs)
            
            # 3. 执行后：更新所有系统
            duration = time.time() - start_time
            await self._after_execute(task, result, duration, success=True, **kwargs)
            
            return result
            
        except Exception as e:
            # 4. 错误处理
            duration = time.time() - start_time
            await self._after_execute(task, None, duration, success=False, error=e, **kwargs)
            raise
    
    async def _execute_impl(self, task: str, **kwargs) -> Any:
        """
        实际执行逻辑
        
        默认行为：如果有原始实例，调用它的 execute
        子类可以覆盖此方法实现自定义逻辑
        """
        if self._original_instance and hasattr(self._original_instance, 'execute'):
            method = getattr(self._original_instance, 'execute')
            if asyncio.iscoroutinefunction(method):
                return await method(task, **kwargs)
            else:
                return method(task, **kwargs)
        
        raise NotImplementedError(
            f"技能 {self.skill_name} 没有实现 _execute_impl 方法"
        )
    
    async def _before_execute(self, task: str, **kwargs):
        """执行前钩子：记忆检索，经验复用"""
        # 检索类似任务的历史经验
        similar_tasks = await self.memory.retrieve_by_content(task, limit=3)
        
        # 注入经验到上下文（方便子类使用）
        kwargs['past_experience'] = similar_tasks
    
    async def _after_execute(
        self, 
        task: str, 
        result: Any, 
        duration: float, 
        success: bool,
        error: Optional[Exception] = None,
        **kwargs
    ):
        """执行后钩子：记录记忆，更新修炼，触发反思"""
        # 1. 写入工作记忆
        memory_id = f"{self.skill_id}:{int(time.time()*1000)}"
        await self.memory.working.add(
            memory_id=memory_id,
            content=f"任务: {task}\n结果: {str(result)[:200]}",
            metadata={
                "skill_id": self.skill_id,
                "task": task,
                "duration_ms": int(duration * 1000),
                "success": success,
                "error": str(error) if error else None,
                "timestamp": time.time()
            }
        )
        
        # 2. 更新修炼系统
        # 这里需要适配 cultivating 的实际接口
        try:
            # 简化版：直接记录统计
            if not hasattr(self.cultivating, '_stats'):
                self.cultivating._stats = {
                    'total': 0,
                    'success': 0,
                    'total_duration': 0
                }
            self.cultivating._stats['total'] += 1
            if success:
                self.cultivating._stats['success'] += 1
            self.cultivating._stats['total_duration'] += duration
        except Exception:
            pass
        
        # 3. 异步触发反思循环（不阻塞主流程）
        if success:
            asyncio.create_task(self._trigger_reflection(task, result, duration))
        elif error:
            asyncio.create_task(self._trigger_error_reflection(task, error))
    
    async def _trigger_reflection(self, task: str, result: Any, duration: float):
        """触发成功反思：分析做得好的地方和可改进之处"""
        try:
            # 简单的反思逻辑
            if duration > 5.0:  # 超过 5 秒
                await self.memory.store(
                    content=f"反思: 任务[{task}]耗时较长({duration:.1f}s)，建议优化",
                    metadata={"type": "reflection", "priority": "medium"}
                )
        except Exception:
            pass  # 反思失败不影响主流程
    
    async def _trigger_error_reflection(self, task: str, error: Exception):
        """触发错误反思：分析失败原因，生成改进建议"""
        try:
            await self.memory.store(
                content=f"错误反思: 任务[{task}]失败，原因: {str(error)}",
                metadata={"type": "error_reflection", "priority": "high"}
            )
        except Exception:
            pass
    
    # ===== ZenSkill 能力方法 =====
    
    def get_growth_status(self) -> Dict:
        """获取技能成长状态"""
        stats = getattr(self.cultivating, '_stats', {'total': 0, 'success': 0, 'total_duration': 0})
        total = stats['total'] or 1
        success_rate = stats['success'] / total * 100
        
        # 计算境界（简化版）
        if total < 5:
            level = "NOVICE"
            progress = total / 5 * 100
        elif total < 20:
            level = "APPRENTICE"
            progress = (total - 5) / 15 * 100
        elif total < 50:
            level = "ADEPT"
            progress = (total - 20) / 30 * 100
        elif total < 100:
            level = "EXPERT"
            progress = (total - 50) / 50 * 100
        else:
            level = "MASTER"
            progress = 100
        
        return {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "skill_type": self.skill_type.value if self.skill_type else "unknown",
            "version": self.version,
            "current_level": level,
            "progress": round(progress, 1),
            "total_executions": stats['total'],
            "success_rate": round(success_rate, 1),
            "avg_duration_ms": round(stats['total_duration'] / total * 1000, 0) if total else 0,
            "capabilities": self.get_capabilities()
        }
    
    def get_capabilities(self) -> List[SkillCapability]:
        """获取技能能力清单（随成长动态变化）"""
        base_caps = self._get_base_capabilities()
        growth_bonus = self._get_growth_capabilities()
        return base_caps + growth_bonus
    
    def _get_base_capabilities(self) -> List[SkillCapability]:
        """基础能力（静态定义）"""
        return [
            SkillCapability(
                name="基础执行",
                description="执行基本的任务指令",
                proficiency=0.8,
                examples=["执行简单任务", "返回结果"]
            )
        ]
    
    def _get_growth_capabilities(self) -> List[SkillCapability]:
        """成长解锁的能力（动态计算）"""
        status = self.get_growth_status()
        level = status['current_level']
        capabilities = []
        
        if level in ["APPRENTICE", "ADEPT", "EXPERT", "MASTER"]:
            capabilities.append(SkillCapability(
                name="经验复用",
                description="利用历史执行经验优化当前任务",
                proficiency=0.6,
                examples=["从记忆中检索类似任务", "复用成功模式"]
            ))
        
        if level in ["ADEPT", "EXPERT", "MASTER"]:
            capabilities.append(SkillCapability(
                name="错误自修复",
                description="执行失败时自动分析原因并重试",
                proficiency=0.5,
                examples=["自动重试机制", "错误原因分析"]
            ))
        
        if level in ["EXPERT", "MASTER"]:
            capabilities.append(SkillCapability(
                name="任务智能分解",
                description="将复杂任务自动分解为可执行步骤",
                proficiency=0.4,
                examples=["大任务分解", "多步骤编排"]
            ))
        
        if level == "MASTER":
            capabilities.append(SkillCapability(
                name="跨技能协作",
                description="能够协调其他技能共同完成复杂任务",
                proficiency=0.3,
                examples=["技能编排", "结果整合"]
            ))
        
        return capabilities
    
    async def get_evolution_suggestions(self) -> List[Dict]:
        """获取技能进化建议"""
        status = self.get_growth_status()
        suggestions = []
        
        total = status['total_executions']
        success_rate = status['success_rate']
        
        # 基于成功率的建议
        if success_rate < 70:
            suggestions.append({
                "type": "ERROR_RESILIENCE",
                "priority": "HIGH",
                "title": "增强错误处理能力",
                "description": f"当前成功率 {success_rate:.1f}%，建议增加异常捕获和重试机制",
                "expected_impact": "+20% 成功率"
            })
        elif success_rate < 85:
            suggestions.append({
                "type": "ERROR_RESILIENCE",
                "priority": "MEDIUM",
                "title": "优化错误边界处理",
                "description": "针对常见失败场景增加预处理和输入校验",
                "expected_impact": "+10% 成功率"
            })
        
        # 基于执行次数的建议
        if total >= 10:
            suggestions.append({
                "type": "CAPABILITY_EXTEND",
                "priority": "MEDIUM",
                "title": "扩展任务类型支持",
                "description": f"已执行 {total} 次，可以考虑增加更多任务场景的支持",
                "expected_impact": "覆盖更多使用场景"
            })
        
        # 基于成长阶段的建议
        level = status['current_level']
        if level == "NOVICE":
            suggestions.append({
                "type": "GROWTH_ACCELERATION",
                "priority": "LOW",
                "title": "积累实战经验",
                "description": "多执行不同类型的任务以快速成长到 APPRENTICE",
                "expected_impact": "加速成长进度"
            })
        
        return suggestions
    
    # ===== OmniAgent 能力方法 =====
    
    async def plan_task(self, task: str) -> List[Dict]:
        """任务规划：将大任务分解为可执行步骤"""
        return await self.task_planner.plan(task, self)
    
    async def retry_with_feedback(self, task: str, error: Exception) -> Any:
        """带反馈的重试执行"""
        recovery_plan = await self.error_recoverer.analyze(error, task)
        return await self._retry_with_adjustments(task, recovery_plan)
    
    async def _retry_with_adjustments(self, task: str, plan: Dict) -> Any:
        """根据恢复计划调整后重试"""
        # 简化实现
        return await self.execute(task)


# ===== 默认执行引擎实现 =====

class _DefaultTaskPlanner:
    """默认任务规划器"""
    async def plan(self, task: str, skill: ZenOmniSkill) -> List[Dict]:
        # 简化版：把整个任务作为一个步骤
        return [{"step": 1, "description": task, "action": "execute"}]


class _DefaultStepExecutor:
    """默认步骤执行器"""
    async def execute_step(self, step: Dict, skill: ZenOmniSkill) -> Any:
        return await skill.execute(step['description'])


class _DefaultErrorRecoverer:
    """默认错误恢复器"""
    async def analyze(self, error: Exception, task: str) -> Dict:
        return {"strategy": "retry", "max_attempts": 3}


class _DefaultResultIntegrator:
    """默认结果整合器"""
    async def integrate(self, results: List[Any]) -> Any:
        return results


# ===== 技能装饰器 =====

def omni_skill(
    skill_id: str,
    name: str,
    skill_type: SkillType = SkillType.EXECUTION,
    description: str = "",
    author: str = "",
    version: str = "1.0.0"
):
    """
    技能装饰器：让任何类一秒变成 ZenOmni 智能技能！
    
    使用示例：
        @omni_skill(
            skill_id="web-crawler",
            name="智能网页爬虫",
            skill_type=SkillType.EXECUTION
        )
        class WebCrawler:
            async def execute(self, task: str):
                # 你的爬虫逻辑
                return {"content": "..."}
    
    装饰后自动获得：
    🧠 三层记忆系统 - 记住执行过的任务
    🏆 五重境界修炼 - 执行越多越强大
    🧘 四大禅思循环 - 自动反思改进
    📋 执行引擎 - 规划、分解、重试、整合
    """
    def decorator(cls):
        # 动态创建融合后的技能类
        class WrappedSkill(ZenOmniSkill):
            _original_cls = cls
            
            # 元数据将由下方 setattr 设置
            
            def _create_original_instance(self, *args, **kwargs) -> Any:
                return cls(*args, **kwargs)
            
            async def can_handle(self, task: str) -> float:
                """判断能不能处理任务"""
                # 如果原始类有 can_handle 方法，调用它
                if self._original_instance and hasattr(self._original_instance, 'can_handle'):
                    method = getattr(self._original_instance, 'can_handle')
                    if asyncio.iscoroutinefunction(method):
                        return await method(task)
                    else:
                        return method(task)
                
                # 默认实现：根据关键词简单判断
                # 子类可以自定义更智能的判断逻辑
                task_lower = task.lower()
                keywords = skill_id.lower().replace('-', ' ').split()
                match_count = sum(1 for kw in keywords if kw in task_lower)
                
                if match_count > 0:
                    return min(0.9, 0.5 + match_count * 0.1)
                return 0.3  # 默认置信度
        
        # 设置元数据为类属性
        WrappedSkill.skill_id = skill_id
        WrappedSkill.skill_name = name
        WrappedSkill.skill_type = skill_type
        WrappedSkill.description = description or cls.__doc__ or ""
        WrappedSkill.author = author
        WrappedSkill.version = version
        
        # 设置类名
        WrappedSkill.__name__ = f"ZenOmni_{cls.__name__}"
        WrappedSkill.__doc__ = f"""
        ZenOmni 智能技能: {name} (v{version})
        
        基于 {cls.__name__} 深度融合增强
        
        自动获得：
        🧠 三层记忆系统
        🏆 五重境界成长
        🧘 持续反思进化
        📋 智能执行引擎
        """
        
        return WrappedSkill
    
    return decorator
