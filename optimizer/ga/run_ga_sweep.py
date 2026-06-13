#!/usr/bin/env python3
"""Run the GA solver for German cities (off-grid, 1000 kW) and save coherent results.

Usage:
  python3 run_ga_sweep.py                  # all cities
  python3 run_ga_sweep.py --city Munich    # single city
"""
import argparse
import json
import time
from pathlib import Path

import ga_solver as ga
from save_results import make_record, save

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def run_city(city, load_kw, weights, min_load_met, pop, gens):
    ctx = ga.load_city_context(city, load_kw=load_kw, weights=weights, min_load_met=min_load_met)
    t0 = time.time()
    best, fit, m = ga.run_ga(ctx, pop=pop, gens=gens)
    runtime = time.time() - t0
    week = ga.representative_week(ctx, best)

    per_tech_years = {}
    lead = ctx["lead"]
    if m["pv_kw"] > 1.0: per_tech_years["PV"] = round(lead["PV"], 3)
    if m["wind_kw"] > 1.0: per_tech_years["Wind"] = round(lead["Wind"], 3)
    if m["batt_kwh"] > 1.0: per_tech_years["ElectricStorage"] = round(lead["ElectricStorage"], 3)
    if m["gen_kw"] > 1.0: per_tech_years["Generator"] = round(lead["Generator"], 3)

    record = make_record(
        method="GA",
        location={"city": city, "latitude": ctx["lat"], "longitude": ctx["lon"]},
        config={"grid": "off", "load_kw": load_kw, "weights": weights, "min_load_met": min_load_met},
        sizes={"pv_kw": round(m["pv_kw"], 1), "wind_kw": round(m["wind_kw"], 1),
               "gen_kw": round(m["gen_kw"], 1), "battery_kwh": round(m["batt_kwh"], 1),
               "battery_kw": round(m["batt_kw"], 1)},
        annual_served_kwh={"pv": m["e_pv"], "wind": m["e_wind"], "battery": m["e_batt"],
                           "gas": m["e_gas"], "unmet": m["e_unmet"], "total_load": m["total_load"]},
        co2_tonnes=m["co2_tonnes"],
        buildout_years=m["buildout"], per_tech_years=per_tech_years,
        load_matching=week,
        economics={"lcc_eur": round(m["lcc"], 0), "capex_eur": round(m["capex"], 0),
                   "annual_fuel_gal": round(m["fuel_gal"], 0)},
        solver_meta={"method": "GA", "runtime_s": round(runtime, 2), "generations": gens,
                     "population": pop, "fitness": round(fit, 5)},
    )
    save(record, RESULTS / f"{city}.json")
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default=None)
    ap.add_argument("--load-kw", type=float, default=1000.0)
    ap.add_argument("--pop", type=int, default=60)
    ap.add_argument("--gens", type=int, default=50)
    ap.add_argument("--time-weight", type=float, default=0.50)
    ap.add_argument("--cost-weight", type=float, default=0.35)
    ap.add_argument("--co2-weight", type=float, default=0.15)
    ap.add_argument("--min-load-met", type=float, default=0.80)
    a = ap.parse_args()
    weights = {"time": a.time_weight, "cost": a.cost_weight, "co2": a.co2_weight}

    pv_db = json.load(open(ga.DATA / "pv_production_factors.json"))
    cities = [a.city] if a.city else list(pv_db.keys())

    print(f"GA off-grid sweep | load {a.load_kw:.0f} kW | weights {weights} | "
          f"pop {a.pop} gens {a.gens}")
    print(f"{'City':<12} {'PV':>6} {'Wind':>6} {'Gas':>6} {'Batt kWh':>9} "
          f"{'build yr':>8} {'CO2 t':>7} {'LCC M':>6} {'served':>7} {'s':>5}")
    print("-" * 86)
    summary = {}
    for city in cities:
        r = run_city(city, a.load_kw, weights, a.min_load_met, a.pop, a.gens)
        s = r["energy_mix"]["sizes_kw"]; em = r["energy_mix"]
        summary[city] = {
            "pv_kw": s["pv_kw"], "wind_kw": s["wind_kw"], "gen_kw": s["gen_kw"],
            "battery_kwh": s["battery_kwh"],
            "buildout_years": r["time_to_energy"]["system_buildout_time_years"],
            "co2_tonnes": r["co2"]["annual_tonnes"], "lcc_eur": r["economics"]["lcc_eur"],
            "served_fraction": em["served_fraction"], "runtime_s": r["solver"]["runtime_s"],
        }
        print(f"{city:<12} {s['pv_kw']:>6.0f} {s['wind_kw']:>6.0f} {s['gen_kw']:>6.0f} "
              f"{s['battery_kwh']:>9.0f} {r['time_to_energy']['system_buildout_time_years']:>8.2f} "
              f"{r['co2']['annual_tonnes']:>7.0f} {r['economics']['lcc_eur']/1e6:>6.1f} "
              f"{em['served_fraction']:>7.2f} {r['solver']['runtime_s']:>5.1f}")
    json.dump(summary, open(RESULTS / "_summary.json", "w"), indent=2)
    print(f"\nWrote {len(cities)} city files + _summary.json to {RESULTS}")


if __name__ == "__main__":
    main()
