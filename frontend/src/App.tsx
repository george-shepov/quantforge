import { useMemo, useState } from 'react'
import type { ChangeEvent, ReactNode } from 'react'
import { runBacktest } from './api'
import { MetricGrid } from './components/MetricGrid'
import { PerformanceChart } from './components/PerformanceChart'
import { TradesTable } from './components/TradesTable'
import type { BacktestResponse, RunConfig, ScenarioName, StrategyName } from './types'

const initialConfig: RunConfig = {
  market: { exchange: 'hyperliquid', symbol: 'BTC', interval: '1h', limit: 1000, fallback_to_synthetic: true },
  market_kind: 'perp',
  starting_capital: 100_000,
  strategy: { name: 'ema_crossover', fast_period: 20, slow_period: 50, lookback: 20, entry_z: 1.5, exit_z: 0.25, breakout_period: 30 },
  execution: { order_type: 'market', allocation: 0.25, leverage: 3, taker_fee_bps: 5, maker_fee_bps: 2, base_slippage_bps: 3, limit_offset_bps: 2, maintenance_margin_rate: 0.005, stop_loss_pct: 0.04, take_profit_pct: 0.08 },
  scenario: { name: 'baseline', start_percent: 0.6, duration_bars: 24, shock_pct: -0.12, volatility_multiplier: 3, slippage_multiplier: 4, funding_rate_hourly: 0.00001 },
}

