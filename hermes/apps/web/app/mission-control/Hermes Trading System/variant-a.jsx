/* Variant A — Institutional. Ultra-clean, hairline rules, near-monochrome with a single cool accent. */
const { useMemo } = React;

function A_Chip({ children, tone = "mute" }) {
  const toneMap = {
    mute:  { c: "var(--a-muted)", b: "var(--a-line)" },
    gain:  { c: "var(--a-gain)",  b: "color-mix(in oklch, var(--a-gain) 35%, transparent)" },
    loss:  { c: "var(--a-loss)",  b: "color-mix(in oklch, var(--a-loss) 35%, transparent)" },
    warn:  { c: "var(--a-warn)",  b: "color-mix(in oklch, var(--a-warn) 35%, transparent)" },
    info:  { c: "var(--a-accent)",b: "color-mix(in oklch, var(--a-accent) 35%, transparent)" },
    solid: { c: "var(--a-bg)", b: "var(--a-fg)", bg: "var(--a-fg)" },
  };
  const s = toneMap[tone] || toneMap.mute;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      height: 18, padding: "0 6px",
      fontSize: 10, fontFamily: "var(--a-mono)", letterSpacing: "0.1em",
      color: s.c, border: `1px solid ${s.b}`, background: s.bg || "transparent",
      textTransform: "uppercase",
    }}>{children}</span>
  );
}

function A_Panel({ title, eyebrow, action, children, style }) {
  return (
    <section style={{
      display: "flex", flexDirection: "column",
      background: "var(--a-panel)", border: "1px solid var(--a-line)",
      ...style,
    }}>
      <header style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 14px", borderBottom: "1px solid var(--a-line)",
        minHeight: 38,
      }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          {eyebrow && <span style={{
            fontFamily: "var(--a-mono)", fontSize: 10, letterSpacing: "0.14em",
            color: "var(--a-muted)", textTransform: "uppercase",
          }}>{eyebrow}</span>}
          <h3 style={{ margin: 0, fontSize: 13, fontWeight: 500, letterSpacing: "-0.005em" }}>{title}</h3>
        </div>
        {action}
      </header>
      <div style={{ flex: 1, minHeight: 0 }}>{children}</div>
    </section>
  );
}

function A_TopBar() {
  const { session } = HERMES_DATA;
  const now = session.loggedAt;
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "auto 1fr auto",
      alignItems: "center",
      gap: 18,
      padding: "0 18px",
      height: 48,
      borderBottom: "1px solid var(--a-line)",
      background: "var(--a-panel)",
    }}>
      {/* Brand */}
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{
          width: 20, height: 20, border: "1px solid var(--a-fg)",
          display: "grid", placeItems: "center", fontFamily: "var(--a-mono)",
          fontSize: 11, fontWeight: 600,
        }}>H</div>
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.15 }}>
          <span style={{ fontSize: 12, fontWeight: 500 }}>Hermes</span>
          <span style={{ fontFamily: "var(--a-mono)", fontSize: 9, letterSpacing: "0.14em", color: "var(--a-muted)", textTransform: "uppercase" }}>
            Mission Control
          </span>
        </div>
        <nav style={{ marginLeft: 18, display: "flex", gap: 2, fontFamily: "var(--a-mono)", fontSize: 11 }}>
          {["Dashboard", "Mission", "Research", "Execution", "Agents", "Journal"].map((t, i) => (
            <span key={t} style={{
              padding: "6px 10px",
              color: i === 1 ? "var(--a-fg)" : "var(--a-muted)",
              borderBottom: i === 1 ? "1px solid var(--a-fg)" : "1px solid transparent",
              cursor: "pointer",
            }}>{t}</span>
          ))}
        </nav>
      </div>

      {/* Market regime strip */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "center", gap: 18,
        fontFamily: "var(--a-mono)", fontSize: 11, color: "var(--a-muted)",
      }}>
        <span><span style={{ color: "var(--a-fg)" }}>BTC</span> 91,821.40 <span style={{ color: "var(--a-gain)" }}>+1.24%</span></span>
        <span style={{ opacity: 0.4 }}>│</span>
        <span><span style={{ color: "var(--a-fg)" }}>ETH</span> 3,358.20 <span style={{ color: "var(--a-gain)" }}>+1.87%</span></span>
        <span style={{ opacity: 0.4 }}>│</span>
        <span><span style={{ color: "var(--a-fg)" }}>SOL</span> 182.40 <span style={{ color: "var(--a-loss)" }}>−0.42%</span></span>
        <span style={{ opacity: 0.4 }}>│</span>
        <span><span style={{ color: "var(--a-fg)" }}>DXY</span> 104.21 <span style={{ color: "var(--a-loss)" }}>−0.08%</span></span>
      </div>

      {/* Session */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, fontFamily: "var(--a-mono)", fontSize: 11 }}>
        <A_Chip tone="gain">● LIVE</A_Chip>
        <span style={{ color: "var(--a-muted)" }}>{session.regime}</span>
        <span style={{ color: "var(--a-muted)" }}>│</span>
        <span>{session.operator} · {session.desk}</span>
        <span style={{ color: "var(--a-fg)" }}>{now.slice(11, 19)} UTC</span>
        <button style={{
          height: 26, padding: "0 10px", fontFamily: "var(--a-mono)", fontSize: 10,
          letterSpacing: "0.12em", textTransform: "uppercase",
          border: "1px solid var(--a-loss)", color: "var(--a-loss)",
          background: "transparent", cursor: "pointer",
        }}>Kill ⌘K</button>
      </div>
    </div>
  );
}

