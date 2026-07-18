from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    pass

_caffeinate_proc: subprocess.Popen | None = None
_wake_lock_count: int = 0


def acquireWakeLock() -> None:
    """Prevent the system from sleeping. Call once when downloads start."""
    global _caffeinate_proc, _wake_lock_count
    _wake_lock_count += 1
    if _wake_lock_count > 1:
        return  # already held

    try:
        match sys.platform:
            case "win32":
                import ctypes
                # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
                result = ctypes.windll.kernel32.SetThreadExecutionState(
                    0x80000000 | 0x00000001 | 0x00000040
                )
                if result == 0:
                    logger.warning("acquireWakeLock: SetThreadExecutionState returned 0")
                else:
                    logger.debug("Wake lock acquired (Windows)")
            case "darwin":
                _caffeinate_proc = subprocess.Popen(
                    ["caffeinate", "-i"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logger.debug("Wake lock acquired (macOS caffeinate pid={})", _caffeinate_proc.pid)
            case _:
                # Linux: use systemd-inhibit if available
                import shutil
                if shutil.which("systemd-inhibit"):
                    _caffeinate_proc = subprocess.Popen(
                        [
                            "systemd-inhibit",
                            "--what=idle:sleep",
                            "--who=Ghost Downloader",
                            "--why=Download in progress",
                            "--mode=block",
                            "sleep", "infinity",
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    logger.debug("Wake lock acquired (Linux systemd-inhibit pid={})", _caffeinate_proc.pid)
                else:
                    logger.warning("acquireWakeLock: systemd-inhibit not found, sleep prevention unavailable")
    except Exception as e:
        logger.opt(exception=e).warning("acquireWakeLock failed")


def releaseWakeLock() -> None:
    """Allow the system to sleep again. Call when downloads finish."""
    global _caffeinate_proc, _wake_lock_count
    if _wake_lock_count <= 0:
        return
    _wake_lock_count -= 1
    if _wake_lock_count > 0:
        return  # still held by other callers

    try:
        match sys.platform:
            case "win32":
                import ctypes
                # ES_CONTINUOUS only — clears the previous flags
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
                logger.debug("Wake lock released (Windows)")
            case _:
                if _caffeinate_proc is not None:
                    _caffeinate_proc.kill()
                    _caffeinate_proc = None
                    logger.debug("Wake lock released (caffeinate/systemd-inhibit killed)")
    except Exception as e:
        logger.opt(exception=e).warning("releaseWakeLock failed")
