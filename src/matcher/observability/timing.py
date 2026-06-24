from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager

from matcher.models.telemetry import RunTelemetry
from matcher.observability.run_log import log_stage_timing


@contextmanager
def stage_timer(name: str, telemetry: RunTelemetry | None = None) -> Generator[None, None, None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        log_stage_timing(name, elapsed_ms)
        if telemetry is not None:
            telemetry.stage_timings_ms[name] = elapsed_ms
