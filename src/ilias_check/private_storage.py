"""Private Linux/POSIX storage anchored to directory descriptors and process locks."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import stat
from urllib.parse import urlsplit, urlunsplit

from ilias_check.cache_config import CacheError


class RuntimeStoreBusy(CacheError):
    """A nonblocking runtime lease is currently held by another operation."""


def account_key(config) -> str:
    parsed = urlsplit(config.base_url)
    host = parsed.hostname.lower()
    if ":" in host:
        host = "[" + host + "]"
    authority = host if parsed.port in (None, 443) else f"{host}:{parsed.port}"
    installation = urlunsplit(("https", authority, parsed.path.rstrip("/"), "", ""))
    return hashlib.sha256("\0".join((installation, config.client_id, config.username)).encode()).hexdigest()


def private_root(path: Path, checkout: Path | None = None) -> tuple[Path, int]:
    path = Path(os.path.abspath(path.expanduser()))
    checkout = (checkout or Path(__file__).resolve().parents[2]).resolve()
    # Also reject descendants of any containing Git checkout, including installed wheels.
    if path == checkout or checkout in path.parents or any((p / ".git").exists() for p in (path, *path.parents)):
        raise CacheError("Private runtime storage must be outside the checkout.")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise CacheError("Private runtime directory must be owned by this account with mode 0700.")
        return path, fd
    except Exception:
        os.close(fd)
        raise CacheError("Private runtime directory is unavailable or unsafe.") from None


def private_open(root_fd: int, name: str, flags: int, mode: int = 0o600) -> int:
    if "/" in name or name in {"", ".", ".."}:
        raise CacheError("Unsafe managed filename.")
    fd = os.open(name, flags | os.O_NOFOLLOW, mode, dir_fd=root_fd)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        os.close(fd)
        raise CacheError("Unsafe managed file.")
    return fd


@contextmanager
def process_lock(root_fd: int, name: str = "cache.lock"):
    fd = private_open(root_fd, name, os.O_CREAT | os.O_RDWR)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeStoreBusy("Another process is using this private runtime store.") from None
        yield
    finally:
        os.close(fd)
