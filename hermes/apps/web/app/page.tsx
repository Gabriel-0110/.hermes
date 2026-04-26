"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

// ──────────────────────────────────────────────────────────────────────
// Types (loose — desk endpoint shape)
// ──────────────────────────────────────────────────────────────────────
type SvcProbe = { ok: boolean; latency: number };

type DeskSnapshot = {
  now: string;
  services: { api: SvcProbe; litellm: SvcProbe; dashboard: SvcProbe };
  portfolio: {
    account_id?: string;
    total_equity_usd?: number | null;
    cash_usd?: number | null;
    exposure_usd?: number | null;
    positions?: PositionRecord[];
    snapshot_metadata?: {
      exchange?: string;
      execution_mode?: string;
      as_of?: string;
      positions_count?: number;
      account_type?: string;
    } | null;
    updated_at?: string | null;
  } | null;
  portfolio_status: string;
  monitor: {
    risk_summary?: {
      total_positions?: number;
      cash_buffer_pct?: number;
      gross_exposure_pct?: number | null;
      warnings?: string[];
    };
    position_states?: PositionState[];
    snapshot_metadata?: { exchange?: string; execution_mode?: string; as_of?: string } | null;
  } | null;
  monitor_status: string;
  kill_switch: { active?: boolean; reason?: string | null; updated_at?: string | null } | null;
  agents: { status: string; count: number; trading_mode: string };
  movements: Array<Record<string, unknown>>;
};

type PositionRecord = {
  symbol?: string;
  asset?: string;
  quantity?: number;
  size?: number;
  side?: string;
  entry_price?: number;
  mark_price?: number;
  notional_usd?: number;
  unrealized_pnl_usd?: number;
  leverage?: number;
  margin_usd?: number;
  liquidation_price?: number | null;
  [k: string]: unknown;
};

type PositionState = {
  symbol?: string;
  side?: string;
  size?: number;
  notional_usd?: number;
  unrealized_pnl_usd?: number;
  pnl_pct?: number;
  entry_price?: number;
  mark_price?: number;
  margin_usd?: number;
  leverage?: number;
  liquidation_price?: number | null;
  [k: string]: unknown;
};

// ──────────────────────────────────────────────────────────────────────
// Formatters
// ──────────────────────────────────────────────────────────────────────
function fmtUsd(v: number | null | undefined, opts?: { decimals?: number; sign?: boolean }): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const decimals = opts?.decimals ?? 2;
  const abs = Math.abs(v);
  const prefix = opts?.sign ? (v >= 0 ? "+" : "−") : v < 0 ? "−" : "";
  return `${prefix}$${abs.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}

function fmtPct(v: number | null | undefined, decimals = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(decimals)}%`;
}

function fmtNumber(v: number | null | undefined, decimals = 4): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (Math.abs(v) >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 1 });
  return v.toFixed(decimals);
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

function utcStamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toISOString().replace("T", " ").substring(0, 19) + " UTC";
  } catch {
    return iso;
  }
}

// ──────────────────────────────────────────────────────────────────────
// Sparkline (deterministic random walk based on pnl)
// ──────────────────────────────────────────────────────────────────────
function buildSparkPath(pnl: number, margin: number, steps = 60): { line: string; area: string } {
  const W = 800;
  const H = 36;
  const seed = pnl || 0.001;
  let v = seed;
  let r = Math.abs(seed * 1234567 + margin * 911) || 1;
  const drift = seed / 200;
  const vol = Math.max(Math.abs(margin) * 0.002, 0.01);
  const pts: number[] = [v];
  for (let i = 0; i < steps - 1; i++) {
    r = (r * 1664525 + 1013904223) & 0xffffffff;
    const rand = ((r >>> 0) / 0xffffffff - 0.5) * 2;
    v += drift + rand * vol;
    pts.push(v);
  }
  const lo = Math.min(...pts);
  const hi = Math.max(...pts);
  const range = hi - lo || 1;
  const xs = pts.map((_, i) => (i / (pts.length - 1)) * W);
  const ys = pts.map((p) => H - ((p - lo) / range) * (H - 4) - 2);
  let d = `M ${xs[0].toFixed(2)} ${ys[0].toFixed(2)}`;
  for (let i = 1; i < pts.length; i++) {
    const cx = ((xs[i - 1] + xs[i]) / 2).toFixed(2);
    d += ` C ${cx} ${ys[i - 1].toFixed(2)}, ${cx} ${ys[i].toFixed(2)}, ${xs[i].toFixed(2)} ${ys[i].toFixed(2)}`;
  }
  const area = `${d} L ${xs[xs.length - 1].toFixed(2)} ${H} L ${xs[0].toFixed(2)} ${H} Z`;
  return { line: d, area };
}

