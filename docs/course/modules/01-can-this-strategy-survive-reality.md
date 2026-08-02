# Module 1 — Can This Strategy Survive Reality?

**Course:** Crypto Algorithmic Trading Research with Python  
**Subtitle:** Backtesting, Order Books, Walk-Forward Analysis, and Monte Carlo with QuantForge  
**Target runtime:** 82 minutes  
**Format:** instructor-led demonstration + executable lab + workbook  
**Level:** software developers and technically curious traders new to rigorous strategy research

## Module promise

A promising backtest is not a trading conclusion.

By the end of this module, the learner will take one simple trading idea through six increasingly demanding questions:

1. Does it produce an attractive baseline backtest?
2. Does it survive fees and slippage?
3. Does its execution assumption survive an L2 order book?
4. Does performance persist across time windows?
5. How wide is the range of plausible outcomes under resampling?
6. What verdict is justified by the evidence—and what remains unknown?

The learner will finish with a compact, reproducible research report rather than a screenshot of a profitable equity curve.

## Learning objectives

After completing the module, the learner can:

- write a falsifiable trading hypothesis;
- distinguish a strategy hypothesis from an execution hypothesis;
- run and compare deterministic QuantForge backtests;
- explain why market and limit orders encode different assumptions;
- calculate a volume-weighted fill from an L2 book;
- identify partial fills and unfilled quantity;
- read fold-to-fold instability without averaging it away;
- interpret Monte Carlo percentiles and loss probability;
- classify expected-versus-actual deltas;
- produce a cautious research verdict that does not imply future profitability.

## Required QuantForge capabilities

The module uses capabilities already present in QuantForge:

- `POST /api/backtests/run`
- `POST /api/research/execution/story`
- `POST /api/research/replay`
- `POST /api/research/experiments`
- persisted experiment history
- guided and expert execution-story modes

The module also requires one bundled deterministic event fixture, `course-btc-l2-v1`, so every learner can reproduce the walk-forward and Monte Carlo sections without waiting for a live recording.

## The investigation

### Research question

> Can a simple trend-following idea remain credible after realistic trading costs, order-book constraints, time-window testing, and path uncertainty are introduced?

### Baseline hypothesis

> A fast EMA crossing above or below a slow EMA identifies persistent BTC price movement strongly enough to remain positive after ordinary execution costs.

### Supporting hypotheses

- Increasing fees and slippage should reduce returns and may change the strategy verdict.
- A market order larger than top-of-book depth should fill across multiple price levels.
- A limit order should reduce price impact but may leave quantity unfilled.
- A robust idea should not depend on one favorable time window.
- A robust idea should retain an acceptable outcome distribution when observed return blocks are resampled.

### Explicit assumptions

- The candle series is correctly ordered and has no look-ahead leakage.
- The strategy acts only on information available at each bar.
- Fee and slippage settings are plausible for the intended venue and order size.
- The deterministic L2 snapshot is a teaching fixture, not a claim about current BTC liquidity.
- The event fixture is representative enough to demonstrate the mechanics, but not sufficient to prove deployability.
- Monte Carlo resampling explores path uncertainty in the observed evidence; it does not repair biased data or a flawed strategy.

### Invalidation conditions

The learner must withhold or weaken the conclusion if:

- results change materially when one reasonable cost assumption changes;
- most returns come from one fold;
- the experiment has too few trades or fills;
- the strategy requires unavailable liquidity;
- the result depends on synthetic data but is described as live-market evidence;
- the loss probability or lower percentile conflicts with the learner’s risk constraint;
- the implementation cannot be reproduced from the stored scenario, dataset checksum, seed, and code version.

---

# Recording plan

## 0:00–4:30 — Cold open: the dangerous screenshot

### On screen

Open QuantForge to a clean baseline backtest with a rising equity curve and attractive headline metrics.

### Instructor narration

“Most algorithmic-trading mistakes begin with a chart that feels like an answer. The equity curve rises. The Sharpe ratio looks respectable. The strategy appears to make money. At that moment, the temptation is to stop researching and start believing.

In this module, we are going to do the opposite. We will treat the attractive backtest as the beginning of the investigation.

We are not asking whether this strategy made money in one simulation. We are asking whether the idea survives increasingly realistic objections: trading costs, order type, available liquidity, partial fills, changing time windows, and uncertainty in the order of returns.

