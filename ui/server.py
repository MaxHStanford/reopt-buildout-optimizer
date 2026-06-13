#!/usr/bin/env python3
"""Flask backend for the off-grid buildout UI.

Serves the static `ui/` folder and exposes POST /api/optimize, which runs the
genetic-algorithm solver (optimizer/ga/ga_solver.py, European prices) over all
German cities for the user's weights + load, then returns the best 5 cities plus
Munich with their full 8760-h dispatch for the interactive week selector.

Load cheat: the UI shows MW, but the GA actually solves at load/SCALE so it stays
in its numerically-tuned ~1 MW regime (and the per-acre area caps don't bind).
Because the rule-based dispatch is linear in load and capacity, every extensive
output (sizes, energy, dispatch series, cost, CO2) is multiplied back by SCALE so
the returned numbers describe the true full-scale system.
"""
import sys
from pathlib import Path

import numpy as np
from flask import Flask, jsonify, request, send_from_directory

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "optimizer" / "ga"))

import ga_solver as ga  # noqa: E402

SCALE = 100.0          # UI MW -> backend solves at MW/SCALE, results scaled back x SCALE
POP = 40
GENS = 30
HOURS_PER_WEEK = 168

app = Flask(__name__, static_folder=str(HERE), static_url_path="")


def _city_list():
    import json
    pv_db = json.load(open(ga.DATA / "pv_production_factors.json"))
    return list(pv_db.keys())


def _full_series(ctx, ind):
    """Full 8760-h served-by-source dispatch (GA scale) + per-hour renewable output."""
    pv_kw, wind_kw, batt_kwh, gen_kw = ind
    batt_kw = batt_kwh / ga.BATT_DURATION_H
    n = ctx["pv"].shape[0]
    pv_l = np.zeros(n); wind_l = np.zeros(n); batt_l = np.zeros(n)
    gas_l = np.zeros(n); unmet_l = np.zeros(n)
    ga.dispatch_series(ctx["load_kw"], ctx["pv"], ctx["wind"], pv_kw, wind_kw,
                       batt_kwh, batt_kw, gen_kw, ga.BATT_RT_EFF,
                       pv_l, wind_l, batt_l, gas_l, unmet_l)
    renew = pv_kw * ctx["pv"] + wind_kw * ctx["wind"]
    return pv_l, wind_l, batt_l, gas_l, unmet_l, renew


def _design_label(sizes):
    has_gen = sizes["genKw"] > 1
    has_ren = sizes["pvKw"] > 1 or sizes["windKw"] > 1
    if has_gen and has_ren:
        return "Renewables + gas backup"
    if has_gen:
        return "Gas only"
    return "Fully renewable + battery"


