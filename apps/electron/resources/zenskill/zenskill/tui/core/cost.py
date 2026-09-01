"""Token/成本计算 -- 纯逻辑，零 UI 依赖。

ZenSkill 6 家 provider 的估算定价。
"""

from __future__ import annotations

# 模型定价 (美元/1K tokens) -- 输入/输出
MODEL_PRICING = {
    # DeepSeek
    "deepseek-chat": (0.00027, 0.0011),
    "deepseek-coder": (0.00027, 0.0011),
    "deepseek-reasoner": (0.00055, 0.0022),
    # Mimo
    "mimo-v2.5": (0.001, 0.003),
    "mimo-v2.5-pro": (0.003, 0.01),
    # OpenAI
    "gpt-4o": (0.005, 0.015),
    "gpt-4o-mini": (0.00015, 0.0006),
    # Anthropic
    "claude-sonnet-4-20250514": (0.003, 0.015),
    "claude-haiku-35-20241022": (0.0008, 0.004),
    # Qwen
    "qwen-max": (0.002, 0.006),
    "qwen-plus": (0.0008, 0.002),
    # Volc
    "doubao-pro": (0.0008, 0.002),
    "doubao-lite": (0.0003, 0.0006),
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """估算调用成本 (美元)。"""
    input_price, output_price = MODEL_PRICING.get(model, (0.001, 0.003))
    input_cost = (prompt_tokens / 1000) * input_price
    output_cost = (completion_tokens / 1000) * output_price
    return input_cost + output_cost


def format_cost(cost: float) -> str:
    """格式化成本显示。"""
    if cost < 0.001:
        return f"${cost:.6f}"
    elif cost < 0.01:
        return f"${cost:.4f}"
    else:
        return f"${cost:.2f}"


def estimate_tokens_from_text(text: str) -> int:
    """粗略估算文本 token 数 (中文 ~1.5 字/token, 英文 ~4 字/token)。"""
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 1.5 + other_chars / 4)
