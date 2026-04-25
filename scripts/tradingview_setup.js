// TradingView dual-view setup script
// View 1: Active bot positions with indicators + Chronos-2 forecast overlay
// View 2: Next opportunity scanner with Chronos-2 predictions

const { spawn } = require('child_process');
const proc = spawn('node', ['src/server.js'], { stdio: ['pipe','pipe','pipe'], cwd: '/Users/openclaw/Coding/tradingview-mcp-jackson' });

let msgId = 1;
let buf = '';
const pending = new Map();

proc.stdout.on('data', (data) => {
  buf += data.toString();
  const lines = buf.split('\n');
  buf = lines.pop();
  for (const line of lines) {
    if (!line.trim()) continue;
    try {
      const obj = JSON.parse(line);
      if (obj.id && pending.has(obj.id)) {
        const { resolve } = pending.get(obj.id);
        pending.delete(obj.id);
        resolve(obj);
      }
    } catch(e) {}
  }
});

proc.stderr.on('data', () => {});

function call(method, params) {
  return new Promise((resolve, reject) => {
    const id = msgId++;
    pending.set(id, { resolve, reject });
    proc.stdin.write(JSON.stringify({jsonrpc:'2.0', id, method, params}) + '\n');
    setTimeout(() => {
      if (pending.has(id)) { pending.delete(id); reject(new Error('timeout ' + method)); }
    }, 30000);
  });
}

