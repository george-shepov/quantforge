import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { BacktestResponse } from '../types'

export function PerformanceChart({ data }: { data: BacktestResponse['equity_curve'] }) {
  const chartData = data.map((point) => ({
    ...point,
    label: new Date(point.timestamp).toLocaleDateString(),
  }))

  return (
    <div className="chart-shell">
      <div className="panel-title"><span>EQUITY CURVE</span><span>{data.length} BARS</span></div>
      <div className="chart-canvas">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 16, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="label" minTickGap={48} />
            <YAxis width={48} domain={['auto', 'auto']} tickFormatter={(v: number | string) => `$${Math.round(Number(v) / 1000)}k`} />
            <Tooltip
              formatter={(value: number | string) => Number(value).toLocaleString('en-US', { style: 'currency', currency: 'USD' })}
              labelStyle={{ color: '#9ca8b7' }}
              contentStyle={{ background: '#0d1218', border: '1px solid #27313d' }}
            />
            <Line type="monotone" dataKey="equity" dot={false} stroke="currentColor" strokeWidth={1.5} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
