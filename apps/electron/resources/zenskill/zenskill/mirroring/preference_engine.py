"""
偏好学习引擎 (Phase 9B + 9B+)

自动学习用户的工作风格、沟通偏好、决策模式。
支持 Session-level 实时学习 + 跨项目偏好同步。
"""

import json
import logging
import shutil
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .event_collector import EventCollector
from .feature_store import FeatureStore

logger = logging.getLogger(__name__)


def get_global_mirror_dir() -> Path:
    """获取全局镜像目录（跨项目共享）"""
    from zenskill.core.paths import get_user_data_dir
    return get_user_data_dir() / "global" / "mirroring"


@dataclass
class Preference:
    """带置信度的偏好"""
    value: str
    confidence: float  # 0.0 - 1.0
    evidence_count: int = 0
    last_updated: str = ""

    def update(self, new_value: str, strength: float = 0.3) -> None:
        """更新偏好（带置信度衰减）"""
        now = datetime.now().isoformat()
        if self.value == new_value:
            # 强化现有偏好
            new_conf = min(1.0, self.confidence + strength * (1 - self.confidence))
            self.confidence = new_conf
            self.evidence_count += 1
            self.last_updated = now
        else:
            # 弱化并可能切换
            self.confidence *= 0.9
            if self.confidence < 0.3:
                self.value = new_value
                self.confidence = strength
                self.evidence_count = 1
                self.last_updated = now


