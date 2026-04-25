const {spawn}=require('child_process');
const fs=require('fs');
const proc=spawn('node',['src/server.js'],{stdio:['pipe','pipe','pipe'],cwd:'/Users/openclaw/Coding/tradingview-mcp-jackson'});
let id=1,buf='';const pend=new Map();
proc.stdout.on('data',(d)=>{buf+=d.toString();const lines=buf.split('\n');buf=lines.pop();for(const l of lines){if(!l.trim())continue;try{const o=JSON.parse(l);if(o.id&&pend.has(o.id)){pend.get(o.id)(o);pend.delete(o.id);}}catch(e){}}});
proc.stderr.on('data',()=>{});
function rpc(m,p){return new Promise(r=>{const i=id++;pend.set(i,r);proc.stdin.write(JSON.stringify({jsonrpc:'2.0',id:i,method:m,params:p})+'\n');setTimeout(()=>{if(pend.has(i)){pend.delete(i);r({error:'timeout'});}},25000);})}
function tv(n,a){return rpc('tools/call',{name:n,arguments:a||{}}).then(r=>{const t=r.result?.content?.[0]?.text||r.result;try{return JSON.parse(t);}catch(e){return t;}});}
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}

const fc=JSON.parse(fs.readFileSync('/Users/openclaw/.hermes/scripts/chronos_forecast.json'));

