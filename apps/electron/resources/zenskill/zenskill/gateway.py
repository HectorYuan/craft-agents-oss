"""ZenSkill 多租户 Gateway — EduAgent 账户绑定 + 每用户隔离引擎。

设计（docs/ZENLEARNING_TENANCY_PLAN.md §3）：
- 身份：验证 EduAgent 签发的 access JWT（HS256 共享密钥，claims: sub/role/type/exp），
  不自建账户。
- 隔离：每用户一个容器（zs-t-<user_key>，loopback 端口）+ 独立数据目录
  （ZG_TENANT_ROOT/<user_key> bind mount 到容器 /root/.zenskill）。引擎零改动。
- 回收：空闲超时 docker rm -f（数据在宿主机目录，安全）。
- 路由：静态文件 gateway 自持（webui dist），/ws 与 /api/* 反代到该用户的引擎；
  引擎自身 token 鉴权保持开启（gateway 代持 tenant token）。

认证流：
  POST /api/auth {password: <EduAgent access JWT>}
    → 本地验签 → 拉起/复用租户引擎 → 用 tenant token 调引擎 /api/auth
    → 透传引擎 Set-Cookie + 附加 gateway cookie（zs_gw，HMAC 签名 user_key+exp）
  后续 /ws、/api/*：gateway cookie 定路由，Cookie 头整体转发给引擎（引擎自验自身 cookie）。

配置全部走环境变量（见 ENV_DEFAULTS）。启动：python -m zenskill.gateway
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

ENV_DEFAULTS = {
    "ZG_LISTEN": "127.0.0.1",
    "ZG_PORT": "9200",
    "ZG_SECRET": "",  # EduAgent AUTH_SECRET（必填）
    "ZG_GATEWAY_SECRET": "",  # gateway cookie 签名密钥（必填）
    "ZG_TENANT_ROOT": "/opt/zenskill-tenants",
    "ZG_REGISTRY": "/opt/zenskill-gateway/registry.json",
    "ZG_WEBUI_DIST": "",  # 静态 dist 目录（必填）
    "ZG_PORT_MIN": "9300",
    "ZG_PORT_MAX": "9349",
    "ZG_IDLE_TIMEOUT": "1800",
    "ZG_REAP_INTERVAL": "60",
    "ZG_IMAGE": "zenskill:latest",
    "ZG_EDU_BASE": "http://127.0.0.1:8808",
    "ZG_JWT_ALG": "HS256",
    "ZG_ENGINE_STARTUP_TIMEOUT": "25",
    "ZG_COOKIE_NAME": "zs_gw",
    "ZG_COOKIE_TTL": "604800",
    "ZG_LOGIN_HTML": "",  # 自定义登录页覆盖（缺省用 dist 内 login.html）
    "ZG_RATE_LOGIN": "10/300",  # /api/login、/api/auth 按 IP 限速：次/秒窗口
}

GW_COOKIE_MAX_AGE = None  # 由 ZG_COOKIE_TTL 决定


def _cfg(name: str) -> str:
    return os.environ.get(name, ENV_DEFAULTS[name])


class RateLimiter:
    """内存滑动窗口限速（单进程网关足够；按 IP 维度）。"""

    def __init__(self, spec: str):
        count, _, window = spec.partition("/")
        self.max_events = max(1, int(count))
        self.window_s = max(1, int(window))
        self._events: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        recent = [t for t in self._events.get(key, []) if now - t < self.window_s]
        self._events[key] = recent
        if len(recent) >= self.max_events:
            return False
        recent.append(now)
        return True


# ============================================================
# JWT（HS256 手写验签，零依赖，与 ws_server._verify_jwt 同风格）
# ============================================================


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def verify_edu_token(token: str, secret: str, expected_type: str = "access") -> Optional[dict]:
    """验证 EduAgent access JWT。返回 claims（sub/role/type/exp/iat）或 None。"""
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        header = json.loads(_b64url_decode(header_b64))
        if header.get("alg", "").upper() != _cfg("ZG_JWT_ALG"):
            return None
        signing_input = f"{header_b64}.{payload_b64}".encode()
        expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
            return None
        claims = json.loads(_b64url_decode(payload_b64))
        if claims.get("type") != expected_type:
            return None
        if int(claims.get("exp", 0)) < time.time():
            return None
        if not claims.get("sub"):
            return None
        return claims
    except (ValueError, KeyError, TypeError):
        return None


def make_hs256_token(payload: dict, secret: str) -> str:
    """测试辅助：按 EduAgent 同结构签发 JWT。"""
    header = {"alg": "HS256", "typ": "JWT"}
    seg = lambda obj: base64.urlsafe_b64encode(
        json.dumps(obj, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    signing_input = f"{seg(header)}.{seg(payload)}"
    sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{base64.urlsafe_b64encode(sig).rstrip(b'=').decode()}"


def resolve_static_target(dist_root: Path, rel: str) -> Optional[Path]:
    """resolve 后返回 dist 根内的目标路径；逃逸 dist 根（含前缀同名兄弟目录，
    如 dist-backup）时返回 None。"""
    root = dist_root.resolve()
    target = (dist_root / rel.lstrip("/")).resolve()
    if target != root and not str(target).startswith(str(root) + os.sep):
        return None
    return target


def tenant_key_from_sub(sub: str) -> Optional[str]:
    key = re.sub(r"[^a-zA-Z0-9_-]", "", f"u{sub}")
    return key[:40] if key and key != "u" else None


def ws_url_for(proto: str, host: str) -> str:
    """浏览器可用的 WS 地址：scheme 跟随 X-Forwarded-Proto（反代 HTTPS
    时后端 scheme 仍为 http），host 跟随请求头。"""
    ws_scheme = "wss" if proto == "https" else "ws"
    return f"{ws_scheme}://{host}/ws"


# ============================================================
# gateway cookie（HMAC 签名 user_key + exp）
# ============================================================


def sign_gateway_cookie(user_key: str, secret: str, ttl: int) -> str:
    exp = int(time.time()) + ttl
    sig = hmac.new(secret.encode(), f"{user_key}:{exp}".encode(), hashlib.sha256).hexdigest()
    return f"{user_key}:{exp}:{sig}"


def verify_gateway_cookie(value: str, secret: str) -> Optional[str]:
    try:
        user_key, exp_str, sig = value.rsplit(":", 2)
        expected = hmac.new(
            secret.encode(), f"{user_key}:{exp_str}".encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        if int(exp_str) < time.time():
            return None
        if not re.fullmatch(r"u[a-zA-Z0-9_-]{1,39}", user_key):
            return None
        return user_key
    except (ValueError, TypeError):
        return None


# ============================================================
# 租户注册表
# ============================================================


class TenantRegistry:
    def __init__(self, path: str):
        self.path = Path(path)
        self.entries: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self.entries = json.loads(self.path.read_text())
            except (ValueError, OSError):
                self.entries = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.entries, indent=2))
        tmp.replace(self.path)

    def get(self, user_key: str) -> Optional[dict]:
        return self.entries.get(user_key)

    def put(self, user_key: str, entry: dict) -> None:
        self.entries[user_key] = entry
        self.save()

    def remove(self, user_key: str) -> None:
        self.entries.pop(user_key, None)
        self.save()


# ============================================================
# Docker 引擎后端
# ============================================================


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check, timeout=60
    )


def container_running(name: str) -> bool:
    try:
        r = _docker("inspect", "-f", "{{.State.Running}}", name, check=False)
        return r.stdout.strip() == "true"
    except (subprocess.SubprocessError, OSError):
        return False


class DockerBackend:
    def __init__(self, tenant_root: str, image: str, port_min: int, port_max: int):
        self.tenant_root = Path(tenant_root)
        self.image = image
        self.port_min = port_min
        self.port_max = port_max

    @staticmethod
    def container_name(user_key: str) -> str:
        return f"zs-t-{user_key}"

    def build_run_args(self, user_key: str, port: int, token: str) -> list[str]:
        data_dir = self.tenant_root / user_key
        data_dir.mkdir(parents=True, exist_ok=True)
        return [
            "run", "-d",
            "--name", self.container_name(user_key),
            "--restart", "no",
            "-p", f"127.0.0.1:{port}:9100",
            "-v", f"{data_dir}:/root/.zenskill",
            "-e", f"ZENSKILL_TOKEN={token}",
            "-e", "PYTHONUNBUFFERED=1",
            self.image,
        ]

    def _port_free(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return True
            except OSError:
                return False

    def allocate_port(self, registry: TenantRegistry) -> int:
        used = {e["port"] for e in registry.entries.values()}
        for port in range(self.port_min, self.port_max + 1):
            if port not in used and self._port_free(port):
                return port
        raise RuntimeError("no free port in ZG_PORT range")

    def spawn(self, user_key: str, port: int, token: str) -> None:
        _docker(*self.build_run_args(user_key, port, token))

    def stop(self, user_key: str) -> None:
        name = self.container_name(user_key)
        _docker("rm", "-f", name, check=False)


# ============================================================
# Gateway 应用
# ============================================================


class Gateway:
    def __init__(self) -> None:
        self.secret = _cfg("ZG_SECRET")
        self.gw_secret = _cfg("ZG_GATEWAY_SECRET")
        self.webui_dist = Path(_cfg("ZG_WEBUI_DIST")) if _cfg("ZG_WEBUI_DIST") else None
        self.cookie_name = _cfg("ZG_COOKIE_NAME")
        self.cookie_ttl = int(_cfg("ZG_COOKIE_TTL"))
        self.idle_timeout = int(_cfg("ZG_IDLE_TIMEOUT"))
        self.reap_interval = int(_cfg("ZG_REAP_INTERVAL"))
        self.startup_timeout = int(_cfg("ZG_ENGINE_STARTUP_TIMEOUT"))
        self.edu_base = _cfg("ZG_EDU_BASE").rstrip("/")
        self.login_html = Path(_cfg("ZG_LOGIN_HTML")) if _cfg("ZG_LOGIN_HTML") else None
        self.login_limiter = RateLimiter(_cfg("ZG_RATE_LOGIN"))
        self.registry = TenantRegistry(_cfg("ZG_REGISTRY"))
        self.backend = DockerBackend(
            _cfg("ZG_TENANT_ROOT"),
            _cfg("ZG_IMAGE"),
            int(_cfg("ZG_PORT_MIN")),
            int(_cfg("ZG_PORT_MAX")),
        )
        self._lock = asyncio.Lock()
        self._client_session: Any = None
        self._reaper_task: Optional[asyncio.Task] = None
        # user_key → 最近一次持久化 last_seen 的时刻（fast path 写盘节流）
        self._last_persist: dict[str, float] = {}
        # user_key → 首个登录的 EduAgent sub；同 key 异 sub = 清洗碰撞，拒绝后者
        self._sub_index: dict[str, str] = {}

    async def _container_running_async(self, name: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, container_running, name)

    # ---- 租户生命周期 ----

    async def ensure_tenant(self, user_key: str) -> dict:
        # 活跃租户 fast path 不拿全局锁：否则单个冷启动（spawn + 最长 25s
        # 启动等待）会阻塞全部租户的 /api 与 /ws。冷启动路径才进锁串行。
        entry = self.registry.get(user_key)
        name = self.backend.container_name(user_key)
        if entry and await self._container_running_async(name):
            entry["last_seen"] = time.time()
            now = time.time()
            if now - self._last_persist.get(user_key, 0) > 60:
                self._last_persist[user_key] = now
                self.registry.put(user_key, entry)
            return entry
        async with self._lock:
            entry = self.registry.get(user_key)
            if entry and await self._container_running_async(name):
                entry["last_seen"] = time.time()
                self.registry.put(user_key, entry)
                return entry
            if entry:
                self.backend.stop(user_key)  # 清理残留
            loop = asyncio.get_running_loop()
            port = await loop.run_in_executor(None, self.backend.allocate_port, self.registry)
            token = secrets.token_hex(32)
            await loop.run_in_executor(
                None, self.backend.spawn, user_key, port, token
            )
            entry = {
                "port": port, "token": token, "container": name,
                "started_at": time.time(), "last_seen": time.time(),
            }
            ok = await self._wait_engine(port)
            if not ok:
                self.backend.stop(user_key)
                raise RuntimeError(f"engine {user_key} failed to start")
            self.registry.put(user_key, entry)
            self._last_persist[user_key] = time.time()
            return entry

    async def _wait_engine(self, port: int) -> bool:
        import aiohttp
        deadline = time.time() + self.startup_timeout
        url = f"http://127.0.0.1:{port}/healthz"
        async with aiohttp.ClientSession() as s:
            while time.time() < deadline:
                try:
                    async with s.get(url, timeout=aiohttp.ClientTimeout(total=2)) as r:
                        if r.status == 200:
                            return True
                except aiohttp.ClientError:
                    pass
                await asyncio.sleep(1)
        return False

    async def stop_tenant(self, user_key: str) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.backend.stop, user_key)
            self.registry.remove(user_key)

    async def reap_idle(self) -> int:
        now = time.time()
        stale = [
            k for k, e in self.registry.entries.items()
            if now - e.get("last_seen", 0) > self.idle_timeout
        ]
        reaped = 0
        for k in stale:
            # 锁内复查 last_seen：判定与回收之间该租户可能重新活跃，
            # fast path 无锁刷新的 last_seen 在此可见
            async with self._lock:
                e = self.registry.entries.get(k)
                if e is None or now - e.get("last_seen", 0) <= self.idle_timeout:
                    continue
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self.backend.stop, k)
                self.registry.remove(k)
                self._last_persist.pop(k, None)
                reaped += 1
        return reaped

    # ---- 认证 ----

    def gateway_cookie_for(self, user_key: str) -> str:
        return sign_gateway_cookie(user_key, self.gw_secret, self.cookie_ttl)

    def user_key_from_request(self, request: Any) -> Optional[str]:
        raw = request.cookies.get(self.cookie_name, "")
        return verify_gateway_cookie(raw, self.gw_secret) if raw else None

    # ---- 反代 ----

    def _engine_url(self, entry: dict, path: str, ws: bool = False) -> str:
        scheme = "ws" if ws else "http"
        return f"{scheme}://127.0.0.1:{entry['port']}{path}"

    async def proxy_http(self, request: Any, entry: dict, path: str,
                         cookie_override: Optional[str] = None,
                         _retried: bool = False) -> Any:
        import aiohttp
        target = self._engine_url(entry, path)
        headers = {
            "Cookie": cookie_override or request.headers.get("Cookie", ""),
            # 引擎 /api/config 之外的端点（及未来功能）需要感知真实 scheme
            "X-Forwarded-Proto": request.headers.get("X-Forwarded-Proto",
                                                     request.scheme or "http"),
        }
        async with self._client_session.request(
            request.method, target,
            headers=headers,
            data=await request.read(),
            allow_redirects=False,
        ) as up:
            # 引擎会话失效（cookie 过期 86400s，或租户容器被回收后重新拉起
            # 时 engine token 轮换导致旧 JWT 全部失效）：用 gateway 代持的
            # tenant token 自动重登换新 cookie，携带新 cookie 重放原请求（仅一次）。
            if up.status == 401 and path != "/api/auth" and not _retried:
                fresh_cookie = await self.engine_login(entry)
                if fresh_cookie:
                    resp = await self.proxy_http(
                        request, entry, path,
                        cookie_override=fresh_cookie.split(";")[0], _retried=True)
                    # 新会话 cookie 回写浏览器，后续请求免再登
                    if resp.status == 200 and "Set-Cookie" not in resp.headers:
                        resp.headers["Set-Cookie"] = fresh_cookie
                    return resp
            body = await up.read()
            resp = aiohttp.web.Response(
                status=up.status, body=body,
                content_type=(up.headers.get("Content-Type") or "text/plain").split(";")[0],
            )
            # Location（引擎 302，配合 allow_redirects=False）与
            # Content-Disposition（下载端点）是功能性头，必须透传
            for h in ("Set-Cookie", "Location", "Content-Disposition"):
                if h in up.headers:
                    resp.headers[h] = up.headers[h]
            return resp

    async def engine_login(self, entry: dict) -> Optional[str]:
        """用 gateway 代持的 tenant token 登录引擎，返回新 Set-Cookie 值。"""
        import aiohttp
        try:
            async with self._client_session.post(
                self._engine_url(entry, "/api/auth"),
                json={"password": entry["token"]},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as up:
                if up.status == 200:
                    return up.headers.get("Set-Cookie")
        except aiohttp.ClientError:
            pass
        return None

    async def proxy_ws(self, request: Any, entry: dict) -> Any:
        import aiohttp
        import aiohttp.web as web

        client = web.WebSocketResponse()
        await client.prepare(request)
        entry["last_seen"] = time.time()

        async def connect_upstream(cookie: str):
            return await self._client_session.ws_connect(
                self._engine_url(entry, "/ws", ws=True),
                headers={"Cookie": cookie},
            )

        upstream = None
        cookie = request.headers.get("Cookie", "")
        try:
            upstream = await connect_upstream(cookie)
        except aiohttp.WSServerHandshakeError as exc:
            if exc.status == 401:
                # 引擎会话失效同 proxy_http：重登后重试一次（新 cookie
                # 尽力回写给浏览器，失败不阻塞连接建立）。
                fresh = await self.engine_login(entry)
                if fresh:
                    cookie = fresh
                    try:
                        name, _, value = fresh.split(";")[0].partition("=")
                        client.set_cookie(name, value)
                    except (AttributeError, ValueError, TypeError):
                        pass
                    try:
                        upstream = await connect_upstream(cookie)
                    except (aiohttp.ClientError, asyncio.TimeoutError):
                        pass
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass
        if upstream is None:
            await client.close(code=aiohttp.WSCloseCode.INTERNAL_ERROR,
                               message=b"engine unavailable")
            return client
        try:
            async def pump(src, dst) -> None:
                async for msg in src:
                    entry["last_seen"] = time.time()
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await dst.send_str(msg.data)
                    elif msg.type == aiohttp.WSMsgType.BINARY:
                        await dst.send_bytes(msg.data)
                    elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING,
                                      aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break

            done, pending = await asyncio.wait(
                [asyncio.create_task(pump(client, upstream)),
                 asyncio.create_task(pump(upstream, client))],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
            # 收集被取消的 task，避免 "Task exception was never retrieved"
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        finally:
            await upstream.close()
            await client.close()
        return client

    # ---- 路由 ----

    async def handle_login(self, request: Any) -> Any:
        """POST /api/login {phone,password} → 代理 EduAgent 登录（返回 token 给调用方）。"""
        import aiohttp
        import aiohttp.web as web
        if not self.login_limiter.allow(request.remote or "unknown"):
            return web.json_response({"error": "too many attempts"}, status=429)
        try:
            body = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"error": "invalid json"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"error": "invalid json"}, status=400)
        try:
            async with self._client_session.post(
                f"{self.edu_base}/api/v1/auth/login", json=body,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as up:
                return aiohttp.web.Response(
                    status=up.status, body=await up.read(),
                    content_type=(up.headers.get("Content-Type") or "application/json")
                    .split(";")[0],
                )
        except aiohttp.ClientError:
            return web.json_response({"error": "identity provider unavailable"},
                                     status=502)

    async def handle_auth(self, request: Any) -> Any:
        """POST /api/auth {password: <EduAgent access JWT>} → 租户引擎登录。"""
        import aiohttp
        import aiohttp.web as web
        if not self.login_limiter.allow(request.remote or "unknown"):
            return web.json_response({"error": "too many attempts"}, status=429)
        try:
            body = await request.json()
        except (ValueError, TypeError):
            return aiohttp.web.json_response({"error": "invalid json"}, status=400)
        if not isinstance(body, dict):
            return aiohttp.web.json_response({"error": "invalid json"}, status=400)
        claims = verify_edu_token(body.get("password", ""), self.secret)
        if not claims:
            return aiohttp.web.json_response({"error": "invalid token"}, status=401)
        user_key = tenant_key_from_sub(claims["sub"])
        if not user_key:
            return aiohttp.web.json_response({"error": "invalid subject"}, status=401)
        # 清洗碰撞防御：不同 sub 清洗出同一 user_key 时二者会共享同一容器与
        # 数据目录。首个登录者占位，后到的异 sub 一律拒绝并告警（进程重启后
        # 索引重建，占位者重新登记）。
        known_sub = self._sub_index.get(user_key)
        if known_sub is not None and known_sub != claims["sub"]:
            logger.warning(
                "tenant key collision: user_key=%s already bound to sub=%r, "
                "rejecting sub=%r", user_key, known_sub, claims["sub"])
            return aiohttp.web.json_response({"error": "invalid subject"}, status=401)
        self._sub_index[user_key] = claims["sub"]
        try:
            entry = await self.ensure_tenant(user_key)
        except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
            return aiohttp.web.json_response({"error": f"engine spawn failed: {exc}"},
                                              status=502)
        engine_cookie = await self.engine_login(entry)
        if engine_cookie is None:
            return aiohttp.web.json_response({"error": "engine unreachable"}, status=502)
        resp = aiohttp.web.Response(status=200, body=b'{"ok": true}',
                                    content_type="application/json")
        resp.headers["Set-Cookie"] = engine_cookie
        resp.set_cookie(
            self.cookie_name, self.gateway_cookie_for(user_key),
            max_age=self.cookie_ttl, httponly=True, samesite="Lax", path="/",
        )
        return resp

    async def handle_config(self, request: Any) -> Any:
        """GET /api/config 由网关自答——引擎视角的 request.host 是内网
        loopback:port，透传会返回浏览器无法使用的 wsUrl。"""
        import aiohttp.web as web
        proto = request.headers.get("X-Forwarded-Proto", request.scheme)
        return web.json_response({"wsUrl": ws_url_for(proto, request.host)})

    async def handle_api(self, request: Any) -> Any:
        """其它 /api/*：gateway cookie 鉴权 → 反代引擎。"""
        import aiohttp.web as web
        user_key = self.user_key_from_request(request)
        if not user_key:
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            entry = await self.ensure_tenant(user_key)
        except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
            return web.json_response({"error": f"engine unavailable: {exc}"}, status=502)
        return await self.proxy_http(request, entry, request.path)

    async def handle_ws(self, request: Any) -> Any:
        user_key = self.user_key_from_request(request)
        if not user_key:
            import aiohttp.web as web
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            entry = await self.ensure_tenant(user_key)
        except (RuntimeError, subprocess.SubprocessError, OSError):
            import aiohttp.web as web
            return web.json_response({"error": "engine unavailable"}, status=502)
        return await self.proxy_ws(request, entry)

    async def handle_index(self, request: Any) -> Any:
        import aiohttp.web as web
        if self.user_key_from_request(request):
            target = self.webui_dist / "index.html" if (
                self.webui_dist and self.webui_dist.exists()) else None
        elif self.login_html and self.login_html.exists():
            target = self.login_html
        elif self.webui_dist and self.webui_dist.exists():
            target = self.webui_dist / "login.html"
        else:
            target = None
        if target is None:
            return web.Response(status=500, text="ZG_WEBUI_DIST not configured")
        if not target.exists():
            return web.Response(status=404, text="dist incomplete")
        # no-cache（保留协商缓存）：登录态切换后同一 URL 必须立即换页面——
        # FileResponse 默认带 ETag/Last-Modified 且无 Cache-Control，Chromium
        # 启发式缓存会让登录后的 / 导航直接吃未登录时的缓存副本
        return web.FileResponse(target, headers={"Cache-Control": "no-cache"})

    async def handle_static(self, request: Any) -> Any:
        import aiohttp.web as web
        rel = request.match_info.get("tail", "")
        if not (self.webui_dist and self.webui_dist.exists()):
            return web.Response(status=500, text="ZG_WEBUI_DIST not configured")
        target = resolve_static_target(self.webui_dist, rel)
        if target is None:
            return web.Response(status=403, text="forbidden")
        if target.is_file():
            if target.suffix == ".html":
                return web.FileResponse(target,
                                        headers={"Cache-Control": "no-cache"})
            return web.FileResponse(target)
        return web.FileResponse(self.webui_dist / "index.html",
                                headers={"Cache-Control": "no-cache"})

    async def handle_healthz(self, request: Any) -> Any:
        import aiohttp.web as web
        return web.json_response({
            "ok": True, "tenants": len(self.registry.entries),
            "active": [k for k, e in self.registry.entries.items()],
        })

    def create_app(self) -> Any:
        import aiohttp.web as web

        app = web.Application()
        app.router.add_post("/api/login", self.handle_login)
        app.router.add_post("/api/auth", self.handle_auth)
        app.router.add_get("/api/config", self.handle_config)
        app.router.add_get("/ws", self.handle_ws)
        app.router.add_get("/healthz", self.handle_healthz)
        app.router.add_route("*", "/api/{tail:.*}", self.handle_api)
        app.router.add_get("/", self.handle_index)
        app.router.add_get("/{tail:.*}", self.handle_static)
        return app

    async def _reaper(self, app: Any) -> None:
        while True:
            await asyncio.sleep(self.reap_interval)
            try:
                await self.reap_idle()
            except (subprocess.SubprocessError, OSError, RuntimeError):
                pass

    def _list_orphan_containers(self) -> list[str]:
        """容器名以 zs-t- 开头但 registry 无记录的容器（上次进程崩溃残留）。
        此类孤儿占用端口且不会被 reap（reap 只看 registry），启动时一次性回收。"""
        try:
            r = _docker("ps", "-a", "--filter", "name=zs-t-",
                        "--format", "{{.Names}}", check=False)
        except (subprocess.SubprocessError, OSError):
            return []
        known = {self.backend.container_name(k) for k in self.registry.entries}
        return [n for n in r.stdout.split()
                if n.startswith("zs-t-") and n not in known]

    async def start(self) -> None:
        import aiohttp
        from aiohttp import web

        if not self.secret or not self.gw_secret:
            raise SystemExit("ZG_SECRET / ZG_GATEWAY_SECRET required")
        loop = asyncio.get_running_loop()
        for key in list(self.registry.entries):
            if not await self._container_running_async(
                    self.backend.container_name(key)):
                self.registry.remove(key)
        orphans = await loop.run_in_executor(None, self._list_orphan_containers)
        for name in orphans:
            logger.warning("reclaiming orphan tenant container %s", name)
            await loop.run_in_executor(
                None, lambda n=name: _docker("rm", "-f", n, check=False))
        self._client_session = aiohttp.ClientSession()
        app = self.create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        # on_startup 回调返回值会被 Signal.send await，reaper 不能挂在那里；
        # 引用必须保存在实例上——事件循环仅弱引用 task，丢引用可被 GC 中止，
        # 之后空闲容器永不回收
        self._reaper_task = asyncio.create_task(self._reaper(app))
        site = web.TCPSite(runner, _cfg("ZG_LISTEN"), int(_cfg("ZG_PORT")))
        await site.start()
        print(f"zenskill-gateway on {_cfg('ZG_LISTEN')}:{_cfg('ZG_PORT')} "
              f"(tenants dir {_cfg('ZG_TENANT_ROOT')})")
        while True:
            await asyncio.sleep(3600)


def main() -> int:
    asyncio.run(Gateway().start())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
