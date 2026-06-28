"""
Tiny append-only file logger for diagnosing the input-forwarding path.

The packaged app is windowed (no console), so print() output is invisible.
When enabled, this writes timestamped lines to `cross_hid_log.txt` next to
the executable (falling back to the current working directory).

Logging is OFF by default so it never adds any overhead to the normal
forwarding path. Enable it only when diagnosing an issue by setting the
environment variable CROSS_HID_DEBUG=1 before launching the app.
"""
import os
import sys
import threading
import time

# Opt-in only: anything other than unset/""/"0"/"false" turns logging on.
_ENABLED = os.environ.get("CROSS_HID_DEBUG", "").strip().lower() not in ("", "0", "false", "no")

_LOCK = threading.Lock()
_PATH = None


def enabled() -> bool:
    return _ENABLED


def _resolve_path() -> str:
    global _PATH
    if _PATH:
        return _PATH
    base = None
    try:
        # Directory of the running .exe / script.
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
    except Exception:
        base = None
    if not base or not os.path.isdir(base):
        base = os.getcwd()
    _PATH = os.path.join(base, "cross_hid_log.txt")
    return _PATH


def log(msg: str) -> None:
    if not _ENABLED:
        return
    try:
        line = f"{time.strftime('%H:%M:%S')} [{threading.current_thread().name}] {msg}\n"
        with _LOCK:
            with open(_resolve_path(), "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass


def reset(header: str = "") -> None:
    """Start a fresh log section (called on app start)."""
    if not _ENABLED:
        return
    try:
        with _LOCK:
            with open(_resolve_path(), "a", encoding="utf-8") as f:
                f.write("\n" + "=" * 60 + "\n")
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {header}\n")
                f.write("=" * 60 + "\n")
    except Exception:
        pass
