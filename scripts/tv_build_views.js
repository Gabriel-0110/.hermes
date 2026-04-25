const { spawn } = require('child_process');
const proc = spawn('node', ['src/server.js'], { stdio: ['pipe','pipe','pipe'], cwd: '/Users/openclaw/Coding/tradingview-mcp-jackson' });
let id=1, buf=''; const pend=new Map();
proc.stdout.on('data',(d)=>{ buf+=d.toString(); const lines=buf.split('\n'); buf=lines.pop(); for(const l of lines){if(!l.trim())continue;try{const o=JSON.parse(l);if(o.id&&pend.has(o.id)){pend.get(o.id)(o);pend.delete(o.id);}}catch(e){}}});
proc.stderr.on('data',()=>{});
function rpc(m,p){return new Promise(r=>{const i=id++;pend.set(i,r);proc.stdin.write(JSON.stringify({jsonrpc:'2.0',id:i,method:m,params:p})+'\n');setTimeout(()=>{if(pend.has(i)){pend.delete(i);r({error:'timeout'});}},25000);})}
function tv(n,a){return rpc('tools/call',{name:n,arguments:a||{}}).then(r=>{const t=r.result?.content?.[0]?.text||r.result;try{return JSON.parse(t);}catch(e){return t;}});}
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}

const fs = require('fs');
const forecast = JSON.parse(fs.readFileSync('/Users/openclaw/.hermes/scripts/chronos_forecast.json'));

