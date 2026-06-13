#!/usr/bin/env python3
"""Dashboard for the best GA off-grid city solutions (top 5 by objective + Munich).

Shows: locations on a lon/lat map, energy-mix composition, CO2, time-to-energy,
and the load-curve matching (representative week) for each selected city.
"""
import json
from pathlib import Path

import numpy as np
import ga_solver as ga

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
OUT = HERE / "ga_dashboard.html"


def full_dispatch(city, load_kw, sizes):
    """Reconstruct the full 8760-h served-by-source dispatch for a city's chosen design."""
    ctx = ga.load_city_context(city, load_kw=load_kw)
    pv_kw = sizes["pv_kw"]; wind_kw = sizes["wind_kw"]
    batt_kwh = sizes["battery_kwh"]; gen_kw = sizes["gen_kw"]
    batt_kw = batt_kwh / ga.BATT_DURATION_H
    n = ctx["pv"].shape[0]
    pv_l = np.zeros(n); wind_l = np.zeros(n); batt_l = np.zeros(n)
    gas_l = np.zeros(n); unmet_l = np.zeros(n)
    ga.dispatch_series(load_kw, ctx["pv"], ctx["wind"], pv_kw, wind_kw, batt_kwh,
                       batt_kw, gen_kw, ga.BATT_RT_EFF, pv_l, wind_l, batt_l, gas_l, unmet_l)
    renew = pv_kw * ctx["pv"] + wind_kw * ctx["wind"]
    return pv_l, wind_l, batt_l, gas_l, unmet_l, renew

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>GA Off-Grid Optimization - Best German Cities</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
 :root{--bg:#0f1420;--panel:#171f2e;--line:#2b3650;--txt:#e6edf6;--muted:#93a4bd;
  --pv:#fbbd23;--wind:#36d399;--batt:#a78bfa;--gas:#f87272;--unmet:#5b7290;--accent:#3ea6ff;}
 *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
 header{padding:24px 32px 14px;border-bottom:1px solid var(--line);background:linear-gradient(180deg,#141c2b,#0f1420);}
 header h1{margin:0 0 6px;font-size:21px}header .sub{color:var(--muted);font-size:13px}
 .wrap{padding:22px 32px 60px;max-width:1360px;margin:0 auto}
 .grid{display:grid;gap:16px}
 .cards{grid-template-columns:repeat(auto-fit,minmax(200px,1fr));margin-bottom:20px}
 .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
 .card.muni{border-color:#a78bfa;box-shadow:0 0 0 1px #a78bfa55}
 .rank{font-size:12px;color:var(--muted);letter-spacing:.5px}
 .city{font-size:19px;font-weight:700;margin:2px 0 8px}
 .kv{display:flex;justify-content:space-between;font-size:12.5px;padding:2px 0;color:var(--muted)}
 .kv b{color:var(--txt);font-weight:600}
 .badge{display:inline-block;font-size:10px;padding:2px 7px;border-radius:999px;background:#2a2150;color:#a78bfa;margin-left:6px}
 .charts{grid-template-columns:repeat(2,1fr)}.charts .full{grid-column:1 / -1}
 .card h3{margin:0 0 4px;font-size:15px}.card .hint{color:var(--muted);font-size:12px;margin:0 0 12px}
 .chartbox{position:relative;height:300px}
 .weeks{grid-template-columns:repeat(3,1fr)}
 .weeks .wk{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
 .weeks .wk h4{margin:0 0 8px;font-size:13px}
 .wkbox{position:relative;height:170px}
 .foot{color:var(--muted);font-size:12px;margin-top:22px;line-height:1.6}
 @media(max-width:980px){.charts{grid-template-columns:1fr}.weeks{grid-template-columns:1fr}}
</style></head><body>
<header><h1>GA Off-Grid Optimization &mdash; Best German City Solutions</h1>
<div class="sub" id="subhdr"></div></header>
<div class="wrap">
 <div class="grid cards" id="cards"></div>
 <div class="grid charts">
  <div class="card"><h3>Locations on the map</h3><p class="hint">Selected cities (colored) among all 20 in the database (grey). x=longitude, y=latitude.</p>
   <div class="chartbox"><canvas id="mapChart"></canvas></div></div>
  <div class="card"><h3>Energy-mix composition</h3><p class="hint">Share of annual load served by each source (target 80%).</p>
   <div class="chartbox"><canvas id="mixChart"></canvas></div></div>
  <div class="card"><h3>Time to energy (buildout) &amp; CO&#8322;</h3><p class="hint">Years to deploy (MAX over built techs) and annual CO2.</p>
   <div class="chartbox"><canvas id="btChart"></canvas></div></div>
  <div class="card"><h3>System size &amp; cost</h3><p class="hint">Installed capacity (PV/Wind/Gas kW, Battery kWh/10) and lifecycle cost.</p>
   <div class="chartbox"><canvas id="sizeChart"></canvas></div></div>
 </div>
 <h3 style="margin:26px 0 4px;font-size:16px">Load-curve matching
   <select id="weekSel" style="margin-left:10px;background:#1e293b;color:#e6edf6;border:1px solid #2b3650;border-radius:6px;padding:4px 8px;font-size:13px"></select>
   <button id="stressBtn" style="margin-left:6px;background:#1e293b;color:#93a4bd;border:1px solid #2b3650;border-radius:6px;padding:4px 9px;font-size:12px;cursor:pointer">jump to most-stressed week</button>
 </h3>
 <p style="color:var(--muted);font-size:12px;margin:0 0 14px">How each source covers the constant 1000 kW load in the selected week. Gold=solar, green=wind, purple=battery, red=gas, grey=unmet.</p>
 <div class="grid weeks" id="weeks"></div>
 <div class="foot" id="foot"></div>
</div>
<script>
const D=__DATA__;const S=D.selected;
const COL={pv:"#fbbd23",wind:"#36d399",battery:"#a78bfa",gas:"#f87272",unmet:"#5b7290"};
const f0=n=>Math.round(n).toLocaleString();
const MLM=Math.round((D.min_load_met||0.99)*100);
document.getElementById("subhdr").innerHTML=
 "Island systems (PV + Wind + Battery + Gas) | constant 1000 kW load | weights time 0.50 / cost 0.35 / CO2 0.15 | "
 +"min load met "+MLM+"% | solver: genetic algorithm";
// KPI cards
document.getElementById("cards").innerHTML=S.map(c=>`
 <div class="card ${c.is_munich?'muni':''}">
   <div class="rank">#${c.rank} by objective ${c.is_munich?'<span class=badge>Munich</span>':''}</div>
   <div class="city">${c.city}</div>
   <div class="kv"><span>PV / Wind</span><b>${f0(c.sizes.pv_kw)} / ${f0(c.sizes.wind_kw)} kW</b></div>
   <div class="kv"><span>Gas / Battery</span><b>${f0(c.sizes.gen_kw)} kW / ${f0(c.sizes.battery_kwh)} kWh</b></div>
   <div class="kv"><span>Buildout</span><b>${c.buildout.toFixed(1)} yr</b></div>
   <div class="kv"><span>CO&#8322;</span><b>${f0(c.co2)} t/yr</b></div>
   <div class="kv"><span>LCC</span><b>\u20ac${(c.lcc/1e6).toFixed(1)}M</b></div>
   <div class="kv"><span>Load met</span><b>${(c.served*100).toFixed(0)}%</b></div>
 </div>`).join("");
Chart.defaults.color="#93a4bd";Chart.defaults.borderColor="#2b3650";
Chart.defaults.font.family=getComputedStyle(document.body).fontFamily;
const labels=S.map(c=>c.city);

// map scatter
new Chart(mapChart,{type:"scatter",data:{datasets:[
  {label:"all cities",data:D.all_coords.map(c=>({x:c.lon,y:c.lat})),backgroundColor:"#3a4760",pointRadius:4},
  {label:"selected",data:S.map(c=>({x:c.lon,y:c.lat,city:c.city})),backgroundColor:S.map(c=>c.is_munich?"#a78bfa":"#3ea6ff"),pointRadius:7},
 ]},options:{responsive:true,maintainAspectRatio:false,
   scales:{x:{title:{display:true,text:"longitude"}},y:{title:{display:true,text:"latitude"}}},
   plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.raw.city||""}}}}});

// energy mix shares (stacked %)
new Chart(mixChart,{type:"bar",data:{labels,datasets:[
  {label:"Solar",data:S.map(c=>c.shares.pv),backgroundColor:COL.pv,stack:"s"},
  {label:"Wind",data:S.map(c=>c.shares.wind),backgroundColor:COL.wind,stack:"s"},
  {label:"Battery",data:S.map(c=>c.shares.battery),backgroundColor:COL.battery,stack:"s"},
  {label:"Gas",data:S.map(c=>c.shares.gas),backgroundColor:COL.gas,stack:"s"},
  {label:"Unmet",data:S.map(c=>c.shares.unmet),backgroundColor:COL.unmet,stack:"s"},
 ]},options:{responsive:true,maintainAspectRatio:false,
   scales:{x:{stacked:true},y:{stacked:true,title:{display:true,text:"% of load"},max:100}},
   plugins:{tooltip:{callbacks:{label:c=>c.dataset.label+": "+c.raw+"%"}}}}});

// buildout + CO2 (dual axis)
new Chart(btChart,{data:{labels,datasets:[
  {type:"bar",label:"Buildout (yr)",data:S.map(c=>c.buildout),backgroundColor:"#3ea6ff",yAxisID:"y"},
  {type:"bar",label:"CO2 (t/yr)",data:S.map(c=>c.co2),backgroundColor:"#f87272",yAxisID:"y1"},
 ]},options:{responsive:true,maintainAspectRatio:false,
   scales:{y:{position:"left",title:{display:true,text:"years"}},
     y1:{position:"right",grid:{drawOnChartArea:false},title:{display:true,text:"t CO2/yr"}}}}});

// sizes + cost
new Chart(sizeChart,{data:{labels,datasets:[
  {type:"bar",label:"PV kW",data:S.map(c=>c.sizes.pv_kw),backgroundColor:COL.pv,stack:"k"},
  {type:"bar",label:"Wind kW",data:S.map(c=>c.sizes.wind_kw),backgroundColor:COL.wind,stack:"k"},
  {type:"bar",label:"Gas kW",data:S.map(c=>c.sizes.gen_kw),backgroundColor:COL.gas,stack:"k"},
  {type:"bar",label:"Battery kWh/10",data:S.map(c=>c.sizes.battery_kwh/10),backgroundColor:COL.battery,stack:"k"},
  {type:"line",label:"LCC (M EUR)",data:S.map(c=>c.lcc/1e6),borderColor:"#e6edf6",yAxisID:"y1",tension:.3},
 ]},options:{responsive:true,maintainAspectRatio:false,
   scales:{y:{stacked:true,title:{display:true,text:"kW (battery kWh/10)"}},
     y1:{position:"right",grid:{drawOnChartArea:false},title:{display:true,text:"M EUR"}}}}});

// dispatch weeks (interactive week selector)
const NW = D.nweeks;
const HRS = Array.from({length:168}, (_,h)=>h);
const wkDiv=document.getElementById("weeks");
S.forEach((c,i)=>{
  const d=document.createElement("div");d.className="wk";
  d.innerHTML=`<h4>${c.city}${c.is_munich?' (Munich)':''}</h4><div class="wkbox"><canvas id="wk${i}"></canvas></div>`;
  wkDiv.appendChild(d);
});
const slice=(arr,w)=>arr.slice(w*168, w*168+168);
const wkCharts=[];
function buildWeek(c,i,w){
  const s=c.series;
  return new Chart(document.getElementById("wk"+i),{type:"line",data:{labels:HRS,datasets:[
    {label:"Solar",data:slice(s.pv,w),backgroundColor:"rgba(251,189,35,.8)",borderColor:COL.pv,fill:true,stack:"s",pointRadius:0,borderWidth:0},
    {label:"Wind",data:slice(s.wind,w),backgroundColor:"rgba(54,211,153,.7)",borderColor:COL.wind,fill:true,stack:"s",pointRadius:0,borderWidth:0},
    {label:"Battery",data:slice(s.battery,w),backgroundColor:"rgba(167,139,250,.8)",borderColor:COL.battery,fill:true,stack:"s",pointRadius:0,borderWidth:0},
    {label:"Gas",data:slice(s.gas,w),backgroundColor:"rgba(248,114,114,.8)",borderColor:COL.gas,fill:true,stack:"s",pointRadius:0,borderWidth:0},
    {label:"Unmet",data:slice(s.unmet,w),backgroundColor:"rgba(91,114,144,.8)",borderColor:COL.unmet,fill:true,stack:"s",pointRadius:0,borderWidth:0},
    {label:"Load",data:HRS.map(()=>c.load_kw),borderColor:"#e6edf6",borderWidth:1.5,fill:false,pointRadius:0,borderDash:[3,2]},
   ]},options:{responsive:true,maintainAspectRatio:false,animation:false,
     scales:{x:{ticks:{maxTicksLimit:7},title:{display:true,text:"hour of week"}},
       y:{stacked:true,title:{display:true,text:"kW"}}},
     plugins:{legend:{display:i===0,labels:{boxWidth:10,font:{size:9}}}}}});
}
function setWeek(w){
  S.forEach((c,i)=>{
    const s=c.series, ch=wkCharts[i];
    ch.data.datasets[0].data=slice(s.pv,w);
    ch.data.datasets[1].data=slice(s.wind,w);
    ch.data.datasets[2].data=slice(s.battery,w);
    ch.data.datasets[3].data=slice(s.gas,w);
    ch.data.datasets[4].data=slice(s.unmet,w);
    ch.update();
  });
}
// populate selector
const sel2=document.getElementById("weekSel");
const MONTHS=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
for(let w=0; w<NW; w++){
  const o=document.createElement("option"); o.value=w;
  const approxMonth=MONTHS[Math.min(11, Math.floor(w/4.345))];
  o.textContent="Week "+(w+1)+"  ("+approxMonth+")"+(w===D.stress_week?"  - most stressed":"");
  sel2.appendChild(o);
}
sel2.value=D.stress_week;
S.forEach((c,i)=>wkCharts.push(buildWeek(c,i,D.stress_week)));
sel2.onchange=()=>setWeek(parseInt(sel2.value));
document.getElementById("stressBtn").onclick=()=>{sel2.value=D.stress_week; setWeek(D.stress_week);};

const gasfree=S.filter(c=>c.sizes.gen_kw<1).map(c=>c.city);
let msg="<b>Read:</b> cities ranked by the GA objective (weighted cost/CO2/time), serving "+MLM+"% of load off-grid. ";
if(gasfree.length){
  msg+="With these prices, wind-rich cities ("+gasfree.join(", ")+") go fully gas-free on large batteries "
      +"(lower buildout, 0 CO2); the rest keep a small gas backstop.";
}else{
  msg+="Cheap solar + cheap battery now dominate the mix, but every system still keeps a small gas backstop "
      +"for deep-winter lulls. Since wind and gas now share the same 4-yr lead time, going wind-heavy no longer "
      +"shortens the buildout, so all systems land at 4 yr; CO2 is low thanks to storage.";
}
msg+=" Munich is shown for reference. Each GA run solved in under 1 second.";
document.getElementById("foot").innerHTML=msg;
</script></body></html>
"""

records = {}
for p in RES.glob("*.json"):
    if p.name.startswith("_"):
        continue
    records[p.stem] = json.load(open(p))

# rank by GA objective (lower fitness = better)
ranked = sorted(records.values(), key=lambda r: r["solver"]["fitness"])
top = ranked[:5]
names = [r["location"]["city"] for r in top]
if "Munich" not in names and "Munich" in records:
    top.append(records["Munich"])  # ensure Munich is included

all_coords = [{"city": r["location"]["city"], "lon": r["location"]["longitude"],
               "lat": r["location"]["latitude"]} for r in records.values()]

sel = []
renew_weekly_sum = None
NHOURS = None
for rank, r in enumerate(top, 1):
    em = r["energy_mix"]; s = em["sizes_kw"]
    load_kw = r["config"].get("load_kw", 1000.0)
    pv_l, wind_l, batt_l, gas_l, unmet_l, renew = full_dispatch(r["location"]["city"], load_kw, s)
    NHOURS = len(pv_l)
    nweeks = NHOURS // 168
    # accumulate renewable availability per week (to find the globally most-stressed week)
    wk = np.array([renew[w * 168:(w + 1) * 168].sum() for w in range(nweeks)])
    renew_weekly_sum = wk if renew_weekly_sum is None else renew_weekly_sum + wk
    sel.append({
        "rank": rank, "city": r["location"]["city"],
        "lat": r["location"]["latitude"], "lon": r["location"]["longitude"],
        "is_munich": r["location"]["city"] == "Munich",
        "sizes": s, "shares": em["shares_pct_of_load"], "served": em["served_fraction"],
        "co2": r["co2"]["annual_tonnes"],
        "buildout": r["time_to_energy"]["system_buildout_time_years"],
        "lcc": r["economics"]["lcc_eur"], "fitness": r["solver"]["fitness"],
        "load_kw": load_kw,
        "series": {  # full 8760-h dispatch (rounded ints to keep the file small)
            "pv": [int(round(x)) for x in pv_l],
            "wind": [int(round(x)) for x in wind_l],
            "battery": [int(round(x)) for x in batt_l],
            "gas": [int(round(x)) for x in gas_l],
            "unmet": [int(round(x)) for x in unmet_l],
        },
    })

nweeks = NHOURS // 168
stress_week = int(np.argmin(renew_weekly_sum)) if renew_weekly_sum is not None else 0
min_load_met = top[0]["config"].get("min_load_met", 0.99)
payload = {"selected": sel, "all_coords": all_coords, "min_load_met": min_load_met,
           "nweeks": nweeks, "stress_week": stress_week}
HTML = HTML_TEMPLATE.replace("__DATA__", json.dumps(payload))
open(OUT, "w").write(HTML)
print(f"Wrote {OUT}")
print("Selected (rank: city, LCC M, buildout yr, CO2 t):")
for c in sel:
    tag = " [Munich]" if c["is_munich"] else ""
    print(f"  {c['rank']}: {c['city']:<11} {c['lcc']/1e6:>5.1f}M  {c['buildout']:.1f}yr  {c['co2']:.0f}t{tag}")
