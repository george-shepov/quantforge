# Lesson 1.1 — The Platform We Are Building

**Target runtime:** 12–15 minutes  
**Format:** instructor narration + architecture walkthrough + live API check  
**Student artifact:** completed platform boundary worksheet

## Learning objectives

By the end of this lesson, the student can:

1. distinguish a trading research platform from a trading bot;
2. explain why QuantForge is simulation-first;
3. identify the major services in the final architecture;
4. state what the platform intentionally refuses to do;
5. describe the evidence required before a backtest result deserves trust.

## Opening hook

A moving-average crossover can be written in a notebook in a few minutes. That is not the hard part.

The hard part is answering the questions the notebook quietly avoids:

- Where did the data come from?
- Was it normalized correctly?
- Did we accidentally use information from the future?
- Would the order really have filled?
- How much size was available?
- What happened to the unfilled quantity?
- Were fees, funding, leverage, and liquidation included?
- Can we replay the exact same market events tomorrow?
- Did we choose parameters on the same period used to judge them?
- Is the final equity curve one lucky ordering of returns?
- Can the research interface ever submit a real mainnet order?

QuantForge exists to make those questions visible, testable, and reproducible.

## Instructor narration

### 1. A research platform is not a signal generator

A signal generator answers a narrow question such as:

> Is the fast moving average above the slow moving average?

A research platform must answer a larger chain of questions:

1. What market observation produced the signal?
2. What information was available at that moment?
3. What order did the strategy intend to place?
4. What execution assumptions converted that intention into a fill?
5. How did the fill alter cash, position, fees, funding, and risk?
6. Can we reproduce every step from saved inputs?
7. Can another researcher challenge the assumptions?

A strategy can be simple while the surrounding research system remains rigorous.

### 2. Simulation-first is an architectural constraint

QuantForge is not a mainnet trading bot with the submit button hidden.

The research API does not implement mainnet order submission. The optional execution adapter is limited to Hyperliquid testnet and remains dry-run unless several independent server-side gates are satisfied.

That distinction matters:

- **Hidden capability** can be exposed accidentally.
- **Absent capability** cannot be triggered by a frontend bug.

We will still use public mainnet market data because public observation is different from authenticated execution. The platform can study real markets while refusing to place real orders.

### 3. The final system

Walk through the architecture from left to right.

```text
Public exchange APIs
    │
    ├── REST candles
    └── WebSocket market events
             │
             ▼
Adapters and normalizers
             │
      ┌──────┴─────────┐
      ▼                ▼
Candle engine    Canonical event stream
                       │
                       ▼
              Parquet dataset catalog
                       │
                       ▼
              Deterministic replay
                       │
                       ▼
          Strategy, portfolio, and fills
                       │
                       ▼
         Experiments and persisted runs
                       │
                       ▼
              FastAPI research API
                       │
                       ▼
                React terminal
```

Then add the runtime services:

- PostgreSQL stores experiment and run records.
- Redis stores queued work.
- The RQ worker executes long-running experiments outside API requests.
- Docker Compose connects the services and persists their volumes.
- The shared reverse proxy exposes the terminal while the API remains behind the same origin.

### 4. Two research engines, not one fake abstraction

QuantForge supports both candle backtests and event-driven replay.

They solve different problems.

A candle can tell us:

- open, high, low, close, and volume for an interval;
- enough to research many directional strategies;
- not the sequence of trades inside the candle;
- not queue position;
- not which side changed the book first;
- not whether enough depth existed at the assumed price.

An event dataset preserves more of the market path, but it is larger, more complicated, and easier to corrupt with ordering mistakes.

The course does not pretend event-driven simulation is always necessary. It teaches when candles are adequate and when they become misleading.

### 5. The trust chain

A backtest result deserves increasing confidence only as we establish a chain of evidence:

```text
Source provenance
  → normalized schema
  → integrity checks
  → deterministic replay
  → explicit execution assumptions
  → accounting invariants
  → out-of-sample validation
  → path-risk analysis
  → reproducible deployment
```

A polished equity curve at the end cannot compensate for a broken link near the beginning.

### 6. What QuantForge intentionally refuses to promise

QuantForge does not promise:

- that a profitable backtest will remain profitable;
- that historical liquidity will be available in the future;
- that a simulated queue model perfectly reproduces an exchange matching engine;
- that Monte Carlo analysis predicts every future regime;
- that testnet behavior is identical to mainnet behavior;
- that more parameter combinations produce more truth;
- that a strategy is safe because it has a high Sharpe ratio;
- that software can eliminate market risk.

The product promise is narrower and more defensible:

> QuantForge makes assumptions explicit, preserves research inputs, supports deterministic replay, and gives developers tools to test where a strategy story can break.

