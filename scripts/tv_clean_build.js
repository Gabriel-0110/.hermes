const {spawn}=require('child_process');
const fs=require('fs');
const proc=spawn('node',['src/server.js'],{stdio:['pipe','pipe','pipe'],cwd:'/Users/openclaw/Coding/tradingview-mcp-jackson'});
let id=1,buf='';const pend=new Map();
proc.stdout.on('data',(d)=>{buf+=d.toString();const lines=buf.split('\n');buf=lines.pop();for(const l of lines){if(!l.trim())continue;try{const o=JSON.parse(l);if(o.id&&pend.has(o.id)){pend.get(o.id)(o);pend.delete(o.id);}}catch(e){}}});
proc.stderr.on('data',()=>{});
function rpc(m,p){return new Promise(r=>{const i=id++;pend.set(i,r);proc.stdin.write(JSON.stringify({jsonrpc:'2.0',id:i,method:m,params:p})+'\n');setTimeout(()=>{if(pend.has(i)){pend.delete(i);r({error:'timeout'});}},30000);})}
function tv(n,a){return rpc('tools/call',{name:n,arguments:a||{}}).then(r=>{const t=r.result?.content?.[0]?.text||r.result;try{return JSON.parse(t);}catch(e){return t;}});}
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}
const fc=JSON.parse(fs.readFileSync('/Users/openclaw/.hermes/scripts/chronos_forecast.json'));

