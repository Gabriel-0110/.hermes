/* Variant B — Mission Ops. Cinematic graphite, cyan status glow, tactical brackets and indexing. */
const { useMemo: useMemoB } = React;

function B_Bracket({ children, tone = "mute" }) {
  const c = {
    mute: "var(--b-muted)", accent: "var(--b-accent)", gain: "var(--b-gain)",
    loss: "var(--b-loss)", warn: "var(--b-warn)", fg: "var(--b-fg)",
  }[tone] || "var(--b-muted)";
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      fontFamily: "var(--b-mono)", fontSize: 10, letterSpacing: "0.16em",
      color: c, textTransform: "uppercase",
    }}>
      <span style={{ opacity: 0.5 }}>[</span>
      {children}
      <span style={{ opacity: 0.5 }}>]</span>
    </span>
  );
}

function B_Module({ code, title, subtitle, status, right, children, style }) {
  return (
    <section style={{
      position: "relative",
      background: "var(--b-panel)",
      border: "1px solid var(--b-line)",
      display: "flex", flexDirection: "column",
      ...style,
    }}>
      {/* Corner ticks */}
      {[[0,0],[1,0],[0,1],[1,1]].map(([x,y]) => (
        <span key={`${x}${y}`} style={{
          position: "absolute",
          left: x ? "auto" : -1, right: x ? -1 : "auto",
          top: y ? "auto" : -1, bottom: y ? -1 : "auto",
          width: 6, height: 6,
          borderLeft: x ? "none" : `1px solid var(--b-accent)`,
          borderRight: x ? `1px solid var(--b-accent)` : "none",
          borderTop: y ? "none" : `1px solid var(--b-accent)`,
          borderBottom: y ? `1px solid var(--b-accent)` : "none",
          opacity: 0.9,
        }} />
      ))}
      <header style={{
        display: "flex", alignItems: "center", gap: 12,
        padding: "10px 14px", borderBottom: "1px solid var(--b-line)",
        minHeight: 40, background: "var(--b-panel-hi)",
      }}>
        <span style={{
          fontFamily: "var(--b-mono)", fontSize: 10, color: "var(--b-accent)",
          letterSpacing: "0.18em", textTransform: "uppercase",
        }}>/{code}</span>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, flex: 1, minWidth: 0 }}>
          <h3 style={{ margin: 0, fontSize: 13, fontWeight: 500, letterSpacing: "0.01em", textTransform: "uppercase" }}>{title}</h3>
          {subtitle && <span style={{ fontFamily: "var(--b-mono)", fontSize: 10, color: "var(--b-muted)", letterSpacing: "0.1em" }}>{subtitle}</span>}
        </div>
        {status && <B_Bracket tone="gain">{status}</B_Bracket>}
        {right}
      </header>
      <div style={{ flex: 1, minHeight: 0 }}>{children}</div>
    </section>
  );
}

function B_HudRule() {
  // Thin cyan guide above topbar — mission HUD feel
  return (
    <div style={{ height: 2, background: "linear-gradient(90deg, transparent, var(--b-accent), transparent)", opacity: 0.6 }} />
  );
}

