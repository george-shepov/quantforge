import type { BacktestResponse, RunConfig } from './types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8008'

export async function runBacktest(config: RunConfig): Promise<BacktestResponse> {
  const response = await fetch(`${API_URL}/api/backtests/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(payload.detail ?? 'Backtest failed')
  }
  return response.json()
}
