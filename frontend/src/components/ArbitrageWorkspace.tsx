import { useEffect, useMemo, useState } from 'react'

import { queueExperiment, replayDataset, scanArbitrage } from '../api'
import type {
  ArbitrageDecision,
  ArbitrageMode,
  ArbitrageOpportunity,
  ArbitrageScanRequest,
  ArbitrageScanResponse,
  DatasetManifest,
  HistoryEntry,
} from '../types'

type DecisionFilter = 'all' | ArbitrageDecision

interface Props {
  datasets: DatasetManifest[]
  remember: (entry: Omit<HistoryEntry, 'id' | 'createdAt'>) => void
  onChanged: () => Promise<void>
}

export const modeGuidance: Record<ArbitrageMode, string> = {
  build: 'Choose the evidence and assumptions that define this replay scan.',
  guided: 'Follow the arithmetic from displayed spread to an accepted or rejected decision.',
  expert: 'Inspect the compact decision record and both source checksums without tutorial copy.',
  watch: 'Step through candidates as a narrated lesson generated from replay evidence.',
}

export function filterOpportunities(opportunities: ArbitrageOpportunity[], filter: DecisionFilter) {
  return filter === 'all' ? opportunities : opportunities.filter((item) => item.decision === filter)
}

export function opportunityLesson(item: ArbitrageOpportunity) {
  const route = `Buy ${item.symbol} on ${item.buy_exchange}, then sell on ${item.sell_exchange}.`
  return `${route} ${item.explanation} Modeled profit at the displayed quantity: ${usd(item.estimated_profit)}.`
}

