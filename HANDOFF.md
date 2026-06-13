# Energy-AI Hackathon - REopt Buildout-Time Optimization - HANDOFF

This document is a self-contained handoff. It explains the whole setup and how to run the
parameterized optimization via the bash script. Give this file to a fresh chat and it will
have everything needed.

---

## 1. What this is

A locally-running techno-economic optimizer for German energy systems (data-center / commercial
sites) that jointly minimizes **cost + CO2 + deployment time ("time-to-energy")**.

It is built on **REopt** (National Lab of the Rockies). Two pieces:
- **REopt_API** - Django REST API (not strictly needed for the bash workflow, but it's how the
  Docker stack/solver container is created).
- **REopt.jl** - the Julia optimization package (a Mixed-Integer Linear Program solved with HiGHS).

A labmate (`fschweden/energy_ai_hack_DC`) forked REopt.jl to add a **buildout-time** objective.
We integrated that fork with German wind/solar/grid data and a 3-way weighting, and wrapped the
whole thing in one bash script.

Everything runs **locally** in Docker. The only external calls are to `developer.nlr.gov`
(PVWatts) for the solar production factor.

---

## 2. The labmate's fork: how the time dimension works

The fork (`Hackathon/energy_ai_hack_DC/`, a clone of REopt.jl 0.59.2) adds:

- `Settings.buildout_time_cost_per_year` - EUR penalty per year of system buildout time (0 disables).
- Per-tech `buildout_time` (years) on `PV`, `Wind`, `Generator`, `CHP`, `SteamTurbine`, `ElectricStorage`.
- A new constraint `add_buildout_time_constraints!` that introduces `dvSystemBuildoutTime`, forced to be
  the **MAX `buildout_time` over the technologies that are actually built** (parallel deployment), and
  adds `buildout_time_cost_per_year * dvSystemBuildoutTime` to the objective.
- New output `Site.system_buildout_time_years`.

Objective: `min( Costs + ObjectivePenalties )`, where Costs is the usual lifecycle cost (optionally
including monetized CO2), and ObjectivePenalties now includes the buildout-time term.

So it is a single exact MILP solve that trades cost vs CO2 vs time. No genetic algorithm.

---

## 3. How the fork is installed into the running container

The solver runs in the Docker container **`julia_api`**. The container ships the registry REopt
0.59.2 at `/root/.julia/packages/REopt/3aYeS/`. A fresh `Pkg.develop` of the fork fails (a newer
`PROJ_jll` needs `libsqlite3.so.0`, missing in the container). So we **overlay the fork's source**
onto the working install:

```bash
PKG=/root/.julia/packages/REopt/3aYeS
docker exec julia_api sh -c "
  [ -d $PKG/src.orig ] || cp -r $PKG/src $PKG/src.orig    # one-time backup
  cp -r /opt/energy_ai_hack_DC/src/. $PKG/src/            # overlay fork source
"
# (the fork repo was copied in with: docker cp Hackathon/energy_ai_hack_DC julia_api:/opt/energy_ai_hack_DC)
```

Verify it took effect:
```bash
docker exec julia_api sh -c 'grep -c buildout /root/.julia/packages/REopt/3aYeS/src/constraints/tech_constraints.jl'
docker exec -e NREL_DEVELOPER_API_KEY=DUMMY julia_api /usr/local/julia/bin/julia --project=/opt/julia_src \
  -e 'using REopt; println(isdefined(REopt, :add_buildout_time_constraints!))'   # expect true
```
First `using REopt` after an overlay recompiles (~15 s).

If the container is ever rebuilt, re-copy the fork and re-overlay (above). `src.orig` restores stock REopt.

---

## 4. Prerequisites / starting from scratch

```bash
# 1. bring up the stack (Postgres, Redis, Celery, Django, Julia) - first build is slow (~5-10 min)
cd Hackathon/REopt_API
docker-compose up -d            # legacy compose v1 is what's installed here
# wait until healthy:
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/_health    # expect 200
docker ps --format '{{.Names}}: {{.Status}}'   # julia_api must be Up

# 2. ensure the fork is overlaid (section 3)

# 3. keys.py must hold a real NLR/NREL developer key (DEMO_KEY hits a 10 req/hr limit)
grep developer_nrel_gov_key Hackathon/REopt_API/keys.py
# currently set to: gAfosXcQ9Ldfw3qXqvKVb7PxMEkYigozmC9R3mXQ  (shipped in julia_src/.env)
```