export default function App() {
  const [config, setConfig] = useState<RunConfig>(initialConfig)
  const [result, setResult] = useState<BacktestResponse | null>(null)
  const [runs, setRuns] = useState<BacktestResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const status = useMemo(() => result ? `${result.source.toUpperCase()} · ${result.metrics.trade_count ?? 0} TRADES` : 'READY', [result])

  function patch<T extends keyof RunConfig>(section: T, value: RunConfig[T]) {
    setConfig((current) => ({ ...current, [section]: value }))
  }

  async function execute() {
    setLoading(true)
    setError('')
    try {
      const output = await runBacktest(config)
      setResult(output)
      setRuns((existing) => [output, ...existing].slice(0, 6))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main>
      <header className="topbar">
        <div><strong>QUANTFORGE</strong><span>CRYPTO STRATEGY LAB</span></div>
        <div className="status"><i /> {status}</div>
      </header>

      <div className="workspace">
        <aside className="controls">
          <div className="panel-title"><span>EXPERIMENT</span><span>SIMULATION ONLY</span></div>

          <Field label="Exchange">
            <select value={config.market.exchange} onChange={(e: ChangeEvent<HTMLSelectElement>) => patch('market', { ...config.market, exchange: e.target.value as RunConfig['market']['exchange'] })}>
              <option value="hyperliquid">Hyperliquid</option><option value="bitmex">BitMEX</option><option value="synthetic">Synthetic</option>
            </select>
          </Field>
          <div className="field-row">
            <Field label="Symbol"><select value={config.market.symbol} onChange={(e: ChangeEvent<HTMLSelectElement>) => patch('market', { ...config.market, symbol: e.target.value })}><option>BTC</option><option>ETH</option><option>SOL</option><option>HYPE</option></select></Field>
            <Field label="Interval"><select value={config.market.interval} onChange={(e: ChangeEvent<HTMLSelectElement>) => patch('market', { ...config.market, interval: e.target.value })}><option>5m</option><option>15m</option><option>1h</option><option>4h</option><option>1d</option></select></Field>
          </div>
          <div className="field-row">
            <Field label="Market"><select value={config.market_kind} onChange={(e: ChangeEvent<HTMLSelectElement>) => patch('market_kind', e.target.value as RunConfig['market_kind'])}><option value="spot">Spot</option><option value="perp">Perpetual</option><option value="future">Future</option></select></Field>
            <Field label="Bars"><input type="number" value={config.market.limit} onChange={(e: ChangeEvent<HTMLInputElement>) => patch('market', { ...config.market, limit: Number(e.target.value) })} /></Field>
          </div>

          <Field label="Strategy">
            <select value={config.strategy.name} onChange={(e: ChangeEvent<HTMLSelectElement>) => patch('strategy', { ...config.strategy, name: e.target.value as StrategyName })}>
              <option value="ema_crossover">EMA crossover</option><option value="mean_reversion">Mean reversion</option><option value="breakout">Breakout</option>
            </select>
          </Field>
          {config.strategy.name === 'ema_crossover' && <div className="field-row"><NumberField label="Fast EMA" value={config.strategy.fast_period} onChange={(v) => patch('strategy', { ...config.strategy, fast_period: v })} /><NumberField label="Slow EMA" value={config.strategy.slow_period} onChange={(v) => patch('strategy', { ...config.strategy, slow_period: v })} /></div>}
          {config.strategy.name === 'mean_reversion' && <div className="field-row"><NumberField label="Lookback" value={config.strategy.lookback} onChange={(v) => patch('strategy', { ...config.strategy, lookback: v })} /><NumberField label="Entry Z" value={config.strategy.entry_z} step="0.1" onChange={(v) => patch('strategy', { ...config.strategy, entry_z: v })} /></div>}
          {config.strategy.name === 'breakout' && <NumberField label="Breakout period" value={config.strategy.breakout_period} onChange={(v) => patch('strategy', { ...config.strategy, breakout_period: v })} />}

          <div className="field-row">
            <NumberField label="Allocation %" value={config.execution.allocation * 100} step="1" onChange={(v) => patch('execution', { ...config.execution, allocation: v / 100 })} />
            <NumberField label="Leverage" value={config.market_kind === 'spot' ? 1 : config.execution.leverage} step="1" disabled={config.market_kind === 'spot'} onChange={(v) => patch('execution', { ...config.execution, leverage: v })} />
          </div>
          <div className="field-row">
            <NumberField label="Fee bps" value={config.execution.taker_fee_bps} step="0.1" onChange={(v) => patch('execution', { ...config.execution, taker_fee_bps: v })} />
            <NumberField label="Slippage bps" value={config.execution.base_slippage_bps} step="0.1" onChange={(v) => patch('execution', { ...config.execution, base_slippage_bps: v })} />
          </div>

          <Field label="Stress scenario">
            <select value={config.scenario.name} onChange={(e: ChangeEvent<HTMLSelectElement>) => patch('scenario', { ...config.scenario, name: e.target.value as ScenarioName })}>
              <option value="baseline">Baseline</option><option value="flash_crash">Flash crash</option><option value="volatility_spike">Volatility spike</option><option value="liquidity_drought">Liquidity drought</option><option value="funding_squeeze">Funding squeeze</option>
            </select>
          </Field>
          {config.scenario.name === 'flash_crash' && <NumberField label="Shock %" value={config.scenario.shock_pct * 100} step="1" onChange={(v) => patch('scenario', { ...config.scenario, shock_pct: v / 100 })} />}
          {config.scenario.name === 'liquidity_drought' && <NumberField label="Slippage multiplier" value={config.scenario.slippage_multiplier} step="0.5" onChange={(v) => patch('scenario', { ...config.scenario, slippage_multiplier: v })} />}
          {(config.scenario.name === 'volatility_spike' || config.scenario.name === 'funding_squeeze') && <NumberField label="Stress multiplier" value={config.scenario.volatility_multiplier} step="0.5" onChange={(v) => patch('scenario', { ...config.scenario, volatility_multiplier: v })} />}

          <button className="run" onClick={execute} disabled={loading}>{loading ? 'RUNNING…' : 'RUN BACKTEST'}</button>
          {error && <div className="error">{error}</div>}
          <p className="safety">No wallet connection. No exchange keys. No live orders.</p>
        </aside>

        <section className="results">
          {result ? (
            <>
              {result.warnings.length > 0 && <div className="warnings">{result.warnings.map((warning) => <span key={warning}>{warning}</span>)}</div>}
              <MetricGrid metrics={result.metrics} />
              <PerformanceChart data={result.equity_curve} />
              <TradesTable trades={result.trades} />
            </>
          ) : (
            <div className="empty">
              <strong>NO EXPERIMENT SELECTED</strong>
              <p>Configure a market, strategy, execution model, and stress scenario. QuantForge will use public exchange candles or a deterministic synthetic fallback.</p>
            </div>
          )}
        </section>

        <aside className="history">
          <div className="panel-title"><span>RECENT RUNS</span><span>LOCAL SESSION</span></div>
          {runs.length === 0 && <p className="muted">Runs appear here for side-by-side inspection.</p>}
          {runs.map((run, index) => (
            <button className="run-card" key={run.run_id} onClick={() => setResult(run)}>
              <span>RUN {runs.length - index}</span><strong className={(run.metrics.total_return_pct ?? 0) >= 0 ? 'positive' : 'negative'}>{(run.metrics.total_return_pct ?? 0).toFixed(2)}%</strong>
              <small>{run.source} · {run.metrics.trade_count} trades · DD {(run.metrics.max_drawdown_pct ?? 0).toFixed(1)}%</small>
            </button>
          ))}
        </aside>
      </div>
    </main>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>
}

function NumberField({ label, value, onChange, step = '1', disabled = false }: { label: string; value: number; onChange: (v: number) => void; step?: string; disabled?: boolean }) {
  return <Field label={label}><input type="number" value={value} step={step} disabled={disabled} onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(Number(e.target.value))} /></Field>
}
