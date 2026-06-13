// Off-grid buildout-time "cheat" model.
//
// The real tool solves a MILP per scenario. For the demo we instead score every
// candidate German city with a transparent, deterministic techno-economic model and
// pick the one that minimises the weighted objective. Every displayed number (time,
// cost, emissions, sizes, load curve) comes from this same model, so the detail page
// is internally consistent with the location that was chosen.
//
// Off-grid: load is met entirely on site from PV + Wind + Battery + Generator.
// The only emissions come from the gas generator's fuel burn.

export const CONST = {
  PV_CAPEX: 1400, PV_OM: 16, // EUR/kW, EUR/kW-yr
  WIND_CAPEX: 1600, WIND_OM: 40,
  BATT_CAPEX: 350, BATT_OM: 8, // EUR/kWh
  GEN_CAPEX: 800, GEN_OM: 15, // EUR/kW
  GEN_FUEL_EUR_PER_KWH: 0.12, // gas fuel cost per kWh electric
  DISCOUNT: 0.08, YEARS: 25,
  PEAK_FACTOR: 1.6, // peak load / mean load for the generator sizing
  PV_ACRE_PER_KW: 0.006, WIND_ACRE_PER_KW: 0.03,
};

const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const presentWorthFactor = (d, n) => (1 - Math.pow(1 + d, -n)) / d;
export const PWF = presentWorthFactor(CONST.DISCOUNT, CONST.YEARS);

// Solar capacity factor proxy: southern (lower-latitude) German sites are sunnier.
export function solarCF(lat) {
  return clamp(0.130 - (lat - 48) * 0.005, 0.092, 0.132);
}

export function normalizeWeights(w) {
  let t = Math.max(0, w.time), c = Math.max(0, w.cost), e = Math.max(0, w.emit);
  let s = t + c + e;
  if (s <= 0) { t = c = e = 1; s = 3; }
  return { time: t / s, cost: c / s, emit: e / s };
}

// Evaluate one design for a city. `withGenerator` chooses between two archetypes the
// real MILP would weigh against each other:
//   • hybrid    — renewables + a gas generator backup: cheaper, but the generator's
//                 4-yr lead dominates buildout and it burns fuel (emissions).
//   • renewable — PV/wind + a large battery, no generator: pricier and needs overbuild,
//                 but buildout is 2–3 yr and emissions are zero.
export function evaluateDesign(city, L, w, data, withGenerator) {
  const sCF = solarCF(city.lat);
  const wCF = city.windCF;
  // Resource quality 0..1: how easily this site can run on renewables.
  const q = Math.min(1, 0.5 * clamp(sCF / 0.13, 0, 1.2) + 0.5 * clamp(wCF / 0.48, 0, 1.2));

  // Split renewables between wind and PV. Wind wins when it is strong and emissions/cost
  // matter; time weight favours fast-to-build PV. A small wind share is dropped because it
  // is not worth the extra year of buildout that wind adds.
  const windAttr = (wCF / 0.30) * (0.6 + w.emit + 0.5 * w.cost) * (1 - 0.95 * w.time);
  const solarAttr = (sCF / 0.11) * (0.6 + 0.4 * w.cost) * (1 + 1.4 * w.time);
  let windShare = clamp(windAttr / (windAttr + solarAttr), 0, 1);
  if (windShare < 0.15) windShare = 0;
  if (windShare > 0.92) windShare = 1;

  const dailyLoad = L / 365;
  let rf, genKwh, overbuild, battKwh, genKw;
  if (withGenerator) {
    rf = clamp((0.55 + 0.15 * w.emit) * (0.8 + 0.2 * q), 0.45, 0.9);
    genKwh = (1 - rf) * L;
    overbuild = 1 + 0.4 * rf;
    battKwh = dailyLoad * (0.3 + 0.5 * rf);
    genKw = (L / 8760) * CONST.PEAK_FACTOR;
  } else {
    rf = 1.0;
    genKwh = 0;
    overbuild = 1.6 - 0.4 * q; // full autonomy needs more overbuild, worse for poor resource
    battKwh = dailyLoad * (1.0 + 1.2 * (1 - q));
    genKw = 0;
  }

  const renewKwh = rf * L;
  const pvKwh = (1 - windShare) * renewKwh;
  const windKwh = windShare * renewKwh;
  const pvKw = pvKwh > 0 ? (pvKwh * overbuild) / (sCF * 8760) : 0;
  const windKw = windKwh > 0 ? (windKwh * overbuild) / (wCF * 8760) : 0;

  // Buildout time = MAX lead among the technologies actually built (parallel deployment).
  const lead = data.leadTimesDays;
  const builtLeads = [];
  if (pvKw > 1) builtLeads.push(lead.PV);
  if (windKw > 1) builtLeads.push(lead.Wind);
  if (battKwh > 1) builtLeads.push(lead.ElectricStorage);
  if (genKw > 1) builtLeads.push(lead.Generator);
  const buildoutDays = builtLeads.length ? Math.max(...builtLeads) : 0;
  const buildoutYears = buildoutDays / 365;

  const capex = pvKw * CONST.PV_CAPEX + windKw * CONST.WIND_CAPEX
    + battKwh * CONST.BATT_CAPEX + genKw * CONST.GEN_CAPEX;
  const omPerYear = pvKw * CONST.PV_OM + windKw * CONST.WIND_OM
    + battKwh * CONST.BATT_OM + genKw * CONST.GEN_OM;
  const fuelPerYear = genKwh * CONST.GEN_FUEL_EUR_PER_KWH;
  const lcc = capex + (omPerYear + fuelPerYear) * PWF;

  const co2Tonnes = (genKwh * data.genEmissionKgPerKwh) / 1000;
  const landAcres = pvKw * CONST.PV_ACRE_PER_KW + windKw * CONST.WIND_ACRE_PER_KW;

  const built = [];
  if (pvKw > 1) built.push("PV");
  if (windKw > 1) built.push("Wind");
  if (battKwh > 1) built.push("Battery");
  if (genKw > 1) built.push("Generator");

  return {
    city, sCF, wCF, q, windShare, rfEff: rf, withGenerator,
    design: withGenerator ? "Renewables + gas backup" : "Fully renewable + battery",
    sizes: { pvKw, windKw, battKwh, genKw },
    energy: { L, pvKwh, windKwh, genKwh, renewKwh },
    buildoutYears, buildoutDays,
    capex, omPerYear, fuelPerYear, lcc,
    co2Tonnes, landAcres, built,
  };
}