The base image `reopt/py312` is on Docker Hub (`docker pull reopt/py312`).

---

## 5. Running the optimization (the bash script)

```bash
cd Hackathon/optimizer
./run_optimization.sh [options]
```

It (1) assembles a scenario JSON from your parameters, (2) stages it into `julia_api`,
(3) solves with the fork (HiGHS), (4) copies results back, (5) builds a dashboard.
Artifacts land in `Hackathon/optimizer/output/` (or `--out DIR`).

### Parameters

| Flag | Meaning | Default |
|---|---|---|
| `--time-weight F` | weight on deployment time | 0.50 |
| `--cost-weight F` | weight on lifecycle cost | 0.35 |
| `--co2-weight F` | weight on CO2 | 0.15 |
| `--city NAME` | location (German city with data) | Munich |
| `--grid on\|off` | grid access (off => off-grid island) | on |
| `--pv on\|off` | allow PV | on |
| `--wind on\|off` | allow wind | on |
| `--battery on\|off` | allow battery | on |
| `--generator on\|off` | grid-parallel gas generator | off |
| `--pv-acres F` | land for PV -> caps PV size (acres / 0.006 = kW) | 50 |
| `--wind-acres F` | land for wind -> caps wind size (acres / 0.03 = kW) | 200 |
| `--annual-kwh F` | annual electric load | 8000000 |
| `--load-profile NAME` | DOE reference building | Hospital |
| `--energy-rate F` | blended energy rate EUR/kWh | 0.26 |
| `--demand-rate F` | blended demand rate EUR/kW | 12 |
| `--analysis-years N` | financial horizon | 25 |
| `--out DIR` | output directory | optimizer/output |
| `--no-dashboard` | skip dashboard | (off) |

Weights are normalized to sum to 1. `--help` prints this list.

Cities with data (20 German): Munich, Berlin, Hamburg, Frankfurt, Cologne, Stuttgart, Nuremberg,
Dusseldorf, Leipzig, Dresden, Hanover, Freiburg, Bremen, Dortmund, Kiel, Erfurt, Rostock, Augsburg,
Wiesbaden, Mannheim. (See `optimizer/data/wind_production_factors.json`.)

### Examples

```bash
# default: time-dominant -> builds fast PV only
./run_optimization.sh

# cost-dominant, allow gas -> builds PV+Wind+Gas, slower buildout, cheaper
./run_optimization.sh --time-weight 0.05 --cost-weight 0.85 --co2-weight 0.10 --generator on

# Hamburg, CO2-focused, bigger wind plot
./run_optimization.sh --city Hamburg --co2-weight 0.6 --cost-weight 0.3 --time-weight 0.1 --wind-acres 400

# off-grid island (needs storage/generation to be feasible)
./run_optimization.sh --grid off --battery on --generator on
```

---

## 6. How the weights map onto the model (scalarization)

The model uses absolute monetary penalties, so the 3 normalized weights are mapped to two
coefficients at reference scales (in `assemble_scenario.py`):

```
buildout_time_cost_per_year = (w_time / w_cost) * COST_SCALE / TIME_SCALE
CO2_cost_per_tonne          = (w_co2  / w_cost) * COST_SCALE / (PWF_CO2 * CO2_SCALE)
include_climate_in_objective = true
```
with `COST_SCALE = 9.3e6` EUR (LCC spread), `CO2_SCALE = 1373` t/yr (BAU emissions),
`TIME_SCALE = max buildout_time among the buildable techs` (yr), `PWF_CO2 = 16.25`
(lifecycle present-worth factor). Cost is the numeraire (weight on LCC = 1). The actual mapping
used for a run is recorded in `output/weight_mapping.json`.

Lead times (days) in `optimizer/data/lead_times.json`, synced from the labmate fork defaults
(commit 05983f4a): Grid 0, PV 730 (2 yr), Battery 730 (2 yr), Wind 1095 (3 yr), Generator 1460 (4 yr).
Edit to taste. Note: Generator is now the slowest to deploy.

