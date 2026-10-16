"""S3 craft 风格 session.jsonl 写入辅助（对齐 vendor SessionManager 持久化机制）。

提供：
- `get_session_dir(workspace_root, session_id)`：vendor storage.ts:79-81 路径解析
- `default_session_header(...)`：35+ SESSION_PERSISTENT_FIELDS + 5 预计算字段初始 dict
- `atomic_write(path, content)`：vendor jsonl.ts:159-163 tmp + unlink + rename
- `read_header(path)`：8KB 偏移快速读 header（vendor jsonl.ts:80-97 同款）
- `update_precompute_fields(header, new_message)`：维护 messageCount/lastMessageRole/preview/tokenUsage/lastFinalMessageId
- `rewrite_header(path, header)`：整文件 rewrite（替换 line 1）
- `append_message_and_update_precompute(path, header, message_line)`：合并写
- `metadata_signature(header)` / `merge_header_with_external_metadata(...)` / `write_header_with_signature_check(...)`：vendor persistence-queue.ts:113-136 防覆盖
"""
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


# ── 路径解析（对齐 vendor storage.ts:79-81）───────────────────────────────

def get_session_dir(workspace_root: Path, session_id: str) -> Path:
    """`{workspaceRoot}/sessions/{sessionId}/` —— 与 vendor 完全一致。"""
    return Path(workspace_root) / "sessions" / session_id


def get_session_path(workspace_root: Path, session_id: str) -> Path:
    """`{workspaceRoot}/sessions/{sessionId}/session.jsonl`"""
    return get_session_dir(workspace_root, session_id) / "session.jsonl"


# ── Header 构造（vendor SESSION_PERSISTENT_FIELDS 35+ + 5 预计算）────

EMPTY_TOKEN_USAGE: Dict[str, Any] = {
    "inputTokens": 0,
    "outputTokens": 0,
    "totalTokens": 0,
    "contextTokens": 0,
    "costUsd": 0.0,
}


