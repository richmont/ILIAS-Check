"""Optional low-noise extraction progress.

Writes counts and elapsed time to stderr only: stdout stays a clean JSON
inventory. No course titles, URLs, credentials or account identifiers are
included, and emission is throttled so cron logs stay readable.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Callable, TextIO


@dataclass(slots=True)
class Progress:
    stream: TextIO = field(default_factory=lambda: sys.stderr)
    interval: float = 2.0
    clock: Callable[[], float] = time.monotonic
    _started: float = field(init=False, repr=False)
    _last: float = field(init=False, repr=False)
    _requests: int = field(default=0, init=False)
    _objects: int = field(default=0, init=False)
    _root_index: int = field(default=0, init=False)
    _root_count: int = field(default=0, init=False)
    _root_id: str | None = field(default=None, init=False)
    _finished: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._started = self._last = self.clock()

    def start(self, root_count: int, max_requests: int) -> None:
        self._root_count = root_count
        self._write(f"progress: starting roots={root_count} request_budget={max_requests}")

    def request(self) -> None:
        self._requests += 1
        self._emit()

    def root(self, index: int, root_id: str) -> None:
        self._root_index = index
        self._root_id = root_id
        self._emit(force=True)

    def objects(self, count: int) -> None:
        self._objects = count
        self._emit()

    def finish(self, completed: bool = True) -> None:
        if self._finished:
            return
        self._finished = True
        state = "done" if completed else "stopped"
        self._write(
            f"progress: {state} requests={self._requests} objects={self._objects} "
            f"elapsed={self._elapsed():.1f}s"
        )

    def _elapsed(self) -> float:
        return max(0.0, self.clock() - self._started)

    def _emit(self, *, force: bool = False) -> None:
        now = self.clock()
        if not force and now - self._last < self.interval:
            return
        self._last = now
        if self._root_id is None:
            detail = "phase=login"
        else:
            detail = f"root={self._root_index}/{self._root_count} ({self._root_id})"
        self._write(
            f"progress: {detail} requests={self._requests} objects={self._objects} "
            f"elapsed={self._elapsed():.1f}s"
        )

    def _write(self, line: str) -> None:
        try:
            self.stream.write(line + "\n")
            flush = getattr(self.stream, "flush", None)
            if callable(flush):
                flush()
        except (OSError, ValueError):
            # Diagnostics must never break a collection run.
            pass
