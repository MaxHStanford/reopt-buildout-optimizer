#!/usr/bin/env python3
"""Dashboard for a parameterized buildout-time REopt run.

Usage: python3 build_dashboard.py [output_dir]
Reads <dir>/results.json + <dir>/weight_mapping.json, writes <dir>/dashboard.html.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTDIR = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "output"

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>REopt Buildout-Time Optimization</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
 :root{--bg:#0f1420;--panel:#171f2e;--line:#2b3650;--txt:#e6edf6;--muted:#93a4bd;
  --accent:#3ea6ff;--green:#36d399;--amber:#fbbd23;--red:#f87272;--purple:#a78bfa;--grid:#5b7290;}
 *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
 header{padding:26px 32px 16px;border-bottom:1px solid var(--line);background:linear-gradient(180deg,#141c2b,#0f1420);}
 header h1{margin:0 0 6px;font-size:21px}header .sub{color:var(--muted);font-size:13px}
 .wrap{padding:22px 32px 60px;max-width:1320px;margin:0 auto}
 .grid{display:grid;gap:16px}.kpis{grid-template-columns:repeat(auto-fit,minmax(165px,1fr));margin-bottom:20px}
 .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 20px}
 .kpi .label{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.6px}
 .kpi .val{font-size:24px;font-weight:700;margin-top:7px;line-height:1.1}.kpi .unit{font-size:13px;color:var(--muted);font-weight:500}
 .kpi .delta{font-size:12px;margin-top:6px}.pos{color:var(--green)}.neutral{color:var(--muted)}
 .hero{border:1px solid #3a2f5a;background:linear-gradient(180deg,#1c1733,#171f2e)}.hero .val{font-size:32px;color:var(--purple)}
 .charts{grid-template-columns:repeat(2,1fr)}.charts .full{grid-column:1 / -1}
 .card h3{margin:0 0 4px;font-size:15px}.card .hint{color:var(--muted);font-size:12px;margin:0 0 14px}
 .chartbox{position:relative;height:300px}.chartbox.tall{height:360px}
 .foot{color:var(--muted);font-size:12px;margin-top:24px;line-height:1.6}
 @media(max-width:880px){.charts{grid-template-columns:1fr}.charts .full{grid-column:auto}}
</style></head><body>
<header><h1>REopt Buildout-Time Optimization</h1><div class="sub" id="subline"></div></header>
<div class="wrap">
 <div class="grid kpis" id="kpis"></div>
 <div class="grid charts">
  <div class="card"><h3>Lead time of built technologies</h3>
   <p class="hint">System buildout time = MAX over built techs (parallel). Tallest bar sets it.</p>
   <div class="chartbox"><canvas id="buildoutChart"></canvas></div></div>
  <div class="card"><h3>Objective weighting</h3><p class="hint" id="weightHint"></p>
   <div class="chartbox"><canvas id="mixChart"></canvas></div></div>
  <div class="card"><h3>Annual utility bill: BAU vs optimized</h3><p class="hint">Year-one energy + demand charges.</p>
   <div class="chartbox"><canvas id="billChart"></canvas></div></div>
  <div class="card"><h3>25-year lifecycle cost</h3><p class="hint">Discounted cost incl. monetized CO2; gap = NPV.</p>
   <div class="chartbox"><canvas id="lccChart"></canvas></div></div>
  <div class="card"><h3>Electricity to load by source</h3><p class="hint">Annual energy delivered to the building.</p>
   <div class="chartbox"><canvas id="sourceChart"></canvas></div></div>
  <div class="card"><h3>Annual CO&#8322; emissions</h3><p class="hint">Tonnes CO&#8322;/yr (German grid intensity).</p>
   <div class="chartbox"><canvas id="co2Chart"></canvas></div></div>
  <div class="card full"><h3>Hourly dispatch &mdash; peak-load week</h3><p class="hint" id="dispatchHint"></p>
   <div class="chartbox tall"><canvas id="dispatchChart"></canvas></div></div>
 </div>
 <div class="foot" id="foot"></div>
</div>
<script>
const D=__DATA__;const W=D.kpis.weights;
const f0=n=>(n==null?"--":Math.round(n).toLocaleString());
const fUSDk=n=>(n==null?"--":"\u20ac"+(n/1000).toFixed(0)+"k");
const fUSDm=n=>(n==null?"--":"\u20ac"+(n/1e6).toFixed(2)+"M");
const fPct=n=>(n==null?"--":(n*100).toFixed(0)+"%");
const days=y=>Math.round((y||0)*365);
const norm=x=>(!x||(x<0&&x>-1)?0:x);
document.getElementById("subline").innerHTML=
 `${D.kpis.city} &nbsp;|&nbsp; status <b>${D.status}</b> &nbsp;|&nbsp; grid ${D.kpis.grid} / chp ${D.kpis.chp} `+
 `&nbsp;|&nbsp; weights time/cost/CO2 = ${(W.time*100)|0}/${(W.cost*100)|0}/${(W.co2*100)|0}`;
const co2cut=(D.kpis.co2_bau)?1-(D.kpis.co2/D.kpis.co2_bau):null;
const s=D.kpis.sizes;
const cards=[
 {hero:1,label:"System buildout time",val:(D.kpis.buildout_years||0),unit:"yr ("+days(D.kpis.buildout_years)+" d)",delta:"MAX over built techs"},
 {label:"PV",val:f0(norm(s.PV)),unit:"kW",delta:s.PV>1?"built":"not selected"},
 {label:"Wind",val:f0(norm(s.Wind)),unit:"kW",delta:s.Wind>1?"built":"not selected"},
 {label:"Battery",val:f0(norm(s.ElectricStorage)),unit:"kWh",delta:s.ElectricStorage>1?"built":"not selected"},
 {label:"Generator / CHP",val:f0(norm(s.Generator))+" / "+f0(norm(s.CHP)),unit:"kW",delta:""},
 {label:"Net Present Value",val:fUSDm(D.kpis.npv),unit:"",delta:"<span class='pos'>vs BAU</span>"},
 {label:"Renewable share",val:fPct(D.kpis.renew_frac),unit:"of load",delta:""},
 {label:"CO\u2082 vs BAU",val:co2cut==null?"--":fPct(Math.abs(co2cut)),unit:(co2cut==null?"":(co2cut>=0?"lower":"higher")),
  delta:D.kpis.co2_bau?(((D.kpis.co2_bau-D.kpis.co2)>=0?"-":"+")+Math.abs(D.kpis.co2_bau-D.kpis.co2).toFixed(0)+" t/yr"):""},
];
document.getElementById("kpis").innerHTML=cards.map(k=>`<div class="card kpi ${k.hero?'hero':''}">
 <div class="label">${k.label}</div><div class="val">${k.val} <span class="unit">${k.unit}</span></div>
 <div class="delta">${k.delta}</div></div>`).join("");
Chart.defaults.color="#93a4bd";Chart.defaults.borderColor="#2b3650";
Chart.defaults.font.family=getComputedStyle(document.body).fontFamily;

const bo=D.buildout_bars;const blabels=Object.keys(bo);
const maxv=Math.max(0,...Object.values(bo));
new Chart(buildoutChart,{type:"bar",data:{labels:blabels,
 datasets:[{data:blabels.map(k=>bo[k]),backgroundColor:blabels.map(k=>bo[k]>=maxv-1e-9?"#a78bfa":"#5b7290")}]},
 options:{indexAxis:"y",responsive:true,maintainAspectRatio:false,scales:{x:{title:{display:true,text:"years"}}},
  plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.raw+" yr ("+Math.round(c.raw*365)+" d)"}}}}});

document.getElementById("weightHint").textContent=
 "Time \u20ac"+(D.kpis.buildout_cost_per_year/1e6).toFixed(2)+"M/yr; CO2 \u20ac"+D.kpis.co2_price+"/t.";
new Chart(mixChart,{type:"doughnut",data:{labels:["Time","Cost","CO2"],
 datasets:[{data:[W.time,W.cost,W.co2],backgroundColor:["#a78bfa","#3ea6ff","#36d399"]}]},
 options:{responsive:true,maintainAspectRatio:false,plugins:{tooltip:{callbacks:{label:c=>c.label+": "+(c.raw*100|0)+"%"}}}}});

new Chart(billChart,{type:"bar",data:{labels:["BAU","Optimized"],
 datasets:[{label:"Energy",data:[D.cost_breakdown.bau.energy,D.cost_breakdown.opt.energy],backgroundColor:"#3ea6ff"},
  {label:"Demand",data:[D.cost_breakdown.bau.demand,D.cost_breakdown.opt.demand],backgroundColor:"#a78bfa"}]},
 options:{responsive:true,maintainAspectRatio:false,scales:{x:{stacked:true},y:{stacked:true,ticks:{callback:v=>"\u20ac"+(v/1000)+"k"}}},
  plugins:{tooltip:{callbacks:{label:c=>c.dataset.label+": \u20ac"+Math.round(c.raw).toLocaleString()}}}}});

new Chart(lccChart,{type:"bar",data:{labels:["BAU","Optimized"],
 datasets:[{data:[D.kpis.lcc_bau,D.kpis.lcc],backgroundColor:["#5b7290","#36d399"]}]},
 options:{responsive:true,maintainAspectRatio:false,scales:{y:{ticks:{callback:v=>"\u20ac"+(v/1e6).toFixed(0)+"M"}}},
  plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>"\u20ac"+Math.round(c.raw).toLocaleString()}}}}});

const es=D.energy_split;const el=Object.keys(es);
new Chart(sourceChart,{type:"doughnut",data:{labels:el,
 datasets:[{data:el.map(k=>es[k]),backgroundColor:["#fbbd23","#36d399","#f87272","#a78bfa","#3ea6ff","#5b7290"]}]},
 options:{responsive:true,maintainAspectRatio:false,plugins:{tooltip:{callbacks:{label:c=>c.label+": "+f0(c.raw)+" kWh"}}}}});

new Chart(co2Chart,{type:"bar",data:{labels:["BAU","Optimized"],
 datasets:[{data:[D.kpis.co2_bau,D.kpis.co2],backgroundColor:["#f87272","#36d399"]}]},
 options:{responsive:true,maintainAspectRatio:false,scales:{y:{title:{display:true,text:"t CO2 / yr"}}},
  plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>(c.raw||0).toFixed(0)+" t/yr"}}}}});

document.getElementById("dispatchHint").textContent="Supply to load during the peak week ("+D.dispatch.peak_label+").";
const step=Math.max(1,Math.floor(D.dispatch.labels.length/56));
new Chart(dispatchChart,{type:"line",data:{labels:D.dispatch.labels,
 datasets:[
  {label:"Grid",data:D.dispatch.grid,backgroundColor:"rgba(91,114,144,.7)",borderColor:"#5b7290",fill:true,stack:"s",pointRadius:0,borderWidth:1},
  {label:"Solar",data:D.dispatch.pv,backgroundColor:"rgba(251,189,35,.75)",borderColor:"#fbbd23",fill:true,stack:"s",pointRadius:0,borderWidth:1},
  {label:"Wind",data:D.dispatch.wind,backgroundColor:"rgba(54,211,153,.6)",borderColor:"#36d399",fill:true,stack:"s",pointRadius:0,borderWidth:1},
  {label:"Total load",data:D.dispatch.load,borderColor:"#e6edf6",borderWidth:2,fill:false,pointRadius:0,borderDash:[4,2]}]},
 options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},
  scales:{x:{ticks:{maxTicksLimit:14,callback:function(v,i){return i%step===0?this.getLabelForValue(v):"";}}},
   y:{stacked:true,title:{display:true,text:"kW"}}}}});

document.getElementById("foot").innerHTML=
 `<b>Run:</b> ${D.kpis.city}, weights time ${(W.time*100)|0}% / cost ${(W.cost*100)|0}% / CO\u2082 ${(W.co2*100)|0}%, `+
 `grid ${D.kpis.grid}, chp ${D.kpis.chp}. Built: <b>${D.kpis.built.join(", ")||"none"}</b>. `+
 `System buildout time <b>${D.kpis.buildout_years||0} yr</b>. Solved with labmate's buildout-time REopt fork (HiGHS).`;
</script></body></html>
"""

