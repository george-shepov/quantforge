from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


API_KEY_HEADER = "X-QuantForge-API-Key"
ADMIN_TOKEN_HEADER = "X-QuantForge-Admin-Token"


@dataclass(frozen=True)
class ApiPrincipal:
    key_id: str
    name: str
    plan: str
    monthly_quota: int
    rate_limit_per_minute: int


class MeteringStore:
    """Small durable metering store.

    SQLite keeps the first release dependency-free and works for a single API
    service. The schema is intentionally portable so it can later move to
    PostgreSQL without changing the HTTP contract.
    """

    def __init__(self, database_path: str | None = None) -> None:
        configured = database_path or os.getenv(
            "QUANTFORGE_METERING_DB", "/data/quantforge/metering.sqlite3"
        )
        self.path = Path(configured)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS api_keys (
                    key_id TEXT PRIMARY KEY,
                    key_hash TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    monthly_quota INTEGER NOT NULL,
                    rate_limit_per_minute INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT
                );
                CREATE TABLE IF NOT EXISTS api_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    period TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    units INTEGER NOT NULL DEFAULT 1,
                    latency_ms REAL NOT NULL,
                    FOREIGN KEY (key_id) REFERENCES api_keys(key_id)
                );
                CREATE INDEX IF NOT EXISTS idx_api_usage_key_period
                    ON api_usage(key_id, period);
                CREATE INDEX IF NOT EXISTS idx_api_usage_occurred_at
                    ON api_usage(occurred_at);
                """
            )

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @staticmethod
    def current_period() -> str:
        return datetime.now(UTC).strftime("%Y-%m")

    def create_key(
        self,
        *,
        name: str,
        plan: str,
        monthly_quota: int,
        rate_limit_per_minute: int,
    ) -> dict[str, str | int]:
        raw_key = f"qf_live_{secrets.token_urlsafe(32)}"
        key_id = f"key_{secrets.token_hex(8)}"
        created_at = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO api_keys (
                    key_id, key_hash, name, plan, monthly_quota,
                    rate_limit_per_minute, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key_id,
                    self._hash_key(raw_key),
                    name,
                    plan,
                    monthly_quota,
                    rate_limit_per_minute,
                    created_at,
                ),
            )
        return {
            "id": key_id,
            "apiKey": raw_key,
            "name": name,
            "plan": plan,
            "monthlyQuota": monthly_quota,
            "rateLimitPerMinute": rate_limit_per_minute,
            "createdAt": created_at,
        }

    def authenticate(self, raw_key: str) -> ApiPrincipal | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT key_id, name, plan, monthly_quota, rate_limit_per_minute
                FROM api_keys
                WHERE key_hash = ? AND enabled = 1
                """,
                (self._hash_key(raw_key),),
            ).fetchone()
        if row is None:
            return None
        return ApiPrincipal(
            key_id=row["key_id"],
            name=row["name"],
            plan=row["plan"],
            monthly_quota=row["monthly_quota"],
            rate_limit_per_minute=row["rate_limit_per_minute"],
        )

    def usage_for_period(self, key_id: str, period: str | None = None) -> int:
        selected_period = period or self.current_period()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(units), 0) AS units
                FROM api_usage
                WHERE key_id = ? AND period = ?
                """,
                (key_id, selected_period),
            ).fetchone()
        return int(row["units"])

    def usage_last_minute(self, key_id: str) -> int:
        cutoff = datetime.fromtimestamp(time.time() - 60, tz=UTC).isoformat()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(units), 0) AS units
                FROM api_usage
                WHERE key_id = ? AND occurred_at >= ?
                """,
                (key_id, cutoff),
            ).fetchone()
        return int(row["units"])

    def record_usage(
        self,
        *,
        principal: ApiPrincipal,
        method: str,
        path: str,
        status_code: int,
        latency_ms: float,
        units: int = 1,
    ) -> None:
        occurred_at = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO api_usage (
                    key_id, occurred_at, period, method, path,
                    status_code, units, latency_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    principal.key_id,
                    occurred_at,
                    self.current_period(),
                    method,
                    path,
                    status_code,
                    units,
                    latency_ms,
                ),
            )
            connection.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE key_id = ?",
                (occurred_at, principal.key_id),
            )

    def usage_summary(self, principal: ApiPrincipal) -> dict[str, str | int]:
        used = self.usage_for_period(principal.key_id)
        remaining = max(principal.monthly_quota - used, 0)
        return {
            "keyId": principal.key_id,
            "name": principal.name,
            "plan": principal.plan,
            "period": self.current_period(),
            "used": used,
            "monthlyQuota": principal.monthly_quota,
            "remaining": remaining,
            "rateLimitPerMinute": principal.rate_limit_per_minute,
        }


class MeteredApiMiddleware(BaseHTTPMiddleware):
    EXEMPT_PATHS = {
        "/api/health",
        "/api/developer/keys",
        "/docs",
        "/openapi.json",
        "/redoc",
    }

    def __init__(self, app, store: MeteringStore) -> None:
        super().__init__(app)
        self.store = store

    async def dispatch(self, request: Request, call_next):
        enabled = os.getenv("QUANTFORGE_METERED_API_ENABLED", "false").lower() == "true"
        if not enabled or not request.url.path.startswith("/api/"):
            return await call_next(request)
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        raw_key = request.headers.get(API_KEY_HEADER)
        if not raw_key:
            return JSONResponse(
                status_code=401,
                content={"detail": f"Missing {API_KEY_HEADER} header"},
            )

        principal = self.store.authenticate(raw_key)
        if principal is None:
            return JSONResponse(status_code=401, content={"detail": "Invalid API key"})

        used = self.store.usage_for_period(principal.key_id)
        if used >= principal.monthly_quota:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": "3600"},
                content={
                    "detail": "Monthly API quota exceeded",
                    "period": self.store.current_period(),
                    "used": used,
                    "quota": principal.monthly_quota,
                },
            )

        recent = self.store.usage_last_minute(principal.key_id)
        if recent >= principal.rate_limit_per_minute:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": "60"},
                content={"detail": "Per-minute API rate limit exceeded"},
            )

        request.state.api_principal = principal
        started = time.perf_counter()
        response = await call_next(request)
        latency_ms = (time.perf_counter() - started) * 1000
        self.store.record_usage(
            principal=principal,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_ms=latency_ms,
        )
        response.headers["X-QuantForge-Usage-Limit"] = str(principal.monthly_quota)
        response.headers["X-QuantForge-Usage-Remaining"] = str(
            max(principal.monthly_quota - used - 1, 0)
        )
        response.headers["X-QuantForge-RateLimit-Minute"] = str(
            principal.rate_limit_per_minute
        )
        return response


def require_admin_token(request: Request) -> None:
    expected = os.getenv("QUANTFORGE_METERING_ADMIN_TOKEN")
    supplied = request.headers.get(ADMIN_TOKEN_HEADER)
    if not expected:
        raise HTTPException(status_code=503, detail="Metering admin token is not configured")
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid metering admin token")


def require_api_principal(request: Request, store: MeteringStore) -> ApiPrincipal:
    principal = getattr(request.state, "api_principal", None)
    if principal is not None:
        return principal
    raw_key = request.headers.get(API_KEY_HEADER)
    if not raw_key:
        raise HTTPException(status_code=401, detail=f"Missing {API_KEY_HEADER} header")
    principal = store.authenticate(raw_key)
    if principal is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return principal
