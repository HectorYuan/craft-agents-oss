"""
MU2-D: 协商与冲突解决 (Negotiation & Conflict Resolution)

多 Agent 意见不一致时的协商机制：
1. 意见结构化呈现 — 结论+理由+证据+置信度+替代方案
2. 交叉质询 — Agent 间互相提问澄清
3. 投票机制 — 简单多数/加权投票/共识决
4. 优先级裁决 — 基于证据强度/专业相关性/历史表现
5. 人类介入 — 无法共识时升级给用户
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .protocol import (
    AgentRole, AgentMessage, MessageType, MessagePriority,
    MessageBus,
)

logger = logging.getLogger(__name__)


# ============================================================
# 协商阶段
# ============================================================

class NegotiationStage(str, Enum):
    """协商阶段"""
    PROPOSAL = "proposal"           # 提案阶段 — 各方提交意见
    CROSS_EXAMINE = "cross_examine" # 质询阶段 — 互相提问澄清
    VOTING = "voting"              # 投票阶段 — 达成共识
    ADJUDICATION = "adjudication"  # 裁决阶段 — 仲裁
    ESCALATION = "escalation"      # 升级阶段 — 人工介入
    RESOLVED = "resolved"          # 已解决
    FAILED = "failed"              # 协商失败


class VotingMethod(str, Enum):
    """投票方法"""
    SIMPLE_MAJORITY = "simple_majority"     # 简单多数
    WEIGHTED = "weighted"                   # 加权投票
    CONSENSUS = "consensus"                 # 共识决
    UNANIMOUS = "unanimous"                 # 全体一致


# ============================================================
# 协商提案
# ============================================================

@dataclass
class StructuredOpinion:
    """结构化意见 — Agent 的完整提案"""
    agent_id: str
    role: AgentRole
    conclusion: str                                      # 结论
    reasons: list[str] = field(default_factory=list)     # 理由
    evidence: list[str] = field(default_factory=list)    # 证据
    confidence: float = 0.5                              # 置信度 0-1
    alternatives: list[str] = field(default_factory=list) # 替代方案
    domain: str = ""                                     # 相关领域

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "conclusion": self.conclusion,
            "reasons": self.reasons,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "alternatives": self.alternatives,
            "domain": self.domain,
        }


@dataclass
class CrossQuestion:
    """质询 — 一个 Agent 向另一个 Agent 提问"""
    question_id: str
    from_agent: str
    to_agent: str
    question: str
    answer: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "question_id": self.question_id,
            "from": self.from_agent,
            "to": self.to_agent,
            "question": self.question,
            "answer": self.answer,
        }


@dataclass
class Vote:
    """投票记录"""
    agent_id: str
    role: AgentRole
    choice: str                    # 投票选项
    weight: float = 1.0            # 权重（基于专业相关性）
    rationale: str = ""            # 投票理由

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "choice": self.choice,
            "weight": self.weight,
            "rationale": self.rationale,
        }


@dataclass
class NegotiationResult:
    """协商结果"""
    topic: str
    stage: NegotiationStage
    proposals: list[dict] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)
    votes: list[dict] = field(default_factory=list)
    consensus_reached: bool = False
    final_decision: str = ""
    winning_proposal: str = ""
    confidence: float = 0.0
    duration_seconds: float = 0.0
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "stage": self.stage.value,
            "proposals": self.proposals,
            "questions": self.questions,
            "votes": self.votes,
            "consensus_reached": self.consensus_reached,
            "final_decision": self.final_decision,
            "winning_proposal": self.winning_proposal,
            "confidence": self.confidence,
            "duration_seconds": self.duration_seconds,
        }


# ============================================================
# 协商引擎
# ============================================================

# 角色专业领域权重（用于加权投票）
ROLE_DOMAIN_WEIGHTS: dict[str, dict[str, float]] = {
    "architect": {
        "architecture": 1.0, "design": 0.9, "security": 0.8,
        "scalability": 0.9, "technology": 0.85,
    },
    "developer": {
        "coding": 1.0, "implementation": 0.95, "debugging": 0.85,
        "performance": 0.8, "refactoring": 0.85,
    },
    "tester": {
        "testing": 1.0, "qa": 0.95, "quality": 0.9,
        "reliability": 0.85, "edge_cases": 0.9,
    },
    "writer": {
        "documentation": 1.0, "writing": 0.95, "communication": 0.85,
    },
    "analyst": {
        "analysis": 1.0, "data": 0.9, "metrics": 0.85,
        "optimization": 0.8, "insights": 0.9,
    },
    "critic": {
        "review": 1.0, "quality": 0.9, "risk": 0.85,
        "best_practices": 0.85, "improvement": 0.8,
    },
    "coordinator": {
        "coordination": 1.0, "integration": 0.85,
        "communication": 0.8, "management": 0.8,
    },
}


class NegotiationSession:
    """
    单次协商会话

    管理从提案到解决的完整协商生命周期。
    """

    def __init__(self, session_id: str, topic: str,
                 voting_method: VotingMethod = VotingMethod.WEIGHTED,
                 timeout_seconds: float = 120.0):
        self.session_id = session_id
        self.topic = topic
        self.voting_method = voting_method
        self.timeout_seconds = timeout_seconds
        self.stage: NegotiationStage = NegotiationStage.PROPOSAL
        self.proposals: dict[str, StructuredOpinion] = {}
        self.questions: list[CrossQuestion] = []
        self.votes: list[Vote] = []
        self.start_time = time.time()
        self.result: Optional[NegotiationResult] = None

    # ── 提案阶段 ──

    def submit_proposal(self, opinion: StructuredOpinion) -> None:
        """
        提交结构化意见

        Args:
            opinion: 结构化意见
        """
        self.proposals[opinion.agent_id] = opinion
        logger.info(f"📋 提案: {opinion.agent_id} → {opinion.conclusion[:50]}")

    def all_proposals_submitted(self) -> bool:
        """检查所有参与方是否都已提交提案"""
        # 至少需要 2 个不同 Agent 的提案才能开始协商
        return len(self.proposals) >= 2

    # ── 质询阶段 ──

    def ask_question(self, from_agent: str, to_agent: str, question: str) -> str:
        """
        提出质询问题

        Args:
            from_agent: 提问方
            to_agent: 被问方
            question: 问题内容

        Returns:
            问题 ID
        """
        q = CrossQuestion(
            question_id=f"q_{uuid.uuid4().hex[:8]}",
            from_agent=from_agent,
            to_agent=to_agent,
            question=question,
        )
        self.questions.append(q)
        logger.info(f"❓ 质询: {from_agent} → {to_agent}: {question[:50]}")
        return q.question_id

    def answer_question(self, question_id: str, answer: str) -> bool:
        """
        回答质询问题

        Args:
            question_id: 问题 ID
            answer: 回答内容

        Returns:
            是否找到对应问题
        """
        for q in self.questions:
            if q.question_id == question_id and not q.answer:
                q.answer = answer
                logger.info(f"💬 回答: {q.to_agent}: {answer[:50]}")
                return True
        return False

    def all_questions_answered(self) -> bool:
        """检查所有质询是否都已回答"""
        return all(q.answer for q in self.questions) if self.questions else True

    # ── 投票阶段 ──

    def cast_vote(self, agent_id: str, role: AgentRole,
                  choice: str, rationale: str = "",
                  domain: str = "") -> None:
        """
        投票

        Args:
            agent_id: 投票者 ID
            role: 投票者角色
            choice: 投票选项（通常为提案的 agent_id）
            rationale: 投票理由
            domain: 相关领域
        """
        # 计算权重
        weight = self._calculate_weight(role.value, domain)

        vote = Vote(
            agent_id=agent_id,
            role=role,
            choice=choice,
            weight=weight,
            rationale=rationale,
        )
        self.votes.append(vote)
        logger.info(f"🗳️ 投票: {agent_id} → {choice} (weight={weight:.2f})")

    def _calculate_weight(self, role: str, domain: str) -> float:
        """计算投票权重"""
        if not domain:
            return 1.0
        domain_weights = ROLE_DOMAIN_WEIGHTS.get(role, {})
        return domain_weights.get(domain, 0.5)

    def tally_votes(self) -> dict[str, float]:
        """
        统计投票结果

        Returns:
            {choice: weighted_total}
        """
        totals: dict[str, float] = {}
        for vote in self.votes:
            totals[vote.choice] = totals.get(vote.choice, 0) + vote.weight
        return totals

    def determine_winner(self) -> tuple[str, float, float]:
        """
        确定获胜提案

        Returns:
            (winning_proposal_id, votes, total_weight)
        """
        totals = self.tally_votes()
        if not totals:
            return ("", 0.0, 0.0)

        winner = max(totals, key=totals.get)
        total_weight = sum(totals.values())
        return (winner, totals[winner], total_weight)

    # ── 协商流程 ──

    async def run_negotiation(self) -> NegotiationResult:
        """
        运行完整协商流程

        按阶段推进：提案 → 质询 → 投票 → 裁决

        Returns:
            协商结果
        """
        logger.info(f"🔄 开始协商: {self.topic}")

        # 阶段 1: 等待提案
        if len(self.proposals) < 2:
            self.stage = NegotiationStage.FAILED
            return self._build_result("协商失败: 提案不足")

        self.stage = NegotiationStage.PROPOSAL

        # 阶段 2: 交叉质询（轮流）
        self.stage = NegotiationStage.CROSS_EXAMINE
        await self._run_cross_examination()

        # 阶段 3: 投票
        self.stage = NegotiationStage.VOTING
        if not self.votes:
            # 如果没有明确投票，按置信度自动投票
            self._auto_vote()

        winner, votes, total = self.determine_winner()
        vote_ratio = votes / total if total > 0 else 0

        if vote_ratio >= 0.6:
            self.stage = NegotiationStage.RESOLVED
            self.result = self._build_result(
                f"协商达成: {winner} 的提案被采纳",
                consensus_reached=True,
                winning_proposal=winner,
            )
        elif vote_ratio >= 0.4:
            # 轻微多数 → 裁决阶段
            self.stage = NegotiationStage.ADJUDICATION
            self.result = self._build_result(
                f"裁决: {winner} 的提案胜出",
                consensus_reached=True,
                winning_proposal=winner,
            )
        else:
            # 无法达成共识 → 升级
            self.stage = NegotiationStage.ESCALATION
            self.result = self._build_result(
                "协商未达成共识，需要人工介入",
                consensus_reached=False,
            )

        return self.result

    async def _run_cross_examination(self) -> None:
        """运行交叉质询 — 各方轮流提问"""
        agent_ids = list(self.proposals.keys())
        if len(agent_ids) < 2:
            return

        # 每个 Agent 对其他所有 Agent 各提一个问题
        for asker in agent_ids:
            for target in agent_ids:
                if asker == target:
                    continue
                proposal = self.proposals.get(target)
                if proposal:
                    q = f"关于「{proposal.conclusion}」, 请提供更多证据支持你的结论"
                    self.ask_question(asker, target, q)
                    # 模拟回答（在真实场景中由 Agent 处理）
                    self.answer_question(
                        self.questions[-1].question_id,
                        f"基于 {len(proposal.evidence)} 项证据: "
                        f"{'; '.join(proposal.evidence[:3])}"
                        if proposal.evidence else "证据正在收集中"
                    )

    def _auto_vote(self) -> None:
        """自动投票 — 基于置信度和证据强度"""
        for agent_id, proposal in self.proposals.items():
            # 对自己投赞成票
            self.cast_vote(agent_id, proposal.role, agent_id,
                          rationale=proposal.conclusion,
                          domain=proposal.domain)
            # 对其他提案投票（倾向于支持置信度高的）
            for other_id, other_proposal in self.proposals.items():
                if other_id == agent_id:
                    continue
                if other_proposal.confidence > 0.7:
                    self.cast_vote(
                        agent_id, proposal.role, other_id,
                        rationale=f"认可其高置信度",
                        domain=other_proposal.domain,
                    )

    def _build_result(self, summary: str,
                      consensus_reached: bool = False,
                      winning_proposal: str = "") -> NegotiationResult:
        """构建协商结果"""
        winner = winning_proposal
        if winner and winner in self.proposals:
            confidence = self.proposals[winner].confidence
        else:
            confidence = 0.0

        return NegotiationResult(
            topic=self.topic,
            stage=self.stage,
            proposals=[p.to_dict() for p in self.proposals.values()],
            questions=[q.to_dict() for q in self.questions],
            votes=[v.to_dict() for v in self.votes],
            consensus_reached=consensus_reached,
            final_decision=(
                self.proposals[winner].conclusion
                if winner in self.proposals else ""
            ),
            winning_proposal=winner,
            confidence=confidence,
            duration_seconds=time.time() - self.start_time,
            summary=summary,
        )


# ============================================================
# 协商协调器 — 自动处理 MessageBus 协商消息
# ============================================================

class NegotiationCoordinator:
    """
    协商协调器

    自动处理通过 MessageBus 发送的协商消息，
    管理多个并发的协商会话。
    """

    def __init__(self, bus: MessageBus):
        self._bus = bus
        self._sessions: dict[str, NegotiationSession] = {}
        self._default_voting = VotingMethod.WEIGHTED

    def start_negotiation(self, topic: str,
                          voting_method: Optional[VotingMethod] = None) -> NegotiationSession:
        """
        开始新的协商会话

        Args:
            topic: 协商主题
            voting_method: 投票方式

        Returns:
            协商会话
        """
        session_id = f"nego_{uuid.uuid4().hex[:8]}"
        session = NegotiationSession(
            session_id=session_id,
            topic=topic,
            voting_method=voting_method or self._default_voting,
        )
        self._sessions[session_id] = session
        logger.info(f"🆕 协商开始: [{session_id}] {topic}")
        return session

    def get_session(self, session_id: str) -> Optional[NegotiationSession]:
        return self._sessions.get(session_id)

    def list_active_sessions(self) -> list[NegotiationSession]:
        return [s for s in self._sessions.values()
                if s.stage not in (NegotiationStage.RESOLVED,
                                   NegotiationStage.FAILED)]

    def list_completed_sessions(self) -> list[NegotiationSession]:
        return [s for s in self._sessions.values()
                if s.stage in (NegotiationStage.RESOLVED,
                               NegotiationStage.FAILED)]

    async def handle_negotiation_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """
        处理协商相关的消息

        根据消息类型自动路由到对应会话
        """
        session_id = message.payload.get("session_id", "")
        session = self._sessions.get(session_id)

        if message.msg_type == MessageType.NEGOTIATION_PROPOSAL:
            return await self._handle_proposal(message, session)
        elif message.msg_type == MessageType.FEEDBACK_REQUEST:
            return self._handle_feedback(message)
        elif message.msg_type == MessageType.FEEDBACK_RESPONSE:
            pass  # 普通反馈，无需处理

        return None

    async def _handle_proposal(self, msg: AgentMessage,
                               session: NegotiationSession) -> Optional[AgentMessage]:
        """处理提案消息"""
        if not session:
            return AgentMessage.new(
                sender="coordinator",
                msg_type=MessageType.FEEDBACK_RESPONSE,
                receiver=msg.sender,
                correlation_id=msg.msg_id,
                payload={"error": "session_not_found", "session_id": msg.payload.get("session_id")},
            )

        payload = msg.payload
        opinion = StructuredOpinion(
            agent_id=msg.sender,
            role=AgentRole(payload.get("role", "developer")),
            conclusion=payload.get("conclusion", ""),
            reasons=payload.get("reasons", []),
            evidence=payload.get("evidence", []),
            confidence=payload.get("confidence", 0.5),
            alternatives=payload.get("alternatives", []),
            domain=payload.get("domain", ""),
        )
        session.submit_proposal(opinion)

        return AgentMessage.new(
            sender="coordinator",
            msg_type=MessageType.FEEDBACK_RESPONSE,
            receiver=msg.sender,
            correlation_id=msg.msg_id,
            payload={
                "status": "proposal_accepted",
                "session_id": session_id,
                "proposals_count": len(session.proposals),
            },
        )

    def _handle_feedback(self, msg: AgentMessage) -> Optional[AgentMessage]:
        """处理协商状态查询"""
        return AgentMessage.new(
            sender="coordinator",
            msg_type=MessageType.FEEDBACK_RESPONSE,
            receiver=msg.sender,
            correlation_id=msg.msg_id,
            payload={
                "active_sessions": len(self.list_active_sessions()),
                "completed_sessions": len(self.list_completed_sessions()),
                "sessions": [
                    {
                        "id": s.session_id,
                        "topic": s.topic,
                        "stage": s.stage.value,
                        "participants": list(s.proposals.keys()),
                    }
                    for s in self._sessions.values()
                ],
            },
        )

    def run_session(self, session: NegotiationSession) -> NegotiationResult:
        """
        运行协商会话并返回结果

        能自动适应同步和异步调用场景。
        如果从协程中调用，使用当前事件循环。
        如果从同步代码中调用，创建新事件循环。

        Args:
            session: 协商会话

        Returns:
            协商结果
        """
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                coro = session.run_negotiation()
                # 如果已经有提案，直接运行（同步内部已经是 async）
                if len(session.proposals) >= 2:
                    # 尝试直接在新线程中运行
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(
                            asyncio.run,
                            session.run_negotiation()
                        )
                        return future.result(timeout=session.timeout_seconds + 10)
            return asyncio.run(session.run_negotiation())
        except RuntimeError:
            return asyncio.run(session.run_negotiation())