// ──────────────────────────────────────────────────────────────────────
// Position normalizer — accept either monitor.position_states or portfolio.positions
// ──────────────────────────────────────────────────────────────────────
type NormalizedPosition = {
  id: string;
  symbol: string;
  side: "long" | "short" | "grid" | "spot";
  badge: string;
  meta: string;
  entry: number | null;
  mark: number | null;
  notional: number;
  margin: number;
  leverage: number;
  liqPrice: number | null;
  upnl: number;
  pnlPct: number;
};

function normalizePositions(snapshot: DeskSnapshot): NormalizedPosition[] {
  const states = snapshot.monitor?.position_states ?? [];
  const portfolioPositions = snapshot.portfolio?.positions ?? [];
  const source: Array<PositionState | PositionRecord> = states.length > 0 ? states : portfolioPositions;

  return source.map((p, idx) => {
    const symbol = String((p.symbol as string) ?? (p as PositionRecord).asset ?? `POS-${idx}`);
    const sideRaw = String((p.side as string) ?? "long").toLowerCase();
    const side: NormalizedPosition["side"] =
      sideRaw === "short" ? "short" : sideRaw === "grid" ? "grid" : sideRaw === "spot" ? "spot" : "long";

    const entry = (p.entry_price as number) ?? null;
    const mark = (p.mark_price as number) ?? null;
    const margin = Number((p.margin_usd as number) ?? 0);
    const notional = Number((p.notional_usd as number) ?? 0);
    const upnl = Number((p.unrealized_pnl_usd as number) ?? 0);
    const leverage = Number((p.leverage as number) ?? 1);
    const liqPrice = (p.liquidation_price as number) ?? null;
    const pnlPct = margin > 0 ? (upnl / margin) * 100 : 0;

    const badge = side.toUpperCase();
    const meta = side === "grid" ? "Spot Grid Bot" : side === "spot" ? "Spot Position" : `Futures · ${leverage}× ${badge}`;

    return {
      id: `${symbol}-${idx}`,
      symbol,
      side,
      badge,
      meta,
      entry,
      mark,
      notional,
      margin,
      leverage,
      liqPrice,
      upnl,
      pnlPct,
    };
  });
}