def default_session_header(
    session_id: str,
    workspace_root: Path,
    cwd: str = "",
    now_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """构造 vendor SessionHeader 初始 dict（35+ 字段默认 + 5 预计算字段）。"""
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    return {
        # Identity（"type": "session" 标记 header 行，让老 SessionManager.load 能识别）
        "type": "session",
        "id": session_id,
        "workspaceRootPath": str(workspace_root),
        "sdkSessionId": None,
        "sdkCwd": None,
        # Timestamps
        "createdAt": now,
        "lastUsedAt": now,
        "lastMessageAt": None,
        # Display
        "name": "",
        "isFlagged": False,
        "sessionStatus": "todo",
        "labels": [],
        "hidden": False,
        # Read tracking
        "lastReadMessageId": None,
        "hasUnread": False,
        # Config
        "enabledSourceSlugs": [],
        "permissionMode": "allow-all",
        "previousPermissionMode": None,
        "workingDirectory": cwd,
        # Model/Connection
        "model": None,
        "llmConnection": None,
        "connectionLocked": False,
        "thinkingLevel": None,
        # Sharing
        "sharedUrl": None,
        "sharedId": None,
        # Plan execution
        "pendingPlanExecution": None,
        # Archive
        "isArchived": False,
        "archivedAt": None,
        # Branching
        "branchFromMessageId": None,
        "branchFromSdkSessionId": None,
        "branchFromSessionPath": None,
        "branchFromSdkCwd": None,
        "branchFromSdkTurnId": None,
        # Remote transfer
        "transferredSessionSummary": None,
        "transferredSessionSummaryApplied": False,
        # Automation origin
        "triggeredBy": None,
        # Project binding
        "projectId": None,
        # Kanban / Task hierarchy
        "parentSessionId": None,
        "kanbanColumn": None,
        # Tasks Conductor
        "taskSlug": None,
        "taskRunId": None,
        "taskNodeId": None,
        "taskNodeCount": None,
        "taskDraft": False,
        # 5 预计算字段（vendor jsonl.ts:171-185 createSessionHeader）
        "messageCount": 0,
        "lastMessageRole": None,
        "preview": None,
        "tokenUsage": dict(EMPTY_TOKEN_USAGE),
        "lastFinalMessageId": None,
    }


# ── Atomic write（vendor jsonl.ts:159-163 同款）──────────────────────────

def atomic_write(path: Path, content: str) -> None:
    """tmp + unlink + rename —— 与 vendor persistence-queue.ts:148-152 一致。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    if path.exists():
        path.unlink()
    tmp.rename(path)


# ── 读 header（vendor jsonl.ts:80-97 8KB 偏移快速读）─────────────────────

def read_header(path: Path) -> Optional[Dict[str, Any]]:
    """读 session.jsonl line 1 header；坏行/不存在/解析失败返回 None。"""
    if not path.is_file():
        return None
    try:
        with open(path, "rb") as f:
            raw = f.read(8192)
    except OSError:
        return None
    first_line = raw.split(b"\n", 1)[0]
    if not first_line:
        return None
    try:
        d = json.loads(first_line)
    except json.JSONDecodeError:
        return None
    return d if isinstance(d, dict) else None


def read_messages_after_header(path: Path) -> list:
    """读 session.jsonl line 2+ messages（vendor parseMessagesResilient 风格：坏行跳过）。"""
    out = []
    if not path.is_file():
        return out
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return out
    for line in lines[1:]:  # skip header line
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # 坏行跳过（对齐 vendor jsonl.ts:287-299）
    return out


# ── 预计算字段维护（vendor jsonl.ts:171-185 + enqueuePersist 顺序）───────

_PREVIEW_MAX = 150  # vendor jsonl.ts:222 preview 长度


def _strip_preview(raw: str) -> str:
    """对齐 vendor jsonl.ts:222-238 preview 清理：剥 <edit_request>/<...>/[skill:...]/合并空白。"""
    import re
    s = re.sub(r"<edit_request>.*?</edit_request>", "", raw, flags=re.DOTALL)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\[skill:[^\]]+\]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:_PREVIEW_MAX]


def update_precompute_fields(
    header: Dict[str, Any], new_message: Dict[str, Any]
) -> Dict[str, Any]:
    """写新消息后更新 header 的 5 预计算字段。返回新 header（in-place 改并返回）。"""
    msg_type = new_message.get("type", "user")
    header["messageCount"] = int(header.get("messageCount", 0)) + 1
    header["lastMessageRole"] = msg_type
    header["lastUsedAt"] = int(time.time() * 1000)
    if "id" in new_message:
        header["lastMessageAt"] = new_message.get("timestamp") or header["lastUsedAt"]
    # preview：仅首条 user 消息时设
    if msg_type == "user" and not header.get("preview"):
        content = new_message.get("content", "")
        if isinstance(content, str):
            header["preview"] = _strip_preview(content)
    # lastFinalMessageId + tokenUsage 累加（仅非中间态 assistant）
    if msg_type == "assistant" and not new_message.get("isIntermediate", False):
        if new_message.get("id"):
            header["lastFinalMessageId"] = new_message["id"]
        if "tokenUsage" in new_message and isinstance(new_message["tokenUsage"], dict):
            current = header.get("tokenUsage") or dict(EMPTY_TOKEN_USAGE)
            for k in ("inputTokens", "outputTokens", "cacheReadTokens", "cacheCreationTokens"):
                current[k] = int(current.get(k, 0) or 0) + int(new_message["tokenUsage"].get(k, 0) or 0)
            current["totalTokens"] = int(current.get("inputTokens", 0) or 0) + int(current.get("outputTokens", 0) or 0)
            header["tokenUsage"] = current
    return header


# ── 整文件 rewrite（替换 line 1 header）──────────────────────────────

def rewrite_header(path: Path, header: Dict[str, Any]) -> None:
    """整文件 rewrite：line 1 = 新 header, line 2+ = 原 messages（保持顺序）。"""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    lines[0] = json.dumps(header, ensure_ascii=False) + "\n"
    atomic_write(path, "".join(lines))


# ── 合并写（append message + rewrite header）───────────────────────

def append_message_and_update_precompute(
    path: Path, header: Dict[str, Any], message: Dict[str, Any]
) -> Dict[str, Any]:
    """追加消息 + 维护 precompute（用 rewrite_header 合并）。

    与 vendor sessionPersistenceQueue 行为对齐：每条消息触发 header 预计算字段更新。
    """
    msg_line = json.dumps(message, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(msg_line)
    update_precompute_fields(header, message)
    rewrite_header(path, header)
    return header


# ── 防覆盖签名机制（vendor persistence-queue.ts:113-136）──────────────────

# vendor persistence-queue.ts:24-35 metadata 签名字段
_METADATA_SIG_FIELDS = (
    "name",
    "labels",
    "isFlagged",
    "sessionStatus",
    "permissionMode",
    "hasUnread",
    "lastReadMessageId",
)


def metadata_signature(header: Dict[str, Any]) -> Tuple[Tuple[str, Any], ...]:
    return tuple((k, header.get(k)) for k in _METADATA_SIG_FIELDS)


def merge_header_with_external_metadata(
    local: Dict[str, Any], disk: Dict[str, Any]
) -> Dict[str, Any]:
    """vendor persistence-queue.ts:127-129：disk 的 metadata 字段优先保留。

    本地负责：precompute 字段（messageCount/preview/lastMessageRole/lastFinalMessageId/tokenUsage）+
    SessionConfig（model/llmConnection/permissionMode 等本地状态）。
    Disk 负责：用户可能从其他进程（Desktop Mode GUI）改的 metadata（name/labels/isFlagged/...）。
    """
    merged = dict(local)
    for k in _METADATA_SIG_FIELDS:
        if k in disk:
            merged[k] = disk[k]
    return merged


def write_header_with_signature_check(
    path: Path,
    header: Dict[str, Any],
    last_signature: Optional[Tuple[Tuple[str, Any], ...]] = None,
) -> Tuple[Tuple[str, Any], ...]:
    """写 header 前检查 disk 是否被外部修改（vendor persistence-queue.ts:113-136 行为）。

    返回：新的 metadata signature（供下次比较）。
    """
    disk_header = read_header(path)
    if disk_header is None:
        # 新文件或不可读：直接写
        atomic_write(path, json.dumps(header, ensure_ascii=False) + "\n")
        return metadata_signature(header)
    disk_sig = metadata_signature(disk_header)
    if last_signature is None:
        # 首次写：merge disk metadata（disk 优先）
        merged = merge_header_with_external_metadata(header, disk_header)
        atomic_write(path, json.dumps(merged, ensure_ascii=False) + "\n")
        return metadata_signature(merged)
    local_sig = metadata_signature(header)
    if disk_sig != last_signature and disk_sig != local_sig:
        # 外部修改：保留 disk metadata
        merged = merge_header_with_external_metadata(header, disk_header)
        atomic_write(path, json.dumps(merged, ensure_ascii=False) + "\n")
        return metadata_signature(merged)
    atomic_write(path, json.dumps(header, ensure_ascii=False) + "\n")
    return local_sig
