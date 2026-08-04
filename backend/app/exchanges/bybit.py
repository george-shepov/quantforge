from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from urllib.parse import urlsplit

import httpx

from app.symbols import canonical_symbol

from app.exchanges.base import ExchangeAdapter, ExchangeAdapterError
from app.exchanges.environment import configured_environment, endpoints_for
from app.models import Candle, MarketDataRequest


class BybitAdapter(ExchangeAdapter):
    name = "bybit"
    interval_map = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "1d": "D"}

    async def fetch_candles(self, request: MarketDataRequest) -> list[Candle]:
        environment = configured_environment(self.name)
        endpoint = endpoints_for(self.name, environment)
        try:
            interval = self.interval_map[request.interval]
        except KeyError as exc:
            raise ExchangeAdapterError(f"Bybit interval is not supported: {request.interval}") from exc

        params: dict[str, str | int] = {
            "category": "linear",
            "symbol": _normalize_symbol(request.symbol),
            "interval": interval,
            "limit": min(request.limit, 1000),
        }
        if request.start_time:
            params["start"] = int(request.start_time.timestamp() * 1000)
        if request.end_time:
            params["end"] = int(request.end_time.timestamp() * 1000)

        if _regional_preferred():
            try:
                payload = await _get_regional_json(params)
            except RegionalConnectorError as regional_error:
                try:
                    payload = await _get_public_json(
                        f"{endpoint.rest}/v5/market/kline", params, operation="market-data"
                    )
                except BybitHttpError as direct_error:
                    raise _regional_failure(regional_error, direct_error) from direct_error
                except ExchangeAdapterError as direct_error:
                    raise ExchangeAdapterError(
                        f"Bybit market-data failed: regional={regional_error}; direct={direct_error}"
                    ) from direct_error
        else:
            try:
                payload = await _get_public_json(
                    f"{endpoint.rest}/v5/market/kline", params, operation="market-data"
                )
            except BybitHttpError as direct_error:
                if direct_error.status_code != 403:
                    raise
                try:
                    payload = await _get_regional_json(params)
                except RegionalConnectorError as regional_error:
                    raise _regional_failure(regional_error, direct_error) from regional_error

        if payload.get("retCode") != 0:
            raise ExchangeAdapterError(f"Bybit rejected market-data request: {payload.get('retMsg', 'unknown error')}")

        try:
            rows = payload["result"]["list"]
            candles = [
                Candle(
                    timestamp=datetime.fromtimestamp(float(row[0]) / 1000, tz=timezone.utc),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
                for row in reversed(rows)
            ]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ExchangeAdapterError("Unexpected Bybit candle response") from exc
        if len(candles) < 20:
            raise ExchangeAdapterError("Bybit returned too few candles")
        return candles[-request.limit :]

    async def fetch_order_book(self, symbol: str, depth: int = 50) -> dict:
        environment = configured_environment(self.name)
        endpoint = endpoints_for(self.name, environment)
        venue_symbol = _normalize_symbol(symbol)
        params = {"category": "linear", "symbol": venue_symbol, "limit": min(depth, 200)}
        payload = await _get_public_json(
            f"{endpoint.rest}/v5/market/orderbook",
            params,
            operation="order-book",
        )
        if payload.get("retCode") != 0:
            raise ExchangeAdapterError(payload.get("retMsg", "Bybit order-book request failed"))
        result = payload["result"]
        return {
            "exchange": self.name,
            "symbol": canonical_symbol(venue_symbol),
            "canonical_symbol": canonical_symbol(venue_symbol),
            "venue_symbol": venue_symbol,
            "timestamp_ms": int(result.get("ts", payload.get("time", 0))),
            "sequence": int(result.get("u", 0)),
            "bids": [[float(p), float(q)] for p, q in result.get("b", [])],
            "asks": [[float(p), float(q)] for p, q in result.get("a", [])],
            "environment": environment.value,
        }


async def _get_public_json(url: str, params: dict[str, str | int], *, operation: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise BybitHttpError(operation, exc.response.status_code) from exc
    except httpx.HTTPError as exc:
        raise ExchangeAdapterError(f"Bybit {operation} request failed: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise ExchangeAdapterError(
            f"Bybit {operation} returned a non-JSON response; inspect the response path and server region."
        ) from exc
    if not isinstance(payload, dict):
        raise ExchangeAdapterError(f"Unexpected Bybit {operation} response")
    return payload


class BybitHttpError(ExchangeAdapterError):
    def __init__(self, operation: str, status_code: int):
        self.status_code = status_code
        super().__init__(f"direct Bybit {operation} HTTP {status_code}")


class RegionalConnectorError(ExchangeAdapterError):
    pass


async def _get_regional_json(params: dict[str, str | int]) -> dict:
    base_url = os.getenv("BYBIT_REGIONAL_CONNECTOR_URL", "").strip().rstrip("/")
    secret = os.getenv("BYBIT_REGIONAL_CONNECTOR_SECRET", "")
    if not base_url or not secret:
        raise RegionalConnectorError("regional connector is not configured")
    parts = urlsplit(base_url)
    if parts.scheme != "https" or not parts.netloc or parts.query or parts.fragment:
        raise RegionalConnectorError("regional connector URL is invalid")

    path = "/v1/exchanges/bybit/kline"
    body = json.dumps(params, separators=(",", ":"), sort_keys=True).encode("utf-8")
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(24)
    canonical = "\n".join((timestamp, nonce, "POST", path, hashlib.sha256(body).hexdigest())).encode()
    signature = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-QuantForge-Timestamp": timestamp,
        "X-QuantForge-Nonce": nonce,
        "X-QuantForge-Signature": signature,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(f"{base_url}{path}", content=body, headers=headers)
    except httpx.HTTPError as exc:
        raise RegionalConnectorError("regional connector request failed") from exc
    if response.status_code < 200 or response.status_code >= 300:
        raise RegionalConnectorError(f"regional connector HTTP {response.status_code}")
    try:
        envelope = response.json()
    except ValueError as exc:
        raise RegionalConnectorError("regional connector returned invalid JSON") from exc
    if not isinstance(envelope, dict) or envelope.get("exchange") != "bybit":
        raise RegionalConnectorError("regional connector returned an invalid envelope")
    upstream_status = envelope.get("exchange_http_status")
    payload = envelope.get("payload")
    if not isinstance(upstream_status, int) or not isinstance(payload, dict):
        raise RegionalConnectorError("regional connector returned an invalid result")
    if upstream_status < 200 or upstream_status >= 300:
        raise RegionalConnectorError(f"regional Bybit HTTP {upstream_status}")
    return payload


def _regional_preferred() -> bool:
    return os.getenv("BYBIT_REGIONAL_CONNECTOR_PREFER", "true").lower() == "true"


def _regional_failure(regional_error: RegionalConnectorError, direct_error: BybitHttpError) -> ExchangeAdapterError:
    return ExchangeAdapterError(
        f"Bybit market-data failed: direct=HTTP {direct_error.status_code}; regional={regional_error}"
    )


def _normalize_symbol(symbol: str) -> str:
    parts = [part for part in re.split(r"[/_:\-]", symbol.upper()) if part and part not in {"PERP", "PERPETUAL"}]
    if len(parts) > 1:
        base, quote = parts[0], next((part for part in parts[1:] if part in {"USDT", "USDC"}), "USDT")
        return f"{base}{quote}"
    value = parts[0] if parts else symbol.upper()
    return value if value.endswith(("USDT", "USDC")) else f"{value}USDT"
