"""scan 命令（W2）：安全 + 可用性双扫描报告。"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from ..cli_utils import output as cli_output

_RISK_ICON = {"safe": "✅", "warn": "⚠️", "dangerous": "⛔"}
_STATUS_ICON = {"usable": "✅", "degraded": "⚠️", "broken": "⛔"}


def _scan_skill(skill_dir: Path) -> dict:
    from ..skills.security_scanner import scan_directory
    from ..skills.usability_validator import validate_usability

    sec = scan_directory(skill_dir)
    use = validate_usability(skill_dir)
    return {
        "skill_id": sec.skill_id,
        "path": str(skill_dir),
        "security": {
            "risk_level": sec.risk_level,
            "findings": [asdict(f) for f in sec.findings],
            "scanned_files": sec.scanned_files,
            "skipped": sec.skipped,
            "duration_ms": sec.duration_ms,
        },
        "usability": {
            "status": use.status,
            "issues": [asdict(i) for i in use.issues],
            "skipped": use.skipped,
        },
    }


def _skill_text(item: dict) -> str:
    sec, use = item["security"], item["usability"]
    lines = [
        f"  {_RISK_ICON.get(sec['risk_level'], '•')} {item['skill_id']}"
        f" — 安全 {sec['risk_level']} / 可用 {use['status']}"
        f"（findings {len(sec['findings'])}，issues {len(use['issues'])}，"
        f"{sec['duration_ms']}ms）",
    ]
    for f in sec["findings"]:
        lines.append(f"     [{f['severity']}] {f['rule_id']} {f['file']}:{f['line']}"
                     f" {f['message']}")
    for i in use["issues"]:
        lines.append(f"     [{i['level']}] {i['check']} {i['message']}"
                     f"（修复: {i['fix_hint']}）")
    return "\n".join(lines)


def cmd_scan(args: argparse.Namespace) -> None:
    if getattr(args, "all", False):
        skills_root = Path.home() / ".agents" / "skills"
        if not skills_root.is_dir():
            cli_output({"skills": [], "summary": {"count": 0}}, args,
                       text=lambda: "未找到已装技能目录 ~/.agents/skills")
            return
        targets = [d for d in sorted(skills_root.iterdir())
                   if d.is_dir() and not d.name.startswith(".")
                   and (d / "SKILL.md").exists()]
    elif args.path:
        targets = [Path(args.path)]
    else:
        print("请指定扫描目录路径，或 --all 扫描全部已装技能（~/.agents/skills）")
        return

    results = [_scan_skill(t) for t in targets]
    risk_summary = {r: sum(1 for x in results if x["security"]["risk_level"] == r)
                    for r in ("safe", "warn", "dangerous")}
    status_summary = {s: sum(1 for x in results if x["usability"]["status"] == s)
                      for s in ("usable", "degraded", "broken")}

    def _text():
        out = ["🔍 ZenSkill 双扫描报告（安全 + 可用性）", "=" * 62, ""]
        if not results:
            out.append("  无可扫描技能")
        out.extend(_skill_text(x) for x in results)
        out += ["", "─" * 62,
                f"  安全: {risk_summary['dangerous']} dangerous / "
                f"{risk_summary['warn']} warn / {risk_summary['safe']} safe    "
                f"可用: {status_summary['broken']} broken / "
                f"{status_summary['degraded']} degraded / "
                f"{status_summary['usable']} usable",
                "  提示: dangerous 拒绝安装（--force 走确认流）；broken 建议拒装；"
                "degraded 安装后按 fix_hint 补全"]
        return "\n".join(out)

    cli_output({
        "skills": results,
        "summary": {"risk": risk_summary, "usability": status_summary,
                    "count": len(results)},
    }, args, text=_text)


def register_scan_parser(subparsers) -> None:
    scan_parser = subparsers.add_parser(
        "scan", help="安全+可用性双扫描（W2：本地技能或目录）")
    scan_parser.add_argument("path", nargs="?", help="技能目录路径")
    scan_parser.add_argument("--all", action="store_true",
                             help="扫描全部已装技能（~/.agents/skills）")
    scan_parser.add_argument("--json", dest="json_output", action="store_true",
                             help="JSON 输出")
    scan_parser.set_defaults(func=cmd_scan)
