"""CLI 命令模块 — 统一 re-export（迁移兼容层）。

测试应从 zenskill.cli 导入而非 zenskill.__main__。
"""

from zenskill.cli.agent import (
    register_agent_engine_parser,
)

from zenskill.cli.chain import (
    cmd_chain_list,
    cmd_chain_run,
    cmd_chain_show,
    register_chain_parser,
)

from zenskill.cli.collector import (
    cmd_collector_hook,
    cmd_collector_list,
    cmd_collector_pipeline,
    cmd_collector_run,
    cmd_collector_run_all,
    register_collector_parser,
)

from zenskill.cli.config import (
    cmd_config_model,
    cmd_config_set,
    cmd_config_show,
    cmd_model_info,
    cmd_model_list,
    cmd_model_setup,
    cmd_model_switch,
    register_config_parser,
)

from zenskill.cli.context import (
    cmd_context,
    cmd_context_card,
    cmd_context_guide,
    cmd_context_history,
    cmd_context_reset,
    cmd_context_respond,
    cmd_context_stats,
    register_context_parser,
)

from zenskill.cli.data import (
    cmd_data_export,
    cmd_data_paths,
    cmd_data_stats,
    register_data_parser,
)

from zenskill.cli.doctor import (
    cmd_doctor,
    cmd_doctor_diagnostics,
    cmd_doctor_migrate,
    cmd_doctor_repair,
    cmd_doctor_snapshot,
    cmd_doctor_state,
    register_doctor_parser,
)

from zenskill.cli.experiment import (
    cmd_experiment_analyze,
    cmd_experiment_complete,
    cmd_experiment_create,
    cmd_experiment_list,
    cmd_experiment_record,
    register_experiment_parser,
)

from zenskill.cli.goal import (
    cmd_goal_set,
    cmd_goal_status,
    cmd_goal_suggest,
    register_goal_parser,
)

from zenskill.cli.graph import (
    cmd_graph_alerts,
    cmd_graph_combos,
    cmd_graph_conflicts,
    cmd_graph_cross_project,
    cmd_graph_discover,
    cmd_graph_dynamics,
    cmd_graph_influence,
    cmd_graph_innovate,
    cmd_graph_learning_path,
    cmd_graph_lifecycle,
    cmd_graph_orchestrate,
    cmd_graph_overview,
    cmd_graph_query,
    cmd_graph_redundancy,
    cmd_graph_register,
    cmd_graph_related,
    cmd_graph_resources,
    cmd_graph_transfer,
    register_graph_parser,
)

from zenskill.cli.growth import (
    cmd_default_overview,
    cmd_growth_abilities,
    cmd_growth_accelerate,
    cmd_growth_achievements,
    cmd_growth_ceremony,
    cmd_growth_compare,
    cmd_growth_dimensions,
    cmd_growth_errors,
    cmd_growth_export,
    cmd_growth_feedback,
    cmd_growth_habits,
    cmd_growth_insight,
    cmd_growth_milestones,
    cmd_growth_predict,
    cmd_growth_replay,
    cmd_growth_report,
    cmd_growth_status,
    cmd_growth_trend,
    register_growth_parser,
)

from zenskill.cli.hook import (
    cmd_hook_disable,
    cmd_hook_enable,
    cmd_hook_list,
    cmd_hook_status,
    register_hook_parser,
)

from zenskill.cli.insight import (
    cmd_insight_generate,
    cmd_insight_mark_read,
    cmd_insight_unread,
    register_insight_parser,
)

from zenskill.cli.llm import (
    cmd_llm_list,
    cmd_llm_set,
    cmd_llm_show,
    cmd_llm_status,
    cmd_llm_test,
    register_llm_parser,
)

from zenskill.cli.mcp import (
    cmd_mcp_serve,
    register_mcp_parser,
)

from zenskill.cli.memory import (
    cmd_memory_add,
    cmd_memory_cross_index,
    cmd_memory_cross_network,
    cmd_memory_cross_related,
    cmd_memory_cross_remind,
    cmd_memory_cross_search,
    cmd_memory_export,
    cmd_memory_import,
    cmd_memory_list,
    cmd_memory_search,
    cmd_memory_stats,
    register_memory_parser,
)

from zenskill.cli.meta import (
    cmd_meta_biases,
    cmd_meta_implement,
    cmd_meta_report,
    cmd_meta_suggestions,
    register_meta_parser,
)

from zenskill.cli.mirror import (
    cmd_mirror_delete_all,
    cmd_mirror_events,
    cmd_mirror_export,
    cmd_mirror_features,
    cmd_mirror_import,
    cmd_mirror_learn,
    cmd_mirror_predict,
    cmd_mirror_privacy,
    cmd_mirror_privacy_set,
    cmd_mirror_profile,
    cmd_mirror_purge,
    cmd_mirror_scan,
    cmd_mirror_status,
    cmd_mirror_sync_global,
    cmd_mirror_sync_skills,
    cmd_mirror_tips,
    cmd_mirror_workflow,
    register_mirror_parser,
)

