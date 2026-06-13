// App controller: three screens (inputs -> map -> detail), simple state, no framework.
// The ranking now comes from the Python GA backend (POST /api/optimize); the JS
// heuristic in model.js is retained only for normalizeWeights/CONST.

import { normalizeWeights, CONST } from "./model.js";
import { eur, kw, num, pct, years, tonnes } from "./format.js";
import { initMap, renderCities, invalidate } from "./map.js";
import { renderWeek, setWeek, renderMix, PALETTE } from "./charts.js";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

// UI shows MW; a flat baseload of P MW delivers P*1000 kW over 8760 h.
const HOURS_PER_YEAR = 8760;
const mwToKwhYr = (mw) => mw * 1e3 * HOURS_PER_YEAR;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const energyReadout = (kwh) => {
  if (kwh >= 1e9) return num(kwh / 1e9, 2) + " TWh/yr";
  if (kwh >= 1e6) return num(kwh / 1e6, 1) + " GWh/yr";
  return num(kwh) + " kWh/yr";
};

const state = {
  data: null,
  weights: { time: 34, cost: 33, emit: 33 },
  loadMw: 100,
  loadKwh: mwToKwhYr(100),
  result: null,
  stressWeek: 0,
  nweeks: 0,
};

// ---- screen routing -------------------------------------------------------
function show(screen) {
  $$(".screen").forEach((s) => s.classList.toggle("active", s.id === `screen-${screen}`));
  if (screen === "map") invalidate();
  window.scrollTo({ top: 0, behavior: "instant" });
}

// ---- inputs ---------------------------------------------------------------
function readWeights() {
  return {
    time: +$("#w-time").value,
    cost: +$("#w-cost").value,
    emit: +$("#w-emit").value,
  };
}

function paintWeightShares() {
  const n = normalizeWeights(readWeights());
  $("#share-time").textContent = pct(n.time);
  $("#share-cost").textContent = pct(n.cost);
  $("#share-emit").textContent = pct(n.emit);
  $("#wbar-time").style.width = n.time * 100 + "%";
  $("#wbar-cost").style.width = n.cost * 100 + "%";
  $("#wbar-emit").style.width = n.emit * 100 + "%";
}

function bindInputs() {
  ["w-time", "w-cost", "w-emit"].forEach((id) =>
    $("#" + id).addEventListener("input", paintWeightShares)
  );
  $$(".preset").forEach((btn) =>
    btn.addEventListener("click", () => {
      const [t, c, e] = btn.dataset.w.split(",").map(Number);
      $("#w-time").value = t; $("#w-cost").value = c; $("#w-emit").value = e;
      paintWeightShares();
    })
  );
  $("#load-input").addEventListener("input", (e) => {
    const mw = +e.target.value;
    $("#load-readout").textContent = mw ? `${num(mw, 3)} MW baseload · ${energyReadout(mwToKwhYr(mw))}` : "—";
  });
  $("#optimize-form").addEventListener("submit", (e) => {
    e.preventDefault();
    runOptimization();
  });
  paintWeightShares();
  $("#load-readout").textContent =
    `${num(state.loadMw, 3)} MW baseload · ${energyReadout(state.loadKwh)}`;
}

// ---- run / map ------------------------------------------------------------
async function runOptimization() {
  state.weights = readWeights();
  state.loadMw = Math.max(0.001, +$("#load-input").value || state.loadMw);
  state.loadKwh = mwToKwhYr(state.loadMw);

  const btn = $("#optimize-form button[type=submit]");
  const label = btn ? btn.innerHTML : "";
  if (btn) { btn.disabled = true; btn.innerHTML = "Solving with the GA…"; }

  try {
    const resp = await fetch("/api/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...state.weights, load_kw: state.loadMw * 1000 }),
    });
    if (!resp.ok) throw new Error(`server ${resp.status}`);
    const data = await resp.json();
    state.result = {
      evals: data.evals, best: data.evals[0],
      weights: data.weights, allCoords: data.allCoords,
    };
    state.stressWeek = data.stressWeek || 0;
    state.nweeks = data.nweeks || 0;
  } catch (err) {
    $("#boot-error").textContent =
      "Optimization failed — is the GA backend running? Start it with `python server.py`.";
    $("#boot-error").hidden = false;
    return;
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = label; }
  }

  const best = state.result.best;
  const w = state.result.weights;
  $("#map-summary").innerHTML =
    `Weighting <b>time ${pct(w.time)}</b> · <b>cost ${pct(w.cost)}</b> · <b>emissions ${pct(w.emit)}</b>` +
    ` &nbsp;for&nbsp; <b>${num(state.loadMw, 3)} MW baseload</b> (${energyReadout(state.loadKwh)}) off-grid load.` +
    ` GA picks the best 5 cities + Munich.`;

  const yy = years(best.buildoutYears);
  $("#opt-card").innerHTML = `
    <div class="opt-rank">Optimal area · approximate</div>
    <div class="opt-name">${best.city.name}<span class="opt-approx"> &amp; surroundings</span></div>
    <div class="opt-metrics">
      <div><span class="dot" style="background:${PALETTE.time}"></span>${yy.value} yr <small>buildout</small></div>
      <div><span class="dot" style="background:${PALETTE.cost}"></span>${eur(best.lcc)} <small>lifecycle</small></div>
      <div><span class="dot" style="background:${PALETTE.emit}"></span>${tonnes(best.co2Tonnes)} t <small>CO₂/yr</small></div>
    </div>
    <button class="btn btn-primary" id="opt-detail-btn">View system details →</button>`;
  $("#opt-detail-btn").addEventListener("click", () => openDetail(best));

  show("map");
  renderCities(state.result, openDetail);
}