function buildAllInOne(sym,f,lv){
const sc=f.scenarios,last=f.last;
const trend=sc[11].median>last?'UP':'DOWN';
const pct=((sc[11].median-last)/last*100).toFixed(2);
const mArr=sc.map(s=>s.median.toFixed(2)).join(',');
const lArr=sc.map(s=>s.low.toFixed(2)).join(',');
const hArr=sc.map(s=>s.high.toFixed(2)).join(',');
return `//@version=6
indicator("🤖 Hermes ${sym} — ${lv.bot} + Chronos-2", overlay=true, max_lines_count=500, max_labels_count=500)
// Chronos-2 | amazon/chronos-t5-tiny | 100 samples | 4H | 48h | ${new Date().toISOString().slice(0,16)} UTC
// ${sym} last: ${last} | 48h: ${trend} ${pct}%
var float[] mfc=array.from(${mArr})
var float[] lfc=array.from(${lArr})
var float[] hfc=array.from(${hArr})
ema20=ta.ema(close,20)
ema50=ta.ema(close,50)
[bbMid,bbUp,bbLo]=ta.bb(close,20,2.0)
plot(ema20,  "EMA 20",  color=color.new(color.blue,20),  linewidth=1)
plot(ema50,  "EMA 50",  color=color.new(color.orange,20),linewidth=2)
plot(bbUp,   "BB Up",   color=color.new(color.purple,40),linewidth=1)
plot(bbLo,   "BB Low",  color=color.new(color.purple,40),linewidth=1)
plot(bbMid,  "BB Mid",  color=color.new(color.purple,65),linewidth=1)
hline(${lv.tp},      "💰 TP",       color=color.new(color.lime,  0),linestyle=hline.style_solid, linewidth=2)
hline(${lv.gridTop}, "Grid Top",   color=color.new(color.green, 35),linestyle=hline.style_dashed,linewidth=1)
hline(${lv.trigger}, "🔥 Trigger", color=color.new(color.yellow,0), linestyle=hline.style_dashed,linewidth=3)
hline(${lv.gridBot}, "Grid Low",   color=color.new(color.orange,35),linestyle=hline.style_dashed,linewidth=1)
hline(${lv.sl},      "🛑 SL",      color=color.new(color.red,   0), linestyle=hline.style_solid, linewidth=2)
if barstate.islast
    float pm=close,float pl=close,float ph=close
    for i=0 to 11
        float m=array.get(mfc,i),float lo=array.get(lfc,i),float hi=array.get(hfc,i)
        line.new(bar_index+i,pm,bar_index+i+1,m,  color=color.new(color.yellow,0), width=2)
        line.new(bar_index+i,ph,bar_index+i+1,hi, color=color.new(color.green, 20),width=1,style=line.style_dashed)
        line.new(bar_index+i,pl,bar_index+i+1,lo, color=color.new(color.red,   20),width=1,style=line.style_dashed)
        if i%4==3
            line.new(bar_index+i,lo,bar_index+i,hi,color=color.new(color.gray,65),width=1,style=line.style_dotted)
        pm:=m,pl:=lo,ph:=hi
    float eM=array.get(mfc,11),float eH=array.get(hfc,11),float eL=array.get(lfc,11)
    label.new(bar_index+13,eH,"Chronos-2 +48h\\nMedian: $"+str.tostring(eM,"#.00")+"\\nBull: $"+str.tostring(eH,"#.00")+"\\nBear: $"+str.tostring(eL,"#.00")+"\\n${trend} ${pct}%",color=eM>close?color.new(color.teal,5):color.new(color.maroon,5),textcolor=color.white,style=label.style_label_left,size=size.normal)
    float dist=${lv.trigger}-close
    bool ok=close>=${lv.trigger}
    label.new(bar_index,${lv.trigger},ok?"✅ BOT TRIGGERED":"⚡ $"+str.tostring(math.abs(dist),"#.00")+" to trigger",color=ok?color.new(color.lime,20):color.new(color.orange,20),textcolor=color.white,style=label.style_label_right,size=size.small)
var table d=table.new(position.top_right,2,11,bgcolor=color.new(color.black,10),border_width=1,border_color=color.new(color.gray,60))
if barstate.islast
    float dist=math.abs(${lv.trigger}-close),float dp=dist/close*100,bool ok=close>=${lv.trigger}
    table.cell(d,0,0,"HERMES ${sym}",         bgcolor=color.new(#0d1b4b,0),text_color=color.yellow,text_size=size.normal)
    table.cell(d,1,0,"${lv.bot}",             bgcolor=color.new(#0d1b4b,0),text_color=color.yellow,text_size=size.small)
    table.cell(d,0,1,"Price",                 text_color=color.silver,text_size=size.small)
    table.cell(d,1,1,"$"+str.tostring(close,"#.00"),text_color=color.aqua,text_size=size.small)
    table.cell(d,0,2,"EMA Signal",            text_color=color.silver,text_size=size.small)
    table.cell(d,1,2,ema20>ema50?"▲ EMA20>50 BULL":"▼ EMA20<50 BEAR",text_color=ema20>ema50?color.lime:color.red,text_size=size.tiny)
    table.cell(d,0,3,"BB Position",           text_color=color.silver,text_size=size.small)
    table.cell(d,1,3,close>bbUp?"OVERBOUGHT ⚠️":close<bbLo?"OVERSOLD ✅":"INSIDE BANDS",text_color=close>bbUp?color.red:close<bbLo?color.lime:color.gray,text_size=size.tiny)
    table.cell(d,0,4,"Bot Trigger",           text_color=color.silver,text_size=size.small)
    table.cell(d,1,4,ok?"✅ ACTIVE":"$"+str.tostring(dist,"#.00")+" ("+str.tostring(dp,"#.2")+"%)",text_color=ok?color.lime:color.orange,text_size=size.small)
    table.cell(d,0,5,"Chronos +4h",           text_color=color.silver,text_size=size.small)
    table.cell(d,1,5,"$"+str.tostring(array.get(mfc,0),"#.00"),text_color=color.yellow,text_size=size.small)
    table.cell(d,0,6,"Chronos +12h",          text_color=color.silver,text_size=size.small)
    table.cell(d,1,6,"$"+str.tostring(array.get(mfc,2),"#.00"),text_color=color.yellow,text_size=size.small)
    table.cell(d,0,7,"Chronos +24h",          text_color=color.silver,text_size=size.small)
    table.cell(d,1,7,"$"+str.tostring(array.get(mfc,5),"#.00"),text_color=color.yellow,text_size=size.small)
    table.cell(d,0,8,"Chronos +48h",          text_color=color.silver,text_size=size.small)
    table.cell(d,1,8,"$"+str.tostring(array.get(mfc,11),"#.00")+" (${trend} ${pct}%)",text_color=${sc[11].median>last}?color.lime:color.red,text_size=size.small)
    table.cell(d,0,9,"Grid Zone",             text_color=color.silver,text_size=size.small)
    table.cell(d,1,9,"${lv.gridBot}–${lv.gridTop}",text_color=color.aqua,text_size=size.small)
    table.cell(d,0,10,"SL / TP",              text_color=color.silver,text_size=size.small)
    table.cell(d,1,10,"${lv.sl} / ${lv.tp}", text_color=color.lime,text_size=size.small)
`;}

