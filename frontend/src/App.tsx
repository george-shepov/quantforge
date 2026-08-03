import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  addExecutionReflection,
  buildExecutionStory,
  getCapabilities,
  getCatalog,
  getExecutionSafety,
  getExperiment,
  listDatasets,
  listExperiments,
  listRecordings,
  queueExperiment,
  replayDataset,
  runBacktest,
  runCourse,
  startRecording,
  stopRecording,
} from "./api";
import { MetricGrid } from "./components/MetricGrid";
import { PerformanceChart } from "./components/PerformanceChart";
import { TradesTable } from "./components/TradesTable";
import { ArbitrageWorkspace } from "./components/ArbitrageWorkspace";
import type {
  BacktestResponse,
  CatalogResponse,
  CourseRunResponse,
  DatasetManifest,
  EventStrategyName,
  ExecutionStoryRequest,
  ExecutionStoryResponse,
  ExperimentConfig,
  ExperimentView,
  HistoryEntry,
  RecordingConfig,
  RecordingStatus,
  ReplayRequest,
  ReplayResponse,
  ResearchCapabilities,
  RunConfig,
  SafetyStatus,
  ScenarioName,
  StoryMode,
  StrategyName,
  WorkspaceName,
} from "./types";
import "./research.css";

const HISTORY_KEY = "quantforge:history:v1";

const initialConfig: RunConfig = {
  market: {
    exchange: "hyperliquid",
    symbol: "BTC",
    interval: "1h",
    limit: 1000,
    fallback_to_synthetic: true,
  },
  market_kind: "perp",
  starting_capital: 100_000,
  strategy: {
    name: "ema_crossover",
    fast_period: 20,
    slow_period: 50,
    lookback: 20,
    entry_z: 1.5,
    exit_z: 0.25,
    breakout_period: 30,
  },
  execution: {
    order_type: "market",
    allocation: 0.25,
    leverage: 3,
    taker_fee_bps: 5,
    maker_fee_bps: 2,
    base_slippage_bps: 3,
    limit_offset_bps: 2,
    maintenance_margin_rate: 0.005,
    stop_loss_pct: 0.04,
    take_profit_pct: 0.08,
  },
  scenario: {
    name: "baseline",
    start_percent: 0.6,
    duration_bars: 24,
    shock_pct: -0.12,
    volatility_multiplier: 3,
    slippage_multiplier: 4,
    funding_rate_hourly: 0.00001,
  },
};

const defaultStoryRequest: ExecutionStoryRequest = {
  snapshot: {
    exchange: "bybit",
    symbol: "BTC",
    timestamp_ms: Date.now(),
    sequence: 1,
    environment: "simulation",
    bids: [
      [100000, 0.4],
      [99990, 0.8],
      [99970, 1.2],
    ],
    asks: [
      [100010, 0.3],
      [100020, 0.5],
      [100050, 1.5],
    ],
  },
  side: "buy",
  quantity: 1,
  limit_price: null,
  fee_bps: 0,
  mode: "guided",
  intent: "Learn how available order-book depth changes the actual fill.",
  hypothesis:
    "The order should fill completely with limited book-walking slippage.",
  assumptions: [
    "The snapshot is fresh",
    "Fees and latency are evaluated separately",
  ],
  invalidation_conditions: [
    "The market moves before the order reaches the venue",
  ],
  hopes: ["The strategy remains viable after realistic execution costs"],
  risks: ["A partial fill can leave residual directional exposure"],
};

const tabs: Array<[WorkspaceName, string]> = [
  ["backtest", "Backtest"],
  ["arbitrage", "Arbitrage"],
  ["recordings", "Record"],
  ["replay", "Replay"],
  ["experiments", "Experiments"],
  ["manual", "Trading manual"],
  ["system", "System"],
  ["history", "History"],
];