export function ArbitrageWorkspace({ datasets, remember, onChanged }: Props) {
  const [request, setRequest] = useState<ArbitrageScanRequest>({
    dataset_id: datasets[0]?.dataset_id ?? '',
    min_edge_bps: 5,
    fee_bps: 2,
    max_quantity: 1,
    limit: 500,
  })
  const [mode, setMode] = useState<ArbitrageMode>('guided')
  const [filter, setFilter] = useState<DecisionFilter>('all')
  const [result, setResult] = useState<ArbitrageScanResponse | null>(null)
  const [selectedId, setSelectedId] = useState('')
  const [loading, setLoading] = useState(false)
  const [action, setAction] = useState('')
  const [actionMessage, setActionMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!request.dataset_id && datasets[0]) {
      setRequest((current) => ({ ...current, dataset_id: datasets[0].dataset_id }))
    }
  }, [datasets, request.dataset_id])

  const visible = useMemo(
    () => filterOpportunities(result?.opportunities ?? [], filter),
    [filter, result],
  )
  const selected = visible.find((item) => item.opportunity_id === selectedId) ?? visible[0] ?? null

  useEffect(() => {
    if (mode !== 'watch' || visible.length < 2) return
    const timer = window.setInterval(() => {
      setSelectedId((current) => {
        const index = visible.findIndex((item) => item.opportunity_id === current)
        return visible[(index + 1) % visible.length].opportunity_id
      })
    }, 4500)
    return () => window.clearInterval(timer)
  }, [mode, visible])

  async function scan() {
    setLoading(true)
    setError('')
    try {
      const output = await scanArbitrage(request)
      setResult(output)
      setSelectedId(output.opportunities[0]?.opportunity_id ?? '')
      remember({
        kind: 'arbitrage',
        title: `Arbitrage scan · ${request.dataset_id}`,
        summary: `${output.accepted_count} accepted · ${output.rejected_count} rejected`,
        payload: { request, output },
      })
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setLoading(false)
    }
  }

  async function replayDatasetFromOpportunity(item: ArbitrageOpportunity) {
    if (!result) return
    setAction('replay')
    setActionMessage('')
    setError('')
    try {
      const config = {
        dataset_id: result.dataset_id,
        strategy: 'cross_exchange_arbitrage' as const,
        parameters: { ...result.parameters },
        starting_cash: 100_000,
        timer_interval_ms: 1_000,
      }
      const output = await replayDataset(config)
      remember({
        kind: 'replay',
        title: `Dataset replay · ${result.dataset_id}`,
        summary: `${output.fill_count} fills · ${output.return_pct.toFixed(4)}% return · from ${item.opportunity_id}`,
        payload: { opportunity: item, config, output },
      })
      setActionMessage(`Dataset replay complete: ${output.fill_count} fills, ${output.return_pct.toFixed(4)}% modeled return.`)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setAction('')
    }
  }

  async function addToExperiment(item: ArbitrageOpportunity) {
    if (!result) return
    setAction('experiment')
    setActionMessage('')
    setError('')
    try {
      const config = {
        dataset_id: result.dataset_id,
        strategy: 'cross_exchange_arbitrage' as const,
        starting_cash: 100_000,
        timer_interval_ms: 1_000,
        base_parameters: { ...result.parameters },
        parameter_grid: {
          min_edge_bps: [result.parameters.min_edge_bps],
          max_quantity: [result.parameters.max_quantity],
        },
        walk_forward_folds: 4,
        monte_carlo_runs: 500,
        monte_carlo_block_size: 5,
        seed: 7,
      }
      const output = await queueExperiment(config)
      remember({
        kind: 'experiment',
        title: `Opportunity experiment · ${item.opportunity_id}`,
        summary: `${output.status} · exact scanner parameters preserved`,
        payload: { opportunity: item, config, output },
      })
      setActionMessage(`Experiment ${output.id} queued with this opportunity's parameters.`)
      await onChanged()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setAction('')
    }
  }

  return <div className="arbitrage-page">
    <section className="arb-hero">
      <div>
        <span className="arb-kicker">ARBITRAGE LAB · PHASE 1</span>
        <h1>Reason about the edge before risking the trade.</h1>
        <p>{modeGuidance[mode]}</p>
      </div>
      <div className="arb-safety"><i />SIMULATION ONLY<span>NO ORDER SUBMISSION</span></div>
    </section>

    <div className="arb-mode-bar" aria-label="Arbitrage presentation mode">
      {(['build', 'guided', 'expert', 'watch'] as ArbitrageMode[]).map((item) => (
        <button key={item} className={mode === item ? 'active' : ''} onClick={() => setMode(item)}>
          {item === 'watch' ? 'Watch & Learn' : item}
        </button>
      ))}
    </div>

    <section className="arb-builder surface-card">
      <label><span>Replay dataset</span><select value={request.dataset_id} onChange={(event) => setRequest({ ...request, dataset_id: event.target.value })}><option value="">Select dataset</option>{datasets.map((dataset) => <option key={dataset.dataset_id} value={dataset.dataset_id}>{dataset.dataset_id} · {dataset.event_count.toLocaleString()} events</option>)}</select></label>
      <label><span>Minimum edge (bps)</span><input inputMode="decimal" type="number" step="0.1" value={request.min_edge_bps} onChange={(event) => setRequest({ ...request, min_edge_bps: Number(event.target.value) })} /></label>
      <label><span>Fee per leg (bps)</span><input inputMode="decimal" type="number" step="0.1" min="0" value={request.fee_bps} onChange={(event) => setRequest({ ...request, fee_bps: Number(event.target.value) })} /></label>
      <label><span>Maximum quantity</span><input inputMode="decimal" type="number" step="0.01" min="0.00000001" value={request.max_quantity} onChange={(event) => setRequest({ ...request, max_quantity: Number(event.target.value) })} /></label>
      <button className="arb-scan-button" disabled={loading || !request.dataset_id} onClick={() => void scan()}>{loading ? 'SCANNING REPLAY…' : 'SCAN REPLAY'}</button>
      {mode === 'build' && <p className="arb-build-note">Expected edge = gross spread − buy fee − sell fee. Later phases add quote age, skew, latency, slippage, funding, legging loss, and rebalancing without hiding any term.</p>}
      {error && <div className="error arb-error">{error}</div>}
    </section>

    {result ? <>
      <section className="arb-summary" aria-label="Arbitrage scan summary">
        <SummaryMetric label="Candidates" value={result.candidate_count.toLocaleString()} />
        <SummaryMetric label="Accepted" value={result.accepted_count.toLocaleString()} tone="positive" />
        <SummaryMetric label="Rejected" value={result.rejected_count.toLocaleString()} tone="negative" />
        <SummaryMetric label="Events replayed" value={result.event_count.toLocaleString()} />
        <SummaryMetric label="Best expected edge" value={result.opportunities.length ? `${Math.max(...result.opportunities.map((item) => item.expected_edge_bps)).toFixed(2)} bps` : '—'} />
      </section>

      <section className="arb-terminal surface-card">
        <div className="arb-terminal-head">
          <div><span>OPPORTUNITY TAPE</span><h2>Every decision leaves evidence</h2></div>
          <div className="arb-filters">{(['all', 'accepted', 'rejected'] as DecisionFilter[]).map((item) => <button key={item} className={filter === item ? 'active' : ''} onClick={() => setFilter(item)}>{item}</button>)}</div>
        </div>
        {visible.length ? <>
          <div className="arb-table-wrap">
            <table className="arb-table"><thead><tr><th>Status</th><th>Symbol</th><th>Buy venue</th><th>Sell venue</th><th>Gross edge</th><th>Expected edge</th><th>Available qty</th><th>Est. profit</th></tr></thead><tbody>{visible.map((item) => <tr key={item.opportunity_id} className={selected?.opportunity_id === item.opportunity_id ? 'selected' : ''} onClick={() => setSelectedId(item.opportunity_id)}><td><DecisionPill decision={item.decision} /></td><td>{item.symbol}</td><td>{item.buy_exchange}<small>{number(item.buy_price)}</small></td><td>{item.sell_exchange}<small>{number(item.sell_price)}</small></td><td>{item.gross_edge_bps.toFixed(2)} bps</td><td className={item.expected_edge_bps >= 0 ? 'positive' : 'negative'}>{item.expected_edge_bps.toFixed(2)} bps</td><td>{number(item.quantity)}</td><td className={item.estimated_profit >= 0 ? 'positive' : 'negative'}>{usd(item.estimated_profit)}</td></tr>)}</tbody></table>
          </div>
          <div className="arb-card-list">{visible.map((item) => <button key={item.opportunity_id} className={`arb-opportunity-card ${selected?.opportunity_id === item.opportunity_id ? 'selected' : ''}`} onClick={() => setSelectedId(item.opportunity_id)}><div><DecisionPill decision={item.decision} /><b>{item.symbol}</b><strong className={item.expected_edge_bps >= 0 ? 'positive' : 'negative'}>{item.expected_edge_bps.toFixed(2)} bps</strong></div><p><span>BUY</span>{item.buy_exchange} @ {number(item.buy_price)}</p><p><span>SELL</span>{item.sell_exchange} @ {number(item.sell_price)}</p><footer><span>{number(item.quantity)} available</span><b>{usd(item.estimated_profit)}</b></footer></button>)}</div>
          {selected && <OpportunityDetail item={selected} mode={mode} index={visible.indexOf(selected)} total={visible.length} action={action} actionMessage={actionMessage} onReplay={() => void replayDatasetFromOpportunity(selected)} onExperiment={() => void addToExperiment(selected)} />}
        </> : <div className="arb-empty"><b>No {filter === 'all' ? '' : filter} candidates in this replay.</b><p>Try another filter or scan a synchronized multi-venue L2 dataset.</p></div>}
      </section>
    </> : <section className="arb-onboarding surface-card"><span>START WITH EVIDENCE</span><h2>Select a recorded multi-venue dataset</h2><p>The lab deterministically replays order-book events, evaluates both directions between venues, and keeps rejected candidates visible. A failed edge is still a successful lesson.</p><div><b>1</b>Choose a dataset<i /> <b>2</b>State the threshold<i /> <b>3</b>Inspect every decision</div></section>}
  </div>
}

