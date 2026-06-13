#!/usr/bin/env python3
"""Assemble a REopt (buildout-time fork) scenario from CLI parameters.

Driven by run_optimization.sh. Produces:
  - <out>/scenario.json        the native REopt.jl scenario for the fork
  - <out>/weight_mapping.json  the weight -> monetary-penalty mapping (for the dashboard)

Data sources (in data/):
  - wind_production_factors.json  city -> {latitude, longitude, production_factor_series[8760]}
  - german_grid_emissions.json    8760-h grid CO2 intensity [lb/kWh]
  - lead_times.json               per-source deployment lead times [days]
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

# ---- fixed model assumptions ----
COST_SCALE = 9.3e6     # EUR; LCC spread (reference for scalarization)
CO2_SCALE = 1373.0     # tonnes CO2/yr; BAU annual emissions (reference)
PWF_CO2 = 16.25        # lifecycle present-worth factor REopt applies to annual CO2 cost
DAYS_PER_YEAR = 365.0
PV_ACRES_PER_KW = 0.006    # ground-mount PV power density
WIND_ACRES_PER_KW = 0.03   # wind power density (~30 acres/MW)


def parse_args():
    p = argparse.ArgumentParser(description="Assemble REopt buildout-time scenario")
    # weights
    p.add_argument("--time-weight", type=float, default=0.50)
    p.add_argument("--cost-weight", type=float, default=0.35)
    p.add_argument("--co2-weight", type=float, default=0.15)
    # location
    p.add_argument("--city", default="Munich", help="German city with wind+location data")
    # toggles
    p.add_argument("--grid", choices=["on", "off"], default="on")
    p.add_argument("--pv", choices=["on", "off"], default="on")
    p.add_argument("--wind", choices=["on", "off"], default="on")
    p.add_argument("--battery", choices=["on", "off"], default="on")
    p.add_argument("--generator", choices=["on", "off"], default="off")
    # areas (acres)
    p.add_argument("--pv-acres", type=float, default=50.0)
    p.add_argument("--wind-acres", type=float, default=200.0)
    # load + tariff
    p.add_argument("--annual-kwh", type=float, default=8_000_000.0)
    p.add_argument("--load-profile", default="Hospital")
    p.add_argument("--energy-rate", type=float, default=0.26)
    p.add_argument("--demand-rate", type=float, default=12.0)
    p.add_argument("--analysis-years", type=int, default=25)
    p.add_argument("--timeout-seconds", type=int, default=60, help="solver time cap")
    p.add_argument("--gap", type=float, default=0.10, help="MIP optimality tolerance")
    p.add_argument("--min-load-met", type=float, default=1.0,
                   help="off-grid: min annual fraction of load that must be served "
                        "(<1 allows load shedding / longer under-supply, easier to solve)")
    p.add_argument("--out", default=str(HERE / "output"))
    return p.parse_args()


def main():
    a = parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    # normalize weights; cost is the numeraire so it must be > 0
    w = {"time": a.time_weight, "cost": a.cost_weight, "co2": a.co2_weight}
    tot = sum(w.values())
    if tot <= 0:
        sys.exit("weights must sum to > 0")
    w = {k: v / tot for k, v in w.items()}
    if w["cost"] < 1e-6:
        w["cost"] = 1e-6  # floor: cost is the objective numeraire

    wind_db = json.load(open(DATA / "wind_production_factors.json"))
    if a.city not in wind_db:
        sys.exit(f"city '{a.city}' not in wind dataset. Options: {', '.join(sorted(wind_db))}")
    city = wind_db[a.city]
    co2 = json.load(open(DATA / "german_grid_emissions.json"))
    leads = json.load(open(DATA / "lead_times.json"))["lead_times_days"]
    bo_years = {t: days / DAYS_PER_YEAR for t, days in leads.items()}

    scenario = {
        "Meta": {
            "description": (f"{a.city} | weights t/c/co2={w['time']:.2f}/{w['cost']:.2f}/{w['co2']:.2f} | "
                            f"grid={a.grid} pv={a.pv}({a.pv_acres}ac) wind={a.wind}({a.wind_acres}ac)"),
            "address": a.city + ", DE",
        },
        "Settings": {
            "solver_name": "HiGHS",
            "time_steps_per_hour": 1,
            "include_climate_in_objective": True,
            "off_grid_flag": (a.grid == "off"),
            # keys required by the Julia /reopt HTTP endpoint (it pops these before building Settings)
            # skip BAU off-grid (a do-nothing island can't meet load -> infeasible BAU)
            "run_bau": (a.grid == "on"),
            "timeout_seconds": a.timeout_seconds,
            "optimality_tolerance": a.gap,  # loose gap; buildout binaries make
            # optimality hard to *prove*, so we return the incumbent at the time cap
        },
        "Site": {"latitude": city["latitude"], "longitude": city["longitude"]},
        "ElectricLoad": {"doe_reference_name": a.load_profile, "annual_kwh": a.annual_kwh, "year": 2017},
        "Financial": {
            "analysis_years": a.analysis_years,
            "elec_cost_escalation_rate_fraction": 0.02,
            "offtaker_discount_rate_fraction": 0.08,
            "owner_discount_rate_fraction": 0.08,
            "offtaker_tax_rate_fraction": 0.0,
            "owner_tax_rate_fraction": 0.0,
            "om_cost_escalation_rate_fraction": 0.025,
        },
    }

    # Tariff + grid emissions only when grid-connected
    if a.grid == "on":
        scenario["ElectricTariff"] = {
            "blended_annual_energy_rate": a.energy_rate,
            "blended_annual_demand_rate": a.demand_rate,
        }
        scenario["ElectricUtility"] = {
            "emissions_factor_series_lb_CO2_per_kwh": co2["emissions_factor_series_lb_CO2_per_kwh"],
        }
    else:
        # off-grid: REopt forbids Meta and an ElectricTariff/ElectricUtility; drop them
        scenario.pop("Meta", None)

    if a.pv == "on":
        scenario["PV"] = {
            "installed_cost_per_kw": 1300.0, "om_cost_per_kw": 15.0,
            "federal_itc_fraction": 0.0, "macrs_option_years": 0,
            "tilt": 30.0, "azimuth": 180.0, "array_type": 1, "module_type": 0,
            "location": "ground",
            "max_kw": round(a.pv_acres / PV_ACRES_PER_KW, 1),
            "buildout_time": round(bo_years["PV"], 4),
        }
    if a.wind == "on":
        scenario["Wind"] = {
            "size_class": "large",
            "production_factor_series": city["production_factor_series"],
            "installed_cost_per_kw": 1600.0, "om_cost_per_kw": 40.0,
            "federal_itc_fraction": 0.0, "macrs_option_years": 0,
            "max_kw": round(a.wind_acres / WIND_ACRES_PER_KW, 1),
            "buildout_time": round(bo_years["Wind"], 4),
        }
    if a.battery == "on":
        scenario["ElectricStorage"] = {
            "installed_cost_per_kw": 800.0, "installed_cost_per_kwh": 350.0,
            "installed_cost_constant": 0.0,  # drop the fixed-cost binary -> faster MILP
            "replace_cost_per_kw": 380.0, "replace_cost_per_kwh": 180.0,
            "total_itc_fraction": 0.0, "macrs_option_years": 0,
            "can_grid_charge": (a.grid == "on"),
            "buildout_time": round(bo_years["ElectricStorage"], 4),
        }
    if a.generator == "on":
        # off-grid needs firm dispatchable capacity >= peak load; forcing the generator min size
        # guarantees a feasible island and gives HiGHS an easy first incumbent (else it can't find one)
        avg_load_kw = a.annual_kwh / 8760.0
        gen_min_kw = round(avg_load_kw * 1.05, 1) if a.grid == "off" else 0.0
        # tight max off-grid shrinks the big-M on the 8760 hourly on/off binaries -> HiGHS solves faster
        gen_max_kw = round(avg_load_kw * 1.5, 1) if a.grid == "off" else 5000.0
        scenario["Generator"] = {
            "min_kw": gen_min_kw, "max_kw": gen_max_kw,
            "only_runs_during_grid_outage": False, "sells_energy_back_to_grid": False,
            "installed_cost_per_kw": 1000.0, "om_cost_per_kw": 20.0, "fuel_cost_per_gallon": 3.0,
            "fuel_avail_gal": 1.0e9,  # effectively unlimited fuel so it can run continuously off-grid
            "min_turn_down_fraction": 0.0,  # no min-loading -> avoids hourly on/off commitment binaries
            "macrs_option_years": 0,
            "buildout_time": round(bo_years["Generator"], 4),
        }
    # off-grid relaxations: allow under-serving the load and drop operating-reserve burden
    # (makes the island MILP feasible/easier instead of requiring ~100% load met every hour)
    if a.grid == "off":
        scenario["ElectricLoad"]["min_load_met_annual_fraction"] = a.min_load_met
        scenario["ElectricLoad"]["operating_reserve_required_fraction"] = 0.0
        scenario["ElectricLoad"]["critical_load_fraction"] = 1.0  # serve full load (match GA)
        for t in ("PV", "Wind"):
            if t in scenario:
                scenario[t]["operating_reserve_required_fraction"] = 0.0

    # ---- map weights -> buildout_time_cost_per_year + CO2 price ----
    present_bo = [scenario[t]["buildout_time"] for t in ["PV", "Wind", "ElectricStorage", "Generator"]
                  if t in scenario]
    time_scale = max(present_bo) if present_bo else 1.0
    B = (w["time"] / w["cost"]) * COST_SCALE / time_scale
    co2_price = (w["co2"] / w["cost"]) * COST_SCALE / (PWF_CO2 * CO2_SCALE)
    scenario["Settings"]["buildout_time_cost_per_year"] = round(B, 2)
    scenario["Financial"]["CO2_cost_per_tonne"] = round(co2_price, 2)

    json.dump(scenario, open(out / "scenario.json", "w"))
    mapping = {
        "weights": w, "city": a.city,
        "buildout_time_years": {t: scenario[t]["buildout_time"] for t in
                                ["PV", "Wind", "ElectricStorage", "Generator"] if t in scenario},
        "buildout_time_cost_per_year_eur": round(B, 2),
        "CO2_cost_per_tonne_eur": round(co2_price, 2),
        "include_climate_in_objective": True,
        "grid": a.grid, "chp": "off",
        "reference_scales": {"cost_eur": COST_SCALE, "co2_tonnes": CO2_SCALE,
                             "time_years": time_scale, "pwf_co2": PWF_CO2},
    }
    json.dump(mapping, open(out / "weight_mapping.json", "w"), indent=2)

    techs = [t for t in ["PV", "Wind", "ElectricStorage", "Generator"] if t in scenario]
    print(f"scenario: {a.city} | grid={a.grid} | techs={','.join(techs)}")
    print(f"  weights t/c/co2 = {w['time']:.2f}/{w['cost']:.2f}/{w['co2']:.2f}")
    print(f"  buildout_time_cost_per_year = EUR {B:,.0f}/yr ; CO2 price = EUR {co2_price:,.1f}/t")


if __name__ == "__main__":
    main()