async function run(){
  await rpc('initialize',{protocolVersion:'2024-11-05',capabilities:{},clientInfo:{name:'hermes',version:'1'}});

  // ── CHART 1: ETH 4H — Bot B active view ──
  console.log('Switching to ETH 4H...');
  await tv('chart_set_symbol', { symbol: 'BINANCE:ETHUSDTPERP' });
  await sleep(3000);
  await tv('chart_set_timeframe', { timeframe: '240' });
  await sleep(2500);

  // Remove old custom indicators, keep clean
  const state1 = await tv('chart_get_state', {});
  for (const s of (state1.studies || [])) {
    if (s.name !== 'Volume' && s.name !== 'Moving Average Exponential') {
      await tv('chart_manage_indicator', { action: 'remove', entity_id: s.id }).catch(()=>{});
      await sleep(300);
    }
  }

  // Clear old drawings
  await tv('draw_clear', {});
  await sleep(500);

  // Add fresh indicators for ETH Bot B view
  await tv('chart_manage_indicator', { action: 'add', name: 'Relative Strength Index' });
  await sleep(1200);
  await tv('chart_manage_indicator', { action: 'add', name: 'Bollinger Bands' });
  await sleep(1200);
  await tv('chart_manage_indicator', { action: 'add', name: 'MACD' });
  await sleep(1200);

  // Draw Bot B levels
  const now = Math.floor(Date.now()/1000);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 2580 },  color: '#69F0AE', text: '💰 TAKE PROFIT $2,580', linewidth: 2 });
  await sleep(400);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 2500 },  color: '#00E676', text: 'Grid Top $2,500 (20 grids)', linewidth: 1, linestyle: 'dashed' });
  await sleep(400);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 2350 },  color: '#FFD700', text: '🔥 BOT B TRIGGER — 4H close above = BOT ACTIVATES', linewidth: 3, linestyle: 'dashed' });
  await sleep(400);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 2316 },  color: '#00BCD4', text: `⚡ CURRENT $2,316 — Chronos +48h median $${forecast.ETH.scenarios[11].median}`, linewidth: 1, linestyle: 'dotted' });
  await sleep(400);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 2150 },  color: '#FF9800', text: 'Grid Low $2,150 (grid bottom)', linewidth: 1, linestyle: 'dashed' });
  await sleep(400);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 2050 },  color: '#FF1744', text: '🛑 HARD STOP $2,050 — BOT B stops here', linewidth: 2 });
  await sleep(400);

  // Chronos forecast lines as draws
  const ethSc = forecast.ETH.scenarios;
  // Draw a trend arrow text label for Chronos direction
  await tv('draw_shape', { type: 'horizontal_line', point: { price: ethSc[0].median },  color: '#FFF176', text: `Chronos +4h median $${ethSc[0].median}`, linewidth: 1, linestyle: 'dotted' });
  await sleep(400);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: ethSc[5].median },  color: '#FFEB3B', text: `Chronos +24h median $${ethSc[5].median}`, linewidth: 1, linestyle: 'dotted' });
  await sleep(400);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: ethSc[11].median }, color: '#FFD700', text: `Chronos +48h median $${ethSc[11].median} ▲ UP ${((ethSc[11].median-forecast.ETH.last)/forecast.ETH.last*100).toFixed(2)}%`, linewidth: 2, linestyle: 'dotted' });
  await sleep(400);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: ethSc[11].high },   color: '#A5D6A7', text: `Chronos +48h HIGH scenario $${ethSc[11].high}`, linewidth: 1, linestyle: 'dotted' });
  await sleep(400);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: ethSc[11].low },    color: '#EF9A9A', text: `Chronos +48h LOW scenario $${ethSc[11].low}`, linewidth: 1, linestyle: 'dotted' });
  await sleep(400);

  // Inject Pine Script for ETH
  await tv('ui_open_panel', { panel: 'pine-editor' });
  await sleep(2000);
  await tv('pine_new', { type: 'indicator' });
  await sleep(1500);

  const eth = forecast.ETH;
  const ethPine = buildPine('ETH', eth, {
    trigger: 2350, gridTop: 2500, gridBot: 2150, sl: 2050, tp: 2580,
    botName: 'BOT B — LONG GRID', triggerNote: '4H close above $2,350'
  });
  await tv('pine_set_source', { source: ethPine });
  await sleep(1500);
  await tv('pine_smart_compile', {});
  await sleep(3000);

  // Screenshot Chart 1
  const ss1 = await tv('capture_screenshot', { region: 'chart' });
  console.log('ETH_CHART:', ss1.file_path);

  // ── CHART 2: BTC 4H — Next opportunity / prediction ──
  console.log('\nSwitching to BTC 4H...');
  await tv('chart_set_symbol', { symbol: 'BINANCE:BTCUSDTPERP' });
  await sleep(3000);
  await tv('chart_set_timeframe', { timeframe: '240' });
  await sleep(2500);

  await tv('draw_clear', {});
  await sleep(500);

  // Clean indicators for BTC
  const state2 = await tv('chart_get_state', {});
  for (const s of (state2.studies || [])) {
    if (!['Volume','Moving Average Exponential','Relative Strength Index'].includes(s.name)) {
      await tv('chart_manage_indicator', { action: 'remove', entity_id: s.id }).catch(()=>{});
      await sleep(300);
    }
  }

  await tv('chart_manage_indicator', { action: 'add', name: 'Bollinger Bands' });
  await sleep(1200);
  await tv('chart_manage_indicator', { action: 'add', name: 'MACD' });
  await sleep(1200);

  // BTC levels
  const btcSc = forecast.BTC.scenarios;
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 83500 }, color: '#69F0AE', text: '💰 TP $83,500', linewidth: 2 });
  await sleep(300);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 84000 }, color: '#00E676', text: 'Grid Top $84,000', linewidth: 1, linestyle: 'dashed' });
  await sleep(300);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 78100 }, color: '#FFD700', text: '🚀 BOT C TRIGGER $78,100 — break + hold = DEPLOY GRID', linewidth: 3, linestyle: 'dashed' });
  await sleep(300);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 77438 }, color: '#00BCD4', text: `⚡ CURRENT $77,438 — Chronos +48h $${btcSc[11].median}`, linewidth: 1, linestyle: 'dotted' });
  await sleep(300);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 72000 }, color: '#FF9800', text: 'Grid Low $72,000', linewidth: 1, linestyle: 'dashed' });
  await sleep(300);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 71500 }, color: '#FF1744', text: '🛑 HARD STOP $71,500', linewidth: 2 });
  await sleep(300);

  // Chronos BTC forecasts
  await tv('draw_shape', { type: 'horizontal_line', point: { price: btcSc[0].median },  color: '#FFF176', text: `Chronos +4h median $${btcSc[0].median}`, linewidth: 1, linestyle: 'dotted' });
  await sleep(300);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: btcSc[5].median },  color: '#FFEB3B', text: `Chronos +24h median $${btcSc[5].median}`, linewidth: 1, linestyle: 'dotted' });
  await sleep(300);
  const btcTrend = btcSc[11].median > forecast.BTC.last ? '▲' : '▼';
  const btcPct = ((btcSc[11].median-forecast.BTC.last)/forecast.BTC.last*100).toFixed(2);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: btcSc[11].median }, color: '#FFD700', text: `Chronos +48h median $${btcSc[11].median} ${btcTrend} ${btcPct}%`, linewidth: 2, linestyle: 'dotted' });
  await sleep(300);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: btcSc[11].high },   color: '#A5D6A7', text: `Chronos +48h HIGH $${btcSc[11].high}`, linewidth: 1, linestyle: 'dotted' });
  await sleep(300);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: btcSc[11].low },    color: '#EF9A9A', text: `Chronos +48h LOW $${btcSc[11].low}`, linewidth: 1, linestyle: 'dotted' });
  await sleep(300);

  // Inject BTC Pine
  await tv('pine_new', { type: 'indicator' });
  await sleep(1500);
  const btc = forecast.BTC;
  const btcPine = buildPine('BTC', btc, {
    trigger: 78100, gridTop: 84000, gridBot: 72000, sl: 71500, tp: 83500,
    botName: 'BOT C — GRID (PENDING TRIGGER)', triggerNote: 'break + hold above $78,100'
  });
  await tv('pine_set_source', { source: btcPine });
  await sleep(1500);
  await tv('pine_smart_compile', {});
  await sleep(3000);

  const ss2 = await tv('capture_screenshot', { region: 'chart' });
  console.log('BTC_CHART:', ss2.file_path);

  console.log('\n=== ALL DONE ===');
  proc.kill();
}