// ---- detail ---------------------------------------------------------------
function kpiCard(accent, label, big, unit, sub) {
  return `<div class="kpi" style="--accent:${accent}">
    <div class="kpi-label">${label}</div>
    <div class="kpi-val">${big}<span class="kpi-unit">${unit}</span></div>
    <div class="kpi-sub">${sub}</div></div>`;
}

function statRow(label, value, hint = "") {
  return `<div class="stat"><span class="stat-label">${label}</span>
    <span class="stat-val">${value}</span>${hint ? `<span class="stat-hint">${hint}</span>` : ""}</div>`;
}

function populateWeekSelector(stressWeek) {
  const sel = $("#week-sel");
  if (!sel) return;
  sel.innerHTML = "";
  for (let w = 0; w < state.nweeks; w++) {
    const o = document.createElement("option");
    o.value = w;
    const month = MONTHS[Math.min(11, Math.floor(w / 4.345))];
    o.textContent = `Week ${w + 1} (${month})` + (w === stressWeek ? " — most stressed" : "");
    sel.appendChild(o);
  }
  sel.value = stressWeek;
}

function openDetail(ev) {
  const yy = years(ev.buildoutYears);
  const renewFrac = ev.energy.renewKwh / ev.energy.L;

  $("#detail-title").textContent = ev.city.name;
  $("#detail-sub").innerHTML =
    `Off-grid · <b>${ev.design}</b> · rank #${ev.rank} of ${state.result.evals.length} · built: <b>${ev.built.join(", ") || "—"}</b>`;

  $("#kpis").innerHTML =
    kpiCard(PALETTE.time, "Time to energy", yy.value, " yr", `${yy.days} days · max lead of built techs`) +
    kpiCard(PALETTE.cost, "Lifecycle cost", eur(ev.lcc), "", `${CONST.YEARS}-yr · capex ${eur(ev.capex)}`) +
    kpiCard(PALETTE.emit, "Emissions", tonnes(ev.co2Tonnes), " t/yr", `gas generator only · ${pct(renewFrac)} renewable`);

  // interactive per-week dispatch
  populateWeekSelector(state.stressWeek);
  renderWeek($("#dispatchChart"), ev, state.stressWeek);
  renderMix($("#mixChart"), ev);

  // system composition
  const s = ev.sizes;
  $("#sizes").innerHTML =
    statRow(`<span class="dot" style="background:${PALETTE.pv}"></span>Solar PV`, kw(s.pvKw) + " kW") +
    statRow(`<span class="dot" style="background:${PALETTE.wind}"></span>Wind`, kw(s.windKw) + " kW") +
    statRow(`<span class="dot" style="background:${PALETTE.battery}"></span>Battery`, kw(s.battKwh) + " kWh") +
    statRow(`<span class="dot" style="background:${PALETTE.gas}"></span>Generator`, kw(s.genKw) + " kW");

  // statistics
  $("#stats").innerHTML =
    statRow("Renewable share of load", pct(renewFrac)) +
    statRow("Load met (served)", pct(ev.served)) +
    statRow("Wind / solar split", pct(ev.windShare) + " / " + pct(1 - ev.windShare)) +
    statRow("Solar / wind capacity factor", `${num(ev.sCF * 100, 1)}% / ${num(ev.wCF * 100, 1)}%`) +
    statRow("Annual load", num(ev.energy.L) + " kWh") +
    statRow("Generator energy", num(ev.energy.genKwh) + " kWh/yr") +
    statRow("Net capital cost", eur(ev.capex)) +
    statRow("Lifecycle cost", eur(ev.lcc));

  show("detail");
}

// ---- boot -----------------------------------------------------------------
async function boot() {
  bindInputs();
  initMap("map");
  $$("[data-nav]").forEach((b) => b.addEventListener("click", () => show(b.dataset.nav)));

  const sel = $("#week-sel");
  if (sel) sel.addEventListener("change", () => setWeek(+sel.value));
  const stressBtn = $("#week-stress");
  if (stressBtn) stressBtn.addEventListener("click", () => {
    if (sel) sel.value = state.stressWeek;
    setWeek(state.stressWeek);
  });

  try {
    state.data = await (await fetch("./data/germany.json")).json();
    $("#city-count").textContent = state.data.cities.length;
  } catch (err) {
    $("#boot-error").textContent =
      "Could not load data/germany.json — serve this folder via `python server.py` (see README).";
    $("#boot-error").hidden = false;
    return;
  }

  // Optional deep-link: ?time=&cost=&emit=&load=&go=1 prefills inputs (and auto-runs).
  const q = new URLSearchParams(location.search);
  const setIf = (param, id) => { if (q.has(param)) $(id).value = q.get(param); };
  setIf("time", "#w-time"); setIf("cost", "#w-cost"); setIf("emit", "#w-emit");
  setIf("load", "#load-input");
  paintWeightShares();
  {
    const mw = +$("#load-input").value;
    $("#load-readout").textContent = `${num(mw, 3)} MW baseload · ${energyReadout(mwToKwhYr(mw))}`;
  }
  if (q.get("go") === "1") {
    await runOptimization();
    if (q.get("view") === "detail" && state.result) openDetail(state.result.best);
  }
}

boot();
