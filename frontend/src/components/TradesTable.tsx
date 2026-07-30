import type { BacktestResponse } from '../types'

export function TradesTable({ trades }: { trades: BacktestResponse['trades'] }) {
  return (
    <div className="table-panel">
      <div className="panel-title"><span>TRADES</span><span>{trades.length} CLOSED</span></div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr><th>#</th><th>Side</th><th>Entry</th><th>Exit</th><th>Notional</th><th>Net P&L</th><th>Return</th><th>MAE</th><th>MFE</th><th>Reason</th></tr>
          </thead>
          <tbody>
            {[...trades].reverse().map((trade) => (
              <tr key={trade.id}>
                <td>{trade.id}</td>
                <td className={trade.side === 'long' ? 'positive' : 'negative'}>{trade.side.toUpperCase()}</td>
                <td>{trade.entry_price.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                <td>{trade.exit_price.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                <td>${trade.notional.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                <td className={trade.net_pnl >= 0 ? 'positive' : 'negative'}>${trade.net_pnl.toFixed(2)}</td>
                <td>{trade.return_pct.toFixed(2)}%</td>
                <td>{trade.mae_pct.toFixed(2)}%</td>
                <td>{trade.mfe_pct.toFixed(2)}%</td>
                <td>{trade.exit_reason.replaceAll('_', ' ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
