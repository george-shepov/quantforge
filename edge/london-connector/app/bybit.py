from __future__ import annotations

import os
from typing import Any

import httpx


BYBIT_KLINE_URL = "https://api.bybit.com/v5/market/kline"


async def fetch_kline(params: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Call the one fixed public Bybit market-data endpoint."""

    async with httpx.AsyncClient(timeout=_timeout_seconds()) as client:
        response = await client.get(BYBIT_KLINE_URL, params=params)
    try:
        payload = response.json()
    except ValueError:
        payload = {"retCode": -1, "retMsg": "Bybit returned non-JSON data"}
    if not isinstance(payload, dict):
        payload = {"retCode": -1, "retMsg": "Bybit returned an invalid payload"}
    return response.status_code, payload


def _timeout_seconds() -> float:
    try:
        return max(1.0, min(float(os.getenv("BYBIT_CONNECTOR_TIMEOUT_SECONDS", "15")), 60.0))
    except ValueError:
        return 15.0
