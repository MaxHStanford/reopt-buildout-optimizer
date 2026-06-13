#!/usr/bin/env python3
"""Compare the GA Munich result against the MILP Munich result.

Converts the MILP native REopt output into the same coherent schema as the GA,
then writes a side-by-side comparison JSON and prints a table.

Usage: python3 compare_munich.py <milp_results.json> [ga_results.json]
"""
import json
import sys
from pathlib import Path

import numpy as np

from save_results import make_record, save

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
MILP = sys.argv[1] if len(sys.argv) > 1 else str(HERE.parent / "output_munich_milp" / "results.json")
GA = sys.argv[2] if len(sys.argv) > 2 else str(HERE / "results" / "Munich.json")


def ssum(d, sec, key):
    v = d.get(sec, {}).get(key)
    return float(np.sum(v)) if isinstance(v, list) else 0.0


def milp_to_coherent(path):
    d = json.load(open(path))
    site, fin, load = d.get("Site", {}), d.get("Financial", {}), d.get("ElectricLoad", {})
    leads = json.load(open(DATA / "lead_times.json"))["lead_times_days"]
    lead_y = {k: v / 365.0 for k, v in leads.items()}

    def size(sec, key="size_kw"):
        v = d.get(sec, {}).get(key); return float(v) if v else 0.0

    pv_kw, wind_kw = size("PV"), size("Wind")
    gen_kw = size("Generator")
    batt_kwh, batt_kw = size("ElectricStorage", "size_kwh"), size("ElectricStorage", "size_kw")

    e_pv = ssum(d, "PV", "electric_to_load_series_kw")
    e_wind = ssum(d, "Wind", "electric_to_load_series_kw")
    e_gas = ssum(d, "Generator", "electric_to_load_series_kw")
    e_batt = ssum(d, "ElectricStorage", "storage_to_load_series_kw")
    load_series = load.get("load_series_kw", []) or []
    total_load = float(np.sum(load_series)) if load_series else 0.0
    served = e_pv + e_wind + e_gas + e_batt
    unmet = max(0.0, total_load - served)

    per_tech = {}
    if pv_kw > 1: per_tech["PV"] = round(lead_y["PV"], 3)
    if wind_kw > 1: per_tech["Wind"] = round(lead_y["Wind"], 3)
    if batt_kwh > 1: per_tech["ElectricStorage"] = round(lead_y["ElectricStorage"], 3)
    if gen_kw > 1: per_tech["Generator"] = round(lead_y["Generator"], 3)

    # representative (lowest-renewable) week from the dispatch series
    n = len(load_series)
    pv_s = np.asarray(d.get("PV", {}).get("electric_to_load_series_kw", [0] * n), float)
    wd_s = np.asarray(d.get("Wind", {}).get("electric_to_load_series_kw", [0] * n), float)
    bt_s = np.asarray(d.get("ElectricStorage", {}).get("storage_to_load_series_kw", [0] * n), float)
    gn_s = np.asarray(d.get("Generator", {}).get("electric_to_load_series_kw", [0] * n), float)
    ld = np.asarray(load_series, float)
    renew = pv_s + wd_s
    nweeks = n // 168 if n >= 168 else 1
    sums = [renew[w * 168:(w + 1) * 168].sum() for w in range(nweeks)]
    w0 = int(np.argmin(sums)) if sums else 0
    s, e = w0 * 168, w0 * 168 + 168
    unmet_s = np.maximum(0.0, ld - (pv_s + wd_s + bt_s + gn_s))
    week = {
        "week_start_hour": s,
        "description": "lowest-renewable week of the year",
        "load_kw": [round(x, 2) for x in ld[s:e]],
        "served_by": {
            "pv": [round(x, 2) for x in pv_s[s:e]], "wind": [round(x, 2) for x in wd_s[s:e]],
            "battery": [round(x, 2) for x in bt_s[s:e]], "gas": [round(x, 2) for x in gn_s[s:e]],
            "unmet": [round(x, 2) for x in unmet_s[s:e]],
        },
    }

    return make_record(
        method="MILP",
        location={"city": "Munich", "latitude": 48.14, "longitude": 11.58},
        config={"grid": "off", "load_kw": round(total_load / max(n, 1), 1),
                "weights": {"time": 0.50, "cost": 0.35, "co2": 0.15}, "min_load_met": 0.80},
        sizes={"pv_kw": round(pv_kw, 1), "wind_kw": round(wind_kw, 1), "gen_kw": round(gen_kw, 1),
               "battery_kwh": round(batt_kwh, 1), "battery_kw": round(batt_kw, 1)},
        annual_served_kwh={"pv": e_pv, "wind": e_wind, "battery": e_batt, "gas": e_gas,
                           "unmet": unmet, "total_load": total_load},
        co2_tonnes=site.get("annual_emissions_tonnes_CO2") or 0.0,
        buildout_years=site.get("system_buildout_time_years") or 0.0,
        per_tech_years=per_tech,
        load_matching=week,
        economics={"lcc_eur": round(fin.get("lcc") or 0.0, 0)},
        solver_meta={"method": "MILP", "status": d.get("status"),
                     "runtime_s": round(d.get("solver_seconds") or 0.0, 1)},
    )


def main():
    milp = milp_to_coherent(MILP)
    save(milp, HERE.parent / "output_munich_milp" / "coherent.json")
    ga = json.load(open(GA))

    def row(r):
        s = r["energy_mix"]["sizes_kw"]
        return {
            "method": r["method"],
            "pv_kw": s["pv_kw"], "wind_kw": s["wind_kw"], "gen_kw": s["gen_kw"],
            "battery_kwh": s["battery_kwh"],
            "buildout_years": r["time_to_energy"]["system_buildout_time_years"],
            "co2_tonnes": r["co2"]["annual_tonnes"],
            "lcc_eur": r["economics"].get("lcc_eur"),
            "served_fraction": r["energy_mix"]["served_fraction"],
            "runtime_s": r["solver"]["runtime_s"],
        }

    cmp = {"GA": row(ga), "MILP": row(milp)}
    save(cmp, HERE / "results" / "_compare_munich.json")

    print(f"\n{'metric':<22}{'GA':>14}{'MILP':>14}")
    print("-" * 50)
    for k in ["pv_kw", "wind_kw", "gen_kw", "battery_kwh", "buildout_years",
              "co2_tonnes", "lcc_eur", "served_fraction", "runtime_s"]:
        g, m = cmp["GA"][k], cmp["MILP"][k]
        print(f"{k:<22}{g:>14}{m:>14}")


if __name__ == "__main__":
    main()