function tv(name, args) {
  return call('tools/call', { name, arguments: args || {} })
    .then(r => {
      const text = r.result?.content?.[0]?.text || r.result;
      try { return JSON.parse(text); } catch(e) { return text; }
    });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  // Init MCP
  await call('initialize', {
    protocolVersion: '2024-11-05',
    capabilities: {},
    clientInfo: { name: 'hermes-setup', version: '1' }
  });
  await call('notifications/initialized', {});

  console.log('\n=== HERMES TRADINGVIEW SETUP ===\n');

  // ── CHART 1: ETH/USDT — Active Bot View ──
  console.log('Setting up Chart 1: ETH active bot view...');
  
  await tv('chart_set_symbol', { symbol: 'BINANCE:ETHUSDTPERP' });
  await sleep(2000);
  await tv('chart_set_timeframe', { timeframe: '240' }); // 4H — matches our bot triggers
  await sleep(2000);
  await tv('chart_set_type', { type: 'Candles' });
  await sleep(1000);

  // Add core indicators
  console.log('Adding indicators...');
  
  // EMA 20 — trend direction
  await tv('chart_manage_indicator', { action: 'add', name: 'Moving Average Exponential', inputs: { length: 20 } });
  await sleep(1500);
  
  // EMA 50 — medium trend
  await tv('chart_manage_indicator', { action: 'add', name: 'Moving Average Exponential', inputs: { length: 50 } });
  await sleep(1500);
  
  // EMA 200 — macro trend
  await tv('chart_manage_indicator', { action: 'add', name: 'Moving Average Exponential', inputs: { length: 200 } });
  await sleep(1500);

  // RSI — momentum
  await tv('chart_manage_indicator', { action: 'add', name: 'Relative Strength Index', inputs: { length: 14 } });
  await sleep(1500);
  
  // Bollinger Bands — volatility / range
  await tv('chart_manage_indicator', { action: 'add', name: 'Bollinger Bands', inputs: { length: 20, mult: 2 } });
  await sleep(1500);

  // Volume — conviction
  await tv('chart_manage_indicator', { action: 'add', name: 'Volume' });
  await sleep(1500);

  // MACD — momentum confirmation
  await tv('chart_manage_indicator', { action: 'add', name: 'MACD', inputs: { fast_length: 12, slow_length: 26, signal_smoothing: 9 } });
  await sleep(1500);

  // ATR — volatility for stop sizing
  await tv('chart_manage_indicator', { action: 'add', name: 'Average True Range', inputs: { length: 14 } });
  await sleep(1500);

  // Draw key grid bot levels for ETH Bot B
  console.log('Drawing Bot B grid levels...');

  // Bot B range: $2,150 - $2,500, SL $2,050, TP $2,580, Trigger $2,350
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 2350 }, color: '#FFD700', text: '🔥 BOT B TRIGGER — ETH must close 4H above here', linewidth: 2, linestyle: 'dashed' });
  await sleep(800);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 2500 }, color: '#00E676', text: '✅ BOT B GRID TOP — Take Profit zone $2,580', linewidth: 1, linestyle: 'dashed' });
  await sleep(800);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 2150 }, color: '#FF9800', text: '📊 BOT B GRID LOW — Grid base $2,150', linewidth: 1, linestyle: 'dashed' });
  await sleep(800);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 2050 }, color: '#FF1744', text: '🛑 BOT B STOP LOSS — Hard SL $2,050', linewidth: 2 });
  await sleep(800);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 2580 }, color: '#69F0AE', text: '💰 BOT B TAKE PROFIT — TP $2,580', linewidth: 2 });
  await sleep(800);

  // Draw grid box zone
  await tv('draw_shape', { type: 'rectangle', point: { price: 2500, time: Math.floor(Date.now()/1000) - 86400*7 }, point2: { price: 2150, time: Math.floor(Date.now()/1000) + 86400*14 }, color: '#1565C0', text: 'BOT B GRID ZONE (20 grids)', transparency: 85 });
  await sleep(800);

  // Screenshot Chart 1
  console.log('Capturing Chart 1 screenshot...');
  const ss1 = await tv('capture_screenshot', { region: 'chart' });
  console.log('CHART1_SCREENSHOT:', JSON.stringify(ss1));

  await sleep(2000);

  // ── CHART 2: BTC/USDT — Next Opportunity / Prediction View ──
  console.log('\nSetting up Chart 2: BTC next opportunity view...');

  // Save layout 1 first
  await tv('pine_save', {}).catch(() => {}); // ignore if no pine editor open

  await tv('chart_set_symbol', { symbol: 'BINANCE:BTCUSDTPERP' });
  await sleep(2000);
  await tv('chart_set_timeframe', { timeframe: '240' }); // 4H
  await sleep(2000);

  // Wipe drawings for clean BTC view
  await tv('draw_clear', {});
  await sleep(800);

  // Add indicators for opportunity scanning
  console.log('Adding opportunity scanner indicators...');

  // Bollinger Bands — squeeze detection
  await tv('chart_manage_indicator', { action: 'add', name: 'Bollinger Bands', inputs: { length: 20, mult: 2 } });
  await sleep(1500);

  // RSI
  await tv('chart_manage_indicator', { action: 'add', name: 'Relative Strength Index', inputs: { length: 14 } });
  await sleep(1500);

  // Volume
  await tv('chart_manage_indicator', { action: 'add', name: 'Volume' });
  await sleep(1500);

  // EMA 21 + EMA 55 — golden/death cross
  await tv('chart_manage_indicator', { action: 'add', name: 'Moving Average Exponential', inputs: { length: 21 } });
  await sleep(1500);
  await tv('chart_manage_indicator', { action: 'add', name: 'Moving Average Exponential', inputs: { length: 55 } });
  await sleep(1500);

  // MACD
  await tv('chart_manage_indicator', { action: 'add', name: 'MACD' });
  await sleep(1500);

  // Draw BTC Bot C levels
  console.log('Drawing Bot C trigger levels...');
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 78100 }, color: '#FFD700', text: '🚀 BOT C TRIGGER — BTC must break + hold above here', linewidth: 2, linestyle: 'dashed' });
  await sleep(800);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 84000 }, color: '#00E676', text: '✅ BOT C GRID TOP / TP $83,500', linewidth: 1, linestyle: 'dashed' });
  await sleep(800);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 72000 }, color: '#FF9800', text: '📊 BOT C GRID LOW $72,000', linewidth: 1, linestyle: 'dashed' });
  await sleep(800);
  await tv('draw_shape', { type: 'horizontal_line', point: { price: 71500 }, color: '#FF1744', text: '🛑 BOT C STOP LOSS $71,500', linewidth: 2 });
  await sleep(800);

  // Grid zone box
  await tv('draw_shape', { type: 'rectangle', point: { price: 84000, time: Math.floor(Date.now()/1000) - 86400*7 }, point2: { price: 72000, time: Math.floor(Date.now()/1000) + 86400*14 }, color: '#4A148C', text: 'BOT C GRID ZONE (24 grids, deploy if trigger fires)', transparency: 85 });
  await sleep(800);

  // Screenshot Chart 2
  console.log('Capturing Chart 2 screenshot...');
  const ss2 = await tv('capture_screenshot', { region: 'chart' });
  console.log('CHART2_SCREENSHOT:', JSON.stringify(ss2));

  // Get current state for both
  console.log('\nGetting final state...');
  const state = await tv('chart_get_state', {});
  console.log('FINAL_STATE:', JSON.stringify(state).substring(0, 500));

  console.log('\n=== SETUP COMPLETE ===');
  proc.kill();
}

main().catch(e => {
  console.error('ERROR:', e.message);
  proc.kill();
  process.exit(1);
});