@app.route("/api/optimize", methods=["POST"])
def optimize():
    body = request.get_json(force=True) or {}
    raw = {
        "time": max(0.0, float(body.get("time", 34))),
        "cost": max(0.0, float(body.get("cost", 33))),
        "emit": max(0.0, float(body.get("emit", 33))),
    }
    s = raw["time"] + raw["cost"] + raw["emit"]
    if s <= 0:
        raw = {"time": 1, "cost": 1, "emit": 1}; s = 3
    norm = {k: v / s for k, v in raw.items()}
    weights = {"time": norm["time"], "cost": norm["cost"], "co2": norm["emit"]}

    load_kw_display = max(1.0, float(body.get("load_kw", 100_000.0)))  # full-scale kW
    ga_load_kw = load_kw_display / SCALE
    min_load_met = float(body.get("min_load_met", 0.80))

    cities = _city_list()
    evaluated = []
    for city in cities:
        ctx = ga.load_city_context(city, load_kw=ga_load_kw, weights=weights,
                                   min_load_met=min_load_met)
        best, fit, m = ga.run_ga(ctx, pop=POP, gens=GENS, seed=0)
        evaluated.append({"city": city, "ctx": ctx, "ind": best, "fit": fit, "m": m})

    evaluated.sort(key=lambda e: e["fit"])
    selected = evaluated[:5]
    if not any(e["city"] == "Munich" for e in selected):
        muni = next((e for e in evaluated if e["city"] == "Munich"), None)
        if muni:
            selected.append(muni)

    n_hours = selected[0]["ctx"]["pv"].shape[0]
    nweeks = n_hours // HOURS_PER_WEEK
    renew_weekly = np.zeros(nweeks)

    evals = []
    for rank, e in enumerate(selected, 1):
        ctx, m = e["ctx"], e["m"]
        pv_l, wind_l, batt_l, gas_l, unmet_l, renew = _full_series(ctx, e["ind"])
        renew_weekly += np.array([renew[w * 168:(w + 1) * 168].sum() for w in range(nweeks)])

        sizes = {"pvKw": m["pv_kw"] * SCALE, "windKw": m["wind_kw"] * SCALE,
                 "battKwh": m["batt_kwh"] * SCALE, "genKw": m["gen_kw"] * SCALE}
        e_ren = (m["e_pv"] + m["e_wind"] + m["e_batt"]) * SCALE
        windgen = m["e_pv"] + m["e_wind"]
        evals.append({
            "city": {"name": e["city"], "lat": ctx["lat"], "lon": ctx["lon"]},
            "rank": rank,
            "optimal": rank == 1,
            "isMunich": e["city"] == "Munich",
            "buildoutYears": m["buildout"],
            "lcc": m["lcc"] * SCALE,
            "capex": m["capex"] * SCALE,
            "co2Tonnes": m["co2_tonnes"] * SCALE,
            "served": m["served_fraction"],
            "windShare": (m["e_wind"] / windgen) if windgen > 0 else 0.0,
            "sCF": float(ctx["pv"].mean()),
            "wCF": float(ctx["wind"].mean()),
            "design": _design_label(sizes),
            "built": [t for t, ok in (("PV", sizes["pvKw"] > 1), ("Wind", sizes["windKw"] > 1),
                                      ("Battery", sizes["battKwh"] > 1), ("Generator", sizes["genKw"] > 1)) if ok],
            "sizes": sizes,
            "energy": {
                "L": m["total_load"] * SCALE,
                "pvKwh": m["e_pv"] * SCALE,
                "windKwh": m["e_wind"] * SCALE,
                "genKwh": m["e_gas"] * SCALE,
                "renewKwh": e_ren,
            },
            "loadKw": ctx["load_kw"] * SCALE,
            "series": {
                "pv": [int(round(x * SCALE)) for x in pv_l],
                "wind": [int(round(x * SCALE)) for x in wind_l],
                "battery": [int(round(x * SCALE)) for x in batt_l],
                "gas": [int(round(x * SCALE)) for x in gas_l],
                "unmet": [int(round(x * SCALE)) for x in unmet_l],
            },
        })

    stress_week = int(np.argmin(renew_weekly)) if nweeks else 0
    all_coords = [{"name": e["city"], "lat": e["ctx"]["lat"], "lon": e["ctx"]["lon"]}
                  for e in evaluated]

    return jsonify({
        "evals": evals,
        "nweeks": nweeks,
        "stressWeek": stress_week,
        "weights": norm,
        "minLoadMet": min_load_met,
        "allCoords": all_coords,
    })


@app.route("/")
def index():
    return send_from_directory(str(HERE), "index.html")


def _warm_start():
    """Trigger numba JIT compile so the first real request is fast."""
    try:
        ctx = ga.load_city_context("Munich", load_kw=1000.0)
        best, _, _ = ga.run_ga(ctx, pop=4, gens=1, seed=0)
        _full_series(ctx, best)
        print("[server] numba warm-start done")
    except Exception as exc:  # pragma: no cover
        print(f"[server] warm-start skipped: {exc}")


if __name__ == "__main__":
    _warm_start()
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=False)
