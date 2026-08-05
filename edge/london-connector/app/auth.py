from __future__ import annotations

import hashlib
import hmac
import os
import re
import time

from fastapi import Depends, HTTPException, Request

from .store import ReplayStore


NONCE_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{16,128}$")


def get_replay_store(request: Request) -> ReplayStore:
    return request.app.state.replay_store


async def verify_hmac(request: Request, store: ReplayStore = Depends(get_replay_store)) -> None:
    timestamp_value = request.headers.get("X-QuantForge-Timestamp", "")
    nonce = request.headers.get("X-QuantForge-Nonce", "")
    signature = request.headers.get("X-QuantForge-Signature", "")
    try:
        timestamp = int(timestamp_value)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid authentication") from exc

    ttl = _ttl_seconds()
    if abs(int(time.time()) - timestamp) > ttl or not NONCE_PATTERN.fullmatch(nonce):
        raise HTTPException(status_code=401, detail="expired or invalid authentication")
    if not re.fullmatch(r"[0-9a-f]{64}", signature):
        raise HTTPException(status_code=401, detail="invalid authentication")

    body = await request.body()
    body_digest = hashlib.sha256(body).hexdigest()
    canonical = "\n".join((timestamp_value, nonce, request.method, request.url.path, body_digest)).encode()
    expected = hmac.new(_secret().encode(), canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="invalid authentication")
    if not store.claim(nonce, timestamp, ttl):
        raise HTTPException(status_code=409, detail="replayed request")


def _secret() -> str:
    secret = os.getenv("BYBIT_REGIONAL_CONNECTOR_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(status_code=503, detail="connector authentication is not configured")
    return secret


def _ttl_seconds() -> int:
    try:
        value = int(os.getenv("BYBIT_REGIONAL_CONNECTOR_AUTH_TTL_SECONDS", "30"))
    except ValueError:
        value = 30
    return max(5, min(value, 300))
