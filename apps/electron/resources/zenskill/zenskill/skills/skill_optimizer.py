"""SKILL.md 瘦身与 token 预算 (P2-1)

渐进式披露: 主文件保留触发描述 + 工作流概览，
超长章节整段抽取到 references/ 并在原位留链接。

吸收自 tools/prototype/src/skill_management/skill_optimizer.py 并强化:
- token 预算驱动（tiktoken 可选，缺省 CJK/ASCII 启发式估算）
- 索引重建而非字符串 replace（避免误替换）
- dry-run、文件名清洗、报告结构化
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .frontmatter import dump_skill_md, parse_skill_md

TOKEN_BUDGETS = {"tight": 500, "normal": 2000, "loose": 8000}

_SECTION_RE = re.compile(r"^## (.+)\s*$")
_SLUG_RE = re.compile(r"[^\w\u4e00-\u9fff-]+")

_encoder = None


def estimate_tokens(text: str) -> int:
    """token 估算: tiktoken 可选，缺省 CJK≈1 token/字 + 其余 4 字符/token"""
    global _encoder
    if _encoder is None:
        try:
            import tiktoken

            _encoder = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            _encoder = False
    if _encoder is not False:
        return len(_encoder.encode(text))

    cjk = sum(
        1 for ch in text
        if 0x2E80 <= ord(ch) <= 0x9FFF or 0xFF00 <= ord(ch) <= 0xFFEF
    )
    return cjk + (len(text) - cjk + 3) // 4


@dataclass
class Section:
    title: str
    start: int
    end: int

    @property
    def line_count(self) -> int:
        return self.end - self.start


@dataclass
class OptimizeReport:
    path: str
    dry_run: bool
    original_lines: int
    optimized_lines: int
    original_tokens: int
    optimized_tokens: int
    budget: int
    extracted: List[dict] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.original_lines != self.optimized_lines

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "dry_run": self.dry_run,
            "changed": self.changed,
            "original_lines": self.original_lines,
            "optimized_lines": self.optimized_lines,
            "original_tokens": self.original_tokens,
            "optimized_tokens": self.optimized_tokens,
            "budget": self.budget,
            "extracted": self.extracted,
        }


def _split_sections(body_lines: List[str]) -> List[Tuple[Section, List[str]]]:
    """按 `## ` 切分正文。主标题 `#` 与其前的前言不参与抽取"""
    sections: List[Tuple[Section, List[str]]] = []
    current: Optional[Section] = None
    current_lines: List[str] = []

    for i, line in enumerate(body_lines):
        m = _SECTION_RE.match(line.rstrip("\r"))
        if m:
            if current:
                current.end = i
                sections.append((current, current_lines))
            current = Section(title=m.group(1).strip(), start=i, end=len(body_lines))
            current_lines = [line]
        elif current is not None:
            current_lines.append(line)
    if current:
        current.end = len(body_lines)
        sections.append((current, current_lines))

    return sections


def _slug(title: str, fallback: str) -> str:
    slug = _SLUG_RE.sub("-", title.strip()).strip("-")
    return slug[:60] or fallback


def optimize_skill_md(
    path: Path | str,
    max_tokens: Optional[int] = None,
    budget: Optional[str] = None,
    min_section_lines: int = 50,
    dry_run: bool = False,
) -> OptimizeReport:
    """按 token 预算瘦身 SKILL.md（超预算时把大章节抽到 references/）

    Args:
        path: 技能目录或 SKILL.md 文件
        max_tokens: 正文 token 预算（优先于 budget 档位）
        budget: 档位 tight/normal/loose
        min_section_lines: 低于此行数的章节不抽取
        dry_run: 只生成报告不写盘

    Returns:
        OptimizeReport
    """
    path = Path(path)
    skill_md = path if path.is_file() else path / "SKILL.md"
    skill_dir = skill_md.parent

    if max_tokens is None:
        max_tokens = TOKEN_BUDGETS.get(budget or "normal", TOKEN_BUDGETS["normal"])

    meta, body = parse_skill_md(skill_md)
    body_lines = body.split("\n")
    original_tokens = estimate_tokens(body)

    report = OptimizeReport(
        path=str(skill_dir),
        dry_run=dry_run,
        original_lines=len(body_lines),
        optimized_lines=len(body_lines),
        original_tokens=original_tokens,
        optimized_tokens=original_tokens,
        budget=max_tokens,
    )

    if original_tokens <= max_tokens:
        return report

    sections = _split_sections(body_lines)
    candidates = sorted(
        ((s, lines) for s, lines in sections if s.line_count >= min_section_lines),
        key=lambda pair: pair[0].line_count,
        reverse=True,
    )

    extracted: List[dict] = []
    chosen: Dict[int, Tuple[Section, List[str], str]] = {}

    for section, lines in candidates:
        slug = _slug(section.title, f"section-{len(extracted) + 1}")
        rel_file = f"references/{slug}.md"
        chosen[section.start] = (section, lines, rel_file)
        extracted.append({
            "section": section.title,
            "file": rel_file,
            "lines": section.line_count,
            "content": "\n".join(lines).rstrip("\n") + "\n",
        })

        # 用「保留行 + 替换占位」估算优化后 token
        placeholder_tokens = estimate_tokens(
            "\n".join(
                f"## {s.title}\n\n详见 [{s.title}](references/x.md)。\n"
                for s, _, _ in chosen.values()
            )
        )
        removed_tokens = sum(
            estimate_tokens("\n".join(lines)) for _, lines, _ in chosen.values()
        )
        report.optimized_tokens = original_tokens - removed_tokens + placeholder_tokens
        report.optimized_lines = (
            len(body_lines)
            - sum(s.line_count for s, _, _ in chosen.values())
            + 4 * len(chosen)
        )
        if report.optimized_tokens <= max_tokens:
            break

    report.extracted = [
        {k: v for k, v in item.items() if k != "content"} for item in extracted
    ]

    if dry_run or not extracted:
        return report

    new_body_lines: List[str] = []
    i = 0
    while i < len(body_lines):
        if i in chosen:
            section, _, rel_file = chosen[i]
            new_body_lines += [
                f"## {section.title}",
                "",
                f"详见 [{section.title}]({rel_file})。",
                "",
            ]
            i = section.end
        else:
            new_body_lines.append(body_lines[i])
            i += 1

    references_dir = skill_dir / "references"
    references_dir.mkdir(exist_ok=True)
    for item in extracted:
        (skill_dir / item["file"]).write_text(item["content"], encoding="utf-8")

    dump_skill_md(skill_md, meta, "\n".join(new_body_lines))

    final_meta, final_body = parse_skill_md(skill_md)
    report.optimized_tokens = estimate_tokens(final_body)
    report.optimized_lines = len(final_body.split("\n"))

    return report
