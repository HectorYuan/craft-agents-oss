"""统一技能类型枚举 (Phase Z1A — 从 ZenOmni 抽取)

用法:
    from zenskill.core.skill_types import SkillType
    skill_type = SkillType.EXECUTION
"""

from enum import Enum


class SkillType(str, Enum):
    """技能类型"""
    EXECUTION = "execution"          # 执行类（代码、部署、工具调用）
    ANALYSIS = "analysis"            # 分析类（数据、报告、诊断）
    CREATION = "creation"            # 创作类（写作、设计、生成）
    COORDINATION = "coordination"    # 协调类（规划、调度、整合）
    KNOWLEDGE = "knowledge"          # 知识类（轻量级技能：书/文章）
    GENERAL = "general"              # 通用类
