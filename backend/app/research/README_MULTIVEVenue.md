# Multi-exchange milestone

Implemented on this branch:

- Bybit public candle and L2 REST adapters with testnet/demo/mainnet-readonly endpoint configuration.
- WhiteBIT public candle and L2 REST adapters, including demo-token symbol mapping (`DBTC_DUSDT`).
- Hyperliquid and BitMEX testnet-aware REST/WebSocket endpoint configuration.
- Explicit environment metadata and UI-ready safety badges through `/api/catalog`.
- Deterministic L2 snapshot replay.
- Multi-level market/limit execution simulation with partial-fill results.
- Hard block on all order submission in this release.

Next validation steps:

1. Run the complete backend tests three consecutive times.
2. Smoke-test Bybit testnet, Hyperliquid testnet, BitMEX testnet, and WhiteBIT public/demo endpoints from an allowed network.
3. Add incremental WebSocket book-delta ingestion and persistence to the existing Parquet recorder.
4. Add the read-only cross-exchange arbitrage opportunity endpoint and execution trace UI.
