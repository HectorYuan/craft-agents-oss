"""chain 命令组（从 __main__.py 提取）。"""
from __future__ import annotations

import argparse


def cmd_chain_list(args: argparse.Namespace) -> None:
    """列出已保存的技能链"""
    import json
    chains_dir = _runtime_storage_dir() / "chains"
    chains_dir.mkdir(parents=True, exist_ok=True)

    chains = []
    for f in sorted(chains_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            chains.append({
                "chain_id": data.get("chain_id", f.stem),
                "description": data.get("description", ""),
                "steps": len(data.get("steps", {})),
            })
        except Exception:
            continue

    def _text():
        if not chains:
            return "  暂无已保存的技能链\n  使用 'zenskill chain show <file>' 查看链定义"
        lines = ["  已保存的技能链:", ""]
        for c in chains:
            lines.append(f"  • {c['chain_id']} — {c['steps']} 步骤")
            if c["description"]:
                lines.append(f"    {c['description']}")
        return "\n".join(lines)

    cli_output({"chains": chains}, args, text=_text)



def cmd_chain_show(args: argparse.Namespace) -> None:
    """显示技能链定义 (从 JSON 文件加载)"""
    import json
    from pathlib import Path
    from .runtime import SkillChain

    path = Path(args.file)
    if not path.exists():
        path = _runtime_storage_dir() / "chains" / f"{args.file}.json"
    if not path.exists():
        print(f"❌ 链定义文件不存在: {args.file}")
        sys.exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    chain = SkillChain.from_dict(data)
    errors = chain.validate()

    def _text():
        lines = [
            f"  技能链: {chain.chain_id}",
            f"  描述: {chain.description or '(无)'}",
            f"  验证: {'✅ 通过' if not errors else '❌ ' + '; '.join(errors)}",
            "",
            "  执行顺序:",
        ]
        for i, step_id in enumerate(chain.execution_order, 1):
            step = chain.get_step(step_id)
            deps = f" ← {step.depends_on}" if step.depends_on else ""
            lines.append(f"    {i}. [{step_id}] {step.name} ({step.tool_name}){deps}")
        return "\n".join(lines)

    cli_output({"chain": chain.to_dict(), "valid": not errors, "errors": errors},
               args, text=_text)



def cmd_chain_run(args: argparse.Namespace) -> None:
    """执行技能链 (使用内置执行器)"""
    import asyncio
    import json
    from pathlib import Path
    from .runtime import SkillChain, ChainExecutor, BuiltinExecutor

    path = Path(args.file)
    if not path.exists():
        path = _runtime_storage_dir() / "chains" / f"{args.file}.json"
    if not path.exists():
        print(f"❌ 链定义文件不存在: {args.file}")
        sys.exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    chain = SkillChain.from_dict(data)

    async def _run():
        executor = BuiltinExecutor()
        chain_executor = ChainExecutor(executor)
        return await chain_executor.execute(chain)

    result = asyncio.run(_run())

    def _text():
        lines = [
            f"  {result.get_summary()}",
            "",
            "  步骤结果:",
        ]
        for step_id, step_result in result.step_results.items():
            lines.append(f"    [{step_result.status.value}] {step_id} (尝试 {step_result.attempts} 次)")
            if step_result.error:
                lines.append(f"      错误: {step_result.error[:60]}")
        return "\n".join(lines)

    cli_output(result.to_dict(), args, text=_text)



def register_chain_parser(subparsers) -> None:
    """注册 chain 子命令组。"""
    chain_parser = subparsers.add_parser("chain", help="技能链管理 (Phase 12.5)")
    chain_sub = chain_parser.add_subparsers(dest="subcommand", help="技能链操作")
    chain_list_p = chain_sub.add_parser("list", help="列出已保存的技能链")
    chain_list_p.set_defaults(func=cmd_chain_list)
    chain_show_p = chain_sub.add_parser("show", help="显示技能链定义")
    chain_show_p.add_argument("file", help="链定义文件路径或名称")
    chain_show_p.set_defaults(func=cmd_chain_show)
    chain_run_p = chain_sub.add_parser("run", help="执行技能链")
    chain_run_p.add_argument("file", help="链定义文件路径或名称")
    chain_run_p.set_defaults(func=cmd_chain_run)

