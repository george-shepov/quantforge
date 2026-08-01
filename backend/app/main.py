from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.engine import run_backtest
from app.exchanges import get_exchange_adapter
from app.exchanges.base import ExchangeAdapterError
from app.exchanges.environment import configured_environment, endpoints_for
from app.exchanges.synthetic import SyntheticAdapter
from app.models import BacktestRequest, BacktestResponse
from app.research.api import router as research_router

app = FastAPI(title="QuantForge API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173", "*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(research_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "quantforge-api", "version": "0.3.0"}


@app.get("/api/catalog")
async def catalog() -> dict:
    exchanges = ["hyperliquid", "bybit", "bitmex", "whitebit", "synthetic"]
    environments = {}
    for exchange in exchanges[:-1]:
        environment = configured_environment(exchange)
        endpoint = endpoints_for(exchange, environment)
        environments[exchange] = {
            "environment": environment.value,
            "websocketConfigured": bool(endpoint.websocket),
            "executionAllowed": False,
            "badge": f"{exchange.upper()} {environment.value.upper()} — EXECUTION DISABLED",
        }
    environments["synthetic"] = {
        "environment": "simulation",
        "websocketConfigured": False,
        "executionAllowed": False,
        "badge": "SYNTHETIC SIMULATION",
    }
    return {
        "exchanges": exchanges,
        "exchangeEnvironments": environments,
        "symbols": ["BTC", "ETH", "SOL", "HYPE"],
        "intervals": ["5m", "15m", "1h", "4h", "1d"],
        "marketKinds": ["spot", "perp", "future"],
        "strategies": ["ema_crossover", "mean_reversion", "breakout"],
        "eventStrategies": ["cross_exchange_arbitrage", "inventory_market_making"],
        "scenarios": ["baseline", "flash_crash", "volatility_spike", "liquidity_drought", "funding_squeeze"],
        "mainnetOrderSubmission": False,
    }


@app.post("/api/backtests/run", response_model=BacktestResponse)
async def backtest(request: BacktestRequest) -> BacktestResponse:
    warnings: list[str] = []
    allow_network = os.getenv("QUANTFORGE_ALLOW_NETWORK", "true").lower() == "true"
    adapter = get_exchange_adapter(request.market.exchange)
    source = adapter.name

    if request.market.exchange.value != "synthetic" and not allow_network:
        if not request.market.fallback_to_synthetic:
            raise HTTPException(status_code=503, detail="Network market data is disabled")
        adapter = SyntheticAdapter()
        source = "synthetic-fallback"

    try:
        candles = await adapter.fetch_candles(request.market)
    except ExchangeAdapterError as exc:
        if not request.market.fallback_to_synthetic:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        warnings.append(str(exc))
        candles = await SyntheticAdapter().fetch_candles(request.market)
        source = "synthetic-fallback"

    return await run_backtest(request, candles, source, warnings)
