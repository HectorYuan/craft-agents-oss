"""
ZenSkill 主动通知引擎

多渠道推送: Claude Code Notification / TUI / CLI
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class ZenNotifier:
    """多通道通知引擎"""

    def __init__(self):
        self._sent_file = Path.home() / ".zenskill" / "session" / ".notifications_sent"
        self._sent: List[str] = self._load_sent()

    def _load_sent(self) -> List[str]:
        """加载已发送的通知 ID (防重复)"""
        if self._sent_file.exists():
            try:
                return json.loads(self._sent_file.read_text()).get("ids", [])
            except Exception:
                pass
        return []

    def _save_sent(self) -> None:
        """保存已发送列表"""
        self._sent_file.parent.mkdir(parents=True, exist_ok=True)
        self._sent_file.write_text(json.dumps({
            "ids": self._sent[-50:],  # 只保留最近 50 条
            "updated": time.time(),
        }, ensure_ascii=False))

    def _dedup(self, nid: str) -> bool:
        """去重检查: True = 可以发送"""
        if nid in self._sent:
            return False
        self._sent.append(nid)
        self._save_sent()
        return True

    def check(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检查是否可以发送通知

        context = {tool_count, elapsed_min, level, session_started, ...}
        返回需要发送的通知列表
        """
        notifications = []
        tc = context.get("tool_count", 0)
        elapsed = context.get("elapsed_min", 0)

        # 1. 里程碑通知
        for milestone in [50, 100, 200, 500]:
            nid = f"milestone_{milestone}"
            if tc >= milestone and tc - milestone < 3 and self._dedup(nid):
                notifications.append({
                    "id": nid,
                    "type": "milestone",
                    "level": "info",
                    "title": f"🎉 里程碑: {milestone} 次工具调用",
                    "message": f"本会话已达到 {milestone} 次操作。运行 `zenskill skill info` 查看成长状态。",
                    "action": "zenskill skill info",
                })

        # 2. 疲劳提醒
        nid = f"fatigue_{int(elapsed/30)}"
        if elapsed > 60 and self._dedup(nid):
            notifications.append({
                "id": nid,
                "type": "health",
                "level": "warning",
                "title": f"⏰ 已持续 {elapsed:.0f} 分钟",
                "message": f"会话已持续 {elapsed:.0f} 分钟/{tc} 次操作，建议短暂休息。运行 `zenskill mirror tips` 查看建议。",
                "action": "zenskill mirror tips",
            })

        # 3. 新洞察通知 (pipeline 刷新后)
        pipeline_file = Path.home() / ".zenskill" / "mirroring" / "pipeline.json"
        if pipeline_file.exists():
            try:
                pipeline = json.loads(pipeline_file.read_text())
                ts = pipeline.get("timestamp", 0)
                insights = pipeline.get("insights", [])
                if insights and time.time() - ts < 120:
                    nid = f"insight_{int(ts/60)}"
                    if self._dedup(nid):
                        notifications.append({
                            "id": nid,
                            "type": "insight",
                            "level": "info",
                            "title": f"💡 新洞察 ({len(insights)} 条)",
                            "message": insights[0] if insights else "查看最新洞察",
                            "action": "zenskill mirror predict",
                        })
            except Exception:
                pass

        # 4. 级升通知
        level = context.get("level", "")
        old_level = context.get("old_level", "")
        nid = f"levelup_{level}"
        if level and old_level and level != old_level and self._dedup(nid):
            notifications.append({
                "id": nid,
                "type": "growth",
                "level": "success",
                "title": f"🏆 境界提升: {old_level} → {level}",
                "message": f"你的技能境界已从 {old_level} 提升到 {level}！运行 `zenskill skill info` 查看详情。",
                "action": "zenskill skill info",
            })

        return notifications

    def format_for_hook(self, notifications: List[Dict]) -> str:
        """格式化为 Hook 可读输出 (Claude Code Notification)"""
        if not notifications:
            return ""

        lines = []
        for n in notifications:
            icon = {"info": "ℹ️", "warning": "⚠️", "success": "✅", "error": "❌"}
            i = icon.get(n.get("level", "info"), "ℹ️")
            lines.append(f"{i} [{n['type']}] {n['title']}")
            lines.append(f"   {n['message']}")
            if n.get("action"):
                lines.append(f"   → `{n['action']}`")

        return "\n".join(lines)

    def format_for_tui(self, notifications: List[Dict]) -> str:
        """格式化为 TUI 可显示文本"""
        if not notifications:
            return "[dim]无新通知[/dim]"

        lines = []
        for n in notifications[:3]:
            lines.append(f"{n['title']}")
            lines.append(f"[dim]{n['message'][:80]}[/dim]")
        return "\n".join(lines)


# 全局单例
notifier = ZenNotifier()
