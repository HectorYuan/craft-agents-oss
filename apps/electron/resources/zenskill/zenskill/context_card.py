"""
ZenSkill 上下文卡片

生成 Claude 可读的上下文摘要，让 Claude 在对话中主动感知和调用 ZenSkill。
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════
# Layer 1: UserPromptSubmit — 每次对话前注入上下文
# ═══════════════════════════════════════════════════════════════

def generate_context_card() -> Optional[str]:
    """生成 ZenSkill 上下文卡片 — 7X3: 拆分为 [Status] + [Dialogue] 双块"""
    now = time.time()

    # 预加载数据
    state = {}
    session_file = Path.home() / ".zenskill" / "session" / "current.json"
    if session_file.exists():
        try:
            state = json.loads(session_file.read_text())
        except Exception:
            pass

    pipeline_data = {}
    pipeline_file = Path.home() / ".zenskill" / "mirroring" / "pipeline.json"
    if pipeline_file.exists():
        try:
            d = json.loads(pipeline_file.read_text())
            if now - d.get("timestamp", 0) < 600:
                pipeline_data = d
        except Exception:
            pass

    patterns_data = {}
    patterns_file = Path.home() / ".zenskill" / "mirroring" / "patterns.json"
    if patterns_file.exists():
        try:
            patterns_data = json.loads(patterns_file.read_text())
        except Exception:
            pass

    tc = state.get("tool_count", 0) if state else 0
    nlp = pipeline_data.get("nlp", {})
    domains = nlp.get("domains", {})
    intents = nlp.get("intents", {})

    # ═════════════════════════════════════════════════════════
    # [ZenSkill Status] — 紧凑状态块 (Claude 快速扫读)
    # ═════════════════════════════════════════════════════════
    status_parts = []

    if tc > 0:
        elapsed = (now - state.get("started", now)) / 60
        status_parts.append(f"Session: {tc} tools in {elapsed:.0f}min")

    if domains:
        top_d = max(domains, key=domains.get)
        status_parts.append(f"Domain: {top_d} ({domains[top_d]:.0f}%)")
    if intents:
        top_i = max(intents, key=intents.get)
        status_parts.append(f"Intent: {top_i} ({intents[top_i]}x)")

    tools_data = pipeline_data.get("aggregation", {}).get("tools", {})
    if tools_data:
        top_tools = sorted(tools_data, key=tools_data.get, reverse=True)[:3]
        status_parts.append(f"Tools: {', '.join(top_tools)}")

    # 活跃目标 + 记忆 + 洞察 + 任务 (紧凑)
    goals_info = _get_goals_summary()
    if goals_info:
        status_parts.append(goals_info)
    mem_info = _get_memory_summary()
    if mem_info:
        status_parts.append(mem_info)
    insights_info = _get_insights_summary()
    if insights_info:
        status_parts.append(insights_info)
    tasks_info = _get_tasks_summary()
    if tasks_info:
        status_parts.append(tasks_info)

    # GTD Context (8.7S)
    gtd_info = _get_gtd_context()
    if gtd_info:
        status_parts.append(gtd_info)

    # 主动干预 (7Y1-7Y4: 梯度升级 + 自适应频率 + 偏好学习)
    interventions = generate_active_interventions(state, pipeline_data, patterns_data)
    if interventions:
        # 7Y4: 优先推送用户响应率最高的 ACT 类型
        preferred_type = _get_act_type_preference()
        if preferred_type:
            preferred = [i for i in interventions
                        if _classify_act_type(i.get("message", "")) == preferred_type]
            if preferred:
                interventions = preferred + [i for i in interventions if i not in preferred]

        # 7Y3: 自适应 ACT 频率
        response_rate = _get_act_response_rate()
        if _should_show_act(response_rate):
            top = interventions[0]
            skip_count = _get_unresponded_count()
            icon, emphasis = _get_act_gradient(skip_count)
            act_type = _classify_act_type(top.get("message", ""))
            _record_act_shown()
            _record_act_type_preference(act_type, False)
            status_parts.append(f"ACT: {icon} {top['message']}{emphasis}")

    # 意图 + 上次建议
    intent = _classify_session_intent(state, pipeline_data)
    if intent:
        status_parts.append(f"Intent: {intent}")
    last_imp = _get_last_improvements()
    if last_imp:
        status_parts.append(f"上次: {last_imp}")

    status_line = "[ZenSkill Status] " + " | ".join(status_parts) + " | Commands: zenskill mirror tips | zenskill skill info | zenskill collector run-all"

    # ═════════════════════════════════════════════════════════
    # [ZenSkill Dialogue] — 对话触发块 (7X1: 状态->提问)
    # ═════════════════════════════════════════════════════════
    dialogue = _to_dialogue_trigger(state, pipeline_data, domains, tc)

    return status_line + "\n" + dialogue


# ═══════════════════════════════════════════════════════════════
# 7X1: 对话式触发 — 将数据转为自然语言提问
# ═══════════════════════════════════════════════════════════════
def _to_dialogue_trigger(state: dict, pipeline_data: dict, domains: dict, tc: int) -> str:
    """7X1+7X2+7X4: 状态->对话触发, 含多轮上下文感知。"""
    triggers = []
    trigger_types = {}

    # 7X4: 读取上次对话历史
    last_dialogue = _get_dialogue_history()

    # 检测弱领域
    if domains:
        weak = [(d, s) for d, s in domains.items() if s < 30]
        if weak:
            w_domain, w_score = min(weak, key=lambda x: x[1])
            if last_dialogue and last_dialogue.get("topic") == w_domain:
                triggers.append(f"上次提到过 {w_domain}({w_score:.0f}%), 这次要试试设定目标吗?")
            else:
                triggers.append(f"你 {w_domain} 领域较弱({w_score:.0f}%), 要帮你设定提升目标吗?")
            trigger_types[triggers[-1]] = "goal"

    # 检测疲劳
    elapsed = (state.get("started", 0) and (time.time() - state["started"]) / 60) or 0
    if elapsed > 90:
        triggers.append(f"已连续工作 {elapsed:.0f} 分钟, 要休息一下吗?")
        trigger_types[triggers[-1]] = "health"
    elif elapsed > 45 and tc > 20:
        triggers.append(f"高强度工作 {elapsed:.0f} 分钟了, 建议 commit 后休息")
        trigger_types[triggers[-1]] = "health"

    # 检测工具使用偏差
    recent = state.get("recent_tools", [])
    if len(recent) >= 5:
        explore_count = sum(1 for t in recent[-5:] if t in ("Read", "Bash", "Glob", "Grep"))
        if explore_count >= 4:
            triggers.append("你最近主要在探索代码, 需要开始编写/修改吗?")
            trigger_types[triggers[-1]] = "workflow"

    # 检测里程碑
    if tc > 0 and tc % 50 < 5 and tc >= 50:
        triggers.append(f"已完成 {tc} 次操作, 要帮你做成长总结吗?")
        trigger_types[triggers[-1]] = "milestone"

    # 7X4: 避免重复上周期的建议
    if last_dialogue and not last_dialogue.get("responded", True):
        last_topic = last_dialogue.get("topic", "")
        triggers = [t for t in triggers if last_topic not in t]

    if triggers:
        chosen = triggers[0]
        _save_dialogue_history(
            topic=trigger_types.get(chosen, "general"),
            trigger=chosen,
        )
        return f"[ZenSkill Dialogue]\nZS: {chosen}\n(Claude 应在回复中自然回应此问题)"
    else:
        return f"[ZenSkill Dialogue]\nZS: 一切正常。需要帮助吗?"




# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
# 7Y1-7Y4: 梯度升级 + 自适应ACT + 偏好学习 + 多轮上下文
# ═══════════════════════════════════════════════════════════════

def _get_unresponded_count() -> int:
    """7Y1: 读取连续未响应 ACT 的次数"""
    try:
        f = Path.home() / ".zenskill" / "session" / "unresponded.json"
        if f.exists():
            return json.loads(f.read_text()).get("act_skipped", 0)
    except Exception:
        pass
    return 0


def _get_act_gradient(skip_count: int) -> tuple:
    """7Y2: 四级梯度升级 -> (icon, emphasis)"""
    if skip_count <= 2:
        return "ℹ️", ""
    elif skip_count <= 4:
        return "💡", f" (第{skip_count}次)"
    elif skip_count <= 6:
        return "⚠️", " ⚠️"
    else:
        return "🚨", f" 🚨已{skip_count}次!"


def _reset_unresponded() -> None:
    """7Y1: ACT 被响应时重置计数"""
    try:
        f = Path.home() / ".zenskill" / "session" / "unresponded.json"
        f.write_text(json.dumps({"act_skipped": 0}))
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# 7X4: 多轮上下文 — 对话历史追踪
# ═══════════════════════════════════════════════════════════════

def _get_dialogue_history() -> Optional[Dict]:
    """7X4: 读取上次对话历史 (30分钟内有效)"""
    try:
        f = Path.home() / ".zenskill" / "session" / "dialogue_history.json"
        if f.exists():
            data = json.loads(f.read_text())
            if time.time() - data.get("timestamp", 0) < 1800:
                return data
    except Exception:
        pass
    return None


def _save_dialogue_history(topic: str, trigger: str) -> None:
    """7X4: 保存本次对话主题"""
    try:
        f = Path.home() / ".zenskill" / "session" / "dialogue_history.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({
            "topic": topic, "trigger": trigger[:100],
            "responded": False, "timestamp": time.time(),
        }, ensure_ascii=False))
    except Exception:
        pass


def _mark_dialogue_responded() -> None:
    """7X4: 标记对话已被响应"""
    try:
        f = Path.home() / ".zenskill" / "session" / "dialogue_history.json"
        if f.exists():
            data = json.loads(f.read_text())
            data["responded"] = True
            f.write_text(json.dumps(data, ensure_ascii=False))
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# 7Y3: 自适应 ACT 频率 — 响应率调控
# ═══════════════════════════════════════════════════════════════

def _get_act_response_rate() -> float:
    """7Y3: 计算 ACT 响应率"""
    try:
        f = Path.home() / ".zenskill" / "session" / "act_response.json"
        if f.exists():
            data = json.loads(f.read_text())
            total = data.get("total_acts", 0)
            responded = data.get("responded_acts", 0)
            return responded / max(total, 1)
    except Exception:
        pass
    return 0.5


def _should_show_act(response_rate: float) -> bool:
    """7Y3: 根据响应率决定 ACT 频率"""
    import random
    if response_rate > 0.8:
        return True
    elif response_rate > 0.4:
        return random.random() < 0.6
    else:
        try:
            f = Path.home() / ".zenskill" / "session" / "unresponded.json"
            if f.exists():
                skipped = json.loads(f.read_text()).get("act_skipped", 0)
                return skipped >= 3
        except Exception:
            pass
        return True


def _record_act_shown() -> None:
    """7Y3: 记录 ACT 已展示"""
    try:
        f = Path.home() / ".zenskill" / "session" / "act_response.json"
        data = {}
        if f.exists():
            data = json.loads(f.read_text())
        data["total_acts"] = data.get("total_acts", 0) + 1
        data["last_shown"] = time.time()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data, ensure_ascii=False))
    except Exception:
        pass


def _record_act_responded() -> None:
    """7Y3: 记录 ACT 被响应 (同时重置 7Y1 + 7X4)"""
    try:
        f = Path.home() / ".zenskill" / "session" / "act_response.json"
        data = {}
        if f.exists():
            data = json.loads(f.read_text())
        data["responded_acts"] = data.get("responded_acts", 0) + 1
        f.write_text(json.dumps(data, ensure_ascii=False))
        _reset_unresponded()
        _mark_dialogue_responded()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# 7Y4: 偏好学习 — 学习用户最常响应的 ACT 类型
# ═══════════════════════════════════════════════════════════════

def _get_act_type_preference() -> str:
    """7Y4: 返回用户响应率最高的 ACT 类型"""
    try:
        f = Path.home() / ".zenskill" / "session" / "act_preferences.json"
        if f.exists():
            prefs = json.loads(f.read_text())
            best_type, best_rate = "", 0
            for act_type, stats in prefs.items():
                shown = stats.get("shown", 0)
                responded = stats.get("responded", 0)
                rate = responded / max(shown, 1)
                if rate > best_rate:
                    best_rate = rate
                    best_type = act_type
            return best_type if best_rate > 0 else ""
    except Exception:
        pass
    return ""


def _record_act_type_preference(act_type: str, responded: bool) -> None:
    """7Y4: 记录某类型 ACT 的展示/响应"""
    try:
        f = Path.home() / ".zenskill" / "session" / "act_preferences.json"
        prefs = {}
        if f.exists():
            prefs = json.loads(f.read_text())
        if act_type not in prefs:
            prefs[act_type] = {"shown": 0, "responded": 0}
        prefs[act_type]["shown"] += 1
        if responded:
            prefs[act_type]["responded"] += 1
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(prefs, ensure_ascii=False))
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# ACT 类型分类
# ═══════════════════════════════════════════════════════════════

def _classify_act_type(message: str) -> str:
    """7Y4: 分类 ACT 类型"""
    for kw, tp in [("休息", "health"), ("疲劳", "health"), ("番茄钟", "health"),
                    ("目标", "goal"), ("提升", "goal"), ("较弱", "goal"),
                    ("洞察", "insight"), ("瓶颈", "insight"), ("趋势", "insight"),
                    ("操作", "milestone"), ("里程碑", "milestone"),
                    ("建议", "workflow"), ("探索", "workflow"), ("修改", "workflow")]:
        if kw in message:
            return tp
    return "general"


def _get_goals_summary() -> str:
    """读取活跃目标摘要"""
    try:
        from zenskill.systems.active.goal_engine import ActiveGoalEngine
        engine = ActiveGoalEngine()
        goals = engine.get_active_goals()
        if goals:
            parts = []
            for g in goals[:2]:
                progress = engine.get_goal_progress(g)  # g 是 GrowthGoal 对象
                pct = progress.progress_pct if progress else 0
                dim_name = engine.DIMENSION_NAMES.get(g.dimension, g.dimension)
                parts.append(f"{dim_name}: {pct:.0f}%")
            return f"🎯 {' | '.join(parts)}"
    except Exception:
        pass
    return ""


def _get_memory_summary() -> str:
    """读取记忆统计摘要 (从 state episodes)"""
    try:
        from zenskill.core.paths import SkillStateManager
        mgr = SkillStateManager("zenskill-core")
        state = mgr.load()
        episodes = state.get("episodes", [])
        if episodes:
            hook_eps = sum(1 for e in episodes if "hook" in str(e.get("tags", "")))
            return f"🧠 记忆: {len(episodes)}条 (Hook: {hook_eps})"
    except Exception:
        pass
    return ""


def _get_insights_summary() -> str:
    """7F: 读取未读洞察推送 — 从 ProactiveInsightEngine"""
    try:
        from zenskill.systems.active.proactive_insight import ProactiveInsightEngine
        engine = ProactiveInsightEngine()
        unread = engine.get_unread_insights()
        if unread:
            # 优先推送 high/critical 级别
            high = [i for i in unread if i.level in ("high", "critical")]
            target = high[0] if high else unread[0]
            icon = {"milestone": "🏆", "celebration": "🎊", "warning": "⚠️", "bottleneck": "🔍"}.get(target.type, "💡")
            return f"{icon} {target.title}"
    except Exception:
        pass
    return ""


def _get_tasks_summary() -> str:
    """7G: 读取为活跃目标生成的推荐任务摘要"""
    try:
        from zenskill.task_generator import TaskGenerator
        from zenskill.systems.active.goal_engine import ActiveGoalEngine
        engine = ActiveGoalEngine()
        active = engine.get_active_goals()
        if not active:
            return ""
        gen = TaskGenerator()
        all_tasks = []
        for goal in active[:1]:  # 只取最高优先级目标的任务
            cached = gen.get_cached_tasks(goal.goal_id)
            if cached:
                all_tasks = cached
                break
        if not all_tasks:
            all_tasks = gen.generate_for_goal(active[0])
        if all_tasks:
            titles = [t["title"][:12] for t in all_tasks[:2]]
            return f"📋 {' | '.join(titles)}"
    except Exception:
        pass
    return ""


def _classify_session_intent(state: dict, pipeline_data: dict) -> str:
    """L1: 基于最近工具链 + NLP 意图分类会话主题"""
    recent = state.get("recent_tools", []) if state else []
    intents = pipeline_data.get("nlp", {}).get("intents", {}) if pipeline_data else {}
    tc = state.get("tool_count", 0) if state else 0

    # 工具比例分析
    edit_pct = sum(1 for t in recent if t in ("Edit", "Write")) / max(len(recent), 1)
    read_pct = sum(1 for t in recent if t == "Read") / max(len(recent), 1)
    bash_pct = sum(1 for t in recent if t == "Bash") / max(len(recent), 1)

    if tc <= 3:
        return "session_start"
    if edit_pct > 0.4:
        return "build_session"
    if read_pct > 0.6:
        return "review_session"
    if bash_pct > 0.4:
        return "debug_session"
    if intents.get("debug", 0) > intents.get("build", 0):
        return "debug_session"
    return "mixed_session"


def _get_last_improvements() -> str:
    """L5: 读取上次会话的改进建议"""
    try:
        from .zen_reflection import ZenReflectionEngine
        engine = ZenReflectionEngine()
        imps = engine.get_last_improvements(unimplemented_only=True)
        if imps:
            # 取最高优先级的一条
            high = [i for i in imps if i.get("priority") == "high"]
            target = high[0] if high else imps[0]
            return f"{target['area']}: {target['suggestion'][:60]}"
    except Exception:
        pass
    return ""


def _get_daily_plan(pipeline_data: dict, patterns_data: dict) -> str:
    """7L: 基于当前状态生成每日计划建议"""
    tips = []

    # 弱领域练习建议
    domains = pipeline_data.get("nlp", {}).get("domains", {}) if pipeline_data else {}
    weak = [d for d, s in domains.items() if s < 20]
    if weak:
        tips.append(f"练习弱领域: {', '.join(weak[:2])}")

    # 活跃时段优化
    peak = patterns_data.get("peak_hours", []) if patterns_data else []
    if peak:
        import time
        current_hour = time.localtime().tm_hour
        if current_hour in peak:
            tips.append("当前是你的高效时段，建议处理复杂任务")
        elif current_hour not in peak and peak:
            tips.append(f"非常规时段，适合轻度任务 (高峰: {peak[0]}:00)")

    # 基于主导工具的建议
    tools = patterns_data.get("dominant_tools", []) if patterns_data else []
    if "explore" in tools[:2]:
        tips.append("今日建议: 减少探索，增加实操 (Edit/Write)")
    elif "edit" in [t.lower() for t in tools[:2]]:
        tips.append("今日建议: 编辑较多，记得中间运行测试验证")

    if tips:
        return f"Plan: {' | '.join(tips)}"
    return ""


# ═══════════════════════════════════════════════════════════════
# Stage D: 主动干预规则
# ═══════════════════════════════════════════════════════════════

INTERVENTION_RULES = [
    {
        "id": "session-milestone",
        "condition": lambda ctx: ctx.get("tool_count", 0) % 50 == 0 and ctx["tool_count"] > 0,
        "action": "zenskill collector run-all",
        "priority": "recommended",
        "message": lambda ctx: (
            f"Milestone: {ctx['tool_count']} tools in this session. "
            f"Run `zenskill collector run-all` to capture a snapshot of today's patterns."
        ),
    },
    {
        "id": "fatigue-break",
        "condition": lambda ctx: ctx.get("elapsed_min", 0) > 90 and ctx.get("tool_count", 0) > 50,
        "action": "zenskill mirror tips",
        "priority": "recommended",
        "message": lambda ctx: (
            f"Session: {ctx['elapsed_min']:.0f}min/{ctx['tool_count']} tools. "
            f"Consider `zenskill mirror tips` for a quick status check before continuing."
        ),
    },
    {
        "id": "long-no-commit",
        "condition": lambda ctx: (
            ctx.get("tool_count", 0) > 60 and
            all(t not in ctx.get("recent_tools", []) for t in ["Edit", "Write"])
        ),
        "action": "zenskill doctor",
        "priority": "suggested",
        "message": lambda ctx: (
            f"{ctx['tool_count']} tools with no Edit/Write. "
            f"`zenskill doctor` can check if everything is running smoothly."
        ),
    },
    {
        "id": "domain-imbalance",
        "condition": lambda ctx: ctx.get("_domain_imbalance", False),
        "action": "zenskill mirror predict",
        "priority": "suggested",
        "message": lambda ctx: (
            "Your skill domains are unbalanced — "
            "`zenskill mirror predict` can show patterns and suggest goals."
        ),
    },
    {
        "id": "fresh-pipeline",
        "condition": lambda ctx: ctx.get("_pipeline_fresh", False),
        "action": "zenskill mirror profile",
        "priority": "info",
        "message": lambda ctx: (
            "Fresh pipeline data available. "
            "`zenskill mirror profile` shows your updated user portrait."
        ),
    },
    {
        "id": "session-start",
        "condition": lambda ctx: ctx.get("tool_count", 0) <= 3,
        "action": "zenskill skill info",
        "priority": "info",
        "message": lambda ctx: (
            "New session started. `zenskill skill info` shows your current skill overview."
        ),
    },
]


def generate_active_interventions(state: dict, pipeline_data: dict,
                                   patterns_data: dict) -> List[dict]:
    """生成主动干预建议列表（按优先级排序）"""
    interventions = []

    ctx = {
        "tool_count": state.get("tool_count", 0),
        "elapsed_min": (time.time() - state.get("started", time.time())) / 60 if state else 0,
        "recent_tools": state.get("recent_tools", []),
        "_pipeline_fresh": bool(pipeline_data),
    }

    # 领域不平衡检测
    domains = pipeline_data.get("nlp", {}).get("domains", {}) if pipeline_data else {}
    if domains:
        sorted_d = sorted(domains.items(), key=lambda x: x[1], reverse=True)
        if len(sorted_d) >= 2 and sorted_d[0][1] > 40 and sorted_d[1][1] < 20:
            ctx["_domain_imbalance"] = True

    for rule in INTERVENTION_RULES:
        try:
            if rule["condition"](ctx):
                interventions.append({
                    "id": rule["id"],
                    "action": rule["action"],
                    "priority": rule["priority"],
                    "message": rule["message"](ctx),
                })
        except Exception:
            pass

    # 去重（同一 action 只保留最高优先级）并按优先级排序
    seen = set()
    unique = []
    priority_order = {"recommended": 0, "suggested": 1, "info": 2}
    for item in sorted(interventions, key=lambda x: priority_order.get(x["priority"], 9)):
        if item["action"] not in seen:
            seen.add(item["action"])
            unique.append(item)

    return unique[:3]


def _get_context_actions(state: dict, pipeline_data: dict, patterns_data: dict) -> List[str]:
    """7W: 基于上下文生成个性化行动建议"""
    actions = []
    tc = state.get("tool_count", 0) if state else 0

    # 长时间无 Edit → 建议收集数据
    if tc > 30:
        actions.append("zenskill collector run-all (采集今日数据)")

    # 有 pipeline 数据 → 建议查看画像
    if pipeline_data and pipeline_data.get("nlp"):
        actions.append("zenskill mirror profile (查看画像)")

    # 有 patterns → 建议查看工作流
    if patterns_data and patterns_data.get("dominant_tools"):
        actions.append("zenskill mirror workflow (工作流分析)")

    # 多工具少 Edit → 建议 doctor
    recent = state.get("recent_tools", []) if state else []
    if len(recent) >= 5 and "Edit" not in recent and "Write" not in recent:
        actions.append("zenskill doctor (系统诊断)")

    return actions


def _check_ecosystem_health(pipeline_data: dict) -> Optional[str]:
    """8J: 检查技能生态健康度"""
    if not pipeline_data:
        return None

    nlp = pipeline_data.get("nlp", {})
    domains = nlp.get("domains", {})

    if not domains:
        return None

    # 单点依赖检测: 如果某个领域 > 40% 且其他都 < 15%
    sorted_d = sorted(domains.items(), key=lambda x: x[1], reverse=True)
    if len(sorted_d) >= 2:
        top_score = sorted_d[0][1]
        second_score = sorted_d[1][1]
        if top_score > 40 and second_score < 20:
            weak_domains = [d for d, s in sorted_d[1:] if s < 15]
            if weak_domains:
                return f"⚠️ 技能集中度偏高 ({sorted_d[0][0]}={top_score:.0f}%), 弱领域: {', '.join(weak_domains)}"

    return None


# ═══════════════════════════════════════════════════════════════
# Layer 2: PostToolUse — 阈值触发智能提醒
# ═══════════════════════════════════════════════════════════════

def generate_smart_alert(tool_name: str = "") -> Optional[str]:
    """每次工具调用后，检查是否需要提醒 Claude

    返回 Claude 可以直接理解和执行的自然语言指令。
    """
    now = time.time()

    # 1. 检查是否有新鲜洞察
    pipeline_file = Path.home() / ".zenskill" / "mirroring" / "pipeline.json"
    if not pipeline_file.exists():
        return None

    try:
        pipeline = json.loads(pipeline_file.read_text())
    except Exception:
        return None

    ts = pipeline.get("timestamp", 0)
    if now - ts > 600:  # 超过 10 分钟
        return None

    insights = pipeline.get("insights", [])
    if not insights:
        return None

    # 2. 生成提醒
    tip_lines = []
    for ins in insights[:2]:
        tip_lines.append(f"  - {ins}")

    # 3. 技能缺口
    domains = pipeline.get("nlp", {}).get("domains", {})
    weak = [d for d, s in domains.items() if s < 20]
    if weak:
        domains_str = ", ".join(weak)
        tip_lines.append(f"  - Weaker domains: {domains_str} — consider adding related tasks")

    if not tip_lines:
        return None

    action = f"ZenSkill has insights:\n" + "\n".join(tip_lines)
    action += "\n  Run 'zenskill mirror tips' for detailed suggestions."
    return action


# ═══════════════════════════════════════════════════════════════
# Layer 3: Stop — 会话摘要
# ═══════════════════════════════════════════════════════════════

def generate_session_briefing(output_format: str = "markdown") -> str:
    """会话结束摘要 — 包含工作流回顾 + PDCA 建议 (7H)"""
    now = time.time()
    briefing: Dict[str, Any] = {"timestamp": now}

    # 会话统计
    state = {}
    session_file = Path.home() / ".zenskill" / "session" / "current.json"
    if session_file.exists():
        try:
            state = json.loads(session_file.read_text())
        except Exception:
            pass

    tc = state.get("tool_count", 0)
    elapsed = (now - state.get("started", now)) / 60 if state else 0

    # 感知评估
    perception_summary = ""
    try:
        from .perception_engine import PerceptionEngine
        engine = PerceptionEngine()
        lt = time.localtime(now)
        ctx = {
            "tool_count": tc, "elapsed_min": elapsed,
            "recent_tools": state.get("recent_tools", []),
            "current_hour": lt.tm_hour, "current_minute": lt.tm_min,
            "last_command": "", "error_rate": 0.0,
        }
        p = engine.evaluate(ctx)
        alerts_n = len(p.get("alerts", []))
        suggestions_n = len(p.get("suggestions", []))
        if alerts_n or suggestions_n:
            perception_summary = f" | {alerts_n} 提醒, {suggestions_n} 建议"
    except Exception:
        pass

    # 保存结构化摘要
    briefing["session"] = {"tool_count": tc, "duration_min": round(elapsed, 1)}
    briefing_dir = Path.home() / ".zenskill" / "session"
    briefing_dir.mkdir(parents=True, exist_ok=True)
    briefing_file = briefing_dir / "latest_briefing.json"
    briefing_file.write_text(json.dumps(briefing, ensure_ascii=False))

    # L4+L5: 禅思反思 + 改进建议
    reflection_note = ""
    try:
        from .zen_reflection import ZenReflectionEngine
        zr = ZenReflectionEngine()
        trigger = zr.should_trigger(tc, elapsed, session_end=True)
        if trigger:
            reflection = zr.generate_reflection({
                "tool_count": tc, "elapsed_min": elapsed,
                "recent_tools": state.get("recent_tools", []),
                "pipeline_insights": [], "anomalies": [],
            })
            # 生成改进建议
            imps = zr.generate_improvements({
                "tool_count": tc, "elapsed_min": elapsed,
                "anomalies": [], "skill_gaps": [],
                "recent_tools": state.get("recent_tools", []),
            })
            reflection_note = f" | 🧘 反思已保存 | {len(imps)} 条改进"
    except Exception:
        pass

        # 7H: 元反思触发 — 对比本次vs历史，发现异常模式
        try:
            from zenskill.systems.active.meta_reflection import MetaReflectionEngine
            mr = MetaReflectionEngine()
            meta_report = mr.generate_meta_report()
            if meta_report:
                reflection_note += " | 🔍 元反思已生成"
        except Exception:
            pass

        # 7F: 生成新洞察 — 基于会话数据检查是否产生新洞察
        try:
            from zenskill.systems.active.proactive_insight import ProactiveInsightEngine
            insight_engine = ProactiveInsightEngine()
            new_insights = insight_engine.check_and_generate_insights()
            if new_insights:
                reflection_note += f" | 💡 {len(new_insights)} 新洞察"
        except Exception:
            pass

    # 输出
    lines = [f"[ZenSkill Session Briefing]"]
    lines.append(f"Session: {tc} tools in {elapsed:.0f}min{perception_summary}{reflection_note}")
    lines.append("Run 'zenskill mirror tips' for growth suggestions.")
    return "\n".join(lines)


def _get_gtd_context() -> str:
    """8.7S: GTD 上下文信息注入 Context Card"""
    try:
        from zenskill.systems.gtd import InboxEngine, ActionEngine, ProjectEngine, EnergyEngine

        parts = []

        # Inbox 状态
        inbox = InboxEngine()
        inbox_count = inbox.count()
        if inbox_count > 0:
            parts.append(f"📥 Inbox: {inbox_count} 未处理")

        # Action 状态
        actions = ActionEngine()
        stats = actions.stats()
        if stats["overdue"] > 0:
            parts.append(f"📋 Action: {stats['pending']} pending, {stats['overdue']} overdue ⚠️")
        elif stats["pending"] > 0:
            parts.append(f"📋 Action: {stats['pending']} pending")

        # Project 状态
        projects = ProjectEngine()
        dash = projects.dashboard()
        if dash["stale"] > 0:
            parts.append(f"📦 Project: {dash['active']} active, {dash['stale']} stale")

        # Energy 状态
        energy = EnergyEngine()
        s = energy.status()
        if s["level"] == "critical":
            parts.append(f"⚡ Energy: {s['current_energy']}/{s['max_energy']} 🔴 需要休息")
        elif s["level"] == "low":
            parts.append(f"⚡ Energy: {s['current_energy']}/{s['max_energy']} 🟠")

        if parts:
            return "GTD: " + " | ".join(parts)
    except Exception:
        pass
    return ""
