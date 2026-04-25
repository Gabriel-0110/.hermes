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

function pine(sym,f,lv){
const sc=f.scenarios,last=f.last;
const trend=sc[11].median>last?'UP ▲':'DOWN ▼';
const pct=((sc[11].median-last)/last*100).toFixed(2);
const mArr=sc.map(s=>s.median.toFixed(2)).join(',');
const lArr=sc.map(s=>s.low.toFixed(2)).join(',');
const hArr=sc.map(s=>s.high.toFixed(2)).join(',');
return `//@version=5
indicator("🤖 Hermes ${sym} — ${lv.bot} + Chronos-2 Forecast", overlay=true, max_lines_count=500, max_labels_count=500)
// Chronos-2 live ML forecast | amazon/chronos-t5-tiny | 100 samples | 4H | 48h horizon
// Generated: ${new Date().toISOString().slice(0,16)} UTC | ${sym} last: ${last} | 48h: ${trend} ${pct}%

var float[] mfc=array.from(${mArr})
var float[] lfc=array.from(${lArr})
var float[] hfc=array.from(${hArr})

// ── Key Levels ──
hline(${lv.tp},      "💰 Take Profit",     color=color.new(color.lime,   0), linestyle=hline.style_solid,  linewidth=2)
hline(${lv.gridTop}, "Grid Top",           color=color.new(color.green,  30),linestyle=hline.style_dashed, linewidth=1)
hline(${lv.trigger}, "🔥 Bot Trigger",     color=color.new(color.yellow, 0), linestyle=hline.style_dashed, linewidth=3)
hline(${lv.gridBot}, "Grid Low",           color=color.new(color.orange, 30),linestyle=hline.style_dashed, linewidth=1)
hline(${lv.sl},      "🛑 Stop Loss",       color=color.new(color.red,    0), linestyle=hline.style_solid,  linewidth=2)

// ── Chronos-2 Forecast Fan (last bar only) ──
if barstate.islast
    float pm=close, float pl=close, float ph=close
    for i=0 to 11
        x0=bar_index+i
        x1=bar_index+i+1
        m=array.get(mfc,i), lo=array.get(lfc,i), hi=array.get(hfc,i)
        line.new(x0,pm,x1,m,  color=color.new(color.yellow,0), width=2)
        line.new(x0,ph,x1,hi, color=color.new(color.green, 25),width=1,style=line.style_dashed)
        line.new(x0,pl,x1,lo, color=color.new(color.red,   25),width=1,style=line.style_dashed)
        pm:=m, pl:=lo, ph:=hi
    for i=0 to 2
        s=(i+1)*4-1
        line.new(bar_index+s,array.get(lfc,s),bar_index+s,array.get(hfc,s),color=color.new(color.gray,60),width=1,style=line.style_dotted)
    eM=array.get(mfc,11), eH=array.get(hfc,11), eL=array.get(lfc,11)
    lc=eM>close?color.new(color.teal,10):color.new(color.maroon,10)
    label.new(bar_index+13,eH,"Chronos-2 +48h\\nMedian: "+str.tostring(eM,"#.00")+"\\nHigh: "+str.tostring(eH,"#.00")+"\\nLow: "+str.tostring(eL,"#.00")+"\\n${trend} ${pct}%",color=lc,textcolor=color.white,style=label.style_label_left,size=size.normal)

// ── Dashboard Table ──
var table d=table.new(position.top_right,2,10,bgcolor=color.new(color.black,15),border_width=1,border_color=color.new(color.gray,50))
if barstate.islast
    dist=math.abs(${lv.trigger}-close)
    dpct=dist/close*100
    ok=close>=${lv.trigger}
    table.cell(d,0,0,"HERMES ${sym}",        text_color=color.yellow,bgcolor=color.new(#1a237e,10),text_size=size.normal)
    table.cell(d,1,0,"${lv.bot}",            text_color=color.yellow,bgcolor=color.new(#1a237e,10),text_size=size.normal)
    table.cell(d,0,1,"Price",                text_color=color.silver,text_size=size.small)
    table.cell(d,1,1,str.tostring(close,"#.00"),text_color=color.aqua,text_size=size.small)
    table.cell(d,0,2,"Bot Trigger",          text_color=color.silver,text_size=size.small)
    table.cell(d,1,2,ok?"✅ ACTIVE":"$${(lv.trigger).toFixed(0)} — "+str.tostring(dist,"#.00")+" away ("+str.tostring(dpct,"#.2")+"%)",text_color=ok?color.lime:color.orange,text_size=size.small)
    table.cell(d,0,3,"Chronos +4h",          text_color=color.silver,text_size=size.small)
    table.cell(d,1,3,str.tostring(array.get(mfc,0),"#.00"),text_color=color.yellow,text_size=size.small)
    table.cell(d,0,4,"Chronos +12h",         text_color=color.silver,text_size=size.small)
    table.cell(d,1,4,str.tostring(array.get(mfc,2),"#.00"),text_color=color.yellow,text_size=size.small)
    table.cell(d,0,5,"Chronos +24h",         text_color=color.silver,text_size=size.small)
    table.cell(d,1,5,str.tostring(array.get(mfc,5),"#.00"),text_color=color.yellow,text_size=size.small)
    table.cell(d,0,6,"Chronos +48h",         text_color=color.silver,text_size=size.small)
    table.cell(d,1,6,str.tostring(array.get(mfc,11),"#.00")+" (${trend} ${pct}%)",text_color=${sc[11].median>last}?color.lime:color.red,text_size=size.small)
    table.cell(d,0,7,"Grid zone",            text_color=color.silver,text_size=size.small)
    table.cell(d,1,7,"${lv.gridBot} — ${lv.gridTop}",text_color=color.aqua,text_size=size.small)
    table.cell(d,0,8,"Stop / TP",            text_color=color.silver,text_size=size.small)
    table.cell(d,1,8,"${lv.sl} / ${lv.tp}", text_color=color.lime,text_size=size.small)
    table.cell(d,0,9,"Model",                text_color=color.silver,text_size=size.small)
    table.cell(d,1,9,"Chronos-2 | "+str.tostring(timenow,"HHmm")+" UTC",text_color=color.gray,text_size=size.tiny)
`;
}

