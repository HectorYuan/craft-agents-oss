"""
ZenSkill - Reflection Loop 反思循环

每次用户交互完成后执行：
- 总结这次交互的得失
- 提取用户偏好模式
- 存入记忆
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from zenskill.core.llm_provider import get_llm_provider, ChatMessage, HostedLLMRequired
from ..loop_base import (
    ZenLoopPlugin,
    LoopType,
    LoopResult,
)

logger = logging.getLogger(__name__)


REFLECTION_PROMPT = """你是一位技能系统的禅思大师，擅长从用户交互中提炼深刻洞察。

## 交互上下文

### 用户查询
{query}

### 系统回复
{response}

### 用户反馈（如果有）
{user_feedback}

### 任务类型
{task_type}

## 你的任务

请对本次交互进行深度反思，从以下维度分析：

### 1. 观察到的模式
- 用户的沟通风格是怎样的？
- 用户偏好简洁还是详细的回答？
- 用户是否特别关注某些方面（代码质量、解释深度、架构设计等）？

### 2. 本次回复的优点
- 哪些地方做得好？
- 哪些内容对用户真正有价值？

### 3. 可以改进的地方
- 有哪些可以提升的空间？
- 下次遇到类似问题应该如何优化？

### 4. 可执行的行动建议
- 针对本次交互，有什么具体的改进建议？

请用结构化 Markdown 输出，使用如下格式：

## 🔍 观察到的模式
- 模式 1
- 模式 2

## ✅ 本次优点
- 优点 1
- 优点 2

## 💡 改进建议
- 建议 1
- 建议 2