export default function App() {
  const [workspace, setWorkspace] = useState<WorkspaceName>("backtest");
  const [catalog, setCatalog] = useState<CatalogResponse | null>(null);
  const [capabilities, setCapabilities] = useState<ResearchCapabilities | null>(
    null,
  );
  const [safety, setSafety] = useState<SafetyStatus | null>(null);
  const [datasets, setDatasets] = useState<DatasetManifest[]>([]);
  const [recordings, setRecordings] = useState<RecordingStatus[]>([]);
  const [experiments, setExperiments] = useState<ExperimentView[]>([]);
  const [history, setHistory] = useState<HistoryEntry[]>(() => loadHistory());
  const [systemError, setSystemError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  async function refreshPlatform() {
    setRefreshing(true);
    setSystemError("");
    const results = await Promise.allSettled([
      getCatalog(),
      getCapabilities(),
      getExecutionSafety(),
      listDatasets(),
      listRecordings(),
      listExperiments(),
    ]);
    const [
      catalogResult,
      capabilityResult,
      safetyResult,
      datasetResult,
      recordingResult,
      experimentResult,
    ] = results;
    if (catalogResult.status === "fulfilled") setCatalog(catalogResult.value);
    if (capabilityResult.status === "fulfilled")
      setCapabilities(capabilityResult.value);
    if (safetyResult.status === "fulfilled") setSafety(safetyResult.value);
    if (datasetResult.status === "fulfilled") setDatasets(datasetResult.value);
    if (recordingResult.status === "fulfilled")
      setRecordings(recordingResult.value);
    if (experimentResult.status === "fulfilled")
      setExperiments(experimentResult.value);
    const failures = results.filter(
      (item): item is PromiseRejectedResult => item.status === "rejected",
    );
    if (failures.length)
      setSystemError(
        failures
          .map((item) =>
            item.reason instanceof Error
              ? item.reason.message
              : String(item.reason),
          )
          .join(" · "),
      );
    setRefreshing(false);
  }

  useEffect(() => {
    void refreshPlatform();
  }, []);
  useEffect(() => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, 40)));
  }, [history]);

  function remember(entry: Omit<HistoryEntry, "id" | "createdAt">) {
    setHistory((current) =>
      [
        {
          ...entry,
          id: crypto.randomUUID(),
          createdAt: new Date().toISOString(),
        },
        ...current,
      ].slice(0, 40),
    );
  }

  const safetyLabel = useMemo(() => {
    if (!safety) return "SAFETY UNKNOWN";
    const enabled = Boolean(safety.enabled);
    return enabled
      ? `TESTNET EXECUTION ENABLED · ${String(safety.network ?? "testnet").toUpperCase()}`
      : "EXECUTION DISABLED";
  }, [safety]);

  return (
    <main className="app-shell research-shell">
      <header className="topbar research-topbar">
        <div className="brand">
          <strong>QUANTFORGE</strong>
          <span>CRYPTO RESEARCH PLATFORM</span>
        </div>
        <div className="topbar-actions">
          <span
            className={`safety-pill ${Boolean(safety?.enabled) ? "warning-pill" : "safe-pill"}`}
          >
            {safetyLabel}
          </span>
          <button
            className="ghost-button compact"
            onClick={() => void refreshPlatform()}
            disabled={refreshing}
          >
            {refreshing ? "SYNCING…" : "SYNC"}
          </button>
        </div>
      </header>

      <nav className="workspace-tabs" aria-label="QuantForge workspaces">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            className={workspace === key ? "active" : ""}
            onClick={() => setWorkspace(key)}
          >
            {label}
          </button>
        ))}
      </nav>

      {systemError && (
        <div className="global-alert">
          Some platform services did not load: {systemError}
        </div>
      )}

      <section className="platform-strip" aria-label="Exchange environments">
        {catalog ? (
          Object.entries(catalog.exchangeEnvironments).map(
            ([exchange, environment]) => (
              <span
                className="environment-badge"
                key={exchange}
                title={environment.badge}
              >
                <b>{exchange}</b>
                <i className={environment.executionAllowed ? "online" : ""} />
                {environment.environment}
              </span>
            ),
          )
        ) : (
          <span className="muted">Loading exchange catalog…</span>
        )}
      </section>

      {workspace === "backtest" && (
        <BacktestWorkspace catalog={catalog} remember={remember} />
      )}
      {workspace === "arbitrage" && (
        <ArbitrageWorkspace
          datasets={datasets}
          remember={remember}
          onChanged={refreshPlatform}
        />
      )}
      {workspace === "recordings" && (
        <RecordingWorkspace
          recordings={recordings}
          datasets={datasets}
          onChanged={refreshPlatform}
        />
      )}
      {workspace === "replay" && (
        <ReplayWorkspace datasets={datasets} remember={remember} />
      )}
      {workspace === "experiments" && (
        <ExperimentWorkspace
          datasets={datasets}
          experiments={experiments}
          onChanged={refreshPlatform}
          remember={remember}
        />
      )}
      {workspace === "manual" && <ManualWorkspace remember={remember} />}
      {workspace === "system" && (
        <SystemWorkspace
          catalog={catalog}
          capabilities={capabilities}
          safety={safety}
        />
      )}
      {workspace === "history" && (
        <HistoryWorkspace history={history} onClear={() => setHistory([])} />
      )}
    </main>
  );
}

