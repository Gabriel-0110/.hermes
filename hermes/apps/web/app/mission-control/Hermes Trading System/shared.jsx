/* Shared primitives & mock data for Hermes Mission Control variants */

const HERMES_DATA = {
  session: {
    operator: "R. KLEIN",
    desk: "DESK-07",
    loggedAt: "2026-04-23 08:41:12 UTC",
    regime: "RISK-ON · LOW-VOL",
    mode: "LIVE · BITMART",
    killSwitch: false,
  },
  portfolio: {
    equity: 2847321.44,
    equityDelta: 18432.91,
    equityDeltaPct: 0.65,
    cash: 412908.12,
    exposure: 2434413.32,
    netExposurePct: 85.5,
    leverage: 1.18,
    dayPnL: 18432.91,
    weekPnL: 64211.08,
    monthPnL: 142908.77,
    realized: 47211.00,
    unrealized: -4778.09,
    drawdown: -2.1,
    var95: -38250.0,
  },
  positions: [
    { sym: "BTCUSDT",  side: "LONG",  qty: 12.4,   notional: 1138220, pnl:  14220, pnlPct:  1.27, weight: 40.0, thesis: "Momentum · 4H trend intact" },
    { sym: "ETHUSDT",  side: "LONG",  qty: 182.3,  notional:  612408, pnl:   8420, pnlPct:  1.39, weight: 21.5, thesis: "Beta carry vs BTC" },
    { sym: "SOLUSDT",  side: "LONG",  qty: 2104.0, notional:  384712, pnl:  -1980, pnlPct: -0.51, weight: 13.5, thesis: "Range accumulation" },
    { sym: "LINKUSDT", side: "SHORT", qty:  8400.0,notional:  181344, pnl:   2105, pnlPct:  1.17, weight:  6.4, thesis: "Mean-reversion short" },
    { sym: "ARBUSDT",  side: "LONG",  qty: 41200,  notional:   94120, pnl:   -812, pnlPct: -0.85, weight:  3.3, thesis: "L2 rotation watch" },
    { sym: "DOGEUSDT", side: "LONG",  qty: 920000, notional:   82104, pnl:    420, pnlPct:  0.51, weight:  2.9, thesis: "Tactical · social flow" },
  ],
  focus: {
    symbol: "BTCUSDT",
    last: 91821.40,
    change: 1.24,
    change24: 2.87,
    high24: 92410.00,
    low24: 89120.00,
    vol24: "41.2K BTC",
    atr: 1842.50,
    rsi: 58,
    trend: "UP · 4H",
    levels: {
      r2: 93200, r1: 92400, pivot: 91600, s1: 90800, s2: 89900,
    },
    notes: "Reclaimed 91.2k pivot on 4H close. Funding neutral. Watch 92.4k for breakout confirmation; invalidation below 90.8k.",
  },
  tape: [
    { t: "08:41:02", kind: "FILL",    sym: "ETHUSDT",  side: "BUY",  qty: 12.4,  px: 3358.20, note: "TWAP slice 4/8" },
    { t: "08:39:47", kind: "ALERT",   sym: "SOLUSDT",  side: "—",    qty: null,  px: 182.40, note: "4H RSI cross > 60" },
    { t: "08:38:11", kind: "SIGNAL",  sym: "LINKUSDT", side: "SELL", qty: null,  px: 21.58,  note: "Mean-rev short · conf 0.71" },
    { t: "08:36:02", kind: "FILL",    sym: "BTCUSDT",  side: "BUY",  qty: 0.40,  px: 91820.10, note: "Approved · manual" },
    { t: "08:32:20", kind: "RESEARCH",sym: "ARBUSDT",  side: "—",    qty: null,  px: null,   note: "Thesis v2 committed" },
    { t: "08:28:44", kind: "ALERT",   sym: "BTCUSDT",  side: "—",    qty: null,  px: 91640.00,note: "Pivot reclaim · 4H" },
    { t: "08:24:03", kind: "FILL",    sym: "DOGEUSDT", side: "BUY",  qty: 120000,px: 0.0892, note: "TWAP slice 2/3" },
    { t: "08:19:58", kind: "REJECT",  sym: "PEPEUSDT", side: "BUY",  qty: null,  px: null,   note: "Risk · exposure cap" },
    { t: "08:14:12", kind: "SIGNAL",  sym: "ETHUSDT",  side: "BUY",  qty: null,  px: 3355.00,note: "Momentum · conf 0.82" },
    { t: "08:09:33", kind: "FILL",    sym: "SOLUSDT",  side: "SELL", qty: 140.0, px: 182.75, note: "Trim · partial" },
  ],
  lanes: [
    { name: "Watching",      count: 6, items: [
      { sym: "AVAXUSDT", thesis: "L1 rotation candidate",   conf: 0.54, agent: "Scout-2", age: "14m" },
      { sym: "OPUSDT",   thesis: "L2 volume compression",    conf: 0.48, agent: "Scout-2", age: "41m" },
      { sym: "INJUSDT",  thesis: "Breakout retest",          conf: 0.62, agent: "Scout-1", age: "1h" },
    ]},
    { name: "Researching",   count: 3, items: [
      { sym: "ARBUSDT",  thesis: "L2 rotation · thesis v2",  conf: 0.71, agent: "Analyst-A", age: "22m" },
      { sym: "TIAUSDT",  thesis: "Unlock calendar risk",     conf: 0.40, agent: "Analyst-B", age: "2h" },
    ]},
    { name: "Ready",         count: 2, items: [
      { sym: "LINKUSDT", thesis: "Mean-rev short · 4H",       conf: 0.71, agent: "Exec-1", age: "3m" },
      { sym: "ETHUSDT",  thesis: "Momentum add · TWAP 4/8",   conf: 0.82, agent: "Exec-1", age: "8m" },
    ]},
    { name: "Executing",     count: 2, items: [
      { sym: "ETHUSDT",  thesis: "TWAP 4/8 · 50% filled",     conf: 0.82, agent: "Exec-1", age: "12m" },
      { sym: "DOGEUSDT", thesis: "TWAP 2/3 · 67% filled",     conf: 0.55, agent: "Exec-1", age: "18m" },
    ]},
    { name: "Review",        count: 3, items: [
      { sym: "SOLUSDT",  thesis: "Trim fill · -0.5% slip",    conf: null, agent: "—",       age: "34m" },
      { sym: "BTCUSDT",  thesis: "Manual entry · post-trade", conf: null, agent: "—",       age: "1h" },
    ]},
  ],
  timeline: [
    { t: "08:41", label: "FILL",   detail: "ETHUSDT +12.4 @ 3358.20",  tone: "gain" },
    { t: "08:39", label: "ALERT",  detail: "SOLUSDT 4H RSI > 60",       tone: "warn" },
    { t: "08:38", label: "SIGNAL", detail: "LINKUSDT short · 0.71",     tone: "info" },
    { t: "08:36", label: "FILL",   detail: "BTCUSDT +0.40 @ 91820.1",  tone: "gain" },
    { t: "08:32", label: "NOTE",   detail: "ARBUSDT thesis v2",         tone: "mute" },
    { t: "08:28", label: "ALERT",  detail: "BTCUSDT pivot reclaim",     tone: "info" },
    { t: "08:19", label: "REJECT", detail: "PEPEUSDT · exposure cap",   tone: "loss" },
    { t: "08:14", label: "SIGNAL", detail: "ETHUSDT momentum · 0.82",   tone: "info" },
    { t: "07:58", label: "OPEN",   detail: "Session start · RISK-ON",   tone: "mute" },
  ],
  approvals: [
    { sym: "LINKUSDT", side: "SELL", size: "$180k", conf: 0.71, reason: "Mean-rev short · exposure OK", expiresIn: "4m 22s" },
    { sym: "AVAXUSDT", side: "BUY",  size: "$120k", conf: 0.64, reason: "Momentum continuation",         expiresIn: "7m 10s" },
  ],
  risk: {
    posture: "NORMAL",
    exposurePct: 85.5,
    maxExposurePct: 100,
    concentration: "BTC 40% · ETH 22%",
    alerts: [
      { level: "amber", msg: "Gross exposure approaching 90% cap" },
      { level: "blue",  msg: "Correlation rising: BTC/ETH 30d = 0.84" },
    ],
  },
  watchlist: [
    { sym: "BTCUSDT",  px: 91821.4, chg:  1.24 },
    { sym: "ETHUSDT",  px:  3358.2, chg:  1.87 },
    { sym: "SOLUSDT",  px:   182.4, chg: -0.42 },
    { sym: "LINKUSDT", px:    21.58,chg: -1.12 },
    { sym: "ARBUSDT",  px:     2.28,chg:  0.54 },
    { sym: "AVAXUSDT", px:    42.10,chg:  2.14 },
    { sym: "OPUSDT",   px:     3.41,chg: -0.22 },
    { sym: "INJUSDT",  px:    27.82,chg:  3.41 },
  ],
};

