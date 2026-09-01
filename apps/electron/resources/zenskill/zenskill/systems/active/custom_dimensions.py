"""自定义成长维度 (7O)"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from zenskill.core.paths import atomic_write_json, get_user_data_dir


@dataclass
class CustomDimension:
    dimension_id: str
    name: str
    weight: float
    method: str
    milestones: Dict[str, str]
    created_at: str
    updated_at: str


class CustomDimensionManager:
    TEMPLATES = {
        "cli_tui": {
            "name": "CLI/TUI 熟练度",
            "weight": 0.12,
            "method": "基于命令行与终端界面操作频率、成功率和切换流畅度评估",
            "milestones": {"20": "能完成基础命令", "50": "能独立排查交互问题", "80": "能优化复杂终端工作流"},
        },
        "debugging": {
            "name": "调试能力",
            "weight": 0.14,
            "method": "基于错误定位速度、复现质量和回归验证完整度评估",
            "milestones": {"30": "能定位常见错误", "60": "能系统缩小问题范围", "90": "能沉淀稳定排障方法"},
        },
        "testing": {
            "name": "测试意识",
            "weight": 0.1,
            "method": "基于测试覆盖、边界验证和失败用例归因质量评估",
            "milestones": {"25": "能补基础验证", "55": "能覆盖关键路径", "85": "能建立回归保护网"},
        },
        "architecture": {
            "name": "架构判断",
            "weight": 0.1,
            "method": "基于边界划分、依赖控制和长期演进成本评估",
            "milestones": {"30": "能识别模块边界", "60": "能控制改动半径", "90": "能做清晰取舍"},
        },
        "security": {
            "name": "安全意识",
            "weight": 0.1,
            "method": "基于输入边界、权限控制、敏感信息处理和风险识别评估",
            "milestones": {"30": "能识别明显风险", "60": "能默认安全实现", "90": "能主动建模威胁"},
        },
        "performance": {
            "name": "性能敏感度",
            "weight": 0.08,
            "method": "基于瓶颈识别、测量优先和优化收益评估",
            "milestones": {"30": "能发现明显慢点", "60": "能量化优化效果", "85": "能平衡性能与复杂度"},
        },
        "documentation": {
            "name": "文档沉淀",
            "weight": 0.08,
            "method": "基于说明清晰度、上下文保留和可复用程度评估",
            "milestones": {"25": "能记录使用方法", "55": "能解释设计动机", "80": "能形成可复用知识"},
        },
        "automation": {
            "name": "自动化能力",
            "weight": 0.1,
            "method": "基于重复任务识别、脚本化能力和工具链串联质量评估",
            "milestones": {"30": "能自动化简单流程", "60": "能串联多工具", "90": "能构建稳定流水线"},
        },
        "collaboration": {
            "name": "协作表达",
            "weight": 0.08,
            "method": "基于需求澄清、变更说明和评审沟通质量评估",
            "milestones": {"30": "能说明改动内容", "60": "能表达取舍理由", "85": "能降低协作成本"},
        },
        "product_sense": {
            "name": "产品判断",
            "weight": 0.08,
            "method": "基于用户目标理解、优先级判断和体验完整度评估",
            "milestones": {"30": "能理解直接需求", "60": "能发现体验断点", "85": "能平衡价值与成本"},
        },
    }

    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id
        self.path = get_user_data_dir() / "growth" / "custom_dimensions.json"

    def list_dimensions(self) -> List[CustomDimension]:
        data = self._load()
        dimensions = data.get("skills", {}).get(self.skill_id, {}).get("dimensions", {})
        return [CustomDimension(**item) for item in dimensions.values()]

    def add_dimension(
        self,
        dimension_id: str,
        name: str,
        weight: float = 0.1,
        method: str = "manual",
        milestones: Optional[Dict[str, str]] = None,
    ) -> CustomDimension:
        clean_id = self._normalize_id(dimension_id)
        now = datetime.now().isoformat()
        item = CustomDimension(
            dimension_id=clean_id,
            name=name.strip(),
            weight=max(0.0, min(float(weight), 1.0)),
            method=method.strip() or "manual",
            milestones=milestones or {},
            created_at=now,
            updated_at=now,
        )
        data = self._load()
        skill_data = data.setdefault("skills", {}).setdefault(self.skill_id, {"dimensions": {}})
        existing = skill_data.setdefault("dimensions", {}).get(clean_id)
        if existing:
            item.created_at = existing.get("created_at", now)
        skill_data["dimensions"][clean_id] = asdict(item)
        skill_data["updated_at"] = now
        self._save(data)
        return item

    def remove_dimension(self, dimension_id: str) -> bool:
        data = self._load()
        dimensions = data.get("skills", {}).get(self.skill_id, {}).get("dimensions", {})
        clean_id = self._normalize_id(dimension_id)
        if clean_id not in dimensions:
            return False
        del dimensions[clean_id]
        data["skills"][self.skill_id]["updated_at"] = datetime.now().isoformat()
        self._save(data)
        return True

    def apply_template(self, template_id: str) -> CustomDimension:
        clean_id = self._normalize_id(template_id)
        if clean_id not in self.TEMPLATES:
            raise ValueError(f"未知模板: {template_id}")
        tpl = self.TEMPLATES[clean_id]
        return self.add_dimension(clean_id, tpl["name"], tpl["weight"], tpl["method"], tpl["milestones"])

    def export_dimensions(self, output: Optional[str] = None) -> str:
        data = {
            "skill_id": self.skill_id,
            "dimensions": [asdict(item) for item in self.list_dimensions()],
            "exported_at": datetime.now().isoformat(),
        }
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if output:
            out = Path(output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            return str(out)
        return text

    def import_dimensions(self, source: str) -> int:
        raw = json.loads(Path(source).read_text(encoding="utf-8"))
        items = raw.get("dimensions", raw if isinstance(raw, list) else [])
        count = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            self.add_dimension(
                item.get("dimension_id", item.get("id", "")),
                item.get("name", ""),
                item.get("weight", 0.1),
                item.get("method", "manual"),
                item.get("milestones", {}),
            )
            count += 1
        return count

    def format_report(self) -> str:
        dimensions = self.list_dimensions()
        lines = ["🎛️ 自定义成长维度 (7O)", "═" * 50, ""]
        if not dimensions:
            lines.extend([
                "   暂无自定义维度",
                "   可用模板: " + ", ".join(sorted(self.TEMPLATES.keys())[:5]) + " ...",
                "   试试: zenskill growth dimensions --action apply --id cli_tui",
            ])
            return "\n".join(lines)
        total_weight = sum(item.weight for item in dimensions)
        lines.append(f"   已启用 {len(dimensions)} 个附加维度 | 总权重 {total_weight:.2f}")
        lines.append("")
        for item in dimensions:
            lines.append(f"   • {item.name} ({item.dimension_id})")
            lines.append(f"     权重: {item.weight:.2f} | 评估: {item.method}")
            if item.milestones:
                milestones = ", ".join(f"{score}:{label}" for score, label in sorted(item.milestones.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 999))
                lines.append(f"     里程碑: {milestones}")
        return "\n".join(lines)

    @classmethod
    def format_templates(cls) -> str:
        lines = ["📚 自定义维度模板库", "═" * 50, ""]
        for template_id, item in sorted(cls.TEMPLATES.items()):
            lines.append(f"   • {template_id:14s} {item['name']}  权重 {item['weight']:.2f}")
            lines.append(f"     {item['method']}")
        return "\n".join(lines)

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "skills": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"version": 1, "skills": {}}

    def _save(self, data: Dict[str, Any]) -> None:
        atomic_write_json(self.path, data)

    @staticmethod
    def _normalize_id(value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value).strip().lower()).strip("_")
        if not cleaned:
            raise ValueError("维度 ID 不能为空")
        return cleaned


def parse_milestones(values: Optional[List[str]]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for value in values or []:
        if ":" not in value:
            continue
        score, label = value.split(":", 1)
        score = score.strip()
        label = label.strip()
        if score.isdigit() and label:
            result[str(max(0, min(int(score), 100)))] = label
    return result
