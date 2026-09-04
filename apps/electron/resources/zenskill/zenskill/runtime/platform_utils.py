"""跨平台工具层 — 业务代码不得直接调用 POSIX-only API。

封装进程管理、端口清理、文件锁、安全文件、临时目录等平台差异。
所有函数在 Linux/macOS/Windows 上行为一致。
"""
from __future__ import annotations

import platform
import subprocess
from typing import Optional

IS_WINDOWS = platform.system() == "Windows"


# ═══════════════════════════════════════════════════════════════
# 进程管理
# ═══════════════════════════════════════════════════════════════


def kill_process_tree(pid: int) -> None:
    """杀掉指定 PID 及其全部子进程（跨平台）。"""
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True, timeout=10,
        )
    else:
        import os, signal
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


def kill_pid(pid: int) -> None:
    """杀掉单个进程（跨平台）。"""
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    else:
        import os, signal
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass


def get_new_process_kwargs() -> dict:
    """返回 subprocess.Popen/create_subprocess_shell 的平台特定参数。

    用法:
        kwargs = get_new_process_kwargs()
        proc = await asyncio.create_subprocess_shell(cmd, **kwargs)
    """
    if IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


# ═══════════════════════════════════════════════════════════════
# 端口管理
# ═══════════════════════════════════════════════════════════════


def find_port_pids(port: int) -> list[int]:
    """查找占用指定端口的进程 PID 列表。"""
    if IS_WINDOWS:
        result = subprocess.run(
            ["powershell", "-Command",
             f"(Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue).OwningProcess"],
            capture_output=True, text=True, timeout=10,
        )
    else:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=5,
        )
    pids = []
    for line in result.stdout.strip().splitlines():
        try:
            pids.append(int(line.strip()))
        except ValueError:
            pass
    return pids


def kill_port(port: int) -> int:
    """杀掉占用指定端口的全部进程。返回杀掉的进程数。"""
    pids = find_port_pids(port)
    for pid in pids:
        kill_pid(pid)
    return len(pids)


# ═══════════════════════════════════════════════════════════════
# shell 执行
# ═══════════════════════════════════════════════════════════════


def shell_run(cmd: str | list[str], timeout: int = 30, **kwargs) -> subprocess.CompletedProcess:
    """跨平台 shell 命令执行。"""
    if isinstance(cmd, list):
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)
    if IS_WINDOWS:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, **kwargs)
    return subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout, **kwargs)


def get_bun_command() -> list[str]:
    """返回启动 bun 的命令前缀。"""
    if IS_WINDOWS:
        return ["cmd", "/c", "bun"]
    return ["bun"]
