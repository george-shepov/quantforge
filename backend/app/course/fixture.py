from __future__ import annotations

import hashlib
import json
from typing import Any

from app.research.events import EventKind, MarketEvent


COURSE_DATASET_ID = "course-btc-l2-v1"


def _book_payload(index: int) -> dict[str, Any]:
    mid = 100.0 + index * 0.25
    return {
        "levels": [
            [{"px": f"{mid - 0.5:.2f}", "sz": "1.00"}, {"px": f"{mid - 1.0:.2f}", "sz": "2.00"}],
            [{"px": f"{mid + 0.5:.2f}", "sz": "1.00"}, {"px": f"{mid + 1.0:.2f}", "sz": "2.00"}],
        ]
    }


def course_fixture_events() -> list[MarketEvent]:
    """Return the same small synthetic event stream on every invocation."""

    events: list[MarketEvent] = []
    for index in range(16):
        timestamp_ns = (1_770_000_000 + index) * 1_000_000_000
        events.append(
            MarketEvent.build(
                sequence=index + 1,
                exchange="course_fixture",
                symbol="BTC",
                kind=EventKind.BOOK,
                event_time_ns=timestamp_ns,
                receive_time_ns=timestamp_ns,
                payload=_book_payload(index),
            )
        )
        events.append(
            MarketEvent.build(
                sequence=index + 17,
                exchange="course_fixture",
                symbol="BTC",
                kind=EventKind.TRADE,
                event_time_ns=timestamp_ns + 500_000_000,
                receive_time_ns=timestamp_ns + 500_000_000,
                payload={
                    "coin": "BTC",
                    "px": f"{100.0 + index * 0.25:.2f}",
                    "sz": "0.10",
                    "side": "B" if index % 2 else "A",
                },
            )
        )
    return sorted(events, key=lambda event: event.sequence)


def fixture_checksum_chain(events: list[MarketEvent] | None = None) -> str:
    digest = hashlib.sha256()
    for event in events or course_fixture_events():
        digest.update(event.checksum.encode())
    return digest.hexdigest()


def course_fixture_manifest() -> dict[str, Any]:
    events = course_fixture_events()
    return {
        "dataset_id": COURSE_DATASET_ID,
        "schema_version": 1,
        "source": "synthetic",
        "label": "synthetic course fixture; not current market liquidity",
        "event_count": len(events),
        "min_event_time_ns": min(event.event_time_ns for event in events),
        "max_event_time_ns": max(event.event_time_ns for event in events),
        "symbols": ["BTC"],
        "kinds": sorted({event.kind.value for event in events}),
        "chain_hash": fixture_checksum_chain(events),
        "seed": 7,
    }


def fixture_json() -> str:
    return json.dumps(
        {
            "manifest": course_fixture_manifest(),
            "events": [event.model_dump(mode="json") for event in course_fixture_events()],
        },
        indent=2,
        sort_keys=True,
    )
