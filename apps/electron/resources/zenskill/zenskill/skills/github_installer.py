"""
GitHub 技能安装管线 (Phase E2A-C)

用法:
    from zenskill.skills.github_installer import GitHubSkillInstaller

    installer = GitHubSkillInstaller()
    spec = installer.install("user", "repo")
    # → SkillSpec 已写入 SQLite + skill.toml

管线:
    git clone --depth 1
    → RepoAnalyzer (语言/依赖/CI/许可证)
    → ReadmeToPrompts (agent 提示词)
    → SkillSpec
    → save()
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 已知仓库技能映射 (用于检测知名工具)
KNOWN_REPOS = {
    "prettier/prettier": {"category": "dev", "difficulty": "beginner"},
    "eslint/eslint": {"category": "dev", "difficulty": "intermediate"},
    "vitejs/vite": {"category": "dev", "difficulty": "beginner"},
    "withastro/astro": {"category": "dev", "difficulty": "intermediate"},
    "nestjs/nest": {"category": "dev", "difficulty": "advanced"},
    "microsoft/playwright": {"category": "dev", "difficulty": "intermediate"},
    "grafana/grafana": {"category": "ops", "difficulty": "advanced"},
    "kubernetes/kubernetes": {"category": "ops", "difficulty": "expert"},
    "pandas-dev/pandas": {"category": "data", "difficulty": "intermediate"},
    "numpy/numpy": {"category": "data", "difficulty": "advanced"},
}


# ═══════════════════════════════════════════════════════════════
# E2B: RepoAnalyzer
# ═══════════════════════════════════════════════════════════════

@dataclass
class RepoAnalysis:
    """仓库分析结果"""
    # 语言
    languages: Dict[str, float] = field(default_factory=dict)  # {"Python": 0.6, "TS": 0.3}
    primary_language: str = ""

    # 依赖
    dependencies: List[str] = field(default_factory=list)
    dev_dependencies: List[str] = field(default_factory=list)
    runtime_requires: Dict[str, str] = field(default_factory=dict)

    # 结构
    has_readme: bool = False
    readme_path: str = ""
    readme_preview: str = ""
    has_license: bool = False
    license_type: str = ""
    has_ci: bool = False
    ci_provider: str = ""
    has_tests: bool = False
    test_framework: str = ""

    # 统计
    total_files: int = 0
    total_lines: int = 0
    repo_size_kb: int = 0

    # 元数据
    stars: int = 0
    description: str = ""
    topics: List[str] = field(default_factory=list)


class RepoAnalyzer:
    """仓库结构分析器

    从仓库文件结构中自动提取:
    - 语言比例
    - 依赖 (package.json/pyproject.toml/go.mod/Cargo.toml)
    - README 内容
    - CI/CD 检测
    - 许可证检测
    """

    # 扩展名 → 语言映射
    EXT_TO_LANG = {
        ".py": "Python", ".pyi": "Python",
        ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
        ".ts": "TypeScript", ".tsx": "TypeScript",
        ".jsx": "React", ".vue": "Vue", ".svelte": "Svelte",
        ".rs": "Rust", ".go": "Go", ".java": "Java", ".kt": "Kotlin",
        ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
        ".c": "C", ".h": "C/C++", ".cpp": "C++", ".cc": "C++",
        ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
        ".md": "Markdown", ".mdx": "MDX",
        ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML",
        ".css": "CSS", ".scss": "SCSS", ".less": "Less",
        ".sql": "SQL", ".graphql": "GraphQL",
        ".dockerfile": "Docker", ".tf": "Terraform",
    }

    # 包管理文件
    DEP_FILES = {
        "package.json": "npm",
        "pyproject.toml": "python",
        "requirements.txt": "python",
        "setup.py": "python",
        "go.mod": "go",
        "Cargo.toml": "rust",
        "pom.xml": "maven",
        "build.gradle": "gradle",
        "Gemfile": "ruby",
        "composer.json": "php",
        "CMakeLists.txt": "cmake",
    }

    # CI 检测
    CI_PATHS = [
        (".github/workflows/", "GitHub Actions"),
        (".gitlab-ci.yml", "GitLab CI"),
        ("Jenkinsfile", "Jenkins"),
        (".circleci/", "CircleCI"),
        (".travis.yml", "Travis CI"),
        ("azure-pipelines.yml", "Azure Pipelines"),
    ]

    # 测试目录
    TEST_DIRS = ["tests", "test", "__tests__", "spec", "specs"]
    TEST_FRAMEWORKS = {
        "pytest": ["pytest", "conftest.py"],
        "jest": ["jest.config", "__tests__"],
        "mocha": [".mocharc"],
        "vitest": ["vitest.config"],
        "go test": ["_test.go"],
        "cargo test": ["tests/"],
    }

    def analyze(self, repo_path: str | Path) -> RepoAnalysis:
        """完整分析仓库"""
        repo_path = Path(repo_path)
        analysis = RepoAnalysis()

        self._analyze_languages(repo_path, analysis)
        self._analyze_dependencies(repo_path, analysis)
        self._analyze_readme(repo_path, analysis)
        self._analyze_license(repo_path, analysis)
        self._analyze_ci(repo_path, analysis)
        self._analyze_tests(repo_path, analysis)
        self._count_stats(repo_path, analysis)

        return analysis

    def _analyze_languages(self, path: Path, a: RepoAnalysis) -> None:
        """扩展名统计 → 语言比例"""
        ext_counts: Dict[str, int] = {}
        total = 0

        for f in path.rglob("*"):
            if f.is_file() and not any(p in f.parts for p in (".git", "node_modules", "__pycache__", "target", "dist", "build", ".venv")):
                ext = f.suffix.lower()
                if ext:
                    ext_counts[ext] = ext_counts.get(ext, 0) + 1
                    total += 1

        lang_counts: Dict[str, int] = {}
        for ext, count in ext_counts.items():
            lang = self.EXT_TO_LANG.get(ext, ext)
            lang_counts[lang] = lang_counts.get(lang, 0) + count

        a.total_files = total
        if total > 0:
            a.languages = {k: round(v / total, 3) for k, v in sorted(lang_counts.items(), key=lambda x: -x[1])[:5]}
            a.primary_language = list(a.languages.keys())[0] if a.languages else ""

    def _analyze_dependencies(self, path: Path, a: RepoAnalysis) -> None:
        """提取依赖信息"""
        for dep_file, dep_type in self.DEP_FILES.items():
            fp = path / dep_file
            if not fp.exists():
                continue

            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
                if dep_file == "package.json":
                    data = json.loads(content)
                    deps = data.get("dependencies", {})
                    dev_deps = data.get("devDependencies", {})
                    a.dependencies = list(deps.keys())[:20]
                    a.dev_dependencies = list(dev_deps.keys())[:10]
                    engines = data.get("engines", {})
                    if engines:
                        a.runtime_requires.update(engines)
                elif dep_file == "pyproject.toml":
                    self._parse_python_deps(content, a)
                elif dep_file == "requirements.txt":
                    a.dependencies = [l.strip() for l in content.splitlines() if l.strip() and not l.startswith("#")][:20]
                elif dep_file == "go.mod":
                    for line in content.splitlines():
                        m = re.match(r'\s*require\s+(\S+)\s+(\S+)', line)
                        if m:
                            a.dependencies.append(m.group(1))
                    if any("go " in l for l in content.splitlines()[:5]):
                        m = re.search(r'go\s+(\S+)', content)
                        if m:
                            a.runtime_requires["go"] = m.group(1)
                elif dep_file == "Cargo.toml":
                    in_deps = False
                    for line in content.splitlines():
                        if "[dependencies]" in line:
                            in_deps = True
                            continue
                        if in_deps and line.startswith("["):
                            break
                        if in_deps and "=" in line:
                            dep = line.split("=")[0].strip().strip('"')
                            if dep:
                                a.dependencies.append(dep)
            except Exception as e:
                logger.debug(f"Failed to parse {dep_file}: {e}")

    def _parse_python_deps(self, content: str, a: RepoAnalysis) -> None:
        """解析 pyproject.toml 的 Python 依赖"""
        try:
            import tomllib as tl
        except ImportError:
            try:
                import tomli as tl
            except ImportError:
                return
        try:
            data = tl.loads(content)
            deps = data.get("project", {}).get("dependencies", [])
            a.dependencies = [str(d) for d in deps][:20]
            req = data.get("project", {}).get("requires-python", "")
            if req:
                a.runtime_requires["python"] = req
        except Exception:
            pass

    def _analyze_readme(self, path: Path, a: RepoAnalysis) -> None:
        """查找并预览 README"""
        for name in ("README.md", "README.rst", "README.txt", "README", "readme.md"):
            fp = path / name
            if fp.exists():
                a.has_readme = True
                a.readme_path = str(fp)
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace")
                    a.readme_preview = text[:2000]
                except Exception:
                    pass
                break

    def _analyze_license(self, path: Path, a: RepoAnalysis) -> None:
        """检测许可证"""
        for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "LICENCE"):
            fp = path / name
            if fp.exists():
                a.has_license = True
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace")[:500]
                    a.license_type = self._detect_license(text)
                except Exception:
                    pass
                break

    def _detect_license(self, text: str) -> str:
        """从许可证文本推断类型"""
        text_lower = text.lower()
        patterns = [
            (r"mit\s+license", "MIT"),
            (r"apache\s+license.*version\s+2", "Apache-2.0"),
            (r"gnu\s+general\s+public\s+license.*version\s+3", "GPL-3.0"),
            (r"gnu\s+general\s+public\s+license.*version\s+2", "GPL-2.0"),
            (r"bsd\s+3-clause", "BSD-3-Clause"),
            (r"bsd\s+2-clause", "BSD-2-Clause"),
            (r"mozilla\s+public\s+license", "MPL-2.0"),
            (r"isc\s+license", "ISC"),
            (r"unlicense", "Unlicense"),
        ]
        for pat, name in patterns:
            if re.search(pat, text_lower):
                return name
        return ""

    def _analyze_ci(self, path: Path, a: RepoAnalysis) -> None:
        """检测 CI/CD"""
        for ci_path, ci_name in self.CI_PATHS:
            fp = path / ci_path
            if "/*" in ci_path:
                fp = path / ci_path.rstrip("/*")
                if fp.exists() and fp.is_dir() and any(fp.iterdir()):
                    a.has_ci = True
                    a.ci_provider = ci_name
                    break
            elif fp.exists():
                a.has_ci = True
                a.ci_provider = ci_name
                break

    def _analyze_tests(self, path: Path, a: RepoAnalysis) -> None:
        """检测测试框架"""
        for test_dir in self.TEST_DIRS:
            td = path / test_dir
            if td.exists() and td.is_dir():
                a.has_tests = True
                # 检测框架
                for fw, markers in self.TEST_FRAMEWORKS.items():
                    for marker in markers:
                        mp = path / marker
                        if mp.exists() or any(td.rglob(marker)):
                            a.test_framework = fw
                            break
                    if a.test_framework:
                        break
                break

    def _count_stats(self, path: Path, a: RepoAnalysis) -> None:
        """统计文件数和行数"""
        total_lines = 0
        total_size = 0
        for f in path.rglob("*"):
            if f.is_file() and not any(p in f.parts for p in (".git", "node_modules", "__pycache__", "target", "dist", "build", ".venv")):
                try:
                    total_size += f.stat().st_size
                    lines = len(f.read_text(encoding="utf-8", errors="replace").splitlines())
                    total_lines += lines
                except Exception:
                    pass
        a.total_lines = total_lines
        a.repo_size_kb = total_size // 1024


# ═══════════════════════════════════════════════════════════════
# E2C: ReadmeToPrompts
# ═══════════════════════════════════════════════════════════════

@dataclass
class AgentPrompt:
    """Agent 角色提示词"""
    role: str          # "developer" | "coach" | "architect"
    title: str         # 提示词标题
    content: str       # 系统指令


class ReadmeToPrompts:
    """README → Agent 角色提示词

    按 ## 标题分割段落，关键词匹配指派角色:
    - install/setup/getting → developer
    - usage/example/guide → coach
    - api/reference/architecture → architect
    """

    ROLE_KEYWORDS = {
        "developer": [
            "install", "setup", "getting started", "quick start",
            "building", "contribute", "development", "develop",
            "安装", "构建", "开发",
        ],
        "coach": [
            "usage", "example", "examples", "guide", "tutorial",
            "how to", "walkthrough", "demo",
            "使用", "示例", "教程", "指南",
        ],
        "architect": [
            "api", "architecture", "design", "reference",
            "internals", "advanced", "configuration", "config",
            "架构", "设计", "参考",
        ],
    }

    ROLE_PREFIXES = {
        "developer": (
            "You are an expert developer familiar with this project. "
            "Help users install, configure, and contribute to this codebase. "
            "Provide actionable, tested instructions.\n\n"
        ),
        "coach": (
            "You are a patient coach who helps users learn and use this tool. "
            "Explain concepts clearly with examples. "
            "Focus on practical usage patterns and common workflows.\n\n"
        ),
        "architect": (
            "You are a systems architect who understands the design of this project. "
            "Explain architecture decisions, API design, and internal structure. "
            "Help users understand how components fit together.\n\n"
        ),
    }

    def convert(self, readme_text: str) -> List[AgentPrompt]:
        """转换 README 为 Agent 提示词列表
        
        Returns:
            至少包含一个 coach 提示词
        """
        if not readme_text.strip():
            return []

        prompts: List[AgentPrompt] = []
        sections = self._split_sections(readme_text)

        # 第一段（标题下方）→ 作为 coach 用
        if sections and sections[0][0] == "":
            prompts.append(AgentPrompt(
                role="coach",
                title="Project Overview",
                content=self.ROLE_PREFIXES["coach"] + sections[0][1][:1000],
            ))

        # 按关键词分类各段落
        for heading, body in sections:
            if not heading or not body.strip():
                continue
            role = self._classify_section(heading)
            if role:
                prompts.append(AgentPrompt(
                    role=role,
                    title=heading,
                    content=self.ROLE_PREFIXES[role] + body[:1500],
                ))

        # 确保至少有一个 coach
        if not any(p.role == "coach" for p in prompts):
            # 使用第一个非空段落
            for heading, body in sections:
                if body.strip():
                    prompts.append(AgentPrompt(
                        role="coach",
                        title=heading or "Getting Started",
                        content=self.ROLE_PREFIXES["coach"] + body[:1500],
                    ))
                    break

        return prompts

    def _split_sections(self, text: str) -> List[Tuple[str, str]]:
        """按 ## 标题分割"""
        text = text.replace("\r\n", "\n")
        parts = re.split(r'\n(#{1,3})\s+(.+?)\n', text)

        sections: List[Tuple[str, str]] = []
        # 第一段（标题前）
        if parts and not parts[0].startswith("#"):
            sections.append(("", parts[0].strip()))

        # 后续段落
        i = 1
        while i + 2 < len(parts):
            level = parts[i]
            heading = parts[i + 1]
            body = parts[i + 2] if i + 2 < len(parts) else ""
            sections.append((f"{'#' * len(level)} {heading}", body.strip()))
            i += 3

        return sections

    def _classify_section(self, heading: str) -> Optional[str]:
        """根据标题分类段落"""
        heading_lower = heading.lower().lstrip("#").strip()
        for role, keywords in self.ROLE_KEYWORDS.items():
            for kw in keywords:
                if kw in heading_lower:
                    return role
        return None


