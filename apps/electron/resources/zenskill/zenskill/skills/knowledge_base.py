"""
KnowledgeBase Skill — 知识库管理技能 (Phase Z1B: 脱离 ZenOmni)

整合知识库入库、索引、校验、恢复和飞书分享等全部规则。
已从 ZenOmniSkill 基类迁移为独立 SkillDefinition 模式。

Deprecated: 此技能为 Coze/飞书平台遗留，推荐使用 SkillDefinition + SkillDAO。
"""

from typing import Any, Dict, List

from ..core.skill_types import SkillType
from ..skill_dsl import SkillDefinition


class KnowledgeBaseSkill:
    """
    知识库管理技能 (Phase Z1B: no longer extends ZenOmniSkill)

    负责知识库的完整生命周期管理：
    - 入库：文件存储、索引更新、版本控制
    - 校验：sha256 校验和验证
    - 恢复：git + checksum 双保险恢复
    - 分享：飞书文档分享链接管理
    """

    # 技能元数据
    skill_id = "knowledge-base"
    skill_name = "知识库管理"
    skill_type = SkillType.COORDINATION
    description = "管理知识库的入库、索引、校验、恢复和飞书分享"
    author = "小书童"
    version = "1.0.0"

    # 知识库根路径
    KB_ROOT = "./knowledge"

    @classmethod
    def to_definition(cls) -> SkillDefinition:
        """转换为标准 SkillDefinition (兼容新技能体系)"""
        return SkillDefinition(
            name=cls.skill_name,
            description=cls.description,
            category="writing",
            difficulty="intermediate",
        )
    
    async def can_handle(self, task: str) -> float:
        """
        判断能否处理此任务
        
        返回 0-1 的置信度
        """
        keywords = [
            "知识库", "入库", "成果归档", "归档", 
            "校验", "checksum", "sha256", "知识索引",
            "恢复文件", "文件恢复", "知识分享", "分享链接"
        ]
        task_lower = task.lower()
        score = 0.0
        
        # 精确匹配权重更高
        if "知识库" in task:
            score += 0.4
        if "入库" in task or "归档" in task:
            score += 0.3
        if "校验" in task or "checksum" in task_lower or "sha256" in task_lower:
            score += 0.3
        if "索引" in task or "index" in task_lower:
            score += 0.2
        if "恢复" in task:
            score += 0.3
        if "分享" in task or "飞书" in task:
            score += 0.2
            
        return min(score, 1.0)
    
    async def _execute_impl(self, task: str, **kwargs) -> Dict[str, Any]:
        """
        执行知识库操作
        
        由 sub-agent 在实际执行时通过 bash 工具操作
        这里定义操作规范和流程，供执行时参考
        """
        # 根据任务类型返回对应的操作流程
        task_lower = task.lower()
        
        if "入库" in task or "归档" in task:
            return {
                "action": "ingest",
                "workflow": [
                    "1. 确认文件类型和目标目录",
                    "2. 移动/复制文件到知识库",
                    "3. 更新索引文件 (index.json)",
                    "4. 执行 git add + commit",
                    "5. 更新 checksum.json"
                ],
                "kb_root": self.KB_ROOT
            }
        elif "校验" in task or "checksum" in task_lower:
            return {
                "action": "verify",
                "workflow": [
                    "1. 读取 checksum.json",
                    "2. 计算当前文件 sha256",
                    "3. 对比校验和",
                    "4. 报告不一致文件"
                ],
                "kb_root": self.KB_ROOT
            }
        elif "恢复" in task:
            return {
                "action": "recover",
                "workflow": [
                    "1. 从 checksum.json 获取目标 sha256",
                    "2. 使用 git checkout 恢复文件",
                    "3. 重新校验 sha256"
                ],
                "kb_root": self.KB_ROOT
            }
        elif "索引" in task or "index" in task_lower:
            return {
                "action": "index",
                "workflow": [
                    "1. 扫描知识库目录结构",
                    "2. 更新 index.json 索引",
                    "3. 生成目录树"
                ],
                "kb_root": self.KB_ROOT
            }
        else:
            return {
                "action": "unknown",
                "suggestion": "请明确任务：入库、校验、恢复或索引",
                "kb_root": self.KB_ROOT
            }
    
    def _get_base_capabilities(self) -> List[SkillCapability]:
        """基础能力清单"""
        return [
            SkillCapability(
                name="知识入库",
                description="将文件安全归档到知识库，包含版本控制",
                proficiency=0.9,
                examples=["归档报告文件", "入库图片资源", "存入代码片段"]
            ),
            SkillCapability(
                name="索引管理",
                description="维护知识库的索引文件，支持快速检索",
                proficiency=0.85,
                examples=["更新索引", "查询文件位置", "生成目录结构"]
            ),
            SkillCapability(
                name="防篡改校验",
                description="通过 sha256 校验和 git 版本控制确保文件完整性",
                proficiency=0.9,
                examples=["校验文件完整性", "检测篡改", "验证入库结果"]
            ),
            SkillCapability(
                name="故障恢复",
                description="基于 git 和 checksum 的双保险恢复机制",
                proficiency=0.85,
                examples=["恢复误删文件", "回滚错误修改", "找回历史版本"]
            ),
            SkillCapability(
                name="飞书分享",
                description="生成飞书文档分享链接并记录",
                proficiency=0.7,
                examples=["分享知识条目", "生成外链", "管理分享记录"]
            ),
            SkillCapability(
                name="外部链接归档",
                description="记录外部参考资料链接及其元信息",
                proficiency=0.75,
                examples=["归档参考链接", "记录来源", "追踪外部资源"]
            )
        ]


# 导出单例供注册表使用
_knowledge_base_skill = KnowledgeBaseSkill()

__all__ = ["KnowledgeBaseSkill", "_knowledge_base_skill"]