// Big KPI label/value block
function A_Kpi({ label, value, sub, tone }) {
  const toneC = tone === "gain" ? "var(--a-gain)" : tone === "loss" ? "var(--a-loss)" : "var(--a-fg)";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
      <span style={{
        fontFamily: "var(--a-mono)", fontSize: 10, letterSpacing: "0.12em",
        color: "var(--a-muted)", textTransform: "uppercase",
      }}>{label}</span>
      <span style={{ fontFamily: "var(--a-mono)", fontSize: 20, fontWeight: 500, color: toneC, letterSpacing: "-0.01em" }}>
        {value}
      </span>
      {sub && <span style={{ fontFamily: "var(--a-mono)", fontSize: 10, color: "var(--a-muted)" }}>{sub}</span>}
    </div>
  );
}

function A_PortfolioCommand() {
  const p = HERMES_DATA.portfolio;
  const closes = useMemo(() => genCandles(60, 11, 2780000, 8000).map(c => c.c), []);
  const path = sparkPath(closes, 300, 60);
  return (
    <A_Panel title="Portfolio Command" eyebrow="01"
      action={<div style={{ display: "flex", gap: 6 }}>
        <A_Chip>1D</A_Chip><A_Chip tone="info">1W</A_Chip><A_Chip>1M</A_Chip><A_Chip>ALL</A_Chip>
      </div>}>
      <div style={{ padding: "16px 18px", display: "grid", gap: 16 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 20 }}>
          <A_Kpi label="Equity" value={fmtUsd(p.equity)} sub={`${fmtUsd(p.equityDelta, { sign: true })}  ${fmtPct(p.equityDeltaPct)}`} />
          <A_Kpi label="Day P&L" value={fmtUsd(p.dayPnL, { sign: true })} sub={fmtPct(p.equityDeltaPct)} tone="gain" />
          <A_Kpi label="Week P&L" value={fmtUsd(p.weekPnL, { sign: true })} sub="+2.31%" tone="gain" />
          <A_Kpi label="Month P&L" value={fmtUsd(p.monthPnL, { sign: true })} sub="+5.28%" tone="gain" />
        </div>

        <svg viewBox="0 0 300 60" style={{ width: "100%", height: 60 }}>
          <defs>
            <linearGradient id="a-eq" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--a-fg)" stopOpacity="0.18" />
              <stop offset="100%" stopColor="var(--a-fg)" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={`${path} L 298 58 L 2 58 Z`} fill="url(#a-eq)" />
          <path d={path} fill="none" stroke="var(--a-fg)" strokeWidth="1" />
        </svg>

        <div style={{
          display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 0,
          borderTop: "1px solid var(--a-line)", paddingTop: 12,
        }}>
          {[
            ["Cash",        fmtUsd(p.cash, { compact: true })],
            ["Exposure",    fmtUsd(p.exposure, { compact: true })],
            ["Leverage",    `${p.leverage.toFixed(2)}×`],
            ["Max DD",      fmtPct(p.drawdown)],
            ["VaR 95%",     fmtUsd(p.var95, { compact: true, sign: true })],
          ].map(([k, v]) => (
            <div key={k} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <span style={{ fontFamily: "var(--a-mono)", fontSize: 10, color: "var(--a-muted)", textTransform: "uppercase", letterSpacing: "0.12em" }}>{k}</span>
              <span style={{ fontFamily: "var(--a-mono)", fontSize: 13 }}>{v}</span>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", gap: 8, paddingTop: 4 }}>
          {["Rebalance", "Reduce Risk", "Flatten", "Sync Ledger"].map(t => (
            <button key={t} style={{
              height: 28, padding: "0 12px", fontFamily: "var(--a-mono)", fontSize: 10,
              letterSpacing: "0.12em", textTransform: "uppercase",
              border: "1px solid var(--a-line)", background: "transparent", color: "var(--a-fg)",
              cursor: "pointer",
            }}>{t}</button>
          ))}
        </div>
      </div>
    </A_Panel>
  );
}

function A_MarketFocus() {
  const f = HERMES_DATA.focus;
  const candles = useMemo(() => genCandles(70, 31, 89500, 420), []);
  const vals = candles.flatMap(c => [c.h, c.l]);
  const min = Math.min(...vals), max = Math.max(...vals), rng = max - min;
  const w = 720, h = 280, padL = 0, padR = 48, padT = 10, padB = 22;
  const iw = w - padL - padR, ih = h - padT - padB;
  const cw = iw / candles.length;

  return (
    <A_Panel title="Market Focus" eyebrow="02"
      action={
        <div style={{ display: "flex", gap: 6, fontFamily: "var(--a-mono)", fontSize: 10 }}>
          {["1m","5m","15m","1H","4H","1D"].map((t, i) => (
            <span key={t} style={{
              padding: "2px 6px",
              color: i === 4 ? "var(--a-fg)" : "var(--a-muted)",
              borderBottom: i === 4 ? "1px solid var(--a-fg)" : "1px solid transparent",
              cursor: "pointer",
            }}>{t}</span>
          ))}
        </div>
      }>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 220px", gap: 0, height: "100%" }}>
        {/* Chart */}
        <div style={{ padding: "14px 0 14px 18px", borderRight: "1px solid var(--a-line)" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 14, marginBottom: 10 }}>
            <span style={{ fontFamily: "var(--a-mono)", fontSize: 18, fontWeight: 500 }}>{f.symbol}</span>
            <span style={{ fontFamily: "var(--a-mono)", fontSize: 22, fontWeight: 500 }}>{f.last.toLocaleString()}</span>
            <span style={{ fontFamily: "var(--a-mono)", fontSize: 12, color: "var(--a-gain)" }}>
              +{(f.last * f.change / 100).toFixed(2)}  {fmtPct(f.change)}
            </span>
            <span style={{ fontFamily: "var(--a-mono)", fontSize: 11, color: "var(--a-muted)", marginLeft: "auto", paddingRight: 18 }}>
              24H {f.low24.toLocaleString()} – {f.high24.toLocaleString()}  ·  VOL {f.vol24}
            </span>
          </div>
          <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: 260, display: "block" }}>
            {/* Grid */}
            {[0.25, 0.5, 0.75].map(p => (
              <line key={p} x1={padL} x2={w - padR} y1={padT + ih * p} y2={padT + ih * p}
                stroke="var(--a-line)" strokeDasharray="2 3" />
            ))}
            {/* Key levels */}
            {Object.entries(f.levels).map(([k, v]) => {
              const y = padT + (1 - (v - min) / rng) * ih;
              const isR = k.startsWith("r"), isS = k.startsWith("s");
              const col = isR ? "var(--a-loss)" : isS ? "var(--a-gain)" : "var(--a-accent)";
              return (
                <g key={k}>
                  <line x1={padL} x2={w - padR} y1={y} y2={y} stroke={col} strokeOpacity="0.35" strokeDasharray="1 3" />
                  <text x={w - padR + 4} y={y + 3} fill={col} fontFamily="var(--a-mono)" fontSize="9">
                    {k.toUpperCase()} {v.toLocaleString()}
                  </text>
                </g>
              );
            })}
            {/* Candles */}
            {candles.map((c, i) => {
              const x = padL + i * cw + cw * 0.15;
              const bw = cw * 0.7;
              const up = c.c >= c.o;
              const col = up ? "var(--a-gain)" : "var(--a-loss)";
              const y = (v) => padT + (1 - (v - min) / rng) * ih;
              const hi = y(c.h), lo = y(c.l), op = y(c.o), cl = y(c.c);
              const top = Math.min(op, cl), bh = Math.max(1, Math.abs(cl - op));
              return (
                <g key={i}>
                  <line x1={x + bw/2} x2={x + bw/2} y1={hi} y2={lo} stroke={col} strokeWidth="1" />
                  <rect x={x} y={top} width={bw} height={bh} fill={up ? "transparent" : col} stroke={col} strokeWidth="1" />
                </g>
              );
            })}
            {/* Last price */}
            {(() => {
              const y = padT + (1 - (f.last - min) / rng) * ih;
              return (
                <g>
                  <line x1={padL} x2={w - padR} y1={y} y2={y} stroke="var(--a-fg)" strokeDasharray="4 3" strokeOpacity="0.5" />
                  <rect x={w - padR} y={y - 8} width={padR} height={16} fill="var(--a-fg)" />
                  <text x={w - padR + 4} y={y + 3} fill="var(--a-bg)" fontFamily="var(--a-mono)" fontSize="10" fontWeight="600">
                    {f.last.toLocaleString()}
                  </text>
                </g>
              );
            })()}
          </svg>
        </div>

        {/* Right meta */}
        <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <span style={{ fontFamily: "var(--a-mono)", fontSize: 10, color: "var(--a-muted)", letterSpacing: "0.14em", textTransform: "uppercase" }}>AI Read</span>
            <p style={{ margin: "6px 0 0", fontSize: 12, lineHeight: 1.5, color: "var(--a-fg)" }}>
              {f.notes}
            </p>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {[
              ["Trend",  f.trend,       "gain"],
              ["RSI 14", f.rsi,         "mute"],
              ["ATR",    f.atr,         "mute"],
              ["24H Chg",fmtPct(f.change24), "gain"],
            ].map(([k, v, tone]) => (
              <div key={k} style={{ borderTop: "1px solid var(--a-line)", paddingTop: 8 }}>
                <div style={{ fontFamily: "var(--a-mono)", fontSize: 9, color: "var(--a-muted)", letterSpacing: "0.14em", textTransform: "uppercase" }}>{k}</div>
                <div style={{ fontFamily: "var(--a-mono)", fontSize: 13, color: tone === "gain" ? "var(--a-gain)" : "var(--a-fg)" }}>{v}</div>
              </div>
            ))}
          </div>
          <div>
            <span style={{ fontFamily: "var(--a-mono)", fontSize: 10, color: "var(--a-muted)", letterSpacing: "0.14em", textTransform: "uppercase" }}>Key Levels</span>
            <div style={{ marginTop: 6, display: "grid", gap: 4, fontFamily: "var(--a-mono)", fontSize: 11 }}>
              {[
                ["R2", f.levels.r2, "var(--a-loss)"],
                ["R1", f.levels.r1, "var(--a-loss)"],
                ["PP", f.levels.pivot, "var(--a-accent)"],
                ["S1", f.levels.s1, "var(--a-gain)"],
                ["S2", f.levels.s2, "var(--a-gain)"],
              ].map(([k, v, c]) => (
                <div key={k} style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: c }}>{k}</span>
                  <span>{v.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </A_Panel>
  );
}

function A_Watchlist() {
  return (
    <A_Panel title="Watchlist" eyebrow="W"
      action={<span style={{ fontFamily: "var(--a-mono)", fontSize: 10, color: "var(--a-muted)" }}>8 / 24</span>}>
      <div style={{ padding: "4px 0" }}>
        {HERMES_DATA.watchlist.map((r, i) => {
          const closes = genCandles(20, 7 + i, r.px, r.px * 0.02).map(c => c.c);
          const path = sparkPath(closes, 64, 18);
          const up = r.chg > 0;
          return (
            <div key={r.sym} style={{
              display: "grid", gridTemplateColumns: "80px 1fr 64px 70px",
              alignItems: "center", gap: 10, padding: "7px 14px",
              borderTop: i === 0 ? "none" : "1px solid var(--a-line)",
              fontFamily: "var(--a-mono)", fontSize: 11,
            }}>
              <span>{r.sym.replace("USDT", "")}<span style={{ color: "var(--a-muted)" }}>/USDT</span></span>
              <span style={{ textAlign: "right" }}>{r.px.toLocaleString()}</span>
              <svg viewBox="0 0 64 18" style={{ width: 64, height: 18 }}>
                <path d={path} fill="none" stroke={up ? "var(--a-gain)" : "var(--a-loss)"} strokeWidth="1" />
              </svg>
              <span style={{ textAlign: "right", color: up ? "var(--a-gain)" : "var(--a-loss)" }}>{fmtPct(r.chg)}</span>
            </div>
          );
        })}
      </div>
    </A_Panel>
  );
}

function A_Positions() {
  const p = HERMES_DATA.positions;
  return (
    <A_Panel title="Positions" eyebrow="P" action={<A_Chip>{p.length} OPEN</A_Chip>}>
      <div>
        <div style={{
          display: "grid", gridTemplateColumns: "1.1fr 0.5fr 0.9fr 0.9fr 0.7fr 1.2fr",
          gap: 10, padding: "8px 14px", borderBottom: "1px solid var(--a-line)",
          fontFamily: "var(--a-mono)", fontSize: 9, color: "var(--a-muted)",
          letterSpacing: "0.14em", textTransform: "uppercase",
        }}>
          <span>Symbol</span><span>Side</span><span style={{ textAlign: "right" }}>Notional</span>
          <span style={{ textAlign: "right" }}>P&L</span><span style={{ textAlign: "right" }}>Weight</span>
          <span>Thesis</span>
        </div>
        {p.map((r, i) => (
          <div key={r.sym} style={{
            display: "grid", gridTemplateColumns: "1.1fr 0.5fr 0.9fr 0.9fr 0.7fr 1.2fr",
            gap: 10, padding: "8px 14px",
            borderTop: i === 0 ? "none" : "1px solid var(--a-line)",
            fontFamily: "var(--a-mono)", fontSize: 11,
            background: i === 0 ? "color-mix(in oklch, var(--a-fg) 3%, transparent)" : "transparent",
          }}>
            <span style={{ fontWeight: 500 }}>{r.sym.replace("USDT","")}<span style={{ color: "var(--a-muted)" }}>/USDT</span></span>
            <span style={{ color: r.side === "LONG" ? "var(--a-gain)" : "var(--a-loss)" }}>{r.side}</span>
            <span style={{ textAlign: "right" }}>{fmtUsd(r.notional, { compact: true })}</span>
            <span style={{ textAlign: "right", color: r.pnl >= 0 ? "var(--a-gain)" : "var(--a-loss)" }}>
              {fmtUsd(r.pnl, { sign: true })} <span style={{ color: "var(--a-muted)" }}>{fmtPct(r.pnlPct)}</span>
            </span>
            <span style={{ textAlign: "right" }}>
              <span style={{ display: "inline-block", width: 32, height: 4, background: "var(--a-line)", position: "relative", verticalAlign: "middle", marginRight: 6 }}>
                <span style={{ position: "absolute", left: 0, top: 0, height: "100%", width: `${r.weight}%`, background: "var(--a-fg)" }} />
              </span>
              {r.weight.toFixed(1)}%
            </span>
            <span style={{ color: "var(--a-muted)", fontSize: 10.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.thesis}</span>
          </div>
        ))}
      </div>
    </A_Panel>
  );
}

function A_ExecutionFeed() {
  const kindColor = { FILL: "var(--a-gain)", SIGNAL: "var(--a-accent)", ALERT: "var(--a-warn)", REJECT: "var(--a-loss)", RESEARCH: "var(--a-muted)" };
  return (
    <A_Panel title="Execution Feed" eyebrow="03"
      action={<div style={{ display: "flex", gap: 6 }}>
        <A_Chip tone="info">ALL</A_Chip><A_Chip>FILL</A_Chip><A_Chip>SIGNAL</A_Chip><A_Chip>ALERT</A_Chip>
      </div>}>
      <div>
        {HERMES_DATA.tape.map((r, i) => (
          <div key={i} style={{
            display: "grid", gridTemplateColumns: "58px 54px 90px 48px 1fr 90px",
            gap: 10, padding: "8px 14px",
            borderTop: i === 0 ? "none" : "1px solid var(--a-line)",
            fontFamily: "var(--a-mono)", fontSize: 11,
          }}>
            <span style={{ color: "var(--a-muted)" }}>{r.t}</span>
            <span style={{ color: kindColor[r.kind] }}>{r.kind}</span>
            <span>{r.sym}</span>
            <span style={{ color: r.side === "BUY" ? "var(--a-gain)" : r.side === "SELL" ? "var(--a-loss)" : "var(--a-muted)" }}>{r.side}</span>
            <span style={{ color: "var(--a-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.note}</span>
            <span style={{ textAlign: "right" }}>
              {r.qty ? <span style={{ color: "var(--a-muted)" }}>{fmtNum(r.qty)} @ </span> : null}
              {r.px != null ? r.px.toLocaleString() : "—"}
            </span>
          </div>
        ))}
      </div>
    </A_Panel>
  );
}

function A_ResearchPipeline() {
  return (
    <A_Panel title="Research Pipeline" eyebrow="04"
      action={<A_Chip>{HERMES_DATA.lanes.reduce((a, l) => a + l.count, 0)} ACTIVE</A_Chip>}>
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(5, 1fr)",
      }}>
        {HERMES_DATA.lanes.map((lane, li) => (
          <div key={lane.name} style={{
            borderRight: li < 4 ? "1px solid var(--a-line)" : "none",
            display: "flex", flexDirection: "column",
          }}>
            <div style={{
              padding: "10px 12px", display: "flex", justifyContent: "space-between", alignItems: "center",
              borderBottom: "1px solid var(--a-line)",
            }}>
              <span style={{ fontFamily: "var(--a-mono)", fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--a-muted)" }}>{lane.name}</span>
              <span style={{ fontFamily: "var(--a-mono)", fontSize: 10, color: "var(--a-fg)" }}>{lane.count}</span>
            </div>
            <div style={{ padding: 8, display: "flex", flexDirection: "column", gap: 6 }}>
              {lane.items.map((it, i) => (
                <div key={i} style={{
                  padding: "8px 10px", border: "1px solid var(--a-line)",
                  display: "flex", flexDirection: "column", gap: 4,
                  background: "var(--a-bg)",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--a-mono)", fontSize: 11 }}>
                    <span style={{ fontWeight: 500 }}>{it.sym.replace("USDT","")}</span>
                    {it.conf != null && <span style={{ color: it.conf > 0.7 ? "var(--a-gain)" : it.conf > 0.5 ? "var(--a-fg)" : "var(--a-muted)" }}>
                      {it.conf.toFixed(2)}
                    </span>}
                  </div>
                  <div style={{ fontSize: 10.5, color: "var(--a-muted)", lineHeight: 1.4 }}>{it.thesis}</div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--a-mono)", fontSize: 9, color: "var(--a-muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                    <span>{it.agent}</span><span>{it.age}</span>
                  </div>
                </div>
              ))}
              {lane.items.length === 0 && (
                <div style={{ fontFamily: "var(--a-mono)", fontSize: 10, color: "var(--a-muted)", padding: "6px 2px" }}>—</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </A_Panel>
  );
}

function A_RiskPosture() {
  const r = HERMES_DATA.risk;
  return (
    <A_Panel title="Risk Posture" eyebrow="R"
      action={<A_Chip tone={r.posture === "NORMAL" ? "gain" : "warn"}>{r.posture}</A_Chip>}>
      <div style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: 14 }}>
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--a-mono)", fontSize: 10, color: "var(--a-muted)", textTransform: "uppercase", letterSpacing: "0.12em" }}>
            <span>Gross Exposure</span><span>{r.exposurePct.toFixed(1)}% / {r.maxExposurePct}%</span>
          </div>
          <div style={{ marginTop: 6, height: 4, background: "var(--a-line)", position: "relative" }}>
            <div style={{ position: "absolute", left: 0, top: 0, height: "100%", width: `${r.exposurePct}%`, background: "var(--a-warn)" }} />
          </div>
        </div>
        <div>
          <div style={{ fontFamily: "var(--a-mono)", fontSize: 10, color: "var(--a-muted)", textTransform: "uppercase", letterSpacing: "0.12em" }}>Concentration</div>
          <div style={{ fontFamily: "var(--a-mono)", fontSize: 12, marginTop: 4 }}>{r.concentration}</div>
        </div>
        <div>
          <div style={{ fontFamily: "var(--a-mono)", fontSize: 10, color: "var(--a-muted)", textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 6 }}>Active Alerts</div>
          {r.alerts.map((a, i) => (
            <div key={i} style={{ display: "flex", gap: 8, padding: "6px 0", fontSize: 11, borderTop: i > 0 ? "1px solid var(--a-line)" : "none" }}>
              <span style={{
                width: 6, height: 6, borderRadius: 999, marginTop: 5,
                background: a.level === "amber" ? "var(--a-warn)" : "var(--a-accent)",
              }} />
              <span style={{ color: "var(--a-fg)" }}>{a.msg}</span>
            </div>
          ))}
        </div>
      </div>
    </A_Panel>
  );
}

function A_ApprovalQueue() {
  return (
    <A_Panel title="Approval Queue" eyebrow="Q"
      action={<A_Chip tone="warn">{HERMES_DATA.approvals.length} PENDING</A_Chip>}>
      <div>
        {HERMES_DATA.approvals.map((a, i) => (
          <div key={i} style={{
            padding: "12px 14px", borderTop: i === 0 ? "none" : "1px solid var(--a-line)",
            display: "flex", flexDirection: "column", gap: 8,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontFamily: "var(--a-mono)", fontSize: 13, fontWeight: 500 }}>
                <span style={{ color: a.side === "BUY" ? "var(--a-gain)" : "var(--a-loss)" }}>{a.side}</span>{" "}
                {a.sym.replace("USDT","")} · <span style={{ color: "var(--a-muted)" }}>{a.size}</span>
              </span>
              <span style={{ fontFamily: "var(--a-mono)", fontSize: 10, color: "var(--a-warn)" }}>expires {a.expiresIn}</span>
            </div>
            <div style={{ fontSize: 11, color: "var(--a-muted)", lineHeight: 1.4 }}>
              {a.reason} · conf <span style={{ color: "var(--a-fg)", fontFamily: "var(--a-mono)" }}>{a.conf.toFixed(2)}</span>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button style={{ flex: 1, height: 28, fontFamily: "var(--a-mono)", fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase",
                border: "1px solid var(--a-gain)", color: "var(--a-bg)", background: "var(--a-gain)", cursor: "pointer" }}>Approve</button>
              <button style={{ flex: 1, height: 28, fontFamily: "var(--a-mono)", fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase",
                border: "1px solid var(--a-line)", color: "var(--a-fg)", background: "transparent", cursor: "pointer" }}>Modify</button>
              <button style={{ flex: 1, height: 28, fontFamily: "var(--a-mono)", fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase",
                border: "1px solid var(--a-loss)", color: "var(--a-loss)", background: "transparent", cursor: "pointer" }}>Reject</button>
            </div>
          </div>
        ))}
      </div>
    </A_Panel>
  );
}

function A_OperationalTimeline() {
  const t = HERMES_DATA.timeline;
  const tone = { gain: "var(--a-gain)", loss: "var(--a-loss)", warn: "var(--a-warn)", info: "var(--a-accent)", mute: "var(--a-muted)" };
  return (
    <A_Panel title="Operational Timeline" eyebrow="T">
      <div style={{ padding: "10px 14px" }}>
        {t.map((r, i) => (
          <div key={i} style={{
            display: "grid", gridTemplateColumns: "44px 16px 1fr",
            gap: 10, padding: "7px 0", fontFamily: "var(--a-mono)", fontSize: 11,
            borderTop: i === 0 ? "none" : "1px solid var(--a-line)",
          }}>
            <span style={{ color: "var(--a-muted)" }}>{r.t}</span>
            <span style={{ position: "relative" }}>
              <span style={{
                position: "absolute", left: 4, top: 5, width: 6, height: 6, borderRadius: 999,
                background: tone[r.tone],
              }} />
              {i < t.length - 1 && (
                <span style={{ position: "absolute", left: 6.5, top: 12, width: 1, height: 18, background: "var(--a-line)" }} />
              )}
            </span>
            <span>
              <span style={{ color: tone[r.tone], marginRight: 6 }}>{r.label}</span>
              <span style={{ color: "var(--a-fg)" }}>{r.detail}</span>
            </span>
          </div>
        ))}
      </div>
    </A_Panel>
  );
}

function A_StatusStrip() {
  return (
    <div style={{
      height: 26, display: "flex", alignItems: "center", gap: 18,
      padding: "0 18px", borderTop: "1px solid var(--a-line)",
      background: "var(--a-panel)",
      fontFamily: "var(--a-mono)", fontSize: 10, color: "var(--a-muted)",
      letterSpacing: "0.1em", textTransform: "uppercase",
    }}>
      <span><span style={{ color: "var(--a-gain)" }}>●</span> API 12ms</span>
      <span><span style={{ color: "var(--a-gain)" }}>●</span> WS stable</span>
      <span><span style={{ color: "var(--a-gain)" }}>●</span> Bitmart auth ok</span>
      <span>Kill switch: armed</span>
      <span>Agents: 6 online</span>
      <span style={{ marginLeft: "auto" }}>Build 2026.04.23-r17</span>
      <span>Tick 0.7s</span>
    </div>
  );
}

function VariantA() {
  return (
    <div style={{
      width: 1440, height: 1024, display: "grid",
      gridTemplateRows: "48px 1fr 26px",
      background: "var(--a-bg)", color: "var(--a-fg)",
      fontFamily: "var(--a-sans)",
      "--a-bg": "#0d0e10",
      "--a-panel": "#131418",
      "--a-fg": "#e8e9ec",
      "--a-muted": "#7d8088",
      "--a-line": "#23252b",
      "--a-accent": "#6aa7ff",
      "--a-gain": "#5bbf88",
      "--a-loss": "#d46a6a",
      "--a-warn": "#c9a04a",
      "--a-mono": "'JetBrains Mono', ui-monospace, monospace",
      "--a-sans": "'Inter Tight', 'Inter', system-ui, sans-serif",
    }}>
      <A_TopBar />
      <div style={{
        display: "grid",
        gridTemplateColumns: "248px minmax(0, 1fr) 320px",
        gap: 0, minHeight: 0,
      }}>
        {/* Left rail */}
        <div style={{ borderRight: "1px solid var(--a-line)", display: "grid", gridTemplateRows: "auto 1fr", minHeight: 0 }}>
          <A_Watchlist />
          <A_RiskPosture />
        </div>

        {/* Center */}
        <div style={{ display: "grid", gridTemplateRows: "auto auto 1fr", gap: 0, minHeight: 0 }}>
          <A_PortfolioCommand />
          <A_MarketFocus />
          <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", borderTop: "1px solid var(--a-line)", minHeight: 0 }}>
            <A_Positions />
            <div style={{ borderLeft: "1px solid var(--a-line)" }}>
              <A_ExecutionFeed />
            </div>
          </div>
        </div>

        {/* Right rail */}
        <div style={{ borderLeft: "1px solid var(--a-line)", display: "grid", gridTemplateRows: "auto auto 1fr", minHeight: 0 }}>
          <A_ApprovalQueue />
          <A_OperationalTimeline />
          <A_ResearchPipeline />
        </div>
      </div>
      <A_StatusStrip />
    </div>
  );
}

Object.assign(window, { VariantA });
