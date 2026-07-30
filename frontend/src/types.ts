export type StrategyName = 'ema_crossover' | 'mean_reversion' | 'breakout'
export type ScenarioName = 'baseline' | 'flash_crash' | 'volatility_spike' | 'liquidity_drought' | 'funding_squeeze'
export type ExchangeName = 'hyperliquid' | 'bitmex' | 'synthetic'
export type MarketKind = 'spot' | 'perp' | 'future'

export interface RunConfig {
  market: {
    exchange: ExchangeName
    symbol: string
    interval: string
    limit: number
    fallback_to_synthetic: boolean
  }
  market_kind: MarketKind
  starting_capital: number
  strategy: {
    name: StrategyName
    fast_period: number
    slow_period: number
    lookback: number
    entry_z: number
    exit_z: number
    breakout_period: number
  }
  execution: {
    order_type: 'market' | 'limit'
    allocation: number
    leverage: number
    taker_fee_bps: number
    maker_fee_bps: number
    base_slippage_bps: number
    limit_offset_bps: number
    maintenance_margin_rate: number
    stop_loss_pct: number | null
    take_profit_pct: number | null
  }
  scenario: {
    name: ScenarioName
    start_percent: number
    duration_bars: number
    shock_pct: number
    volatility_multiplier: number
    slippage_multiplier: number
    funding_rate_hourly: number
  }
}

export interface BacktestResponse {
  run_id: string
  source: string
  warnings: string[]
  metrics: Record<string, number>
  equity_curve: Array<{
    timestamp: string
    equity: number
    drawdown_pct: number
    close: number
    signal: number
  }>
  trades: Array<{
    id: number
    side: 'long' | 'short'
    entry_time: string
    exit_time: string
    entry_price: number
    exit_price: number
    quantity: number
    notional: number
    net_pnl: number
    return_pct: number
    fees: number
    funding: number
    exit_reason: string
    mae_pct: number
    mfe_pct: number
  }>
}
