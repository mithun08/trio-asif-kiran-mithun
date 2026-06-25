from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import MagicMock, patch

from matcher.models.consultant import Consultant
from matcher.pipeline.extract import extract_signals, extract_signals_async


def _noop(c: Consultant, *args: object) -> Consultant:
    return c


def test_async_matches_sync_result() -> None:
    consultant = Consultant(email="a@b.com", name="A", raw_profile_text="")
    with (
        patch("matcher.pipeline.extract.extract_profile", side_effect=_noop),
        patch("matcher.pipeline.extract.extract_feedback", side_effect=_noop),
        patch("matcher.pipeline.extract.extract_adaptability", side_effect=_noop),
        patch("matcher.pipeline.extract.extract_trend", side_effect=_noop),
    ):
        sync_result = extract_signals([consultant], MagicMock())
        async_result = asyncio.run(extract_signals_async([consultant], MagicMock()))
    assert sync_result[0].email == async_result[0].email


def test_max_workers_respected() -> None:
    active: list[int] = []
    lock = threading.Lock()
    max_seen = 0

    def slow_extract(c: Consultant, *args: object) -> Consultant:
        nonlocal max_seen
        with lock:
            active.append(1)
            max_seen = max(max_seen, len(active))
        time.sleep(0.05)
        with lock:
            active.pop()
        return c

    consultants = [
        Consultant(email=f"{i}@b.com", name=str(i), raw_profile_text="text") for i in range(10)
    ]
    with (
        patch("matcher.pipeline.extract.extract_profile", side_effect=slow_extract),
        patch("matcher.pipeline.extract.extract_adaptability", side_effect=_noop),
        patch("matcher.pipeline.extract.extract_trend", side_effect=_noop),
    ):
        asyncio.run(extract_signals_async(consultants, MagicMock(), max_workers=3))

    assert max_seen <= 3


def test_output_order_preserved() -> None:
    emails = ["a@b.com", "c@d.com", "e@f.com"]
    consultants = [Consultant(email=e, name=e) for e in emails]
    with (
        patch("matcher.pipeline.extract.extract_profile", side_effect=_noop),
        patch("matcher.pipeline.extract.extract_feedback", side_effect=_noop),
        patch("matcher.pipeline.extract.extract_adaptability", side_effect=_noop),
        patch("matcher.pipeline.extract.extract_trend", side_effect=_noop),
    ):
        result = asyncio.run(extract_signals_async(consultants, MagicMock()))
    assert [c.email for c in result] == emails