// Utilities
const fmtUsd = (n, opts = {}) => {
  if (n == null) return "—";
  const { compact = false, sign = false } = opts;
  const abs = Math.abs(n);
  let body;
  if (compact && abs >= 1000) {
    if (abs >= 1e6) body = (abs/1e6).toFixed(2) + "M";
    else body = (abs/1e3).toFixed(1) + "k";
  } else {
    body = abs.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  const s = sign ? (n > 0 ? "+" : n < 0 ? "−" : "") : (n < 0 ? "−" : "");
  return `${s}$${body}`;
};
const fmtPct = (n, digits = 2) => (n == null ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(digits)}%`);
const fmtNum = (n) => (n == null ? "—" : n.toLocaleString("en-US", { maximumFractionDigits: 4 }));

// Deterministic pseudo-candle generator
function genCandles(n = 80, seed = 17, start = 91000, vol = 300) {
  let x = seed;
  const rnd = () => { x = (x * 9301 + 49297) % 233280; return x / 233280; };
  const out = [];
  let last = start;
  for (let i = 0; i < n; i++) {
    const o = last;
    const drift = (rnd() - 0.48) * vol;
    const c = Math.max(10, o + drift);
    const h = Math.max(o, c) + rnd() * vol * 0.6;
    const l = Math.min(o, c) - rnd() * vol * 0.6;
    out.push({ o, h, l, c });
    last = c;
  }
  return out;
}

// Simple SVG sparkline from candle closes
function sparkPath(vals, w, h, pad = 2) {
  if (!vals.length) return "";
  const min = Math.min(...vals), max = Math.max(...vals), rng = max - min || 1;
  return vals.map((v, i) => {
    const x = pad + (i / (vals.length - 1)) * (w - pad * 2);
    const y = pad + (1 - (v - min) / rng) * (h - pad * 2);
    return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
}

// Export
Object.assign(window, { HERMES_DATA, fmtUsd, fmtPct, fmtNum, genCandles, sparkPath });
