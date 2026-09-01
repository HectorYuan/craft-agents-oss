"""
隐私保护层

Phase 9A: 用户画像数据层
提供数据采集控制、加密、匿名化、GDPR 导出/删除等功能
"""

import hashlib
import json
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .models import EventType, UserPrivacyPrefs

try:
    from cryptography.fernet import Fernet
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False

# 敏感 key 模式 - 包含这些关键词的 context key 会被过滤
SENSITIVE_KEY_PATTERNS = [
    "password", "secret", "token", "api_key", "credential",
    "auth", "private", "ssh", "pgp",
]


def _is_sensitive_key(key: str) -> bool:
    """判断 key 是否包含敏感信息"""
    key_lower = key.lower()
    return any(pattern in key_lower for pattern in SENSITIVE_KEY_PATTERNS)


class PrivacyLayer:
    """隐私保护层"""

    def __init__(self, data_dir: Optional[Path] = None):
        self._mirroring_dir = data_dir or self._get_default_dir()
        self._mirroring_dir.mkdir(parents=True, exist_ok=True)
        self._prefs_file = self._mirroring_dir / "privacy_prefs.json"
        self._key_file = self._mirroring_dir / "encryption.key"
        self._prefs = self._load_prefs()

    @staticmethod
    def _get_default_dir() -> Path:
        from zenskill.core.paths import get_mirroring_dir
        return get_mirroring_dir()

    def _load_prefs(self) -> UserPrivacyPrefs:
        """加载隐私偏好"""
        if self._prefs_file.exists():
            with open(self._prefs_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return UserPrivacyPrefs.from_dict(data)
        # 首次使用，保存默认偏好
        prefs = UserPrivacyPrefs(last_modified=datetime.now().isoformat())
        self._save_prefs(prefs)
        return prefs

    def _save_prefs(self, prefs: UserPrivacyPrefs) -> None:
        """持久化隐私偏好"""
        prefs.last_modified = datetime.now().isoformat()
        temp_path = self._prefs_file.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(prefs.to_dict(), f, indent=2, ensure_ascii=False)
        temp_path.rename(self._prefs_file)
        self._prefs = prefs

    def should_collect(self, event_type: EventType) -> bool:
        """判断是否应该采集某类事件"""
        if not self._prefs.consent_given:
            return False
        return event_type.value not in self._prefs.excluded_event_types

    def get_prefs(self) -> UserPrivacyPrefs:
        """获取当前隐私偏好"""
        return self._prefs

    def update_prefs(self, **kwargs: Any) -> None:
        """更新隐私偏好"""
        prefs_dict = self._prefs.to_dict()
        for key, value in kwargs.items():
            if key in prefs_dict:
                # 类型转换
                if key == "retention_days" or key == "anonymize_after_days":
                    value = int(value)
                elif key == "consent_given" or key == "encryption_enabled":
                    value = str(value).lower() in ("true", "1", "yes")
                prefs_dict[key] = value
        self._save_prefs(UserPrivacyPrefs.from_dict(prefs_dict))

    def filter_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """过滤敏感数据，移除包含敏感关键词的 key"""
        return {k: v for k, v in data.items() if not _is_sensitive_key(k)}

    def hash_user_input(self, text: str) -> Dict[str, Any]:
        """对用户输入进行数据最小化处理 - 只保留行为信号"""
        return {
            "input_hash": hashlib.sha256(text.encode()).hexdigest()[:16],
            "input_length": len(text),
        }

    def enable_encryption(self) -> str:
        """启用加密，返回 key 指纹"""
        if not _HAS_CRYPTO:
            raise ImportError(
                "加密功能需要 cryptography 库: pip install cryptography"
            )
        if not self._key_file.exists():
            key = Fernet.generate_key()
            with open(self._key_file, "wb") as f:
                f.write(key)
            os.chmod(self._key_file, 0o600)
        self.update_prefs(encryption_enabled=True)
        # 返回 key 指纹 (不暴露实际 key)
        with open(self._key_file, "rb") as f:
            key = f.read()
        return hashlib.sha256(key).hexdigest()[:16]

    def disable_encryption(self) -> None:
        """禁用加密（不删除 key 文件，以便解密历史数据）"""
        self.update_prefs(encryption_enabled=False)

    def _get_fernet(self) -> Optional["Fernet"]:
        """获取 Fernet 实例"""
        if not _HAS_CRYPTO or not self._prefs.encryption_enabled:
            return None
        if not self._key_file.exists():
            return None
        with open(self._key_file, "rb") as f:
            key = f.read()
        return Fernet(key)

    def encrypt_sensitive(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """加密 context 中的敏感字段值"""
        fernet = self._get_fernet()
        if fernet is None:
            return data
        encrypted = {}
        for k, v in data.items():
            if isinstance(v, str) and len(v) > 0:
                try:
                    encrypted[k] = f"enc:{fernet.encrypt(v.encode()).decode()}"
                except Exception:
                    encrypted[k] = v
            else:
                encrypted[k] = v
        return encrypted

    def decrypt_sensitive(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """解密 context 中的加密字段值"""
        fernet = self._get_fernet()
        if fernet is None:
            return data
        decrypted = {}
        for k, v in data.items():
            if isinstance(v, str) and v.startswith("enc:"):
                try:
                    decrypted[k] = fernet.decrypt(v[4:].encode()).decode()
                except Exception:
                    decrypted[k] = v
            else:
                decrypted[k] = v
        return decrypted

    def get_data_summary(self) -> Dict[str, Any]:
        """获取数据概览"""
        summary: Dict[str, Any] = {
            "mirroring_dir": str(self._mirroring_dir),
            "files": [],
            "total_size_bytes": 0,
            "consent_given": self._prefs.consent_given,
            "encryption_enabled": self._prefs.encryption_enabled,
        }
        if not self._mirroring_dir.exists():
            return summary
        for f in self._mirroring_dir.iterdir():
            if f.is_file():
                size = f.stat().st_size
                summary["files"].append({"name": f.name, "size_bytes": size})
                summary["total_size_bytes"] += size
        return summary

    def export_all_data(self, output_path: Path) -> int:
        """导出所有镜像数据为 zip 文件 (GDPR)"""
        file_count = 0
        seen_names: set = set()
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # 导出偏好
            zf.writestr("privacy_prefs.json", json.dumps(self._prefs.to_dict(), indent=2))
            seen_names.add("privacy_prefs.json")
            file_count += 1
            # 导出所有数据文件
            if self._mirroring_dir.exists():
                for f in self._mirroring_dir.iterdir():
                    if f.is_file() and f.name != "encryption.key" and f.name not in seen_names:
                        zf.write(f, f.name)
                        seen_names.add(f.name)
                        file_count += 1
        return file_count

    def delete_all_data(self) -> int:
        """删除所有镜像数据 (GDPR)"""
        deleted = 0
        if not self._mirroring_dir.exists():
            return 0
        for f in self._mirroring_dir.iterdir():
            if f.is_file():
                f.unlink()
                deleted += 1
        # 重新初始化默认偏好
        self._save_prefs(UserPrivacyPrefs())
        return deleted

    def anonymize_old_data(self) -> int:
        """匿名化超期事件数据"""
        events_file = self._mirroring_dir / "events.jsonl"
        if not events_file.exists():
            return 0

        threshold = datetime.now().timestamp() - (self._prefs.anonymize_after_days * 86400)
        anonymized = 0
        lines = []

        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if event.get("timestamp", 0) < threshold:
                        event["context"] = {}
                        event["action"] = "[anonymized]"
                        anonymized += 1
                    lines.append(json.dumps(event, ensure_ascii=False))
                except (json.JSONDecodeError, KeyError):
                    lines.append(line)

        if anonymized > 0:
            temp_path = events_file.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            temp_path.rename(events_file)

        return anonymized
