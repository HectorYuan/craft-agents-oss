"""
LLM 密钥本地保险库（provider → API key）

存储：~/.zenskill/llm-secrets.json
- api_key 明文落盘 + 文件 0600（gh/aws/gcloud 惯例）；DPAPI 跨进程在本机
  实测不可靠（CryptUnprotectData 随机失败），升级路径：OS keyring

解析链优先级：环境变量（最高，CI/测试）→ 本保险库 → 交互输入
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

SECRETS_PATH = Path.home() / ".zenskill" / "llm-secrets.json"

# provider → 引擎/环境变量名（与 runtime/agent/providers 注册表对齐）
ENV_KEY_NAMES = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "volc": "ARK_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "mimo": "MIMO_API_KEY",
}

def env_name_for(provider: str) -> str:
    return ENV_KEY_NAMES.get(provider, f"{provider.upper()}_API_KEY")


# ============================================================
# DPAPI（Windows，ctypes 直调 crypt32，零第三方依赖）
# ============================================================


def _load_store() -> dict:
    if not SECRETS_PATH.exists():
        return {}
    try:
        return json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_store(store: dict) -> None:
    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_PATH.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(SECRETS_PATH, 0o600)
    except OSError:
        pass


def set_secret(provider: str, api_key: str, base_url: Optional[str] = None,
               model: Optional[str] = None) -> None:
    """保存 provider 的 API key（Windows 经 DPAPI 加密）。"""
    store = _load_store()
    entry: dict = {"api_key": api_key}
    if base_url:
        entry["base_url"] = base_url
    if model:
        entry["model"] = model
    store = _load_store()
    entry: dict = {"api_key": api_key}
    if base_url:
        entry["base_url"] = base_url
    if model:
        entry["model"] = model
    store[provider] = entry
    _save_store(store)
    try:
        os.chmod(SECRETS_PATH, 0o600)
    except OSError:
        pass


def get_secret(provider: str) -> Optional[dict]:
    """返回 {api_key, base_url?, model?}（api_key 已解密）或 None。"""
    entry = _load_store().get(provider)
    if not isinstance(entry, dict):
        return None
    return dict(entry)


def forget(provider: str) -> bool:
    store = _load_store()
    if provider in store:
        del store[provider]
        _save_store(store)
        return True
    return False


def stored_providers() -> list[str]:
    return list(_load_store().keys())


def apply_to_env() -> int:
    """把保险库中的 key 注入 os.environ（已存在的环境变量优先，不覆盖）。

    在 CLI 入口最早处调用一次；engine 子进程继承注入后的环境。
    返回注入的 provider 数。
    """
    injected = 0
    try:
        if not SECRETS_PATH.exists():
            return 0
        store = _load_store()
        for provider, entry in store.items():
            if not isinstance(entry, dict):
                continue
            env_name = env_name_for(provider)
            if os.environ.get(env_name):
                continue
            key = entry.get("api_key")
            if key:
                os.environ[env_name] = key
                injected += 1
    except Exception as e:
        print(f"[llm-keyring] 警告：密钥库读取失败: {e}", file=sys.stderr)
    return injected
