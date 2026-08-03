export type StrategyName = 'ema_crossover' | 'mean_reversion' | 'breakout'
export type EventStrategyName = 'cross_exchange_arbitrage' | 'inventory_market_making'
export type ScenarioName = 'baseline' | 'flash_crash' | 'volatility_spike' | 'liquidity_drought' | 'funding_squeeze'
export type ExchangeName = 'hyperliquid' | 'bybit' | 'bitmex' | 'whitebit' | 'synthetic'
export type MarketKind = 'spot' | 'perp' | 'future'
export type WorkspaceName = 'backtest' | 'arbitrage' | 'recordings' | 'replay' | 'experiments' | 'manual' | 'system' | 'history'
export type ArbitrageMode = 'build' | 'guided' | 'expert' | 'watch'
export type ArbitrageDecision = 'accepted' | 'rejected'
export type StoryMode = 'expert' | 'guided'

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

export interface ExchangeEnvironment {
  environment: string
  websocketConfigured: boolean
  executionAllowed: boolean
  badge: string
}

export interface CatalogResponse {
  exchanges: ExchangeName[]
  exchangeEnvironments: Record<string, ExchangeEnvironment>
  symbols: string[]
  intervals: string[]
  marketKinds: MarketKind[]
  strategies: StrategyName[]
  eventStrategies: EventStrategyName[]
  scenarios: ScenarioName[]
  mainnetOrderSubmission: boolean
}

export interface SafetyStatus {
  enabled?: boolean
  network?: string
  configured?: boolean
  max_notional?: number
  [key: string]: unknown
}

export interface ResearchCapabilities {
  market_data: string[]
  datasets: string[]
  strategy_callbacks: string[]
  portfolio: string[]
  research: string[]
  microstructure: string[]
  persistence: string[]
  execution: SafetyStatus
}

export interface RecordingConfig {
  symbols: string[]
  network: 'mainnet' | 'testnet'
  flush_size: number
  flush_interval_seconds: number
  reconnect_max_seconds: number
}

export interface RecordingStatus {
  dataset_id: string
  network: string
  symbols: string[]
  connected: boolean
  events_recorded: number
  last_error: string | null
  started_at: string
  stopping: boolean
}

export interface DatasetManifest {
  dataset_id: string
  created_at: string
  updated_at: string
  schema_version: number
  event_count: number
  min_event_time_ns: number | null
  max_event_time_ns: number | null
  parts: string[]
  symbols: string[]
  kinds: string[]
  chain_hash: string
}

export interface ReplayRequest {
  dataset_id: string
  strategy: EventStrategyName
  parameters: Record<string, unknown>
  starting_cash: number
  timer_interval_ms: number
}

export interface ReplayResponse {
  strategy: string
  event_count: number
  timer_count: number
  order_intent_count: number
  fill_count: number
  starting_equity: number
  final_equity: number
  return_pct: number
  max_drawdown_pct: number
  portfolio: Record<string, unknown>
  intents: Array<Record<string, unknown>>
  equity_curve: Array<{ timestamp_ns: number; equity: number }>
}

export interface ArbitrageScanRequest {
  dataset_id: string
  min_edge_bps: number
  fee_bps: number
  max_quantity: number
  limit: number
}

export interface ArbitrageOpportunity {
  opportunity_id: string
  timestamp_ns: number
  source_event_checksum: string
  symbol: string
  buy_exchange: string
  sell_exchange: string
  buy_price: number
  sell_price: number
  quantity: number
  gross_edge_bps: number
  fee_cost_bps: number
  expected_edge_bps: number
  estimated_profit: number
  decision: ArbitrageDecision
  rejection_reasons: string[]
  explanation: string
}

export interface ArbitrageScanResponse {
  dataset_id: string
  strategy: 'cross_exchange_arbitrage'
  event_count: number
  candidate_count: number
  accepted_count: number
  rejected_count: number
  parameters: Omit<ArbitrageScanRequest, 'dataset_id' | 'limit'>
  opportunities: ArbitrageOpportunity[]
  safety: {
    environment: 'simulation'
    order_submission: false
    message: string
  }
}

export interface MonteCarloSummary {
  p05: number
  median: number
  p95: number
  loss_probability: number
}

export interface ExperimentCandidate {
  parameters: Record<string, unknown>
  score: number
  folds: Array<Record<string, number>>
  monte_carlo: MonteCarloSummary
}

export interface ExperimentResult {
  dataset_id: string
  strategy: string
  candidate_count: number
  best: ExperimentCandidate | null
  candidates: ExperimentCandidate[]
}

export interface ExperimentConfig {
  dataset_id: string
  strategy: EventStrategyName
  starting_cash: number
  timer_interval_ms: number
  base_parameters: Record<string, unknown>
  parameter_grid: Record<string, unknown[]>
  walk_forward_folds: number
  monte_carlo_runs: number
  monte_carlo_block_size: number
  seed: number
}

export interface ExperimentView {
  id: string
  status: 'queued' | 'running' | 'completed' | 'failed' | string
  config: ExperimentConfig
  result: ExperimentResult | null
  error: string | null
  created_at: string
  updated_at: string
  job_id?: string
}

export interface ExecutionStoryRequest {
  snapshot: {
    exchange: string
    symbol: string
    timestamp_ms: number
    sequence: number
    bids: number[][]
    asks: number[][]
    environment: string
  }
  side: 'buy' | 'sell'
  quantity: number
  limit_price: number | null
  mode: StoryMode
  intent: string
  hypothesis: string
  assumptions: string[]
  invalidation_conditions: string[]
  hopes: string[]
  risks: string[]
}

export interface ExecutionStoryResponse {
  execution: {
    requested_quantity: number
    filled_quantity: number
    remaining_quantity: number
    average_price: number | null
    status: string
    fills: Array<{ price: number; quantity: number; notional: number }>
  }
  story: {
    title: string
    intent: string
    hypothesis: string
    mode: StoryMode
    summary: string
    evidence: Array<{ kind: string; label: string; value: string; explanation?: string | null }>
    detailsCollapsed: boolean
    assumptions?: string[]
    invalidationConditions?: string[]
    hopes?: string[]
    risks?: string[]
    validationSteps?: Array<{ label: string; instruction: string; expected: string }>
    reflectionPrompt?: string
  }
}

export interface HistoryEntry {
  id: string
  kind: 'backtest' | 'arbitrage' | 'replay' | 'experiment' | 'story'
  title: string
  createdAt: string
  summary: string
  payload: unknown
}
