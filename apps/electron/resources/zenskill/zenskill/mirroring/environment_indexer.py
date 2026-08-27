"""
环境索引器 - Claude Code 环境自动采集

自动扫描 .claude/ 配置、项目技术栈、Git 历史等，
构建完整的用户工作环境画像。
"""

import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .event_collector import EventCollector
from .models import EventType


class EnvironmentIndexer:
    """Claude Code 环境索引器"""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path.cwd()
        self.event_collector = EventCollector()
        self._claude_dir = self.project_root / ".claude"

    def scan_all(self) -> Dict[str, Any]:
        """执行完整扫描"""
        result = {
            "scanned_at": datetime.now().isoformat(),
            "project_root": str(self.project_root),
            "claude_settings": self._scan_claude_settings(),
            "skills": self._scan_installed_skills(),
            "project_stack": self._detect_project_stack(),
            "git_profile": self._scan_git_profile(),
            "editor_config": self._scan_editor_config(),
        }

        # 记录扫描事件
        self.event_collector.record(
            event_type=EventType.SESSION_START,
            skill_id="zenskill-core",
            action="environment_scan",
            context={
                "skills_count": len(result["skills"].get("installed", [])),
                "languages": result["project_stack"].get("languages", []),
            },
        )

        return result

    # === Claude Settings ===

    def _scan_claude_settings(self) -> Dict[str, Any]:
        """扫描 .claude/settings.json"""
        settings = {
            "exists": False,
            "hooks": [],
            "custom_settings": {},
        }

        settings_file = self._claude_dir / "settings.json"
        if settings_file.exists():
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                settings["exists"] = True
                settings["hooks"] = list(data.get("hooks", {}).keys())
                settings["custom_settings"] = {
                    k: v for k, v in data.items()
                    if k not in ("hooks", "memory")
                }
            except Exception:
                pass

        # 扫描 memory 目录
        memory_dir = self._claude_dir / "memory"
        if memory_dir.exists():
            settings["memory_files"] = [
                f.name for f in memory_dir.glob("*.md")
            ]

        # 扫描 plans 目录
        plans_dir = self._claude_dir / "plans"
        if plans_dir.exists():
            settings["plans_count"] = len(list(plans_dir.glob("*.md")))

        return settings

    # === 已安装技能 ===

    def _scan_installed_skills(self) -> Dict[str, Any]:
        """扫描 .claude/skills/ 并分析使用数据"""
        result = {
            "installed": [],
            "enabled": [],
            "usage_stats": self._calculate_skill_usage(),
        }

        skills_dir = self._claude_dir / "skills"
        if not skills_dir.exists():
            return result

        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_info = {
                "name": skill_dir.name,
                "has_skill_md": (skill_dir / "skill.md").exists(),
                "has_py": len(list(skill_dir.glob("*.py"))) > 0,
                "file_count": len(list(skill_dir.iterdir())),
            }

            # 尝试读取 skill.md 并提取元数据
            skill_md = skill_dir / "skill.md"
            if skill_md.exists():
                try:
                    content = skill_md.read_text(encoding="utf-8", errors="ignore")
                    skill_info["preview"] = content[:300].strip()
                    # 提取 hook 配置
                    skill_info["has_hooks"] = "hook" in content.lower()
                    # 提取能力关键词
                    keywords = ["agent", "tool", "prompt", "workflow", "auto", "suggest"]
                    skill_info["capabilities"] = [k for k in keywords if k in content.lower()]
                except Exception:
                    pass

            result["installed"].append(skill_info)

        return result

    def _calculate_skill_usage(self) -> Dict[str, Any]:
        """从事件记录计算技能使用统计"""
        try:
            events = self.event_collector.query(limit=100)

            # 按技能统计
            skill_counts: Counter = Counter()
            tool_counts: Counter = Counter()
            category_counts: Counter = Counter()

            for e in events:
                if e.skill_id:
                    skill_counts[e.skill_id] += 1
                ctx = e.context or {}
                if isinstance(ctx, dict):
                    tool = ctx.get("tool")
                    if tool:
                        tool_counts[tool] += 1
                    category = ctx.get("category")
                    if category:
                        category_counts[category] += 1

            return {
                "total_events": len(events),
                "by_skill": dict(skill_counts),
                "by_tool": dict(tool_counts),
                "by_category": dict(category_counts),
                "primary_tool": tool_counts.most_common(1)[0][0] if tool_counts else None,
            }
        except Exception:
            return {"total_events": 0, "by_skill": {}, "by_tool": {}, "by_category": {}}

    def sync_claude_skills_to_zenskill(self) -> Dict[str, Any]:
        """
        将 Claude Code 已安装的技能同步到 ZenSkill

        这实现了从 Claude Code 生态到 ZenSkill 生态的数据桥接
        """
        scan = self.scan_all()
        skills = scan["skills"]
        usage = skills["usage_stats"]

        # 为每个已安装技能创建 ZenSkill 画像
        synchronized = []
        for skill in skills["installed"]:
            skill_id = skill["name"]
            usage_count = usage["by_skill"].get(skill_id, 0)

            skill_profile = {
                "skill_id": f"claude.{skill_id}",
                "source": "claude_code",
                "name": skill_id,
                "usage_count": usage_count,
                "capabilities": skill.get("capabilities", []),
                "last_detected": datetime.now().isoformat(),
            }
            synchronized.append(skill_profile)

        # 记录同步事件
        self.event_collector.record(
            event_type=EventType.SKILL_EXEC,
            skill_id="zenskill-core",
            action=f"同步 {len(synchronized)} 个 Claude Code 技能",
            context={
                "synchronized_count": len(synchronized),
                "skills": [s["name"] for s in skills["installed"]],
            },
        )

        return {
            "synchronized": synchronized,
            "total_usage_events": usage["total_events"],
            "tool_breakdown": usage["by_tool"],
        }

    # === 项目技术栈检测 ===

    def _detect_project_stack(self) -> Dict[str, Any]:
        """检测项目使用的技术栈"""
        result: Dict[str, Any] = {
            "languages": [],
            "package_managers": [],
            "frameworks": [],
            "tools": [],
        }

        # 语言识别标志文件
        LANG_MARKERS = {
            "python": ["pyproject.toml", "setup.py", "requirements.txt", "Pipfile"],
            "typescript": ["tsconfig.json", "package.json"],
            "javascript": ["package.json", "jsconfig.json"],
            "rust": ["Cargo.toml", "Cargo.lock"],
            "go": ["go.mod", "go.sum"],
            "java": ["pom.xml", "build.gradle"],
            "kotlin": ["build.gradle.kts"],
            "swift": ["Package.swift"],
        }

        for lang, markers in LANG_MARKERS.items():
            if any((self.project_root / m).exists() for m in markers):
                result["languages"].append(lang)

        # 包管理器
        if (self.project_root / "package.json").exists():
            result["package_managers"].append("npm")
            if (self.project_root / "pnpm-lock.yaml").exists():
                result["package_managers"].append("pnpm")
            if (self.project_root / "yarn.lock").exists():
                result["package_managers"].append("yarn")

        if (self.project_root / "pyproject.toml").exists():
            result["package_managers"].append("pip")
            content = self._read_file_content("pyproject.toml")
            if content and "poetry" in content:
                result["package_managers"].append("poetry")

        # 常见框架
        FRAMEWORK_MARKERS = {
            "react": ["node_modules/react", "src/App.tsx"],
            "nextjs": ["next.config.js", "next.config.ts"],
            "vue": ["node_modules/vue", "vite.config.ts"],
            "django": ["manage.py", "django_settings.py"],
            "fastapi": ["main.py", "app/main.py"],
            "flask": ["app.py", "application.py"],
        }

        for fw, markers in FRAMEWORK_MARKERS.items():
            if any((self.project_root / m).exists() for m in markers):
                result["frameworks"].append(fw)

        # 工具
        TOOL_MARKERS = {
            "pytest": ["pytest.ini", "conftest.py"],
            "docker": ["Dockerfile", "docker-compose.yml"],
            "github_actions": [".github/workflows/"],
            "gitlab_ci": [".gitlab-ci.yml"],
            "pre-commit": [".pre-commit-config.yaml"],
        }

        for tool, markers in TOOL_MARKERS.items():
            if any((self.project_root / m).exists() for m in markers):
                result["tools"].append(tool)

        return result

    # === Git 画像 ===

    def _scan_git_profile(self) -> Dict[str, Any]:
        """扫描 Git 配置和最近提交模式"""
        result = {
            "has_git": False,
            "user_name": "",
            "user_email": "",
            "recent_commits": [],
            "commit_pattern": {},
        }

        git_dir = self.project_root / ".git"
        if not git_dir.exists():
            return result

        result["has_git"] = True

        # 读取 git config
        git_config = self.project_root / ".git" / "config"
        if git_config.exists():
            try:
                content = git_config.read_text(encoding="utf-8", errors="ignore")
                for line in content.split("\n"):
                    if "name =" in line:
                        result["user_name"] = line.split("=", 1)[1].strip()
                    if "email =" in line:
                        result["user_email"] = line.split("=", 1)[1].strip()
            except Exception:
                pass

        # 最近提交
        import subprocess
        try:
            output = subprocess.check_output(
                ["git", "log", "--oneline", "-n", "20", "--format=%ad|%s", "--date=iso"],
                cwd=self.project_root,
                stderr=subprocess.DEVNULL,
                timeout=5,
                text=True,
            )
            commits = []
            hours = []
            for line in output.strip().split("\n"):
                if "|" in line:
                    date_str, msg = line.split("|", 1)
                    try:
                        dt = datetime.fromisoformat(date_str.strip())
                        commits.append({
                            "hour": dt.hour,
                            "weekday": dt.weekday(),
                            "message": msg[:80],
                        })
                        hours.append(dt.hour)
                    except ValueError:
                        pass

            result["recent_commits"] = commits[:10]

            # 提交时间模式
            if hours:
                hour_counts = Counter(hours)
                result["commit_pattern"] = {
                    "most_active_hour": hour_counts.most_common(1)[0][0],
                    "morning_commits": sum(1 for h in hours if 6 <= h < 12),
                    "afternoon_commits": sum(1 for h in hours if 12 <= h < 18),
                    "evening_commits": sum(1 for h in hours if 18 <= h < 24),
                    "night_commits": sum(1 for h in hours if 0 <= h < 6),
                }
        except Exception:
            pass

        return result

    # === 编辑器配置 ===

    def _scan_editor_config(self) -> Dict[str, Any]:
        """扫描 .vscode/ 和 .editorconfig"""
        result = {
            "vscode_extensions": [],
            "editor_settings": {},
        }

        vscode_dir = self.project_root / ".vscode"
        if vscode_dir.exists():
            # 推荐扩展
            extensions_json = vscode_dir / "extensions.json"
            if extensions_json.exists():
                try:
                    data = json.loads(extensions_json.read_text(encoding="utf-8"))
                    result["vscode_extensions"] = data.get("recommendations", [])
                except Exception:
                    pass

            # 设置
            settings_json = vscode_dir / "settings.json"
            if settings_json.exists():
                try:
                    data = json.loads(settings_json.read_text(encoding="utf-8"))
                    result["editor_settings"] = {
                        k: v for k, v in data.items()
                        if isinstance(v, (str, int, float, bool))
                    }
                except Exception:
                    pass

        # .editorconfig
        editorconfig = self.project_root / ".editorconfig"
        if editorconfig.exists():
            result["has_editorconfig"] = True

        return result

    # === 辅助方法 ===

    def _read_file_content(self, filename: str, max_size: int = 5000) -> Optional[str]:
        """安全读取文件内容"""
        try:
            fpath = self.project_root / filename
            if fpath.exists() and fpath.stat().st_size < max_size:
                return fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
        return None

    def get_work_pattern_summary(self) -> Dict[str, Any]:
        """获取工作模式摘要"""
        scan = self.scan_all()

        return {
            "primary_languages": scan["project_stack"]["languages"][:3],
            "tools": scan["project_stack"]["tools"][:5],
            "active_hours": scan["git_profile"]["commit_pattern"],
            "installed_skills": [s["name"] for s in scan["skills"]["installed"]],
        }