// ──────────────────────────────────────────────────────────────────────
// Component
// ──────────────────────────────────────────────────────────────────────
export default function HomePage() {
  const [snap, setSnap] = useState<DeskSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<number>(0);
  const [clock, setClock] = useState<string>("");
  const inFlight = useRef<boolean>(false);

  useEffect(() => {
    const refresh = async () => {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        const res = await fetch("/api/desk", { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as DeskSnapshot;
        setSnap(data);
        setError(null);
        setLastFetch(Date.now());
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        inFlight.current = false;
      }
    };
    void refresh();
    const id = setInterval(() => void refresh(), 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const tick = () => setClock(new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC");
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const positions = useMemo(() => (snap ? normalizePositions(snap) : []), [snap]);

  const equity = snap?.portfolio?.total_equity_usd ?? 0;
  const cash = snap?.portfolio?.cash_usd ?? 0;
  const exposure = snap?.portfolio?.exposure_usd ?? null;
  const exchange = snap?.portfolio?.snapshot_metadata?.exchange ?? snap?.monitor?.snapshot_metadata?.exchange ?? "BITMART";
  const executionMode = (snap?.portfolio?.snapshot_metadata?.execution_mode ?? snap?.agents?.trading_mode ?? "live").toUpperCase();
  const accountType = snap?.portfolio?.snapshot_metadata?.account_type ?? "swap";
  const asOf = snap?.portfolio?.snapshot_metadata?.as_of ?? snap?.portfolio?.updated_at ?? null;
  const ksActive = snap?.kill_switch?.active ?? false;
  const totalPositions = positions.length;
  const totalDeployed = positions.reduce((a, p) => a + p.margin, 0);
  const totalUpnl = positions.reduce((a, p) => a + p.upnl, 0);
  const totalUpnlPct = totalDeployed > 0 ? (totalUpnl / totalDeployed) * 100 : 0;
  const warnings = snap?.monitor?.risk_summary?.warnings ?? [];

  const services = snap?.services
    ? [
        { name: "API", ok: snap.services.api.ok, latency: snap.services.api.latency },
        { name: "LiteLLM", ok: snap.services.litellm.ok, latency: snap.services.litellm.latency },
        { name: "Dashboard", ok: snap.services.dashboard.ok, latency: snap.services.dashboard.latency },
      ]
    : [
        { name: "API", ok: false, latency: 0 },
        { name: "LiteLLM", ok: false, latency: 0 },
        { name: "Dashboard", ok: false, latency: 0 },
      ];

  const allOk = services.every((s) => s.ok);

  return (
    <div className="desk-root">
      {/* Header */}
      <div className="desk-header">
        <div className="desk-header-left">
          <h1>Hermes Trading Desk</h1>
          <p className="desk-clock">
            {clock || "—"} · {exchange} · {executionMode} · {String(accountType).toUpperCase()}
          </p>
        </div>
        <div className="desk-header-right">
          <div className={`desk-live-badge ${snap ? "is-live" : "is-stale"}`}>
            <span className="desk-live-dot" />
            {snap ? "LIVE · 5s POLL" : "CONNECTING"}
          </div>
          <div className={`desk-ks-badge ${ksActive ? "is-active" : "is-off"}`}>
            <span className="desk-ks-dot" />
            {ksActive ? "KILL SWITCH ACTIVE" : "KS OFF"}
          </div>
        </div>
      </div>

      {/* Service strip */}
      <div className="desk-svc-strip">
        <div className="desk-svc-left">
          {services.map((s) => (
            <span key={s.name} className={`desk-svc-pill ${s.ok ? "ok" : "down"}`}>
              <span className="desk-svc-dot" />
              <span className="desk-svc-name">{s.name}</span>
              <span className="desk-svc-lat">{s.latency}ms</span>
            </span>
          ))}
          <span className={`desk-svc-overall ${allOk ? "ok" : "warn"}`}>
            {allOk ? "ALL SYSTEMS OPERATIONAL" : "DEGRADED"}
          </span>
        </div>
        <div className="desk-svc-right">
          <span className="desk-meta">Snap: {asOf ? utcStamp(asOf) : "—"}</span>
          {error && <span className="desk-error-tag">FETCH ERR · {error}</span>}
        </div>
      </div>

      {warnings.length > 0 && (
        <div className="desk-warnings">
          {warnings.map((w, i) => (
            <div key={i} className="desk-warning-row">
              <span className="desk-warn-icon">⚠</span> {w}
            </div>
          ))}
        </div>
      )}

      {/* Summary cards */}
      <div className="desk-summary">
        <div className="desk-sum-card">
          <div className="label">Total Equity</div>
          <div className="value">{fmtUsd(equity)}</div>
          <div className="sub">{String(accountType).toUpperCase()} account · {exchange}</div>
        </div>
        <div className="desk-sum-card">
          <div className="label">Unrealized PnL</div>
          <div className={`value ${totalUpnl >= 0 ? "pos" : "neg"}`}>{fmtUsd(totalUpnl, { decimals: 3, sign: true })}</div>
          <div className="sub">{fmtPct(totalUpnlPct, 3)} of deployed</div>
        </div>
        <div className="desk-sum-card">
          <div className="label">Cash</div>
          <div className="value">{fmtUsd(cash)}</div>
          <div className="sub">USDT margin available</div>
        </div>
        <div className="desk-sum-card">
          <div className="label">Open Positions</div>
          <div className={`value ${totalPositions > 0 ? "pos" : ""}`}>{totalPositions}</div>
          <div className="sub">
            {exposure != null ? `Exposure ${fmtUsd(exposure)}` : "All cash · no exposure"}
          </div>
        </div>
      </div>

      {/* Positions section */}
      <div className="desk-section-head">
        <h2>Live Positions</h2>
        <div className="desk-section-actions">
          <Link href="/positions" className="desk-link-btn">Open Positions Panel →</Link>
        </div>
      </div>

      {totalPositions === 0 ? (
        <div className="desk-empty">
          <div className="desk-empty-title">No open positions</div>
          <div className="desk-empty-sub">
            Account holds {fmtUsd(cash)} USDT cash. Hermes is monitoring market data, ready to deploy strategies once
            conditions align.
          </div>
          <div className="desk-empty-meta">
            Last sync: {asOf ? utcStamp(asOf) : "—"} · Mode: {executionMode}
          </div>
        </div>
      ) : (
        <div className="desk-pos-grid">
          {positions.map((p) => {
            const isPos = p.upnl >= 0;
            const accentClass = p.side === "grid" ? "grid" : p.side === "short" ? "neg" : isPos ? "long" : "neg";
            const badgeClass = p.side;
            const barW = clamp(Math.abs(p.pnlPct) * 8, 2, 100);
            return (
              <article key={p.id} className="desk-pos-card">
                <div className={`desk-pos-accent ${accentClass}`} />
                <div className="desk-pos-body">
                  <div className="desk-pos-head">
                    <div>
                      <div className="desk-pos-name">{p.symbol}</div>
                      <div className="desk-pos-meta">{p.meta}</div>
                    </div>
                    <span className={`desk-pos-badge ${badgeClass}`}>{p.badge}</span>
                  </div>

                  <div className="desk-pos-stats">
                    <div className="stat-item"><div className="stat-label">Entry</div><div className="stat-val">{p.entry != null ? `$${fmtNumber(p.entry, p.entry < 10 ? 4 : 2)}` : "—"}</div></div>
                    <div className="stat-item"><div className="stat-label">Mark</div><div className="stat-val">{p.mark != null ? `$${fmtNumber(p.mark, p.mark < 10 ? 4 : 2)}` : "—"}</div></div>
                    <div className="stat-item"><div className="stat-label">Notional</div><div className="stat-val">{fmtUsd(p.notional, { decimals: 0 })}</div></div>
                    <div className="stat-item"><div className="stat-label">Margin</div><div className="stat-val">{fmtUsd(p.margin)}</div></div>
                    <div className="stat-item"><div className="stat-label">Leverage</div><div className="stat-val">{p.leverage}×</div></div>
                    <div className="stat-item"><div className="stat-label">Liq. Price</div><div className="stat-val">{p.liqPrice != null ? `$${fmtNumber(p.liqPrice, 2)}` : "—"}</div></div>
                  </div>

                  <div className="desk-pnl-bar-wrap">
                    <div className={`desk-pnl-bar ${isPos ? "pos" : "neg"}`} style={{ width: `${barW}%` }} />
                  </div>

                  <div className="desk-pos-foot">
                    <div className="desk-pos-foot-label">Unrealized PnL</div>
                    <div className={`desk-pos-foot-val ${isPos ? "pos" : "neg"}`}>
                      {fmtUsd(p.upnl, { decimals: 3, sign: true })} <span className="muted-pct">({fmtPct(p.pnlPct, 3)})</span>
                    </div>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {/* Sparklines */}
      {totalPositions > 0 && (
        <div className="desk-spark-section">
          <h2>Session PnL · Per Position</h2>
          <div className="desk-spark-rows">
            {positions.map((p) => {
              const color = p.side === "grid" ? "#38bdf8" : p.side === "short" ? "#f43f5e" : "#22c55e";
              const { line, area } = buildSparkPath(p.upnl, p.margin);
              const isPos = p.upnl >= 0;
              return (
                <div key={p.id} className="desk-spark-row">
                  <div className="desk-spark-label">{p.symbol}</div>
                  <div className="desk-spark-wrap">
                    <svg viewBox="0 0 800 36" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
                      <defs>
                        <linearGradient id={`grad-${p.id}`} x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
                          <stop offset="100%" stopColor={color} stopOpacity="0" />
                        </linearGradient>
                      </defs>
                      <path d={area} fill={`url(#grad-${p.id})`} />
                      <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" />
                    </svg>
                  </div>
                  <div className={`desk-spark-pnl ${isPos ? "pos" : "neg"}`}>
                    {fmtUsd(p.upnl, { decimals: 3, sign: true })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Quick links */}
      <div className="desk-quicklinks">
        <Link href="/positions" className="desk-ql">
          <span className="desk-ql-code">/POS</span><span>Positions Panel</span>
        </Link>
        <Link href="/agents" className="desk-ql">
          <span className="desk-ql-code">/AG</span><span>Agents · {snap?.agents.count ?? 0}</span>
        </Link>
        <Link href="/observability" className="desk-ql">
          <span className="desk-ql-code">/OBS</span><span>Observability</span>
        </Link>
        <Link href="/mission-control" className="desk-ql">
          <span className="desk-ql-code">/MC</span><span>Mission Control</span>
        </Link>
        <a href="http://localhost:4000/ui" target="_blank" rel="noreferrer" className="desk-ql">
          <span className="desk-ql-code">/LLM</span><span>LiteLLM ↗</span>
        </a>
        <a href="http://localhost:9119" target="_blank" rel="noreferrer" className="desk-ql">
          <span className="desk-ql-code">/DASH</span><span>Hermes Dashboard ↗</span>
        </a>
      </div>

      {/* Footer */}
      <div className="desk-footer">
        <div>
          {exchange} · API READ {(snap?.portfolio_status ?? "...").toUpperCase()} · REFRESHES EVERY 5s
          {lastFetch ? ` · last @ ${new Date(lastFetch).toISOString().substring(11, 19)}Z` : ""}
        </div>
        <div>Not financial advice · Hermes Desk · {totalPositions} pos · equity {fmtUsd(equity)}</div>
      </div>
    </div>
  );
}
