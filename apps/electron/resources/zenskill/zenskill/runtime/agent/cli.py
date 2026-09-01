"""`zenskill run --engine agent` 的实现（独立模块，避免 __main__ 继续膨胀）。"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, List

from .agent_loop import AgentLoop, AgentLoopConfig
from .permission_gate import PermissionGate
from .providers import create_stream, resolve_model
from .tools import DEFAULT_SYSTEM_PROMPT, create_default_tools
from .types import (
    AssistantMessage,
    Context,
    MessageEnd,
    MessageUpdate,
    TextDelta,
    ThinkingDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
    TurnStart,
    UserMessage,
    message_to_dict,
    total_usage,
)


def _confirm_prompt(tool_call, params) -> bool:
    detail = ", ".join(f"{k}={str(v)[:50]!r}" for k, v in list(params.items())[:3])
    try:
        answer = input(f"允许执行 {tool_call.name}({detail})? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() in ("y", "yes")


def _runtime_env_block() -> str:
    """运行时环境块：声明工作目录，避免 LLM 浪费轮次探测路径（dogfooding 发现）。"""
    return (
        "\n\n<runtime-env>\n"
        f"Working directory: {os.getcwd()}\n"
        "All relative paths resolve against this directory. Do not search the "
        "filesystem to locate the project root.\n"
        "</runtime-env>"
    )


_SPIN_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_SPIN_INTERVAL = 0.08


class _Spinner:
    """零依赖终端 spinner，用于 LLM 思考等待期间"""

    def __init__(self, label: str = "思考中") -> None:
        self._label = label
        self._frame = 0
        self._active = False
        self._thread = None

    def _run(self) -> None:
        while self._active:
            ch = _SPIN_FRAMES[self._frame % len(_SPIN_FRAMES)]
            sys.stdout.write(f"\r  {ch} {self._label}...")
            sys.stdout.flush()
            self._frame += 1
            time.sleep(_SPIN_INTERVAL)

    def start(self) -> None:
        if self._active:
            return
        self._active = True
        import threading
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._active:
            self._active = False
            sys.stdout.write("\r" + " " * (len(self._label) + 10) + "\r")
            sys.stdout.flush()


def cmd_run_agent(args: Any) -> int:
    try:
        model = resolve_model(getattr(args, "model", None))
    except RuntimeError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2
    max_steps = getattr(args, "max_steps", None) or None
    timeout = getattr(args, "timeout", None) or None
    json_output = bool(getattr(args, "json_output", False))
    permission = getattr(args, "permission", "full") or "full"
    session_id = getattr(args, "session", None)
    continue_session = bool(getattr(args, "continue_session", False))
    fork_entry = getattr(args, "fork_entry", None)
    with_memory = bool(getattr(args, "with_memory", False))
    with_skills = bool(getattr(args, "with_skills", False))
    debug = bool(getattr(args, "debug", False))
    planning = bool(getattr(args, "planning", False))
    graph = bool(getattr(args, "graph", False))
    mcp_server = getattr(args, "mcp_server", None)
    interactive = bool(getattr(args, "interactive", False))
    json_response = bool(getattr(args, "json_response", False))
    images = list(getattr(args, "image", None) or [])
    thinking_level = getattr(args, "thinking_level", None)
    exit_code = asyncio.run(_run_task(
        args.task, model, max_steps, timeout, json_output, permission,
        session_id=session_id, continue_session=continue_session,
        fork_entry=fork_entry, with_memory=with_memory, with_skills=with_skills,
        debug=debug, planning=planning, graph=graph, mcp_server=mcp_server,
        json_response=json_response, images=images,
        thinking_level=thinking_level,
    ))
    # --interactive：任务完成后进入 REPL 继续对话
    if interactive and exit_code == 0 and sys.stdin.isatty():
        exit_code = _enter_repl(model, permission, max_steps, debug, with_memory,
                                with_skills, session_id)
    return exit_code


def _build_capabilities(with_memory: bool, with_skills: bool, cwd: str = "."):
    from .builtin_capabilities import (
        MemoryCapability, ReflectionCapability, SummaryCapability, TaskTypeCapability
    )
    from .capability import CapabilityHost
    from .mcp_capability import format_skills_prompt
    from .project_context import load_project_instructions

    caps = [TaskTypeCapability()]
    if with_memory:
        caps.append(MemoryCapability())
    caps.append(ReflectionCapability())
    caps.append(SummaryCapability())
    host = CapabilityHost(caps)
    # 项目指令（AGENTS.md / ZENSKILL.md / CLAUDE.md）
    instructions = load_project_instructions(cwd)
    if instructions:
        host.add_prompt_section(instructions)
    if with_skills:
        section = format_skills_prompt()
        if section:
            host.add_prompt_section(section)
    return host


def _open_session(session_id, continue_session, fork_entry, task):
    """按 CLI 参数准备会话；返回 (session|None, resume_messages|None)"""
    if not session_id:
        return None, None
    from .session import SessionManager
    manager = SessionManager()
    if continue_session:
        session = manager.load(session_id)
        if fork_entry:
            session.branch_from(fork_entry)
        resume = session.build_context()["messages"]
    else:
        session = manager.create(session_id=session_id)
        resume = []
    task_message = UserMessage(content=task)
    session.append_message(task_message)
    return session, resume + [task_message]


async def _run_task(task: str, model, max_steps, timeout, json_output: bool,
                    permission: str = "full", session_id=None,
                    continue_session=False, fork_entry=None,
                    with_memory=False, with_skills=False, debug=False,
                    planning=False, graph=False, mcp_server=None,
                    json_response=False, images=None,
                    thinking_level=None) -> int:
    tools = create_default_tools(".")

    # MCP server 连接：发现并注册远程工具
    mcp_client = None
    if mcp_server:
        try:
            from ..mcp.client import MCPClient
            mcp_client = MCPClient()
            await mcp_client.connect(mcp_server.split())
            mcp_tools = await mcp_client.list_tools()
            for mt in mcp_tools:
                tools.append(_wrap_mcp_tool(mcp_client, mt))
            if not json_output:
                print(f"MCP: 已连接，发现 {len(mcp_tools)} 个工具")
        except Exception as e:
            print(f"MCP 连接失败: {e}", file=sys.stderr)
            mcp_client = None

    # 自定义工具加载（~/.zenskill/tools/）
    try:
        from .custom_tools import load_custom_tools
        custom = load_custom_tools()
        if custom:
            tools.extend(custom)
            if not json_output:
                print(f"自定义工具: 已加载 {len(custom)} 个")
    except Exception as e:
        if not json_output:
            print(f"自定义工具加载失败: {e}", file=sys.stderr)

    # Skill → Tool 自动发现（~/.agents/skills/）
    try:
        from .skill_tools import load_skill_tools
        skill_tools = load_skill_tools()
        if skill_tools:
            tools.extend(skill_tools)
            if not json_output:
                print(f"Skill 工具: 已加载 {len(skill_tools)} 个")
    except Exception as e:
        if not json_output:
            print(f"Skill 工具加载失败: {e}", file=sys.stderr)

    session, initial_messages = _open_session(session_id, continue_session, fork_entry, task)
    if initial_messages is None:
        initial_messages = [UserMessage(content=task)]

    # --image：附加图片到用户消息（需视觉模型）
    if images:
        image_blocks = []
        for img_path in images:
            block = _load_image_block(img_path)
            if block is None:
                print(f"图片加载失败: {img_path}", file=sys.stderr)
                return 1
            image_blocks.append(block)
        base_msg = initial_messages[-1]
        initial_messages[-1] = UserMessage(
            content=[TextContent(base_msg.text())] + image_blocks,
        )

    host = _build_capabilities(with_memory, with_skills, cwd=".")

    # Graph 模式：分解任务为子任务 DAG 并行执行
    if graph:
        from .graph import AgentGraph, PlannerAgent
        planner = PlannerAgent(create_stream(model), model)
        plan = await planner.plan(task)
        if not json_output:
            print(f"模型: {model.provider}/{model.id}")
            print("-" * 60)
            print(plan.summary())
            print("-" * 60)
        graph_exec = AgentGraph(
            create_stream(model), model,
            lambda: create_default_tools(".") + host.extra_tools,
            system_prompt=host.build_system_prompt(DEFAULT_SYSTEM_PROMPT) + _runtime_env_block(),
        )
        results = await graph_exec.execute(plan)
        if not json_output:
            print()
            for st in plan.subtasks:
                status = "ok" if st.status == "done" else "FAIL"
                print(f"  [{st.id}] {status}: {st.description}")
                if st.result:
                    print(f"       {st.result[:200]}")
            print("-" * 60)
            print(f"子任务: {len(plan.subtasks)} | 完成: {sum(1 for s in plan.subtasks if s.status == 'done')}")
        else:
            import json as _json
            print(_json.dumps({
                "ok": all(s.status == "done" for s in plan.subtasks),
                "plan": plan.summary(),
                "subtasks": [
                    {"id": s.id, "description": s.description, "status": s.status,
                     "result": (s.result or "")[:500]}
                    for s in plan.subtasks
                ],
            }, ensure_ascii=False, indent=2))
        return 0 if all(s.status == "done" for s in plan.subtasks) else 1
    context = Context(
        messages=list(initial_messages),
        system_prompt=host.build_system_prompt(DEFAULT_SYSTEM_PROMPT) + _runtime_env_block(),
        tools=tools + host.extra_tools,
        response_format="json" if json_response else None,
        thinking_level=thinking_level,
    )

    abort_event = asyncio.Event()
    timer_handle = None
    if timeout:
        event_loop = asyncio.get_event_loop()
        timer_handle = event_loop.call_later(timeout, abort_event.set)

    started = time.monotonic()
    stream_fn = create_stream(model)
    host_hooks = host.hooks()
    gate = PermissionGate(
        permission, cwd=os.getcwd(),
        confirm=_confirm_prompt if not json_output else None,
    ) if permission != "full" else None
    if gate is not None:
        host_hooks["before_tool_call"] = gate
    config = AgentLoopConfig(
        stream=stream_fn,
        model=model,
        max_steps=max_steps,
        abort_event=abort_event,
        planning=planning,
        on_entry=session.append_message if session is not None else None,
        **host_hooks,
    )
    loop = AgentLoop(config)

    turns = 0
    had_error = False
    tool_events: List[Dict[str, Any]] = []
    final_texts: List[str] = []
    spinner = _Spinner() if (not json_output and sys.stdout.isatty()) else None
    waiting_for_token = False

    if not json_output:
        print(f"模型: {model.provider}/{model.id}")
        print("-" * 60)

    try:
        async for ev in loop.run(context):
            if isinstance(ev, TurnStart):
                turns += 1
                if not json_output:
                    if turns > 1:
                        print()
                    print(f"--- 第 {turns} 轮 ---")
                waiting_for_token = True
                if spinner:
                    spinner.start()
            elif isinstance(ev, MessageUpdate):
                d = ev.delta
                if isinstance(d, TextDelta) and not json_output:
                    if spinner and waiting_for_token:
                        spinner.stop()
                        waiting_for_token = False
                    sys.stdout.write(d.text)
                    sys.stdout.flush()
                elif isinstance(d, ThinkingDelta) and not json_output:
                    if spinner and waiting_for_token:
                        spinner.stop()
                        waiting_for_token = False
                    sys.stdout.write(f"\033[90m[思考] {d.thinking}\033[0m")
                    sys.stdout.flush()
            elif isinstance(ev, MessageEnd):
                if spinner:
                    spinner.stop()
                    waiting_for_token = False
                if isinstance(ev.message, AssistantMessage):
                    if ev.message.stop_reason in ("error", "aborted"):
                        had_error = True
                        if ev.message.error_message and not json_output:
                            sys.stdout.write(f"\n[错误] {ev.message.error_message}")
                    final_texts.append(ev.message.text())
            elif isinstance(ev, ToolExecutionStart) and not json_output:
                if spinner:
                    spinner.stop()
                    waiting_for_token = False
                short_args = ", ".join(
                    f"{k}={str(v)[:60]!r}" for k, v in list(ev.args.items())[:3]
                )
                sys.stdout.write(f"\n  [工具] {ev.tool_name}({short_args})")
                sys.stdout.flush()
            elif isinstance(ev, ToolExecutionEnd):
                tool_events.append({
                    "tool": ev.tool_name,
                    "is_error": ev.is_error,
                    "text": ev.result.text()[:400],
                })
                if not json_output:
                    status = "失败" if ev.is_error else "完成"
                    raw = ev.result.text().replace("\n", " ").strip()
                    if len(raw) > 200:
                        output = raw[:100] + " ... " + raw[-80:]
                    else:
                        output = raw
                    suffix = f" -> {status}: {output}" if output else f" -> {status}"
                    sys.stdout.write(suffix)
                    sys.stdout.flush()
            elif isinstance(ev, TurnEnd) and debug and not json_output:
                tools_str = ", ".join(ev.tool_names) if ev.tool_names else "(none)"
                print(f"\n  [debug] tokens={ev.turn_tokens} "
                      f"duration={ev.turn_duration_ms}ms tools={tools_str}")
    finally:
        if spinner:
            spinner.stop()
        if timer_handle is not None:
            timer_handle.cancel()

    duration_ms = int((time.monotonic() - started) * 1000)
    totals = total_usage(context.messages)
    timed_out = timeout is not None and duration_ms > timeout * 1000

    try:
        from .stats import SessionStats
        SessionStats().record_run(
            f"{model.provider}/{model.id}",
            session.id if session else None,
            turns, totals,
        )
    except Exception:
        pass

    compaction_done = False
    if session is not None:
        try:
            from .compaction import compact_session
            compaction_done = await compact_session(session, stream_fn, model) is not None
        except Exception as e:
            if not json_output:
                print(f"[会话压缩跳过] {e}")

    exit_code = 1 if (had_error or timed_out) else 0

    if json_output:
        result = {
            "ok": exit_code == 0,
            "model": f"{model.provider}/{model.id}",
            "task": task,
            "turns": turns,
            "duration_ms": duration_ms,
            "timed_out": timed_out,
            "usage": totals.to_dict(),
            "tool_calls": tool_events,
            "session": {"id": session.id, "leaf": session.leaf_id, "compacted": compaction_done} if session else None,
            "messages": [message_to_dict(m, truncate_images=True) for m in context.messages],
            "final_text": "\n".join(t for t in final_texts if t),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print()
        print("-" * 60)
        session_line = f" | 会话: {session.id}" if session else ""
        print(
            f"轮次: {turns} | 工具调用: {len(tool_events)} | "
            f"tokens: {totals.total_tokens} | 耗时: {duration_ms / 1000:.1f}s{session_line}"
        )
        if session is not None:
            print(f"继续: zenskill run \"...\" --engine agent --session {session.id} --continue")
        if timed_out:
            print(f"已达超时上限 {timeout}s，任务被中止")

    return exit_code


def cmd_agent_stats(args: Any) -> int:
    """`zenskill agent-engine stats` 实现"""
    import json as _json

    from .stats import SessionStats

    summary = SessionStats().summary(days=getattr(args, "days", 30) or 30)
    if getattr(args, "json_output", False):
        print(_json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"最近 {summary['days']} 天：运行 {summary['runs']} 次 | "
              f"tokens {summary['total_tokens']} | 成本 ~${summary['cost_usd']}")
        for m in summary["by_model"]:
            print(f"  {m['model']}: {m['runs']} 次 / {m['total_tokens']} tokens / ~${m['cost_usd']}")
    return 0


def cmd_agent_session(args: Any) -> int:
    """`zenskill agent session list|show|tree` 实现"""
    import json as _json

    from .session import SessionManager

    manager = SessionManager()
    action = args.session_action

    if action == "list":
        sessions = manager.list_sessions()
        if getattr(args, "json_output", False):
            print(_json.dumps({"sessions": sessions}, ensure_ascii=False, indent=2))
        elif not sessions:
            print("暂无会话（zenskill run ... --session <id> --engine agent 创建）")
        else:
            for s in sessions:
                print(f"{s['id']}  entries={s['entries']}  cwd={s['cwd']}")
        return 0

    if not args.session_id:
        print("错误: 需要 --session-id", file=sys.stderr)
        return 2
    try:
        session = manager.load(args.session_id)
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2

    if action == "show":
        built = session.build_context()
        payload = {
            "id": session.id,
            "cwd": session.cwd,
            "leaf": session.leaf_id,
            "entries": len(session.entries),
            "message_count": len(built["messages"]),
            "messages": [message_to_dict(m, truncate_images=True) for m in built["messages"]],
        }
        if getattr(args, "json_output", False):
            print(_json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        else:
            for m in built["messages"]:
                role = type(m).__name__.replace("Message", "")
                text = m.text()[:120].replace("\n", " ")
                print(f"[{role}] {text}")
        return 0

    if action == "tree":
        children: Dict[str, List[str]] = {}
        for e in session.entries:
            children.setdefault(e.parent_id or "ROOT", []).append(e.id)
        ids = {e.id: e for e in session.entries}
        on_branch = {e.id for e in session.walk()}

        def render(node_id: str, depth: int = 0) -> None:
            for child in children.get(node_id, []):
                e = ids[child]
                mark = "*" if child in on_branch else " "
                label = e.type
                if e.type == "message":
                    label = f"message:{e.data.get('message', {}).get('role', '?')}"
                print(f"{'  ' * depth}{mark} {child[:13]} {label}")
                render(child, depth + 1)

        print(f"session {session.id} (leaf={session.leaf_id and session.leaf_id[:13]})")
        render("ROOT")
        return 0

    print(f"错误: 未知子命令 {action}", file=sys.stderr)
    return 2


# ═══════════════════════════════════════════════════════════════════
# agent-engine chat — 持续对话 REPL
# ═══════════════════════════════════════════════════════════════════

_SLASH_COMMANDS = {
    "/help": "显示此帮助",
    "/clear": "清空上下文（新会话）",
    "/save": "显式保存会话",
    "/session": "显示当前会话 ID 和消息数",
    "/compact": "手动触发上下文压缩",
    "/exit": "退出（也可用 /quit /q）",
}


def cmd_agent_chat(args: Any) -> int:
    """`zenskill agent-engine chat` — 持续对话 REPL"""
    try:
        model = resolve_model(getattr(args, "model", None))
    except RuntimeError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2

    permission = getattr(args, "permission", "full") or "full"
    max_steps = getattr(args, "max_steps", None) or 10
    debug = bool(getattr(args, "debug", False))
    with_memory = bool(getattr(args, "with_memory", False))
    with_skills = bool(getattr(args, "with_skills", False))
    session_id = getattr(args, "session", None)

    is_tty = sys.stdin.isatty()
    if not is_tty:
        print("[提示] 非交互式终端，输入结束后将自动退出", file=sys.stderr)

    from .builtin_capabilities import MemoryCapability, ReflectionCapability, SummaryCapability, TaskTypeCapability
    from .capability import CapabilityHost
    from .mcp_capability import format_skills_prompt
    from .project_context import load_project_instructions
    from .session import SessionManager

    # 初始化能力
    caps = [TaskTypeCapability()]
    if with_memory:
        caps.append(MemoryCapability())
    caps.append(ReflectionCapability())
    caps.append(SummaryCapability())
    host = CapabilityHost(caps)
    instructions = load_project_instructions(".")
    if instructions:
        host.add_prompt_section(instructions)
    if with_skills:
        section = format_skills_prompt()
        if section:
            host.add_prompt_section(section)

    # 初始化会话
    manager = SessionManager()
    if session_id:
        try:
            session = manager.load(session_id)
        except FileNotFoundError:
            session = manager.create(session_id=session_id)
    else:
        session = manager.create()

    stream_fn = create_stream(model)

    # 打印欢迎信息
    print(f"模型: {model.provider}/{model.id}")
    print(f"会话: {session.id}  (/help 查看命令)")
    print("─" * 50)

    # REPL 主循环
    while True:
        try:
            user_input = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue

        # 斜杠命令
        if user_input.startswith("/"):
            cmd = user_input.split()[0].lower()
            if cmd in ("/exit", "/quit", "/q"):
                print("再见！")
                break
            elif cmd == "/help":
                print("可用命令：")
                for k, v in _SLASH_COMMANDS.items():
                    print(f"  {k:12s} — {v}")
                continue
            elif cmd == "/clear":
                session = manager.create()
                print(f"新会话: {session.id}")
                continue
            elif cmd == "/save":
                print(f"会话已保存: {session.id}")
                continue
            elif cmd == "/session":
                built = session.build_context()
                print(f"会话: {session.id} | 消息: {len(built['messages'])} | leaf: {session.leaf_id}")
                continue
            elif cmd == "/compact":
                try:
                    from .compaction import compact_session
                    result = asyncio.run(compact_session(session, stream_fn, model))
                    if result:
                        print(f"压缩完成: {result.tokens_before} → {result.tokens_after} tokens")
                    else:
                        print("无需压缩（未达阈值）")
                except Exception as e:
                    print(f"压缩失败: {e}")
                continue
            else:
                print(f"未知命令: {cmd}（输入 /help 查看可用命令）")
                continue

        # 正常对话：构造上下文并执行
        context = Context(
            messages=session.build_context()["messages"] + [UserMessage(content=user_input)],
            system_prompt=host.build_system_prompt(DEFAULT_SYSTEM_PROMPT) + _runtime_env_block(),
            tools=create_default_tools(".") + host.extra_tools,
        )
        session.append_message(UserMessage(content=user_input))

        abort_event = asyncio.Event()
        host_hooks = host.hooks()
        if permission != "full":
            host_hooks["before_tool_call"] = PermissionGate(
                permission, cwd=os.getcwd(),
                confirm=_confirm_prompt,
            )

        config = AgentLoopConfig(
            stream=stream_fn,
            model=model,
            max_steps=max_steps,
            abort_event=abort_event,
            on_entry=session.append_message,
            **host_hooks,
        )
        loop = AgentLoop(config)

        try:
            _run_agent_turn(loop, context, debug)
        except KeyboardInterrupt:
            print("\n[中断]")
            abort_event.set()

    return 0


def _run_agent_turn(loop, context, debug=False):
    """同步包装：运行一轮 agent 循环并实时输出"""
    async def _run():
        turn = 0
        async for ev in loop.run(context):
            etype = type(ev).__name__
            if etype == "TurnStart":
                turn += 1
            elif etype == "MessageUpdate":
                d = ev.delta
                dtype = type(d).__name__
                if dtype == "TextDelta":
                    sys.stdout.write(d.text)
                    sys.stdout.flush()
                elif dtype == "ThinkingDelta":
                    sys.stdout.write(f"\033[90m{d.thinking}\033[0m")
                    sys.stdout.flush()
            elif etype == "ToolExecutionStart":
                short_args = ", ".join(
                    f"{k}={str(v)[:40]!r}" for k, v in list(ev.args.items())[:2]
                )
                sys.stdout.write(f"\n  [{ev.tool_name}({short_args})]")
                sys.stdout.flush()
            elif etype == "ToolExecutionEnd":
                status = "失败" if ev.is_error else "完成"
                output = ev.result.text().replace("\n", " ")[:100]
                suffix = f" → {status}: {output}" if output else f" → {status}"
                sys.stdout.write(suffix)
                sys.stdout.flush()
            elif etype == "MessageEnd":
                if isinstance(ev.message, object) and hasattr(ev.message, "stop_reason"):
                    if ev.message.stop_reason in ("error", "aborted"):
                        sys.stdout.write(f"\n[错误] {ev.message.error_message or ev.message.stop_reason}")
                sys.stdout.write("\n")
                sys.stdout.flush()
            elif etype == "AgentEnd":
                if debug:
                    from .types import total_usage
                    totals = total_usage(list(ev.messages) if ev.messages else [])
                    print(f"  [debug] tokens={totals.total_tokens}")
    asyncio.run(_run())


def _wrap_mcp_tool(client, mcp_tool):
    """把 MCP 工具包装为 AgentTool"""
    from .types import AgentTool, AgentToolResult, TextContent

    class _McpTool(AgentTool):
        pass

    tool = _McpTool()
    tool.name = f"mcp__{mcp_tool.name}"
    tool.description = (mcp_tool.description or mcp_tool.name)[:512]
    tool.parameters = mcp_tool.input_schema or {"type": "object", "properties": {}}

    async def _run(tool_call_id, params, on_update=None):
        try:
            result = await client.call_tool(mcp_tool.name, params)
            text = str(result.content) if result.content else ""
            if result.is_error:
                return AgentToolResult(content=[TextContent(text)], is_error=True)
            return AgentToolResult(content=[TextContent(text)])
        except Exception as e:
            return AgentToolResult(content=[TextContent(f"MCP error: {e}")], is_error=True)

    tool.run = _run  # type: ignore[method-assign]
    return tool


def _enter_repl(model, permission, max_steps, debug, with_memory, with_skills, session_id):
    """--interactive 模式：任务完成后进入 REPL 继续对话"""
    from .session import SessionManager

    print("\n── 进入交互模式（/exit 退出）──")

    # 复用 chat REPL 的核心逻辑
    class _ChatArgs:
        pass
    chat_args = _ChatArgs()
    chat_args.model = f"{model.provider}/{model.id}"
    chat_args.permission = permission
    chat_args.max_steps = max_steps
    chat_args.debug = debug
    chat_args.with_memory = with_memory
    chat_args.with_skills = with_skills
    chat_args.session = session_id  # 续接同一会话
    return cmd_agent_chat(chat_args)


def _load_image_block(img_path: str):
    """读取图片文件为 ImageContent block；失败返回 None"""
    from pathlib import Path as _Path
    from .types import ImageContent as _IC

    path = _Path(img_path)
    if not path.is_file():
        return None
    suffix = path.suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        return None
    try:
        if path.stat().st_size > 5 * 1024 * 1024:
            return None
        import base64 as _b64
        data = _b64.b64encode(path.read_bytes()).decode("ascii")
        mime = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp",
        }.get(suffix, "image/png")
        return _IC(data=data, mime_type=mime)
    except Exception:
        return None