function B_TopBar() {
  const s = HERMES_DATA.session;
  return (
    <div style={{
      height: 60, display: "grid",
      gridTemplateColumns: "auto 1fr auto",
      alignItems: "center", gap: 18, padding: "0 18px",
      borderBottom: "1px solid var(--b-line)",
      background: "var(--b-panel-hi)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        {/* Sigil */}
        <svg width="28" height="28" viewBox="0 0 28 28">
          <rect x="1" y="1" width="26" height="26" fill="none" stroke="var(--b-accent)" strokeOpacity="0.5" />
          <rect x="5" y="5" width="18" height="18" fill="none" stroke="var(--b-accent)" />
          <path d="M 9 14 L 14 9 L 19 14 L 14 19 Z" fill="var(--b-accent)" fillOpacity="0.25" stroke="var(--b-accent)" />
        </svg>
        <div style={{ lineHeight: 1.1 }}>
          <div style={{ fontFamily: "var(--b-mono)", fontSize: 10, color: "var(--b-accent)", letterSpacing: "0.22em", textTransform: "uppercase" }}>Hermes · Mission Ops</div>
          <div style={{ fontSize: 14, fontWeight: 500, letterSpacing: "0.02em" }}>Command Surface / OPER-{s.desk.split("-")[1]}</div>
        </div>
      </div>

      {/* HUD segments */}
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 0,
        border: "1px solid var(--b-line)",
        background: "var(--b-bg)",
      }}>
        {[
          ["Regime", s.regime, "gain"],
          ["Mode",   s.mode, "accent"],
          ["Latency","WS 18ms / API 12ms", "accent"],
          ["Window", "08:41:12 UTC  ·  T+2h 43m", "fg"],
        ].map(([k, v, tone], i, arr) => (
          <div key={k} style={{
            padding: "8px 12px",
            borderRight: i < arr.length - 1 ? "1px solid var(--b-line)" : "none",
          }}>
            <div style={{ fontFamily: "var(--b-mono)", fontSize: 9, color: "var(--b-muted)", letterSpacing: "0.18em", textTransform: "uppercase" }}>{k}</div>
            <div style={{
              fontFamily: "var(--b-mono)", fontSize: 12, marginTop: 2,
              color: tone === "gain" ? "var(--b-gain)" : tone === "accent" ? "var(--b-accent)" : "var(--b-fg)",
            }}>{v}</div>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <B_Bracket tone="gain">● ARMED</B_Bracket>
        <span style={{ fontFamily: "var(--b-mono)", fontSize: 11, color: "var(--b-muted)" }}>{s.operator}</span>
        <button style={{
          height: 32, padding: "0 14px",
          fontFamily: "var(--b-mono)", fontSize: 10, letterSpacing: "0.18em", textTransform: "uppercase",
          color: "var(--b-loss)",
          background: "color-mix(in oklch, var(--b-loss) 10%, transparent)",
          border: "1px solid var(--b-loss)",
          cursor: "pointer",
        }}>◈ KILL · ⌘K</button>
      </div>
    </div>
  );
}

function B_CommandDeck() {
  const p = HERMES_DATA.portfolio;
  // Radial exposure ring
  const exposurePct = p.netExposurePct;
  const R = 44, C = 2 * Math.PI * R;
  return (
    <B_Module code="01" title="Portfolio Command" subtitle="REAL-TIME · SYNCED 0.7S"
      status="NOMINAL"
      right={<div style={{ display: "flex", gap: 6 }}>
        <B_Bracket>1D</B_Bracket><B_Bracket tone="accent">1W</B_Bracket><B_Bracket>1M</B_Bracket>
      </div>}>
      <div style={{ padding: 16, display: "grid", gridTemplateColumns: "112px 1fr", gap: 18, alignItems: "center" }}>
        {/* Exposure ring */}
        <div style={{ position: "relative", width: 112, height: 112 }}>
          <svg viewBox="0 0 112 112" style={{ width: "100%", height: "100%" }}>
            <circle cx="56" cy="56" r={R} fill="none" stroke="var(--b-line)" strokeWidth="6" />
            <circle cx="56" cy="56" r={R} fill="none" stroke="var(--b-accent)" strokeWidth="6"
              strokeDasharray={`${(exposurePct/100)*C} ${C}`} strokeLinecap="butt"
              transform="rotate(-90 56 56)" />
            {/* Tick marks */}
            {Array.from({length: 24}).map((_, i) => {
              const a = (i/24) * Math.PI * 2;
              const x1 = 56 + Math.cos(a) * 52, y1 = 56 + Math.sin(a) * 52;
              const x2 = 56 + Math.cos(a) * 55, y2 = 56 + Math.sin(a) * 55;
              return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--b-muted)" strokeOpacity="0.35" strokeWidth="1" />;
            })}
          </svg>
          <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center" }}>
            <div>
              <div style={{ fontFamily: "var(--b-mono)", fontSize: 9, color: "var(--b-muted)", letterSpacing: "0.16em", textTransform: "uppercase" }}>Exposure</div>
              <div style={{ fontFamily: "var(--b-mono)", fontSize: 22, color: "var(--b-accent)", fontWeight: 500 }}>{exposurePct.toFixed(1)}%</div>
              <div style={{ fontFamily: "var(--b-mono)", fontSize: 9, color: "var(--b-muted)" }}>/100</div>
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, rowGap: 14 }}>
          {[
            ["Equity",      fmtUsd(p.equity, { compact: true }),      fmtUsd(p.equityDelta, { sign: true }) + " · " + fmtPct(p.equityDeltaPct), "fg"],
            ["Day P&L",     fmtUsd(p.dayPnL, { sign: true }),          fmtPct(p.equityDeltaPct),                                                "gain"],
            ["Week P&L",    fmtUsd(p.weekPnL, { sign: true }),         "+2.31% · 7d",                                                           "gain"],
            ["Cash",        fmtUsd(p.cash, { compact: true }),         `${((p.cash/p.equity)*100).toFixed(1)}% idle`,                           "fg"],
            ["Leverage",    `${p.leverage.toFixed(2)}×`,               "target ≤ 1.5×",                                                         "fg"],
            ["VaR 95%",     fmtUsd(p.var95, { compact: true, sign: true }), `DD ${fmtPct(p.drawdown)}`,                                         "warn"],
          ].map(([k, v, s, tone]) => (
            <div key={k}>
              <div style={{ fontFamily: "var(--b-mono)", fontSize: 9, color: "var(--b-muted)", letterSpacing: "0.14em", textTransform: "uppercase" }}>{k}</div>
              <div style={{ fontFamily: "var(--b-mono)", fontSize: 16, color: tone === "gain" ? "var(--b-gain)" : tone === "warn" ? "var(--b-warn)" : "var(--b-fg)", fontWeight: 500 }}>{v}</div>
              <div style={{ fontFamily: "var(--b-mono)", fontSize: 9.5, color: "var(--b-muted)" }}>{s}</div>
            </div>
          ))}
        </div>
      </div>
      <div style={{
        borderTop: "1px solid var(--b-line)",
        padding: "8px 14px",
        display: "flex", gap: 6,
        background: "var(--b-bg)",
      }}>
        {["◆ REBALANCE", "▼ REDUCE", "■ FLATTEN", "↻ SYNC"].map(t => (
          <button key={t} style={{
            flex: 1, height: 28, fontFamily: "var(--b-mono)", fontSize: 10, letterSpacing: "0.14em",
            color: "var(--b-fg)", background: "var(--b-panel)",
            border: "1px solid var(--b-line)", cursor: "pointer",
          }}>{t}</button>
        ))}
      </div>
    </B_Module>
  );
}