function BacktestWorkspace({
  catalog,
  remember,
}: {
  catalog: CatalogResponse | null;
  remember: (entry: Omit<HistoryEntry, "id" | "createdAt">) => void;
}) {
  const [config, setConfig] = useState<RunConfig>(initialConfig);
  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const resultsRef = useRef<HTMLElement | null>(null);

  function patch<T extends keyof RunConfig>(section: T, value: RunConfig[T]) {
    setConfig((current) => ({ ...current, [section]: value }));
  }
  async function execute() {
    setLoading(true);
    setError("");
    try {
      const output = await runBacktest(config);
      setResult(output);
      remember({
        kind: "backtest",
        title: `${config.market.exchange} ${config.market.symbol} · ${config.strategy.name}`,
        summary: `${output.metrics.total_return_pct?.toFixed(2) ?? "0.00"}% return · ${output.metrics.trade_count ?? 0} trades`,
        payload: { config, output },
      });
      requestAnimationFrame(() =>
        resultsRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        }),
      );
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setLoading(false);
    }
  }

  const exchanges = catalog?.exchanges ?? [
    "hyperliquid",
    "bybit",
    "bitmex",
    "whitebit",
    "synthetic",
  ];
  const symbols = catalog?.symbols ?? ["BTC", "ETH", "SOL", "HYPE"];
  const intervals = catalog?.intervals ?? ["1m", "5m", "15m", "1h", "4h", "1d"];

  return (
    <div className="workspace research-workspace">
      <aside className="controls">
        <div className="panel-title">
          <span>CANDLE BACKTEST</span>
          <span>SIMULATION ONLY</span>
        </div>
        <button
          className="run backtest-run"
          onClick={() => void execute()}
          disabled={loading}
        >
          {loading ? "RUNNING…" : "RUN BACKTEST"}
        </button>
        {error && <div className="error">{error}</div>}
        <section className="control-group">
          <div className="control-group-title">Market data</div>
          <Field label="Exchange">
            <select
              value={config.market.exchange}
              onChange={(e) =>
                patch("market", {
                  ...config.market,
                  exchange: e.target.value as RunConfig["market"]["exchange"],
                })
              }
            >
              {exchanges.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </Field>
          <div className="field-row">
            <Field label="Symbol">
              <select
                value={config.market.symbol}
                onChange={(e) =>
                  patch("market", { ...config.market, symbol: e.target.value })
                }
              >
                {symbols.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </Field>
            <Field label="Interval">
              <select
                value={config.market.interval}
                onChange={(e) =>
                  patch("market", {
                    ...config.market,
                    interval: e.target.value,
                  })
                }
              >
                {intervals.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </Field>
          </div>
          <div className="field-row">
            <Field label="Market">
              <select
                value={config.market_kind}
                onChange={(e) =>
                  patch(
                    "market_kind",
                    e.target.value as RunConfig["market_kind"],
                  )
                }
              >
                <option value="spot">Spot</option>
                <option value="perp">Perpetual</option>
                <option value="future">Future</option>
              </select>
            </Field>
            <NumberField
              label="Bars"
              value={config.market.limit}
              onChange={(v) => patch("market", { ...config.market, limit: v })}
            />
          </div>
        </section>
        <section className="control-group">
          <div className="control-group-title">Strategy</div>
          <Field label="Model">
            <select
              value={config.strategy.name}
              onChange={(e) =>
                patch("strategy", {
                  ...config.strategy,
                  name: e.target.value as StrategyName,
                })
              }
            >
              <option value="ema_crossover">EMA crossover</option>
              <option value="mean_reversion">Mean reversion</option>
              <option value="breakout">Breakout</option>
            </select>
          </Field>
          {config.strategy.name === "ema_crossover" && (
            <div className="field-row">
              <NumberField
                label="Fast EMA"
                value={config.strategy.fast_period}
                onChange={(v) =>
                  patch("strategy", { ...config.strategy, fast_period: v })
                }
              />
              <NumberField
                label="Slow EMA"
                value={config.strategy.slow_period}
                onChange={(v) =>
                  patch("strategy", { ...config.strategy, slow_period: v })
                }
              />
            </div>
          )}
          {config.strategy.name === "mean_reversion" && (
            <div className="field-row">
              <NumberField
                label="Lookback"
                value={config.strategy.lookback}
                onChange={(v) =>
                  patch("strategy", { ...config.strategy, lookback: v })
                }
              />
              <NumberField
                label="Entry Z"
                value={config.strategy.entry_z}
                step="0.1"
                onChange={(v) =>
                  patch("strategy", { ...config.strategy, entry_z: v })
                }
              />
            </div>
          )}
          {config.strategy.name === "breakout" && (
            <NumberField
              label="Breakout period"
              value={config.strategy.breakout_period}
              onChange={(v) =>
                patch("strategy", { ...config.strategy, breakout_period: v })
              }
            />
          )}
        </section>
        <section className="control-group">
          <div className="control-group-title">Execution model</div>
          <div className="field-row">
            <NumberField
              label="Allocation %"
              value={config.execution.allocation * 100}
              onChange={(v) =>
                patch("execution", { ...config.execution, allocation: v / 100 })
              }
            />
            <NumberField
              label="Leverage"
              value={
                config.market_kind === "spot" ? 1 : config.execution.leverage
              }
              disabled={config.market_kind === "spot"}
              onChange={(v) =>
                patch("execution", { ...config.execution, leverage: v })
              }
            />
          </div>
          <div className="field-row">
            <NumberField
              label="Fee bps"
              value={config.execution.taker_fee_bps}
              step="0.1"
              onChange={(v) =>
                patch("execution", { ...config.execution, taker_fee_bps: v })
              }
            />
            <NumberField
              label="Slippage bps"
              value={config.execution.base_slippage_bps}
              step="0.1"
              onChange={(v) =>
                patch("execution", {
                  ...config.execution,
                  base_slippage_bps: v,
                })
              }
            />
          </div>
        </section>
        <section className="control-group">
          <div className="control-group-title">Stress test</div>
          <Field label="Scenario">
            <select
              value={config.scenario.name}
              onChange={(e) =>
                patch("scenario", {
                  ...config.scenario,
                  name: e.target.value as ScenarioName,
                })
              }
            >
              <option value="baseline">Baseline</option>
              <option value="flash_crash">Flash crash</option>
              <option value="volatility_spike">Volatility spike</option>
              <option value="liquidity_drought">Liquidity drought</option>
              <option value="funding_squeeze">Funding squeeze</option>
            </select>
          </Field>
        </section>
      </aside>
      <section className="results" ref={resultsRef}>
        {result ? (
          <>
            {result.warnings.length > 0 && (
              <div className="warnings">
                {result.warnings.map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
            )}
            <MetricGrid metrics={result.metrics} />
            <PerformanceChart data={result.equity_curve} />
            <TradesTable trades={result.trades} />
          </>
        ) : (
          <Empty title="NO BACKTEST YET">
            Configure the market, strategy, execution assumptions, and stress
            scenario.
          </Empty>
        )}
      </section>
    </div>
  );
}

function RecordingWorkspace({
  recordings,
  datasets,
  onChanged,
}: {
  recordings: RecordingStatus[];
  datasets: DatasetManifest[];
  onChanged: () => Promise<void>;
}) {
  const [symbols, setSymbols] = useState("BTC, ETH");
  const [network, setNetwork] = useState<"mainnet" | "testnet">("mainnet");
  const [flushSize, setFlushSize] = useState(2000);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  async function start() {
    setBusy("start");
    setError("");
    const config: RecordingConfig = {
      symbols: symbols
        .split(",")
        .map((item) => item.trim().toUpperCase())
        .filter(Boolean),
      network,
      flush_size: flushSize,
      flush_interval_seconds: 5,
      reconnect_max_seconds: 30,
    };
    try {
      await startRecording(config);
      await onChanged();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy("");
    }
  }
  async function stop(id: string) {
    setBusy(id);
    setError("");
    try {
      await stopRecording(id);
      await onChanged();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy("");
    }
  }
  return (
    <div className="page-workspace two-column-page">
      <section className="surface-card sticky-card">
        <div className="section-heading">
          <div>
            <span>MARKET DATA</span>
            <h2>Recording manager</h2>
          </div>
          <strong>{recordings.length} ACTIVE</strong>
        </div>
        <Field label="Symbols">
          <input
            value={symbols}
            onChange={(e) => setSymbols(e.target.value)}
            placeholder="BTC, ETH"
          />
        </Field>
        <div className="field-row">
          <Field label="Network">
            <select
              value={network}
              onChange={(e) =>
                setNetwork(e.target.value as "mainnet" | "testnet")
              }
            >
              <option value="mainnet">Mainnet read-only</option>
              <option value="testnet">Testnet</option>
            </select>
          </Field>
          <NumberField
            label="Flush size"
            value={flushSize}
            onChange={setFlushSize}
          />
        </div>
        <button
          className="run"
          onClick={() => void start()}
          disabled={Boolean(busy)}
        >
          {busy === "start" ? "STARTING…" : "START RECORDING"}
        </button>
        <p className="safety">
          Public market data only. Starting a recorder creates a persistent
          Parquet dataset.
        </p>
        {error && <div className="error">{error}</div>}
        <div className="stack-list">
          {recordings.map((recording) => (
            <article className="status-card" key={recording.dataset_id}>
              <div>
                <b>{recording.symbols.join(" · ")}</b>
                <span>
                  {recording.network} ·{" "}
                  {recording.connected ? "connected" : "connecting"}
                </span>
              </div>
              <strong>
                {recording.events_recorded.toLocaleString()} events
              </strong>
              <button
                className="danger-button"
                onClick={() => void stop(recording.dataset_id)}
                disabled={busy === recording.dataset_id}
              >
                {busy === recording.dataset_id ? "STOPPING…" : "STOP"}
              </button>
              {recording.last_error && <p>{recording.last_error}</p>}
            </article>
          ))}
        </div>
      </section>
      <DatasetCatalog datasets={datasets} />
    </div>
  );
}

function DatasetCatalog({ datasets }: { datasets: DatasetManifest[] }) {
  return (
    <section className="surface-card">
      <div className="section-heading">
        <div>
          <span>PARQUET CATALOG</span>
          <h2>Recorded datasets</h2>
        </div>
        <strong>{datasets.length} DATASETS</strong>
      </div>
      {datasets.length === 0 ? (
        <Empty title="NO DATASETS">
          Start a recorder to create deterministic replay data.
        </Empty>
      ) : (
        <div className="dataset-grid">
          {datasets.map((dataset) => (
            <article className="dataset-card" key={dataset.dataset_id}>
              <div className="dataset-title">
                <b>{dataset.dataset_id}</b>
                <span>{formatDate(dataset.created_at)}</span>
              </div>
              <div className="mini-metrics">
                <span>
                  <small>Events</small>
                  {dataset.event_count.toLocaleString()}
                </span>
                <span>
                  <small>Parts</small>
                  {dataset.parts.length}
                </span>
                <span>
                  <small>Symbols</small>
                  {dataset.symbols.join(", ") || "—"}
                </span>
                <span>
                  <small>Kinds</small>
                  {dataset.kinds.join(", ") || "—"}
                </span>
              </div>
              <code>{dataset.chain_hash.slice(0, 24)}…</code>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function ReplayWorkspace({
  datasets,
  remember,
}: {
  datasets: DatasetManifest[];
  remember: (entry: Omit<HistoryEntry, "id" | "createdAt">) => void;
}) {
  const [request, setRequest] = useState<ReplayRequest>({
    dataset_id: datasets[0]?.dataset_id ?? "",
    strategy: "inventory_market_making",
    parameters: { spread_bps: 8, inventory_skew_bps: 3, quantity: 0.01 },
    starting_cash: 100000,
    timer_interval_ms: 1000,
  });
  const [parameters, setParameters] = useState(
    JSON.stringify(request.parameters, null, 2),
  );
  const [result, setResult] = useState<ReplayResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!request.dataset_id && datasets[0])
      setRequest((current) => ({
        ...current,
        dataset_id: datasets[0].dataset_id,
      }));
  }, [datasets, request.dataset_id]);
  async function run() {
    setLoading(true);
    setError("");
    try {
      const config = {
        ...request,
        parameters: parseObject(parameters, "Strategy parameters"),
      };
      const output = await replayDataset(config);
      setResult(output);
      remember({
        kind: "replay",
        title: `${output.strategy} · ${request.dataset_id}`,
        summary: `${output.return_pct.toFixed(2)}% return · ${output.fill_count} fills`,
        payload: { config, output },
      });
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setLoading(false);
    }
  }
  return (
    <div className="page-workspace two-column-page">
      <section className="surface-card sticky-card">
        <div className="section-heading">
          <div>
            <span>DETERMINISTIC REPLAY</span>
            <h2>Replay workspace</h2>
          </div>
          <strong>{datasets.length} DATASETS</strong>
        </div>
        <DatasetSelect
          datasets={datasets}
          value={request.dataset_id}
          onChange={(dataset_id) => setRequest({ ...request, dataset_id })}
        />
        <Field label="Strategy">
          <select
            value={request.strategy}
            onChange={(e) =>
              setRequest({
                ...request,
                strategy: e.target.value as EventStrategyName,
              })
            }
          >
            <option value="inventory_market_making">
              Inventory market making
            </option>
            <option value="cross_exchange_arbitrage">
              Cross-exchange arbitrage
            </option>
          </select>
        </Field>
        <Field label="Parameters JSON">
          <textarea
            value={parameters}
            onChange={(e) => setParameters(e.target.value)}
            rows={9}
          />
        </Field>
        <div className="field-row">
          <NumberField
            label="Starting cash"
            value={request.starting_cash}
            onChange={(starting_cash) =>
              setRequest({ ...request, starting_cash })
            }
          />
          <NumberField
            label="Timer ms"
            value={request.timer_interval_ms}
            onChange={(timer_interval_ms) =>
              setRequest({ ...request, timer_interval_ms })
            }
          />
        </div>
        <button
          className="run"
          disabled={loading || !request.dataset_id}
          onClick={() => void run()}
        >
          {loading ? "REPLAYING…" : "RUN REPLAY"}
        </button>
        {error && <div className="error">{error}</div>}
      </section>
      <section className="surface-card">
        {result ? (
          <ReplayResults result={result} />
        ) : (
          <Empty title="NO REPLAY YET">
            Choose a recorded dataset and event strategy.
          </Empty>
        )}
      </section>
    </div>
  );
}

function ReplayResults({ result }: { result: ReplayResponse }) {
  const chart = result.equity_curve.map((point) => ({
    ...point,
    label: new Date(point.timestamp_ns / 1_000_000).toLocaleTimeString(),
  }));
  return (
    <>
      <div className="section-heading">
        <div>
          <span>REPLAY RESULT</span>
          <h2>{result.strategy.replaceAll("_", " ")}</h2>
        </div>
        <strong className={result.return_pct >= 0 ? "positive" : "negative"}>
          {result.return_pct.toFixed(2)}%
        </strong>
      </div>
      <div className="research-metric-grid">
        <Metric label="Final equity" value={money(result.final_equity)} />
        <Metric
          label="Max drawdown"
          value={`${result.max_drawdown_pct.toFixed(2)}%`}
        />
        <Metric label="Events" value={result.event_count.toLocaleString()} />
        <Metric label="Timers" value={result.timer_count.toLocaleString()} />
        <Metric
          label="Intents"
          value={result.order_intent_count.toLocaleString()}
        />
        <Metric label="Fills" value={result.fill_count.toLocaleString()} />
      </div>
      <div className="chart-shell">
        <div className="panel-title">
          <span>REPLAY EQUITY</span>
          <span>{chart.length} POINTS</span>
        </div>
        <div className="chart-canvas">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chart}>
              <CartesianGrid strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="label" minTickGap={50} />
              <YAxis width={56} domain={["auto", "auto"]} />
              <Tooltip />
              <Area
                type="monotone"
                dataKey="equity"
                fill="currentColor"
                fillOpacity={0.12}
                stroke="currentColor"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
      <details className="json-details">
        <summary>Portfolio and execution intents</summary>
        <pre>
          {JSON.stringify(
            { portfolio: result.portfolio, intents: result.intents },
            null,
            2,
          )}
        </pre>
      </details>
    </>
  );
}

function ExperimentWorkspace({
  datasets,
  experiments,
  onChanged,
  remember,
}: {
  datasets: DatasetManifest[];
  experiments: ExperimentView[];
  onChanged: () => Promise<void>;
  remember: (entry: Omit<HistoryEntry, "id" | "createdAt">) => void;
}) {
  const [config, setConfig] = useState<ExperimentConfig>({
    dataset_id: datasets[0]?.dataset_id ?? "",
    strategy: "cross_exchange_arbitrage",
    starting_cash: 100000,
    timer_interval_ms: 1000,
    base_parameters: { fee_bps: 2 },
    parameter_grid: { min_edge_bps: [3, 5, 8], max_quantity: [0.1, 0.25] },
    walk_forward_folds: 4,
    monte_carlo_runs: 500,
    monte_carlo_block_size: 5,
    seed: 7,
  });
  const [baseText, setBaseText] = useState(
    JSON.stringify(config.base_parameters, null, 2),
  );
  const [gridText, setGridText] = useState(
    JSON.stringify(config.parameter_grid, null, 2),
  );
  const [selected, setSelected] = useState<ExperimentView | null>(
    experiments[0] ?? null,
  );
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (!config.dataset_id && datasets[0])
      setConfig((current) => ({
        ...current,
        dataset_id: datasets[0].dataset_id,
      }));
  }, [datasets, config.dataset_id]);
  useEffect(() => {
    if (!selected && experiments[0]) setSelected(experiments[0]);
  }, [experiments, selected]);
  async function queue() {
    setBusy("queue");
    setError("");
    try {
      const request = {
        ...config,
        base_parameters: parseObject(baseText, "Base parameters"),
        parameter_grid: parseGrid(gridText),
      };
      const output = await queueExperiment(request);
      setSelected(output);
      remember({
        kind: "experiment",
        title: `${request.strategy} experiment`,
        summary: `${Object.values(request.parameter_grid).reduce((total, values) => total * values.length, 1)} candidates queued`,
        payload: output,
      });
      await onChanged();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy("");
    }
  }
  async function refreshOne(id: string) {
    setBusy(id);
    setError("");
    try {
      const output = await getExperiment(id);
      setSelected(output);
      await onChanged();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy("");
    }
  }
  return (
    <div className="page-workspace experiment-layout">
      <section className="surface-card sticky-card">
        <div className="section-heading">
          <div>
            <span>PARAMETER LAB</span>
            <h2>Queue experiment</h2>
          </div>
          <strong>RQ WORKER</strong>
        </div>
        <DatasetSelect
          datasets={datasets}
          value={config.dataset_id}
          onChange={(dataset_id) => setConfig({ ...config, dataset_id })}
        />
        <Field label="Strategy">
          <select
            value={config.strategy}
            onChange={(e) =>
              setConfig({
                ...config,
                strategy: e.target.value as EventStrategyName,
              })
            }
          >
            <option value="cross_exchange_arbitrage">
              Cross-exchange arbitrage
            </option>
            <option value="inventory_market_making">
              Inventory market making
            </option>
          </select>
        </Field>
        <Field label="Base parameters">
          <textarea
            rows={5}
            value={baseText}
            onChange={(e) => setBaseText(e.target.value)}
          />
        </Field>
        <Field label="Parameter grid">
          <textarea
            rows={7}
            value={gridText}
            onChange={(e) => setGridText(e.target.value)}
          />
        </Field>
        <div className="field-row">
          <NumberField
            label="Walk-forward folds"
            value={config.walk_forward_folds}
            onChange={(walk_forward_folds) =>
              setConfig({ ...config, walk_forward_folds })
            }
          />
          <NumberField
            label="Monte Carlo runs"
            value={config.monte_carlo_runs}
            onChange={(monte_carlo_runs) =>
              setConfig({ ...config, monte_carlo_runs })
            }
          />
        </div>
        <button
          className="run"
          disabled={busy === "queue" || !config.dataset_id}
          onClick={() => void queue()}
        >
          {busy === "queue" ? "QUEUEING…" : "QUEUE EXPERIMENT"}
        </button>
        {error && <div className="error">{error}</div>}
      </section>
      <section className="surface-card">
        <div className="section-heading">
          <div>
            <span>EXPERIMENT QUEUE</span>
            <h2>Runs and results</h2>
          </div>
          <strong>{experiments.length} RUNS</strong>
        </div>
        <div className="experiment-list">
          {experiments.map((experiment) => (
            <button
              key={experiment.id}
              className={`experiment-row ${selected?.id === experiment.id ? "selected" : ""}`}
              onClick={() => setSelected(experiment)}
            >
              <span>
                <b>{experiment.config.strategy.replaceAll("_", " ")}</b>
                <small>{formatDate(experiment.created_at)}</small>
              </span>
              <strong className={`status-${experiment.status}`}>
                {experiment.status}
              </strong>
            </button>
          ))}
        </div>
        {selected ? (
          <ExperimentDetail
            experiment={selected}
            busy={busy === selected.id}
            onRefresh={() => void refreshOne(selected.id)}
          />
        ) : (
          <Empty title="NO EXPERIMENT SELECTED">
            Queue an experiment or select a prior run.
          </Empty>
        )}
      </section>
    </div>
  );
}

function ExperimentDetail({
  experiment,
  busy,
  onRefresh,
}: {
  experiment: ExperimentView;
  busy: boolean;
  onRefresh: () => void;
}) {
  const best = experiment.result?.best;
  const distribution = best
    ? [
        { name: "P05", value: best.monte_carlo.p05 * 100 },
        { name: "Median", value: best.monte_carlo.median * 100 },
        { name: "P95", value: best.monte_carlo.p95 * 100 },
      ]
    : [];
  return (
    <div className="experiment-detail">
      <div className="detail-toolbar">
        <code>{experiment.id}</code>
        <button className="ghost-button" onClick={onRefresh} disabled={busy}>
          {busy ? "REFRESHING…" : "REFRESH STATUS"}
        </button>
      </div>
      {experiment.error && <div className="error">{experiment.error}</div>}
      {best ? (
        <>
          <div className="research-metric-grid">
            <Metric
              label="Candidates"
              value={String(experiment.result?.candidate_count ?? 0)}
            />
            <Metric
              label="Best mean return"
              value={`${(best.score * 100).toFixed(2)}%`}
            />
            <Metric
              label="Loss probability"
              value={`${(best.monte_carlo.loss_probability * 100).toFixed(1)}%`}
            />
            <Metric label="Folds" value={String(best.folds.length)} />
          </div>
          <div className="chart-shell">
            <div className="panel-title">
              <span>MONTE CARLO DISTRIBUTION</span>
              <span>BEST CANDIDATE</span>
            </div>
            <div className="chart-canvas short-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={distribution}>
                  <CartesianGrid strokeDasharray="2 4" vertical={false} />
                  <XAxis dataKey="name" />
                  <YAxis tickFormatter={(value) => `${value}%`} />
                  <Tooltip
                    formatter={(value) => `${Number(value).toFixed(2)}%`}
                  />
                  <Bar dataKey="value" fill="currentColor" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          <details className="json-details" open>
            <summary>Best parameters and walk-forward folds</summary>
            <pre>
              {JSON.stringify(
                {
                  parameters: best.parameters,
                  folds: best.folds,
                  monte_carlo: best.monte_carlo,
                },
                null,
                2,
              )}
            </pre>
          </details>
        </>
      ) : (
        <Empty title={experiment.status.toUpperCase()}>
          {experiment.status === "failed"
            ? (experiment.error ?? "Experiment failed.")
            : "The worker has not produced a result yet."}
        </Empty>
      )}
    </div>
  );
}

function ManualWorkspace({
  remember,
}: {
  remember: (entry: Omit<HistoryEntry, "id" | "createdAt">) => void;
}) {
  const [mode, setMode] = useState<StoryMode>(() => loadStoryMode());
  const [request, setRequest] = useState({ ...defaultStoryRequest, mode });
  const [bookText, setBookText] = useState(
    JSON.stringify(defaultStoryRequest.snapshot, null, 2),
  );
  const [result, setResult] = useState<ExecutionStoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [reflection, setReflection] = useState("");
  const [reflectionStatus, setReflectionStatus] = useState("");
  const [courseResult, setCourseResult] = useState<CourseRunResponse | null>(
    null,
  );
  const [courseLoading, setCourseLoading] = useState(false);
  useEffect(() => {
    localStorage.setItem("quantforge:story-mode:v1", mode);
    setRequest((current) => ({ ...current, mode }));
  }, [mode]);
  async function explain() {
    setLoading(true);
    setError("");
    try {
      const snapshot = parseObject(
        bookText,
        "Order-book snapshot",
      ) as ExecutionStoryRequest["snapshot"];
      const output = await buildExecutionStory({ ...request, snapshot });
      setResult(output);
      setReflection("");
      setReflectionStatus("");
      remember({
        kind: "story",
        title: output.story.title,
        summary: output.story.summary,
        payload: output,
      });
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setLoading(false);
    }
  }
  async function executeCourse() {
    setCourseLoading(true);
    setError("");
    try {
      const output = await runCourse();
      setCourseResult(output);
      remember({
        kind: "experiment",
        title: output.title,
        summary: `${output.labs.length} executable labs · ${output.verdict}`,
        payload: output,
      });
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setCourseLoading(false);
    }
  }
  async function appendReflection() {
    if (!result || !reflection.trim()) return;
    setLoading(true);
    setError("");
    setReflectionStatus("");
    try {
      const event = await addExecutionReflection(
        result.story_id,
        reflection.trim(),
      );
      setResult({
        ...result,
        reflections: [...(result.reflections ?? []), event],
      });
      setReflection("");
      setReflectionStatus(
        "Reflection appended without changing the original execution record.",
      );
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setLoading(false);
    }
  }
  return (
    <div className="page-workspace two-column-page">
      <section className="surface-card sticky-card">
        <div className="section-heading">
          <div>
            <span>EXECUTABLE COURSE MODULE</span>
            <h2>Can This Strategy Survive Reality?</h2>
          </div>
          <strong>82 MIN</strong>
        </div>
        <p className="safety">
          The manual is generated from the versioned scenario, deterministic
          fixture, and measured evidence—not handwritten result values.
        </p>
        <button
          className="run"
          onClick={() => void executeCourse()}
          disabled={courseLoading}
        >
          {courseLoading ? "RUNNING MODULE…" : "RUN STARTER MODULE"}
        </button>
        {courseResult && <CourseResultView result={courseResult} />}
        <div className="section-heading">
          <div>
            <span>EXECUTION STORY</span>
            <h2>Expected vs actual</h2>
          </div>
          <div className="mode-toggle">
            <button
              className={mode === "expert" ? "active" : ""}
              onClick={() => setMode("expert")}
            >
              Expert
            </button>
            <button
              className={mode === "guided" ? "active" : ""}
              onClick={() => setMode("guided")}
            >
              Guided
            </button>
          </div>
        </div>
        <Field label="Order-book snapshot JSON">
          <textarea
            rows={14}
            value={bookText}
            onChange={(e) => setBookText(e.target.value)}
          />
        </Field>
        <div className="field-row">
          <Field label="Side">
            <select
              value={request.side}
              onChange={(e) =>
                setRequest({
                  ...request,
                  side: e.target.value as "buy" | "sell",
                })
              }
            >
              <option value="buy">Buy</option>
              <option value="sell">Sell</option>
            </select>
          </Field>
          <NumberField
            label="Quantity"
            value={request.quantity}
            step="0.01"
            onChange={(quantity) => setRequest({ ...request, quantity })}
          />
        </div>
        <Field label="Limit price (blank = market)">
          <input
            type="number"
            value={request.limit_price ?? ""}
            onChange={(e) =>
              setRequest({
                ...request,
                limit_price: e.target.value ? Number(e.target.value) : null,
              })
            }
          />
        </Field>
        <Field label="Intent">
          <input
            value={request.intent}
            onChange={(e) => setRequest({ ...request, intent: e.target.value })}
          />
        </Field>
        <Field label="Hypothesis">
          <textarea
            rows={3}
            value={request.hypothesis}
            onChange={(e) =>
              setRequest({ ...request, hypothesis: e.target.value })
            }
          />
        </Field>
        <button
          className="run"
          onClick={() => void explain()}
          disabled={loading}
        >
          {loading ? "ANALYZING…" : "GENERATE EXECUTION STORY"}
        </button>
        {error && <div className="error">{error}</div>}
      </section>
      <section className="surface-card">
        {result ? (
          <>
            <StoryView result={result} />
            <section className="guided-sections">
              <h3>Post-run reflection</h3>
              <p>
                Append what happened after reviewing the immutable execution
                result.
              </p>
              <textarea
                rows={4}
                value={reflection}
                onChange={(event) => setReflection(event.target.value)}
              />
              <button
                className="ghost-button"
                disabled={loading || !reflection.trim()}
                onClick={() => void appendReflection()}
              >
                APPEND REFLECTION
              </button>
              {reflectionStatus && (
                <p className="positive">{reflectionStatus}</p>
              )}
              {result.reflections?.map((item) => (
                <blockquote key={item.reflection_id}>{item.text}</blockquote>
              ))}
            </section>
          </>
        ) : (
          <Empty title="NO STORY YET">
            Run the same execution facts through expert or guided presentation.
          </Empty>
        )}
      </section>
    </div>
  );
}

function CourseResultView({ result }: { result: CourseRunResponse }) {
  return (
    <details className="json-details" open>
      <summary>
        {result.verdict.replaceAll("_", " ").toUpperCase()} ·{" "}
        {result.schema_version} · {result.export_status.replaceAll("_", " ")} · {String(result.provenance.dataset_id)}
      </summary>
      <p className="story-summary">{result.question}</p>
      <div className="mini-metrics">
        {result.labs.map((lab) => (
          <span key={lab.scenario_id}>
            <small>{lab.scenario_id}</small>
            {lab.delta_classification.replaceAll("_", " ")}
          </span>
        ))}
      </div>
      <details>
        <summary>Generated research report and platform exports</summary>
        <pre>{result.research_report}</pre>
      </details>
    </details>
  );
}

function StoryView({ result }: { result: ExecutionStoryResponse }) {
  const story = result.story;
  return (
    <>
      <div className="section-heading">
        <div>
          <span>
            {story.mode.toUpperCase()} MODE · ID {result.story_id.slice(0, 10)}
          </span>
          <h2>{story.title}</h2>
        </div>
        <strong className={`status-${result.execution.status}`}>
          {result.execution.status.replaceAll("_", " ")}
        </strong>
      </div>
      <p className="story-summary">{story.summary}</p>
      <div className="research-metric-grid">
        <Metric
          label="Requested"
          value={String(result.execution.requested_quantity)}
        />
        <Metric
          label="Filled"
          value={String(result.execution.filled_quantity)}
        />
        <Metric
          label="Remaining"
          value={String(result.execution.remaining_quantity)}
        />
        <Metric
          label="Average price"
          value={
            result.execution.average_price?.toLocaleString() ?? "Not filled"
          }
        />
        <Metric
          label="Notional"
          value={result.execution.notional.toLocaleString()}
        />
        <Metric label="Fees" value={result.execution.fees.toLocaleString()} />
      </div>
      <details className="story-details" open={!story.detailsCollapsed}>
        <summary>Execution facts and thesis</summary>
        <div className="evidence-grid">
          {story.evidence.map((item, index) => (
            <article
              className={`evidence-card evidence-${item.kind}`}
              key={`${item.kind}-${item.label}-${index}`}
            >
              <span>{item.kind}</span>
              <b>{item.label}</b>
              <p>{item.value}</p>
              {item.explanation && <small>{item.explanation}</small>}
            </article>
          ))}
        </div>
        {story.mode === "guided" && (
          <div className="guided-sections">
            <GuidedList title="Assumptions" items={story.assumptions} />
            <GuidedList
              title="Invalidation conditions"
              items={story.invalidationConditions}
            />
            <GuidedList title="Hopes" items={story.hopes} />
            <GuidedList title="Risks" items={story.risks} />
            <section>
              <h3>Validation steps</h3>
              {story.validationSteps?.map((step) => (
                <article className="validation-step" key={step.label}>
                  <b>{step.label}</b>
                  <p>{step.instruction}</p>
                  <small>Expected: {step.expected}</small>
                </article>
              ))}
            </section>
            {story.reflectionPrompt && (
              <blockquote>{story.reflectionPrompt}</blockquote>
            )}
            {story.postRunReflection && (
              <section>
                <h3>Post-run reflection</h3>
                <p>{story.postRunReflection}</p>
              </section>
            )}
          </div>
        )}
      </details>
    </>
  );
}

function GuidedList({ title, items }: { title: string; items?: string[] }) {
  return (
    <section>
      <h3>{title}</h3>
      <ul>
        {items?.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function SystemWorkspace({
  catalog,
  capabilities,
  safety,
}: {
  catalog: CatalogResponse | null;
  capabilities: ResearchCapabilities | null;
  safety: SafetyStatus | null;
}) {
  return (
    <div className="page-workspace system-grid">
      <section className="surface-card">
        <div className="section-heading">
          <div>
            <span>SAFETY BOUNDARY</span>
            <h2>Execution controls</h2>
          </div>
          <strong
            className={Boolean(safety?.enabled) ? "negative" : "positive"}
          >
            {Boolean(safety?.enabled) ? "ENABLED" : "DISABLED"}
          </strong>
        </div>
        <pre className="system-json">{JSON.stringify(safety, null, 2)}</pre>
        <p className="safety">
          Mainnet order submission reported by the catalog:{" "}
          <b>{catalog?.mainnetOrderSubmission ? "YES" : "NO"}</b>
        </p>
      </section>
      <section className="surface-card">
        <div className="section-heading">
          <div>
            <span>CAPABILITIES</span>
            <h2>Research engine</h2>
          </div>
          <strong>
            {capabilities ? Object.keys(capabilities).length : 0} GROUPS
          </strong>
        </div>
        {capabilities &&
          Object.entries(capabilities)
            .filter(([key]) => key !== "execution")
            .map(([key, values]) => (
              <article className="capability-group" key={key}>
                <h3>{key.replaceAll("_", " ")}</h3>
                <div>
                  {Array.isArray(values) &&
                    values.map((value) => (
                      <span key={String(value)}>
                        {String(value).replaceAll("_", " ")}
                      </span>
                    ))}
                </div>
              </article>
            ))}
      </section>
      <section className="surface-card full-span">
        <div className="section-heading">
          <div>
            <span>ENVIRONMENTS</span>
            <h2>Exchange catalog</h2>
          </div>
          <strong>{catalog?.exchanges.length ?? 0} EXCHANGES</strong>
        </div>
        <div className="environment-grid">
          {catalog &&
            Object.entries(catalog.exchangeEnvironments).map(
              ([name, environment]) => (
                <article key={name}>
                  <b>{name}</b>
                  <span>{environment.environment}</span>
                  <small>{environment.badge}</small>
                  <em>
                    {environment.websocketConfigured
                      ? "WebSocket configured"
                      : "REST / simulation only"}
                  </em>
                </article>
              ),
            )}
        </div>
      </section>
    </div>
  );
}

function HistoryWorkspace({
  history,
  onClear,
}: {
  history: HistoryEntry[];
  onClear: () => void;
}) {
  return (
    <div className="page-workspace">
      <section className="surface-card">
        <div className="section-heading">
          <div>
            <span>LOCAL PERSISTENCE</span>
            <h2>Run history</h2>
          </div>
          <button
            className="danger-button"
            onClick={onClear}
            disabled={!history.length}
          >
            CLEAR HISTORY
          </button>
        </div>
        {history.length === 0 ? (
          <Empty title="NO SAVED RUNS">
            Backtests, replays, experiments, and execution stories persist in
            this browser.
          </Empty>
        ) : (
          <div className="history-table">
            {history.map((entry) => (
              <details key={entry.id}>
                <summary>
                  <span className={`history-kind kind-${entry.kind}`}>
                    {entry.kind}
                  </span>
                  <b>{entry.title}</b>
                  <small>{formatDate(entry.createdAt)}</small>
                  <em>{entry.summary}</em>
                </summary>
                <pre>{JSON.stringify(entry.payload, null, 2)}</pre>
              </details>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function DatasetSelect({
  datasets,
  value,
  onChange,
}: {
  datasets: DatasetManifest[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <Field label="Dataset">
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Select dataset</option>
        {datasets.map((dataset) => (
          <option key={dataset.dataset_id} value={dataset.dataset_id}>
            {dataset.dataset_id} · {dataset.event_count.toLocaleString()} events
          </option>
        ))}
      </select>
    </Field>
  );
}
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
function NumberField({
  label,
  value,
  onChange,
  step = "1",
  disabled = false,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  step?: string;
  disabled?: boolean;
}) {
  return (
    <Field label={label}>
      <input
        inputMode="decimal"
        type="number"
        value={value}
        step={step}
        disabled={disabled}
        onChange={(event: ChangeEvent<HTMLInputElement>) =>
          onChange(Number(event.target.value))
        }
      />
    </Field>
  );
}
function Metric({ label, value }: { label: string; value: string }) {
  return (
    <article>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}
function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="empty compact-empty">
      <strong>{title}</strong>
      <p>{children}</p>
    </div>
  );
}

function parseObject(text: string, label: string): Record<string, unknown> {
  const parsed: unknown = JSON.parse(text);
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object")
    throw new Error(`${label} must be a JSON object`);
  return parsed as Record<string, unknown>;
}
function parseGrid(text: string): Record<string, unknown[]> {
  const parsed = parseObject(text, "Parameter grid");
  for (const [key, value] of Object.entries(parsed))
    if (!Array.isArray(value) || value.length === 0)
      throw new Error(`Parameter grid ${key} must be a non-empty array`);
  return parsed as Record<string, unknown[]>;
}
function messageOf(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}
function money(value: number) {
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}
function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}
function loadHistory(): HistoryEntry[] {
  try {
    const value = JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}
function loadStoryMode(): StoryMode {
  const value = localStorage.getItem("quantforge:story-mode:v1");
  return value === "expert" || value === "guided" ? value : "guided";
}
