interface Props {
  metrics: Record<string, number>
}

const items: Array<[string, string, 'money' | 'percent' | 'number']> = [
  ['ending_equity', 'Ending equity', 'money'],
  ['net_profit', 'Net P&L', 'money'],
  ['total_return_pct', 'Total return', 'percent'],
  ['annualized_return_pct', 'Annualized', 'percent'],
  ['max_drawdown_pct', 'Max drawdown', 'percent'],
  ['sharpe_ratio', 'Sharpe', 'number'],
  ['sortino_ratio', 'Sortino', 'number'],
  ['win_rate_pct', 'Win rate', 'percent'],
  ['profit_factor', 'Profit factor', 'number'],
  ['expectancy', 'Expectancy', 'money'],
  ['total_fees', 'Fees', 'money'],
  ['total_funding', 'Funding', 'money'],
]

function format(value: number | undefined, kind: string) {
  const safe = Number.isFinite(value) ? (value as number) : 0
  if (kind === 'money') return safe.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })
  if (kind === 'percent') return `${safe.toFixed(2)}%`
  return safe.toFixed(2)
}

export function MetricGrid({ metrics }: Props) {
  return (
    <section className="metric-grid" aria-label="Backtest metrics">
      {items.map(([key, label, kind]) => (
        <article className="metric" key={key}>
          <span>{label}</span>
          <strong className={(metrics[key] ?? 0) < 0 ? 'negative' : ''}>{format(metrics[key], kind)}</strong>
        </article>
      ))}
    </section>
  )
}