function B_MarketFocus() {
  const f = HERMES_DATA.focus;
  const candles = useMemoB(() => genCandles(90, 41, 89500, 420), []);
  const vals = candles.flatMap(c => [c.h, c.l]);
  const min = Math.min(...vals), max = Math.max(...vals), rng = max - min;
  const w = 860, h = 320, padL = 0, padR = 62, padT = 14, padB = 28;
  const iw = w - padL - padR, ih = h - padT - padB;
  const cw = iw / candles.length;
  // Volume lane
  const vh = 40;

  return (
    <B_Module code="02" title="Market Focus" subtitle={`${f.symbol} · 4H · PRIMARY SCOPE`}
      status="TREND UP"
      right={
        <div style={{ display: "flex", gap: 6, alignItems: "center", fontFamily: "var(--b-mono)", fontSize: 10 }}>
          {["1m","5m","15m","1H","4H","1D"].map((t, i) => (
            <span key={t} style={{
              padding: "3px 7px",
              color: i === 4 ? "var(--b-bg)" : "var(--b-muted)",
              background: i === 4 ? "var(--b-accent)" : "transparent",
              letterSpacing: "0.1em", textTransform: "uppercase",
              cursor: "pointer",
            }}>{t}</span>
          ))}
        </div>
      }>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 260px", height: "100%" }}>
        <div style={{ padding: "14px 0 10px 14px", borderRight: "1px solid var(--b-line)", position: "relative" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginBottom: 6, paddingRight: 14 }}>
            <span style={{ fontFamily: "var(--b-mono)", fontSize: 20, fontWeight: 500, letterSpacing: "0.02em" }}>{f.symbol}</span>
            <span style={{ fontFamily: "var(--b-mono)", fontSize: 28, fontWeight: 500, color: "var(--b-fg)" }}>{f.last.toLocaleString()}</span>
            <span style={{ fontFamily: "var(--b-mono)", fontSize: 13, color: "var(--b-gain)" }}>▲ {fmtPct(f.change)}</span>
            <span style={{ fontFamily: "var(--b-mono)", fontSize: 11, color: "var(--b-muted)", marginLeft: "auto" }}>
              24H ↑{f.high24.toLocaleString()} ↓{f.low24.toLocaleString()} · VOL {f.vol24}
            </span>
          </div>

          <svg viewBox={`0 0 ${w} ${h + vh + 10}`} style={{ width: "100%", height: 320, display: "block" }}>
            <defs>
              <pattern id="b-grid" width="60" height="40" patternUnits="userSpaceOnUse">
                <path d="M 60 0 L 0 0 0 40" fill="none" stroke="var(--b-line)" strokeOpacity="0.6" />
              </pattern>
            </defs>
            <rect x="0" y="0" width={w} height={h} fill="url(#b-grid)" />

            {/* Key levels with labels */}
            {Object.entries(f.levels).map(([k, v]) => {
              const y = padT + (1 - (v - min) / rng) * ih;
              const isR = k.startsWith("r"), isPivot = k === "pivot";
              const col = isR ? "var(--b-loss)" : isPivot ? "var(--b-accent)" : "var(--b-gain)";
              return (
                <g key={k}>
                  <line x1={padL} x2={w - padR} y1={y} y2={y} stroke={col} strokeDasharray="3 4" strokeOpacity="0.5" />
                  <rect x={w - padR + 2} y={y - 8} width={padR - 4} height={16} fill="var(--b-panel)" stroke={col} strokeOpacity="0.6" />
                  <text x={w - padR + 6} y={y + 3} fill={col} fontFamily="var(--b-mono)" fontSize="10">
                    {k.toUpperCase()} {v.toLocaleString()}
                  </text>
                </g>
              );
            })}

            {/* Candles */}
            {candles.map((c, i) => {
              const x = padL + i * cw + cw * 0.18;
              const bw = cw * 0.64;
              const up = c.c >= c.o;
              const col = up ? "var(--b-gain)" : "var(--b-loss)";
              const y = (v) => padT + (1 - (v - min) / rng) * ih;
              const hi = y(c.h), lo = y(c.l), op = y(c.o), cl = y(c.c);
              const top = Math.min(op, cl), bh = Math.max(1, Math.abs(cl - op));
              return (
                <g key={i}>
                  <line x1={x + bw/2} x2={x + bw/2} y1={hi} y2={lo} stroke={col} />
                  <rect x={x} y={top} width={bw} height={bh} fill={col} fillOpacity={up ? 0.4 : 0.9} stroke={col} />
                </g>
              );
            })}

            {/* Last price tag */}
            {(() => {
              const y = padT + (1 - (f.last - min) / rng) * ih;
              return (
                <g>
                  <line x1={padL} x2={w - padR} y1={y} y2={y} stroke="var(--b-accent)" strokeDasharray="4 4" />
                  <rect x={w - padR} y={y - 9} width={padR} height={18} fill="var(--b-accent)" />
                  <text x={w - padR + 6} y={y + 4} fill="var(--b-bg)" fontFamily="var(--b-mono)" fontSize="11" fontWeight="700">
                    {f.last.toLocaleString()}
                  </text>
                </g>
              );
            })()}

            {/* Volume lane */}
            <g transform={`translate(0, ${h + 4})`}>
              <rect x="0" y="0" width={w - padR} height={vh} fill="var(--b-bg)" stroke="var(--b-line)" />
              {candles.map((c, i) => {
                const x = padL + i * cw + cw * 0.18;
                const bw = cw * 0.64;
                const vol = Math.abs(c.c - c.o) + (c.h - c.l) * 0.3;
                const maxVol = Math.max(...candles.map(x => Math.abs(x.c - x.o) + (x.h - x.l) * 0.3));
                const bh = (vol / maxVol) * (vh - 4);
                const up = c.c >= c.o;
                return <rect key={i} x={x} y={vh - bh} width={bw} height={bh} fill={up ? "var(--b-gain)" : "var(--b-loss)"} fillOpacity="0.5" />;
              })}
              <text x={6} y={12} fill="var(--b-muted)" fontFamily="var(--b-mono)" fontSize="9" letterSpacing="2">VOL</text>
            </g>
          </svg>
        </div>

        {/* Meta column */}
        <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ border: "1px solid var(--b-line)", padding: 10, background: "var(--b-bg)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <B_Bracket tone="accent">AI · ANALYST-A</B_Bracket>
              <span style={{ fontFamily: "var(--b-mono)", fontSize: 10, color: "var(--b-muted)" }}>CONF 0.74</span>
            </div>
            <p style={{ margin: 0, fontSize: 11.5, lineHeight: 1.55, color: "var(--b-fg)" }}>{f.notes}</p>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {[
              ["Trend",   f.trend,          "gain"],
              ["RSI 14",  f.rsi,            "fg"],
              ["ATR",     f.atr.toFixed(1), "fg"],
              ["24H Δ",   fmtPct(f.change24),"gain"],
              ["Funding", "+0.011%/8h",     "fg"],
              ["OI Δ 1H", "+2.4%",          "gain"],
            ].map(([k, v, tone]) => (
              <div key={k} style={{ border: "1px solid var(--b-line)", padding: "6px 8px" }}>
                <div style={{ fontFamily: "var(--b-mono)", fontSize: 9, color: "var(--b-muted)", letterSpacing: "0.12em", textTransform: "uppercase" }}>{k}</div>
                <div style={{ fontFamily: "var(--b-mono)", fontSize: 13, color: tone === "gain" ? "var(--b-gain)" : "var(--b-fg)" }}>{v}</div>
              </div>
            ))}
          </div>
          <div>
            <B_Bracket>Quick Orders</B_Bracket>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginTop: 8 }}>
              <button style={{ height: 30, fontFamily: "var(--b-mono)", fontSize: 10, letterSpacing: "0.14em", color: "var(--b-bg)", background: "var(--b-gain)", border: "none", cursor: "pointer" }}>▲ BUY MKT</button>
              <button style={{ height: 30, fontFamily: "var(--b-mono)", fontSize: 10, letterSpacing: "0.14em", color: "var(--b-bg)", background: "var(--b-loss)", border: "none", cursor: "pointer" }}>▼ SELL MKT</button>
              <button style={{ height: 30, fontFamily: "var(--b-mono)", fontSize: 10, letterSpacing: "0.14em", color: "var(--b-fg)", background: "transparent", border: "1px solid var(--b-line)", cursor: "pointer" }}>LIMIT</button>
              <button style={{ height: 30, fontFamily: "var(--b-mono)", fontSize: 10, letterSpacing: "0.14em", color: "var(--b-fg)", background: "transparent", border: "1px solid var(--b-line)", cursor: "pointer" }}>TWAP</button>
            </div>
          </div>
        </div>
      </div>
    </B_Module>
  );
}