async function main(){
  await rpc('initialize',{protocolVersion:'2024-11-05',capabilities:{},clientInfo:{name:'hermes-views',version:'1'}});

  // ═══ VIEW 1: ETH 4H — Bot B active view ═══
  console.log('Building ETH view...');
  await tv('chart_set_symbol',{symbol:'BINANCE:ETHUSDTPERP'});
  await sleep(3000);
  await tv('chart_set_timeframe',{timeframe:'240'});
  await sleep(2000);
  await tv('draw_clear',{});
  await sleep(500);

  // Remove all existing indicators
  let s=await tv('chart_get_state',{});
  for(const st of (s.studies||[])){
    await tv('chart_manage_indicator',{action:'remove',indicator:st.name,entity_id:st.id}).catch(()=>{});
    await sleep(400);
  }
  await sleep(500);

  // Add clean indicator stack
  await tv('chart_manage_indicator',{action:'add',indicator:'Relative Strength Index'});   await sleep(1200);
  await tv('chart_manage_indicator',{action:'add',indicator:'MACD'});                       await sleep(1200);
  await tv('chart_manage_indicator',{action:'add',indicator:'Bollinger Bands'});            await sleep(1200);
  await tv('chart_manage_indicator',{action:'add',indicator:'Volume'});                     await sleep(1200);
  await tv('chart_manage_indicator',{action:'add',indicator:'Moving Average Exponential',inputs:'{"length":20}'}); await sleep(1200);
  await tv('chart_manage_indicator',{action:'add',indicator:'Moving Average Exponential',inputs:'{"length":50}'}); await sleep(1200);

  // Open Pine editor and inject ETH script
  await tv('ui_open_panel',{panel:'pine-editor'});
  await sleep(2500);
  await tv('pine_new',{type:'indicator'});
  await sleep(2000);

  const ethCode=pine('ETH',fc.ETH,{
    bot:'BOT B — LONG GRID',trigger:2350,gridTop:2500,gridBot:2150,sl:2050,tp:2580
  });
  await tv('pine_set_source',{source:ethCode});
  await sleep(2000);
  const c1=await tv('pine_smart_compile',{});
  console.log('ETH compile errors:',c1.has_errors,c1.errors?.slice(0,2));
  await sleep(4000);

  const ss1=await tv('capture_screenshot',{region:'chart'});
  console.log('ETH_SCREENSHOT:',ss1.file_path);
  await sleep(1000);

  // ═══ VIEW 2: BTC 4H — Bot C trigger + predictions ═══
  console.log('\nBuilding BTC view...');
  await tv('chart_set_symbol',{symbol:'BINANCE:BTCUSDTPERP'});
  await sleep(3000);
  await tv('chart_set_timeframe',{timeframe:'240'});
  await sleep(2000);
  await tv('draw_clear',{});
  await sleep(500);

  s=await tv('chart_get_state',{});
  for(const st of (s.studies||[])){
    await tv('chart_manage_indicator',{action:'remove',indicator:st.name,entity_id:st.id}).catch(()=>{});
    await sleep(400);
  }
  await sleep(500);

  await tv('chart_manage_indicator',{action:'add',indicator:'Relative Strength Index'});   await sleep(1200);
  await tv('chart_manage_indicator',{action:'add',indicator:'MACD'});                       await sleep(1200);
  await tv('chart_manage_indicator',{action:'add',indicator:'Bollinger Bands'});            await sleep(1200);
  await tv('chart_manage_indicator',{action:'add',indicator:'Volume'});                     await sleep(1200);
  await tv('chart_manage_indicator',{action:'add',indicator:'Moving Average Exponential',inputs:'{"length":20}'}); await sleep(1200);
  await tv('chart_manage_indicator',{action:'add',indicator:'Moving Average Exponential',inputs:'{"length":50}'}); await sleep(1200);

  await tv('pine_new',{type:'indicator'});
  await sleep(2000);

  const btcCode=pine('BTC',fc.BTC,{
    bot:'BOT C — GRID (NEEDS TRIGGER)',trigger:78100,gridTop:84000,gridBot:72000,sl:71500,tp:83500
  });
  await tv('pine_set_source',{source:btcCode});
  await sleep(2000);
  const c2=await tv('pine_smart_compile',{});
  console.log('BTC compile errors:',c2.has_errors,c2.errors?.slice(0,2));
  await sleep(4000);

  const ss2=await tv('capture_screenshot',{region:'chart'});
  console.log('BTC_SCREENSHOT:',ss2.file_path);

  console.log('\nDone.');
  console.log('ETH 48h forecast: median $'+fc.ETH.scenarios[11].median+' | high $'+fc.ETH.scenarios[11].high+' | low $'+fc.ETH.scenarios[11].low);
  console.log('BTC 48h forecast: median $'+fc.BTC.scenarios[11].median+' | high $'+fc.BTC.scenarios[11].high+' | low $'+fc.BTC.scenarios[11].low);
  proc.kill();
}

main().catch(e=>{console.error('ERR:',e.message);proc.kill();process.exit(1);});
