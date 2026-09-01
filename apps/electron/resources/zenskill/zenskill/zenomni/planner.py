"""
执行引擎 - OmniAgent 核心能力

提供：
- 任务规划
- 步骤执行
- 错误恢复
- 结果整合
"""

import asyncio
from typing import Any, Dict, List, Optional
from .core import ZenOmniSkill


class TaskPlanner:
    """
    任务规划器
    
    将复杂任务分解为可执行的步骤
    
    功能：
    1. 任务理解与拆解
    2. 依赖关系分析
    3. 执行顺序规划
    """
    
    async def plan(
        self, 
        task: str, 
        skill: Optional[ZenOmniSkill] = None
    ) -> List[Dict]:
        """
        规划任务步骤
        
        Args:
            task: 任务描述
            skill: 执行此任务的技能（可选，用于更精准的规划
        
        Returns:
            步骤列表，每个步骤包含：
            - step: 步骤编号
            - description: 步骤描述
            - action: 要执行的动作类型
            - depends_on: 依赖的步骤编号
        """
        # 基础规划：如果技能的能力做规划
        
        # 1. 检查是不是简单任务
        if len(task) < 50 and "分析" not in task and "设计" not in task:
            return [{
                "step": 1,
                "description": task,
                "action": "execute",
                "depends_on": []
            }]
        
        # 2. 复杂任务：默认拆解
        # 这是一个基础版，实际可以结合 LLM 做智能分解
        steps = []
        
        # 分析类任务
        if "分析" in task or "研究" in task or "调查" in task:
            steps = [
                {
                    "step": 1,
                    "description": f"收集相关信息：" + task,
                    "action": "collect",
                    "depends_on": []
                },
                {
                    "step": 2,
                    "description": f"分析收集到的信息",
                    "action": "analyze",
                    "depends_on": [1]
                },
                {
                    "step": 3,
                    "description": f"整理分析结果，生成报告",
                    "action": "report",
                    "depends_on": [2]
                }
            ]
        
        # 设计类任务
        elif "设计" in task or "架构" in task:
            steps = [
                {
                    "step": 1,
                    "description": f"理解需求，明确目标",
                    "action": "understand",
                    "depends_on": []
                },
                {
                    "step": 2,
                    "description": f"制定多个备选方案",
                    "action": "design",
                    "depends_on": [1]
                },
                {
                    "step": 3,
                    "description": f"评估并优化方案",
                    "action": "evaluate",
                    "depends_on": [2]
                },
                {
                    "step": 4,
                    "description": f"输出最终设计文档",
                    "action": "document",
                    "depends_on": [3]
                }
            ]
        
        # 其他类型任务，直接执行
        if not steps:
            return [{
                "step": 1,
                "description": task,
                "action": "execute",
                "depends_on": []
            }]
        
        return steps


class StepExecutor:
    """
    步骤执行器
    
    按照规划好的步骤依次执行
    支持：
    - 按依赖检查
    - 步骤间上下文传递
    - 中间结果缓存
    """
    
    def __init__(self):
        self._step_results: Dict[int, Any] = {}
    
    async def execute_steps(
        self, 
        steps: List[Dict], skill: ZenOmniSkill
    ) -> Dict[str, Any]:
        """
        按顺序执行所有步骤
        
        Args:
            steps: 规划好的步骤列表
            skill: 执行任务的技能
        
        Returns:
            执行结果汇总
        """
        self._step_results.clear()
        
        for step in steps:
            step_num = step['step']
            description = step['description']
            
            # 检查依赖是否都完成了
            deps = step.get('depends_on', [])
            for dep in deps:
                if dep not in self._step_results:
                    return {
                        "success": False,
                        "error": f"步骤 {step_num} 依赖的步骤 {dep} 未执行",
                        "completed_steps": list(self._step_results.keys())
                    }
            
            # 执行当前步骤
            try:
                result = await self._execute_single_step(step, skill)
                self._step_results[step_num] = result
            except Exception as e:
                return {
                    "success": False,
                    "error": f"步骤 {step_num} 执行失败: {str(e)}",
                    "failed_step": step_num,
                    "completed_steps": list(self._step_results.keys()),
                    "step_results": self._step_results.copy()
                }
        
        return {
            "success": True,
            "total_steps": len(steps),
            "step_results": self._step_results.copy()
        }
    
    async def _execute_single_step(
        self, 
        step: Dict, 
        skill: ZenOmniSkill
    ) -> Any:
        """执行单个步骤"""
        description = step['description']
        action = step.get('action', 'execute')
        
        # 把 action 作为提示，让 skill 去执行具体逻辑
        # 实际实现中，这里可以根据不同 action 做不同处理
        context = {
            'action': action,
            'previous_results': {
                dep: self._step_results[dep]
                for dep in step.get('depends_on', [])
            }
        }
        
        return await skill.execute(description, context=context)


