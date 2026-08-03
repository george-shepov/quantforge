from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Literal

from pydantic import BaseModel, Field


class EventKind(str, Enum):
    BOOK = "book"
    TRADE = "trade"
    MID = "mid"
    FUNDING = "funding"
    TIMER = "timer"


class MarketEvent(BaseModel):
    schema_version: int = 1
    sequence: int = Field(ge=1)
    exchange: str
    symbol: str
    kind: EventKind
    event_time_ns: int = Field(ge=0)
    receive_time_ns: int = Field(ge=0)
    payload: dict[str, Any]
    checksum: str

    @classmethod
    def build(
        cls,
        *,
        sequence: int,
        exchange: str,
        symbol: str,
        kind: EventKind,
        event_time_ns: int,
        receive_time_ns: int,
        payload: dict[str, Any],
    ) -> "MarketEvent":
        canonical = json.dumps(
            {
                "schema_version": 1,
                "sequence": sequence,
                "exchange": exchange,
                "symbol": symbol,
                "kind": kind.value,
                "event_time_ns": event_time_ns,
                "receive_time_ns": receive_time_ns,
                "payload": payload,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return cls(
            sequence=sequence,
            exchange=exchange,
            symbol=symbol,
            kind=kind,
            event_time_ns=event_time_ns,
            receive_time_ns=receive_time_ns,
            payload=payload,
            checksum=hashlib.sha256(canonical.encode()).hexdigest(),
        )


class EventSequencer:
    def __init__(self, start: int = 0) -> None:
        self._value = start

    def next(self) -> int:
        self._value += 1
        return self._value


def event_sort_key(event: MarketEvent) -> tuple[int, int, int, str]:
    return (event.event_time_ns, event.receive_time_ns, event.sequence, event.checksum)


def _as_ns(value: Any, fallback: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return fallback
    if numeric < 10_000_000_000:
        return numeric * 1_000_000_000
    if numeric < 10_000_000_000_000:
        return numeric * 1_000_000
    return numeric


def normalize_hyperliquid_message(
    message: dict[str, Any], sequencer: EventSequencer, *, receive_time_ns: int | None = None
) -> list[MarketEvent]:
    channel = str(message.get("channel", ""))
    data = message.get("data")
    received = receive_time_ns or time.time_ns()
    events: list[MarketEvent] = []

    def build(symbol: str, kind: EventKind, payload: dict[str, Any], event_time: Any = None) -> MarketEvent:
        return MarketEvent.build(
            sequence=sequencer.next(),
            exchange="hyperliquid",
            symbol=symbol,
            kind=kind,
            event_time_ns=_as_ns(event_time, received),
            receive_time_ns=received,
            payload=payload,
        )

    if channel == "l2Book" and isinstance(data, dict):
        events.append(build(str(data.get("coin", "UNKNOWN")), EventKind.BOOK, data, data.get("time")))
    elif channel == "trades" and isinstance(data, list):
        for trade in data:
            if isinstance(trade, dict):
                events.append(build(str(trade.get("coin", "UNKNOWN")), EventKind.TRADE, trade, trade.get("time")))
    elif channel == "allMids" and isinstance(data, dict):
        mids = data.get("mids", data)
        status_time = data.get("statusTimestamp")
        if isinstance(mids, dict):
            for symbol, mid in mids.items():
                events.append(build(str(symbol), EventKind.MID, {"mid": mid}, status_time))
    elif channel == "activeAssetCtx" and isinstance(data, dict):
        symbol = str(data.get("coin", "UNKNOWN"))
        ctx = data.get("ctx", {})
        if isinstance(ctx, dict) and "funding" in ctx:
            events.append(build(symbol, EventKind.FUNDING, {"funding": ctx.get("funding"), "ctx": ctx}))
    return events


class DatasetManifest(BaseModel):
    dataset_id: str
    created_at: datetime
    updated_at: datetime
    schema_version: int = 1
    event_count: int = 0
    min_event_time_ns: int | None = None
    max_event_time_ns: int | None = None
    parts: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    exchanges: list[str] = Field(default_factory=list)
    kinds: list[str] = Field(default_factory=list)
    chain_hash: str = "0" * 64


class EventDatasetCatalog:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or os.getenv("QUANTFORGE_DATA_ROOT", "/data/quantforge"))
        self.root.mkdir(parents=True, exist_ok=True)

    def new_dataset_id(self) -> str:
        return f"hl-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:10]}"

    def _dataset_dir(self, dataset_id: str) -> Path:
        safe = dataset_id.replace("/", "_").replace("..", "_")
        return self.root / safe

    def _manifest_path(self, dataset_id: str) -> Path:
        return self._dataset_dir(dataset_id) / "manifest.json"

    def _load_or_create(self, dataset_id: str) -> DatasetManifest:
        path = self._manifest_path(dataset_id)
        if path.exists():
            return DatasetManifest.model_validate_json(path.read_text())
        now = datetime.now(timezone.utc)
        return DatasetManifest(dataset_id=dataset_id, created_at=now, updated_at=now)

    def _save_manifest(self, manifest: DatasetManifest) -> None:
        path = self._manifest_path(manifest.dataset_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(manifest.model_dump_json(indent=2))
        tmp.replace(path)

    def append(self, dataset_id: str, events: Iterable[MarketEvent]) -> DatasetManifest:
        batch = sorted(list(events), key=event_sort_key)
        if not batch:
            return self._load_or_create(dataset_id)
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise RuntimeError("pyarrow is required for Parquet datasets") from exc

        manifest = self._load_or_create(dataset_id)
        groups: dict[tuple[str, str, str], list[MarketEvent]] = defaultdict(list)
        for event in batch:
            day = datetime.fromtimestamp(event.event_time_ns / 1e9, tz=timezone.utc).strftime("%Y-%m-%d")
            groups[(event.exchange, event.symbol, day)].append(event)

        for (exchange, symbol, day), group in groups.items():
            relative = Path(f"exchange={exchange}") / f"symbol={symbol}" / f"date={day}"
            folder = self._dataset_dir(dataset_id) / relative
            folder.mkdir(parents=True, exist_ok=True)
            part_name = f"part-{len(manifest.parts):06d}-{uuid.uuid4().hex[:8]}.parquet"
            target = folder / part_name
            temp = target.with_suffix(".parquet.tmp")
            rows = [
                {
                    "schema_version": event.schema_version,
                    "sequence": event.sequence,
                    "exchange": event.exchange,
                    "symbol": event.symbol,
                    "kind": event.kind.value,
                    "event_time_ns": event.event_time_ns,
                    "receive_time_ns": event.receive_time_ns,
                    "payload_json": json.dumps(event.payload, sort_keys=True, separators=(",", ":")),
                    "checksum": event.checksum,
                }
                for event in group
            ]
            pq.write_table(pa.Table.from_pylist(rows), temp, compression="zstd")
            temp.replace(target)
            manifest.parts.append(str(relative / part_name))

        manifest.event_count += len(batch)
        manifest.min_event_time_ns = min(
            [event.event_time_ns for event in batch]
            + ([manifest.min_event_time_ns] if manifest.min_event_time_ns is not None else [])
        )
        manifest.max_event_time_ns = max(
            [event.event_time_ns for event in batch]
            + ([manifest.max_event_time_ns] if manifest.max_event_time_ns is not None else [])
        )
        manifest.symbols = sorted(set(manifest.symbols) | {event.symbol for event in batch})
        manifest.exchanges = sorted(set(manifest.exchanges) | {event.exchange for event in batch})
        manifest.kinds = sorted(set(manifest.kinds) | {event.kind.value for event in batch})
        manifest.updated_at = datetime.now(timezone.utc)
        digest = hashlib.sha256()
        digest.update(manifest.chain_hash.encode())
        for event in batch:
            digest.update(event.checksum.encode())
        manifest.chain_hash = digest.hexdigest()
        self._save_manifest(manifest)
        return manifest

    def get(self, dataset_id: str) -> DatasetManifest:
        path = self._manifest_path(dataset_id)
        if not path.exists():
            raise FileNotFoundError(dataset_id)
        return self._derive_manifest_fields(DatasetManifest.model_validate_json(path.read_text()))

    def list(self) -> list[DatasetManifest]:
        manifests: list[DatasetManifest] = []
        for path in self.root.glob("*/manifest.json"):
            try:
                manifests.append(self._derive_manifest_fields(DatasetManifest.model_validate_json(path.read_text())))
            except Exception:
                continue
        return sorted(manifests, key=lambda item: item.created_at, reverse=True)

    @staticmethod
    def _derive_manifest_fields(manifest: DatasetManifest) -> DatasetManifest:
        if not manifest.exchanges:
            manifest.exchanges = sorted(
                {
                    part.split("/", 1)[0].removeprefix("exchange=")
                    for part in manifest.parts
                    if part.startswith("exchange=")
                }
            )
        return manifest

    def read(self, dataset_id: str) -> list[MarketEvent]:
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise RuntimeError("pyarrow is required for Parquet datasets") from exc
        manifest = self.get(dataset_id)
        events: list[MarketEvent] = []
        base = self._dataset_dir(dataset_id)
        for part in manifest.parts:
            table = pq.read_table(base / part)
            for row in table.to_pylist():
                events.append(
                    MarketEvent(
                        schema_version=row["schema_version"],
                        sequence=row["sequence"],
                        exchange=row["exchange"],
                        symbol=row["symbol"],
                        kind=EventKind(row["kind"]),
                        event_time_ns=row["event_time_ns"],
                        receive_time_ns=row["receive_time_ns"],
                        payload=json.loads(row["payload_json"]),
                        checksum=row["checksum"],
                    )
                )
        return sorted(events, key=event_sort_key)


class RecorderConfig(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["BTC", "ETH"])
    network: Literal["mainnet", "testnet"] = "mainnet"
    flush_size: int = Field(default=2_000, ge=1, le=100_000)
    flush_interval_seconds: float = Field(default=5.0, ge=0.25, le=60.0)
    reconnect_max_seconds: float = Field(default=30.0, ge=1.0, le=300.0)


class HyperliquidRecorder:
    URLS = {
        "mainnet": "wss://api.hyperliquid.xyz/ws",
        "testnet": "wss://api.hyperliquid-testnet.xyz/ws",
    }

    def __init__(self, catalog: EventDatasetCatalog, dataset_id: str, config: RecorderConfig) -> None:
        self.catalog = catalog
        self.dataset_id = dataset_id
        self.config = config
        self.sequencer = EventSequencer()
        self.stop_event = asyncio.Event()
        self.connected = False
        self.events_recorded = 0
        self.last_error: str | None = None
        self.started_at = datetime.now(timezone.utc)

    def status(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "network": self.config.network,
            "symbols": self.config.symbols,
            "connected": self.connected,
            "events_recorded": self.events_recorded,
            "last_error": self.last_error,
            "started_at": self.started_at,
            "stopping": self.stop_event.is_set(),
        }

    async def stop(self) -> None:
        self.stop_event.set()

    async def run(self) -> None:
        delay = 1.0
        while not self.stop_event.is_set():
            try:
                await self._stream_once()
                delay = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.connected = False
                self.last_error = str(exc)
                try:
                    await asyncio.wait_for(self.stop_event.wait(), timeout=delay)
                except TimeoutError:
                    pass
                delay = min(delay * 2, self.config.reconnect_max_seconds)

    async def _stream_once(self) -> None:
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("websockets is required for market recording") from exc

        buffer: list[MarketEvent] = []
        last_flush = time.monotonic()
        async with websockets.connect(
            self.URLS[self.config.network], ping_interval=20, ping_timeout=20, close_timeout=5, max_size=8_000_000
        ) as socket:
            self.connected = True
            self.last_error = None
            subscriptions: list[dict[str, Any]] = [{"type": "allMids"}]
            for symbol in self.config.symbols:
                subscriptions.extend(
                    [
                        {"type": "l2Book", "coin": symbol},
                        {"type": "trades", "coin": symbol},
                        {"type": "activeAssetCtx", "coin": symbol},
                    ]
                )
            for subscription in subscriptions:
                await socket.send(json.dumps({"method": "subscribe", "subscription": subscription}))

            while not self.stop_event.is_set():
                try:
                    raw = await asyncio.wait_for(socket.recv(), timeout=1.0)
                except TimeoutError:
                    raw = None
                if raw:
                    message = json.loads(raw)
                    for event in normalize_hyperliquid_message(message, self.sequencer):
                        if event.symbol in self.config.symbols:
                            buffer.append(event)
                if buffer and (
                    len(buffer) >= self.config.flush_size
                    or time.monotonic() - last_flush >= self.config.flush_interval_seconds
                ):
                    self.catalog.append(self.dataset_id, buffer)
                    self.events_recorded += len(buffer)
                    buffer.clear()
                    last_flush = time.monotonic()
            if buffer:
                self.catalog.append(self.dataset_id, buffer)
                self.events_recorded += len(buffer)
            self.connected = False


class RecorderManager:
    def __init__(self, catalog: EventDatasetCatalog) -> None:
        self.catalog = catalog
        self._recorders: dict[str, HyperliquidRecorder] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def start(self, config: RecorderConfig) -> dict[str, Any]:
        dataset_id = self.catalog.new_dataset_id()
        recorder = HyperliquidRecorder(self.catalog, dataset_id, config)
        self._recorders[dataset_id] = recorder
        task = asyncio.create_task(recorder.run(), name=f"quantforge-recorder-{dataset_id}")
        self._tasks[dataset_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(dataset_id, None))
        return recorder.status()

    async def stop(self, dataset_id: str) -> dict[str, Any]:
        recorder = self._recorders.get(dataset_id)
        if not recorder:
            raise KeyError(dataset_id)
        await recorder.stop()
        task = self._tasks.get(dataset_id)
        if task:
            try:
                await asyncio.wait_for(task, timeout=10)
            except TimeoutError:
                task.cancel()
        return recorder.status()

    def status(self, dataset_id: str | None = None) -> list[dict[str, Any]] | dict[str, Any]:
        if dataset_id:
            recorder = self._recorders.get(dataset_id)
            if not recorder:
                raise KeyError(dataset_id)
            return recorder.status()
        return [recorder.status() for recorder in self._recorders.values()]
