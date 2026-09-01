"""
需求缺口识别器 (Phase 9E.3)

三个维度识别用户缺口：
- 技能缺口: 领域覆盖不均衡
- 知识缺口: 错误模式 → 建议文档
- 工具缺口: 未充分利用的工具
"""

from pathlib import Path
from typing import Any, Dict, List, Optional


class GapDetector:
    """三维缺口识别器"""

    def __init__(self):
        self._pipeline_file = Path.home() / ".zenskill" / "mirroring" / "pipeline.json"

    def detect_all(self) -> Dict[str, Any]:
        return {
            "skill_gaps": self._detect_skill_gaps(),
            "knowledge_gaps": self._detect_knowledge_gaps(),
            "tool_gaps": self._detect_tool_gaps(),
        }

    def _detect_skill_gaps(self) -> List[Dict]:
        """技能缺口：领域覆盖不均衡"""
        import json

        if not self._pipeline_file.exists():
            return []

        try:
            pipeline = json.loads(self._pipeline_file.read_text())
            nlp = pipeline.get("nlp", {})
            domains = nlp.get("domains", {})
        except Exception:
            return []

        if not domains:
            return []

        gaps = []
        # 找出得分 < 30% 但与其他高领域相关的领域
        for domain, score in domains.items():
            if score < 15:
                gaps.append({
                    "domain": domain,
                    "score": round(score, 1),
                    "suggestion": self._domain_suggestions.get(
                        domain, f"建议增加 {domain} 领域的实践"
                    ),
                })

        return gaps

    _domain_suggestions = {
        "cli_tui": "你的 CLI/TUI 使用率较低，尝试用 zenskill tui 探索交互式终端界面",
        "frontend": "前端领域覆盖率低，可考虑学习 React 或 Vue 生态",
        "data": "数据处理领域接触较少，推荐用 pandas 分析你的采集数据",
        "devops": "部署自动化方面可加强，尝试写 Dockerfile 或 CI 配置",
    }

    def _detect_knowledge_gaps(self) -> List[Dict]:
        """知识缺口：高频错误关键词 → 建议"""
        import json

        if not self._pipeline_file.exists():
            return []

        try:
            pipeline = json.loads(self._pipeline_file.read_text())
            nlp = pipeline.get("nlp", {})
            intents = nlp.get("intents", {})
            keywords = nlp.get("top_keywords", [])
        except Exception:
            return []

        gaps = []
        # debug 意图高 → 测试覆盖率可能不足
        debug_count = intents.get("debug", 0)
        if debug_count >= 3:
            gaps.append({
                "type": "testing",
                "severity": "medium",
                "message": f"调试意图出现 {debug_count} 次，考虑增加自动化测试或使用 zenskill doctor 诊断",
            })

        # refactor 意图高但没有对应的测试关键词
        refactor_count = intents.get("refactor", 0)
        if refactor_count >= 2 and "test" not in keywords and "测试" not in keywords:
            gaps.append({
                "type": "refactoring",
                "severity": "medium",
                "message": f"重构意图 {refactor_count} 次但缺少测试关键词，建议重构前先补齐测试",
            })

        return gaps

    def _detect_tool_gaps(self) -> List[Dict]:
        """工具缺口：有价值但未充分利用的工具"""
        import json

        if not self._pipeline_file.exists():
            return []

        try:
            pipeline = json.loads(self._pipeline_file.read_text())
            nlp = pipeline.get("nlp", {})
            domains = nlp.get("domains", {})
        except Exception:
            return []

        gaps = []
        # 检查是否有对应工具但未使用
        tool_map = {
            "cli_tui": "在 TUI 中按 0 打开 AI 对话，支持流式推理 + 可折叠思考过程",
            "ai_ml": "用 zenskill chat 直接对话，或 zenskill llm set 切换模型",
            "devops": "运行 zenskill collector run-all 自动采集开发数据",
            "backend": "用 zenskill mirror workflow 查看工作流模式分析",
        }

        for domain, suggestion in tool_map.items():
            score = domains.get(domain, 100)
            if 15 <= score < 30:  # 中等偏低的领域
                gaps.append({
                    "domain": domain,
                    "tool": suggestion,
                })

        return gaps