We will finish with one of three honest outcomes: reject the idea, revise the idea, or justify more research. ‘Deploy it because the curve went up’ is not one of the available outcomes.”

### Teaching beat

Show the final research-report template briefly, then return to the baseline.

### Preview hook for public video

“The most important number in this lesson will not be total return. It will be the difference between what we expected the experiment to prove and what it actually proved.”

---

## 4:30–11:00 — The research contract

### On screen

Create a new guided laboratory entry with these fields:

- question;
- hypothesis;
- assumptions;
- invalidation conditions;
- expected outcome;
- evidence required.

### Instructor narration

“A strategy idea should be stated in a way that can lose.

‘EMA crossover is a good strategy’ is not falsifiable. It has no market, no timeframe, no cost assumptions, no measurement, and no threshold.

A better statement is: ‘On this dataset, a 20/50 EMA crossover on BTC perpetual candles will remain positive after five basis points of taker fees and three basis points of slippage, without exceeding our drawdown limit.’

That statement can fail. That is what makes it useful.

We also separate two hypotheses that beginners often mix together:

- The **strategy hypothesis** asks whether the signal contains useful information.
- The **execution hypothesis** asks whether orders based on that signal can be filled under plausible conditions.

A candle backtest may help with the first question. It cannot fully answer the second because a candle does not preserve the order-book depth, queue position, or sequence of trades that produced it.”

### Learner checkpoint

The learner rewrites a vague strategy belief into this template:

> On `[dataset]`, `[strategy and parameters]` will achieve `[measurable result]` after `[cost assumptions]`, while remaining within `[risk constraint]`.

### Workbook prompt

“What result would make you abandon or revise the idea?”

---

## 11:00–24:00 — Lab A: the baseline candle backtest

### Goal

Establish a reproducible baseline before adding objections.

### Request

```json
{
  "market": {
    "exchange": "synthetic",
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
    "leverage": 2,
    "taker_fee_bps": 5,
    "maker_fee_bps": 2,
    "base_slippage_bps": 3,
    "limit_offset_bps": 2,
    "maintenance_margin_rate": 0.005,
    "stop_loss_pct": 0.04,
    "take_profit_pct": 0.08
  },
  "scenario": {
    "name": "baseline",
    "start_percent": 0.6,
    "duration_bars": 24,
    "shock_pct": -0.12,
    "volatility_multiplier": 3,
    "slippage_multiplier": 4,
    "funding_rate_hourly": 0.00001
  }
}
```

### Instructor narration

“We start with deterministic synthetic data because the first objective is not market realism. The first objective is reproducibility. Every learner should be able to run the same scenario and obtain the same evidence.

Notice that the request stores much more than the strategy name. It records the market kind, allocation, leverage, fees, slippage, maintenance margin, stops, targets, and funding assumption. Without those values, the phrase ‘same backtest’ is meaningless.

Now inspect the output in layers.

First: data provenance. Was the source synthetic, recorded, or live public data? Are there warnings?

Second: sample size. How many trades occurred? A beautiful metric built from three trades is not strong evidence.

Third: return and drawdown together. Return without drawdown is marketing. Drawdown without exposure and trade count can also mislead.

Fourth: the cost totals. Fees and funding are not decoration. They are part of the strategy.

Fifth: individual trades. Look for one trade carrying the entire result, repeated stop-outs, liquidation events, or suspiciously perfect fills.”

### Generated evidence table

The rendered lesson inserts actual values from the run:

| Measurement | Expected | Actual | Delta | Classification |
|---|---:|---:|---:|---|
| Trade count | Generated threshold | `{metrics.trade_count}` | Generated | Generated |
| Total return | Positive baseline | `{metrics.total_return_pct}` | Generated | Generated |
| Max drawdown | Below research limit | `{metrics.max_drawdown_pct}` | Generated | Generated |
| Fees | Greater than zero | `{metrics.total_fees}` | Generated | Generated |
| Funding | Consistent with position exposure | `{metrics.total_funding}` | Generated | Generated |

### Key teaching point

Do not call the baseline “profitable” without saying **under which dataset and assumptions**.

### Learner checkpoint

The learner writes a one-sentence baseline verdict:

> Under the baseline synthetic scenario and stated execution assumptions, the strategy `[supports / does not support]` continued investigation because `[evidence]`; this does not yet test `[largest missing realism]`.

---

## 24:00–37:00 — Lab B: change one execution assumption

### Goal

Demonstrate that execution settings are part of the strategy result.

