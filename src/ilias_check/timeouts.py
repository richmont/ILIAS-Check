"""Interrupt synchronous interactive work on the Linux worker's main thread."""
from __future__ import annotations

from contextlib import contextmanager
import signal
import threading

from ilias_check.cache_config import CacheError

MATERIAL_REQUEST_TIMEOUT_SECONDS = 120


class MaterialRequestTimeout(BaseException):
    """Escape broad per-page recovery so an expired request cannot keep crawling."""


@contextmanager
def material_request_deadline(seconds=MATERIAL_REQUEST_TIMEOUT_SECONDS):
    """Cancel the current request, unwinding transports, transactions and leases.

    No abandoned thread or child continues collecting or sending after timeout.
    The dedicated worker runs synchronously on its process's main thread.
    """
    if threading.current_thread() is not threading.main_thread():
        raise CacheError("Interactive material requests require the worker main thread.")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    if previous_timer[0]:
        raise CacheError("Another request deadline is already active.")

    def expired(signum, frame):
        raise MaterialRequestTimeout()

    signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