## 🎯 行动建议
- 建议 1
- 建议 2
"""


class ReflectionLoop(ZenLoopPlugin):
    """
    反思循环 - 每次交互后即时反思

    人类类比：做完一件事后，在心里复盘一下刚才做得好不好
    """

    @property
    def loop_type(self) -> LoopType:
        return LoopType.REFLECTION

    @property
    def trigger_condition(self) -> str:
        return "每次用户交互完成后自动触发"

    async def should_trigger(self, context: dict[str, Any]) -> bool:
        """
        判断是否应该触发反思

        默认每次都触发，除非明确设置 skip_reflection = True
        """
        if context.get("skip_reflection", False):
            return False

        # 必须有 query 和 response 才能反思
        if "query" not in context or "response" not in context:
            return False

        return True

    async def execute(
        self,
        context: dict[str, Any],
        memory_system: Optional[Any] = None,
    ) -> LoopResult:
        """
        执行反思逻辑（LLM 驱动版）

        Args:
            context: 交互上下文，包含 query, response, user_feedback 等
            memory_system: 记忆系统引用

        Returns:
            反思结果
        """
        import time
        start_time = time.time()

        query = context.get("query", "")
        response = context.get("response", "")
        user_feedback = context.get("feedback", "")
        task_type = context.get("task_type", "general")

        # 1. 使用 LLM 生成深度反思
        llm = get_llm_provider()

        # 用于存储宿主任务信息（如果抛出 HostedLLMRequired）
        hosted_task = None

        try:
            # 构建对话消息
            system_msg = ChatMessage(
                role="system",
                content="你是一位技能系统的禅思大师，善于从用户交互中提炼深刻洞察，帮助系统持续进化。",
            )

            user_msg = ChatMessage(
                role="user",
                content=REFLECTION_PROMPT.format(
                    query=query,
                    response=response,
                    user_feedback=user_feedback or "（无）",
                    task_type=task_type,
                ),
            )

            # 调用 LLM
            llm_result = await llm.chat([system_msg, user_msg], temperature=0.7)
            reflection_content = llm_result.content
            logger.debug(f"LLM reflection generated, length: {len(reflection_content)}")

        except HostedLLMRequired as e:
            # 宿主环境：需要宿主框架执行 LLM 任务
            # 不降级到规则引擎，而是在结果中标记需要宿主执行
            logger.info(f"Hosted LLM required: {e.message}")
            hosted_task = e.task
            # 返回特殊标记的内容，提示调用方需要宿主执行
            reflection_content = f"[HOSTED_LLM_TASK] 需要宿主框架执行 LLM 反思任务\n\n任务详情: {e.message}"

        except Exception as e:
            # LLM 调用失败，降级到规则引擎
            logger.warning(f"LLM reflection failed, falling back to rule-based: {e}")
            reflection_content = self._generate_rule_based_reflection(query, response, user_feedback)

        # 2. 从 LLM 输出中解析结构化信息
        extracted_patterns = self._parse_patterns_from_llm(reflection_content, query, response)
        action_items = self._parse_actions_from_llm(reflection_content)

        # 3. 如果有记忆系统，把反思存入记忆
        memory_updates = []
        if memory_system:
            # 存入情景记忆（完整的反思内容摘要）
            memory_id = await memory_system.store(
                content=f"反思记录: 用户问了'{query[:50]}...'",
                memory_type="episodic",
                importance=0.6,
                tags={"反思", "交互记录", task_type},
                context_type=task_type,
            )
            memory_updates.append({"type": "episodic", "id": memory_id})

            # 提取用户偏好存入语义记忆
            for pattern in extracted_patterns:
                if any(keyword in pattern for keyword in ["偏好", "喜欢", "希望", "倾向于", "更想要"]):
                    pref_id = await memory_system.store(
                        content=pattern,
                        memory_type="semantic",
                        subject="用户",
                        predicate="偏好",
                        object=pattern,
                        importance=0.8,
                    )
                    memory_updates.append({"type": "semantic", "id": pref_id})

        duration = (time.time() - start_time) * 1000

        # 构建 metadata
        metadata = {}
        if hosted_task:
            metadata["hosted_task"] = hosted_task
            metadata["requires_hosted_llm"] = True
            logger.info(f"Hosted LLM task ready - task_id: {hosted_task.get('task_id')}")

        logger.debug(
            f"ReflectionLoop completed: {len(extracted_patterns)} patterns, "
            f"{len(memory_updates)} memory updates, "
            f"{len(action_items)} action items"
        )

        return LoopResult(
            loop_type=LoopType.REFLECTION,
            success=True,
            summary=reflection_content,
            extracted_patterns=extracted_patterns,
            memory_updates=memory_updates,
            action_items=action_items,
            duration_ms=duration,
            metadata=metadata,
        )

    def _generate_rule_based_reflection(
        self,
        query: str,
        response: str,
        user_feedback: str,
    ) -> str:
        """
        降级方案：基于关键词生成简单反思（兼容原规则引擎）
        """
        patterns = self._extract_patterns_rule_based(query, response, user_feedback)
        actions = self._generate_action_items_rule_based(patterns, user_feedback)

        lines = ["## 🔍 观察到的模式（规则引擎降级）", ""]
        for p in patterns:
            lines.append(f"- {p}")
        lines.append("")
        lines.append("## 🎯 行动建议")
        lines.append("")
        for a in actions:
            lines.append(f"- {a}")

        return "\n".join(lines)

    def _extract_patterns_rule_based(
        self,
        query: str,
        response: str,
        user_feedback: str,
    ) -> list[str]:
        """
        从交互中提取关键模式（规则引擎降级版）
        """
        patterns = []
        query_lower = query.lower()
        response_lower = response.lower()

        # 1. 用户需求类型模式
        if "代码" in query_lower or "示例" in query_lower or "怎么写" in query_lower:
            patterns.append("用户需要代码示例")

        if "解释" in query_lower or "什么是" in query_lower or "原理" in query_lower:
            patterns.append("用户需要概念解释")

        if "架构" in query_lower or "设计" in query_lower or "方案" in query_lower:
            patterns.append("用户需要架构设计建议")

        # 2. 回复质量模式
        if len(response) < 100:
            patterns.append("回复较为简洁")
        elif len(response) > 1000:
            patterns.append("回复较为详细")

        if "示例" in response_lower or "```" in response:
            patterns.append("回复包含代码示例")

        # 3. 用户反馈模式
        if user_feedback:
            feedback_lower = user_feedback.lower()
            if "好" in feedback_lower or "棒" in feedback_lower or "谢谢" in feedback_lower:
                patterns.append("用户反馈正面，对回复满意")
            elif "不好" in feedback_lower or "不对" in feedback_lower or "错误" in feedback_lower:
                patterns.append("用户反馈负面，需要改进回复质量")

        return patterns

    def _generate_action_items_rule_based(
        self,
        patterns: list[str],
        user_feedback: str,
    ) -> list[str]:
        """生成后续行动建议（规则引擎降级版）"""
        actions = []

        if "用户需要代码示例" in patterns:
            actions.append("以后的回复中要包含更多代码示例")

        if "用户反馈负面" in " ".join(patterns):
            actions.append("需要分析用户不满意的原因，改进后续回复")

        if "回复较为简洁" in patterns and "用户需要详细解释" not in " ".join(patterns):
            actions.append("下次可以尝试提供更详细的解释和示例")

        if not actions:
            actions.append("继续保持当前的回复质量")

        return actions

    def _parse_patterns_from_llm(
        self,
        llm_output: str,
        query: str,
        response: str,
    ) -> list[str]:
        """
        从 LLM 输出中解析出模式列表
        """
        patterns = []

        # 简单解析：提取"观察到的模式"部分
        lines = llm_output.split("\n")
        in_patterns = False

        for line in lines:
            line = line.strip()

            if "观察到的模式" in line or line.startswith("## 🔍"):
                in_patterns = True
                continue

            if in_patterns and line.startswith("##"):
                in_patterns = False
                break

            if in_patterns and line.startswith("- "):
                patterns.append(line[2:])

        # 如果 LLM 输出格式不标准，至少提取一些基础模式
        if not patterns:
            patterns.extend(self._extract_patterns_rule_based(query, response, ""))

        return patterns[:5]  # 最多保留 5 个模式

    def _parse_actions_from_llm(self, llm_output: str) -> list[str]:
        """
        从 LLM 输出中解析出行动建议列表
        """
        actions = []

        lines = llm_output.split("\n")
        in_actions = False

        for line in lines:
            line = line.strip()

            if "行动建议" in line or line.startswith("## 🎯"):
                in_actions = True
                continue

            if in_actions and line.startswith("##"):
                in_actions = False
                break

            if in_actions and line.startswith("- "):
                actions.append(line[2:])

        return actions[:3]  # 最多保留 3 个行动建议
