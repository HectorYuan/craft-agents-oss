"""
命令注册表

所有 CLI 命令的唯一真相来源。
交互模式的命令面板和命令模式的斜杠命令都从这里读取。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class CommandArg:
    """命令参数定义"""
    name: str
    type: str = "string"        # "choice" | "string" | "int" | "file"
    required: bool = False
    choices: Optional[list[str]] = None
    default: Any = None
    help: str = ""


@dataclass
class CommandEntry:
    """单个命令的完整定义"""
    namespace: str              # "growth"
    name: str                   # "trend"
    display_name: str           # "成长趋势"
    help: str                   # "显示成长趋势图"
    category: str               # "growth" | "memory" | "system" | ...
    action_type: str            # "screen" | "output" | "action"
    handler_name: str           # "cmd_growth_trend" - __main__ 中的函数名
    args: list[CommandArg] = field(default_factory=list)
    flags: list[CommandArg] = field(default_factory=list)
    target: Optional[str] = None
    icon: str = ""
    shortcut: Optional[str] = None

    @property
    def qualified_name(self) -> str:
        """如 'growth trend'"""
        if self.name:
            return f"{self.namespace} {self.name}"
        return self.namespace

    @property
    def palette_text(self) -> str:
        """命令面板中显示的文本"""
        parts = []
        if self.icon:
            parts.append(self.icon)
        parts.append(self.qualified_name)
        if self.display_name:
            parts.append(f"-- {self.display_name}")
        return " ".join(parts)

    @property
    def required_args(self) -> list[CommandArg]:
        """返回所有必需参数"""
        return [a for a in self.args if a.required]


# 命令类别定义
CATEGORIES = {
    "navigation": ("导航", "📂"),
    "growth": ("成长", "📈"),
    "skill": ("技能", "🎯"),
    "goal": ("目标", "🏆"),
    "task": ("任务", "📋"),
    "insight": ("洞察", "💡"),
    "memory": ("记忆", "🧠"),
    "reflect": ("反思", "🧘"),
    "meta": ("元认知", "🔬"),
    "graph": ("图谱", "🕸️"),
    "cross": ("跨技能", "🔗"),
    "eco": ("生态", "🌍"),
    "mirror": ("镜像", "🪞"),
    "data": ("数据", "📊"),
    "config": ("配置", "⚙️"),
    "doctor": ("诊断", "🏥"),
    "experiment": ("实验", "🧪"),
    "llm": ("LLM", "🤖"),
    "hook": ("钩子", "🪝"),
    "collector": ("采集", "📥"),
    "notify": ("通知", "🔔"),
    "session": ("会话", "📡"),
    "perceive": ("感知", "👁️"),
    "context": ("上下文", "🧭"),
    "chat": ("对话", "💬"),
    "system": ("系统", "🔧"),
    "gtd": ("GTD", "🎯"),
}


def build_command_registry() -> list[CommandEntry]:
    """构建完整的命令注册表"""
    registry: list[CommandEntry] = []

    def add(*args, **kwargs):
        registry.append(CommandEntry(*args, **kwargs))

    # ── 导航（屏幕切换） ──────────────────────────────────

    add(
        namespace="dashboard", name="", display_name="仪表盘",
        help="显示五维能力雷达、技能、洞察、目标概览",
        category="navigation", action_type="screen",
        target="dashboard", handler_name="cmd_tui",
        icon="📊", shortcut="1",
    )
    add(
        namespace="chat", name="", display_name="对话",
        help="与 ZenSkill 智能助手对话",
        category="navigation", action_type="screen",
        target="chat", handler_name="cmd_tui",
        icon="💬", shortcut="2",
    )
    add(
        namespace="growth", name="", display_name="成长中心",
        help="成长数据、目标、任务、洞察、元反思",
        category="navigation", action_type="screen",
        target="growth", handler_name="cmd_tui",
        icon="📈", shortcut="3",
    )
    add(
        namespace="mirror", name="", display_name="用户镜像",
        help="查看镜像状态、特征、隐私设置",
        category="navigation", action_type="screen",
        target="mirror", handler_name="cmd_tui",
        icon="🪞", shortcut="4",
    )
    add(
        namespace="knowledge", name="", display_name="知识库",
        help="记忆库、禅思历史、系统诊断、技能图谱",
        category="navigation", action_type="screen",
        target="knowledge", handler_name="cmd_tui",
        icon="📚", shortcut="5",
    )
    add(
        namespace="system", name="", display_name="系统管理",
        help="Hooks/采集器/通知/会话/感知/LLM管理",
        category="navigation", action_type="screen",
        target="system", handler_name="cmd_tui",
        icon="🔧", shortcut="6",
    )
    add(
        namespace="llm", name="", display_name="LLM 管理",
        help="查看模型配置、切换模型、测试",
        category="navigation", action_type="screen",
        target="llm", handler_name="cmd_tui",
        icon="🤖", shortcut="7",
    )
    add(
        namespace="ecosystem", name="", display_name="技能生态",
        help="多技能生态总览、跨技能洞察、对比分析",
        category="navigation", action_type="screen",
        target="ecosystem", handler_name="cmd_tui",
        icon="🌍", shortcut="8",
    )
    add(
        namespace="doctor", name="", display_name="诊断中心",
        help="状态扫描、修复、快照、诊断日志、迁移",
        category="navigation", action_type="screen",
        target="doctor", handler_name="cmd_tui",
        icon="🏥", shortcut="9",
    )
    add(
        namespace="experiment", name="", display_name="实验管理",
        help="A/B 实验列表、创建、记录、分析",
        category="navigation", action_type="screen",
        target="experiment", handler_name="cmd_tui",
        icon="🧪", shortcut="0",
    )
    # ── 成长系统 ──────────────────────────────────────────

    add(
        namespace="growth", name="status", display_name="成长状态",
        help="显示五维能力雷达图",
        category="growth", action_type="output",
        handler_name="cmd_growth_status",
        icon="📊",
        flags=[
            CommandArg("skill_id", type="string", default="zenskill-core", help="技能ID"),
        ],
    )
    add(
        namespace="growth", name="trend", display_name="成长趋势",
        help="显示成长趋势图",
        category="growth", action_type="output",
        handler_name="cmd_growth_trend",
        icon="📈",
        flags=[
            CommandArg("skill_id", type="string", default="zenskill-core", help="技能ID"),
            CommandArg("dimension", type="choice",
                       choices=["composite", "proficiency", "stability", "satisfaction", "responsiveness", "memory"],
                       help="指定维度"),
        ],
    )
    add(
        namespace="growth", name="milestones", display_name="成长里程碑",
        help="列出所有成长里程碑",
        category="growth", action_type="output",
        handler_name="cmd_growth_milestones",
        icon="🏅",
        flags=[CommandArg("skill_id", type="string", default="zenskill-core")],
    )
    add(
        namespace="growth", name="abilities", display_name="已解锁能力",
        help="显示已解锁能力列表",
        category="growth", action_type="output",
        handler_name="cmd_growth_abilities",
        icon="🔮",
        flags=[CommandArg("skill_id", type="string", default="zenskill-core")],
    )
    add(
        namespace="growth", name="ceremony", display_name="境界突破仪式",
        help="显示境界突破仪式",
        category="growth", action_type="output",
        handler_name="cmd_growth_ceremony",
        icon="🎊",
        flags=[
            CommandArg("skill_id", type="string", default="zenskill-core"),
            CommandArg("history", type="choice", choices=["true", "false"], help="显示历史列表"),
        ],
    )
    add(
        namespace="growth", name="insight", display_name="成长洞察报告",
        help="显示智能成长洞察报告",
        category="growth", action_type="output",
        handler_name="cmd_growth_insight",
        icon="💎",
        flags=[
            CommandArg("skill_id", type="string", default="zenskill-core"),
            CommandArg("brief", type="choice", choices=["true", "false"], help="精简版"),
        ],
    )

    # ── 技能管理 ──────────────────────────────────────────

    add(
        namespace="skill", name="status", display_name="修炼状态",
        help="查询技能修炼状态",
        category="skill", action_type="output",
        handler_name="cmd_skill_status",
        icon="🎯",
        args=[CommandArg("skill_id", type="string", default="zenskill-core")],
    )
    add(
        namespace="skill", name="list", display_name="技能列表",
        help="列出所有已注册技能",
        category="skill", action_type="output",
        handler_name="cmd_skill_list",
        icon="📦",
    )
    add(
        namespace="skill", name="metrics", display_name="使用指标",
        help="显示技能使用指标",
        category="skill", action_type="output",
        handler_name="cmd_metrics",
        icon="📊",
        args=[CommandArg("skill_id", type="string", default="zenskill-core")],
    )
    add(
        namespace="skill", name="history", display_name="状态历史",
        help="查看状态历史记录",
        category="skill", action_type="output",
        handler_name="cmd_history",
        icon="📜",
        args=[CommandArg("skill_id", type="string", default="zenskill-core")],
        flags=[CommandArg("n", type="int", default=10, help="显示条数")],
    )
    add(
        namespace="skill", name="rollback", display_name="回滚状态",
        help="回滚技能状态",
        category="skill", action_type="action",
        handler_name="cmd_rollback",
        icon="↩️",
        args=[CommandArg("skill_id", type="string", default="zenskill-core")],
        flags=[CommandArg("n", type="int", default=1, help="回滚步数")],
    )

    # ── 目标管理 ──────────────────────────────────────────

    add(
        namespace="goal", name="status", display_name="目标状态",
        help="显示当前目标状态",
        category="goal", action_type="output",
        handler_name="cmd_goal_status",
        icon="🏆",
        flags=[CommandArg("skill_id", type="string", default="zenskill-core")],
    )
    add(
        namespace="goal", name="suggest", display_name="推荐目标",
        help="推荐成长目标",
        category="goal", action_type="output",
        handler_name="cmd_goal_suggest",
        icon="💡",
        flags=[CommandArg("skill_id", type="string", default="zenskill-core")],
    )
    add(
        namespace="goal", name="set", display_name="设置目标",
        help="设置成长目标",
        category="goal", action_type="action",
        handler_name="cmd_goal_set",
        icon="✅",
        flags=[
            CommandArg("skill_id", type="string", default="zenskill-core"),
            CommandArg("dimension", type="choice", required=True,
                       choices=["proficiency", "stability", "satisfaction", "responsiveness", "memory", "composite"],
                       help="目标维度"),
            CommandArg("target", type="int", required=True, help="目标分数 (0-100)"),
        ],
    )

    # ── 任务推荐 ──────────────────────────────────────────

    add(
        namespace="task", name="recommend", display_name="推荐任务",
        help="推荐练习任务",
        category="task", action_type="output",
        handler_name="cmd_task_recommend",
        icon="📋",
        flags=[CommandArg("skill_id", type="string", default="zenskill-core")],
    )
    add(
        namespace="task", name="status", display_name="任务状态",
        help="查看任务状态",
        category="task", action_type="output",
        handler_name="cmd_task_status",
        icon="📋",
        flags=[CommandArg("skill_id", type="string", default="zenskill-core")],
    )
    add(
        namespace="task", name="complete", display_name="完成任务",
        help="标记任务完成",
        category="task", action_type="action",
        handler_name="cmd_task_complete",
        icon="✅",
        args=[CommandArg("task_id", type="string", required=True, help="任务ID")],
    )

    # ── 洞察系统 ──────────────────────────────────────────

    add(
        namespace="insight", name="unread", display_name="未读洞察",
        help="查看未读洞察",
        category="insight", action_type="output",
        handler_name="cmd_insight_unread",
        icon="💡",
        flags=[CommandArg("skill_id", type="string", default="zenskill-core")],
    )
    add(
        namespace="insight", name="read", display_name="标记已读",
        help="标记洞察为已读",
        category="insight", action_type="action",
        handler_name="cmd_insight_mark_read",
        icon="✅",
        args=[CommandArg("insight_id", type="string", required=True, help="洞察ID")],
    )

    # ── 记忆系统 ──────────────────────────────────────────

    add(
        namespace="memory", name="add", display_name="添加记忆",
        help="添加一条记忆",
        category="memory", action_type="action",
        handler_name="cmd_memory_add",
        icon="➕",
        args=[CommandArg("content", type="string", required=True, help="记忆内容")],
        flags=[CommandArg("tags", type="string", help="标签，逗号分隔")],
    )
    add(
        namespace="memory", name="list", display_name="记忆列表",
        help="列出记忆",
        category="memory", action_type="output",
        handler_name="cmd_memory_list",
        icon="📋",
        flags=[CommandArg("n", type="int", default=20, help="显示条数")],
    )
    add(
        namespace="memory", name="search", display_name="搜索记忆",
        help="搜索记忆",
        category="memory", action_type="output",
        handler_name="cmd_memory_search",
        icon="🔍",
        args=[CommandArg("keyword", type="string", required=True, help="搜索关键词")],
    )
    add(
        namespace="memory", name="export", display_name="导出记忆",
        help="导出记忆到文件",
        category="memory", action_type="action",
        handler_name="cmd_memory_export",
        icon="📤",
        flags=[
            CommandArg("skill_id", type="string", default="zenskill-core"),
            CommandArg("output", type="file", help="输出文件路径"),
        ],
    )
    add(
        namespace="memory", name="import", display_name="导入记忆",
        help="从文件导入记忆",
        category="memory", action_type="action",
        handler_name="cmd_memory_import",
        icon="📥",
        args=[CommandArg("input", type="file", required=True, help="导入文件路径")],
        flags=[
            CommandArg("skill_id", type="string", default="zenskill-core"),
            CommandArg("dry_run", type="choice", choices=["true", "false"], help="预览"),
        ],
    )

    # ── 禅思反思 ──────────────────────────────────────────

    add(
        namespace="reflect", name="trigger", display_name="触发反思",
        help="触发禅思反思",
        category="reflect", action_type="output",
        handler_name="cmd_reflect_trigger",
        icon="🧘",
        flags=[
            CommandArg("skill_id", type="string", default="zenskill-core"),
            CommandArg("hosted", type="choice", choices=["true", "false"], help="宿主协作模式"),
            CommandArg("output", type="choice", choices=["json", "text"], default="text"),
        ],
    )
    add(
        namespace="reflect", name="issues", display_name="自我诊断",
        help="系统自我诊断",
        category="reflect", action_type="output",
        handler_name="cmd_reflect_issues",
        icon="🔍",
    )

    # ── 元认知 ────────────────────────────────────────────

    add(
        namespace="meta", name="report", display_name="元反思报告",
        help="元反思综合报告",
        category="meta", action_type="output",
        handler_name="cmd_meta_report",
        icon="🔬",
        flags=[CommandArg("skill_id", type="string", default="zenskill-core")],
    )
    add(
        namespace="meta", name="suggestions", display_name="优化建议",
        help="生成优化建议列表",
        category="meta", action_type="output",
        handler_name="cmd_meta_suggestions",
        icon="💡",
        flags=[CommandArg("skill_id", type="string", default="zenskill-core")],
    )
    add(
        namespace="meta", name="implement", display_name="标记已实现",
        help="标记优化建议为已实现",
        category="meta", action_type="action",
        handler_name="cmd_meta_implement",
        icon="✅",
        args=[CommandArg("optimization_id", type="string", required=True, help="优化建议ID")],
        flags=[CommandArg("skill_id", type="string", default="zenskill-core")],
    )
    add(
        namespace="meta", name="biases", display_name="偏差分析",
        help="查看系统性偏差分析",
        category="meta", action_type="output",
        handler_name="cmd_meta_biases",
        icon="🔍",
        flags=[CommandArg("skill_id", type="string", default="zenskill-core")],
    )

    # ── 技能图谱 ──────────────────────────────────────────

    add(
        namespace="graph", name="overview", display_name="图谱概览",
        help="技能图谱概览",
        category="graph", action_type="output",
        handler_name="cmd_graph_overview",
        icon="🕸️",
    )
    add(
        namespace="graph", name="register", display_name="注册技能",
        help="注册技能到图谱",
        category="graph", action_type="action",
        handler_name="cmd_graph_register",
        icon="➕",
        args=[CommandArg("skill_id", type="string", required=True, help="技能ID")],
        flags=[
            CommandArg("name", type="string", help="技能名称"),
            CommandArg("category", type="choice",
                       choices=["coding", "writing", "analysis", "learning", "productivity", "communication", "general"],
                       default="general"),
        ],
    )
    add(
        namespace="graph", name="discover", display_name="发现关系",
        help="自动发现技能间关系",
        category="graph", action_type="output",
        handler_name="cmd_graph_discover",
        icon="🔍",
    )
    add(
        namespace="graph", name="related", display_name="关联技能",
        help="查看技能的关联技能",
        category="graph", action_type="output",
        handler_name="cmd_graph_related",
        icon="🔗",
        args=[CommandArg("skill_id", type="string", required=True, help="技能ID")],
        flags=[CommandArg("type", type="string", help="关系类型过滤")],
    )
    add(
        namespace="graph", name="learn-path", display_name="学习路径",
        help="推荐学习路径",
        category="graph", action_type="output",
        handler_name="cmd_graph_learning_path",
        icon="🗺️",
        args=[CommandArg("target_skill", type="string", required=True, help="目标技能")],
        flags=[CommandArg("max_depth", type="int", default=3)],
    )

    # ── 跨技能洞察 ────────────────────────────────────────

    add(
        namespace="cross", name="report", display_name="全局报告",
        help="全局成长报告",
        category="cross", action_type="output",
        handler_name="cmd_cross_report",
        icon="📊",
    )
    add(
        namespace="cross", name="insights", display_name="跨技能洞察",
        help="查看跨技能洞察",
        category="cross", action_type="output",
        handler_name="cmd_cross_insights",
        icon="💡",
    )
    add(
        namespace="cross", name="compare", display_name="对比分析",
        help="跨技能对比分析",
        category="cross", action_type="output",
        handler_name="cmd_cross_compare",
        icon="⚖️",
        args=[CommandArg("skill_ids", type="string", required=True, help="技能ID列表（空格分隔）")],
    )

    # ── 生态仪表盘 ────────────────────────────────────────

    add(
        namespace="eco", name="dashboard", display_name="生态仪表盘",
        help="技能生态系统仪表盘",
        category="eco", action_type="output",
        handler_name="cmd_eco_dashboard",
        icon="🌍",
    )
    add(
        namespace="eco", name="heatmap", display_name="成长热力图",
        help="成长热力图详细报告",
        category="eco", action_type="output",
        handler_name="cmd_eco_heatmap",
        icon="🗺️",
    )
    add(
        namespace="eco", name="health", display_name="健康度",
        help="生态系统健康度评估",
        category="eco", action_type="output",
        handler_name="cmd_eco_health",
        icon="🏥",
    )

    # ── 用户镜像 ──────────────────────────────────────────

    add(
        namespace="mirror", name="status", display_name="镜像状态",
        help="数据采集概览",
        category="mirror", action_type="output",
        handler_name="cmd_mirror_status",
        icon="🪞",
    )
    add(
        namespace="mirror", name="events", display_name="事件记录",
        help="查看最近事件",
        category="mirror", action_type="output",
        handler_name="cmd_mirror_events",
        icon="📋",
        flags=[
            CommandArg("n", type="int", default=20, help="显示条数"),
            CommandArg("type", type="string", help="事件类型过滤"),
        ],
    )
    add(
        namespace="mirror", name="features", display_name="特征向量",
        help="查看或计算用户行为特征",
        category="mirror", action_type="output",
        handler_name="cmd_mirror_features",
        icon="📈",
        flags=[CommandArg("recompute", type="choice", choices=["true", "false"])],
    )
    add(
        namespace="mirror", name="privacy", display_name="隐私设置",
        help="查看隐私设置",
        category="mirror", action_type="output",
        handler_name="cmd_mirror_privacy",
        icon="🔒",
    )
    add(
        namespace="mirror", name="privacy-set", display_name="更新隐私",
        help="更新隐私设置",
        category="mirror", action_type="action",
        handler_name="cmd_mirror_privacy_set",
        icon="🔧",
        args=[
            CommandArg("key", type="string", required=True, help="设置项"),
            CommandArg("value", type="string", required=True, help="值"),
        ],
    )
    add(
        namespace="mirror", name="export", display_name="导出镜像",
        help="导出所有镜像数据",
        category="mirror", action_type="action",
        handler_name="cmd_mirror_export",
        icon="📤",
        args=[CommandArg("output", type="file", required=True, help="输出路径")],
    )
    add(
        namespace="mirror", name="delete-all", display_name="删除镜像",
        help="删除所有镜像数据",
        category="mirror", action_type="action",
        handler_name="cmd_mirror_delete_all",
        icon="🗑️",
    )
    add(
        namespace="mirror", name="purge", display_name="清理过期",
        help="清理过期事件并匿名化旧数据",
        category="mirror", action_type="action",
        handler_name="cmd_mirror_purge",
        icon="🧹",
    )

    # ── 数据管理 ──────────────────────────────────────────

    add(
        namespace="data", name="paths", display_name="数据路径",
        help="显示所有数据目录路径",
        category="data", action_type="output",
        handler_name="cmd_data_paths",
        icon="📂",
    )
    add(
        namespace="data", name="export", display_name="导出数据",
        help="导出所有数据（全量备份）",
        category="data", action_type="action",
        handler_name="cmd_data_export",
        icon="📤",
        flags=[CommandArg("output", type="file", help="输出目录")],
    )
    add(
        namespace="data", name="stats", display_name="数据统计",
        help="显示数据统计",
        category="data", action_type="output",
        handler_name="cmd_data_stats",
        icon="📊",
        flags=[CommandArg("skill_id", type="string", default="zenskill-core")],
    )

    # ── 配置 ──────────────────────────────────────────────

    add(
        namespace="config", name="show", display_name="当前配置",
        help="显示当前配置和宿主环境",
        category="config", action_type="output",
        handler_name="cmd_config_show",
        icon="⚙️",
    )
    add(
        namespace="config", name="set", display_name="设置配置",
        help="设置配置项",
        category="config", action_type="action",
        handler_name="cmd_config_set",
        icon="🔧",
        args=[
            CommandArg("key", type="string", required=True, help="配置键"),
            CommandArg("value", type="string", required=True, help="配置值"),
        ],
    )

    # ── 系统 ──────────────────────────────────────────────

    add(
        namespace="info", name="", display_name="系统信息",
        help="显示系统信息",
        category="system", action_type="output",
        handler_name="cmd_info",
        icon="ℹ️",
    )
    add(
        namespace="theme", name="", display_name="切换主题",
        help="切换简洁/华丽主题",
        category="system", action_type="action",
        handler_name="",  # 由 TUI 内部处理
        icon="🎨",
        args=[CommandArg("name", type="choice", choices=["clean", "rich"], help="主题名")],
    )

    # ── doctor 诊断 ────────────────────────────────────────

    add(
        namespace="doctor", name="state", display_name="扫描状态健康",
        help="扫描状态数据完整性",
        category="doctor", action_type="output",
        handler_name="cmd_doctor_state",
        icon="🏥",
    )
    add(
        namespace="doctor", name="repair", display_name="修复状态文件",
        help="修复可恢复的状态数据",
        category="doctor", action_type="action",
        handler_name="cmd_doctor_repair",
        icon="🔧",
        flags=[CommandArg("dry_run", type="choice", choices=["true", "false"], help="预览修复计划")],
    )
    add(
        namespace="doctor", name="snapshot", display_name="管理快照",
        help="创建/列出数据快照",
        category="doctor", action_type="output",
        handler_name="cmd_doctor_snapshot",
        icon="📸",
        flags=[CommandArg("list", type="choice", choices=["true", "false"], help="列出所有快照")],
    )
    add(
        namespace="doctor", name="diagnostics", display_name="诊断日志",
        help="查看诊断日志",
        category="doctor", action_type="output",
        handler_name="cmd_doctor_diagnostics",
        icon="📋",
        flags=[CommandArg("n", type="int", default=50, help="显示最近 N 条")],
    )
    add(
        namespace="doctor", name="migrate", display_name="迁移 schema",
        help="迁移状态 schema 版本",
        category="doctor", action_type="action",
        handler_name="cmd_doctor_migrate",
        icon="🔄",
        flags=[CommandArg("all", type="choice", choices=["true", "false"], help="迁移所有技能状态")],
    )

    # ── experiment 实验 ────────────────────────────────────

    add(
        namespace="experiment", name="list", display_name="列出实验",
        help="列出所有实验",
        category="experiment", action_type="output",
        handler_name="cmd_experiment_list",
        icon="🧪",
    )
    add(
        namespace="experiment", name="create", display_name="创建实验",
        help="创建 A/B 实验",
        category="experiment", action_type="action",
        handler_name="cmd_experiment_create",
        icon="➕",
        args=[CommandArg("name", type="string", required=True, help="实验名称")],
        flags=[
            CommandArg("description", type="string", default="", help="实验描述"),
            CommandArg("variants", type="string", required=True, help="变体名称列表"),
            CommandArg("metrics", type="string", required=True, help="跟踪指标列表"),
        ],
    )
    add(
        namespace="experiment", name="record", display_name="记录实验数据",
        help="记录实验数据",
        category="experiment", action_type="action",
        handler_name="cmd_experiment_record",
        icon="📝",
        args=[CommandArg("name", type="string", required=True, help="实验名称")],
        flags=[
            CommandArg("variant", type="string", required=True, help="变体名称"),
            CommandArg("metrics", type="string", required=True, help="指标值 JSON"),
        ],
    )
    add(
        namespace="experiment", name="analyze", display_name="分析实验",
        help="分析实验结果",
        category="experiment", action_type="output",
        handler_name="cmd_experiment_analyze",
        icon="📊",
        args=[CommandArg("name", type="string", required=True, help="实验名称")],
    )
    add(
        namespace="experiment", name="delete", display_name="删除实验",
        help="完成并删除实验",
        category="experiment", action_type="action",
        handler_name="cmd_experiment_complete",
        icon="🗑️",
        args=[CommandArg("name", type="string", required=True, help="实验名称")],
    )

    # ── llm 模型管理 ──────────────────────────────────────

    add(
        namespace="llm", name="list", display_name="列出模型",
        help="列出所有支持的模型",
        category="llm", action_type="output",
        handler_name="cmd_llm_list",
        icon="🤖",
    )
    add(
        namespace="llm", name="show", display_name="当前配置",
        help="显示当前 LLM 配置",
        category="llm", action_type="output",
        handler_name="cmd_llm_show",
        icon="⚙️",
    )
    add(
        namespace="llm", name="set", display_name="切换模型",
        help="设置默认模型",
        category="llm", action_type="action",
        handler_name="cmd_llm_set",
        icon="🔧",
        args=[CommandArg("model", type="string", required=True, help="模型名称")],
        flags=[
            CommandArg("provider", type="string", help="强制指定服务商"),
            CommandArg("base_url", type="string", help="自定义 API 地址"),
        ],
    )
    add(
        namespace="llm", name="test", display_name="测试模型",
        help="测试当前模型",
        category="llm", action_type="output",
        handler_name="cmd_llm_test",
        icon="🧪",
        flags=[CommandArg("prompt", type="string", default="请简单介绍一下你自己", help="测试提示词")],
    )
    add(
        namespace="llm", name="providers", display_name="列出 provider",
        help="列出所有模型服务商",
        category="llm", action_type="output",
        handler_name="cmd_llm_list",
        icon="📦",
    )

    # ── hook 钩子管理 ──────────────────────────────────────

    add(
        namespace="hook", name="list", display_name="列出钩子",
        help="列出所有 Hook 及状态",
        category="hook", action_type="output",
        handler_name="cmd_hook_list",
        icon="🪝",
    )
    add(
        namespace="hook", name="enable", display_name="启用钩子",
        help="启用指定 Hook",
        category="hook", action_type="action",
        handler_name="cmd_hook_enable",
        icon="🟢",
        args=[CommandArg("hook_name", type="string", required=True, help="Hook 名称")],
    )
    add(
        namespace="hook", name="disable", display_name="禁用钩子",
        help="禁用指定 Hook",
        category="hook", action_type="action",
        handler_name="cmd_hook_disable",
        icon="🔴",
        args=[CommandArg("hook_name", type="string", required=True, help="Hook 名称")],
    )
    add(
        namespace="hook", name="run", display_name="手动运行钩子",
        help="Hook 状态摘要",
        category="hook", action_type="output",
        handler_name="cmd_hook_status",
        icon="▶️",
        args=[CommandArg("hook_name", type="string", required=True, help="Hook 名称")],
    )

    # ── collector 采集器 ───────────────────────────────────

    add(
        namespace="collector", name="list", display_name="列出采集器",
        help="列出所有采集器",
        category="collector", action_type="output",
        handler_name="cmd_collector_list",
        icon="📥",
    )
    add(
        namespace="collector", name="run", display_name="运行采集器",
        help="运行指定采集器",
        category="collector", action_type="action",
        handler_name="cmd_collector_run",
        icon="▶️",
        args=[CommandArg("name", type="string", required=True, help="采集器名称")],
    )
    add(
        namespace="collector", name="run-all", display_name="运行全部采集器",
        help="运行全部采集器",
        category="collector", action_type="action",
        handler_name="cmd_collector_run_all",
        icon="⏩",
    )
    add(
        namespace="collector", name="status", display_name="采集器状态",
        help="采集器状态摘要",
        category="collector", action_type="output",
        handler_name="cmd_collector_list",
        icon="📊",
    )
    add(
        namespace="collector", name="config", display_name="采集器配置",
        help="查看采集器配置",
        category="collector", action_type="output",
        handler_name="cmd_collector_run",
        icon="⚙️",
        args=[CommandArg("name", type="string", required=True, help="采集器名称")],
    )

    # ── notify 通知 ────────────────────────────────────────

    add(
        namespace="notify", name="list", display_name="列出通知",
        help="列出当前待推送通知",
        category="notify", action_type="output",
        handler_name="cmd_notify",
        icon="🔔",
    )
    add(
        namespace="notify", name="mark-read", display_name="标记已读",
        help="标记通知为已读",
        category="notify", action_type="action",
        handler_name="cmd_notify",
        icon="✅",
        args=[CommandArg("notification_id", type="string", required=True, help="通知ID")],
    )

    # ── session 会话 ───────────────────────────────────────

    add(
        namespace="session", name="stats", display_name="会话统计",
        help="显示当前会话状态",
        category="session", action_type="output",
        handler_name="cmd_session",
        icon="📡",
    )
    add(
        namespace="session", name="reset", display_name="重置会话",
        help="重置当前会话",
        category="session", action_type="action",
        handler_name="cmd_session",
        icon="🔄",
    )

    # ── perceive 感知 ──────────────────────────────────────

    add(
        namespace="perceive", name="check", display_name="感知检查",
        help="感知引擎实时评估",
        category="perceive", action_type="output",
        handler_name="cmd_perceive",
        icon="👁️",
    )

    # ── context 上下文 ─────────────────────────────────────

    add(
        namespace="context", name="stats", display_name="上下文统计",
        help="ACT 响应统计 + 偏好分析",
        category="context", action_type="output",
        handler_name="cmd_context_stats",
        icon="📊",
    )
    add(
        namespace="context", name="respond", display_name="标记响应",
        help="标记对话已被响应",
        category="context", action_type="action",
        handler_name="cmd_context_respond",
        icon="✅",
        args=[CommandArg("context_id", type="string", help="上下文ID")],
    )
    add(
        namespace="context", name="history", display_name="上下文历史",
        help="查看多轮对话历史",
        category="context", action_type="output",
        handler_name="cmd_context_history",
        icon="📜",
        flags=[CommandArg("n", type="int", default=10, help="显示条数")],
    )
    add(
        namespace="context", name="reset", display_name="重置上下文",
        help="重置所有 Context Card 追踪数据",
        category="context", action_type="action",
        handler_name="cmd_context_reset",
        icon="🔄",
    )
    add(
        namespace="context", name="guide", display_name="上下文引导",
        help="上下文感知引导 — 智能操作建议",
        category="context", action_type="output",
        handler_name="cmd_context_guide",
        icon="🧭",
        flags=[CommandArg("hours", type="int", default=24, help="回溯小时数")],
    )
    add(
        namespace="context", name="perceive", display_name="上下文感知",
        help="Context Card 预览",
        category="context", action_type="output",
        handler_name="cmd_context",
        icon="👁️",
    )
    add(
        namespace="context", name="collect", display_name="收集上下文",
        help="收集上下文信息",
        category="context", action_type="output",
        handler_name="cmd_context",
        icon="📥",
    )

    # ── growth 补充 ────────────────────────────────────────

    add(
        namespace="growth", name="accelerate", display_name="成长加速",
        help="成长加速器 — 检测学习陡坡",
        category="growth", action_type="output",
        handler_name="cmd_growth_accelerate",
        icon="🚀",
    )
    add(
        namespace="growth", name="predict", display_name="成长预测",
        help="技能成长预测 — 晋升时间估算",
        category="growth", action_type="output",
        handler_name="cmd_growth_predict",
        icon="🔮",
    )
    add(
        namespace="growth", name="export", display_name="导出成长数据",
        help="导出成长报告 — Markdown/JSON",
        category="growth", action_type="action",
        handler_name="cmd_growth_export",
        icon="📤",
        flags=[
            CommandArg("format", type="choice", choices=["markdown", "json"], default="markdown", help="输出格式"),
            CommandArg("output", type="file", help="输出目录"),
        ],
    )
    add(
        namespace="growth", name="report", display_name="成长报告",
        help="生成终极成长报告",
        category="growth", action_type="output",
        handler_name="cmd_growth_report",
        icon="📊",
        flags=[CommandArg("output", type="file", help="输出文件路径")],
    )
    add(
        namespace="growth", name="compare", display_name="多维对比",
        help="多维对比分析 — 本期 vs 过去",
        category="growth", action_type="output",
        handler_name="cmd_growth_compare",
        icon="⚖️",
    )
    add(
        namespace="growth", name="replay", display_name="路径回放",
        help="成长路径回放 — 时间线叙事",
        category="growth", action_type="output",
        handler_name="cmd_growth_replay",
        icon="⏪",
    )
    add(
        namespace="growth", name="errors", display_name="错误模式",
        help="错误模式聚类 — Top 错误类型与建议",
        category="growth", action_type="output",
        handler_name="cmd_growth_errors",
        icon="🐛",
    )
    add(
        namespace="growth", name="feedback", display_name="即时反馈",
        help="即时反馈与奖励 — 微反馈/连击/每日成就",
        category="growth", action_type="output",
        handler_name="cmd_growth_feedback",
        icon="🎯",
    )
    add(
        namespace="growth", name="dimensions", display_name="自定义维度",
        help="自定义成长维度 — 定义/模板/导入导出",
        category="growth", action_type="output",
        handler_name="cmd_growth_dimensions",
        icon="📐",
    )
    add(
        namespace="growth", name="habits", display_name="习惯追踪",
        help="习惯养成追踪 — 打卡日历/连续天数/中断风险",
        category="growth", action_type="output",
        handler_name="cmd_growth_habits",
        icon="📅",
    )
    add(
        namespace="growth", name="achievements", display_name="成就系统",
        help="成就系统 — 已解锁成就列表",
        category="growth", action_type="output",
        handler_name="cmd_growth_achievements",
        icon="🏆",
    )

    # ── graph 补充 ─────────────────────────────────────────

    add(
        namespace="graph", name="query", display_name="图谱查询",
        help="查询知识图谱",
        category="graph", action_type="output",
        handler_name="cmd_graph_query",
        icon="🔍",
        args=[CommandArg("query", type="string", required=True, help="搜索关键词")],
    )
    add(
        namespace="graph", name="combos", display_name="技能组合推荐",
        help="推荐技能组合",
        category="graph", action_type="output",
        handler_name="cmd_graph_combos",
        icon="🤝",
    )
    add(
        namespace="graph", name="alerts", display_name="生态健康预警",
        help="生态健康预警",
        category="graph", action_type="output",
        handler_name="cmd_graph_alerts",
        icon="⚠️",
    )
    add(
        namespace="graph", name="conflicts", display_name="冲突检测",
        help="跨技能冲突检测",
        category="graph", action_type="output",
        handler_name="cmd_graph_conflicts",
        icon="⚡",
    )
    add(
        namespace="graph", name="dynamics", display_name="网络动力学",
        help="网络动力学分析",
        category="graph", action_type="output",
        handler_name="cmd_graph_dynamics",
        icon="🌊",
    )
    add(
        namespace="graph", name="lifecycle", display_name="生命周期管理",
        help="技能生命周期分析",
        category="graph", action_type="output",
        handler_name="cmd_graph_lifecycle",
        icon="♻️",
    )
    add(
        namespace="graph", name="transfer", display_name="迁移学习",
        help="迁移学习模式检测",
        category="graph", action_type="output",
        handler_name="cmd_graph_transfer",
        icon="🔀",
    )
    add(
        namespace="graph", name="orchestrate", display_name="跨技能编排",
        help="跨技能任务编排",
        category="graph", action_type="output",
        handler_name="cmd_graph_orchestrate",
        icon="🎼",
    )
    add(
        namespace="graph", name="cross-project", display_name="跨项目迁移",
        help="跨项目知识迁移",
        category="graph", action_type="output",
        handler_name="cmd_graph_cross_project",
        icon="🏗️",
    )
    add(
        namespace="graph", name="influence", display_name="影响力评估",
        help="技能影响力评估",
        category="graph", action_type="output",
        handler_name="cmd_graph_influence",
        icon="💪",
    )
    add(
        namespace="graph", name="redundancy", display_name="冗余检测",
        help="知识冗余检测",
        category="graph", action_type="output",
        handler_name="cmd_graph_redundancy",
        icon="🔁",
    )
    add(
        namespace="graph", name="resources", display_name="资源推荐",
        help="学习资源推荐",
        category="graph", action_type="output",
        handler_name="cmd_graph_resources",
        icon="📚",
    )
    add(
        namespace="graph", name="innovate", display_name="创新检测",
        help="跨领域创新检测",
        category="graph", action_type="output",
        handler_name="cmd_graph_innovate",
        icon="💡",
    )

    # ── mirror 补充 ────────────────────────────────────────

    add(
        namespace="mirror", name="scan", display_name="扫描镜像",
        help="扫描并索引当前环境",
        category="mirror", action_type="output",
        handler_name="cmd_mirror_scan",
        icon="🔍",
    )
    add(
        namespace="mirror", name="profile", display_name="用户画像",
        help="查看用户画像",
        category="mirror", action_type="output",
        handler_name="cmd_mirror_profile",
        icon="👤",
    )
    add(
        namespace="mirror", name="sync-skills", display_name="同步技能",
        help="同步 Claude Code 技能到 ZenSkill",
        category="mirror", action_type="action",
        handler_name="cmd_mirror_sync_skills",
        icon="🔄",
    )
    add(
        namespace="mirror", name="learn", display_name="学习模式",
        help="从行为数据学习用户偏好",
        category="mirror", action_type="output",
        handler_name="cmd_mirror_learn",
        icon="📖",
    )
    add(
        namespace="mirror", name="workflow", display_name="工作流分析",
        help="工作流模式分析",
        category="mirror", action_type="output",
        handler_name="cmd_mirror_workflow",
        icon="⚙️",
    )
    add(
        namespace="mirror", name="predict", display_name="行为预测",
        help="预测下一步行动",
        category="mirror", action_type="output",
        handler_name="cmd_mirror_predict",
        icon="🔮",
    )
    add(
        namespace="mirror", name="tips", display_name="智能建议",
        help="轻量智能建议（适合 Hook）",
        category="mirror", action_type="output",
        handler_name="cmd_mirror_tips",
        icon="💡",
    )
    add(
        namespace="mirror", name="export-prefs", display_name="导出偏好",
        help="导出偏好文件",
        category="mirror", action_type="action",
        handler_name="cmd_mirror_export",
        icon="📤",
        args=[CommandArg("output", type="file", required=True, help="输出文件路径")],
    )
    add(
        namespace="mirror", name="import-prefs", display_name="导入偏好",
        help="导入偏好文件",
        category="mirror", action_type="action",
        handler_name="cmd_mirror_import",
        icon="📥",
        args=[CommandArg("input", type="file", required=True, help="输入文件路径")],
    )
    add(
        namespace="mirror", name="sync-global", display_name="全局同步",
        help="全局偏好同步",
        category="mirror", action_type="action",
        handler_name="cmd_mirror_sync_global",
        icon="🌐",
    )

    # ── skill 补充 ─────────────────────────────────────────

    add(
        namespace="skill", name="predict", display_name="技能预测",
        help="技能成长预测",
        category="skill", action_type="output",
        handler_name="cmd_skill_predict",
        icon="🔮",
    )
    add(
        namespace="skill", name="info", display_name="技能详情",
        help="技能全貌（Claude Code + ZenSkill）",
        category="skill", action_type="output",
        handler_name="cmd_skill_info",
        icon="ℹ️",
    )
    add(
        namespace="skill", name="define", display_name="定义技能",
        help="用自然语言定义新技能",
        category="skill", action_type="action",
        handler_name="cmd_skill_define",
        icon="✏️",
    )
    add(
        namespace="skill", name="testgen", display_name="生成测试",
        help="自动生成技能测试用例",
        category="skill", action_type="output",
        handler_name="cmd_skill_testgen",
        icon="🧪",
    )
    add(
        namespace="skill", name="template list", display_name="模板列表",
        help="列出预置技能模板 (8I)",
        category="skill", action_type="output",
        handler_name="cmd_template_list",
        icon="📋",
        flags=[
            CommandArg("category", type="choice",
                       choices=["coding", "writing", "devops", "analysis", "learning", "productivity", "communication"],
                       help="按分类筛选"),
            CommandArg("difficulty", type="choice",
                       choices=["beginner", "intermediate", "advanced", "expert"],
                       help="按难度筛选"),
        ],
    )
    add(
        namespace="skill", name="template use", display_name="使用模板",
        help="使用模板创建技能 (8I)",
        category="skill", action_type="action",
        handler_name="cmd_template_use",
        icon="✅",
        args=[CommandArg("template_name", type="string", required=True, help="模板名称")],
        flags=[CommandArg("skill_id", type="string", help="技能ID")],
    )
    add(
        namespace="skill", name="tutor", display_name="智能导师",
        help="学习风格/错误诊断/自适应建议 (8Y)",
        category="skill", action_type="output",
        handler_name="cmd_tutor",
        icon="🎓",
    )
    add(
        namespace="skill", name="template", display_name="技能模板",
        help="生成技能模板/计划/清单",
        category="skill", action_type="output",
        handler_name="cmd_skill_template",
        icon="📋",
    )
    add(
        namespace="skill", name="route", display_name="学习路由",
        help="智能路由: 找到最匹配的技能能力",
        category="skill", action_type="output",
        handler_name="cmd_skill_route",
        icon="🗺️",
    )
    add(
        namespace="skill", name="curve", display_name="学习曲线",
        help="学习曲线可视化",
        category="skill", action_type="output",
        handler_name="cmd_skill_curve",
        icon="📈",
    )
    add(
        namespace="skill", name="forget", display_name="遗忘曲线",
        help="遗忘检测 — 长时间未使用的技能",
        category="skill", action_type="output",
        handler_name="cmd_skill_forget",
        icon="🧠",
    )
    add(
        namespace="skill", name="break", display_name="瓶颈检测",
        help="智能间歇建议 — 番茄钟 + 疲劳 + 最佳时段",
        category="skill", action_type="output",
        handler_name="cmd_skill_break",
        icon="⏰",
    )
    add(
        namespace="skill", name="transfer", display_name="迁移分析",
        help="跨技能迁移学习",
        category="skill", action_type="output",
        handler_name="cmd_skill_transfer",
        icon="🔀",
    )

    # ── skill 补充: 快照/版本/分支 ──

    add(
        namespace="skill", name="snapshot list", display_name="历史快照",
        help="列出历史快照 (8W)",
        category="skill", action_type="output",
        handler_name="cmd_snapshot_list",
        icon="📸",
        flags=[CommandArg("n", type="int", default=20, help="显示条数")],
    )
    add(
        namespace="skill", name="snapshot save", display_name="保存快照",
        help="创建命名快照 (8W)",
        category="skill", action_type="action",
        handler_name="cmd_snapshot_save",
        icon="💾",
        flags=[CommandArg("name", type="string", required=True, help="快照名称")],
    )
    add(
        namespace="skill", name="snapshot restore", display_name="恢复快照",
        help="恢复到命名快照 (8W)",
        category="skill", action_type="action",
        handler_name="cmd_snapshot_restore",
        icon="⏪",
        args=[CommandArg("name", type="string", required=True, help="快照名称")],
    )
    add(
        namespace="skill", name="diff", display_name="版本对比",
        help="对比两个版本的状态差异 (8X)",
        category="skill", action_type="output",
        handler_name="cmd_skill_diff",
        icon="📊",
        flags=[
            CommandArg("v1", type="int", required=True, help="旧版本号"),
            CommandArg("v2", type="int", required=True, help="新版本号"),
        ],
    )
    add(
        namespace="skill", name="branch create", display_name="创建分支",
        help="创建学习分支 (8W)",
        category="skill", action_type="action",
        handler_name="cmd_branch_create",
        icon="🌿",
        args=[CommandArg("branch_name", type="string", required=True, help="分支名称")],
    )
    add(
        namespace="skill", name="branch list", display_name="列出分支",
        help="列出所有学习分支 (8W)",
        category="skill", action_type="output",
        handler_name="cmd_branch_list",
        icon="📋",
    )

    # ── reflect 补充 ───────────────────────────────────────

    add(
        namespace="reflect", name="consolidate", display_name="整合反思",
        help="手动触发记忆巩固",
        category="reflect", action_type="output",
        handler_name="cmd_reflect_consolidate",
        icon="🧩",
    )
    add(
        namespace="reflect", name="insight", display_name="反思洞察",
        help="手动触发洞见生成",
        category="reflect", action_type="output",
        handler_name="cmd_reflect_insight",
        icon="💡",
    )
    add(
        namespace="reflect", name="purify", display_name="净化反思",
        help="手动触发记忆净化",
        category="reflect", action_type="output",
        handler_name="cmd_reflect_purify",
        icon="🧹",
    )
    add(
        namespace="reflect", name="store", display_name="存储反思",
        help="存储宿主完成的反思结果（从 stdin 读取 JSON）",
        category="reflect", action_type="action",
        handler_name="cmd_reflect_store",
        icon="💾",
        args=[CommandArg("content", type="string", help="反思内容")],
    )

    # ── 零散补充 ───────────────────────────────────────────

    add(
        namespace="memory", name="stats", display_name="记忆统计",
        help="记忆统计 — 容量/去重/高频操作",
        category="memory", action_type="output",
        handler_name="cmd_memory_stats",
        icon="📊",
    )
    add(
        namespace="task", name="generate", display_name="生成任务",
        help="LLM 生成个性化任务",
        category="task", action_type="output",
        handler_name="cmd_task_generate",
        icon="🤖",
    )
    add(
        namespace="insight", name="generate", display_name="生成洞察",
        help="强制生成新洞察",
        category="insight", action_type="output",
        handler_name="cmd_insight_generate",
        icon="💡",
    )
    add(
        namespace="data", name="migrate", display_name="数据迁移",
        help="数据迁移",
        category="data", action_type="action",
        handler_name="cmd_data_stats",
        icon="🔄",
    )
    add(
        namespace="chat", name="send", display_name="发送消息",
        help="发送消息给 AI 助手",
        category="chat", action_type="output",
        handler_name="cmd_chat",
        icon="💬",
        args=[CommandArg("message", type="string", required=True, help="对话内容")],
    )

    # ── GTD 生产力系统 ──

    add(
        namespace="gtd", name="", display_name="GTD 仪表盘",
        help="Inbox/Action/Project/Energy/Calendar 全景",
        category="navigation", action_type="screen",
        target="gtd-dashboard", handler_name="cmd_tui",
        icon="🎯", shortcut="G",
    )
    add(
        namespace="gtd", name="dashboard", display_name="GTD 仪表盘",
        help="Inbox/Action/Project/Energy 全景",
        category="gtd", action_type="output",
        handler_name="cmd_gtd_dashboard",
        icon="🎯",
    )
    add(
        namespace="gtd", name="weekly-review", display_name="GTD 周回顾",
        help="Inbox清零/Project进度/每周统计",
        category="gtd", action_type="output",
        handler_name="cmd_gtd_weekly_review",
        icon="📋",
    )
    add(
        namespace="inbox", name="", display_name="Inbox 捕获",
        help="快速捕获想法到 Inbox",
        category="navigation", action_type="screen",
        target="gtd-inbox", handler_name="cmd_tui",
        icon="📥", shortcut="I",
    )
    add(
        namespace="calendar", name="", display_name="日程管理",
        help="月历/周视图/日视图 + 快速添加",
        category="navigation", action_type="screen",
        target="calendar", handler_name="cmd_tui",
        icon="📅", shortcut="C",
    )
    add(
        namespace="inbox", name="add", display_name="快速捕获",
        help="捕获想法到 Inbox",
        category="gtd", action_type="action",
        handler_name="cmd_inbox_add",
        icon="📥",
        args=[CommandArg("text", type="string", required=True, help="捕获内容")],
        flags=[CommandArg("source", type="choice", choices=["cli", "tui", "hook", "stdin"], help="来源")],
    )
    add(
        namespace="inbox", name="list", display_name="查看 Inbox",
        help="列出未处理的 Inbox 项",
        category="gtd", action_type="output",
        handler_name="cmd_inbox_list",
        icon="📋",
        flags=[
            CommandArg("status", type="choice",
                       choices=["unprocessed", "clarified", "archived", "all"], help="状态过滤"),
        ],
    )
    add(
        namespace="inbox", name="process", display_name="处理 Inbox",
        help="处理 Inbox 项为 Action/Project/Reference",
        category="gtd", action_type="action",
        handler_name="cmd_inbox_process",
        icon="✅",
        args=[CommandArg("item_id", type="string", required=True, help="Inbox ID")],
        flags=[CommandArg("type", type="choice", required=True,
                          choices=["action", "project", "reference", "trash"], help="处理结果类型")],
    )
    add(
        namespace="action", name="add", display_name="添加 Action",
        help="添加 GTD 下一步行动",
        category="gtd", action_type="action",
        handler_name="cmd_action_add",
        icon="✅",
        args=[CommandArg("title", type="string", required=True, help="行动标题")],
        flags=[
            CommandArg("priority", type="choice", choices=["P0", "P1", "P2", "P3"], help="优先级"),
            CommandArg("context", type="string", help="场景标签"),
            CommandArg("due", type="string", help="截止日期"),
            CommandArg("energy", type="int", help="能量消耗"),
            CommandArg("project", type="string", help="关联项目"),
        ],
    )
    add(
        namespace="action", name="list", display_name="列出 Actions",
        help="列出 GTD Actions (支持筛选)",
        category="gtd", action_type="output",
        handler_name="cmd_action_list",
        icon="📋",
        flags=[
            CommandArg("status", type="choice",
                       choices=["pending", "next", "done", "all"], help="状态"),
            CommandArg("priority", type="choice", choices=["P0", "P1", "P2", "P3"], help="优先级"),
            CommandArg("next", type="choice", choices=["true", "false"], help="推荐下一步"),
        ],
    )
    add(
        namespace="action", name="done", display_name="完成 Action",
        help="标记 Action 为完成",
        category="gtd", action_type="action",
        handler_name="cmd_action_done",
        icon="🎉",
        args=[CommandArg("action_id", type="string", required=True, help="Action ID")],
    )
    add(
        namespace="project", name="create", display_name="创建 Project",
        help="创建 GTD 项目",
        category="gtd", action_type="action",
        handler_name="cmd_project_create",
        icon="📦",
        args=[CommandArg("name", type="string", required=True, help="项目名称")],
        flags=[
            CommandArg("outcome", type="string", help="期望结果"),
            CommandArg("skill-id", type="string", help="关联技能"),
        ],
    )
    add(
        namespace="project", name="list", display_name="列出 Projects",
        help="列出 GTD 项目",
        category="gtd", action_type="output",
        handler_name="cmd_project_list",
        icon="📋",
        flags=[CommandArg("status", type="choice",
                           choices=["active", "someday", "done", "all"], help="状态")],
    )
    add(
        namespace="project", name="show", display_name="项目详情",
        help="查看 Project 详细信息",
        category="gtd", action_type="output",
        handler_name="cmd_project_show",
        icon="🔍",
        args=[CommandArg("project_id", type="string", required=True, help="Project ID")],
    )
    add(
        namespace="project", name="templates", display_name="项目模板",
        help="浏览预置项目模板",
        category="gtd", action_type="output",
        handler_name="cmd_project_templates",
        icon="📋",
    )
    add(
        namespace="energy", name="status", display_name="能量状态",
        help="查看当前能量池",
        category="gtd", action_type="output",
        handler_name="cmd_energy_status",
        icon="⚡",
    )
    add(
        namespace="energy", name="advise", display_name="能量建议",
        help="能量优化建议 (高效时段/消耗分析)",
        category="gtd", action_type="output",
        handler_name="cmd_energy_advise",
        icon="💡",
    )
    add(
        namespace="calendar", name="today", display_name="今日日程",
        help="查看今日 Calendar",
        category="gtd", action_type="output",
        handler_name="cmd_calendar_today",
        icon="📅",
    )
    add(
        namespace="calendar", name="week", display_name="本周日程",
        help="查看本周 Calendar",
        category="gtd", action_type="output",
        handler_name="cmd_calendar_week",
        icon="📆",
    )
    add(
        namespace="calendar", name="add", display_name="添加日程",
        help="添加 Calendar 事件",
        category="gtd", action_type="action",
        handler_name="cmd_calendar_add",
        icon="➕",
        args=[
            CommandArg("date", type="string", required=True, help="日期 YYYY-MM-DD"),
            CommandArg("title", type="string", required=True, help="日程标题"),
        ],
        flags=[
            CommandArg("time", type="string", help="时间 HH:MM"),
            CommandArg("repeat-rule", type="choice",
                       choices=["daily", "weekly", "monthly"], help="重复规则"),
        ],
    )

    # ── 9U: 技能搜索与发现 ─────────────────────────────

    add(
        namespace="search", name="", display_name="技能搜索",
        help="自然语言搜索技能 (Phase 9U)",
        category="9U", action_type="output",
        handler_name="cmd_search",
        icon="🔍",
        args=[CommandArg("query", type="string", required=True, help="搜索关键词")],
        flags=[
            CommandArg("category", type="choice",
                       choices=["dev", "design", "data", "ops", "writing", "general", "system"],
                       help="按分类过滤"),
            CommandArg("difficulty", type="choice",
                       choices=["beginner", "intermediate", "advanced", "expert"],
                       help="按难度过滤"),
            CommandArg("top-k", type="int", default=10, help="返回数量"),
        ],
    )
    add(
        namespace="discover", name="", display_name="技能推荐",
        help="发现推荐技能 (Phase 9U)",
        category="9U", action_type="output",
        handler_name="cmd_discover",
        icon="💡",
        flags=[
            CommandArg("owned", type="string", help="已有技能 ID（逗号分隔）"),
            CommandArg("top-k", type="int", default=10, help="推荐数量"),
        ],
    )
    add(
        namespace="trending", name="", display_name="热门趋势",
        help="热门趋势技能 (Phase 9U)",
        category="9U", action_type="output",
        handler_name="cmd_trending",
        icon="🔥",
        flags=[CommandArg("top-k", type="int", default=10, help="排行数量")],
    )
    add(
        namespace="path", name="", display_name="学习路径",
        help="推荐学习路径 (Phase 9U)",
        category="9U", action_type="output",
        handler_name="cmd_path",
        icon="🗺️",
        args=[CommandArg("goal", type="string", required=True, help="学习目标")],
        flags=[
            CommandArg("owned", type="string", help="已掌握技能 ID（逗号分隔）"),
            CommandArg("steps", type="int", default=5, help="路径步数"),
        ],
    )

    # ── 9V: 技能质量评级 ─────────────────────────────

    add(
        namespace="rating", name="", display_name="技能评级",
        help="查看技能质量评级 (Phase 9V)",
        category="9V", action_type="output",
        handler_name="cmd_rating",
        icon="📊",
        args=[CommandArg("skill_id", type="string", required=True, help="技能 ID")],
        flags=[CommandArg("refresh", type="string", help="强制重新计算 (--refresh)")],
    )
    add(
        namespace="rate", name="", display_name="给技能打分",
        help="给技能打分 (Phase 9V)",
        category="9V", action_type="action",
        handler_name="cmd_rate",
        icon="⭐",
        args=[
            CommandArg("skill_id", type="string", required=True, help="技能 ID"),
            CommandArg("score", type="string", required=True, help="评分 1-5"),
        ],
        flags=[CommandArg("comment", type="string", help="评价文字")],
    )
    add(
        namespace="ratings", name="list", display_name="评级列表",
        help="列出所有已评级的技能 (Phase 9V)",
        category="9V", action_type="output",
        handler_name="cmd_ratings_list",
        icon="📋",
    )
    add(
        namespace="ratings", name="rate-all", display_name="批量评级",
        help="批量评级所有已知技能 (Phase 9V)",
        category="9V", action_type="output",
        handler_name="cmd_ratings_rate_all",
        icon="🔄",
    )

    return registry


class CommandRegistry:
    """命令注册表管理器"""

    def __init__(self) -> None:
        self._entries = build_command_registry()
        self._by_name: dict[str, CommandEntry] = {}
        for entry in self._entries:
            self._by_name[entry.qualified_name] = entry
        self._recent: list[str] = []

    def all(self) -> list[CommandEntry]:
        return self._entries

    def get(self, qualified_name: str) -> Optional[CommandEntry]:
        return self._by_name.get(qualified_name)

    def by_category(self, category: str) -> list[CommandEntry]:
        return [e for e in self._entries if e.category == category]

    def screen_commands(self) -> list[CommandEntry]:
        return [e for e in self._entries if e.action_type == "screen"]

    def recent(self, n: int = 10) -> list[CommandEntry]:
        result = []
        for name in self._recent[-n:]:
            entry = self._by_name.get(name)
            if entry:
                result.append(entry)
        return result

    def record_usage(self, qualified_name: str) -> None:
        if qualified_name in self._recent:
            self._recent.remove(qualified_name)
        self._recent.append(qualified_name)

    def search(self, query: str) -> list[CommandEntry]:
        """简单文本搜索，用于命令模式"""
        query = query.lower().strip()
        if not query:
            return self._entries
        results = []
        for entry in self._entries:
            text = f"{entry.qualified_name} {entry.display_name} {entry.help}".lower()
            if query in text:
                results.append(entry)
        return results
