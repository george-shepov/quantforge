from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, FastAPI

from .auth import verify_hmac
from .bybit import fetch_kline
from .models import KlineRequest, KlineResponse
from .store import ReplayStore


NODE_ID = os.getenv("QUANTFORGE_NODE_ID", "eu-london")
app = FastAPI(title="QuantForge London Connector", version="1.0.0")
app.state.replay_store = ReplayStore(os.getenv("CONNECTOR_SQLITE_PATH", "data/replay.sqlite3"))


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {"status": "ok", "service": "quantforge-london-connector", "execution_enabled": False}


@app.post("/v1/exchanges/bybit/kline", response_model=KlineResponse, dependencies=[Depends(verify_hmac)])
async def kline(request: KlineRequest) -> KlineResponse:
    params = request.model_dump(exclude_none=True)
    started = time.perf_counter()
    status, payload = await fetch_kline(params)
    return KlineResponse(
        request_id=str(uuid4()),
        node_id=NODE_ID,
        exchange="bybit",
        observed_at=datetime.now(timezone.utc),
        latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
        exchange_http_status=status,
        payload=payload,
    )
