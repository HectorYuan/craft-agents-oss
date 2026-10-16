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

def _secrets_path() -> Path:
    # 路径动态解析（同 llm_config 教训）：import 时固化 HOME 会让测试 autouse
    # HOME 隔离失效、写真实用户目录 —— 读写一律走此函数
    return Path.home() / ".zenskill" / "llm-secrets.json"

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


# A3 读缓存（同 llm_connections 模式）：stat 键控 + deepcopy 隔离
_STORE_CACHE: dict[str, tuple[int, int, dict]] = {}


def _load_store() -> dict:
    import copy as _copy
    path = _secrets_path()
    try:
        st = path.stat()
        key = str(path)
        cached = _STORE_CACHE.get(key)
        if cached is not None and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
            return _copy.deepcopy(cached[2])
        data = json.loads(path.read_text(encoding="utf-8"))
        _STORE_CACHE[key] = (st.st_mtime_ns, st.st_size, data)
        return _copy.deepcopy(data)
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _save_store(store: dict) -> None:
    import copy as _copy
    path = _secrets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    try:
        st = path.stat()
        _STORE_CACHE[str(path)] = (st.st_mtime_ns, st.st_size, _copy.deepcopy(store))
    except OSError:
        _STORE_CACHE.pop(str(path), None)


def set_secret(provider: str, api_key: str, base_url: Optional[str] = None,
               model: Optional[str] = None, env_provider: Optional[str] = None) -> None:
    """保存 key（provider 可为引擎 provider 或 GUI 连接 slug）。

    env_provider：该 key 应注入的引擎 provider 名（slug 存储时与 key 不同，
    apply_to_env 用它映射 DEEPSEEK_API_KEY 等 env 名；CLI 按 provider 存时省略）。
    """
    entry: dict = {"api_key": api_key}
    if base_url:
        entry["base_url"] = base_url
    if model:
        entry["model"] = model
    if env_provider:
        entry["env_provider"] = env_provider
    store = _load_store()
    store[provider] = entry
    _save_store(store)
    try:
        os.chmod(_secrets_path(), 0o600)
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
        path = _secrets_path()
        if not path.exists():
            return 0
        store = _load_store()
        for key_name, entry in store.items():
            if not isinstance(entry, dict):
                continue
            # slug 存储的 entry 用 env_provider（引擎 provider）映射 env 名
            env_name = env_name_for(entry.get("env_provider") or key_name)
            if os.environ.get(env_name):
                continue
            key = entry.get("api_key")
            if key:
                os.environ[env_name] = key
                injected += 1
    except Exception as e:
        print(f"[llm-keyring] 警告：密钥库读取失败: {e}", file=sys.stderr)
    return injected
