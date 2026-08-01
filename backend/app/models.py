from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ExchangeName(str, Enum):
    HYPERLIQUID = "hyperliquid"
    BYBIT = "bybit"
    BITMEX = "bitmex"
    WHITEBIT = "whitebit"
    SYNTHETIC = "synthetic"


class MarketKind(str, Enum):
    SPOT = "spot"
    PERP = "perp"
    FUTURE = "future"


class StrategyName(str, Enum):
    EMA_CROSSOVER = "ema_crossover"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class ScenarioName(str, Enum):
    BASELINE = "baseline"
    FLASH_CRASH = "flash_crash"
    VOLATILITY_SPIKE = "volatility_spike"
    LIQUIDITY_DROUGHT = "liquidity_drought"
    FUNDING_SQUEEZE = "funding_squeeze"


class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class MarketDataRequest(BaseModel):
    exchange: ExchangeName = ExchangeName.HYPERLIQUID
    symbol: str = "BTC"
    interval: str = "1h"
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = Field(default=1000, ge=100, le=5000)
    fallback_to_synthetic: bool = True


class StrategyConfig(BaseModel):
    name: StrategyName = StrategyName.EMA_CROSSOVER
    fast_period: int = Field(default=20, ge=2, le=300)
    slow_period: int = Field(default=50, ge=3, le=500)
    lookback: int = Field(default=20, ge=5, le=500)
    entry_z: float = Field(default=1.5, ge=0.25, le=5.0)
    exit_z: float = Field(default=0.25, ge=0.0, le=3.0)
    breakout_period: int = Field(default=30, ge=5, le=500)

    @model_validator(mode="after")
    def validate_periods(self) -> "StrategyConfig":
        if self.name == StrategyName.EMA_CROSSOVER and self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be lower than slow_period")
        if self.exit_z >= self.entry_z:
            raise ValueError("exit_z must be lower than entry_z")
        return self


class ExecutionConfig(BaseModel):
    order_type: OrderType = OrderType.MARKET
    allocation: float = Field(default=0.25, gt=0.0, le=1.0)
    leverage: float = Field(default=3.0, ge=1.0, le=50.0)
    taker_fee_bps: float = Field(default=5.0, ge=0.0, le=100.0)
    maker_fee_bps: float = Field(default=2.0, ge=-10.0, le=100.0)
    base_slippage_bps: float = Field(default=3.0, ge=0.0, le=500.0)
    limit_offset_bps: float = Field(default=2.0, ge=0.0, le=200.0)
    maintenance_margin_rate: float = Field(default=0.005, ge=0.001, le=0.25)
    stop_loss_pct: float | None = Field(default=0.04, gt=0.0, le=0.95)
    take_profit_pct: float | None = Field(default=0.08, gt=0.0, le=10.0)


class ScenarioConfig(BaseModel):
    name: ScenarioName = ScenarioName.BASELINE
    start_percent: float = Field(default=0.6, ge=0.05, le=0.95)
    duration_bars: int = Field(default=24, ge=1, le=500)
    shock_pct: float = Field(default=-0.12, ge=-0.95, le=0.95)
    volatility_multiplier: float = Field(default=3.0, ge=1.0, le=20.0)
    slippage_multiplier: float = Field(default=4.0, ge=1.0, le=50.0)
    funding_rate_hourly: float = Field(default=0.00001, ge=-0.01, le=0.01)


class BacktestRequest(BaseModel):
    market: MarketDataRequest = Field(default_factory=MarketDataRequest)
    market_kind: MarketKind = MarketKind.PERP
    starting_capital: float = Field(default=100_000.0, ge=100.0, le=1_000_000_000.0)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    scenario: ScenarioConfig = Field(default_factory=ScenarioConfig)

    @model_validator(mode="after")
    def normalize_spot(self) -> "BacktestRequest":
        if self.market_kind == MarketKind.SPOT and self.execution.leverage != 1.0:
            self.execution.leverage = 1.0
        return self


class EquityPoint(BaseModel):
    timestamp: datetime
    equity: float
    drawdown_pct: float
    close: float
    signal: int


class TradeRecord(BaseModel):
    id: int
    side: Literal["long", "short"]
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    notional: float
    gross_pnl: float
    fees: float
    funding: float
    net_pnl: float
    return_pct: float
    exit_reason: str
    mae_pct: float
    mfe_pct: float


class BacktestMetrics(BaseModel):
    starting_capital: float
    ending_equity: float
    net_profit: float
    total_return_pct: float
    annualized_return_pct: float
    annualized_volatility_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    average_gain: float
    average_loss: float
    profit_factor: float
    expectancy: float
    exposure_pct: float
    total_fees: float
    total_funding: float
    trade_count: int
    liquidation_count: int


class BacktestResponse(BaseModel):
    run_id: str
    source: str
    warnings: list[str]
    market: MarketDataRequest
    market_kind: MarketKind
    strategy: StrategyConfig
    execution: ExecutionConfig
    scenario: ScenarioConfig
    metrics: BacktestMetrics
    equity_curve: list[EquityPoint]
    trades: list[TradeRecord]