## Live demonstration

### Step 1 — Show the safety boundary

Open the repository `README.md` and identify:

- simulation-first language;
- testnet-only execution;
- the required execution gates;
- the absence of a mainnet URL or generic signed-action endpoint.

### Step 2 — Show the runtime composition

Open `docker-compose.yml` and identify:

- `postgres`;
- `redis`;
- `api`;
- `worker`;
- `terminal`;
- persisted volumes;
- health checks;
- the external edge network.

Ask students which services are stateful and what would be lost if each volume disappeared.

### Step 3 — Query the product contract

With the stack running:

```bash
curl -s http://localhost:8008/api/health | python -m json.tool
curl -s http://localhost:8008/api/catalog | python -m json.tool
```

Point out:

- API version;
- metering status;
- exchange environments;
- execution-disabled badges;
- `mainnetOrderSubmission: false`;
- available strategies and scenarios.

Explain that safety state must be returned by the server and displayed by the client. The browser should not invent it.

## Guided-mode explanation

Imagine QuantForge as a laboratory.

- Exchange adapters are measuring instruments.
- Canonical events are the lab's standard units.
- Checksums are tamper-evident seals.
- Parquet datasets are preserved samples.
- Replay is the repeatable experiment.
- The fill model is an explicit physical assumption.
- The experiment queue is the lab scheduler.
- Walk-forward validation is the rule that prevents looking at tomorrow's answer.
- Monte Carlo analysis asks how much the outcome depends on the path we happened to observe.
- Safety gates separate the laboratory from a production control room.

The laboratory can still be wrong. Its job is to make wrong assumptions discoverable.

## Expert-mode note

The most important early design decision is not the framework. FastAPI, React, PostgreSQL, Redis, Parquet, and Docker are replaceable.

The durable decisions are the invariants:

- normalized inputs do not retain ambiguous exchange semantics;
- source provenance is never discarded;
- event ordering is total and stable;
- stochastic simulation is seeded;
- experiment identity includes all inputs needed for reproduction;
- unsafe execution paths fail closed;
- long-running work does not block API processes;
- research results remain inspectable after the worker exits.

Framework choices should serve those invariants.

## Student exercise — platform boundary worksheet

Complete the table before moving to Lesson 1.2.

| Component | Responsibility | Must not do | Persisted state | Primary failure |
|---|---|---|---|---|
| Exchange adapter |  |  |  |  |
| Canonical event normalizer |  |  |  |  |
| Dataset catalog |  |  |  |  |
| Replay engine |  |  |  |  |
| Fill simulator |  |  |  |  |
| Experiment worker |  |  |  |  |
| FastAPI service |  |  |  |  |
| React terminal |  |  |  |  |
| PostgreSQL |  |  |  |  |
| Redis |  |  |  |  |

## Knowledge check

1. Why is a research platform more than a collection of strategy indicators?
2. Why is absent mainnet execution safer than a hidden mainnet switch?
3. Can a simulation-first platform consume public mainnet market data? Explain.
4. Name two questions candles cannot answer about execution.
5. What is the purpose of deterministic replay?
6. Why must a stochastic fill model use an explicit seed?
7. Which parts of the final architecture preserve state?
8. What is the narrow promise QuantForge can honestly make?

## Answers

1. It must preserve inputs, model execution and accounting, expose assumptions, support validation, and reproduce results.
2. A hidden capability can be exposed by configuration or UI failure; an absent capability has no callable path.
3. Yes. Reading public market data does not authorize or submit trades.
4. Examples: queue position, intrabar event sequence, available depth, maker-versus-taker path, and partial-fill timing.
5. To reproduce the same ordered inputs and investigate why a result occurred.
6. Without a seed, repeated runs can differ for reasons unrelated to strategy or parameter changes.
7. PostgreSQL, Redis append-only data, and Parquet dataset volumes; the browser and API process should not be the source of durable experiment truth.
8. It makes assumptions explicit, preserves research inputs, and supports reproducible testing of the strategy story.

## Recording notes

- Start with the finished terminal visible for 10–15 seconds.
- Do not lead with installation commands; establish the problem first.
- Keep the architecture diagram on screen while describing the trust chain.
- Zoom into the safety fields in `/api/catalog`.
- Use one visual distinction throughout the course:
  - observation/data;
  - simulation/research;
  - authenticated execution.
- End by previewing Lesson 1.2: starting the exact services shown in the diagram.

## Lesson completion criteria

- [ ] Student can distinguish research from execution.
- [ ] Student can name all runtime services.
- [ ] Student can explain why candle and event engines remain separate.
- [ ] Student can state the safety boundary.
- [ ] Student completed the platform boundary worksheet.