function OpportunityDetail({ item, mode, index, total, action, actionMessage, onReplay, onExperiment }: { item: ArbitrageOpportunity; mode: ArbitrageMode; index: number; total: number; action: string; actionMessage: string; onReplay: () => void; onExperiment: () => void }) {
  return <article className={`arb-detail mode-${mode}`}>
    <header><div><span>{mode === 'watch' ? `LESSON ${index + 1} OF ${total}` : 'SELECTED DECISION'}</span><h3>{item.buy_exchange} → {item.sell_exchange}</h3></div><DecisionPill decision={item.decision} /></header>
    {mode !== 'expert' && <p className="arb-explanation">{mode === 'watch' ? opportunityLesson(item) : item.explanation}</p>}
    <div className="arb-equation"><span><small>Gross spread</small>{item.gross_edge_bps.toFixed(4)} bps</span><i>−</i><span><small>Two-leg fees</small>{item.fee_cost_bps.toFixed(4)} bps</span><i>=</i><span className={item.expected_edge_bps >= 0 ? 'positive' : 'negative'}><small>Expected edge</small>{item.expected_edge_bps.toFixed(4)} bps</span></div>
    {mode === 'guided' && <div className="arb-guided-grid"><section><span>WHY THIS DECISION</span><p>{item.decision === 'accepted' ? 'The expected edge is at or above the configured minimum. That makes it a research candidate—not a guaranteed or executable profit.' : item.rejection_reasons.join(' ')}</p></section><section><span>HOW TO VALIDATE</span><p>Recalculate the spread from the recorded buy ask and sell bid, subtract both venue fees, then compare the result with the minimum edge.</p></section><section><span>WHAT THIS DOES NOT PROVE</span><p>Phase 1 does not yet model quote age, clock skew, depth beyond the top level, latency, partial fills, balances, or orphan-leg risk.</p></section><section><span>NEXT FALSIFIABLE QUESTION</span><p>Does this edge survive realistic execution costs and synchronized venue timestamps?</p></section></div>}
    {mode === 'expert' && <pre>{JSON.stringify(item, null, 2)}</pre>}
    {mode === 'watch' && <div className="arb-watch-progress"><i style={{ width: `${((index + 1) / total) * 100}%` }} /></div>}
    <div className="arb-actions"><button onClick={onReplay} disabled={Boolean(action)}>{action === 'replay' ? 'REPLAYING DATASET…' : 'REPLAY DATASET'}</button><button onClick={onExperiment} disabled={Boolean(action)}>{action === 'experiment' ? 'QUEUEING…' : 'ADD TO EXPERIMENT'}</button><span>Replay reruns the full recorded dataset with these parameters; the selected opportunity is preserved as context.</span></div>
    {actionMessage && <p className="arb-action-message">{actionMessage}</p>}
    <footer><code>{item.opportunity_id}</code><span>buy {item.buy_source_event_checksum.slice(0, 10)}… · sell {item.sell_source_event_checksum.slice(0, 10)}…</span><strong>{number(item.quantity)} {item.symbol} · {usd(item.estimated_profit)}</strong></footer>
  </article>
}

function DecisionPill({ decision }: { decision: ArbitrageDecision }) { return <span className={`arb-decision ${decision}`}>{decision}</span> }
function SummaryMetric({ label, value, tone = '' }: { label: string; value: string; tone?: string }) { return <article><span>{label}</span><strong className={tone}>{value}</strong></article> }
function number(value: number) { return value.toLocaleString('en-US', { maximumFractionDigits: 8 }) }
function usd(value: number) { return value.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 4 }) }
