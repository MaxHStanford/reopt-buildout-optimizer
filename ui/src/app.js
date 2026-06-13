// App controller: three screens (inputs → map → detail), simple state, no framework.

import { rankCities, annualDispatch, normalizeWeights, CONST } from "./model.js";
import { eur, kw, num, pct, years, tonnes } from "./format.js";
import { initMap, renderCities, invalidate } from "./map.js";
import { renderDispatch, renderMix, PALETTE } from "./charts.js";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

// A baseload (flat, 24/7) profile of P gigawatts delivers P·10^6 kW over 8760 h.
const HOURS_PER_YEAR = 8760;
const gwToKwhYr = (gw) => gw * 1e6 * HOURS_PER_YEAR;

const energyReadout = (kwh) => {
  if (kwh >= 1e9) return num(kwh / 1e9, 2) + " TWh/yr";
  if (kwh >= 1e6) return num(kwh / 1e6, 1) + " GWh/yr";
  return num(kwh) + " kWh/yr";
};

const state = {
  data: null,
  weights: { time: 34, cost: 33, emit: 33 },
  loadGw: 1,
  loadKwh: gwToKwhYr(1),
  result: null,
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
  // mini stacked bar
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
    const gw = +e.target.value;
    $("#load-readout").textContent = gw ? `${num(gw, 3)} GW baseload · ${energyReadout(gwToKwhYr(gw))}` : "—";
  });
  $("#optimize-form").addEventListener("submit", (e) => {
    e.preventDefault();
    runOptimization();
  });
  paintWeightShares();
  $("#load-readout").textContent =
    `${num(state.loadGw, 3)} GW baseload · ${energyReadout(state.loadKwh)}`;
}

// ---- run / map ------------------------------------------------------------
function runOptimization() {
  state.weights = readWeights();
  state.loadGw = Math.max(0.001, +$("#load-input").value || state.loadGw);
  state.loadKwh = gwToKwhYr(state.loadGw);
  state.result = rankCities(state.loadKwh, state.weights, state.data);

  const best = state.result.best;
  const w = state.result.weights;
  $("#map-summary").innerHTML =
    `Weighting <b>time ${pct(w.time)}</b> · <b>cost ${pct(w.cost)}</b> · <b>emissions ${pct(w.emit)}</b>` +
    ` &nbsp;for&nbsp; <b>${num(state.loadGw, 3)} GW baseload</b> (${energyReadout(state.loadKwh)}) off-grid load.`;

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

  // annual load + dispatch chart
  renderDispatch($("#dispatchChart"), annualDispatch(ev));
  renderMix($("#mixChart"), ev);

  // system composition
  const s = ev.sizes;
  $("#sizes").innerHTML =
    statRow(`<span class="dot" style="background:${PALETTE.pv}"></span>Solar PV`, kw(s.pvKw) + " kW") +
    statRow(`<span class="dot" style="background:${PALETTE.wind}"></span>Wind`, kw(s.windKw) + " kW") +
    statRow(`<span class="dot" style="background:${PALETTE.battery}"></span>Battery`, kw(s.battKwh) + " kWh") +
    statRow(`<span class="dot" style="background:${PALETTE.generator}"></span>Generator`, kw(s.genKw) + " kW");

  // statistics
  $("#stats").innerHTML =
    statRow("Renewable share of load", pct(renewFrac)) +
    statRow("Wind / solar split", pct(ev.windShare) + " / " + pct(1 - ev.windShare)) +
    statRow("Resource quality", num(ev.q * 100) + " / 100", `solar CF ${num(ev.sCF * 100, 1)}% · wind CF ${num(ev.wCF * 100, 1)}%`) +
    statRow("Annual load", num(ev.energy.L) + " kWh") +
    statRow("Generator energy", num(ev.energy.genKwh) + " kWh/yr") +
    statRow("Net capital cost", eur(ev.capex)) +
    statRow("Annual O&M + fuel", eur(ev.omPerYear + ev.fuelPerYear) + "/yr") +
    statRow("Land use", num(ev.landAcres, 1) + " acres");

  show("detail");
}

// ---- boot -----------------------------------------------------------------
async function boot() {
  bindInputs();
  initMap("map");
  $$("[data-nav]").forEach((b) => b.addEventListener("click", () => show(b.dataset.nav)));
  try {
    state.data = await (await fetch("./data/germany.json")).json();
    $("#city-count").textContent = state.data.cities.length;
  } catch (err) {
    $("#boot-error").textContent =
      "Could not load data/germany.json — serve this folder over http (see README).";
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
    const gw = +$("#load-input").value;
    $("#load-readout").textContent = `${num(gw, 3)} GW baseload · ${energyReadout(gwToKwhYr(gw))}`;
  }
  if (q.get("go") === "1") {
    runOptimization();
    if (q.get("view") === "detail" && state.result) openDetail(state.result.best);
  }
}

boot();
