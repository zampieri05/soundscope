"""Invocation-scoped, dependency-free telemetry for the artist pipeline."""

from contextlib import contextmanager
from contextvars import ContextVar
import time
from typing import Callable, Iterator


Clock = Callable[[], float]
_current: ContextVar["InvocationMetrics | None"] = ContextVar(
    "artist_invocation_metrics", default=None
)


class InvocationMetrics:
    """Collect additive durations and counters using a monotonic clock."""

    def __init__(self, clock: Clock = time.perf_counter) -> None:
        self.clock = clock
        self.values: dict[str, float | int] = {}

    def increment(self, name: str, amount: int = 1) -> None:
        self.values[name] = int(self.values.get(name, 0)) + amount

    def add_duration(self, name: str, started_at: float) -> None:
        # Defensive max also protects emitted telemetry from a faulty test clock.
        elapsed_ms = max(0.0, (self.clock() - started_at) * 1000)
        self.values[name] = round(float(self.values.get(name, 0)) + elapsed_ms, 3)

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        started_at = self.clock()
        try:
            yield
        finally:
            self.add_duration(name, started_at)

    def snapshot(self) -> dict[str, float | int]:
        return dict(self.values)


def current_metrics() -> InvocationMetrics | None:
    """Return the collector for this execution context, if one is active."""
    return _current.get()


def activate(metrics: InvocationMetrics):
    """Activate a collector and return the ContextVar reset token."""
    return _current.set(metrics)


def deactivate(token: object) -> None:
    _current.reset(token)  # type: ignore[arg-type]


@contextmanager
def measure(name: str) -> Iterator[None]:
    metrics = current_metrics()
    if metrics is None:
        yield
    else:
        with metrics.measure(name):
            yield


def increment(name: str, amount: int = 1) -> None:
    metrics = current_metrics()
    if metrics is not None:
        metrics.increment(name, amount)
