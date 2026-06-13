#!/usr/bin/env python3
"""Coherent results schema + saver, shared by the GA solver and the MILP comparison.

The schema captures exactly the five things we care about:
  1. location on the map        -> record["location"]
  2. composition of energy mix  -> record["energy_mix"]
  3. CO2                         -> record["co2"]
  4. time to energy             -> record["time_to_energy"]
  5. load-curve matching        -> record["load_matching"]  (representative week of dispatch)
plus economics and solver metadata.
"""
import json
from pathlib import Path


def make_record(*, method, location, config, sizes, annual_served_kwh,
                co2_tonnes, buildout_years, per_tech_years,
                load_matching, economics, solver_meta):
    """Assemble the coherent results record.

    sizes: {pv_kw, wind_kw, gen_kw, battery_kwh, battery_kw}
    annual_served_kwh: {pv, wind, battery, gas, unmet, total_load}
    load_matching: {week_start_hour, load_kw[168], served_by:{pv[],wind[],battery[],gas[],unmet[]}}
    """
    total_served = sum(v for k, v in annual_served_kwh.items()
                       if k not in ("unmet", "total_load"))
    total_load = annual_served_kwh.get("total_load", total_served + annual_served_kwh.get("unmet", 0.0))
    served_fraction = (total_served / total_load) if total_load else 0.0

    def share(x):
        return round(100.0 * x / total_load, 1) if total_load else 0.0

    return {
        "method": method,
        "location": location,                 # {city, latitude, longitude}
        "config": config,                     # {grid, load_kw, weights, min_load_met}
        "energy_mix": {
            "sizes_kw": sizes,
            "annual_served_kwh": {k: round(v, 1) for k, v in annual_served_kwh.items()},
            "served_fraction": round(served_fraction, 4),
            "shares_pct_of_load": {
                "pv": share(annual_served_kwh.get("pv", 0.0)),
                "wind": share(annual_served_kwh.get("wind", 0.0)),
                "battery": share(annual_served_kwh.get("battery", 0.0)),
                "gas": share(annual_served_kwh.get("gas", 0.0)),
                "unmet": share(annual_served_kwh.get("unmet", 0.0)),
            },
        },
        "co2": {"annual_tonnes": round(co2_tonnes, 2)},
        "time_to_energy": {
            "system_buildout_time_years": round(buildout_years, 3),
            "per_tech_years": per_tech_years,
        },
        "load_matching": load_matching,
        "economics": economics,
        "solver": solver_meta,
    }


def save(record, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    json.dump(record, open(path, "w"), indent=2)
    return path
