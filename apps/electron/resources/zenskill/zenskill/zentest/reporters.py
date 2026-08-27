"""
ZenTest 多格式报告器

支持 text / json / html / junit 格式输出测试报告。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .core import TestReport


# ═══════════════════════════════════════════════════════════════
# 报告器基类
# ═══════════════════════════════════════════════════════════════

class BaseReporter:
    """报告器基类"""

    def __init__(self, report: TestReport):
        self.report = report

    def generate(self) -> str:
        raise NotImplementedError

    def save(self, path: str | Path) -> Path:
        content = self.generate()
        fp = Path(path)
        fp.write_text(content, encoding="utf-8")
        return fp


# ═══════════════════════════════════════════════════════════════
# TextReporter
# ═══════════════════════════════════════════════════════════════

class TextReporter(BaseReporter):
    """纯文本格式报告器 — 可直接打印到终端"""

    def generate(self) -> str:
        r = self.report
        lines = [
            "=" * 50,
            f"  ZenTest 报告",
            f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 50,
            f"  总计:   {r.total}",
            f"  通过:   {r.passed_count}",
            f"  失败:   {r.failed_count}",
            f"  成功率: {r.success_rate:.1f}%",
            f"  耗时:   {r.duration_ms:.0f}ms",
        ]
        if r.failed_count > 0:
            lines.append("")
            lines.append("  ❌ 失败详情:")
            for tr in r.failed():
                lines.append(f"    [{tr.category.value}] {tr.name}")
                lines.append(f"      原因: {tr.error or '未知'}")

        lines.append("=" * 50)
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# JsonReporter
# ═══════════════════════════════════════════════════════════════

class JsonReporter(BaseReporter):
    """JSON 格式报告器 — 适合 CI 和程序消费"""

    def generate(self) -> str:
        r = self.report
        data: Dict[str, Any] = {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total": r.total,
                "passed": r.passed_count,
                "failed": r.failed_count,
                "success_rate": round(r.success_rate, 1),
                "duration_ms": round(r.duration_ms),
            },
            "results": [
                {
                    "name": tr.name,
                    "category": tr.category.value,
                    "passed": tr.passed,
                    "error": tr.error,
                    "duration_ms": round(tr.duration_ms),
                }
                for tr in r.results
            ],
        }
        return json.dumps(data, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# HtmlReporter
# ═══════════════════════════════════════════════════════════════

class HtmlReporter(BaseReporter):
    """HTML 格式报告器 — 适合浏览器查看"""

    TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>ZenTest 报告</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }}
h1 {{ color: #333; }}
.summary {{ display: flex; gap: 1rem; margin: 1rem 0; }}
.card {{ padding: 1rem; border-radius: 8px; background: #f5f5f5; flex: 1; }}
.card.pass {{ background: #e8f5e9; color: #2e7d32; }}
.card.fail {{ background: #ffebee; color: #c62828; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 0.5rem; text-align: left; border-bottom: 1px solid #ddd; }}
th {{ background: #f5f5f5; }}
tr.failed {{ background: #fff3e0; }}
.status-pass {{ color: #2e7d32; }}
.status-fail {{ color: #c62828; }}
</style>
</head>
<body>
<h1>🧪 ZenTest 报告</h1>
<p>生成时间: {timestamp}</p>
<div class="summary">
  <div class="card"><strong>总计</strong><br>{total}</div>
  <div class="card pass"><strong>通过</strong><br>{passed}</div>
  <div class="card fail"><strong>失败</strong><br>{failed}</div>
  <div class="card"><strong>成功率</strong><br>{rate}%</div>
  <div class="card"><strong>耗时</strong><br>{duration}ms</div>
</div>
<h2>测试详情</h2>
<table><thead><tr><th>名称</th><th>分类</th><th>状态</th><th>错误</th></tr></thead>
<tbody>
{rows}
</tbody></table>
</body></html>"""

    def generate(self) -> str:
        r = self.report
        rows = ""
        for tr in r.results:
            status_cls = "status-pass" if tr.passed else "status-fail"
            status_text = "✅ 通过" if tr.passed else "❌ 失败"
            row_cls = " failed" if not tr.passed else ""
            error = tr.error or ""
            rows += (
                f'<tr class="{row_cls}">'
                f"<td>{tr.name}</td>"
                f"<td>{tr.category.value}</td>"
                f'<td class="{status_cls}">{status_text}</td>'
                f"<td>{error}</td>"
                f"</tr>\n"
            )
        return self.TEMPLATE.format(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total=r.total,
            passed=r.passed_count,
            failed=r.failed_count,
            rate=round(r.success_rate, 1),
            duration=round(r.duration_ms),
            rows=rows,
        )


# ═══════════════════════════════════════════════════════════════
# JUnitXmlReporter
# ═══════════════════════════════════════════════════════════════

class JUnitXmlReporter(BaseReporter):
    """JUnit XML 报告器 — CI 系统兼容"""

    def generate(self) -> str:
        r = self.report
        failures = r.failed_count
        tests = r.total
        time_sec = round(r.duration_ms / 1000, 3)
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<testsuite name="zentest" tests="{tests}" '
            f'failures="{failures}" time="{time_sec}">',
        ]
        for tr in r.results:
            cls_name = f"zentest.{tr.category.value}"
            lines.append(
                f'  <testcase classname="{cls_name}" '
                f'name="{tr.name}" time="0.0">'
            )
            if not tr.passed:
                msg = (tr.error or "Unknown error").replace("<", "&lt;")
                lines.append(
                    f'    <failure message="{msg}"/>'
                )
            lines.append("  </testcase>")
        lines.append("</testsuite>")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 工厂函数
# ═══════════════════════════════════════════════════════════════

REPORTER_MAP: Dict[str, type[BaseReporter]] = {
    "text": TextReporter,
    "json": JsonReporter,
    "html": HtmlReporter,
    "junit": JUnitXmlReporter,
}


def get_reporter(report: TestReport, fmt: str) -> BaseReporter:
    """根据格式名获取报告器实例"""
    cls = REPORTER_MAP.get(fmt)
    if cls is None:
        raise ValueError(f"不支持的格式: {fmt}，可选: {', '.join(REPORTER_MAP)}")
    return cls(report)
