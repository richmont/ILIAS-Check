"""Low-noise extraction progress must stay on a diagnostic stream."""
from __future__ import annotations

from io import StringIO

from ilias_check.progress import Progress


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def make_progress() -> tuple[Progress, StringIO, Clock]:
    stream = StringIO()
    clock = Clock()
    return Progress(stream=stream, interval=2.0, clock=clock), stream, clock


def lines(stream: StringIO) -> list[str]:
    return [line for line in stream.getvalue().splitlines() if line]


def test_progress_reports_counts_without_titles_or_urls() -> None:
    progress, stream, clock = make_progress()
    progress.start(root_count=2, max_requests=500)
    clock.now += 5
    progress.root(1, "1001")
    progress.request()
    progress.request()
    clock.now += 5
    progress.objects(7)
    progress.finish(completed=True)

    text = "\n".join(lines(stream))
    assert "starting roots=2 request_budget=500" in text
    assert "root=1/2 (1001)" in text
    assert "objects=7" in text
    assert "done" in text
    assert "elapsed=" in text
    for leaked in ("https://", "Übung", "password", "session"):
        assert leaked not in text


def test_progress_throttles_requests_but_forces_root_changes() -> None:
    progress, stream, clock = make_progress()
    progress.start(root_count=1, max_requests=500)
    before = len(lines(stream))

    clock.now += 0.5
    progress.request()
    progress.request()
    assert len(lines(stream)) == before

    progress.root(1, "1001")
    assert len(lines(stream)) == before + 1

    clock.now += 2.5
    progress.request()
    assert len(lines(stream)) == before + 2


def test_progress_finish_is_idempotent_and_never_raises() -> None:
    progress, stream, _clock = make_progress()
    progress.finish(completed=False)
    progress.finish(completed=True)
    assert len(lines(stream)) == 1
    assert "stopped" in lines(stream)[0]

    closed = Progress(stream=StringIO())
    closed.stream.close()
    closed.start(root_count=1, max_requests=1)
    closed.request()
    closed.finish()