d = json.load(open(OUTDIR / "results.json"))
wm = json.load(open(OUTDIR / "weight_mapping.json"))


def g(sec, key, default=0.0):
    v = d.get(sec, {}).get(key, default)
    return v if v is not None else default


def series(sec, key, n):
    v = d.get(sec, {}).get(key)
    return v if isinstance(v, list) else [0.0] * n


fin, site, load = d.get("Financial", {}), d.get("Site", {}), d.get("ElectricLoad", {})
et = d.get("ElectricTariff", {})
load_series = load.get("load_series_kw", []) or []
n = len(load_series)
lcc, lcc_bau = fin.get("lcc", 0.0), fin.get("lcc_bau", 0.0) or 0.0

TECHS = ["PV", "Wind", "Generator", "CHP", "ElectricStorage"]
sizes = {t: (g(t, "size_kwh") if t == "ElectricStorage" else g(t, "size_kw")) for t in TECHS}
built = {t: s for t, s in sizes.items() if s and s > 1e-3}

# lead time (years) per built tech -> buildout panel
lead = wm.get("buildout_time_years", {})
buildout_bars = {t: lead.get(t, 0) for t in built}

kpis = {
    "sizes": sizes, "built": list(built.keys()),
    "buildout_years": g("Site", "system_buildout_time_years"),
    "lcc": lcc, "lcc_bau": lcc_bau, "npv": (lcc_bau - lcc) if lcc_bau else None,
    "capex_net": fin.get("initial_capital_costs_after_incentives"),
    "co2": site.get("annual_emissions_tonnes_CO2"),
    "co2_bau": site.get("annual_emissions_tonnes_CO2_bau"),
    "renew_frac": site.get("onsite_renewable_electricity_fraction_of_elec_load"),
    "grid_kwh": g("ElectricUtility", "annual_energy_supplied_kwh"),
    "weights": wm["weights"], "city": wm.get("city"), "grid": wm.get("grid"), "chp": wm.get("chp"),
    "buildout_cost_per_year": wm["buildout_time_cost_per_year_eur"], "co2_price": wm["CO2_cost_per_tonne_eur"],
}