### Experiment 1 — Higher friction

Duplicate the baseline and change only:

```json
{
  "taker_fee_bps": 10,
  "base_slippage_bps": 8
}
```

### Expected directional behavior

- total fees should increase;
- entry and exit prices should become less favorable;
- net return and expectancy should not improve merely because costs increased;
- marginal trades may change from gains to losses;
- the research verdict may change even though the signal is unchanged.

### Experiment 2 — Market versus limit

Duplicate the baseline and change only:

```json
{
  "order_type": "limit",
  "maker_fee_bps": 2,
  "limit_offset_bps": 2
}
```

### Instructor narration

“A market order says: execution now matters more than exact price. A limit order says: price matters enough that we accept the risk of not trading.

Those are not cosmetic choices. They create different missing-data problems.

A candle backtest can model a limit rule, but it cannot know your queue position from OHLCV alone. If the candle touches the limit price, that does not prove your order would have filled. Other orders may have been ahead of you. The market may have traded one tiny quantity at that price. The touch may have occurred before your signal was available.

So this comparison is useful, but its conclusion must be narrow: it tells us how the candle engine behaves under two execution models. It does not prove exchange-quality limit-order fills.”

### Delta table

| Metric | Baseline market | Higher friction | Limit model | Interpretation |
|---|---:|---:|---:|---|
| Total return | Generated | Generated | Generated | Did the verdict survive? |
| Fees | Generated | Generated | Generated | Are costs material? |
| Trade count | Generated | Generated | Generated | Did fill behavior change? |
| Expectancy | Generated | Generated | Generated | Did the average trade retain an edge? |
| Max drawdown | Generated | Generated | Generated | Did risk improve or merely activity fall? |

### Classification rules

- **Matched:** direction and magnitude are within the scenario tolerance.
- **Explainable deviation:** the direction is expected but the size differs because trade count, stops, or position path changed.
- **Assumption failure:** the result depends on an execution rule the available data cannot validate.
- **Data-quality warning:** missing or fallback data prevents a strong conclusion.

### Learner checkpoint

The learner identifies one sentence in their original hypothesis that must now be revised.

---

## 37:00–51:00 — Lab C: what the order book does to one order

### Goal

Make price impact and partial fills visible with arithmetic the learner can verify by hand.

### Deterministic L2 snapshot

```json
{
  "snapshot": {
    "exchange": "course_fixture",
    "symbol": "BTC",
    "timestamp_ms": 1770000000000,
    "sequence": 1,
    "bids": [
      [100.0, 0.30],
      [99.5, 0.70],
      [99.0, 1.00]
    ],
    "asks": [
      [100.5, 0.25],
      [101.0, 0.50],
      [102.0, 1.25]
    ],
    "environment": "synthetic-course-fixture"
  },
  "side": "buy",
  "quantity": 1.0,
  "limit_price": null,
  "mode": "guided",
  "intent": "Buy one BTC immediately and measure book impact.",
  "hypothesis": "The order will fill near the best ask.",
  "assumptions": [
    "Displayed depth remains available while the order executes.",
    "No hidden liquidity or fees are included in this fixture."
  ],
  "invalidation_conditions": [
    "The snapshot is treated as current live BTC liquidity.",
    "Latency or queue behavior is inferred from this static book."
  ],
  "hopes": [
    "Most quantity fills close to the best ask."
  ],
  "risks": [
    "The requested quantity exceeds top-of-book depth."
  ]
}
```

### Hand calculation

The best ask contains only `0.25 BTC` at `100.5`.

The next level contains `0.50 BTC` at `101.0`.

The remaining `0.25 BTC` must trade at `102.0`.

```text
cost = 0.25 × 100.5 + 0.50 × 101.0 + 0.25 × 102.0
     = 25.125 + 50.500 + 25.500
     = 101.125

average fill price = 101.125 / 1.0 = 101.125
```

The order fills completely, but not at the best ask.

### Expected-versus-actual evidence

| Measurement | Expected | Actual from QuantForge | Delta |
|---|---:|---:|---:|
| Requested quantity | 1.00 | Generated | Generated |
| Filled quantity | 1.00 | Generated | Generated |
| Remaining quantity | 0.00 | Generated | Generated |
| Average price | 101.125 | Generated | Generated |
| Fill count | 3 | Generated | Generated |

A golden test should require exact agreement within floating-point tolerance.

### Limit-order variant

Set:

```json
{
  "limit_price": 101.0
}
```