function buildPine(symbol, fc, levels) {
  const sc = fc.scenarios;
  const last = fc.last;
  const trend = sc[11].median > last ? 'UP' : 'DOWN';
  const pct = ((sc[11].median - last)/last*100).toFixed(2);
  const medArr  = sc.map(s=>s.median.toFixed(2)).join(',');
  const lowArr  = sc.map(s=>s.low.toFixed(2)).join(',');
  const highArr = sc.map(s=>s.high.toFixed(2)).join(',');
  const isBTC = symbol === 'BTC';
  const priceFormat = isBTC ? '#.00' : '#.00';

  return `//@version=5
indicator("🤖 Hermes — ${symbol} ${levels.botName} + Chronos-2", overlay=true, max_lines_count=500, max_labels_count=500)

// Chronos-2 live forecast — ${new Date().toISOString().slice(0,16)} UTC
// Source: amazon/chronos-t5-tiny | 100 samples | 4H bars | horizon 12 steps (48h)
// ${symbol} last close: ${last} | 48h outlook: ${trend} ${pct}%

var float[] med_arr  = array.from(${medArr})
var float[] low_arr  = array.from(${lowArr})
var float[] high_arr = array.from(${highArr})

// Key levels
t_line  = hline(${levels.trigger},  "${symbol} BOT TRIGGER",  color=color.new(color.yellow, 0), linestyle=hline.style_dashed, linewidth=2)
g_top   = hline(${levels.gridTop},  "Grid Top",               color=color.new(color.green,  30), linestyle=hline.style_dashed)
g_bot   = hline(${levels.gridBot},  "Grid Low",               color=color.new(color.orange, 30), linestyle=hline.style_dashed)
sl_line = hline(${levels.sl},       "Stop Loss",              color=color.new(color.red,    0), linestyle=hline.style_solid, linewidth=2)
tp_line = hline(${levels.tp},       "Take Profit",            color=color.new(color.lime,   0), linestyle=hline.style_solid, linewidth=2)

// Chronos-2 forecast fan (drawn on last bar only)
if barstate.islast
    prev_med  = close
    prev_low  = close
    prev_high = close
    for i = 0 to 11
        x0 = bar_index + i
        x1 = bar_index + i + 1
        m  = array.get(med_arr,  i)
        lo = array.get(low_arr,  i)
        hi = array.get(high_arr, i)
        // Median — gold solid
        line.new(x0, prev_med,  x1, m,  color=color.new(color.yellow, 0),  width=2)
        // High band — green dashed  
        line.new(x0, prev_high, x1, hi, color=color.new(color.green,  20), width=1, style=line.style_dashed)
        // Low band — red dashed
        line.new(x0, prev_low,  x1, lo, color=color.new(color.red,    20), width=1, style=line.style_dashed)
        prev_med  := m
        prev_low  := lo
        prev_high := hi
    
    // Uncertainty cone fill hint (vertical bars at 4/8/12)
    for i = 0 to 2
        step = (i + 1) * 4 - 1
        x = bar_index + step
        lo = array.get(low_arr, step)
        hi = array.get(high_arr, step)
        line.new(x, lo, x, hi, color=color.new(color.gray, 60), width=1, style=line.style_dotted)
    
    // End label
    end_med = array.get(med_arr,  11)
    end_hi  = array.get(high_arr, 11)
    lbl_col = end_med > close ? color.new(color.teal, 10) : color.new(color.maroon, 10)
    label.new(bar_index + 13, end_hi,
        "Chronos-2 Forecast\\n+48h Median: " + str.tostring(end_med, "${priceFormat}") + "\\n" +
        "High: " + str.tostring(end_hi, "${priceFormat}") + "\\n" +
        "Low: " + str.tostring(array.get(low_arr,11), "${priceFormat}") + "\\n" +
        "${trend} ${pct}%  (${symbol})",
        color=lbl_col, textcolor=color.white, style=label.style_label_left, size=size.normal)

// Dashboard table
var table dash = table.new(position.top_right, 2, 9, bgcolor=color.new(color.black, 15), border_width=1, border_color=color.gray)
if barstate.islast
    dist_trigger = ${levels.trigger} - close
    dist_pct     = dist_trigger / close * 100
    triggered    = close >= ${levels.trigger}
    
    table.cell(dash, 0, 0, "HERMES — ${symbol} DESK",      text_color=color.yellow, bgcolor=color.new(#1a237e,10), text_size=size.normal)
    table.cell(dash, 1, 0, "${levels.botName}",             text_color=color.yellow, bgcolor=color.new(#1a237e,10), text_size=size.normal)
    table.cell(dash, 0, 1, "Price",                         text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 1, str.tostring(close, "${priceFormat}"), text_color=color.aqua, text_size=size.small)
    table.cell(dash, 0, 2, "Trigger",                       text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 2, triggered ? "✅ TRIGGERED" : str.tostring(math.abs(dist_trigger), "${priceFormat}") + " away (" + str.tostring(math.abs(dist_pct), "#.2") + "%)", text_color=triggered ? color.lime : color.orange, text_size=size.small)
    table.cell(dash, 0, 3, "Chronos +4h",                   text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 3, str.tostring(array.get(med_arr,0), "${priceFormat}"), text_color=color.yellow, text_size=size.small)
    table.cell(dash, 0, 4, "Chronos +12h",                  text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 4, str.tostring(array.get(med_arr,2), "${priceFormat}"), text_color=color.yellow, text_size=size.small)
    table.cell(dash, 0, 5, "Chronos +24h",                  text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 5, str.tostring(array.get(med_arr,5), "${priceFormat}"), text_color=color.yellow, text_size=size.small)
    table.cell(dash, 0, 6, "Chronos +48h",                  text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 6, str.tostring(array.get(med_arr,11), "${priceFormat}") + " (${trend} ${pct}%)", text_color=${sc[11].median > last} ? color.lime : color.red, text_size=size.small)
    table.cell(dash, 0, 7, "Grid zone",                     text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 7, "${levels.gridBot} — ${levels.gridTop}", text_color=color.aqua, text_size=size.small)
    table.cell(dash, 0, 8, "SL / TP",                       text_color=color.silver, text_size=size.small)
    table.cell(dash, 1, 8, "${levels.sl} / ${levels.tp}",   text_color=color.lime, text_size=size.small)
`;
}

run().catch(e => { console.error('ERROR:', e.message); proc.kill(); process.exit(1); });
