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
    """尝试终止占用端口的进程"""
    import subprocess, signal, time
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=5
        )
        for pid_str in result.stdout.strip().splitlines():
            pid = int(pid_str.strip())
            try:
                os.kill(pid, signal.SIGKILL)
                print(f"  Stopped old process (PID {pid}) on port {port}")
            except (ProcessLookupError, PermissionError):
                pass
        time.sleep(1)
    except Exception:
        pass


def _detect_craft_mode() -> bool:
    """auto 模式检测：bun + vendor 构建产物齐备 → craft 模式可用。"""
    import shutil
    vendor = Path(__file__).parent.parent.parent / "vendor" / "craft-agents"
    if not shutil.which("bun"):
        return False
    if not (vendor / "packages" / "server").is_dir():
        return False
    return (vendor / "apps" / "webui" / "dist" / "index.html").exists()


def cmd_serve(args) -> int:
    """启动 ZenSkill WebUI server（统一入口，两种运行模式）。

    Mode 决策（统一模式方案，docs/gui_unified_modes.md）：
    - craft:  vendor TS server（287 channel 全功能），需 bun
    - python: 内嵌 ws_server（零 Node 依赖，核心对话闭环）
    - auto:   bun + vendor 构建齐备 → craft，否则 python
    """
    mode = getattr(args, "mode", None) or "auto"
    if mode == "auto":
        mode = "craft" if _detect_craft_mode() else "python"

    if mode == "craft":
        import subprocess
        vendor = Path(__file__).parent.parent.parent / "vendor" / "craft-agents"
        script = vendor / ".." / ".." / "scripts" / "start_gui.sh"
        script = script.resolve()
        if not script.exists():
            print(f"Error: start_gui.sh not found at {script}")
            return 1
        print("=" * 50)
        print("  ZenSkill GUI — craft 模式（vendor TS server）")
        print("=" * 50)
        try:
            return subprocess.call(["bash", str(script)]).returncode or 0
        except KeyboardInterrupt:
            return 0

    try:
        from aiohttp import web
    except ImportError:
        print("Error: aiohttp required for webui server.")
        print("Install: pip install zenskill[webui]")
        return 1

    port = getattr(args, "port", None) or 9100
    token = getattr(args, "token", None) or os.urandom(16).hex()

    # 自动清理端口
    if not _is_port_free(port):
        print(f"Port {port} is in use, attempting to stop old process...")
        _kill_port_process(port)
        if not _is_port_free(port):
            print(f"Error: Port {port} still in use. Use --port to specify a different port.")
            return 1

    # WebUI dist 路径（--webui-path 可指向 vendor 新版构建；默认内置快照）
    webui_path = Path(getattr(args, "webui_path", None)
                      or Path(__file__).parent.parent / "webui" / "dist")
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
        help="启动 WebUI server（统一入口；--mode 选 craft/python）",
    )
    serve_parser.add_argument(
        "--mode", choices=["auto", "craft", "python"], default="auto",
        help="运行模式：craft=vendor TS server 全功能；python=零依赖内嵌（默认 auto 检测）",
    )
    serve_parser.add_argument(
        "--port", type=int, default=9100,
        help="监听端口（默认 9100）",
    )
    serve_parser.add_argument(
        "--token", type=str, default=None,
        help="认证 token（默认自动生成）",
    )
    serve_parser.add_argument(
        "--webui-path", type=str, default=None,
        help="WebUI dist 路径（默认 zenskill/webui/dist，可指向 vendor/craft-agents/apps/webui/dist）",
    )
    serve_parser.set_defaults(func=cmd_serve)
