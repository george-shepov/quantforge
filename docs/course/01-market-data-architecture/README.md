# Module 1 — Market-Data Architecture and Exchange Adapters

## Module outcome

At the end of this module, the student has a running QuantForge development stack and can explain the complete path of a market-data request:

```text
React form
  → POST /api/backtests/run
  → validated BacktestRequest
  → exchange adapter selection
  → normalized candles or controlled failure
  → strategy engine
  → typed BacktestResponse
  → terminal visualization
```

The student also understands why environment metadata and execution status are part of the public product contract rather than deployment trivia.

## What students build

- a local Docker deployment with PostgreSQL, Redis, FastAPI, the RQ worker, and the React terminal;
- an architecture map of the running services and persisted volumes;
- a working request against `/api/catalog` and `/api/backtests/run`;
- a failure matrix for network-disabled, upstream-error, invalid-symbol, and synthetic-fallback scenarios;
- a new exchange-adapter test double that proves the API depends on the adapter contract rather than one exchange implementation;
- a visible environment badge and simulation-only safety assertion.

## Lesson sequence

### Lesson 1.1 — The platform we are building

**Duration:** 12–15 minutes

- Why a research platform is different from a trading bot.
- Simulation-first as an architectural constraint.
- The final system and course progression.
- What QuantForge intentionally refuses to do.

**Checkpoint:** the student can state the safety boundary and identify each service in `docker-compose.yml`.

### Lesson 1.2 — Run QuantForge with Docker

**Duration:** 18–22 minutes

- Copy `.env.example` to `.env`.
- Set a local PostgreSQL password.
- Build the API and terminal images.
- Start the stack.
- Read health checks rather than relying on “container is running.”
- Open the terminal, API docs, health endpoint, and research capabilities.

**Checkpoint:** all services are healthy and the API returns `mainnetOrderSubmission: false`.

### Lesson 1.3 — Trace one request end to end

**Duration:** 20–25 minutes

- Submit a candle backtest from the React terminal.
- Inspect the request payload.
- Follow the FastAPI route.
- Resolve the adapter.
- Normalize candle data.
- Run the engine.
- Return a typed response.

**Checkpoint:** the student can annotate each boundary with its input, output, and likely failure.

### Lesson 1.4 — Design the exchange adapter contract

**Duration:** 20–25 minutes

- Why exchange code must not leak into strategies.
- The smallest useful adapter interface.
- Normalized symbols, intervals, timestamps, and numeric precision.
- Adapter-specific errors versus API errors.
- Why capability metadata eventually belongs beside the adapter contract.

**Checkpoint:** a fake adapter passes the same contract tests as a network adapter.

### Lesson 1.5 — Failure is part of the data model

**Duration:** 20–25 minutes

- Network access disabled.
- Upstream timeout or malformed response.
- Unsupported interval or market kind.
- Deterministic synthetic fallback.
- Warning provenance in backtest results.
- Why silent fallback creates fraudulent confidence.

**Checkpoint:** the response clearly identifies live data, synthetic data, or synthetic fallback.

### Lesson 1.6 — Environment and execution safety metadata

**Duration:** 15–20 minutes

- Mainnet market data is not mainnet execution.
- Public data versus authenticated actions.
- Environment badges from `/api/catalog`.
- Why the frontend must not infer safety from button visibility.
- Safety assertions suitable for automated smoke tests.

**Checkpoint:** every exchange displays an explicit environment and `executionAllowed: false`.

### Lesson 1.7 — Module lab and architecture review

**Duration:** 30–45 minutes

- Complete the architecture worksheet.
- Run the failure matrix.
- Add an adapter test double.
- Explain one design trade-off in a short architecture decision record.

**Checkpoint:** tests pass and the student can reproduce the system from a clean checkout.

## Guided explanation: the adapter boundary

The first QuantForge adapter contract is intentionally small:

```python
class ExchangeAdapter(ABC):
    name: str

    @abstractmethod
    async def fetch_candles(self, request: MarketDataRequest) -> list[Candle]:
        raise NotImplementedError
```

That small boundary is useful because the backtest route does not need to know whether candles came from Hyperliquid, Bybit, BitMEX, WhiteBIT, or a deterministic synthetic generator.

It is not the final universal market-data abstraction. L2 snapshots, trades, funding updates, reconnect semantics, and sequence gaps require an event-stream contract with different guarantees. Module 2 makes that distinction explicit rather than stretching `fetch_candles` until it means everything.

## Expert note: what not to generalize yet