Expected result:

```text
filled quantity = 0.25 + 0.50 = 0.75 BTC
remaining quantity = 0.25 BTC
average price = (0.25 × 100.5 + 0.50 × 101.0) / 0.75
              = 100.8333333333...
status = partial
```

### Instructor narration

“This is the point where ‘the price was 100.5’ stops being a sufficient execution model.

The market had a best ask of 100.5, but it did not offer one BTC at that price. The order consumed three levels and paid an average of 101.125.

Now we add a limit of 101. The average price improves, but only 0.75 BTC fills. The remaining 0.25 BTC is not a rounding error. It changes position size, risk, future P&L, and possibly the entire strategy path.

There is no universally superior order type. There is only a trade-off that must match the strategy’s urgency, edge, and tolerance for missed execution.”

### Guided/expert demonstration

Show the same evidence twice:

- **Guided mode:** assumptions, arithmetic, validation steps, risks, and reflection prompt.
- **Expert mode:** compact fill table, average price, remaining quantity, raw snapshot, and evidence links.

The numbers must be identical in both modes.

### Learner checkpoint

The learner explains why “the candle touched my limit” is not equivalent to “my order filled.”

---

## 51:00–65:00 — Lab D: does the result persist through time?

### Goal

Replace one full-period average with visible fold-by-fold evidence.

### Dataset

Use the bundled deterministic event fixture:

```text
course-btc-l2-v1
```

The generated report must include its dataset ID, event count, time range, symbols, event kinds, and checksum chain.

### Experiment request

```json
{
  "dataset_id": "course-btc-l2-v1",
  "strategy": "inventory_market_making",
  "starting_cash": 100000,
  "timer_interval_ms": 1000,
  "base_parameters": {
    "inventory_skew_bps": 3,
    "max_inventory": 5,
    "quantity": 0.01
  },
  "parameter_grid": {
    "spread_bps": [4, 8, 12]
  },
  "walk_forward_folds": 4,
  "monte_carlo_runs": 0,
  "monte_carlo_block_size": 2,
  "seed": 7
}
```

### Terminology boundary

The current QuantForge implementation evaluates parameter candidates across sequential test folds. It does not yet select parameters inside each training window and then lock them for the next unseen window.

In this module, call the feature:

> **walk-forward window evaluation**

Do not call it full walk-forward optimization until train-select-test behavior and leakage tests are implemented.

### Instructor narration

“One total return can hide a fragile time path.

Suppose three folds are flat or negative and one fold is strongly positive. The average may still look acceptable, but the strategy may depend on one market regime.

We inspect every fold:

- return;
- maximum drawdown;
- event count;
- fill count;
- parameter values.

The question is not ‘Which row is green?’ The question is ‘What pattern repeats, and what market behavior appears to break it?’

A stable but modest result may deserve more research than a spectacular average produced by one exceptional fold.”

### Generated fold table

| Candidate | Fold | Return | Max drawdown | Fills | Interpretation |
|---|---:|---:|---:|---:|---|
| spread 4 bps | 1 | Generated | Generated | Generated | Generated |
| spread 4 bps | 2 | Generated | Generated | Generated | Generated |
| spread 4 bps | 3 | Generated | Generated | Generated | Generated |
| spread 4 bps | 4 | Generated | Generated | Generated | Generated |
| spread 8 bps | 1–4 | Generated | Generated | Generated | Generated |
| spread 12 bps | 1–4 | Generated | Generated | Generated | Generated |

### Questions the learner must answer

- Does the best average candidate also have the most stable folds?
- Does a wider spread reduce fills enough to make the result unreliable?
- Is any fold responsible for most of the score?
- Are drawdowns concentrated in one regime?
- Would a different fold count materially change the conclusion?

### Learner checkpoint

The learner chooses one candidate for continued research and gives a stability-based reason—not merely the highest score.

---

## 65:00–75:00 — Lab E: Monte Carlo is a distribution, not a forecast

### Goal

Show how the same observed fold returns can produce many plausible paths.

### Experiment change

Rerun the selected candidate with:

```json
{
  "monte_carlo_runs": 1000,
  "monte_carlo_block_size": 2,
  "seed": 7
}
```

### Evidence

QuantForge returns:

- `p05`;
- `median`;
- `p95`;
- `loss_probability`.

### Instructor narration

“A backtest gives us one observed path. Monte Carlo asks what happens when blocks from that observed evidence are recombined many times.