function B_Watchlist() {
  return (
    <B_Module code="W" title="Watchlist" subtitle="PINNED · 8"
      status="STREAMING">
      <div>
        {HERMES_DATA.watchlist.map((r, i) => {
          const closes = genCandles(22, 23 + i, r.px, r.px * 0.025).map(c => c.c);
          const path = sparkPath(closes, 70, 22);
          const up = r.chg > 0;
          return (
            <div key={r.sym} style={{
              display: "grid", gridTemplateColumns: "14px 1fr 70px 62px",
              alignItems: "center", gap: 10, padding: "8px 12px",
              borderTop: i === 0 ? "none" : "1px solid var(--b-line)",
              fontFamily: "var(--b-mono)", fontSize: 11,
              background: i === 0 ? "color-mix(in oklch, var(--b-accent) 8%, transparent)" : "transparent",
            }}>
              <span style={{ fontSize: 9, color: "var(--b-muted)" }}>{String(i+1).padStart(2, "0")}</span>
              <span>
                <div style={{ color: "var(--b-fg)" }}>{r.sym.replace("USDT","")}</div>
                <div style={{ fontSize: 9.5, color: "var(--b-muted)" }}>{r.px.toLocaleString()}</div>
              </span>
              <svg viewBox="0 0 70 22" style={{ width: 70, height: 22 }}>
                <path d={path} fill="none" stroke={up ? "var(--b-gain)" : "var(--b-loss)"} strokeWidth="1.2" />
              </svg>
              <span style={{ textAlign: "right", color: up ? "var(--b-gain)" : "var(--b-loss)" }}>
                {up ? "▲" : "▼"} {Math.abs(r.chg).toFixed(2)}%
              </span>
            </div>
          );
        })}
      </div>
    </B_Module>
  );
}

