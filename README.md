# REopt Buildout-Time Optimizer

One-command, parameterized energy-system optimization for German sites that jointly minimizes
**cost + CO2 + deployment time** ("time-to-energy"). Built on a buildout-time fork of REopt.jl,
run locally with the HiGHS solver.

```bash
cd optimizer
./run_optimization.sh                      # default: time-weighted -> fast PV
./run_optimization.sh --time-weight 0.05 --cost-weight 0.85 --co2-weight 0.10 --generator on
./run_optimization.sh --city Hamburg --co2-weight 0.6 --cost-weight 0.3 --time-weight 0.1
./run_optimization.sh --help
```

Results + dashboard land in `optimizer/output/`.

## Prerequisites (one-time)

This optimizer drives a Dockerized REopt stack and the buildout-time REopt.jl fork. Full setup,
parameter reference, weight-mapping math, data provenance, and caveats are in **[HANDOFF.md](HANDOFF.md)**.
In short you need:

1. The REopt API Docker stack running (`julia_api` container, `localhost:8000`) -
   from https://github.com/NatLabRockies/REopt_API (`docker-compose up -d`).
2. The buildout-time fork overlaid into the container -
   from https://github.com/fschweden/energy_ai_hack_DC (see HANDOFF section 3).
3. A real NLR/NREL developer API key in `REopt_API/keys.py` (for PVWatts).

See HANDOFF.md for exact commands.

## What's here

```
optimizer/
  run_optimization.sh      main entry point (all parameters)
  assemble_scenario.py     scenario builder + weight->penalty mapping
  run_buildout.jl          Julia driver (run_reopt on the fork)
  build_dashboard.py       results -> dashboard.html
  data/                    per-city wind capacity factors, German grid CO2, lead times
HANDOFF.md                 full documentation
```

Example default-run dashboard: `example_default_dashboard.png`.
