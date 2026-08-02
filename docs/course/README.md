# Build a Crypto Trading Research Platform

**Python · FastAPI · React · Docker · PostgreSQL · Redis · Parquet**

This is a build-along course based on the real QuantForge platform. Students do not build a toy moving-average notebook and throw it away. They progressively assemble a simulation-first research system that records market microstructure, replays it deterministically, models realistic execution, runs queued experiments, validates strategies out of sample, and deploys behind explicit safety gates.

> QuantForge is research software, not financial advice. The course never enables mainnet order submission.

## Course promise

By the end of the course, a student can:

- design a market-data architecture that supports both candles and event streams;
- normalize exchange-specific payloads into canonical, checksummed events;
- record L2 books, trades, mids, and funding into partitioned Parquet datasets;
- replay a dataset in stable deterministic order;
- simulate queue position, trade-through, fees, funding, leverage, liquidation, partial fills, stops, and targets;
- backtest spot, perpetual, and dated-futures strategies;
- queue Cartesian parameter sweeps in Redis and persist experiment state in PostgreSQL;
- perform walk-forward validation without quietly leaking future information;
- run seeded block-bootstrap Monte Carlo analysis;
- expose the platform through FastAPI and a React research terminal;
- deploy the complete stack with Docker while keeping execution disabled by default;
- meter API usage without exposing exchange credentials to clients.

## Who this is for

The primary audience is a software developer who understands Python or TypeScript but is new to systematic trading and market microstructure.

The course deliberately supports two reading modes:

- **Guided mode:** explains what a component does, why it exists, what assumption it encodes, how to validate it, and how it can fail.
- **Expert mode:** shows contracts, formulas, edge cases, data structures, performance trade-offs, and extension points without repeating introductory material.

## Prerequisites

Students should be comfortable with:

- basic Python and asynchronous programming;
- HTTP APIs and JSON;
- React components and TypeScript fundamentals;
- Docker commands;
- basic statistics such as mean, variance, percentiles, and sampling.

No prior trading experience is required. Every trading-specific term must be introduced before it is used as an assumption in code.

## The final architecture

```text
Exchange REST/WebSocket APIs
          │
          ▼
Exchange adapters and normalizers
          │
          ├──────────────► Candle backtester
          │
          ▼
Canonical checksummed events
          │
          ▼
Parquet dataset catalog ──► Deterministic replay engine
                                  │
                                  ▼
                         Strategy + portfolio + fills
                                  │
                 ┌────────────────┴───────────────┐
                 ▼                                ▼
        Experiment queue                    Execution stories
        Redis + RQ worker                   Guided + expert views
                 │
                 ▼
        PostgreSQL run history
                 │
                 ▼
       FastAPI research API
                 │
                 ▼
          React terminal
                 │
                 ▼
        Docker deployment
```

## Module map

### 1. Market-data architecture and exchange adapters

**Question:** How do we prevent every exchange integration from infecting the rest of the system with its own symbols, intervals, timestamps, and payload shapes?

**Build:**

- run the complete Docker development stack;
- trace a candle request from React to FastAPI to an exchange adapter;
- define the adapter boundary and failure contract;
- compare live exchange data with deterministic synthetic fallback;
- expose environment and execution-disabled metadata through the catalog API.

**QuantForge anchors:**

- `backend/app/exchanges/base.py`
- `backend/app/exchanges/`
- `backend/app/main.py`
- `backend/app/models.py`
- `docker-compose.yml`

### 2. Candles versus event-driven data

**Question:** What information disappears when thousands of order-book and trade events are compressed into one OHLCV candle?

**Build:**

- model candle bars and market events as different research inputs;
- identify strategies that candles can and cannot test honestly;
- create a shared strategy-result vocabulary without pretending both engines are identical.

**QuantForge anchors:**

- `backend/app/engine/backtester.py`
- `backend/app/research/events.py`
- `backend/app/research/engine.py`

### 3. Canonical events, checksums, and deterministic replay

**Question:** Can two researchers replay the same dataset and obtain the same event order and result?

**Build:**

- normalize exchange messages into versioned canonical events;
- preserve exchange time, receive time, and monotonic local sequence;
- hash canonical JSON with SHA-256;
- write Zstandard-compressed Parquet partitions;
- maintain an append-only manifest checksum chain;
- replay using `(event_time, receive_time, sequence, checksum)` ordering.

**QuantForge anchors:**

- `backend/app/research/events.py`
- `backend/app/research/api.py`

### 4. L2 order books and realistic partial fills

**Question:** Why is touching the best bid or ask not the same as getting filled there?

**Build:**

- reconstruct L2 book state;
- distinguish maker and taker execution;
- model queue-ahead volume and trade-through;
- support partial fills and remaining quantity;
- seed stochastic decisions so simulations remain reproducible;
- test crossed books, missing levels, insufficient depth, cancellation, and adverse selection.

**QuantForge anchors:**

- `backend/app/research/engine.py`
- `backend/tests/`

### 5. Backtesting spot and perpetual strategies

**Question:** Which accounting assumptions change when a strategy uses leverage and funding?

**Build:**

- execute EMA crossover, mean reversion, and breakout strategies;
- compare spot, perpetual, and dated-future accounting;
- model fees, slippage, funding, leverage, liquidation, stops, and targets;
- separate realized P&L, unrealized P&L, cash, margin, and equity;
- add explicit warnings when data or assumptions are incomplete.

**QuantForge anchors:**

- `backend/app/engine/`
- `backend/app/models.py`
- `backend/app/exchanges/`

### 6. Parameter sweeps and experiment queues

**Question:** How do we run many experiments without turning an API request into an hour-long blocking process?

**Build:**

