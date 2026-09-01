"""
8.7D: Energy 能量系统

能量作为修炼核心货币 — 消耗 → XP → 成长。
境界决定能量上限，稳定性影响恢复速度。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# 境界 → 能量上限
LEVEL_MAX_ENERGY = {
    "NOVICE": 60, "APPRENTICE": 100, "ADEPT": 150,
    "EXPERT": 200, "MASTER": 300,
}

# Action 难度 → 能量消耗
ACTION_ENERGY_COST = {"easy": 5, "medium": 15, "hard": 30, "extreme": 50}


@dataclass
class EnergyPool:
    skill_id: str = "zenskill-core"
    profile: str = ""  # 所属 profile（空=当前激活）
    max_energy: int = 200
    current_energy: int = 200
    recovery_rate: float = 30.0  # 每小时
    history: list[dict] = field(default_factory=list)  # 最近 100 条记录
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id, "profile": self.profile,
            "max_energy": self.max_energy,
            "current_energy": self.current_energy, "recovery_rate": self.recovery_rate,
            "history": self.history[-100:], "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EnergyPool":
        return cls(
            skill_id=data.get("skill_id", "zenskill-core"),
            profile=data.get("profile", ""),
            max_energy=data.get("max_energy", 200),
            current_energy=data.get("current_energy", 200),
            recovery_rate=data.get("recovery_rate", 30.0),
            history=data.get("history", []),
            updated_at=data.get("updated_at", ""),
        )


class EnergyEngine:
    """能量管理引擎"""

    def __init__(self, skill_id: str = "zenskill-core", data_dir: str = ""):
        self.skill_id = skill_id
        if data_dir:
            self._data_dir = Path(data_dir)
        else:
            from ...core.paths import get_user_data_dir
            self._data_dir = get_user_data_dir() / "gtd"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._data_dir / "energy.json"
        self._pool = self._load()
        self._sync_from_cultivating()

    def status(self) -> dict:
        self._sync_from_cultivating()
        pct = self._pool.current_energy / max(self._pool.max_energy, 1)
        level = self._energy_level(pct)
        return {
            "skill_id": self.skill_id,
            "max_energy": self._pool.max_energy,
            "current_energy": self._pool.current_energy,
            "pct": round(pct, 2),
            "level": level,
            "recovery_rate": self._pool.recovery_rate,
            "level_icon": {"high": "🟢", "medium": "🟡", "low": "🟠", "critical": "🔴"}.get(level),
        }

    def burn(self, amount: int, action_title: str = "") -> dict:
        self._apply_passive_recovery()
        actual = min(amount, self._pool.current_energy)
        self._pool.current_energy -= actual
        self._pool.history.append({
            "type": "burn", "amount": actual, "action": action_title[:60],
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        self._save()
        return {
            "burned": actual, "requested": amount,
            "remaining": self._pool.current_energy,
            "low_energy": self._pool.current_energy < 10,
        }

    def recover(self, amount: int = 10, source: str = "rest") -> dict:
        self._pool.current_energy = min(
            self._pool.current_energy + amount, self._pool.max_energy)
        self._pool.history.append({
            "type": "recover", "amount": amount, "source": source,
            "at":time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        self._save()
        return self.status()

    def advise(self) -> dict:
        """能量优化建议"""
        s = self.status()
        history_7d = [h for h in self._pool.history[-200:]
                      if h["at"] > time.strftime("%Y-%m-%d",
                                                   time.localtime(time.time() - 7 * 86400))]

        # 分析燃烧模式
        burns = [h for h in history_7d if h["type"] == "burn"]
        total_burned = sum(h["amount"] for h in burns)

        # 找高效时段
        hour_burns = {}
        for h in burns:
            try:
                hour = time.strptime(h["at"][:19], "%Y-%m-%dT%H:%M:%S").tm_hour
                hour_burns[hour] = hour_burns.get(hour, 0) + h["amount"]
            except Exception:
                pass
        peak_hour = max(hour_burns, key=hour_burns.get) if hour_burns else 0

        suggestions = []
        if s["current_energy"] < 20:
            suggestions.append("⚡ 能量极低, 建议休息 15 分钟恢复")
        if total_burned > 500:
            suggestions.append("🔥 近 7 天消耗较高, 注意能量管理")
        if peak_hour:
            suggestions.append(
                f"⏰ 最高效时段: {peak_hour}:00 左右, 建议安排高难度任务")

        return {**s, "total_burned_7d": total_burned,
                "peak_hour": peak_hour, "suggestions": suggestions}

    def history_7d(self) -> list[dict]:
        cutoff = time.strftime("%Y-%m-%d",
                               time.localtime(time.time() - 7 * 86400))
        return [h for h in self._pool.history[-200:] if h["at"] >= cutoff]

    # ── 内部 ──

    def _sync_from_cultivating(self) -> None:
        """从修炼体系同步能量上限 (境界决定)"""
        try:
            from ...core.paths import SkillStateManager
            mgr = SkillStateManager(self.skill_id)
            state = mgr.load()
            level = state.get("level", "EXPERT")
            max_e = LEVEL_MAX_ENERGY.get(level, 200)
            self._pool.max_energy = max_e
            self._pool.current_energy = min(self._pool.current_energy, max_e)
            # 稳定性影响恢复速度
            metrics = state.get("metrics", {})
            stability_factor = metrics.get("stability", 80) / 100
            self._pool.recovery_rate = 30.0 * stability_factor
            self._save()
        except Exception:
            pass

    def _apply_passive_recovery(self) -> None:
        """根据时间流逝计算被动恢复"""
        if not self._pool.updated_at:
            return
        try:
            last = time.mktime(time.strptime(self._pool.updated_at[:19],
                                             "%Y-%m-%dT%H:%M:%S"))
            elapsed_hours = (time.time() - last) / 3600
            if elapsed_hours > 0:
                recovered = int(elapsed_hours * self._pool.recovery_rate)
                self._pool.current_energy = min(
                    self._pool.current_energy + recovered, self._pool.max_energy)
        except Exception:
            pass
        self._pool.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    @staticmethod
    def _energy_level(pct: float) -> str:
        if pct > 0.7: return "high"
        if pct > 0.3: return "medium"
        if pct > 0.1: return "low"
        return "critical"

    def _load(self) -> EnergyPool:
        if self._file.exists():
            try:
                return EnergyPool.from_dict(
                    json.loads(self._file.read_text(encoding="utf-8")))
            except Exception:
                pass
        return EnergyPool(skill_id=self.skill_id)

    def _save(self) -> None:
        self._file.write_text(
            json.dumps(self._pool.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8")