async function buildView(sym, symbol, lvs) {
  console.log(`\nBuilding ${sym} view...`);
  
  // Switch symbol + timeframe
  await tv('chart_set_symbol',{symbol}); await sleep(3500);
  await tv('chart_set_timeframe',{timeframe:'240'}); await sleep(2500);
  await tv('draw_clear',{}); await sleep(500);

  // Remove all existing studies
  const s=await tv('chart_get_state',{});
  for(const st of (s.studies||[])){
    await tv('chart_manage_indicator',{action:'remove',indicator:st.name,entity_id:st.id}).catch(()=>{});
    await sleep(600);
  }
  await sleep(1000);

  // Ensure Pine editor is open
  const ui=await tv('tv_ui_state',{});
  if(!ui.pine_editor?.open){ await tv('ui_open_panel',{panel:'pine-editor'}); await sleep(2500); }

  // New blank Pine script
  await tv('pine_new',{type:'indicator'}); await sleep(2500);

  // Set source
  const code=buildAllInOne(sym, fc[sym], lvs);
  await tv('pine_set_source',{source:code}); await sleep(2000);

  // Compile and ADD to chart  
  const c=await tv('pine_compile',{}); 
  console.log(`${sym} pine_compile:`, JSON.stringify(c).substring(0,150));
  await sleep(6000); // wait for chart to render the new indicator

  // CLOSE Pine editor so we can see the full chart
  await tv('ui_open_panel',{panel:'pine-editor'}); await sleep(3000);

  // Check it's on the chart now
  const s2=await tv('chart_get_state',{});
  console.log(`${sym} studies:`, JSON.stringify((s2.studies||[]).map(x=>x.name)));

  // Screenshot the clean chart
  const ss=await tv('capture_screenshot',{region:'chart'});
  console.log(`${sym}_SCREENSHOT:`, ss.file_path);
  return ss.file_path;
}

async function main(){
  await rpc('initialize',{protocolVersion:'2024-11-05',capabilities:{},clientInfo:{name:'hermes-final',version:'1'}});

  // Close any open modal
  await tv('ui_click',{by:'aria-label',value:'Close'}).catch(()=>{});
  await sleep(1000);

  const ethFile = await buildView('ETH','BINANCE:ETHUSDTPERP',{
    bot:'BOT B — LONG GRID',trigger:2350,gridTop:2500,gridBot:2150,sl:2050,tp:2580
  });

  const btcFile = await buildView('BTC','BINANCE:BTCUSDTPERP',{
    bot:'BOT C — GRID (TRIGGER PENDING)',trigger:78100,gridTop:84000,gridBot:72000,sl:71500,tp:83500
  });

  console.log('\n=== COMPLETE ===');
  console.log('ETH view:', ethFile);
  console.log('BTC view:', btcFile);
  console.log('\nChronos-2 Forecasts:');
  console.log('ETH +48h: med $'+fc.ETH.scenarios[11].median+' | high $'+fc.ETH.scenarios[11].high+' | low $'+fc.ETH.scenarios[11].low);
  console.log('BTC +48h: med $'+fc.BTC.scenarios[11].median+' | high $'+fc.BTC.scenarios[11].high+' | low $'+fc.BTC.scenarios[11].low);
  proc.kill();
}

main().catch(e=>{console.error('FATAL:',e.message);proc.kill();process.exit(1);});