function B_Positions() {
  const p = HERMES_DATA.positions;
  return (
    <B_Module code="03" title="Positions" subtitle={`${p.length} OPEN · NET LONG`} status="MONITORED">
      <div>
        <div style={{
          display: "grid", gridTemplateColumns: "1fr 0.5fr 1fr 1fr 1.4fr",
          gap: 10, padding: "8px 14px", borderBottom: "1px solid var(--b-line)",
          fontFamily: "var(--b-mono)", fontSize: 9, color: "var(--b-muted)",
          letterSpacing: "0.16em", textTransform: "uppercase", background: "var(--b-bg)",
        }}>
          <span>Symbol</span><span>Side</span><span style={{ textAlign: "right" }}>Notional</span>
          <span style={{ textAlign: "right" }}>P&L</span>
          <span>Allocation</span>
        </div>
        {p.map((r, i) => (
          <div key={r.sym} style={{
            display: "grid", gridTemplateColumns: "1fr 0.5fr 1fr 1fr 1.4fr",
            gap: 10, padding: "9px 14px",
            borderTop: i === 0 ? "none" : "1px solid var(--b-line)",
            fontFamily: "var(--b-mono)", fontSize: 11,
          }}>
            <span>
              <div style={{ fontWeight: 500 }}>{r.sym.replace("USDT","")}</div>
              <div style={{ fontSize: 9.5, color: "var(--b-muted)" }}>{r.thesis}</div>
            </span>
            <span style={{
              color: r.side === "LONG" ? "var(--b-gain)" : "var(--b-loss)",
              alignSelf: "center",
            }}>{r.side === "LONG" ? "▲ L" : "▼ S"}</span>
            <span style={{ textAlign: "right", alignSelf: "center" }}>
              <div>{fmtUsd(r.notional, { compact: true })}</div>
              <div style={{ fontSize: 9.5, color: "var(--b-muted)" }}>{fmtNum(r.qty)}</div>
            </span>
            <span style={{ textAlign: "right", alignSelf: "center", color: r.pnl >= 0 ? "var(--b-gain)" : "var(--b-loss)" }}>
              <div>{fmtUsd(r.pnl, { sign: true })}</div>
              <div style={{ fontSize: 9.5, color: "var(--b-muted)" }}>{fmtPct(r.pnlPct)}</div>
            </span>
            <span style={{ alignSelf: "center" }}>
              <div style={{ height: 6, background: "var(--b-line)", position: "relative" }}>
                <div style={{ position: "absolute", left: 0, top: 0, height: "100%", width: `${r.weight}%`,
                  background: `linear-gradient(90deg, var(--b-accent), color-mix(in oklch, var(--b-accent) 40%, transparent))` }} />
              </div>
              <div style={{ fontSize: 9.5, color: "var(--b-muted)", marginTop: 3 }}>{r.weight.toFixed(1)}% of gross</div>
            </span>
          </div>
        ))}
      </div>
    </B_Module>
  );
}