@dataclass
class UserPreferences:
    """完整的用户偏好画像"""

    # --- 沟通风格 ---
    communication_style: Preference = field(
        default_factory=lambda: Preference("detailed", 0.5)
    )  # concise / detailed / technical / casual

    explanation_depth: Preference = field(
        default_factory=lambda: Preference("moderate", 0.5)
    )  # beginner / moderate / expert

    response_length: Preference = field(
        default_factory=lambda: Preference("medium", 0.5)
    )  # short / medium / long

    # --- 工作风格 ---
    work_pace: Preference = field(
        default_factory=lambda: Preference("steady", 0.5)
    )  # fast / steady / thorough

    tool_preference: Preference = field(
        default_factory=lambda: Preference("automation", 0.5)
    )  # manual / automation / hybrid

    code_style: Preference = field(
        default_factory=lambda: Preference("pragmatic", 0.5)
    )  # pragmatic / clean / minimal / comprehensive

    # --- 决策模式 ---
    decision_style: Preference = field(
        default_factory=lambda: Preference("systematic", 0.5)
    )  # intuitive / systematic / collaborative

    risk_tolerance: Preference = field(
        default_factory=lambda: Preference("moderate", 0.5)
    )  # conservative / moderate / aggressive

    # --- 学习风格 ---
    learning_style: Preference = field(
        default_factory=lambda: Preference("learning_by_doing", 0.5)
    )  # theory_first / learning_by_doing / example_driven

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典"""
        result: Dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if isinstance(value, Preference):
                result[key] = asdict(value)
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserPreferences":
        """从字典加载"""
        prefs = cls()
        for key, value in data.items():
            if hasattr(prefs, key) and isinstance(value, dict):
                pref = getattr(prefs, key)
                pref.value = value.get("value", pref.value)
                pref.confidence = value.get("confidence", pref.confidence)
                pref.evidence_count = value.get("evidence_count", 0)
                pref.last_updated = value.get("last_updated", "")
        return prefs

    def get_high_confidence_prefs(self, threshold: float = 0.7) -> Dict[str, str]:
        """获取高置信度的偏好"""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, Preference) and value.confidence >= threshold:
                result[key] = value.value
        return result


class PreferenceEngine:
    """偏好学习引擎 - 从行为数据推导用户偏好"""

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            from zenskill.core.paths import get_mirroring_dir
            self._data_dir = get_mirroring_dir()
        else:
            self._data_dir = data_dir

        self._prefs_file = self._data_dir / "preferences.json"
        self.event_collector = EventCollector(data_dir)
        self.feature_store = FeatureStore(data_dir)

        # 缓存的偏好
        self._prefs: Optional[UserPreferences] = None

    def load_preferences(self) -> UserPreferences:
        """加载偏好（带缓存）"""
        if self._prefs is not None:
            return self._prefs

        if self._prefs_file.exists():
            try:
                data = json.loads(self._prefs_file.read_text(encoding="utf-8"))
                self._prefs = UserPreferences.from_dict(data)
                return self._prefs
            except Exception:
                pass

        self._prefs = UserPreferences()
        return self._prefs

    def save_preferences(self) -> None:
        """保存偏好"""
        if self._prefs is None:
            return

        self._data_dir.mkdir(parents=True, exist_ok=True)
        data = self._prefs.to_dict()
        self._prefs_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # -------------------------------------------------------------------------
    # 行为信号分析器
    # -------------------------------------------------------------------------

    def analyze_tool_patterns(self) -> Dict[str, Any]:
        """分析工具使用模式"""
        events = self.event_collector.query(limit=100)

        tool_counts: Counter = Counter()
        category_counts: Counter = Counter()
        edit_ratio = 0
        read_count = 0

        for e in events:
            ctx = e.context or {}
            if isinstance(ctx, dict):
                tool = ctx.get("tool")
                if tool:
                    tool_counts[tool] += 1
                category = ctx.get("category")
                if category:
                    category_counts[category] += 1

        total = len(events)
        read_count = tool_counts.get("Read", 0)
        edit_count = tool_counts.get("Edit", 0) + tool_counts.get("Write", 0)

        if total > 0:
            edit_ratio = edit_count / total
            read_ratio = read_count / total
        else:
            read_ratio = 0

        # 推导工具偏好
        if edit_ratio > 0.5:
            tool_style = "hands_on"
        elif read_ratio > 0.5:
            tool_style = "research_first"
        else:
            tool_style = "balanced"

        # 工作节奏: 事件时间间隔
        pace = "steady"
        if len(events) >= 5:
            timestamps = [e.timestamp for e in events[-10:]]
            if timestamps:
                avg_interval = sum(
                    timestamps[i] - timestamps[i - 1]
                    for i in range(1, len(timestamps))
                ) / (len(timestamps) - 1)
                if avg_interval < 10:  # 小于 10 秒
                    pace = "fast"
                elif avg_interval > 60:  # 大于 60 秒
                    pace = "thorough"

        return {
            "tool_distribution": dict(tool_counts),
            "category_distribution": dict(category_counts),
            "edit_ratio": edit_ratio,
            "read_ratio": read_ratio,
            "tool_style": tool_style,
            "work_pace": pace,
            "total_events": total,
        }

    def analyze_git_patterns(self) -> Dict[str, Any]:
        """分析 Git 提交模式"""
        events = self.event_collector.query(limit=50)

        commit_count = 0
        push_count = 0
        commit_messages: List[str] = []

        for e in events:
            action = e.action.lower() if e.action else ""
            if "git" in action and "commit" in action:
                commit_count += 1
                commit_messages.append(e.action or "")
            if "git" in action and "push" in action:
                push_count += 1

        # 提交风格
        commit_style = "infrequent"
        if commit_count >= 3:
            commit_style = "frequent_small_commits"
        elif commit_count >= 1:
            commit_style = "regular"

        return {
            "commit_count": commit_count,
            "push_count": push_count,
            "commit_style": commit_style,
        }

    def analyze_documentation_preference(self) -> Dict[str, Any]:
        """分析文档偏好（从 Read 模式推导）"""
        events = self.event_collector.query(limit=50)

        doc_reads = 0
        code_reads = 0

        for e in events:
            ctx = e.context or {}
            if isinstance(ctx, dict):
                ext = ctx.get("extension", "")
                if ext in [".md", ".rst", ".txt"]:
                    doc_reads += 1
                elif ext in [".py", ".ts", ".js", ".rs", ".go"]:
                    code_reads += 1

        if doc_reads + code_reads == 0:
            style = "undetermined"
        elif doc_reads / (doc_reads + code_reads) > 0.5:
            style = "documentation_heavy"
        else:
            style = "code_first"

        return {
            "doc_reads": doc_reads,
            "code_reads": code_reads,
            "learning_style": style,
        }

    # -------------------------------------------------------------------------
    # 偏好更新
    # -------------------------------------------------------------------------

    def learn_from_behavior(self, save: bool = True) -> Dict[str, Any]:
        """从行为数据学习偏好"""
        prefs = self.load_preferences()

        tool_patterns = self.analyze_tool_patterns()
        git_patterns = self.analyze_git_patterns()
        doc_prefs = self.analyze_documentation_preference()

        # 工作节奏
        pace = tool_patterns["work_pace"]
        if pace == "fast":
            prefs.work_pace.update("fast", 0.4)
        elif pace == "thorough":
            prefs.work_pace.update("thorough", 0.4)

        # 工具偏好
        tool_style = tool_patterns["tool_style"]
        if tool_style == "hands_on":
            prefs.tool_preference.update("automation", 0.3)
        elif tool_style == "research_first":
            prefs.tool_preference.update("careful", 0.3)

        # 学习风格
        learning = doc_prefs["learning_style"]
        if learning == "documentation_heavy":
            prefs.learning_style.update("theory_first", 0.35)
        elif learning == "code_first":
            prefs.learning_style.update("learning_by_doing", 0.35)

        # 代码风格
        edit_ratio = tool_patterns["edit_ratio"]
        if edit_ratio > 0.4:
            prefs.code_style.update("pragmatic", 0.25)

        if save:
            self.save_preferences()

        return {
            "preferences": prefs.to_dict(),
            "signals": {
                "tool_patterns": tool_patterns,
                "git_patterns": git_patterns,
                "doc_preferences": doc_prefs,
            },
        }

    def get_profile_summary(self) -> Dict[str, Any]:
        """获取用户画像摘要"""
        prefs = self.load_preferences()
        prefs_dict = prefs.to_dict()

        # 高置信度偏好
        high_conf = prefs.get_high_confidence_prefs(0.7)

        # 计算总体置信度
        conf_values = [
            v.confidence
            for v in prefs.__dict__.values()
            if isinstance(v, Preference)
        ]
        avg_confidence = sum(conf_values) / len(conf_values) if conf_values else 0

        # 行为信号
        signals = self.analyze_tool_patterns()

        return {
            "profile_strength": "strong" if avg_confidence > 0.7 else "developing" if avg_confidence > 0.5 else "initial",
            "average_confidence": avg_confidence,
            "high_confidence_preferences": high_conf,
            "all_preferences": prefs_dict,
            "behavior_signals": signals,
        }

    # -------------------------------------------------------------------------
    # Session-level 实时学习 (9B-2)
    # -------------------------------------------------------------------------

    def learn_from_user_input(
        self,
        user_message: str,
        ai_response: Optional[str] = None,
        user_feedback: Optional[str] = None,
        save: bool = True,
    ) -> Dict[str, Any]:
        """
        从单轮对话中实时学习用户偏好

        Args:
            user_message: 用户输入内容
            ai_response: AI 响应内容
            user_feedback: 用户反馈（如 "太长了"、"不够详细"）
        """
        prefs = self.load_preferences()

        # 1. 分析用户输入长度 → 沟通风格
        msg_length = len(user_message)
        if msg_length < 30:
            # 短输入 → 用户偏好简洁沟通
            prefs.communication_style.update("concise", 0.2)
            prefs.response_length.update("short", 0.15)
        elif msg_length > 200:
            # 长输入 → 用户偏好详细沟通
            prefs.communication_style.update("detailed", 0.2)
            prefs.response_length.update("long", 0.15)
        else:
            prefs.communication_style.update("balanced", 0.1)

        # 2. 分析输入中的技术术语密度
        tech_terms = ["implement", "architecture", "refactor", "optimize", "debug",
                      "设计", "架构", "重构", "优化", "调试"]
        tech_count = sum(1 for t in tech_terms if t.lower() in user_message.lower())
        if tech_count >= 2:
            prefs.explanation_depth.update("expert", 0.25)
            prefs.communication_style.update("technical", 0.2)
        elif tech_count == 0:
            prefs.explanation_depth.update("beginner", 0.1)

        # 3. 从用户反馈学习
        if user_feedback:
            feedback_lower = user_feedback.lower()
            if any(k in feedback_lower for k in ["太长", "太长了", "too long", "shorten"]):
                prefs.response_length.update("short", 0.4)
            elif any(k in feedback_lower for k in ["太短", "不够", "more detail", "详细点"]):
                prefs.response_length.update("long", 0.4)
            elif any(k in feedback_lower for k in ["太快", "慢点", "slow down"]):
                prefs.work_pace.update("thorough", 0.35)
            elif any(k in feedback_lower for k in ["太慢", "快点", "faster"]):
                prefs.work_pace.update("fast", 0.35)

        # 4. 从 AI 响应的反馈学习（如果有）
        if ai_response and len(ai_response) > 0:
            # 响应风格分析可以进一步细化
            pass

        if save:
            self.save_preferences()

        return {
            "learned_signals": {
                "message_length": msg_length,
                "tech_terms_found": tech_count,
                "has_feedback": user_feedback is not None,
            },
            "updated_preferences": prefs.to_dict(),
        }

    # -------------------------------------------------------------------------
    # 跨项目偏好同步 (9B-3)
    # -------------------------------------------------------------------------

    def sync_with_global(self) -> Dict[str, Any]:
        """
        将当前项目偏好与全局偏好合并

        合并策略: 取置信度更高的偏好
        """
        global_dir = get_global_mirror_dir()
        global_dir.mkdir(parents=True, exist_ok=True)
        global_prefs_file = global_dir / "preferences.json"

        local_prefs = self.load_preferences()
        sync_stats: Dict[str, Any] = {
            "merged": [],
            "local_kept": [],
            "global_kept": [],
        }

        # 1. 加载或初始化全局偏好
        if global_prefs_file.exists():
            try:
                global_data = json.loads(global_prefs_file.read_text(encoding="utf-8"))
                global_prefs = UserPreferences.from_dict(global_data)
            except Exception:
                global_prefs = UserPreferences()
        else:
            global_prefs = UserPreferences()

        # 2. 合并偏好（置信度高的胜出）
        for key in local_prefs.__dict__.keys():
            if not isinstance(getattr(local_prefs, key), Preference):
                continue

            local: Preference = getattr(local_prefs, key)
            global_pref: Preference = getattr(global_prefs, key)

            if local.confidence > global_pref.confidence:
                # 本地更新全局
                global_pref.value = local.value
                global_pref.confidence = local.confidence
                global_pref.evidence_count += local.evidence_count
                global_pref.last_updated = datetime.now().isoformat()
                sync_stats["merged"].append(key)
                sync_stats["local_kept"].append(key)
            else:
                # 全局更新本地
                local.value = global_pref.value
                local.confidence = max(local.confidence, global_pref.confidence)
                sync_stats["global_kept"].append(key)

        # 3. 双向保存
        self._prefs = local_prefs
        self.save_preferences()

        global_prefs_file.write_text(
            json.dumps(global_prefs.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # 4. 同步事件数据（可选备份）
        self._sync_event_history(global_dir)

        return sync_stats

    def _sync_event_history(self, global_dir: Path) -> None:
        """同步事件历史到全局存储（增量追加）"""
        local_events = self._data_dir / "events.jsonl"
        global_events = global_dir / "events.backup.jsonl"

        if not local_events.exists():
            return

        # 简单的增量追加（生产环境需要去重）
        try:
            with open(local_events, "r", encoding="utf-8") as lf:
                local_lines = lf.readlines()

            existing_ids = set()
            if global_events.exists():
                with open(global_events, "r", encoding="utf-8") as gf:
                    for line in gf:
                        if line.strip():
                            try:
                                data = json.loads(line)
                                existing_ids.add(data.get("event_id", ""))
                            except Exception:
                                pass

            new_lines = [
                line for line in local_lines
                if json.loads(line).get("event_id", "") not in existing_ids
            ]

            if new_lines:
                with open(global_events, "a", encoding="utf-8") as gf:
                    gf.writelines(new_lines)
        except Exception:
            pass

    def export_preferences(self, output_path: str) -> bool:
        """导出偏好到文件"""
        prefs = self.load_preferences()
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(prefs.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return True
        except Exception:
            return False

    def import_preferences(self, input_path: str, merge: bool = True) -> bool:
        """导入偏好文件"""
        try:
            path = Path(input_path)
            data = json.loads(path.read_text(encoding="utf-8"))
            imported = UserPreferences.from_dict(data)

            if merge:
                # 合并到当前
                current = self.load_preferences()
                for key in imported.__dict__.keys():
                    if not isinstance(getattr(imported, key), Preference):
                        continue
                    imp: Preference = getattr(imported, key)
                    cur: Preference = getattr(current, key)
                    if imp.confidence > cur.confidence:
                        cur.value = imp.value
                        cur.confidence = imp.confidence
                        cur.evidence_count += imp.evidence_count
                self._prefs = current
            else:
                self._prefs = imported

            self.save_preferences()
            return True
        except Exception as e:
            logger.exception("导入偏好失败: %s", e)
            return False

    # -------------------------------------------------------------------------
    # 批量历史学习 (Phase 9B 增强)
    # -------------------------------------------------------------------------

    def learn_from_history(
        self, limit: Optional[int] = None, show_progress: bool = False
    ) -> Dict[str, Any]:
        """
        从完整的事件历史批量学习偏好

        Args:
            limit: 最多处理多少条事件，None 为全部
            show_progress: 是否显示学习进度条

        Returns:
            学习结果统计
        """
        try:
            events = self.event_collector.query(limit=limit or 1000)
            total = len(events)

            if show_progress and total > 0:
                print(self._progress_bar(0, total, prefix="学习进度"))

            for i, event in enumerate(events):
                # 从每个事件提取信号并学习
                self._learn_from_single_event(event)

                if show_progress and (i + 1) % 10 == 0:
                    print(
                        f"\r{self._progress_bar(i + 1, total, prefix='学习进度')}",
                        end="",
                        flush=True,
                    )

            if show_progress:
                print()  # 换行

            self.save_preferences()

            profile = self.get_profile_summary()
            logger.info("批量学习完成: %d 条事件, 平均置信度 %.2f",
                       total, profile["average_confidence"])

            return {
                "events_processed": total,
                "new_average_confidence": profile["average_confidence"],
                "profile_strength": profile["profile_strength"],
                "high_confidence_count": len(profile["high_confidence_preferences"]),
            }

        except Exception as e:
            logger.exception("批量历史学习失败: %s", e)
            return {"error": str(e), "events_processed": 0}

    def _learn_from_single_event(self, event: Any) -> None:
        """从单个事件学习偏好"""
        try:
            ctx = event.context or {}
            if not isinstance(ctx, dict):
                return

            # 工具使用模式
            tool = ctx.get("tool", "")
            if tool in ["Edit", "Write", "Bash"]:
                prefs = self.load_preferences()
                prefs.tool_preference.update("automation", 0.1)
            elif tool == "Read":
                prefs = self.load_preferences()
                prefs.tool_preference.update("careful", 0.05)

            # 命令复杂度
            if tool == "Bash" and "command" in ctx:
                cmd = ctx["command"]
                if len(cmd) > 100 or "|" in cmd or "&&" in cmd:
                    prefs = self.load_preferences()
                    prefs.code_style.update("comprehensive", 0.1)

        except Exception:
            pass  # 单个事件失败不影响整体

    # -------------------------------------------------------------------------
    # 置信度可视化
    # -------------------------------------------------------------------------

    def _progress_bar(self, current: int, total: int, prefix: str = "", width: int = 40) -> str:
        """生成 ASCII 进度条"""
        if total == 0:
            return f"{prefix}: [{'=' * width}] 100%"
        percent = current / total
        filled = int(width * percent)
        bar = "=" * filled + "-" * (width - filled)
        return f"{prefix}: [{bar}] {percent * 100:.1f}% ({current}/{total})"

    def visualize_confidence(self, width: int = 30) -> str:
        """
        可视化所有偏好的置信度

        返回格式类似:
            communication_style: detailed    [======-----] 60.0%
            work_pace:         fast         [========---] 85.0%
        """
        prefs = self.load_preferences()
        lines = []
        max_key_len = max(len(k) for k in prefs.__dict__.keys()
                         if isinstance(getattr(prefs, k), Preference))

        for key, value in prefs.__dict__.items():
            if not isinstance(value, Preference):
                continue

            filled = int(width * value.confidence)
            bar = "=" * filled + "-" * (width - filled)
            key_padded = key.ljust(max_key_len)
            lines.append(
                f"  {key_padded}: {value.value:12s} [{bar}] {value.confidence * 100:.1f}%"
            )

        return "\n".join(lines)

    def get_confidence_chart(self) -> str:
        """生成美观的置信度图表（用于 CLI 输出）"""
        profile = self.get_profile_summary()
        avg_conf = profile["average_confidence"]

        output = ["\n📊 用户偏好置信度概览\n", "=" * 60, ""]
        output.append(self.visualize_confidence())
        output.append("")
        output.append(f"整体画像强度: {profile['profile_strength'].upper()}")
        output.append(f"平均置信度: {avg_conf * 100:.1f}%")
        output.append(f"高置信度偏好: {len(profile['high_confidence_preferences'])} 项")
        output.append("")

        return "\n".join(output)

    # -------------------------------------------------------------------------
    # 偏好比较 (本地 vs 全局)
    # -------------------------------------------------------------------------

    def compare_with_global(self) -> Dict[str, Any]:
        """
        比较本地偏好与全局偏好的差异

        Returns:
            差异分析结果
        """
        try:
            local_prefs = self.load_preferences()
            global_dir = get_global_mirror_dir()
            global_file = global_dir / "preferences.json"

            if not global_file.exists():
                return {"error": "全局偏好不存在，请先执行 sync-global"}

            global_data = json.loads(global_file.read_text(encoding="utf-8"))
            global_prefs = UserPreferences.from_dict(global_data)

            differences = []
            local_only = []
            global_only = []

            for key in local_prefs.__dict__.keys():
                if not isinstance(getattr(local_prefs, key), Preference):
                    continue

                local: Preference = getattr(local_prefs, key)
                global_pref: Preference = getattr(global_prefs, key)

                if local.value != global_pref.value:
                    differences.append({
                        "preference": key,
                        "local_value": local.value,
                        "local_confidence": local.confidence,
                        "global_value": global_pref.value,
                        "global_confidence": global_pref.confidence,
                    })
                elif local.confidence > global_pref.confidence + 0.2:
                    local_only.append({
                        "preference": key,
                        "value": local.value,
                        "confidence_diff": local.confidence - global_pref.confidence,
                    })
                elif global_pref.confidence > local.confidence + 0.2:
                    global_only.append({
                        "preference": key,
                        "value": global_pref.value,
                        "confidence_diff": global_pref.confidence - local.confidence,
                    })

            return {
                "differences": differences,
                "local_stronger": local_only,
                "global_stronger": global_only,
                "total_preferences": sum(
                    1 for v in local_prefs.__dict__.values()
                    if isinstance(v, Preference)
                ),
            }

        except Exception as e:
            logger.exception("偏好比较失败: %s", e)
            return {"error": str(e)}
