# Arbitrage Lab Phase 1

Issue #31 Phase 1 turns the existing `cross_exchange_arbitrage` replay strategy into an
explainable scanner workspace. It is a research and teaching surface, not an execution surface.

## Safety contract

- The scanner reads recorded datasets and returns analysis.
- It never signs, submits, or routes an order.
- The response declares `environment: simulation` and `order_submission: false`.
- Replaying the dataset from an opportunity uses `/api/research/replay` and preserves the selected row as context.
- Adding an opportunity to an experiment uses `/api/research/experiments`.
- Mainnet order submission remains unavailable.

## Calculation contract

Phase 1 deliberately preserves the strategy's existing calculation:

```text
gross edge = (sell bid - buy ask) / buy ask × 10,000
fee cost = 2 × configured fee per leg
expected edge = gross edge - fee cost
decision = accepted when expected edge >= configured minimum edge
available quantity = min(buy ask size, sell bid size, configured maximum quantity)
estimated profit = buy ask × available quantity × expected edge / 10,000
```

The scanner evaluates both directions for every pair of venues available for a symbol. Accepted
and rejected candidates share one data model. A rejected row includes both the arithmetic and an
explicit threshold reason; UI filters change visibility only and never recalculate a decision.

Phase 3 will expand expected edge with quote age, timestamp skew, venue-specific fees, latency,
depth-aware slippage, opportunity persistence, funding exposure, expected legging loss, and a
rebalancing allowance. The Phase 1 interface names these omissions instead of implying the current
calculation proves executability.

## API

`POST /api/research/arbitrage/scan`

```json
{
  "dataset_id": "<recorded-dataset>",
  "min_edge_bps": 5,
  "fee_bps": 2,
  "max_quantity": 1,
  "limit": 500
}
```

Each opportunity contains its stable ID, both source-event checksums and timestamps, venue route,
displayed prices, gross and expected edges, two-leg fee cost, available quantity, estimated profit,
decision, explanation, and rejection reasons. IDs are deterministic for the dataset, both source
quotes, route, and scanner parameters. Only pairs involving the updated quote are re-evaluated, and
the response window is bounded while the dataset is scanned.

## Presentation modes

| Mode | Purpose | Calculation source |
| --- | --- | --- |
| Build | Configure the dataset, threshold, fee, and maximum quantity; preview future cost terms | Scanner response |
| Guided | Explain the decision, validation steps, limitations, and next falsifiable question | Scanner response |
| Expert | Show the compact raw decision record and both source checksums | Scanner response |
| Watch & Learn | Advance through candidates as a narrated replay lesson | Scanner response |

All modes use the same response object. Presentation cannot turn a rejection into an acceptance or
change any displayed number.

## Issue #12 course-engine mapping

Every Phase 1 scan can become a lab artifact:

- dataset ID plus buy/sell quote checksums and timestamps identify the evidence;
- scanner parameters state the assumptions;
- the decision and explanation demonstrate the calculation;
- a rejected candidate becomes a lesson about a failed hypothesis;
- Replay dataset records the deterministic full-dataset run and preserves the selected opportunity as context;
- Add to experiment sends the exact assumptions to the research queue;
- local history preserves the opportunity, request, and returned result for reflection.

A lesson prompt can ask a learner to recalculate gross edge, subtract both fees, predict the
decision, compare it with QuantForge, name the missing executability terms, and propose the next
falsifiable experiment.

## Acceptance matrix

| Phase 1 criterion | Implementation | Validation |
| --- | --- | --- |
| Dedicated Arbitrage workspace | `ArbitrageWorkspace.tsx` and the primary workspace tabs | Frontend build |
| Existing replay strategy and datasets | Shared engine evaluation, dataset catalog, replay and experiment APIs | Backend unit/integration tests |
| Required opportunity columns | Desktop opportunity tape and mobile opportunity cards | TypeScript validation |
| Build, Guided, Watch & Learn | Four modes, including the larger-vision Expert mode | Frontend unit tests |
| Accepted and rejected explanations | Shared candidate projection with explicit rejection reasons | Backend unit/integration tests |
| Replay from an opportunity | Clearly labeled full-dataset replay with exact scanner parameters and selected-row context | Frontend API integration test |
| Add parameters to experiment | Existing experiment endpoint with exact scanner parameters | Frontend API integration test |
| Simulation first / no mainnet | Scanner safety metadata and no execution call in the workspace | Backend integration test |
| Mobile friendly | Responsive cards, controls, equations, actions, and safe-area-aware shell | Production CSS/build |

## Local validation

```bash
cd backend
PYTHONPATH=. pytest -q

cd ../frontend
npm install --no-package-lock
npm run lint
npm test
npm run build
```

The production build currently reports Vite's advisory for a JavaScript chunk over 500 kB. Phase 1
does not increase runtime privileges or add a mainnet configuration to address that unrelated
optimization opportunity.
