# Starter-First Course Strategy

## Product title

**Crypto Algorithmic Trading Research with Python**  
*Backtesting, Order Books, Walk-Forward Analysis, and Monte Carlo with QuantForge*

## Decision

Do not produce twenty hours of course video yet.

Produce one excellent, executable 60–90 minute module first and use it as:

- the Udemy preview;
- the Pluralsight audition source;
- the LinkedIn Learning sample source;
- a YouTube lead generator;
- the first KDP chapters;
- the first workbook unit;
- proof that the teaching format and publishing pipeline work.

The first module is:

> **Can This Strategy Survive Reality?**  
> From a promising backtest to order-book execution, time-window evaluation, Monte Carlo uncertainty, and a defensible research verdict.

See [`modules/01-can-this-strategy-survive-reality.md`](modules/01-can-this-strategy-survive-reality.md).

## One source of truth

The canonical teaching source is an **executable laboratory scenario**, not a video script, slide deck, or handwritten chapter.

Each scenario must contain:

- a falsifiable research question;
- learner level and prerequisites;
- a deterministic or checksum-pinned dataset reference;
- exact QuantForge request payloads and parameters;
- assumptions and invalidation conditions;
- expected measurements or expected directional behavior;
- actual measurements produced by the run;
- absolute and percentage deltas;
- a classification: matched, explainable deviation, assumption failure, or data-quality warning;
- guided explanation and expert summary;
- validation steps;
- reflection prompts, quiz items, and an assignment;
- evidence links to the run, replay, experiment, dataset, seed, and Git commit.

The scenario is rendered into:

1. QuantForge guided-mode laboratory
2. QuantForge expert-mode evidence view
3. instructor recording script
4. learner workbook
5. KDP chapter source
6. quiz and assignment bank
7. YouTube lesson and short clips
8. Udemy preview lesson
9. Pluralsight audition segment
10. LinkedIn Learning sample
11. landing-page copy and screenshots

Platform-specific exports may shorten or rearrange the canonical material, but they must not invent independent claims.

## Evidence contract

Every generated claim must be traceable to:

- `scenario_id`;
- scenario schema version;
- QuantForge Git SHA;
- dataset ID and checksum chain;
- random seed;
- request payload;
- run, replay, or experiment ID;
- generation timestamp.

A result produced from live public data must be labeled time-specific. A deterministic fixture must be labeled synthetic or recorded. Testnet, live-read-only, simulated, and synthetic evidence must never be visually interchangeable.

## Teaching contract

Every lesson follows the same loop:

1. **Question** — What are we trying to learn?
2. **Hypothesis** — What result would support the idea?
3. **Assumptions** — What must be true for the test to mean anything?
4. **Experiment** — Change one variable at a time before testing interactions.
5. **Evidence** — Inspect fills, fees, funding, P&L, drawdown, and uncertainty.
6. **Delta** — Compare expected and actual behavior.
7. **Invalidation** — State what would make the conclusion unreliable.
8. **Verdict** — Reject, revise, or continue the hypothesis.
9. **Reproduction** — Rerun from the same scenario and evidence references.

The course teaches research judgment, not a promise of profitable trading.

## Current implementation boundary

QuantForge currently supports:

- candle backtests with fees, slippage, leverage, funding, stops, targets, and stress scenarios;
- deterministic event replay over recorded market events;
- L2 execution stories with guided and expert modes;
- parameter grids;
- time-window fold evaluation;
- seeded block Monte Carlo summaries;
- persisted experiment history;
- explicit simulation/testnet safety boundaries.

Until train-select-test optimization is implemented, course material must call the current experiment feature **walk-forward window evaluation**, not full walk-forward optimization.

## Definition of done for the starter module

The starter module is complete only when:

- every demonstration runs from its scenario definition;
- deterministic examples pass golden tests;
- generated numbers are inserted into the lesson rather than copied by hand;
- guided and expert views use the same evidence;
- a learner can export a compact research report;
- all platform derivatives identify the same scenario version;
- the 12–15 minute audition cut works without hidden context;
- the YouTube version has a useful standalone payoff and a natural QuantForge call to action;
- the KDP chapters and workbook are generated from the same blocks;
- no result is framed as financial advice or proof of future profitability.

## Expansion gate

Build the complete course from Issue #12 only after the starter module proves:

- learners understand the question → hypothesis → evidence → delta → verdict loop;
- executable examples are reliable enough to record once and regenerate later;
- the guided mode helps beginners without annoying experts;
- the material can be repackaged without manual factual drift;
- at least one distribution channel shows real demand: watch time, email signups, course wishlists, paid enrollments, or hosted-lab conversions.