We use blocks rather than blindly shuffling individual observations because adjacent results may share regime behavior. The block size is an assumption, not a truth.

The fifth percentile is not ‘the worst thing that can happen.’ It is the lower fifth percentile of this model, using this evidence, this block size, this number of runs, and this seed.

The median is not a forecast. The ninety-fifth percentile is not an upside promise. The loss probability is conditional on the model and source observations.

Monte Carlo is valuable because it weakens our attachment to the one path we happened to observe. It is dangerous when its precision makes weak assumptions look scientific.”

### Generated distribution table

| Statistic | Actual | Research meaning |
|---|---:|---|
| p05 | Generated | Lower-tail outcome under this resampling model |
| median | Generated | Middle simulated path, not a forecast |
| p95 | Generated | Upper-tail outcome under this resampling model |
| loss probability | Generated | Fraction of generated paths below zero |
| runs | 1000 | Simulation count |
| block size | 2 | Dependence-preservation assumption |
| seed | 7 | Reproducibility control |

### Sensitivity check

Change only the block size from `2` to `4`.

If the distribution changes materially, classify the conclusion as sensitive to the dependence assumption.

### Learner checkpoint

The learner writes one sentence beginning:

> “This Monte Carlo result does not prove…”

---

## 75:00–82:00 — The research verdict

### Goal

Convert metrics into a bounded decision.

### Verdict template

```text
Question:

Evidence used:
- baseline run ID:
- friction comparison run IDs:
- execution-story ID:
- dataset ID and checksum:
- experiment ID:
- seed:
- QuantForge Git SHA:

What matched expectations:

What deviated:

Delta classification:

Most important risk:

Most important missing evidence:

Verdict:
[reject / revise / continue research]

Next falsifiable experiment:
```

### Instructor narration

“A defensible research report is allowed to be disappointing.

If the result collapses under modest costs, the experiment succeeded by saving us from a weak idea.

If execution requires unavailable depth, the experiment succeeded by revealing a mismatch between signal and market structure.

If fold results are unstable, the experiment succeeded by identifying regime dependence.

If Monte Carlo shows an uncomfortable lower tail, the experiment succeeded by making risk visible before money was involved.

The purpose of research is not to manufacture confidence. It is to earn the next decision.”

### Final learner deliverable

A one-page QuantForge research report containing:

- hypothesis;
- assumptions;
- baseline result;
- execution-cost delta;
- L2 fill evidence;
- fold stability summary;
- Monte Carlo distribution;
- invalidation conditions;
- verdict;
- next experiment;
- complete reproduction metadata.

---

# Assessment

## Knowledge check

1. Why can a limit order show a better modeled price but produce a worse strategy outcome?
2. What information is missing from an OHLCV candle when modeling queue position?
3. Why should fees and slippage be stored in the scenario rather than described in narration?
4. What does a profitable average across folds hide?
5. What does a Monte Carlo fifth percentile mean—and what does it not mean?
6. What is the difference between an explainable deviation and an assumption failure?
7. Why must guided and expert modes use the same evidence?

## Practical assignment

Create a new scenario by changing exactly one of:

- EMA periods;
- leverage;
- taker fee;
- slippage;
- stop-loss distance;
- order-book quantity;
- limit price;
- market-making spread;
- Monte Carlo block size.

Before running it, record:

- expected directional behavior;
- the measurement most likely to change;
- the result that would invalidate the expectation.

After running it, classify the delta and write a five-sentence verdict.

## Grading rubric

| Dimension | Excellent | Adequate | Weak |
|---|---|---|---|
| Hypothesis | Specific, measurable, falsifiable | Measurable but incomplete | Vague belief |
| Assumptions | Explicit and linked to evidence | Listed but generic | Hidden or absent |
| Experiment design | One variable changed | Minor confounding | Many variables changed |
| Evidence | Reproducible IDs and metrics | Metrics without full provenance | Screenshot-only |
| Delta analysis | Explains direction and magnitude | Notes difference | Ignores difference |
| Verdict | Bounded and justified | General conclusion | Profit claim |
| Next experiment | Falsifiable and targeted | Relevant but broad | More optimization without rationale |

---

# Platform derivatives

## Udemy preview

Use the full module, with the first 12 minutes and the L2 partial-fill lab available as preview lectures.

Suggested lecture cuts:

