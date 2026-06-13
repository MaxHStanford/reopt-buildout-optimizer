# Off-Grid Buildout Optimizer — UI

A lightweight web UI for the buildout-time optimizer. You set how much you care about
**time-to-energy**, **lifecycle cost**, and **emissions**, enter the annual load, and it
surfaces the best German location for an **off-grid** energy system, then drills into the
chosen system's parameters and yearly load/supply curve.

## Run

It uses native ES modules and `fetch`, so it must be served over HTTP (opening the file
directly will fail on CORS). From this folder:

```bash
python -m http.server 8080
# then open http://localhost:8080/
```

## Flow

1. **Inputs** — three priority sliders (auto-normalised to 100 %) + annual load, with presets.
2. **Map** — the 20 candidate cities on a map of Germany; the optimal one is highlighted.
   Click it to open details.
3. **Detail** — headline **Time / Cost / Emissions** KPIs, the year-long load-and-supply
   curve, the energy mix, system composition, and statistics.

## How the "optimal" location is chosen (demo heuristic)

This is **not** a full MILP solve. For each city we evaluate two off-grid archetypes —
a *renewables + gas-backup hybrid* and a *fully-renewable + battery* system — using real
per-city wind capacity factors (`../optimizer/data/wind_production_factors.json`) and a
latitude-based solar proxy. Each candidate gets a buildout time (max tech lead time),
lifecycle cost, and CO₂; these are normalised and combined with your weights, and the
lowest-objective city wins. Swapping in real REopt results later means replacing
`rankCities`/`evaluateDesign` in `src/model.js` — the UI is otherwise unchanged.

The model is intentionally simple but coherent: heavy **time** weight favours a sunny
southern PV-only build (2 yr), heavy **cost** favours a windy site with a cheap gas backup
(4 yr, emits), and heavy **emissions** favours a fully-renewable windy site (0 t CO₂).

## Files

```
index.html        screens + layout
styles.css        theme (light, no purple)
data/germany.json compact per-city resource data (generated from optimizer/data)
src/
  model.js        off-grid scoring + ranking + synthetic annual dispatch
  map.js          Leaflet map + markers
  charts.js       Chart.js wrappers
  format.js       number/unit formatters
  app.js          state + screen routing
```