> Note: CHP was intentionally removed from this tool. Its unit-commitment binaries made the MILP
> much slower for little benefit in these electric-only scenarios. The labmate's fork still supports
> CHP, but `run_optimization.sh` no longer exposes it.

---

## 7. Data provenance (our additions)

- **Wind** (`optimizer/data/wind_production_factors.json`): 8760-h capacity factors per city, built by
  `wind_data/build_wind_data.py` from ERA5 (Open-Meteo, keyless) through REopt's turbine power curve.
  Needed because REopt's Wind Toolkit is US-only. Fed into `Wind.production_factor_series`.
- **Grid CO2** (`optimizer/data/german_grid_emissions.json`): 8760-h German grid carbon intensity
  (lb/kWh), built by `german_grid/german_grid_emissions.py` from SMARD.de actual generation by fuel.
  Needed because AVERT/Cambium are US-only. Fed into `ElectricUtility.emissions_factor_series_lb_CO2_per_kwh`.
- **PV** production factor is fetched live from PVWatts (works worldwide; uses the key in keys.py).

---

## 8. Reading results

Native REopt.jl output (top-level sections), saved to `output/results.json`:
- sizes: `PV.size_kw`, `Wind.size_kw`, `Generator.size_kw`, `CHP.size_kw`, `ElectricStorage.size_kwh`
- `Site.system_buildout_time_years` - the headline time metric (MAX lead of built techs)
- `Financial.lcc`, `Financial.lcc_bau` (NPV = lcc_bau - lcc)
- `Site.annual_emissions_tonnes_CO2` (+ `_bau`)
- per-tech hourly `electric_to_load_series_kw`, etc.

The dashboard (`output/dashboard.html` + `dashboard.png`) visualizes all of this.

### Validated results
- Default (time 0.50): **PV-only ~2.8 MW, buildout 0.25 yr, LCC ~EUR 29M**.
- Cost-dominant (time 0.05, +generator): **PV+Wind+Gas, buildout 1.48 yr, LCC ~EUR 20M, CO2 +55%**.
The time weight clearly drives the technology mix and the buildout time.

---

## 9. Known caveats

- **Solve time**: the buildout binaries make each solve ~2-5 min (BAU + optimal). Be patient.
- **Benign warnings** for German sites: "Could not find AVERT region", "Cambium ... outside CONUS",
  "EASIUR ... outside CAMx grid". These are US-only datasets; we supply CO2 ourselves, so ignore them.
- **Off-grid** (`--grid off`) sets `Settings.off_grid_flag=true`; the system must meet load every hour,
  so it generally needs battery and/or generator or it will be infeasible.
- **API key**: PV needs PVWatts. `DEMO_KEY` is rate-limited (10/hr); keys.py holds a real key.
- **git push to MaxHStanford is currently blocked**: the repo `MaxHStanford/energy_ai_hack_DC` does
  not exist and `gh` is not installed, so it cannot be auto-created. SSH authenticates as MaxHStanford,
  so once the empty repo exists: `git -C Hackathon/energy_ai_hack_DC push -u maxh HEAD`.

---

## 10. File map

```
Hackathon/
  optimizer/                         <- the parameterized tool (use this)
    run_optimization.sh              main entry point (all parameters)
    assemble_scenario.py             builds scenario.json from params + maps weights
    run_buildout.jl                  Julia driver (run_reopt on the fork, HiGHS)
    build_dashboard.py               results.json -> dashboard.html
    data/
      wind_production_factors.json   per-city 8760-h wind capacity factors
      german_grid_emissions.json     8760-h German grid CO2 intensity
      lead_times.json                per-source deployment lead times (days)
    output/                          scenario.json, results.json, weight_mapping.json, dashboard.*
    output_costdom/                  saved cost-dominant example run
  energy_ai_hack_DC/                 labmate's REopt.jl fork (buildout-time)
    hackathon_munich_dc/             our integration bundle committed into the fork
  REopt_API/                         Django API + docker-compose (creates the stack)
  wind_data/ , german_grid/          data generators (ERA5 wind, SMARD CO2)
  munich_run/ , buildout_run/        earlier one-off runs (superseded by optimizer/)
```
