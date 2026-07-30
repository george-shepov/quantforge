# QuantForge — Crypto Strategy Lab

QuantForge is a simulation-first crypto research platform for testing spot, perpetual, and futures strategies without placing real orders or connecting a wallet.

## Included in this MVP

- Hyperliquid public candle adapter (`POST https://api.hyperliquid.xyz/info`, `candleSnapshot`)
- BitMEX public bucketed-trades adapter (`GET /api/v1/trade/bucketed`)
- Deterministic synthetic fallback for offline development and reproducible tests
- Spot, perpetual, and futures simulation modes
- Market and limit entry orders
- Fees, slippage, leverage, funding, maintenance margin, stops, targets, and liquidation
- EMA crossover, mean-reversion, and breakout strategies
- Flash-crash, volatility-spike, liquidity-drought, and funding-squeeze scenarios
- Equity curve, drawdown, Sharpe, Sortino, return, win rate, expectancy, fees, funding, MAE/MFE, and trade ledger
- React/Recharts terminal UI
- Docker Compose deployment

## Safety boundary

QuantForge does **not** request private exchange keys, connect a wallet, sign orders, or submit live trades. Exchange integrations in this version are read-only market-data adapters.

## Run with Docker

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Terminal: http://localhost:4173
- API docs: http://localhost:8008/docs
- Health: http://localhost:8008/api/health

## Run for development

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Test

```bash
cd backend
PYTHONPATH=. pytest -q
```

## API example

```bash
curl -X POST http://localhost:8008/api/backtests/run \
  -H 'Content-Type: application/json' \
  -d '{
    "market": {
      "exchange": "hyperliquid",
      "symbol": "BTC",
      "interval": "1h",
      "limit": 1000,
      "fallback_to_synthetic": true
    },
    "market_kind": "perp",
    "starting_capital": 100000,
    "strategy": {
      "name": "ema_crossover",
      "fast_period": 20,
      "slow_period": 50,
      "lookback": 20,
      "entry_z": 1.5,
      "exit_z": 0.25,
      "breakout_period": 30
    },
    "execution": {
      "order_type": "market",
      "allocation": 0.25,
      "leverage": 3,
      "taker_fee_bps": 5,
      "maker_fee_bps": 2,
      "base_slippage_bps": 3,
      "limit_offset_bps": 2,
      "maintenance_margin_rate": 0.005,
      "stop_loss_pct": 0.04,
      "take_profit_pct": 0.08
    },
    "scenario": {
      "name": "flash_crash",
      "start_percent": 0.6,
      "duration_bars": 24,
      "shock_pct": -0.12,
      "volatility_multiplier": 3,
      "slippage_multiplier": 4,
      "funding_rate_hourly": 0.00001
    }
  }'
```

## Current modeling limitations

This MVP is candle-based. It models fees, slippage, touch-based limit fills, funding, and liquidation, but does not yet reconstruct queue position, tick-level order books, latency distributions, cross-exchange clock skew, or portfolio-wide cross margin. Those belong in the next milestone.

## Next milestones

1. WebSocket recorder for Hyperliquid L2 books, trades, mids, and funding
2. Parquet dataset catalog and deterministic event replay
3. Strategy SDK with `on_book`, `on_trade`, `on_funding`, and `on_timer`
4. Multi-asset portfolio and cross-exchange arbitrage engine
5. Parameter sweeps, walk-forward validation, and Monte Carlo resampling
6. Market-making inventory and queue-position simulator
7. Experiment persistence in PostgreSQL and worker queue
8. Optional testnet execution adapter behind an explicit safety gate