class ErrorRecoverer:
    """
    错误恢复器
    
    执行失败时分析原因，制定恢复策略
    
    支持的恢复策略：
    1. 简单重试
    2. 调整参数重试
    3. 分解为更小步骤
    4. 调用其他技能辅助
    """
    
    async def analyze(
        self, 
        error: Exception, 
        task: str,
        skill: Optional[ZenOmniSkill] = None
    ) -> Dict:
        """
        分析错误，制定恢复计划
        
        Returns:
            {
                "recoverable": bool,      # 是否可恢复
                "strategy": str,              # 恢复策略
                "suggestion": str,           # 具体建议
                "max_attempts": int,       # 最大尝试次数
                "adjustments": Dict         # 参数调整
            }
        """
        error_str = str(error).lower()
        
        # 网络错误
        if any(kw in error_str for kw in ['timeout', 'connection', 'network']):
            return {
                "recoverable": True,
                "strategy": "retry_with_backoff",
                "suggestion": "网络不稳定，建议增加超时时间后重试",
                "max_attempts": 3,
                "adjustments": {"timeout": "increase"}
            }
        
        # 资源不存在
        if any(kw in error_str for kw in ['404', 'not found', '不存在']):
            return {
                "recoverable": False,
                "strategy": "check_input",
                "suggestion": "资源不存在，请检查输入参数是否正确",
                "max_attempts": 1,
                "adjustments": {}
            }
        
        # 权限错误
        if any(kw in error_str for kw in ['403', 'forbidden', '权限', 'unauthorized']):
            return {
                "recoverable": False,
                "strategy": "check_permission",
                "suggestion": "权限不足，请检查认证信息",
                "max_attempts": 1,
                "adjustments": {}
            }
        
        # 默认：可以重试 2 次
        return {
            "recoverable": True,
            "strategy": "simple_retry",
            "suggestion": "未知错误，尝试重试",
            "max_attempts": 2,
            "adjustments": {}
        }
    
    async def execute_recovery(
        self,
        plan: Dict,
        task: str,
        skill: ZenOmniSkill,
        attempt: int = 1
    ) -> Any:
        """执行恢复计划"""
        if attempt > plan['max_attempts']:
            raise Exception("达到最大重试次数")
        
        # 等待一段时间（退避策略）
        wait_time = min(2 ** (attempt - 1)
        await asyncio.sleep(wait_time)
        
        # 执行重试
        return await skill.execute(task)


class ResultIntegrator:
    """
    结果整合器
    
    将多个步骤或多个技能的结果整合为统一格式
    """
    
    async def integrate_steps(self, step_results: Dict[int, Any]) -> Any:
        """整合多步骤执行结果"""
        if len(step_results) == 1:
            # 只有一个步骤，直接返回结果
            return list(step_results.values())[0]
        
        # 多个步骤，返回结构化结果
        return {
            "summary": f"成功执行 {len(step_results)} 个步骤",
            "step_count": len(step_results),
            "detailed_results": step_results
        }
    
    async def integrate_skills(
        self, 
        skill_results: List[Dict]
    ) -> Dict[str, Any]:
        """整合多技能协作结果"""
        successful = [r for r in skill_results if r.get('success', False)]
        failed = [r for r in skill_results if not r.get('success', False)]
        
        return {
            "success": len(successful) > 0,
            "total_skills": len(skill_results),
            "successful_skills": len(successful),
            "failed_skills": len(failed),
            "results": {
                r['skill_name']: r.get('result')
                for r in successful
            },
            "errors": {
                r['skill_name']: r.get('error')
                for r in failed
            }
        }
    
    async def format_report(self, data: Any, format_type: str = "text") -> str:
        """将结果格式化为报告"""
        if format_type == "text":
            return str(data)
        elif format_type == "markdown":
            return f"## 执行结果\n\n```\n{str(data)}\n```"
        else:
            return str(data)