function B_ResearchLanes() {
  return (
    <B_Module code="04" title="Research Pipeline" subtitle="AGENT-ASSISTED FLOW"
      status={`${HERMES_DATA.lanes.reduce((a,l)=>a+l.count,0)} ACTIVE`}
      right={<div style={{ display: "flex", gap: 6 }}>
        <B_Bracket>ALL</B_Bracket><B_Bracket tone="accent">MINE</B_Bracket><B_Bracket>URGENT</B_Bracket>
      </div>}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", height: "100%" }}>
        {HERMES_DATA.lanes.map((lane, li) => (
          <div key={lane.name} style={{
            borderRight: li < 4 ? "1px solid var(--b-line)" : "none",
            display: "flex", flexDirection: "column", minWidth: 0,
          }}>
            <div style={{
              padding: "10px 12px", display: "flex", justifyContent: "space-between", alignItems: "center",
              borderBottom: "1px solid var(--b-line)", background: "var(--b-bg)",
            }}>
              <span style={{ fontFamily: "var(--b-mono)", fontSize: 10, letterSpacing: "0.16em", textTransform: "uppercase",
                color: li === 2 ? "var(--b-accent)" : "var(--b-fg)" }}>
                /{String(li+1).padStart(2,"0")} {lane.name}
              </span>
              <span style={{ fontFamily: "var(--b-mono)", fontSize: 10, color: "var(--b-muted)" }}>{lane.count}</span>
            </div>
            <div style={{ padding: 8, display: "flex", flexDirection: "column", gap: 6, flex: 1 }}>
              {lane.items.map((it, i) => (
                <div key={i} style={{
                  padding: "8px 10px", border: "1px solid var(--b-line)",
                  background: "var(--b-bg)",
                  position: "relative",
                }}>
                  {/* Left rail indicator */}
                  <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 2,
                    background: it.conf == null ? "var(--b-muted)" : it.conf > 0.7 ? "var(--b-gain)" : it.conf > 0.5 ? "var(--b-accent)" : "var(--b-warn)" }} />
                  <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--b-mono)", fontSize: 11 }}>
                    <span style={{ fontWeight: 500 }}>{it.sym.replace("USDT","")}</span>
                    {it.conf != null && (
                      <span style={{ fontSize: 10, color: "var(--b-muted)" }}>
                        C·<span style={{ color: "var(--b-fg)" }}>{it.conf.toFixed(2)}</span>
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 10.5, color: "var(--b-muted)", lineHeight: 1.4, marginTop: 2 }}>{it.thesis}</div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--b-mono)", fontSize: 9, color: "var(--b-muted)", marginTop: 6, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                    <span>· {it.agent}</span><span>{it.age}</span>
                  </div>
                </div>
              ))}
              {lane.items.length === 0 && (
                <div style={{ fontFamily: "var(--b-mono)", fontSize: 10, color: "var(--b-muted)", padding: "6px 2px", opacity: 0.6 }}>— empty —</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </B_Module>
  );
}

function B_Feed() {
  const kindColor = { FILL: "var(--b-gain)", SIGNAL: "var(--b-accent)", ALERT: "var(--b-warn)", REJECT: "var(--b-loss)", RESEARCH: "var(--b-muted)" };
  return (
    <B_Module code="05" title="Execution Feed" subtitle="TRADE TAPE · LIVE"
      status={`${HERMES_DATA.tape.length} EVENTS`}>
      <div>
        {HERMES_DATA.tape.map((r, i) => (
          <div key={i} style={{
            display: "grid", gridTemplateColumns: "64px 14px 62px 84px 44px 1fr 90px",
            gap: 8, padding: "7px 14px",
            borderTop: i === 0 ? "none" : "1px solid var(--b-line)",
            fontFamily: "var(--b-mono)", fontSize: 11,
            background: i < 1 ? "color-mix(in oklch, var(--b-accent) 6%, transparent)" : "transparent",
          }}>
            <span style={{ color: "var(--b-muted)" }}>{r.t}</span>
            <span style={{ color: kindColor[r.kind] }}>●</span>
            <span style={{ color: kindColor[r.kind], letterSpacing: "0.1em" }}>{r.kind}</span>
            <span>{r.sym.replace("USDT", "")}</span>
            <span style={{ color: r.side === "BUY" ? "var(--b-gain)" : r.side === "SELL" ? "var(--b-loss)" : "var(--b-muted)" }}>{r.side}</span>
            <span style={{ color: "var(--b-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.note}</span>
            <span style={{ textAlign: "right" }}>
              {r.qty ? <span style={{ color: "var(--b-muted)" }}>{fmtNum(r.qty)} @</span> : null}{" "}
              {r.px != null ? r.px.toLocaleString() : "—"}
            </span>
          </div>
        ))}
      </div>
    </B_Module>
  );
}

function B_ApprovalQueue() {
  return (
    <B_Module code="Q" title="Approval Queue" subtitle="HUMAN-IN-LOOP"
      status={<span style={{ color: "var(--b-warn)" }}>{HERMES_DATA.approvals.length} PENDING</span>}>
      <div>
        {HERMES_DATA.approvals.map((a, i) => (
          <div key={i} style={{
            padding: "12px 14px", borderTop: i === 0 ? "none" : "1px solid var(--b-line)",
            display: "flex", flexDirection: "column", gap: 8,
            position: "relative",
          }}>
            <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 2, background: "var(--b-warn)" }} />
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <span style={{ fontFamily: "var(--b-mono)", fontSize: 12 }}>
                <span style={{ color: a.side === "BUY" ? "var(--b-gain)" : "var(--b-loss)", fontWeight: 600 }}>{a.side}</span>{" "}
                <span style={{ fontWeight: 500 }}>{a.sym.replace("USDT","")}</span>{" "}
                <span style={{ color: "var(--b-muted)" }}>· {a.size}</span>
              </span>
              <span style={{ fontFamily: "var(--b-mono)", fontSize: 10, color: "var(--b-warn)" }}>⏱ {a.expiresIn}</span>
            </div>
            <div style={{ fontSize: 11, color: "var(--b-muted)", lineHeight: 1.45 }}>
              {a.reason}
              <span style={{ marginLeft: 8, fontFamily: "var(--b-mono)", color: "var(--b-accent)" }}>conf {a.conf.toFixed(2)}</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr 1fr", gap: 4 }}>
              <button style={{ height: 28, fontFamily: "var(--b-mono)", fontSize: 10, letterSpacing: "0.16em",
                color: "var(--b-bg)", background: "var(--b-gain)", border: "none", cursor: "pointer" }}>✓ APPROVE</button>
              <button style={{ height: 28, fontFamily: "var(--b-mono)", fontSize: 10, letterSpacing: "0.14em",
                color: "var(--b-fg)", background: "transparent", border: "1px solid var(--b-line)", cursor: "pointer" }}>EDIT</button>
              <button style={{ height: 28, fontFamily: "var(--b-mono)", fontSize: 10, letterSpacing: "0.14em",
                color: "var(--b-loss)", background: "transparent", border: "1px solid var(--b-loss)", cursor: "pointer" }}>REJECT</button>
            </div>
          </div>
        ))}
      </div>
    </B_Module>
  );
}

function B_Timeline() {
  const t = HERMES_DATA.timeline;
  const tone = { gain: "var(--b-gain)", loss: "var(--b-loss)", warn: "var(--b-warn)", info: "var(--b-accent)", mute: "var(--b-muted)" };
  return (
    <B_Module code="T" title="Operational Timeline" subtitle="T-0 / SESSION">
      <div style={{ padding: "10px 14px" }}>
        {t.map((r, i) => (
          <div key={i} style={{
            display: "grid", gridTemplateColumns: "44px 18px 1fr",
            gap: 8, padding: "6px 0", fontFamily: "var(--b-mono)", fontSize: 11,
          }}>
            <span style={{ color: "var(--b-muted)" }}>{r.t}</span>
            <span style={{ position: "relative" }}>
              <span style={{ position: "absolute", left: 6, top: 4, width: 6, height: 6, background: tone[r.tone], transform: "rotate(45deg)" }} />
              {i < t.length - 1 && (
                <span style={{ position: "absolute", left: 8.5, top: 12, width: 1, height: 16, background: "var(--b-line)" }} />
              )}
            </span>
            <span>
              <span style={{ color: tone[r.tone], marginRight: 6, letterSpacing: "0.1em" }}>{r.label}</span>
              <span style={{ color: "var(--b-fg)" }}>{r.detail}</span>
            </span>
          </div>
        ))}
      </div>
    </B_Module>
  );
}

function B_RiskRisk() {
  const r = HERMES_DATA.risk;
  return (
    <B_Module code="R" title="Risk Posture" subtitle="CAPS · LIMITS · ALERTS"
      status={r.posture}>
      <div style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: 12 }}>
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--b-mono)", fontSize: 10, color: "var(--b-muted)", letterSpacing: "0.14em", textTransform: "uppercase" }}>
            <span>Gross Exposure</span><span style={{ color: "var(--b-fg)" }}>{r.exposurePct.toFixed(1)}% / {r.maxExposurePct}%</span>
          </div>
          <div style={{ marginTop: 6, height: 6, background: "var(--b-bg)", border: "1px solid var(--b-line)", position: "relative" }}>
            <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${r.exposurePct}%`, background: "var(--b-warn)" }} />
            {/* 90% cap mark */}
            <span style={{ position: "absolute", left: "90%", top: -3, bottom: -3, width: 1, background: "var(--b-loss)" }} />
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div style={{ border: "1px solid var(--b-line)", padding: "6px 8px" }}>
            <div style={{ fontFamily: "var(--b-mono)", fontSize: 9, color: "var(--b-muted)", letterSpacing: "0.14em", textTransform: "uppercase" }}>Top Concentration</div>
            <div style={{ fontFamily: "var(--b-mono)", fontSize: 12, marginTop: 2 }}>BTC 40%</div>
          </div>
          <div style={{ border: "1px solid var(--b-line)", padding: "6px 8px" }}>
            <div style={{ fontFamily: "var(--b-mono)", fontSize: 9, color: "var(--b-muted)", letterSpacing: "0.14em", textTransform: "uppercase" }}>Corr BTC/ETH</div>
            <div style={{ fontFamily: "var(--b-mono)", fontSize: 12, marginTop: 2, color: "var(--b-warn)" }}>0.84 · 30d</div>
          </div>
        </div>
        <div>
          <div style={{ fontFamily: "var(--b-mono)", fontSize: 9, color: "var(--b-muted)", letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 6 }}>Active Flags</div>
          {r.alerts.map((a, i) => (
            <div key={i} style={{ display: "flex", gap: 8, padding: "6px 0", fontSize: 11, borderTop: i > 0 ? "1px solid var(--b-line)" : "none", alignItems: "center" }}>
              <span style={{
                fontFamily: "var(--b-mono)", fontSize: 9, letterSpacing: "0.16em",
                color: a.level === "amber" ? "var(--b-warn)" : "var(--b-accent)",
              }}>{a.level === "amber" ? "▲" : "◆"}</span>
              <span style={{ color: "var(--b-fg)" }}>{a.msg}</span>
            </div>
          ))}
        </div>
      </div>
    </B_Module>
  );
}

function B_StatusStrip() {
  return (
    <div style={{
      height: 28, display: "flex", alignItems: "center", gap: 18,
      padding: "0 18px", borderTop: "1px solid var(--b-line)",
      background: "var(--b-panel-hi)",
      fontFamily: "var(--b-mono)", fontSize: 10, color: "var(--b-muted)",
      letterSpacing: "0.14em", textTransform: "uppercase",
    }}>
      <span style={{ color: "var(--b-accent)" }}>◆ HERMES OPS</span>
      <span><span style={{ color: "var(--b-gain)" }}>●</span> WS 18ms</span>
      <span><span style={{ color: "var(--b-gain)" }}>●</span> API 12ms</span>
      <span><span style={{ color: "var(--b-gain)" }}>●</span> BITMART AUTH</span>
      <span><span style={{ color: "var(--b-gain)" }}>●</span> 6 AGENTS ONLINE</span>
      <span>KILL · ARMED</span>
      <span style={{ marginLeft: "auto" }}>BUILD 2026.04.23-R17</span>
      <span>TICK 0.7s</span>
      <span style={{ color: "var(--b-accent)" }}>T+02:43:08</span>
    </div>
  );
}

function VariantB() {
  return (
    <div style={{
      width: 1440, height: 1024,
      display: "grid", gridTemplateRows: "2px 60px 1fr 28px",
      background: "var(--b-bg)", color: "var(--b-fg)",
      fontFamily: "var(--b-sans)",
      // darker, warmer cinematic palette
      "--b-bg": "#0a0b0e",
      "--b-panel": "#111318",
      "--b-panel-hi": "#161922",
      "--b-fg": "#dfe4ee",
      "--b-muted": "#6b7384",
      "--b-line": "#222631",
      "--b-accent": "#57c7e6",
      "--b-gain": "#4ec28a",
      "--b-loss": "#d36464",
      "--b-warn": "#d4a24c",
      "--b-mono": "'JetBrains Mono', ui-monospace, monospace",
      "--b-sans": "'Inter Tight', 'Inter', system-ui, sans-serif",
      backgroundImage: "radial-gradient(ellipse at 20% 0%, color-mix(in oklch, var(--b-accent) 6%, transparent), transparent 45%), radial-gradient(ellipse at 100% 100%, color-mix(in oklch, var(--b-accent) 4%, transparent), transparent 55%)",
    }}>
      <B_HudRule />
      <B_TopBar />

      {/* Main grid: 3 columns, center is the hero stack */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "280px minmax(0, 1fr) 320px",
        gap: 0,
        minHeight: 0,
      }}>
        {/* Left rail */}
        <div style={{ borderRight: "1px solid var(--b-line)", display: "grid", gridTemplateRows: "auto 1fr", minHeight: 0 }}>
          <B_Watchlist />
          <B_RiskRisk />
        </div>

        {/* Center */}
        <div style={{
          display: "grid",
          gridTemplateRows: "auto auto 1fr",
          minHeight: 0,
        }}>
          <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", borderBottom: "1px solid var(--b-line)" }}>
            <B_CommandDeck />
            <div style={{ borderLeft: "1px solid var(--b-line)" }}>
              <B_Positions />
            </div>
          </div>
          <div style={{ borderBottom: "1px solid var(--b-line)" }}>
            <B_MarketFocus />
          </div>
          <B_ResearchLanes />
        </div>

        {/* Right rail */}
        <div style={{ borderLeft: "1px solid var(--b-line)", display: "grid", gridTemplateRows: "auto auto 1fr", minHeight: 0 }}>
          <B_ApprovalQueue />
          <B_Timeline />
          <B_Feed />
        </div>
      </div>

      <B_StatusStrip />
    </div>
  );
}

Object.assign(window, { VariantB });