// Score and rank all cities. For each city both designs (hybrid + fully renewable) are
// evaluated; sub-scores are normalised across all candidates so the weighted objective is
// comparable, then each city keeps its better design. Returns one evaluation per city,
// sorted best-first, with the optimal flag set.
export function rankCities(L, weights, data) {
  const w = normalizeWeights(weights);
  const candidates = [];
  data.cities.forEach((c) => {
    candidates.push(evaluateDesign(c, L, w, data, false));
    candidates.push(evaluateDesign(c, L, w, data, true));
  });

  const range = (key) => {
    const vals = candidates.map((e) => e[key]);
    return [Math.min(...vals), Math.max(...vals)];
  };
  const [tMin, tMax] = range("buildoutYears");
  const [cMin, cMax] = range("lcc");
  const [eMin, eMax] = range("co2Tonnes");
  const nrm = (v, lo, hi) => (hi - lo < 1e-9 ? 0 : (v - lo) / (hi - lo));

  candidates.forEach((e) => {
    e.scores = {
      time: nrm(e.buildoutYears, tMin, tMax),
      cost: nrm(e.lcc, cMin, cMax),
      emit: nrm(e.co2Tonnes, eMin, eMax),
    };
    e.objective = w.time * e.scores.time + w.cost * e.scores.cost + w.emit * e.scores.emit;
  });

  // Keep the better design per city.
  const byCity = new Map();
  candidates.forEach((e) => {
    const cur = byCity.get(e.city.name);
    if (!cur || e.objective < cur.objective) byCity.set(e.city.name, e);
  });

  const evals = [...byCity.values()].sort((a, b) => a.objective - b.objective);
  evals.forEach((e, i) => { e.rank = i + 1; e.optimal = i === 0; });
  return { weights: w, evals, best: evals[0] };
}

// Synthetic daily-mean dispatch over a year for the detail chart. Real shape would come
// from a DOE load profile + the 8760-h resource series; here we generate a believable
// seasonal curve scaled to the chosen system.
export function annualDispatch(ev) {
  const days = 365;
  const meanLoad = ev.energy.L / days;
  const labels = [], load = [], pv = [], wind = [], gen = [];
  const TWO_PI = Math.PI * 2;
  const base = new Date(2023, 0, 1);
  const fmt = (d) => {
    const dt = new Date(base.getTime() + d * 86400000);
    return dt.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
  };
  // Daily-mean availability per installed kW.
  const pvDayKwh = ev.sizes.pvKw * ev.sCF * 24;
  const windDayKwh = ev.sizes.windKw * ev.wCF * 24;
  for (let d = 0; d < days; d++) {
    // Load: mild winter peak, weekend dip.
    const season = 1 + 0.10 * Math.cos((d - 15) / days * TWO_PI);
    const weekday = [d % 7 === 5 || d % 7 === 6 ? 0.88 : 1.0][0];
    const Ld = meanLoad * season * weekday;
    // PV peaks in summer; wind peaks in winter.
    const pvDay = pvDayKwh * (1 + 0.55 * Math.cos((d - 172) / days * TWO_PI));
    const windDay = windDayKwh * (1 + 0.45 * Math.cos((d - 15) / days * TWO_PI));
    const renew = pvDay + windDay;
    const servedRenew = Math.min(Ld, renew);
    const pvToLoad = renew > 0 ? servedRenew * (pvDay / renew) : 0;
    const windToLoad = renew > 0 ? servedRenew * (windDay / renew) : 0;
    const genToLoad = Math.max(0, Ld - servedRenew);
    labels.push(fmt(d));
    load.push(Ld / 1000); // MWh/day
    pv.push(pvToLoad / 1000);
    wind.push(windToLoad / 1000);
    gen.push(genToLoad / 1000);
  }
  // The daily shortfall (load above same-day renewable output) is covered by the gas
  // generator in a hybrid design, or by the battery (stored renewable energy) when the
  // system is fully renewable.
  const hasGen = ev.sizes.genKw > 1;
  return { labels, load, pv, wind, fill: gen, hasGen };
}
