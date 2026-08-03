import { useEffect, useMemo, useState } from "react";
import { getCapabilities, getCatalog, getExecutionSafety } from "./api";
import "./eu-miner.css";

type NodeState = "checking" | "online" | "degraded";

const feeds = [
  { name: "BYBIT", detail: "Candles · order books", color: "cyan" },
  { name: "HYPERLIQUID", detail: "L2 · trades · funding", color: "green" },
  { name: "WHITEBIT", detail: "Public market data", color: "violet" },
  { name: "BITMEX", detail: "Candles · derivatives", color: "amber" },
];

const pipeline = [
  ["01", "INGEST", "Public exchange feeds"],
  ["02", "NORMALIZE", "Canonical market events"],
  ["03", "VERIFY", "Sequence + checksums"],
  ["04", "ARCHIVE", "Replay-ready datasets"],
];

export function EuMinerPage() {
  const [nodeState, setNodeState] = useState<NodeState>("checking");
  const [exchangeCount, setExchangeCount] = useState(4);
  const [executionEnabled, setExecutionEnabled] = useState(false);
  const [clock, setClock] = useState(() => new Date());

  useEffect(() => {
    const originalTitle = document.title;
    document.title = "EU Xchange Miner · QuantForge";
    const timer = window.setInterval(() => setClock(new Date()), 1_000);
    let cancelled = false;

    void Promise.allSettled([
      getCatalog(),
      getCapabilities(),
      getExecutionSafety(),
    ]).then(([catalog, capabilities, safety]) => {
      if (cancelled) return;
      const available = [catalog, capabilities, safety].filter(
        (result) => result.status === "fulfilled",
      ).length;
      setNodeState(available === 3 ? "online" : "degraded");

      if (catalog.status === "fulfilled") {
        setExchangeCount(
          catalog.value.exchanges.filter((exchange) => exchange !== "synthetic")
            .length,
        );
      }
      if (safety.status === "fulfilled") {
        setExecutionEnabled(Boolean(safety.value.enabled));
      }
    });

    return () => {
      cancelled = true;
      window.clearInterval(timer);
      document.title = originalTitle;
    };
  }, []);

  const statusLabel = useMemo(() => {
    if (nodeState === "checking") return "CHECKING NODE";
    if (nodeState === "online") return "NODE ONLINE";
    return "NODE DEGRADED";
  }, [nodeState]);

  return (
    <main className="eu-page">
      <header className="eu-nav">
        <a className="eu-brand" href="/" aria-label="Open QuantForge research lab">
          <span className="eu-brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span><strong>QUANTFORGE</strong><small>EUROPE</small></span>
        </a>
        <nav aria-label="EU Xchange Miner navigation">
          <a href="#pipeline">PIPELINE</a>
          <a href="#feeds">FEEDS</a>
          <a href="#learn">LEARN</a>
          <a href="/docs">API</a>
          <a className="eu-lab-link" href="/">OPEN LAB <span>↗</span></a>
        </nav>
      </header>

      <section className="eu-hero">
        <div className="eu-hero-copy">
          <div className="eu-eyebrow">
            <span className={`eu-status-dot ${nodeState}`} />
            LONDON · AWS EU-WEST-2 · {statusLabel}
          </div>
          <h1>EU XCHANGE <span>MINER</span></h1>
          <p>
            QuantForge's European market-data observation node. It captures public
            exchange feeds, verifies every event, and produces deterministic datasets
            for arbitrage research, replay, and education.
          </p>
          <div className="eu-hero-actions">
            <a className="eu-primary-action" href="/">ENTER QUANTFORGE <span>→</span></a>
            <a className="eu-secondary-action" href="#pipeline">VIEW DATA PIPELINE</a>
          </div>
          <div className="eu-safety-line">
            <span>◆</span>
            RESEARCH ONLY · {executionEnabled ? "TESTNET GATE ENABLED" : "ORDER EXECUTION DISABLED"} · NO MAINNET SUBMISSION
          </div>
        </div>

        <div className="eu-node-console" aria-label="European collector node status">
          <div className="eu-console-head">
            <div><small>NODE</small><strong>QF-EU-LON-01</strong></div>
            <span className={`eu-node-badge ${nodeState}`}>{statusLabel}</span>
          </div>
          <div className="eu-orbit" aria-hidden="true">
            <div className="eu-orbit-ring ring-one" />
            <div className="eu-orbit-ring ring-two" />
            <div className="eu-core"><strong>EU</strong><small>LON</small></div>
            <i className="eu-point p1" /><i className="eu-point p2" />
            <i className="eu-point p3" /><i className="eu-point p4" />
          </div>
          <dl className="eu-node-metrics">
            <div><dt>REGION</dt><dd>EU-WEST-2</dd></div>
            <div><dt>PUBLIC FEEDS</dt><dd>{exchangeCount}</dd></div>
            <div><dt>MODE</dt><dd>OBSERVE</dd></div>
            <div><dt>UTC</dt><dd>{clock.toISOString().slice(11, 19)}</dd></div>
          </dl>
          <div className="eu-stream">
            <span>INGEST</span><div>{Array.from({ length: 8 }, (_, index) => <i key={index} />)}</div>
            <strong>{nodeState === "online" ? "LIVE" : nodeState === "checking" ? "SYNC" : "WAIT"}</strong>
          </div>
        </div>
      </section>

      <section className="eu-facts" aria-label="Node guarantees">
        <div><small>LOCATION</small><strong>LONDON, UNITED KINGDOM</strong></div>
        <div><small>INTEGRITY</small><strong>SHA-256 CHECKSUM CHAIN</strong></div>
        <div><small>OUTPUT</small><strong>DETERMINISTIC REPLAY</strong></div>
        <div><small>SAFETY</small><strong>SIMULATION FIRST</strong></div>
      </section>

      <section className="eu-section" id="pipeline">
        <div className="eu-section-head">
          <span>01 / DATA FLOW</span>
          <h2>From public quote to defensible research.</h2>
          <p>Every observation retains exchange time, receive time, local sequence, and a canonical checksum.</p>
        </div>
        <div className="eu-pipeline">
          {pipeline.map(([number, name, detail]) => (
            <article key={number}>
              <small>{number}</small>
              <div className="eu-pipeline-icon" aria-hidden="true"><i /><i /><i /></div>
              <h3>{name}</h3><p>{detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="eu-section eu-feed-section" id="feeds">
        <div className="eu-section-head wide">
          <span>02 / VENUES</span>
          <h2>European observation. Multi-venue evidence.</h2>
        </div>
        <div className="eu-feeds">
          {feeds.map((feed) => (
            <article key={feed.name}>
              <span className={`eu-feed-signal ${feed.color}`}><i /><i /><i /></span>
              <div><h3>{feed.name}</h3><p>{feed.detail}</p></div>
              <small>PUBLIC</small>
            </article>
          ))}
        </div>
      </section>

      <section className="eu-learn" id="learn">
        <div className="eu-demo-stage">
          <div className="eu-demo-head"><span><i /> RECORDED LAB / ARBITRAGE REPLAY</span><small>00:42</small></div>
          <div className="eu-demo-screen">
            <div className="eu-demo-side"><i className="active" /><i /><i /><i /><i /></div>
            <div className="eu-demo-workspace">
              <div className="eu-demo-ticker"><span>BTC / USDT</span><strong>+12.4 BPS</strong></div>
              <div className="eu-demo-chart">{Array.from({ length: 12 }, (_, index) => <i key={index} />)}</div>
              <div className="eu-demo-row"><span>BYBIT → HYPERLIQUID</span><strong>ACCEPTED</strong></div>
              <div className="eu-demo-row rejected"><span>WHITEBIT → BITMEX</span><strong>REJECTED · FEES</strong></div>
            </div>
            <span className="eu-demo-play" aria-hidden="true">▶</span>
          </div>
          <p>Video-ready slot for deterministic Playwright-recorded product tours.</p>
        </div>

        <div className="eu-learning-copy">
          <div className="eu-section-head">
            <span>03 / LEARN THE SYSTEM</span>
            <h2>Watch the evidence. Reproduce the lesson.</h2>
            <p>Every demonstration is backed by a replayable scenario, keeping the software, course, and books aligned.</p>
          </div>
          <div className="eu-products">
            <article className="eu-course-card">
              <div><span>COURSE</span><small>60–90 MIN STARTER MODULE</small></div>
              <h3>Crypto Algorithmic Trading Research with Python</h3>
              <p>Backtesting, order books, walk-forward analysis, and Monte Carlo with QuantForge.</p>
              <span className="eu-coming">PREVIEW COMING SOON →</span>
            </article>
            <article className="eu-book-card book-green">
              <span>BOOK I</span><h3>Crypto Strategy Research Without Risk</h3>
              <small>BACKTEST · REPLAY · VALIDATE</small>
            </article>
            <article className="eu-book-card book-violet">
              <span>BOOK II</span><h3>Building QuantForge</h3>
              <small>MARKET DATA · L2 · EXECUTION</small>
            </article>
          </div>
        </div>
      </section>

      <footer className="eu-footer">
        <span>QUANTFORGE / EU XCHANGE MINER</span>
        <p>Observation and education only. Not an exchange, broker, or trading service.</p>
        <a href="/">RESEARCH LAB ↗</a>
      </footer>
    </main>
  );
}