- generate Cartesian parameter combinations;
- create durable experiment and run records;
- enqueue work through Redis/RQ;
- process jobs in a separate worker container;
- expose queue progress, failures, metrics, and persisted history;
- make every run reproducible from dataset, strategy, parameters, code version, and seed.

**QuantForge anchors:**

- `backend/app/research/experiments.py`
- `backend/app/research/persistence.py`
- `backend/app/research/worker.py`
- `docker-compose.yml`

### 7. Walk-forward validation

**Question:** Does the strategy still work when parameters are chosen only from data available before the test window?

**Build:**

- define train, validation, and test windows;
- roll windows forward through time;
- select parameters inside each training window;
- evaluate on the next unseen window;
- aggregate fold results without hiding unstable periods;
- visualize parameter drift and fold-to-fold degradation.

### 8. Monte Carlo risk analysis

**Question:** Is the observed backtest path unusually lucky?

**Build:**

- resample return or trade blocks rather than shuffling individual points blindly;
- preserve short-range dependence with block bootstrap;
- seed every run;
- compute distributions for final equity, maximum drawdown, Sharpe-like ratios, and loss probability;
- explain why Monte Carlo explores path risk but does not repair bad source data or biased strategy selection.

### 9. Testnet safety gates and secret management

**Question:** How can a research platform prove that a UI click cannot silently become a mainnet order?

**Build:**

- keep mainnet submission absent rather than merely hidden;
- require an explicit testnet environment;
- default to dry-run;
- require a server-side feature gate, safety token, acknowledgement phrase, credential presence, maker-only new exposure, and a notional cap;
- load runtime secrets from the server-side vault;
- display environment and execution status in every relevant UI surface;
- test every denial path before testing successful submission.

**QuantForge anchors:**

- `backend/app/research/execution.py`
- `backend/app/exchanges/environment.py`
- `backend/app/main.py`
- `.env.example`
- deployment workflow and vault adapter

### 10. Deploying the complete QuantForge platform

**Question:** How do the API, worker, database, queue, datasets, frontend, metering, secrets, health checks, and reverse proxy operate as one product?

**Build:**

- package FastAPI and React independently;
- run PostgreSQL, Redis, API, worker, and terminal services;
- persist database, queue, and Parquet volumes;
- use health-based startup dependencies;
- expose only the terminal through the shared edge network;
- proxy `/api`, `/docs`, and `/openapi.json` through the same origin;
- configure metered developer API keys and usage reporting;
- execute a production smoke-test checklist.

**QuantForge anchors:**

- `docker-compose.yml`
- `backend/Dockerfile`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `.github/workflows/`
- `backend/app/metering.py`

## Build-along rhythm

Every module follows the same structure:

1. **The problem:** a concrete failure of the naive implementation.
2. **The mental model:** the minimum trading and systems concepts needed.
3. **The contract:** types, invariants, API shape, and failure semantics.
4. **The implementation:** one vertical slice in QuantForge.
5. **The adversarial test:** a scenario designed to expose a false assumption.
6. **The research story:** assumptions, hopes, observed results, delta, and validation steps.
7. **The checkpoint:** a visible UI or API result students can verify.
8. **The extension:** an optional expert task.

## Definition of done for a lesson

A lesson is not complete because code compiles. It is complete when:

- the behavior has a deterministic automated test;
- failure behavior is visible and understandable;
- the API contract is documented;
- the UI explains the important assumption without blocking expert use;
- the student can reproduce the result from a clean checkout;
- no secret or mainnet execution capability is required;
- the lesson produces a reusable artifact for later modules.

## Capstone demonstration

The final demonstration should perform this complete story:

1. Start PostgreSQL, Redis, FastAPI, worker, and React with Docker.
2. Confirm the environment badges and `mainnetOrderSubmission: false`.
3. Record public BTC and ETH events from Hyperliquid.
4. Inspect the dataset manifest and checksum chain.
5. Replay the dataset with the inventory market-making strategy.
6. Explain queue assumptions and partial fills through the execution story.
7. Queue a parameter sweep with walk-forward folds and Monte Carlo runs.
8. Inspect persisted run history and compare candidate parameters.
9. Perform a dry-run testnet order and demonstrate at least three rejected unsafe requests.
10. Create a metered developer key and inspect usage accounting.
11. Redeploy and repeat the smoke test against the hosted environment.

## Commercial packaging

The same source material can become several products:

- **Udemy / similar marketplace:** practical video course with downloadable checkpoints.
- **Pluralsight / LinkedIn Learning pitch:** narrower professional course emphasizing architecture, deterministic systems, and testing.
- **KDP book:** expanded explanations, diagrams, code excerpts, exercises, and troubleshooting chapters.
- **Paid QuantForge lab:** hosted datasets, larger experiment quotas, saved run history, and metered API access.
- **Team workshop:** a one- or two-day architecture and backtesting workshop using a private QuantForge deployment.

The open-source repository is the proof of competence. The paid value is structure, explanation, curated datasets, guided labs, assessments, hosted compute, and ongoing updates—not hiding the source code.

## Course status

- [x] Working simulation-first platform
- [x] Candle and event-driven engines
- [x] Exchange adapters
- [x] Deterministic event datasets
- [x] L2 partial-fill simulation
- [x] Experiment queue
- [x] Walk-forward and Monte Carlo capabilities
- [x] Testnet safety boundary
- [x] Full research UI
- [x] Docker deployment
- [x] Metered API foundation
- [ ] Complete lesson manuscripts
- [ ] Architecture diagrams and animations
- [ ] Curated downloadable datasets
- [ ] Quizzes and coding exercises
- [ ] Instructor scripts
- [ ] Video recording and editing
- [ ] KDP manuscript build
