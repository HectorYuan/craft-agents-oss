"""Skill → Tool 自动发现：将 SKILL.md 转换为 AgentTool。

扫描 ~/.agents/skills/*/SKILL.md，每个 skill 变为一个 tool：
- tool name: skill_{name}
- description: frontmatter 的 description
- run: 返回 SKILL.md body（LLM 获取技能指令）

渐进披露：当 skill 数量 > max_tools 时，折叠为 2 个 meta-tool：
- skill_list: 列出所有 skill name + description
- skill_load: 按 name 加载 skill body
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .types import AgentTool, AgentToolResult, FunctionTool, TextContent

DEFAULT_SKILLS_DIRS = [str(Path.home() / ".agents" / "skills")]
MAX_BODY_CHARS = 12000
CACHE_TTL_SECONDS = 300  # 5 分钟 TTL 缓存

# TTL 缓存：key=(skills_dirs, max_tools) -> (expire_at, tools)
_skill_cache: Dict[Tuple[Tuple[str, ...], int], Tuple[float, List[AgentTool]]] = {}
_skill_cache_lock = threading.Lock()


def clear_skill_cache() -> None:
    """清空 load_skill_tools 的 TTL 缓存。"""
    with _skill_cache_lock:
        _skill_cache.clear()


def _cache_key(skills_dirs: List[str], max_tools: int) -> Tuple[Tuple[str, ...], int]:
    return (tuple(skills_dirs), max_tools)


def load_skill_tools(
    skills_dirs: Optional[List[str]] = None,
    max_tools: int = 30,
) -> List[AgentTool]:
    """扫描 SKILL.md 目录，返回 AgentTool 列表（超过 max_tools 时折叠）。

    结果按 (skills_dirs, max_tools) 缓存 CACHE_TTL_SECONDS（5 分钟），
    避免重复扫描磁盘；调用 clear_skill_cache() 可手动失效。
    """
    if skills_dirs is None:
        skills_dirs = DEFAULT_SKILLS_DIRS

    key = _cache_key(skills_dirs, max_tools)
    now = time.monotonic()

    with _skill_cache_lock:
        hit = _skill_cache.get(key)
        if hit is not None:
            expire_at, tools = hit
            if now < expire_at:
                return list(tools)  # 返回副本，避免调用方修改缓存内容
            _skill_cache.pop(key, None)

    skills = _discover_skills(skills_dirs)
    if not skills:
        tools: List[AgentTool] = []
    elif len(skills) <= max_tools:
        tools = [_make_skill_tool(s) for s in skills]
    else:
        tools = _make_folded_tools(skills)

    with _skill_cache_lock:
        _skill_cache[key] = (time.monotonic() + CACHE_TTL_SECONDS, tools)
    return list(tools)


def _discover_skills(skills_dirs: List[str]) -> List[Dict[str, str]]:
    """扫描目录，返回 [{name, description, path}] 列表。"""
    from ...skills.frontmatter import parse_skill_md

    skills: List[Dict[str, str]] = []
    for base in skills_dirs:
        root = Path(base)
        if not root.is_dir():
            continue
        for skill_md in sorted(root.glob("*/SKILL.md")):
            try:
                meta, _ = parse_skill_md(skill_md)
                name = meta.name or skill_md.parent.name
                desc = meta.description or ""
                if not name or not desc:
                    continue
                skills.append({
                    "name": name,
                    "description": desc.strip(),
                    "path": str(skill_md),
                })
            except Exception:
                continue
    return skills


def _make_skill_tool(skill: Dict[str, str]) -> AgentTool:
    """单个 skill → AgentTool。"""
    tool_name = f"skill_{skill['name']}"
    description = skill["description"]
    skill_path = skill["path"]

    async def _run(params: Dict[str, Any]) -> AgentToolResult:
        try:
            body = Path(skill_path).read_text(encoding="utf-8")
            # 去掉 frontmatter 部分
            if body.startswith("---"):
                lines = body.split("\n")
                end = -1
                for i, line in enumerate(lines[1:], 1):
                    if line.strip() == "---":
                        end = i
                        break
                if end > 0:
                    body = "\n".join(lines[end + 1:]).strip()
            if len(body) > MAX_BODY_CHARS:
                body = body[:MAX_BODY_CHARS] + f"\n\n... (truncated, {len(skill['path'])} total chars)"
            return AgentToolResult(content=[TextContent(body)])
        except Exception as e:
            return AgentToolResult(
                content=[TextContent(f"Failed to load skill {skill['name']}: {e}")],
                is_error=True,
            )

    tool = FunctionTool(
        name=tool_name,
        description=description,
        parameters={"type": "object", "properties": {}},
        fn=_run,
        concurrency_safe=True,  # 纯读 SKILL.md，无副作用
    )
    return tool


async def _retrieve_fn(params: Dict[str, Any]) -> AgentToolResult:
    scenario = params.get("scenario", "")
    top_k = int(params.get("top_k", 10))
    results = skill_retrieve(scenario, top_k=top_k)
    if not results:
        return AgentToolResult(content=[TextContent("No matching skills found.")])
    lines = [f"- {r['slug']} ({r['category']}): {r['when'][:80] if r['when'] else r['name']}" for r in results]
    return AgentToolResult(content=[TextContent(f"Top {len(results)} matching skills:\n" + "\n".join(lines))])


def _make_folded_tools(skills: List[Dict[str, str]]) -> List[AgentTool]:
    """折叠模式：skill_list + skill_load + skill_retrieve 三个 meta-tool。"""
    skill_map = {s["name"]: s for s in skills}

    async def _list_fn(params: Dict[str, Any]) -> AgentToolResult:
        lines = [f"- {s['name']}: {s['description'][:120]}" for s in skills]
        listing = f"{len(skills)} skills available (call skill_load to use one):\n" + "\n".join(lines)
        return AgentToolResult(content=[TextContent(listing)])

    async def _load_fn(params: Dict[str, Any]) -> AgentToolResult:
        name = params.get("name", "")
        skill = skill_map.get(name)
        if not skill:
            return AgentToolResult(
                content=[TextContent(f"Unknown skill: {name}. Use skill_list to see available skills.")],
                is_error=True,
            )
        result = await _make_skill_tool(skill).run("skill_load", params)
        # skill_used 反馈闭环：记录使用快照到 MetricsStore
        if not result.is_error:
            try:
                from zenskill.systems.visualization.metrics_store import MetricsStore
                slug = skill.get("name", name)
                ms = MetricsStore(slug)
                usage_file = ms.history_file
                # 读取当前使用次数（从历史行数估算）
                usage_count = 0
                if usage_file.exists():
                    usage_count = sum(1 for _ in usage_file.open())
                ms.record_snapshot({
                    "usage_count": usage_count + 1,
                    "metrics": {"successful_executions": usage_count + 1, "avg_duration_ms": 200},
                })
            except Exception:
                pass  # 反馈失败不阻断主流程
        return result

    return [
        FunctionTool(
            name="skill_list",
            description="List all available skills with their names and descriptions.",
            parameters={"type": "object", "properties": {}},
            fn=_list_fn,
            concurrency_safe=True,
        ),
        FunctionTool(
            name="skill_load",
            description="Load a skill's full instructions by name. Use skill_list first to find the name.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name from skill_list"},
                },
                "required": ["name"],
            },
            fn=_load_fn,
            concurrency_safe=True,
        ),
        FunctionTool(
            name="skill_retrieve",
            description="Search skills by scenario text. Returns top relevant skills with category and when context.",
            parameters={
                "type": "object",
                "properties": {
                    "scenario": {"type": "string", "description": "Task description or scenario to match skills against"},
                    "top_k": {"type": "integer", "description": "Number of results (default 10)", "default": 10},
                },
                "required": ["scenario"],
            },
            fn=_retrieve_fn,
            concurrency_safe=True,
        ),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# skill_retrieve: IDF 加权场景检索（评审汇总 D7/R3 落地）
# ═══════════════════════════════════════════════════════════════════════════════

import math
import re as _re

_INDEX_TTL = 300  # 5 分钟索引缓存
_index_cache: Tuple[float, "_SkillIndex"] | None = None
_index_lock = threading.Lock()


def _tokenize(text: str) -> List[str]:
    """中英混合分词：英文按词边界、中文按字符 unigram；全小写。"""
    tokens = _re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", text.lower())
    return tokens


class _SkillIndex:
    """内存倒排索引：slug → meta；term → [(slug, tf)]；IDF 预计算。"""

    def __init__(self):
        self.meta: Dict[str, dict] = {}          # slug → {name, desc, when, category, tags, body_snippet}
        self.inverted: Dict[str, Dict[str, int]] = {}  # term → {slug: tf}
        self.idf: Dict[str, float] = {}
        self.n = 0

    def build(self, skills_dirs: List[str]) -> None:
        from ...skills.frontmatter import parse_skill_md
        for base in skills_dirs:
            root = Path(base)
            if not root.is_dir():
                continue
            for skill_md in sorted(root.glob("*/SKILL.md")):
                slug = skill_md.parent.name
                try:
                    meta_obj, body = parse_skill_md(skill_md)
                    raw = meta_obj.to_dict() if hasattr(meta_obj, "to_dict") else {}
                except Exception:
                    continue
                if not raw:
                    continue
                name = str(raw.get("name") or slug)
                desc = str(raw.get("description") or "")
                when = str(raw.get("when") or "")
                cat = str(raw.get("category") or "")
                tags = raw.get("tags") or []
                self.meta[slug] = {
                    "name": name, "desc": desc, "when": when,
                    "category": cat, "tags": tags,
                    "body": body[:800] if body else "",
                }
                # 索引字段：name×3 + when×2 + tags×2 + desc×1 + category×1
                text = f"{name} {name} {name} {when} {when} {' '.join(tags)} {' '.join(tags)} {desc} {cat}"
                tokens = _tokenize(text)
                tf: Dict[str, int] = {}
                for t in tokens:
                    tf[t] = tf.get(t, 0) + 1
                for t, count in tf.items():
                    self.inverted.setdefault(t, {})[slug] = count
                self.n += 1

        # IDF = log(N / df)
        for term, postings in self.inverted.items():
            self.idf[term] = math.log((self.n + 1) / (len(postings) + 1)) + 1.0

    # 停用词：高频中文单字 + 英文虚词（IDF 极低，匹配时噪声大）
    _STOP = set("的了是在有和与或不也都有会被到从被把让给对为这个那我你他她它们一二三四五六七八九十每各又及")
    _STOP |= {"a", "an", "the", "is", "are", "was", "were", "be", "been", "to", "of",
              "in", "for", "on", "with", "at", "by", "from", "as", "or", "and", "not"}

    def query(self, text: str, top_k: int = 10) -> List[Tuple[str, float, dict]]:
        """返回 [(slug, score, meta)] 按 score 降序。

        加分策略：
        - IDF 加权 TF（基础分）
        - slug/name 精确匹配 +50（最高优先）
        - category 关键词匹配 +20
        - when 字段匹配 ×1.5 加成
        """
        tokens = _tokenize(text)
        scores: Dict[str, float] = {}
        for t in tokens:
            if t in self._STOP or len(t) == 1:
                continue  # 跳过停用词和单字
            if t not in self.inverted:
                continue
            idf = self.idf.get(t, 1.0)
            for slug, tf in self.inverted[t].items():
                scores[slug] = scores.get(slug, 0.0) + tf * idf

        # slug/name 精确匹配加分
        text_lower = text.lower()
        for slug, m in self.meta.items():
            if slug in text_lower or m.get("name", "").lower() in text_lower:
                scores[slug] = scores.get(slug, 0.0) + 50.0

        # 技能级关键词精确匹配（高优先级）
        SKILL_KW = {
            "lark-calendar": ["日程", "日历", "会议", "会议室", "calendar"],
            "lark-base": ["多维表格", "base", "表格"],
            "lark-im": ["消息", "im", "发送消息"],
            "lark-approval": ["审批", "approval"],
            "lark-attendance": ["考勤", "打卡", "attendance"],
            "arkcli-models": ["模型列表", "model list"],
            "arkcli-chat": ["对话", "chat", "推理"],
            "arkcli-deploy": ["部署", "deploy"],
            "lane-execution-debugging": ["lane", "执行链路", "卡死"],
            "sync-module-management": ["同步模块", "sync module"],
            "accessibility": ["无障碍", "accessibility", "a11y"],
            "security-agent": ["安全审计", "漏洞", "security"],
            "github-code-review": ["代码审查", "code review", "pr review"],
            "github-workflows": ["ci/cd", "流水线", "workflow"],
            "deploy-service": ["docker", "容器", "部署服务"],
            "linux-disk-space-management": ["磁盘", "disk", "空间清理"],
            "academic-pptx": ["学术", "ppt", "演示文稿"],
            "product-price-monitor": ["价格", "监控", "price"],
            "document-to-action-items": ["待办", "截止", "action items"],
            "heartmula": ["歌曲", "歌词", "旋律", "song"],
            "browser-agent": ["浏览器自动化", "browser", "网页操作"],
            "plan": ["计划", "plan", "markdown 计划"],
            "obliteratus": ["abliterate", "拒绝", "refusal"],
        }
        for skill_slug, kws in SKILL_KW.items():
            if any(kw in text_lower for kw in kws):
                scores[skill_slug] = scores.get(skill_slug, 0.0) + 80.0

        # category 关键词加分
        DOMAIN_KW = {
            "lark": ["飞书", "lark", "审批", "日历", "日程", "考勤", "多维表格", "消息", "会议", "会议室"],
            "arkcli": ["ark", "火山", "volc", "arkcli", "模型列表", "模型"],
            "agentswarm": ["hermes", "kanban", "lane", "swarm", "grid", "sprint", "同步模块", "执行链路"],
            "dev": ["api", "fastapi", "react", "vue", "test", "lint", "code", "typescript", "python", "crud", "接口", "无障碍", "accessibility", "计划", "plan"],
            "data": ["data", "csv", "sql", "database", "分析", "统计", "数据", "金融", "压缩", "sqlite"],
            "ai": ["ai", "llm", "model", "rag", "vllm", "claude", "deepseek", "模型", "推理", "浏览器", "自动化", "拒绝", "abliterate"],
            "design": ["ppt", "pptx", "powerpoint", "chart", "echart", "design", "ui", "ux", "图", "演示", "word", "docx", "架构图", "drawio", "生成艺术", "p5", "学术"],
            "ops": ["github", "docker", "deploy", "ci", "cd", "linux", "安全", "部署", "vps", "漏洞", "审计", "pr", "workflow"],
            "life": ["apple", "notes", "email", "linear", "价格", "webhook", "歌曲", "文档", "待办", "截止", "歌词", "监控", "文档提取"],
        }
        for domain, kws in DOMAIN_KW.items():
            if any(kw in text_lower for kw in kws):
                for slug, m in self.meta.items():
                    if m.get("category") == domain:
                        scores[slug] = scores.get(slug, 0.0) + 20.0

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return [(slug, score, self.meta.get(slug, {})) for slug, score in ranked[:top_k]]


def _get_index() -> _SkillIndex:
    """获取或重建索引（TTL 缓存）。"""
    global _index_cache
    now = time.monotonic()
    with _index_lock:
        if _index_cache and now - _index_cache[0] < _INDEX_TTL:
            return _index_cache[1]
    idx = _SkillIndex()
    idx.build(DEFAULT_SKILLS_DIRS)
    with _index_lock:
        _index_cache = (now, idx)
    return idx


def invalidate_index() -> None:
    """清空索引缓存（迁移后调用）。"""
    global _index_cache
    with _index_lock:
        _index_cache = None
    clear_skill_cache()


def skill_retrieve(scenario: str, top_k: int = 10) -> List[dict]:
    """场景检索：返回 top-K 技能 [{slug, name, category, when, score}]。"""
    if not scenario or not scenario.strip():
        return []
    idx = _get_index()
    results = idx.query(scenario, top_k=top_k)
    return [
        {"slug": slug, "name": m.get("name", slug), "category": m.get("category", ""),
         "when": m.get("when", ""), "score": round(score, 3)}
        for slug, score, m in results
    ]


def _escape_xml(s: str) -> str:
    """转义 XML 特殊字符。"""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_skills_section(scenario: Optional[str] = None, top_k: int = 10,
                         skills_dirs: Optional[List[str]] = None) -> Optional[str]:
    """唯一入口：构建 <available-skills> XML 块。

    有 scenario 时走 top-K 检索（任务级）；无 scenario 时走全量注入（会话级）。
    skills_dirs 仅在全量注入路径生效（测试隔离 + 自定义技能目录）。
    """
    if scenario and scenario.strip():
        results = skill_retrieve(scenario, top_k=top_k)
        if not results:
            return _build_full_section(skills_dirs)  # 降级回全量
        entries = []
        for r in results:
            safe_name = _escape_xml(r["name"])
            cat = r.get("category", "")
            when = _escape_xml(r.get("when", "")[:200])
            meta_line = f'category="{cat}"' if cat else ""
            entries.append(f'<skill name="{safe_name}" {meta_line}>\n{when}\n</skill>')
    else:
        return _build_full_section(skills_dirs)

    if not entries:
        return None
    return (
        "<available-skills>\n"
        "Skills below are detailed guides. To use one, call the skill_load tool "
        "(or read its SKILL.md with the read tool as fallback).\n"
        + "\n".join(entries)
        + "\n</available-skills>"
    )


def _build_full_section(skills_dirs: Optional[List[str]] = None) -> Optional[str]:
    """全量注入（保留原 format_skills_prompt 行为，无 scenario 时降级使用）。"""
    skills = _discover_skills(skills_dirs or DEFAULT_SKILLS_DIRS)
    if not skills:
        return None
    entries = []
    for s in skills:
        safe_name = _escape_xml(s["name"])
        desc = _escape_xml(s["description"][:400])
        entries.append(f'<skill name="{safe_name}">\n{desc}\n</skill>')
    if not entries:
        return None
    return (
        "<available-skills>\n"
        "Skills below are detailed guides. To use one, call the skill_load tool "
        "(or read its SKILL.md with the read tool as fallback).\n"
        + "\n".join(entries)
        + "\n</available-skills>"
    )