cost_breakdown = {
    "opt": {"energy": et.get("year_one_energy_cost_before_tax", 0.0),
            "demand": et.get("year_one_demand_cost_before_tax", 0.0)},
    "bau": {"energy": et.get("year_one_energy_cost_before_tax_bau", 0.0),
            "demand": et.get("year_one_demand_cost_before_tax_bau", 0.0)},
}

src_keys = {"PV": ("PV", "electric_to_load_series_kw"), "Wind": ("Wind", "electric_to_load_series_kw"),
            "Generator": ("Generator", "electric_to_load_series_kw"), "CHP": ("CHP", "electric_to_load_series_kw"),
            "Battery": ("ElectricStorage", "storage_to_load_series_kw"),
            "Grid": ("ElectricUtility", "electric_to_load_series_kw")}
energy_split = {label: sum(series(sec, key, n)) for label, (sec, key) in src_keys.items()}
energy_split = {k: v for k, v in energy_split.items() if v > 1}

# dispatch peak week
pv_l = series("PV", "electric_to_load_series_kw", n)
gr_l = series("ElectricUtility", "electric_to_load_series_kw", n)
wd_l = series("Wind", "electric_to_load_series_kw", n)
peak = max(range(n), key=lambda i: load_series[i]) if n else 0
week = 168
start = max(0, min(peak - week // 2, max(0, n - week)))
end = min(n, start + week)
base = datetime(2017, 1, 1)
dispatch = {
    "labels": [(base + timedelta(hours=i)).strftime("%a %H:%M") for i in range(start, end)],
    "load": load_series[start:end], "pv": pv_l[start:end], "wind": wd_l[start:end], "grid": gr_l[start:end],
    "peak_label": (base + timedelta(hours=peak)).strftime("%A %b %d, %H:%M"),
}

payload = {"kpis": kpis, "cost_breakdown": cost_breakdown, "energy_split": energy_split,
           "buildout_bars": buildout_bars, "dispatch": dispatch,
           "status": d.get("status"), "solver_seconds": d.get("solver_seconds")}

html = HTML_TEMPLATE.replace("__DATA__", json.dumps(payload))
open(OUTDIR / "dashboard.html", "w").write(html)
print(f"Wrote {OUTDIR / 'dashboard.html'}")
