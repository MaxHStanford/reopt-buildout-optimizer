# Off-Grid Buildout Optimizer — UI

A web UI for the buildout-time optimizer. You set how much you care about
**time-to-energy**, **lifecycle cost**, and **emissions**, enter the load, and the
**genetic-algorithm solver** (European prices) sizes an **off-grid** PV + Wind + Battery + Gas
system for every German city. The map surfaces the best 5 cities plus Munich; clicking a
city drills into its KPIs, energy mix, and an interactive, week-selectable load/supply curve.

## Run

The UI calls a small Flask backend that runs the GA, so start the server (not a plain
static file server):

```bash
pip install flask          # one-time (numba is also required by the GA)
python server.py           # serves the UI + GA at http://localhost:8080
# then open http://localhost:8080/
```

The first request triggers a one-off numba JIT compile (warmed at boot); subsequent solves
take a few seconds for all 20 cities.

## Flow

1. **Inputs** — three priority sliders (auto-normalised to 100 %) + load in MW, with presets.
2. **Map** — the GA's best 5 cities + Munich are highlighted on a map of Germany (rank #1 in
   accent with an area halo, the rest in teal); the other cities are muted. Click any
   highlighted city to open its details.
3. **Detail** — headline **Time / Cost / Emissions** KPIs, an interactive **week-selectable**
   hourly load-and-supply curve (jump to the most-stressed week), the energy mix, system
   composition, and statistics.

## How locations are ranked (GA)

On submit, the UI POSTs `{time, cost, emit, load_kw}` to `/api/optimize`. The backend
([server.py](server.py)) runs the genetic algorithm in
[`../optimizer/ga/ga_solver.py`](../optimizer/ga/ga_solver.py) for all 20 cities, scoring
each off-grid design by a weighted sum of normalised cost, CO₂, and buildout time over real
per-city PV and wind production factors (`../optimizer/data/`). It returns the 5
lowest-objective cities plus Munich, each with its full 8760-h dispatch for the week selector.

### Load scaling ("cheat")

The GA is numerically tuned around a ~1 MW system. The UI therefore shows the load in **MW**
but the backend solves at **load / 100**, then multiplies every extensive output (capacities,
energy, dispatch series, cost, CO₂) back by 100. Because the rule-based dispatch is linear in
load and capacity, the reported numbers describe the true full-scale system while the solver
stays in its tuned regime (and the per-acre area caps don't bind).

## Files

```
server.py         Flask backend: serves the UI + runs the GA (/api/optimize)
index.html        screens + layout
styles.css        theme
data/germany.json compact per-city resource data (map context + city count)
src/
  model.js        normalizeWeights + constants (legacy JS heuristic kept for reference)
  map.js          Leaflet map + markers (best 5 + Munich)
  charts.js       Chart.js wrappers (week dispatch + energy mix)
  format.js       number/unit formatters
  app.js          state + screen routing + backend calls
```
