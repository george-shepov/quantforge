import type { BacktestResponse } from '../types'

function money(value: number, maximumFractionDigits = 2) {
  return value.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits })
}

export function TradesTable({ trades }: { trades: BacktestResponse['trades'] }) {
  const orderedTrades = [...trades].reverse()

  return (
    <div className="table-panel">
      <div className="panel-title"><span>TRADES</span><span>{trades.length} CLOSED</span></div>

      <div className="table-scroll">
        <table>
          <thead>
            <tr><th>#</th><th>Side</th><th>Entry</th><th>Exit</th><th>Notional</th><th>Net P&L</th><th>Return</th><th>MAE</th><th>MFE</th><th>Reason</th></tr>
          </thead>
          <tbody>
            {orderedTrades.map((trade) => (
              <tr key={trade.id}>
                <td>{trade.id}</td>
                <td className={trade.side === 'long' ? 'positive' : 'negative'}>{trade.side.toUpperCase()}</td>
                <td>{trade.entry_price.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                <td>{trade.exit_price.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                <td>{money(trade.notional, 0)}</td>
                <td className={trade.net_pnl >= 0 ? 'positive' : 'negative'}>{money(trade.net_pnl)}</td>
                <td>{trade.return_pct.toFixed(2)}%</td>
                <td>{trade.mae_pct.toFixed(2)}%</td>
                <td>{trade.mfe_pct.toFixed(2)}%</td>
                <td>{trade.exit_reason.replaceAll('_', ' ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="trade-card-list" aria-label="Closed trades">
        {orderedTrades.map((trade) => (
          <article className="trade-card" key={trade.id}>
            <div className="trade-card-header">
              <span className={trade.side === 'long' ? 'positive' : 'negative'}>#{trade.id} · {trade.side.toUpperCase()}</span>
              <strong className={trade.net_pnl >= 0 ? 'positive' : 'negative'}>{money(trade.net_pnl)}</strong>
            </div>
            <div className="trade-card-grid">
              <div><small>Entry</small><b>{trade.entry_price.toLocaleString(undefined, { maximumFractionDigits: 2 })}</b></div>
              <div><small>Exit</small><b>{trade.exit_price.toLocaleString(undefined, { maximumFractionDigits: 2 })}</b></div>
              <div><small>Notional</small><b>{money(trade.notional, 0)}</b></div>
              <div><small>Return</small><b>{trade.return_pct.toFixed(2)}%</b></div>
              <div><small>MAE / MFE</small><b>{trade.mae_pct.toFixed(2)}% / {trade.mfe_pct.toFixed(2)}%</b></div>
              <div className="trade-card-reason"><small>Exit reason</small><b>{trade.exit_reason.replaceAll('_', ' ')}</b></div>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
