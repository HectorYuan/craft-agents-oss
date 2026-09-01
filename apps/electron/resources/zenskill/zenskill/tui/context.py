"""
上下文感知 — 获取当前模型/provider/skill/agent 信息 (Phase T+)

用法:
    from zenskill.tui.context import get_context_info
    ctx = get_context_info()
    # {"model": "Claude Sonnet", "provider": "anthropic", "skill": "zenskill-core", ...}
"""

from __future__ import annotations

from typing import Dict


def get_context_info() -> Dict[str, str]:
    """获取当前运行时上下文信息

    Returns:
        {
            "model": "Claude Sonnet / DeepSeek V4 / ...",
            "provider": "anthropic / openai / hosted / ...",
            "skill": "zenskill-core",
            "profile": "default",
            "backend": "textual / rich / plain",
        }
    """
    ctx = {
        "model": "—",
        "provider": "—",
        "skill": "zenskill-core",
        "profile": "default",
        "backend": "plain",
    }

    # LLM Provider
    try:
        from zenskill.core.llm_provider import get_llm_provider
        provider = get_llm_provider()
        ctx["provider"] = provider.__class__.__name__.replace("LLMProvider", "").replace("Provider", "")
        # Try to get model name
        if hasattr(provider, 'model'):
            ctx["model"] = str(provider.model)
        elif hasattr(provider, 'model_name'):
            ctx["model"] = str(provider.model_name)
    except Exception:
        pass

    # Active skill
    try:
        from zenskill.core.skill_profile import SkillProfile
        p = SkillProfile.load("zenskill-core")
        if p and p.level:
            ctx["skill"] = f"zenskill-core ({p.level})"
    except Exception:
        pass

    # Profile
    import os
    ctx["profile"] = os.environ.get("ZENSKILL_PROFILE", "default")

    # Backend
    try:
        from zenskill.render import detect_backend
        ctx["backend"] = detect_backend()
    except Exception:
        pass

    return ctx