// Build Pine v6 all-in-one: Chronos forecast fan + key levels + info table
// RSI/MACD/BB are embedded as plotted overlays on this single indicator
function buildAllInOne(sym, f, lv) {
  const sc=f.scenarios, last=f.last;
  const trend=sc[11].median>last?'UP ▲':'DOWN ▼';
  const pct=((sc[11].median-last)/last*100).toFixed(2);
  const mArr=sc.map(s=>s.median.toFixed(2)).join(',');
  const lArr=sc.map(s=>s.low.toFixed(2)).join(',');
  const hArr=sc.map(s=>s.high.toFixed(2)).join(',');
  const isBTC=sym==='BTC';

  return `//@version=6
indicator("🤖 Hermes ${sym} — ${lv.bot} + Chronos-2", overlay=true, max_lines_count=500, max_labels_count=500)

// ─── Chronos-2 Live ML Forecast ───────────────────────────────────────────
// Model: amazon/chronos-t5-tiny | 100 samples | 4H bars | 12-step (48h) horizon
// Generated: ${new Date().toISOString().slice(0,16)} UTC
// ${sym} last close: ${last} | 48h outlook: ${trend} ${pct}%

var float[] mfc = array.from(${mArr})
var float[] lfc = array.from(${lArr})
var float[] hfc = array.from(${hArr})

// ─── Embedded Indicators (EMA 20, EMA 50, BB) ─────────────────────────────
ema20 = ta.ema(close, 20)
ema50 = ta.ema(close, 50)
[bbMid, bbUpper, bbLower] = ta.bb(close, 20, 2.0)

plot(ema20,  title="EMA 20",   color=color.new(color.blue,   20), linewidth=1)
plot(ema50,  title="EMA 50",   color=color.new(color.orange, 20), linewidth=2)
plot(bbUpper,title="BB Upper", color=color.new(color.purple, 40), linewidth=1)
plot(bbLower,title="BB Lower", color=color.new(color.purple, 40), linewidth=1)
plot(bbMid,  title="BB Mid",   color=color.new(color.purple, 60), linewidth=1, style=plot.style_circles)

// ─── Key Bot Levels ────────────────────────────────────────────────────────
hline(${lv.tp},      "💰 Take Profit ${lv.tp}",     color=color.new(color.lime,   0), linestyle=hline.style_solid,  linewidth=2)
hline(${lv.gridTop}, "Grid Top ${lv.gridTop}",       color=color.new(color.green,  30),linestyle=hline.style_dashed, linewidth=1)
hline(${lv.trigger}, "🔥 Bot Trigger ${lv.trigger}", color=color.new(color.yellow, 0), linestyle=hline.style_dashed, linewidth=3)
hline(${lv.gridBot}, "Grid Low ${lv.gridBot}",       color=color.new(color.orange, 30),linestyle=hline.style_dashed, linewidth=1)
hline(${lv.sl},      "🛑 Stop Loss ${lv.sl}",        color=color.new(color.red,    0), linestyle=hline.style_solid,  linewidth=2)

// ─── Chronos-2 Forecast Fan ────────────────────────────────────────────────
if barstate.islast
    float pm = close
    float pl = close
    float ph = close
    for i = 0 to 11
        x0 = bar_index + i
        x1 = bar_index + i + 1
        float m  = array.get(mfc, i)
        float lo = array.get(lfc, i)
        float hi = array.get(hfc, i)
        line.new(x0, pm, x1, m,  color=color.new(color.yellow, 0),  width=2)
        line.new(x0, ph, x1, hi, color=color.new(color.green,  20), width=1, style=line.style_dashed)
        line.new(x0, pl, x1, lo, color=color.new(color.red,    20), width=1, style=line.style_dashed)
        if i % 4 == 3
            line.new(bar_index+i, lo, bar_index+i, hi, color=color.new(color.gray, 60), width=1, style=line.style_dotted)
        pm := m
        pl := lo
        ph := hi

    // End-of-forecast label
    float eM = array.get(mfc, 11)
    float eH = array.get(hfc, 11)
    float eL = array.get(lfc, 11)
    color lc = eM > close ? color.new(color.teal, 5) : color.new(color.maroon, 5)
    label.new(bar_index + 13, eH,
        "Chronos-2 +48h\\n" +
        "Median: " + str.tostring(eM, "${isBTC?'#.00':'#.00'}") + "\\n" +
        "Bull case: " + str.tostring(eH, "#.00") + "\\n" +
        "Bear case: " + str.tostring(eL, "#.00") + "\\n" +
        "${trend} ${pct}%",
        color=lc, textcolor=color.white,
        style=label.style_label_left, size=size.normal)

    // Mark trigger distance on chart
    float dist = ${lv.trigger} - close
    bool triggered = close >= ${lv.trigger}
    color tc = triggered ? color.lime : color.orange
    string ts = triggered ? "✅ TRIGGERED" : "⚡ $" + str.tostring(math.abs(dist), "#.00") + " to trigger"
    label.new(bar_index, ${lv.trigger},
        ts,
        color=triggered ? color.new(color.lime,20) : color.new(color.orange,20),
        textcolor=color.white, style=label.style_label_right, size=size.small)

// ─── Dashboard Table ───────────────────────────────────────────────────────
var table dash = table.new(position.top_right, 2, 11,
    bgcolor=color.new(color.black, 10),
    border_width=1, border_color=color.new(color.gray, 60))

if barstate.islast
    float dist    = math.abs(${lv.trigger} - close)
    float dpct    = dist / close * 100
    bool  ok      = close >= ${lv.trigger}
    color distCol = ok ? color.lime : color.orange
    string distTxt = ok ? "✅ ACTIVE" : str.tostring(dist,"#.00") + " away (" + str.tostring(dpct,"#.2") + "%)"

    // Header
    table.cell(dash, 0, 0, "HERMES ${sym} DESK",  bgcolor=color.new(#0d1b4b,0), text_color=color.yellow, text_size=size.normal)
    table.cell(dash, 1, 0, "${lv.bot}",            bgcolor=color.new(#0d1b4b,0), text_color=color.yellow, text_size=size.small)
    // Price
    table.cell(dash, 0, 1, "Price",        text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 1, str.tostring(close, "#.00"), text_color=color.aqua, text_size=size.small)
    // EMA signals
    emaColor = ema20 > ema50 ? color.lime : color.red
    emaTxt   = ema20 > ema50 ? "EMA20 > EMA50 ▲ BULLISH" : "EMA20 < EMA50 ▼ BEARISH"
    table.cell(dash, 0, 2, "EMA Signal",   text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 2, emaTxt,         text_color=emaColor,     text_size=size.tiny)
    // BB signal
    bbPos   = close > bbUpper ? "ABOVE BB — OVERBOUGHT" : close < bbLower ? "BELOW BB — OVERSOLD" : "INSIDE BB — NEUTRAL"
    bbColor = close > bbUpper ? color.red : close < bbLower ? color.lime : color.gray
    table.cell(dash, 0, 3, "BB Signal",    text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 3, bbPos,          text_color=bbColor,      text_size=size.tiny)
    // Trigger
    table.cell(dash, 0, 4, "Bot Trigger",  text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 4, distTxt,        text_color=distCol,      text_size=size.small)
    // Chronos forecasts
    table.cell(dash, 0, 5, "📈 Chronos +4h",  text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 5, "$" + str.tostring(array.get(mfc,0),"#.00"), text_color=color.yellow, text_size=size.small)
    table.cell(dash, 0, 6, "📈 Chronos +12h", text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 6, "$" + str.tostring(array.get(mfc,2),"#.00"), text_color=color.yellow, text_size=size.small)
    table.cell(dash, 0, 7, "📈 Chronos +24h", text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 7, "$" + str.tostring(array.get(mfc,5),"#.00"), text_color=color.yellow, text_size=size.small)
    table.cell(dash, 0, 8, "📈 Chronos +48h", text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 8, "$" + str.tostring(array.get(mfc,11),"#.00") + " (${trend} ${pct}%)", text_color=${sc[11].median>last}?color.lime:color.red, text_size=size.small)
    // Grid / Risk
    table.cell(dash, 0, 9,  "Grid Zone",   text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 9,  "${lv.gridBot} — ${lv.gridTop}", text_color=color.aqua, text_size=size.small)
    table.cell(dash, 0, 10, "SL / TP",     text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 10, "SL ${lv.sl} / TP ${lv.tp}", text_color=color.lime, text_size=size.small)
`;
}

