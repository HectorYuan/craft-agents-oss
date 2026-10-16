"""Pages grants 持久化与安全执行（P1：pages grants 真实现）。

格式 SSOT: vendor packages/core/src/types/page.ts（PageActionGrant/PageActionRequest/PageActionResult）
存储: {workspace_root}/pages/{slug}/page.json 的 grants 数组（宿主 watcher 兼容）

安全模型（对齐 vendor 语义）:
- grant 绑定 contentDigest（页面内容变更即失效）+ 硬过期
- lease nonce 校验（iframe 身份，无 Origin 环境的帧验证）
- invocation 必须与 descriptor 匹配（mcp: toolName 一致；script: 零参数纯触发）
- api 类暂不支持（Server Mode 无 API broker，返回明确错误）
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_GRANT_ID_RE = re.compile(r"^grant_[0-9a-f]{8}$")
_SCRIPT_TRAVERSAL_RE = re.compile(r"(^/|\.\.)")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _hex8(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()[:8]


class PagesGrantsStore:
    """page.json grants 数组读写（原子写，宿主 watcher 兼容）。"""

    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)

    def _page_json_path(self, page_slug: str) -> Path:
        # slug 防穿越：只允许字母数字连字符
        if not re.match(r"^[\w-]+$", page_slug):
            raise ValueError(f"invalid page slug: {page_slug}")
        return self.workspace_root / "pages" / page_slug / "page.json"

    def _load_page(self, page_slug: str) -> dict:
        p = self._page_json_path(page_slug)
        if not p.exists():
            raise FileNotFoundError(f"page not found: {page_slug}")
        return json.loads(p.read_text(encoding="utf-8"))

    def _save_page(self, page_slug: str, cfg: dict) -> None:
        p = self._page_json_path(page_slug)
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".page.json.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, p)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def get_content_digest(self, page_slug: str) -> str | None:
        cfg = self._load_page(page_slug)
        return cfg.get("contentDigest")

    # ── CRUD ──

    def list_grants(self, page_slug: str) -> list[dict]:
        return self._load_page(page_slug).get("grants") or []

    def issue_grant(
        self,
        page_slug: str,
        description: str,
        action: dict,
        expires_in_ms: int = 30 * 24 * 3600 * 1000,  # 默认 30 天
    ) -> dict:
        cfg = self._load_page(page_slug)
        digest = cfg.get("contentDigest")
        if not digest:
            # seed 模板无 digest（宿主首次渲染时写入）——此处实时计算并持久化，
            # 与 createLease 的 _page_content_and_digest 算法一致（sha256 of index.html）
            index_html = self._page_json_path(page_slug).parent / "index.html"
            if not index_html.exists():
                raise ValueError(f"page has no index.html: {page_slug}")
            digest = hashlib.sha256(index_html.read_bytes()).hexdigest()
            cfg["contentDigest"] = digest
            self._save_page(page_slug, cfg)
        action_kind = action.get("kind", "")
        seed = f"{page_slug}:{action_kind}:{_now_ms()}"
        grant = {
            "id": f"grant_{_hex8(seed)}",
            "description": description,
            "action": action,
            "contentDigest": digest,
            "createdAt": _now_ms(),
            "expiresAt": _now_ms() + expires_in_ms,
        }
        grants = cfg.get("grants") or []
        grants.append(grant)
        cfg["grants"] = grants
        self._save_page(page_slug, cfg)
        return grant

    def revoke_grant(self, page_slug: str, grant_id: str) -> bool:
        cfg = self._load_page(page_slug)
        grants = cfg.get("grants") or []
        before = len(grants)
        grants = [g for g in grants if g.get("id") != grant_id]
        if len(grants) == before:
            return False
        cfg["grants"] = grants
        self._save_page(page_slug, cfg)
        return True

    # ── 验证 ──

    def find_valid_grant(self, page_slug: str, grant_id: str, content_digest: str) -> dict:
        """查找 grant 并校验 digest 绑定 + 过期。不匹配/过期/不存在均 raise。"""
        for g in self.list_grants(page_slug):
            if g.get("id") != grant_id:
                continue
            if g.get("contentDigest") != content_digest:
                raise PermissionError("grant bound to different content digest")
            if g.get("expiresAt", 0) < _now_ms():
                raise PermissionError("grant expired")
            return g
        raise PermissionError(f"grant not found: {grant_id}")


class PageActionExecutor:
    """安全执行器：lease + grant 双验证 → mcp/script 动作。"""

    def __init__(self, workspace_root: Path, call_mcp_tool, page_leases: dict):
        self.store = PagesGrantsStore(workspace_root)
        self._call_mcp_tool = call_mcp_tool  # 注入 ws_server 的进程内直调
        self._page_leases = page_leases      # 注入 ws_server 的 lease dict
        self._executed_requests: dict[str, set[str]] = {}  # leaseId → {requestId}（防重放）

    async def execute(self, workspace_id: str, request: dict) -> dict:
        """执行 PageActionRequest → PageActionResult（永不 raise，错误在 result 内）。"""
        start = time.monotonic()
        request_id = request.get("requestId", "")
        page_slug = request.get("pageSlug", "")
        lease_id = request.get("leaseId", "")
        nonce = request.get("nonce", "")
        grant_id = request.get("grantId", "")
        invocation = request.get("invocation") or {}

        def _err(msg: str) -> dict:
            return {"requestId": request_id, "ok": False, "error": msg,
                    "durationMs": int((time.monotonic() - start) * 1000)}

        # 1) lease 验证
        lease = self._page_leases.get(lease_id)
        if not lease or lease.get("nonce") != nonce or lease.get("pageSlug") != page_slug:
            return _err("invalid or expired lease")

        # 2) 防重放（per-lease requestId 去重）
        seen = self._executed_requests.setdefault(lease_id, set())
        if request_id in seen:
            return _err("duplicate requestId")
        seen.add(request_id)

        # 3) grant 验证（digest 绑定 + 过期）
        digest = lease.get("contentDigest", "")
        try:
            grant = self.store.find_valid_grant(page_slug, grant_id, digest)
        except PermissionError as exc:
            return _err(str(exc))

        descriptor = grant.get("action") or {}
        kind = descriptor.get("kind")
        inv_kind = invocation.get("kind")

        # 4) descriptor ↔ invocation 匹配 + 执行
        if kind == "mcp" and inv_kind == "mcp":
            if invocation.get("toolName") != descriptor.get("toolName"):
                return _err("toolName does not match grant descriptor")
            try:
                result_text = await self._call_mcp_tool(
                    workspace_id, descriptor.get("sourceSlug", ""),
                    descriptor["toolName"], invocation.get("args") or {})
                body = json.loads(result_text) if isinstance(result_text, str) else result_text
                return {"requestId": request_id, "ok": True, "body": body,
                        "durationMs": int((time.monotonic() - start) * 1000)}
            except Exception as exc:
                return _err(f"mcp tool failed: {exc}")

        elif kind == "script" and inv_kind == "script":
            return self._run_script(request_id, page_slug, descriptor, start)

        elif kind == "api":
            return _err("api-kind actions require the Desktop Mode broker (not supported in Server Mode)")

        else:
            return _err(f"invocation kind '{inv_kind}' does not match grant kind '{kind}'")

    def _run_script(self, request_id: str, page_slug: str, descriptor: dict, start: float) -> dict:
        def _err(msg: str) -> dict:
            return {"requestId": request_id, "ok": False, "error": msg,
                    "durationMs": int((time.monotonic() - start) * 1000)}

        script = descriptor.get("script", "")
        if not script or _SCRIPT_TRAVERSAL_RE.search(script):
            return _err("invalid script path")
        runtime = descriptor.get("runtime", "bun")
        argv_bin = {"bun": "bun", "node": "node", "python3": sys.executable,
                    "python": sys.executable}.get(runtime)
        if not argv_bin:
            return _err(f"unsupported runtime: {runtime}")

        script_path = (self.store.workspace_root / script).resolve()
        ws_root = self.store.workspace_root.resolve()
        if not str(script_path).startswith(str(ws_root)):
            return _err("script path escapes workspace")
        if not script_path.exists():
            return _err(f"script not found: {script}")

        args = descriptor.get("args") or []  # 固定参数，approval 时钉死
        timeout_ms = 30_000
        try:
            proc = subprocess.run(
                [argv_bin, str(script_path)] + [str(a) for a in args],
                capture_output=True, text=True, timeout=timeout_ms / 1000,
                cwd=str(self.store.workspace_root), check=False,
            )
            body = (proc.stdout or proc.stderr or "")[:2000]
            return {"requestId": request_id, "ok": proc.returncode == 0,
                    "status": proc.returncode, "body": body,
                    "durationMs": int((time.monotonic() - start) * 1000)}
        except subprocess.TimeoutExpired:
            return _err(f"script timeout after {timeout_ms}ms")
        except Exception as exc:
            return _err(f"script execution failed: {exc}")

    def cancel(self, lease_id: str, request_id: str) -> bool:
        """标记取消——同步执行中的无法中断，只做簿记。"""
        seen = self._executed_requests.get(lease_id)
        if seen and request_id in seen:
            return True  # 已执行完成，无需取消
        return False