from zenskill.cli.notify import (
    cmd_notify,
    cmd_notify_hook,
    register_notify_parser,
)

from zenskill.cli.pages import (
    cmd_pages_sync,
    register_pages_parser,
)

from zenskill.cli.perceive import (
    cmd_perceive,
    cmd_perceive_context,
    register_perceive_parser,
)

from zenskill.cli.profile import (
    cmd_profile_create,
    cmd_profile_delete,
    cmd_profile_info,
    cmd_profile_list,
    cmd_profile_migrate,
    cmd_profile_rename,
    cmd_profile_switch,
    register_profile_parser,
)

from zenskill.cli.reflect import (
    cmd_reflect_consolidate,
    cmd_reflect_insight,
    cmd_reflect_issues,
    cmd_reflect_purify,
    cmd_reflect_store,
    cmd_reflect_trigger,
    register_reflect_parser,
)

from zenskill.cli.serve import (
    cmd_serve,
    register_serve_parser,
)

from zenskill.cli.session import (
    cmd_session,
    cmd_session_briefing,
    register_session_parser,
)

from zenskill.cli.skill import (
    cmd_branch_create,
    cmd_branch_list,
    cmd_history,
    cmd_metrics,
    cmd_rollback,
    cmd_skill_break,
    cmd_skill_curve,
    cmd_skill_define,
    cmd_skill_deps,
    cmd_skill_diff,
    cmd_skill_forget,
    cmd_skill_generate,
    cmd_skill_info,
    cmd_skill_lint,
    cmd_skill_list,
    cmd_skill_optimize,
    cmd_skill_predict,
    cmd_skill_route,
    cmd_skill_slim,
    cmd_skill_status,
    cmd_skill_template,
    cmd_skill_testgen,
    cmd_skill_transfer,
    cmd_snapshot_list,
    cmd_snapshot_restore,
    cmd_snapshot_save,
    cmd_template_info,
    cmd_template_list,
    cmd_template_use,
    cmd_tutor,
    register_skill_parser,
)

from zenskill.cli.task import (
    cmd_task_complete,
    cmd_task_generate,
    cmd_task_recommend,
    cmd_task_status,
    register_task_parser,
)

from zenskill.cli.version import (
    cmd_upgrade_apply,
    cmd_upgrade_check,
    cmd_upgrade_rollback,
    cmd_version_list,
    cmd_version_register,
    register_version_parser,
)

from zenskill.cli.workflow import (
    cmd_workflow_bottlenecks,
    cmd_workflow_optimize,
    cmd_workflow_patterns,
    register_workflow_parser,
)

# __main__.py 兼容 re-export（测试迁移期间）
from zenskill.__main__ import (
    __title__ as _title,
    __version__ as _version,
    generate_reflection_report as _gen_refl,
)

__title__ = _title
__version__ = _version
generate_reflection_report = _gen_refl

# __main__ 未迁移的 cmd_* 兼容 re-export
from zenskill.__main__ import (
    cmd_action_add,
    cmd_action_delete,
    cmd_action_done,
    cmd_action_list,
    cmd_agent_discover,
    cmd_browse,
    cmd_calendar_add,
    cmd_calendar_today,
    cmd_calendar_week,
    cmd_chat,
    cmd_content_from_file,
    cmd_content_from_text,
    cmd_content_from_url,
    cmd_cross_compare,
    cmd_cross_insights,
    cmd_cross_report,
    cmd_db,
    cmd_deploy_skill,
    cmd_discover,
    cmd_eco_dashboard,
    cmd_eco_health,
    cmd_eco_heatmap,
    cmd_energy_advise,
    cmd_energy_status,
    cmd_github_info,
    cmd_gtd_dashboard,
    cmd_gtd_migrate,
    cmd_gtd_weekly_review,
    cmd_health_annual,
    cmd_health_card,
    cmd_health_score,
    cmd_inbox_add,
    cmd_inbox_list,
    cmd_inbox_process,
    cmd_info,
    cmd_install,
    cmd_market_search,
    cmd_package_build,
    cmd_package_export,
    cmd_package_install,
    cmd_package_list,
    cmd_package_rollback,
    cmd_package_validate,
    cmd_path,
    cmd_project_create,
    cmd_project_list,
    cmd_project_show,
    cmd_project_templates,
    cmd_rate,
    cmd_rating,
    cmd_ratings_list,
    cmd_ratings_rate_all,
    cmd_report_monthly,
    cmd_report_weekly,
    cmd_run,
    cmd_search,
    cmd_spec_export,
    cmd_spec_inspect,
    cmd_spec_validate,
    cmd_test_skill,
    cmd_trending,
    cmd_tui,
    cmd_uninstall,
    cmd_zentest,
)

# main 入口兼容 re-export
from zenskill.__main__ import main
from zenskill.__main__ import __version_info__ as _version_info

__version_info__ = _version_info