# ═══════════════════════════════════════════════════════════════
# E2A: GitHubSkillInstaller
# ═══════════════════════════════════════════════════════════════

class GitHubSkillInstaller:
    """GitHub 技能安装器 — 完整管线

    管线:
    1. git clone --depth 1 到缓存
    2. RepoAnalyzer 分析仓库
    3. ReadmeToPrompts 生成提示词
    4. → SkillSpec
    5. spec.save()
    """

    def __init__(self):
        self._cache_dir = Path.home() / ".zenskill" / "cache" / "github"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._analyzer = RepoAnalyzer()
        self._prompter = ReadmeToPrompts()

    def install(
        self,
        owner: str,
        repo: str,
        version: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """完整安装管线

        Args:
            owner: GitHub 用户名/组织
            repo: 仓库名
            version: git ref (tag/branch/commit)
            force: 强制重新克隆

        Returns:
            {"success": bool, "skill_id": str, "analysis": RepoAnalysis, ...}
        """
        start = time.time()
        full_name = f"{owner}/{repo}"

        try:
            # 1. Clone
            repo_path = self._clone(owner, repo, version, force)
            if not repo_path:
                return {"success": False, "error": f"Clone failed: {full_name}"}

            # 2. Analyze
            analysis = self._analyzer.analyze(repo_path)

            # 3. Readme → Prompts
            prompts = []
            if analysis.has_readme:
                prompts = self._prompter.convert(analysis.readme_preview)

            # 4. → SkillSpec
            spec = self._build_spec(owner, repo, version, analysis, prompts)

            # 5. Save
            if not spec.save():
                return {"success": False, "error": f"Save failed: {spec.id}"}

            elapsed = int((time.time() - start) * 1000)
            logger.info(f"GitHub install complete: {full_name} ({elapsed}ms)")

            return {
                "success": True,
                "skill_id": spec.id,
                "name": spec.name,
                "source": "github",
                "method": "github-clone",
                "analysis": {
                    "primary_language": analysis.primary_language,
                    "has_ci": analysis.has_ci,
                    "has_tests": analysis.has_tests,
                    "total_files": analysis.total_files,
                    "total_lines": analysis.total_lines,
                    "license": analysis.license_type,
                },
                "prompts_count": len(prompts),
                "elapsed_ms": elapsed,
            }
        except Exception as e:
            logger.error(f"GitHub install error: {full_name}: {e}")
            return {"success": False, "error": str(e)}

    def preview(self, owner: str, repo: str, version: Optional[str] = None) -> Dict[str, Any]:
        """预览仓库信息（不安装）"""
        full_name = f"{owner}/{repo}"
        try:
            repo_path = self._clone(owner, repo, version, force=False)
            if not repo_path:
                return {"error": f"Clone failed: {full_name}"}
            analysis = self._analyzer.analyze(repo_path)
            prompts = []
            if analysis.has_readme:
                prompts = self._prompter.convert(analysis.readme_preview)

            return {
                "owner": owner,
                "repo": repo,
                "analysis": {
                    "primary_language": analysis.primary_language,
                    "languages": analysis.languages,
                    "dependencies": analysis.dependencies[:10],
                    "has_ci": analysis.has_ci,
                    "has_tests": analysis.has_tests,
                    "total_files": analysis.total_files,
                    "total_lines": analysis.total_lines,
                    "license": analysis.license_type,
                },
                "readme_preview": analysis.readme_preview[:500],
                "prompts_preview": [{"role": p.role, "title": p.title} for p in prompts[:3]],
            }
        except Exception as e:
            return {"error": str(e)}

    def _clone(
        self, owner: str, repo: str, version: Optional[str], force: bool
    ) -> Optional[Path]:
        """浅克隆到缓存"""
        cache_path = self._cache_dir / f"{owner}_{repo}"

        if cache_path.exists() and not force:
            # 检查是否有效 (有 .git)
            if (cache_path / ".git").exists():
                return cache_path
            # 无效 → 删除重来
            import shutil
            shutil.rmtree(cache_path, ignore_errors=True)

        if cache_path.exists() and force:
            import shutil
            shutil.rmtree(cache_path, ignore_errors=True)

        url = f"https://github.com/{owner}/{repo}.git"
        cmd = ["git", "clone", "--depth", "1"]

        if version:
            cmd += ["--branch", version]

        cmd += [url, str(cache_path)]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                timeout=30,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            if result.returncode == 0:
                return cache_path
            else:
                logger.warning(f"git clone failed: {result.stderr[:200]}")
                return None
        except subprocess.TimeoutExpired:
            logger.warning(f"git clone timeout: {owner}/{repo}")
            return None
        except FileNotFoundError:
            logger.warning("git not available")
            return None

    def _build_spec(
        self,
        owner: str,
        repo: str,
        version: Optional[str],
        analysis: RepoAnalysis,
        prompts: List[AgentPrompt],
    ) -> "SkillSpec":
        """从分析结果构建 SkillSpec"""
        from zenskill.core.skill_spec import SkillSpec, CapabilitySpec
        from zenskill.core.skill_types import SkillType

        full_name = f"{owner}/{repo}"
        known = KNOWN_REPOS.get(full_name.lower(), {})

        # 推断分类
        category = known.get("category", self._infer_category(analysis))
        difficulty = known.get("difficulty", self._infer_difficulty(analysis))

        # 标签
        tags = [repo, analysis.primary_language.lower()] if analysis.primary_language else [repo]
        if analysis.has_ci:
            tags.append("ci-cd")
        if analysis.has_tests:
            tags.append("tested")

        # 运行时要求
        requires = dict(analysis.runtime_requires)

        # 能力: 每个 prompt 角色 → 一个能力
        capabilities = []
        for p in prompts:
            capabilities.append(CapabilitySpec(
                name=f"{repo}_{p.role}",
                description=p.title,
                proficiency=0.7,
                keywords=[repo, p.role] + (analysis.dependencies[:3] if analysis.dependencies else []),
                examples=[f"Help me with {full_name}: {p.title}"],
            ))
        if not capabilities:
            capabilities.append(CapabilitySpec(
                name=repo,
                description=analysis.readme_preview[:100] or f"GitHub repository: {full_name}",
                proficiency=0.5,
                keywords=[repo, owner],
                examples=[f"Tell me about {full_name}"],
            ))

        # 关键概念
        key_concepts = [analysis.primary_language] if analysis.primary_language else []
        if analysis.dependencies:
            key_concepts.extend(analysis.dependencies[:5])

        # 反思提示词
        reflection_prompts = self._generate_reflections(repo, analysis)

        return SkillSpec(
            id=f"github-{owner}-{repo}".lower().replace("/", "-"),
            name=full_name,
            display_name=repo,
            icon="🐙",
            description=analysis.readme_preview[:200] or f"GitHub repository: {full_name}",
            version=version or "main",
            category=category,
            skill_type=self._infer_skill_type(analysis),
            difficulty=difficulty,
            tags=tags,
            author=owner,
            license=analysis.license_type,
            source="github",
            source_market="github",
            source_url=f"https://github.com/{full_name}",
            source_format="git",
            source_ref=version or "HEAD",
            verified=analysis.has_ci,
            tools=list(analysis.dependencies[:10]),
            requires=requires,
            key_concepts=key_concepts,
            reflection_prompts=reflection_prompts,
            adapter="inline",
            entry_point="",
            capabilities=capabilities,
            keywords=[repo, owner] + (analysis.dependencies[:5] if analysis.dependencies else []),
        )

    def _infer_category(self, a: RepoAnalysis) -> str:
        """从主要语言和文件推断分类"""
        lang = a.primary_language.lower()
        if lang in ("python", "rust", "go", "java", "kotlin", "c", "c++"):
            return "dev"
        if lang in ("typescript", "javascript", "react", "vue", "svelte"):
            return "dev"
        if lang in ("sql", "r"):
            return "data"
        if lang in ("dockerfile", "terraform", "shell"):
            return "ops"
        if lang in ("markdown", "mdx"):
            return "writing"
        return "general"

    def _infer_difficulty(self, a: RepoAnalysis) -> str:
        """从规模推断难度"""
        if a.total_files > 500 or a.total_lines > 50000:
            return "expert"
        if a.total_files > 100 or a.total_lines > 10000:
            return "advanced"
        if a.total_files > 30 or a.total_lines > 3000:
            return "intermediate"
        return "beginner"

    def _infer_skill_type(self, a: RepoAnalysis) -> "SkillType":
        """推断技能类型"""
        from zenskill.core.skill_types import SkillType
        if a.primary_language.lower() in ("markdown", "mdx"):
            return SkillType.KNOWLEDGE
        if a.has_ci or a.primary_language.lower() in ("dockerfile", "terraform", "shell"):
            return SkillType.COORDINATION
        return SkillType.EXECUTION

    def _generate_reflections(self, repo: str, a: RepoAnalysis) -> List[str]:
        """生成反思提示词"""
        prompts = [
            f"我今天使用 {repo} 解决了什么问题？",
            f"{repo} 的哪些特性我还不够熟悉？",
        ]
        if a.dependencies:
            prompts.append(f"{repo} 的核心依赖有哪些？它们之间的关系是什么？")
        if a.has_tests:
            prompts.append(f"我是否理解了 {repo} 的测试策略？")
        return prompts


# ── 便捷函数 ──

def install_github_skill(owner: str, repo: str, version: Optional[str] = None) -> Dict[str, Any]:
    """一行安装 GitHub 技能"""
    return GitHubSkillInstaller().install(owner, repo, version)


def preview_github_skill(owner: str, repo: str) -> Dict[str, Any]:
    """预览 GitHub 仓库"""
    return GitHubSkillInstaller().preview(owner, repo)
