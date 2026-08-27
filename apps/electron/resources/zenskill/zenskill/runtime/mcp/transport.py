"""
StdioTransport — stdio JSON-RPC 传输层

修复旧 mcp_client.py 的三处硬伤：
- 响应按 request id 路由（server 乱序推送 notification 不再被误当响应）
- stderr 持续消费（对端大量写 stderr 不再死锁）
- 大响应跨 chunk 手动缓冲拼接（asyncio readline 有 64KB 行长限制，不能直接用）

client 与 server（mcp/server.py）共用本模块的消息收发骨架。
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any, Callable, Optional

from .protocol import classify_message, make_request_line, make_notification_line

READ_CHUNK = 65536


class TransportError(ConnectionError):
    """传输层错误（连接断开、对端无响应等）"""


class StdioTransport:
    """
    子进程 stdio JSON-RPC 传输。

    - request(): 发送请求并等待对端按相同 id 返回的响应（乱序免疫）
    - send_notification(): 单向通知
    - on_notification: 对端 notification 回调（默认忽略）
    - on_stderr: 对端 stderr 回调（默认丢弃；不消费会死锁，必须有协程在读）
    """

    def __init__(
        self,
        command: list[str],
        *,
        on_notification: Optional[Callable[[dict[str, Any]], None]] = None,
        on_stderr: Optional[Callable[[bytes], None]] = None,
    ):
        self._command = command
        self._on_notification = on_notification
        self._on_stderr = on_stderr
        self._process: Optional[asyncio.subprocess.Process] = None
        self._pending: dict[int, asyncio.Future] = {}
        self._request_id = 0
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._closing = False

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        if self._closing:
            raise TransportError("Transport already closed")
        if self.running:
            return
        self._process = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._stderr_loop())

    async def request(
        self,
        method: str,
        params: dict[str, Any],
        timeout: float = 30.0,
    ) -> Any:
        """发送请求并等待同 id 响应；返回 result，错误抛 TransportError"""
        if not self.running or self._process is None or self._process.stdin is None:
            raise TransportError("Transport not running")

        self._request_id += 1
        request_id = self._request_id
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future

        try:
            self._process.stdin.write(
                (make_request_line(request_id, method, params) + "\n").encode()
            )
            await self._process.stdin.drain()
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        finally:
            self._pending.pop(request_id, None)

    async def send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        if not self.running or self._process is None or self._process.stdin is None:
            raise TransportError("Transport not running")
        self._process.stdin.write(
            (make_notification_line(method, params) + "\n").encode()
        )
        await self._process.stdin.drain()

    async def stop(self) -> None:
        """关闭连接：取消任务、清理 pending、终止进程"""
        self._closing = True
        for task in (self._reader_task, self._stderr_task):
            if task is not None and not task.done():
                task.cancel()
        for future in self._pending.values():
            if not future.done():
                future.set_exception(TransportError("Transport closed"))
        self._pending.clear()

        if self._process is not None:
            try:
                if self._process.stdin is not None:
                    self._process.stdin.close()
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            except (ProcessLookupError, OSError):
                pass
            finally:
                self._process = None

    async def _read_loop(self) -> None:
        """持续读 stdout：手动缓冲拼接按行切分，按消息类型三路分发"""
        assert self._process is not None and self._process.stdout is not None
        buffer = b""
        try:
            while True:
                chunk = await self._process.stdout.read(READ_CHUNK)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    raw_line, buffer = buffer.split(b"\n", 1)
                    self._dispatch_line(raw_line)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            self._fail_all_pending(TransportError("MCP peer closed connection"))

    def _dispatch_line(self, raw_line: bytes) -> None:
        from .protocol import parse_message_line

        try:
            text = raw_line.decode("utf-8")
        except UnicodeDecodeError:
            return
        obj = parse_message_line(text)
        if obj is None:
            return

        kind = classify_message(obj)
        if kind == "response":
            self._resolve_response(obj)
        elif kind == "notification":
            if self._on_notification is not None:
                try:
                    self._on_notification(obj)
                except Exception:
                    pass
        # 对端请求（server→client 方向，如 sampling）：v1 记录忽略
        elif kind == "request":
            print(f"[mcp] peer request ignored: {obj.get('method')}", file=sys.stderr)

    def _resolve_response(self, obj: dict[str, Any]) -> None:
        request_id = obj.get("id")
        future = self._pending.get(request_id)
        if future is None or future.done():
            return
        if obj.get("error") is not None:
            future.set_exception(TransportError(f"MCP error: {obj['error']}"))
        else:
            future.set_result(obj.get("result"))

    def _fail_all_pending(self, exc: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(exc)
        self._pending.clear()

    async def _stderr_loop(self) -> None:
        """持续消费 stderr，防止对端写满管道缓冲导致死锁"""
        assert self._process is not None and self._process.stderr is not None
        try:
            while True:
                chunk = await self._process.stderr.read(4096)
                if not chunk:
                    break
                if self._on_stderr is not None:
                    try:
                        self._on_stderr(chunk)
                    except Exception:
                        pass
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
