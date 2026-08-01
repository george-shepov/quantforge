# QuantForge — Crypto Strategy Lab

QuantForge is a simulation-first crypto research platform for testing spot, perpetual, and futures strategies. It now supports both candle backtests and deterministic event-driven research over recorded market microstructure.

## Safety boundary

QuantForge remains **simulation first**. Mainnet order submission is not implemented in the research API. The optional execution adapter is Hyperliquid **testnet only**, defaults to dry-run, and refuses submission unless all of these are true:

1. `QUANTFORGE_TESTNET_EXECUTION_ENABLED=true`
2. `QUANTFORGE_EXECUTION_NETWORK=testnet`
3. A server-side safety token is configured and supplied in `X-QuantForge-Safety-Token`
4. The request includes `I_UNDERSTAND_THIS_IS_TESTNET`
5. Testnet credentials are configured
6. The order stays below the configured notional cap
7. New exposure uses maker-only `Alo` orders

There is no mainnet URL, mainnet switch, withdrawal function, wallet-connect flow, or generic signed-action endpoint in this adapter.

## Event research milestone

### Hyperliquid WebSocket recorder

The recorder subscribes to public Hyperliquid feeds for:

- L2 book snapshots
- Trades
- All mids
- Active asset context funding updates

It reconnects with bounded exponential backoff, assigns monotonic local sequence numbers, preserves exchange and receive timestamps, and computes a canonical SHA-256 checksum for every event.

### Parquet dataset catalog

Events are stored as Zstandard-compressed Parquet partitions:

```text
/data/quantforge/<dataset-id>/
  manifest.json
  exchange=hyperliquid/symbol=BTC/date=2026-08-01/part-....parquet
```

Each manifest tracks event count, time range, symbols, event kinds, parts, and an append-only checksum chain. Replay ordering is deterministic by event time, receive time, sequence, and checksum.

### Strategy SDK

Event strategies subclass `app.research.engine.Strategy` and implement any of:

```python
def on_book(self, context): ...
def on_trade(self, context): ...
def on_funding(self, context): ...
def on_timer(self, context): ...
```

Included strategies:

- `cross_exchange_arbitrage`
- `inventory_market_making`

### Portfolio, arbitrage, and market making

The event engine includes:

- Multi-asset, multi-exchange positions and marks
- Cash, fees, funding, realized P&L, and equity snapshots
- Cross-exchange best-bid/best-ask arbitrage scanning
- Inventory-skewed market-making quotes
- Seeded queue-ahead and trade-through fill simulation

### Experiment system

Experiments support:

- Cartesian parameter sweeps
- Walk-forward test windows
- Seeded block Monte Carlo resampling
- PostgreSQL experiment records
- Redis/RQ worker execution

## Run with Docker

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Terminal: http://localhost:4173
- API docs: http://localhost:8008/docs
- Health: http://localhost:8008/api/health
- Research capabilities: http://localhost:8008/api/research/capabilities

When deployed behind the shared VPS edge, open `https://quantforge.giorgiy.org`. The frontend proxies `/api`, `/docs`, and `/openapi.json` to the internal API service; no application port is published on the VPS host.

## Record market events

```bash
curl -X POST http://localhost:8008/api/research/recordings \
  -H 'Content-Type: application/json' \
  -d '{"symbols":["BTC","ETH"],"network":"mainnet","flush_size":2000}'
```

Stop the returned dataset ID:

```bash
curl -X DELETE http://localhost:8008/api/research/recordings/<dataset-id>
```

List datasets:

```bash
curl http://localhost:8008/api/research/datasets
```

## Deterministic replay

```bash
curl -X POST http://localhost:8008/api/research/replay \
  -H 'Content-Type: application/json' \
  -d '{
    "dataset_id":"<dataset-id>",
    "strategy":"inventory_market_making",
    "parameters":{"spread_bps":8,"inventory_skew_bps":3,"quantity":0.01},
    "timer_interval_ms":1000
  }'
```

## Queue an experiment

```bash
curl -X POST http://localhost:8008/api/research/experiments \
  -H 'Content-Type: application/json' \
  -d '{
    "dataset_id":"<dataset-id>",
    "strategy":"cross_exchange_arbitrage",
    "base_parameters":{"fee_bps":2},
    "parameter_grid":{"min_edge_bps":[3,5,8],"max_quantity":[0.1,0.25]},
    "walk_forward_folds":4,
    "monte_carlo_runs":1000
  }'
```

## Testnet adapter

Dry-run does not need credentials or a safety token:

```bash
curl -X POST http://localhost:8008/api/research/execution/testnet-order \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"BTC","side":"buy","size":0.001,"limit_price":50000,"submit":false}'
```

Actual testnet submission additionally requires the environment gates and safety header. Keep the gate disabled in normal research deployments.

## Existing candle backtester

The original MVP remains available at `POST /api/backtests/run` with:

- Hyperliquid and BitMEX public candle adapters
- Deterministic synthetic fallback
- Spot, perpetual, and futures modes
- Market and limit entries
- Fees, slippage, leverage, funding, liquidation, stops, and targets
- EMA crossover, mean reversion, and breakout strategies
- Stress scenarios and performance metrics

## Development

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. pytest -q
uvicorn app.main:app --reload --port 8008
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```