async function main(){
  await rpc('initialize',{protocolVersion:'2024-11-05',capabilities:{},clientInfo:{name:'hermes-v6',version:'1'}});

  // Close any modal first
  await tv('ui_click',{by:'aria-label',value:'Close'}).catch(()=>{});
  await sleep(1000);

  // ═══ VIEW 1: ETH 4H ═══
  console.log('Building ETH 4H view...');
  await tv('chart_set_symbol',{symbol:'BINANCE:ETHUSDTPERP'});
  await sleep(3000);
  await tv('chart_set_timeframe',{timeframe:'240'});
  await sleep(2000);
  await tv('draw_clear',{});
  await sleep(500);

  // Remove ALL existing indicators
  let s=await tv('chart_get_state',{});
  for(const st of (s.studies||[])){
    await tv('chart_manage_indicator',{action:'remove',indicator:st.name,entity_id:st.id}).catch(()=>{});
    await sleep(500);
  }
  await sleep(800);

  // Open Pine editor, create new indicator
  await tv('ui_open_panel',{panel:'pine-editor'});
  await sleep(2500);
  await tv('pine_new',{type:'indicator'});
  await sleep(2000);

  // Inject and compile ETH Pine v6
  const ethCode = buildAllInOne('ETH', fc.ETH, {
    bot:'BOT B — LONG GRID (trigger $2,350)',
    trigger:2350, gridTop:2500, gridBot:2150, sl:2050, tp:2580
  });
  await tv('pine_set_source',{source:ethCode});
  await sleep(2000);
  const c1=await tv('pine_smart_compile',{});
  const errs1=(c1.errors||[]).filter(e=>e.severity<4);
  console.log('ETH compile — fatal errors:',errs1.length, errs1.slice(0,3));
  await sleep(5000); // wait for render

  // Close Pine editor to see full chart
  await tv('ui_open_panel',{panel:'pine-editor'});
  await sleep(1500);

  const ss1=await tv('capture_screenshot',{region:'chart'});
  console.log('ETH_VIEW:', ss1.file_path);

  // ═══ VIEW 2: BTC 4H ═══
  console.log('\nBuilding BTC 4H view...');
  await tv('chart_set_symbol',{symbol:'BINANCE:BTCUSDTPERP'});
  await sleep(3000);
  await tv('chart_set_timeframe',{timeframe:'240'});
  await sleep(2000);
  await tv('draw_clear',{});
  await sleep(500);

  s=await tv('chart_get_state',{});
  for(const st of (s.studies||[])){
    await tv('chart_manage_indicator',{action:'remove',indicator:st.name,entity_id:st.id}).catch(()=>{});
    await sleep(500);
  }
  await sleep(800);

  await tv('ui_open_panel',{panel:'pine-editor'});
  await sleep(2500);
  await tv('pine_new',{type:'indicator'});
  await sleep(2000);

  const btcCode = buildAllInOne('BTC', fc.BTC, {
    bot:'BOT C — GRID (needs trigger $78,100)',
    trigger:78100, gridTop:84000, gridBot:72000, sl:71500, tp:83500
  });
  await tv('pine_set_source',{source:btcCode});
  await sleep(2000);
  const c2=await tv('pine_smart_compile',{});
  const errs2=(c2.errors||[]).filter(e=>e.severity<4);
  console.log('BTC compile — fatal errors:',errs2.length, errs2.slice(0,3));
  await sleep(5000);

  await tv('ui_open_panel',{panel:'pine-editor'});
  await sleep(1500);

  const ss2=await tv('capture_screenshot',{region:'chart'});
  console.log('BTC_VIEW:', ss2.file_path);

  console.log('\n=== DONE ===');
  console.log('ETH 48h: med $'+fc.ETH.scenarios[11].median+' high $'+fc.ETH.scenarios[11].high+' low $'+fc.ETH.scenarios[11].low);
  console.log('BTC 48h: med $'+fc.BTC.scenarios[11].median+' high $'+fc.BTC.scenarios[11].high+' low $'+fc.BTC.scenarios[11].low);
  proc.kill();
}

main().catch(e=>{console.error('ERR:',e.message,e.stack?.split('\n')[1]);proc.kill();process.exit(1);});