Do not begin by creating one giant `ExchangeAdapter` with methods for every REST endpoint, WebSocket channel, private account operation, and order type. That interface becomes a list of optional methods with exchange-specific exceptions.

Use narrow capability contracts instead:

- candle source;
- event stream source;
- instrument catalog;
- public market metadata;
- testnet execution adapter.

A component should receive only the capability it needs.

## Hands-on lab

### Part A — Start and inspect the stack

```bash
cp .env.example .env
# Set POSTGRES_PASSWORD in .env
docker compose up --build
```

In another terminal:

```bash
curl -s http://localhost:8008/api/health | python -m json.tool
curl -s http://localhost:8008/api/catalog | python -m json.tool
curl -s http://localhost:8008/api/research/capabilities | python -m json.tool
```

Record:

- API version;
- whether metering is enabled;
- each exchange environment;
- each execution badge;
- the mainnet submission flag;
- the available candle and event strategies.

### Part B — Run a deterministic baseline

Use the synthetic exchange first. A baseline should not depend on an exchange being reachable or changing its historical API behavior.

```bash
curl -s -X POST http://localhost:8008/api/backtests/run \
  -H 'Content-Type: application/json' \
  -d @docs/course/01-market-data-architecture/requests/synthetic-ema.json \
  | python -m json.tool
```

Run the same request twice and compare the result. Any difference must be explainable by an explicit seed or timestamp field.

### Part C — Run the failure matrix

| Scenario | Expected behavior |
|---|---|
| Synthetic source | Successful deterministic result |
| Public exchange reachable | Successful result with exchange source |
| Public exchange unavailable, fallback enabled | Successful synthetic result plus warning |
| Public exchange unavailable, fallback disabled | HTTP 502 with adapter error |
| Network disabled, fallback enabled | Synthetic fallback with clear provenance |
| Network disabled, fallback disabled | HTTP 503 |
| Invalid request | HTTP 422 validation response |

The lab is not complete if a fallback result looks indistinguishable from live exchange data.

### Part D — Add a contract test double

Create an adapter used only in tests:

```python
class FixedCandleAdapter(ExchangeAdapter):
    name = "fixed-test"

    async def fetch_candles(self, request: MarketDataRequest) -> list[Candle]:
        return [
            Candle(
                timestamp=1_700_000_000_000,
                open=100,
                high=103,
                low=99,
                close=102,
                volume=10,
            )
        ]
```

Use it to verify:

- the API route accepts any implementation of the contract;
- adapter errors become controlled HTTP responses;
- warnings and source provenance survive into the response;
- strategy code never imports a concrete exchange adapter.

### Part E — Write an architecture decision record

Create `docs/adr/0001-narrow-market-data-capabilities.md` with:

- **Context:** exchanges expose incompatible public and private APIs;
- **Decision:** use narrow capability interfaces rather than one universal adapter;
- **Consequences:** more small interfaces, easier tests, less exchange leakage;
- **Rejected alternative:** a single adapter containing candle, event, account, and execution methods.

## Architecture worksheet

For every boundary, fill in the contract and failure behavior:

| Boundary | Input | Output | Failure behavior | Deterministic? |
|---|---|---|---|---|
| React → FastAPI | JSON request | HTTP response | validation/network error | request-dependent |
| FastAPI → adapter | `MarketDataRequest` | `list[Candle]` | `ExchangeAdapterError` | source-dependent |
| Adapter → exchange | exchange request | exchange payload | timeout/schema/rate limit | no |
| Adapter → engine | normalized candles | engine input | validation error | yes after normalization |
| Engine → API | typed result | response model | controlled calculation error | yes with fixed inputs |

## Module assessment

1. Why is a deterministic synthetic source valuable even when live exchange adapters exist?
2. What information must be normalized before a strategy consumes candles?
3. Why should an upstream exchange failure not be represented as an empty candle list?
4. What is the danger of silently falling back to synthetic data?
5. Why is mainnet public market data compatible with a simulation-only product?
6. Which capabilities should not be added to the candle adapter?
7. What evidence proves that execution is disabled?

## Definition of done

- [ ] Docker stack starts from a clean checkout.
- [ ] API and frontend health checks pass.
- [ ] `/api/catalog` exposes explicit environment and execution badges.
- [ ] A synthetic baseline is reproducible.
- [ ] Live/fallback provenance is visible.
- [ ] The failure matrix is covered by tests.
- [ ] Strategy code is independent of concrete exchange adapters.
- [ ] The architecture decision record is complete.
