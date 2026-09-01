"""
全局技能注册表

功能：
- 技能注册与发现
- 任务智能路由
- 技能能力评估
- 跨技能协作编排
"""

import asyncio
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .core import ZenOmniSkill


@dataclass
class SkillRoute:
    """技能路由信息"""
    skill_id: str
    skill: ZenOmniSkill
    route_weight: float = 0.5  # 路由权重（基于熟练度动态调整）
    success_count: int = 0     # 成功执行次数
    total_count: int = 0       # 总执行次数


class GlobalSkillRegistry:
    """
    全局技能注册表
    
    技能生态的核心，提供：
    1. 技能注册与发现
    2. 任务智能路由
    3. 技能能力评估
    4. 跨技能协作编排
    """
    
    def __init__(self):
        warnings.warn(
            "GlobalSkillRegistry is deprecated and will be removed in a future release. "
            "Please migrate to SkillProfile (for skill metadata) or SkillDAO (for persistence). "
            "See zenskill.db.skill_dao for the new API.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.skills: Dict[str, ZenOmniSkill] = {}
        self.routes: Dict[str, SkillRoute] = {}
        self._initialized = False
    
    def register(self, skill: ZenOmniSkill):
        """注册技能"""
        skill_id = skill.skill_id
        if not skill_id:
            raise ValueError("技能必须有 skill_id")
        
        self.skills[skill_id] = skill
        
        # 创建路由信息
        if skill_id not in self.routes:
            self.routes[skill_id] = SkillRoute(
                skill_id=skill_id,
                skill=skill
            )
        
        self._initialized = True
    
    def unregister(self, skill_id: str):
        """注销技能"""
        if skill_id in self.skills:
            del self.skills[skill_id]
        if skill_id in self.routes:
            del self.routes[skill_id]
    
    def list_skills(self) -> List[Dict]:
        """列出所有已注册的技能及其状态"""
        return [
            {
                "skill_id": sid,
                "name": skill.skill_name,
                "type": skill.skill_type.value if skill.skill_type else "unknown",
                "version": skill.version,
                "status": skill.get_growth_status() if hasattr(skill, 'get_growth_status') else {}
            }
            for sid, skill in self.skills.items()
        ]
    
    def get_skill(self, skill_id: str) -> Optional[ZenOmniSkill]:
        """获取指定技能"""
        return self.skills.get(skill_id)
    
    async def find_best_skill(self, task: str) -> Optional[ZenOmniSkill]:
        """
        找到最适合处理此任务的技能
        
        评分规则：
        1. 技能的 can_handle 置信度（基础分）
        2. 技能的成长境界加成（境界越高权重越高）
        3. 历史成功率加成（越准权重越高）
        """
        if not self.skills:
            return None
        
        best_skill = None
        best_score = 0
        
        for skill in self.skills.values():
            # 1. 基础置信度
            confidence = await skill.can_handle(task)
            
            # 2. 境界加成（成长越高，技能越可靠）
            route = self.routes.get(skill.skill_id)
            if route:
                # 成功率加成
                if route.total_count > 0:
                    success_rate = route.success_count / route.total_count
                    confidence = confidence * (0.7 + 0.3 * success_rate)
                
                # 经验加成：执行过的任务越多，越可靠
                experience_bonus = min(0.2, route.total_count / 100)
                confidence += experience_bonus
            
            # 3. 记录最高分
            if confidence > best_score:
                best_score = confidence
                best_skill = skill
        
        # 置信度太低的话，不匹配任何技能
        if best_score < 0.2:
            return None
        
        return best_skill
    
    async def route_task(self, task: str, **kwargs) -> Dict:
        """
        智能路由任务到最合适的技能
        
        返回：
        {
            "success": bool,
            "skill_id": str,
            "skill_name": str,
            "result": Any,
            "error": Optional[str]
        }
        """
        skill = await self.find_best_skill(task)
        
        if not skill:
            return {
                "success": False,
                "error": "没有找到能处理此任务的技能",
                "available_skills": self.list_skills()
            }
        
        # 更新路由统计
        route = self.routes.get(skill.skill_id)
        if route:
            route.total_count += 1
        
        try:
            # 执行任务
            result = await skill.execute(task, **kwargs)
            
            # 成功，更新统计
            if route:
                route.success_count += 1
                # 动态调整路由权重：成功率越高，权重越高
                if route.total_count >= 5:
                    route.route_weight = route.success_count / route.total_count
            
            return {
                "success": True,
                "skill_id": skill.skill_id,
                "skill_name": skill.skill_name,
                "confidence": await skill.can_handle(task),
                "result": result
            }
            
        except Exception as e:
            return {
                "success": False,
                "skill_id": skill.skill_id,
                "skill_name": skill.skill_name,
                "error": str(e)
            }
    
    async def coordinate_skills(
        self, 
        task: str, 
        required_skill_ids: List[str] = None,
        parallel: bool = False
    ) -> Dict:
        """
        编排多个技能协作完成复杂任务
        
        Args:
            task: 总任务描述
            required_skill_ids: 指定要使用的技能 ID 列表（None 表示自动选择）
            parallel: 是否并行执行
        
        Returns:
            整合后的结果
        """
        # 1. 确定要使用的技能
        if required_skill_ids:
            skills = [
                self.skills[sid] 
                for sid in required_skill_ids 
                if sid in self.skills
            ]
        else:
            # 自动选择能处理这个任务的所有技能
            skills = []
            for skill in self.skills.values():
                confidence = await skill.can_handle(task)
                if confidence > 0.3:
                    skills.append(skill)
        
        if not skills:
            return {
                "success": False,
                "error": "没有找到可用的技能"
            }
        
        # 2. 任务分解：把大任务分配给各个技能
        subtasks = await self._decompose_task(task, skills)
        
        # 3. 执行子任务
        if parallel:
            # 并行执行
            tasks = [
                self._execute_subtask(subtask, skill)
                for subtask, skill in zip(subtasks, skills)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            # 串行执行
            results = []
            for subtask, skill in zip(subtasks, skills):
                result = await self._execute_subtask(subtask, skill)
                results.append(result)
        
        # 4. 整合结果
        return await self._integrate_results(task, skills, results)
    
    async def _decompose_task(self, task: str, skills: List[ZenOmniSkill]) -> List[str]:
        """把任务分解给各个技能"""
        # 简化版：每个技能执行整个任务
        # 实际应用中可以根据技能能力做更智能的分解
        return [task] * len(skills)
    
    async def _execute_subtask(self, subtask: str, skill: ZenOmniSkill) -> Dict:
        """执行子任务"""
        try:
            result = await skill.execute(subtask)
            return {
                "skill_id": skill.skill_id,
                "skill_name": skill.skill_name,
                "success": True,
                "result": result
            }
        except Exception as e:
            return {
                "skill_id": skill.skill_id,
                "skill_name": skill.skill_name,
                "success": False,
                "error": str(e)
            }
    
    async def _integrate_results(
        self, 
        task: str, 
        skills: List[ZenOmniSkill], 
        results: List[Dict]
    ) -> Dict:
        """整合多个技能的结果"""
        successful = [r for r in results if r.get('success', False)]
        failed = [r for r in results if not r.get('success', False)]
        
        return {
            "success": len(successful) > 0,
            "task": task,
            "skills_used": len(skills),
            "successful_count": len(successful),
            "failed_count": len(failed),
            "results_by_skill": {
                r['skill_name']: r.get('result')
                for r in successful
            },
            "errors": {
                r['skill_name']: r.get('error')
                for r in failed
            }
        }
    
    def get_skill_ranking(self) -> List[Dict]:
        """获取技能排行榜（按路由权重排序）"""
        ranked = sorted(
            self.routes.values(),
            key=lambda r: r.route_weight,
            reverse=True
        )
        
        return [
            {
                "rank": i + 1,
                "skill_id": r.skill_id,
                "skill_name": r.skill.skill_name,
                "route_weight": round(r.route_weight, 2),
                "success_rate": round(r.success_count / max(1, r.total_count), 2),
                "total_executions": r.total_count
            }
            for i, r in enumerate(ranked)
        ]
    
    async def get_all_growth_status(self) -> Dict[str, Dict]:
        """获取所有技能的成长状态"""
        return {
            sid: skill.get_growth_status()
            for sid, skill in self.skills.items()
        }


# 全局单例
global_skill_registry = GlobalSkillRegistry()
