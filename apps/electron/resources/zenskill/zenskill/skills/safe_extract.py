"""安全解压（W2 纯函数，供 W3 安装管线 staging 阶段调用）。

按方案安全评审补强 S5 实现：拒路径穿越（zip slip）/目标外 symlink/
hardlink/device/fifo/mode>0755（含 setuid/setgid/sticky）；
流式限额读（zip 炸弹在扫描前的解压期即中止），失败时清理已落盘内容。
zipfile / tarfile（含 .gz/.bz2/.xz）双支持。
"""

from __future__ import annotations

import io
import re
import shutil
import stat
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import List, Union

_BLOCK = 64 * 1024
_MAX_SYMLINK_TARGET = 4096
_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:")

DEFAULT_MAX_TOTAL = 50 * 1024 * 1024   # 50MB
DEFAULT_MAX_FILES = 500

_TAR_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")


class SafeExtractError(Exception):
    """拒绝解压或超限；抛出前已清理 dest_dir 内已提取内容。"""


def _validate_entry_name(name: str) -> str:
    """校验归档条目名，返回归一化 posix 名；非法即抛 SafeExtractError。"""
    norm = name.replace("\\", "/")
    if norm.startswith("/") or _WINDOWS_ABS_RE.match(norm):
        raise SafeExtractError(f"条目为绝对路径: {name!r}")
    if any(part == ".." for part in PurePosixPath(norm).parts):
        raise SafeExtractError(f"条目含路径穿越(../): {name!r}")
    return norm


def _check_mode(mode: int, name: str) -> None:
    if (mode & 0o7777) > 0o755:
        raise SafeExtractError(f"条目权限超 0755: {name!r} mode={oct(mode & 0o7777)}")


def _validate_symlink_target(entry_name: str, target: str, dest_root: Path) -> None:
    t = target.replace("\\", "/")
    base = (dest_root / PurePosixPath(entry_name).parent).resolve()
    resolved = Path(t).resolve() if t.startswith("/") else (base / t).resolve()
    if not resolved.is_relative_to(dest_root.resolve()):
        raise SafeExtractError(
            f"symlink 指向目标外: {entry_name!r} -> {target!r}")


def _copy_limited(src: io.RawIOBase, dst_path: Path, name: str,
                  counter: List[int], max_total: int) -> None:
    """流式限量复制：超 max_total 立即中止（由上层清理）。"""
    with open(dst_path, "wb") as dst:
        while True:
            chunk = src.read(_BLOCK)
            if not chunk:
                break
            counter[0] += len(chunk)
            if counter[0] > max_total:
                raise SafeExtractError(
                    f"解压总量超限 {max_total} 字节（条目 {name!r} 处中止）")
            dst.write(chunk)


def _prepare_path(dest_root: Path, name: str) -> Path:
    target = dest_root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _extract_zip(archive: Path, dest_root: Path, max_total: int, max_files: int) -> List[str]:
    out: List[str] = []
    counter = [0]
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        if len(infos) > max_files:
            raise SafeExtractError(f"条目数 {len(infos)} 超过上限 {max_files}")
        for info in infos:
            name = _validate_entry_name(info.filename)
            mode = (info.external_attr >> 16) & 0xFFFF
            if mode and stat.S_ISLNK(mode):
                with zf.open(info) as src:
                    target_bytes = src.read(_MAX_SYMLINK_TARGET + 1)
                if len(target_bytes) > _MAX_SYMLINK_TARGET:
                    raise SafeExtractError(f"symlink 目标过长: {name!r}")
                link_target = target_bytes.decode("utf-8", "surrogateescape")
                _validate_symlink_target(name, link_target, dest_root)
                link_path = _prepare_path(dest_root, name)
                link_path.symlink_to(link_target)
                out.append(name)
                continue
            ftype = mode & 0o170000
            if ftype and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise SafeExtractError(
                    f"拒绝非常规条目(hardlink/device/fifo): {name!r} "
                    f"mode={oct(mode)}")
            if mode:
                _check_mode(mode, name)
            if info.is_dir() or name.endswith("/"):
                (dest_root / name).mkdir(parents=True, exist_ok=True)
                continue
            target_path = _prepare_path(dest_root, name)
            with zf.open(info) as src:
                _copy_limited(src, target_path, name, counter, max_total)
            out.append(name)
    return out


def _extract_tar(archive: Path, dest_root: Path, max_total: int, max_files: int) -> List[str]:
    out: List[str] = []
    counter = [0]
    with tarfile.open(archive) as tf:
        members = tf.getmembers()
        if len(members) > max_files:
            raise SafeExtractError(f"条目数 {len(members)} 超过上限 {max_files}")
        for m in members:
            name = _validate_entry_name(m.name)
            if m.issym():
                _validate_symlink_target(name, m.linkname, dest_root)
                link_path = _prepare_path(dest_root, name)
                link_path.symlink_to(m.linkname)
                out.append(name)
                continue
            if m.islnk():
                raise SafeExtractError(f"拒绝 hardlink 条目: {name!r} -> {m.linkname!r}")
            if m.isdev() or m.isfifo():
                raise SafeExtractError(
                    f"拒绝 device/fifo 条目: {name!r} type={m.type!r}")
            _check_mode(m.mode, name)
            if m.isdir():
                (dest_root / name).mkdir(parents=True, exist_ok=True)
                continue
            if not m.isfile():
                raise SafeExtractError(f"拒绝未知条目类型: {name!r} type={m.type!r}")
            src = tf.extractfile(m)
            if src is None:
                raise SafeExtractError(f"条目无法读取: {name!r}")
            target_path = _prepare_path(dest_root, name)
            _copy_limited(src, target_path, name, counter, max_total)
            out.append(name)
    return out


def _cleanup(dest_root: Path) -> None:
    for child in dest_root.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


def safe_extract(archive_path: Union[Path, str], dest_dir: Union[Path, str],
                 max_total: int = DEFAULT_MAX_TOTAL,
                 max_files: int = DEFAULT_MAX_FILES) -> List[str]:
    """安全解压 zip/tar(.gz/.bz2/.xz) 到 dest_dir，返回提取的条目相对路径。

    拒绝：路径穿越/绝对路径条目、指向 dest 外的 symlink、hardlink/device/fifo、
    mode>0755、条目数超 max_files、总量超 max_total（流式中止）。
    任何拒绝/失败都会清理 dest_dir 下已提取内容后抛 SafeExtractError；
    调用方应传入专用空目录（W3 staging）。
    """
    archive = Path(archive_path)
    dest = Path(dest_dir)
    if not archive.is_file():
        raise SafeExtractError(f"归档不存在: {archive}")
    suffix = archive.name.lower()
    try:
        if suffix.endswith(".zip") or (not suffix.endswith(_TAR_SUFFIXES)
                                       and zipfile.is_zipfile(archive)):
            names = _extract_zip(archive, dest, max_total, max_files)
        elif suffix.endswith(_TAR_SUFFIXES):
            names = _extract_tar(archive, dest, max_total, max_files)
        else:
            raise SafeExtractError(f"不支持的归档格式: {archive.name!r}")
        return names
    except SafeExtractError:
        if dest.is_dir():
            _cleanup(dest)
        raise
    except (zipfile.BadZipFile, tarfile.TarError, OSError) as e:
        if dest.is_dir():
            _cleanup(dest)
        raise SafeExtractError(f"解压失败: {e}") from e
