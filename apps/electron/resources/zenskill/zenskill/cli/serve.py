"""`zenskill serve` 命令 — 启动 WebUI server。

用法：
    zenskill serve [--port 9100] [--token <auto>]
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path


def _is_port_free(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('127.0.0.1', port))
            return True
    except OSError:
        return False


def _kill_port_process(port: int):
    """尝试终止占用端口的进程（跨平台）"""
    import time
    from ..runtime.platform_utils import kill_port
    try:
        killed = kill_port(port)
        if killed:
            print(f"  Stopped {killed} process(es) on port {port}")
        time.sleep(1)
    except Exception:
        pass


def _detect_desktop_mode() -> bool:
    """auto 模式检测：bun + vendor 构建产物齐备 → desktop 模式可用。"""
    import shutil
    vendor = Path(__file__).parent.parent.parent / "vendor" / "craft-agents"
    if not shutil.which("bun"):
        return False
    if not (vendor / "packages" / "server").is_dir():
        return False
    return (vendor / "apps" / "webui" / "dist" / "index.html").exists()


def _resolve_serve_config(args) -> "tuple[int, str, Path]":
    """解析 port/token/webui：CLI 参数 > 环境变量 > 默认值。

    托管运行时（扣子编程等）只能注入环境变量、无法自定义启动参数，
    所以 env 回退是部署到平台的硬前提：ZENSKILL_PORT / PORT、
    ZENSKILL_TOKEN、ZENSKILL_WEBUI_PATH。
    """
    port = getattr(args, "port", None)
    if not port:
        raw = os.environ.get("ZENSKILL_PORT") or os.environ.get("PORT")
        try:
            port = int(raw)
        except (TypeError, ValueError):
            port = 9100

    token = (getattr(args, "token", None)
             or os.environ.get("ZENSKILL_TOKEN")
             or os.urandom(16).hex())

    webui_path = Path(
        getattr(args, "webui_path", None)
        or os.environ.get("ZENSKILL_WEBUI_PATH")
        or Path(__file__).parent.parent / "webui" / "dist"
    )
    return port, token, webui_path


def cmd_serve(args) -> int:
    """启动 ZenSkill WebUI server（统一入口，两种运行模式）。

    Mode 决策（统一模式方案，docs/gui_unified_modes.md）：
    - desktop: vendor TS server（287 channel 全功能），需 bun
    - python:  内嵌 ws_server（零 Node 依赖，核心对话闭环）
    - auto:    bun + vendor 构建齐备 → desktop，否则 python
    """
    mode = getattr(args, "mode", None) or "auto"
    if mode == "auto":
        mode = "desktop" if _detect_desktop_mode() else "python"

    if mode == "desktop":
        import subprocess
        vendor = Path(__file__).parent.parent.parent / "vendor" / "craft-agents"
        script = vendor / ".." / ".." / "scripts" / "start_gui.sh"
        script = script.resolve()
        if not script.exists():
            print(f"Error: start_gui.sh not found at {script}")
            return 1
        print("=" * 50)
        print("  ZenSkill GUI — desktop 模式（vendor TS server）")
        print("=" * 50)
        try:
            import platform as _plat
            if _plat.system() == "Windows":
                # Windows: 通过 bun 直接启动 desktop server（bash 不可用）
                return subprocess.call(["cmd", "/c", "bun", "run",
                                        str(vendor / "packages" / "server" / "src" / "index.ts")])
            return subprocess.call(["bash", str(script)])
        except KeyboardInterrupt:
            return 0

    try:
        from aiohttp import web
    except ImportError:
        print("Error: aiohttp required for webui server.")
        print("Install: pip install zenskill[webui]")
        return 1

    port, token, webui_path = _resolve_serve_config(args)

    # 自动清理端口
    if not _is_port_free(port):
        print(f"Port {port} is in use, attempting to stop old process...")
        _kill_port_process(port)
        if not _is_port_free(port):
            print(f"Error: Port {port} still in use. Use --port to specify a different port.")
            return 1

    if not webui_path.exists():
        print(f"Error: WebUI not found at {webui_path}")
        print("Run: python3 scripts/build_webui.py or pass --webui-path")
        return 1

    from ..server.ws_server import create_app
    app = create_app(webui_path=webui_path, token=token, port=port)

    print("=" * 50)
    print("  ZenSkill WebUI Server")
    print("=" * 50)
    print(f"\n  URL:    http://127.0.0.1:{port}")
    print(f"  Token:  {token}")
    print(f"\n  Login with the token above in your browser.")
    print(f"  Press Ctrl+C to stop.\n")

    try:
        web.run_app(app, port=port, print=lambda _: None)
    except KeyboardInterrupt:
        print("\nShutting down...")
    return 0


def register_serve_parser(subparsers) -> None:
    """注册 serve 命令（由 __main__.main 调用）"""
    serve_parser = subparsers.add_parser(
        "serve",
        help="启动 WebUI server（统一入口；--mode 选 desktop/python）",
    )
    serve_parser.add_argument(
        "--mode", choices=["auto", "desktop", "python"], default="auto",
        help="运行模式：desktop=vendor TS server 全功能；python=零依赖内嵌（默认 auto 检测）",
    )
    serve_parser.add_argument(
        "--port", type=int, default=None,
        help="监听端口（默认 9100；可用 ZENSKILL_PORT 或 PORT 环境变量覆盖）",
    )
    serve_parser.add_argument(
        "--token", type=str, default=None,
        help="认证 token（默认优先读 ZENSKILL_TOKEN，否则自动生成）",
    )
    serve_parser.add_argument(
        "--webui-path", type=str, default=None,
        help="WebUI dist 路径（默认 zenskill/webui/dist，可用 ZENSKILL_WEBUI_PATH 覆盖）",
    )
    serve_parser.set_defaults(func=cmd_serve)
