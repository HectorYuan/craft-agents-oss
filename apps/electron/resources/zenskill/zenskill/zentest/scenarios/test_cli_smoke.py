"""
Z2 — CLI 烟雾测试

对 zenskill 所有公开子命令执行 --help 和基本调用，
验证每个命令至少返回非空输出、exit code ∈ {0, 1}。
"""

from __future__ import annotations

import pytest

from zenskill.zentest.utils import run_zenskill


# ═══════════════════════════════════════════════════════════════
# Help smoke — 每个子命令 --help
# ═══════════════════════════════════════════════════════════════

HELP_COMMANDS = [
    [],
    ["skill"],
    ["skill", "info"],
    ["skill", "status"],
    ["skill", "list"],
    ["gtd"],
    ["gtd", "dashboard"],
    ["gtd", "stats"],
    ["gtd", "weekly-review"],
    ["gtd", "migrate"],
    ["mirror"],
    ["mirror", "tips"],
    ["mirror", "predict"],
    ["mirror", "profile"],
    ["mirror", "status"],
    ["energy"],
    ["energy", "status"],
    ["energy", "advise"],
    ["calendar"],
    ["calendar", "today"],
    ["calendar", "week"],
    ["calendar", "add"],
    ["report"],
    ["report", "weekly"],
    ["report", "monthly"],
    ["health"],
    ["health", "score"],
    ["health", "card"],
    ["health", "annual"],
    ["inbox"],
    ["inbox", "list"],
    ["action"],
    ["action", "list"],
    ["project"],
    ["project", "list"],
    ["doctor"],
    ["collector"],
    ["collector", "list"],
    ["collector", "run-all"],
    ["info"],
    ["profile"],
    ["config"],
    ["memory"],
    ["context"],
    ["session"],
    ["growth"],
    ["goal"],
    ["task"],
    ["insight"],
    ["llm"],
    ["chat"],
    ["notify"],
    ["hook"],
    ["workflow"],
    ["agent"],
    ["reflect"],
    ["perceive"],
    ["search"],
    ["discover"],
    ["trending"],
    ["rate"],
    ["rating"],
    ["ratings"],
    ["install"],
    ["spec"],
    ["market"],
    ["tui"],
    ["package"],
    ["db"],
    ["graph"],
    ["cross"],
    ["eco"],
    ["data"],
]


@pytest.mark.e2e
@pytest.mark.parametrize("args", HELP_COMMANDS, ids=lambda a: " ".join(a) or "root")
def test_help_smoke(args: list[str]) -> None:
    """每个子命令 --help 应返回 exit_code=0 且有输出"""
    cmd = args + ["--help"]
    exit_code, stdout, stderr = run_zenskill(cmd)
    assert exit_code == 0, f"{' '.join(cmd)} failed: {stderr[:200]}"
    assert len(stdout) > 0, f"{' '.join(cmd)} produced no output"


# ═══════════════════════════════════════════════════════════════
# Quick invocation — 不加 --help，验证可执行
# ═══════════════════════════════════════════════════════════════

@pytest.mark.e2e
def test_root_invocation() -> None:
    """zenskill 不带参数应显示帮助"""
    exit_code, stdout, stderr = run_zenskill([])
    assert exit_code in (0, 1), f"root invocation failed: {stderr[:200]}"
    assert "usage" in stdout.lower() or "Usage" in stdout or stdout, \
        "expected usage info in output"


@pytest.mark.e2e
def test_version_flag() -> None:
    """--version 应返回版本号"""
    exit_code, stdout, stderr = run_zenskill(["--version"])
    assert exit_code == 0, f"--version failed: {stderr[:200]}"
    assert len(stdout.strip()) > 0, "--version produced no output"


@pytest.mark.e2e
def test_skill_info_smoke() -> None:
    """skill info 应运行（exit_code ∈ {0, 1}）"""
    exit_code, stdout, stderr = run_zenskill(["skill", "info"])
    assert exit_code in (0, 1), f"skill info failed: {stderr[:200]}"
    # 有输出即为正常
    assert stdout or "No skills" in stderr, "unexpected empty response"


@pytest.mark.e2e
def test_doctor_smoke() -> None:
    """doctor 诊断命令应可执行"""
    exit_code, stdout, stderr = run_zenskill(["doctor"])
    assert exit_code in (0, 1), f"doctor failed: {stderr[:200]}"


@pytest.mark.e2e
def test_health_score_smoke() -> None:
    """health score 应可执行"""
    exit_code, stdout, stderr = run_zenskill(["health", "score"])
    assert exit_code in (0, 1), f"health score failed: {stderr[:200]}"


# ═══════════════════════════════════════════════════════════════
# Error handling
# ═══════════════════════════════════════════════════════════════

@pytest.mark.e2e
def test_unknown_command() -> None:
    """未知命令应返回错误码"""
    exit_code, stdout, stderr = run_zenskill(["nonexistent_command"])
    assert exit_code != 0, "unknown command should fail"
    # 应有错误提示
    assert "error" in stderr.lower() or "usage" in stdout.lower() or "not found" in stderr.lower(), \
        "expected error message for unknown command"


@pytest.mark.e2e
def test_unknown_subcommand() -> None:
    """已知父命令 + 未知子命令应返回错误"""
    exit_code, stdout, stderr = run_zenskill(["gtd", "nonexistent"])
    assert exit_code != 0, "unknown subcommand should fail"