1. The dangerous screenshot — 4:30
2. Write a hypothesis that can fail — 6:30
3. Baseline backtest — 13:00
4. Fees, slippage, market, and limit orders — 13:00
5. Order-book partial fills by hand — 14:00
6. Time-window stability — 14:00
7. Monte Carlo without false certainty — 10:00
8. Write the verdict — 7:00

## Pluralsight audition

Use a 12–15 minute cut from Lab C:

- show the static L2 book;
- predict the fill;
- calculate VWAP by hand;
- run the QuantForge execution story;
- compare expected, actual, and delta;
- switch between guided and expert modes;
- close with the limit-order partial-fill variant.

This segment demonstrates technical depth, explanation quality, visual evidence, and a complete learning payoff without requiring the rest of the course.

## LinkedIn Learning sample

Use an 8–10 minute cut:

> “Why touching the best price does not mean your order filled there.”

Keep the arithmetic, visual book consumption, and one reflection question. Remove platform-specific setup.

## YouTube lead generator

Title options:

- **Your Backtest Is Lying About Fills — Here’s the Order-Book Proof**
- **A Profitable Crypto Backtest Is Not Enough**
- **Market vs Limit Orders: The Backtest Mistake Developers Miss**

Standalone payoff:

The viewer learns to calculate a multi-level fill and sees a partial-fill example.

Call to action:

Run the same reproducible lab in QuantForge and download the research-report template.

## KDP chapters

The module becomes the opening book sequence:

1. **A Backtest Is a Question, Not an Answer**
2. **Write a Trading Hypothesis That Can Fail**
3. **Execution Costs Are Part of the Strategy**
4. **What Candles Hide About Order Books**
5. **Partial Fills and Volume-Weighted Price**
6. **Does the Result Survive Time?**
7. **Monte Carlo Without False Confidence**
8. **Writing a Defensible Research Verdict**

The book version expands definitions, diagrams, formulas, implementation notes, troubleshooting, and exercises while preserving the same scenario IDs and generated evidence.

## Workbook unit

The workbook contains:

- hypothesis worksheet;
- assumption and invalidation checklist;
- baseline evidence table;
- cost-comparison table;
- blank L2 fill calculation;
- fold-stability worksheet;
- Monte Carlo interpretation prompts;
- one-page verdict template;
- reproduction metadata checklist.

## Marketing assets generated from this module

- rising-equity-curve cold-open clip;
- three-level order-book consumption animation;
- market-versus-limit comparison card;
- fold-instability chart;
- Monte Carlo percentile graphic;
- “reject, revise, or continue research” decision graphic;
- downloadable report template;
- module completion certificate image.

---

# Production acceptance criteria

## Executability

- A single command seeds `course-btc-l2-v1`.
- A single command runs every module scenario.
- Every run writes evidence IDs and reproduction metadata.
- The order-book market and limit examples pass golden tests.
- Re-running with the same fixture, code SHA, and seed produces the same result.

## Teaching quality

- Every technical term is introduced before it becomes an assumption.
- Every chart answers a named question.
- Every metric is paired with a warning about what it cannot prove.
- The module changes one variable at a time before showing interactions.
- The learner produces an artifact, not merely watches a demonstration.

## Product quality

- Guided mode is useful without becoming a wall of text.
- Expert mode exposes raw evidence and compact comparisons.
- Mobile layouts keep tables, formulas, and controls usable.
- Captions, transcript, keyboard navigation, and color-independent status cues are included.
- All outputs carry scenario version and evidence provenance.

## Safety and truthfulness

- No mainnet order submission is used or taught.
- Synthetic and recorded fixtures are visibly labeled.
- No result is described as proof of profitability.
- Current time-window evaluation is not mislabeled as full train-select-test walk-forward optimization.
- Monte Carlo outputs are described as conditional distributions, not forecasts.

---

# Implementation backlog created by this module

1. Add the versioned executable course-scenario schema.
2. Add deterministic `course-btc-l2-v1` fixture generation.
3. Add a scenario runner that calls QuantForge services directly.
4. Add expected/actual/delta calculation and classification.
5. Add golden tests for the market and limit L2 examples.
6. Add evidence provenance: scenario version, Git SHA, dataset checksum, seed, and run IDs.
7. Add one-page research-report export.
8. Add generated instructor, KDP, workbook, quiz, and marketing renderers.
9. Add a real train-select-test walk-forward optimizer before teaching full walk-forward optimization.
10. Record the 12–15 minute L2 audition cut before producing the rest of the course.
