#!/usr/bin/env python3
"""Genetic-algorithm solver for off-grid PV+Wind+Battery+Gas sizing.

Reframes the REopt off-grid problem (hard for MILP due to 8760 hourly generator
on/off binaries) as a low-dimensional sizing search scored by a fast rule-based
hourly dispatch. Decision vector: [PV_kw, Wind_kw, Battery_kwh, Gen_kw].

Objective (minimize), matching the MILP weighting: weighted sum of normalized
cost, CO2, and system buildout time, plus a penalty for unmet load below the
minimum served fraction.
"""
import json
import time
from pathlib import Path

import numpy as np
from numba import njit

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"

# ---- economic + technical constants (mirror the MILP scenario) ----
COST_PV_PER_KW = 900.0      # solar cheaper
COST_WIND_PER_KW = 2200.0   # wind more expensive
COST_BATT_PER_KWH = 80.0    # battery cheaper still (was 120/350)
COST_BATT_PER_KW = 150.0    # battery power cheaper (was 250/800)
COST_GEN_PER_KW = 1200.0    # gas capex more expensive (EU)
OM_PV = 15.0
OM_WIND = 40.0
OM_GEN = 20.0
FUEL_EUR_PER_GAL = 6.0      # EU diesel/gas ~2x US (was 3.0)
GEN_ELEC_EFF = 0.34
GEN_HHV_KWH_PER_GAL = 40.7
DIESEL_KG_CO2_PER_GAL = 10.18
BATT_RT_EFF = 0.90          # round-trip efficiency
BATT_DURATION_H = 2.0       # power = kwh / duration
DISCOUNT = 0.08
YEARS = 25
BATT_REPLACE_YEAR = 10
PWF = (1 - (1 + DISCOUNT) ** -YEARS) / DISCOUNT            # ~10.675
DISC10 = (1 + DISCOUNT) ** -BATT_REPLACE_YEAR              # ~0.4632

# ---- reference scales for weight normalization (off-grid, ~1000 kW) ----
COST_SCALE = 15.0e6
CO2_SCALE = 6000.0
TIME_SCALE = 4.0


@njit(cache=True)
def dispatch_agg(load_kw, pv, wind, pv_kw, wind_kw, batt_kwh, batt_kw, gen_kw, eff):
    """Rule-based hourly dispatch. Returns annual energy (kWh) by source + gas fuel kWh."""
    n = pv.shape[0]
    soc = 0.0
    e_pv = 0.0
    e_wind = 0.0
    e_batt = 0.0
    e_gas = 0.0
    e_unmet = 0.0
    sqrt_eff = eff ** 0.5
    for t in range(n):
        gen_pv = pv_kw * pv[t]
        gen_wd = wind_kw * wind[t]
        renew = gen_pv + gen_wd
        to_load = renew if renew < load_kw else load_kw
        if renew > 0.0:
            e_pv += to_load * (gen_pv / renew)
            e_wind += to_load * (gen_wd / renew)
        deficit = load_kw - to_load
        surplus = renew - to_load
        # charge battery with surplus
        if surplus > 0.0 and soc < batt_kwh:
            room = (batt_kwh - soc)
            charge = surplus
            if charge > batt_kw:
                charge = batt_kw
            stored = charge * sqrt_eff
            if stored > room:
                stored = room
            soc += stored
        # discharge to cover deficit
        if deficit > 0.0 and soc > 0.0:
            dis = deficit
            if dis > batt_kw:
                dis = batt_kw
            avail = soc * sqrt_eff
            if dis > avail:
                dis = avail
            e_batt += dis
            soc -= dis / sqrt_eff
            deficit -= dis
        # gas covers remaining deficit
        if deficit > 0.0 and gen_kw > 0.0:
            g = deficit if deficit < gen_kw else gen_kw
            e_gas += g
            deficit -= g
        if deficit > 0.0:
            e_unmet += deficit
    return e_pv, e_wind, e_batt, e_gas, e_unmet


@njit(cache=True)
def dispatch_series(load_kw, pv, wind, pv_kw, wind_kw, batt_kwh, batt_kw, gen_kw, eff,
                    pv_l, wind_l, batt_l, gas_l, unmet_l):
    """Same dispatch, but fills per-hour served-by-source arrays (for the winner)."""
    n = pv.shape[0]
    soc = 0.0
    sqrt_eff = eff ** 0.5
    for t in range(n):
        gen_pv = pv_kw * pv[t]
        gen_wd = wind_kw * wind[t]
        renew = gen_pv + gen_wd
        to_load = renew if renew < load_kw else load_kw
        if renew > 0.0:
            pv_l[t] = to_load * (gen_pv / renew)
            wind_l[t] = to_load * (gen_wd / renew)
        deficit = load_kw - to_load
        surplus = renew - to_load
        if surplus > 0.0 and soc < batt_kwh:
            charge = surplus if surplus < batt_kw else batt_kw
            stored = charge * sqrt_eff
            room = batt_kwh - soc
            if stored > room:
                stored = room
            soc += stored
        if deficit > 0.0 and soc > 0.0:
            dis = deficit if deficit < batt_kw else batt_kw
            avail = soc * sqrt_eff
            if dis > avail:
                dis = avail
            batt_l[t] = dis
            soc -= dis / sqrt_eff
            deficit -= dis
        if deficit > 0.0 and gen_kw > 0.0:
            g = deficit if deficit < gen_kw else gen_kw
            gas_l[t] = g
            deficit -= g
        if deficit > 0.0:
            unmet_l[t] = deficit


def evaluate(ind, ctx):
    """Return (fitness, metrics dict) for a design vector ind=[pv,wind,batt_kwh,gen]."""
    pv_kw, wind_kw, batt_kwh, gen_kw = ind
    batt_kw = batt_kwh / BATT_DURATION_H
    e_pv, e_wind, e_batt, e_gas, e_unmet = dispatch_agg(
        ctx["load_kw"], ctx["pv"], ctx["wind"], pv_kw, wind_kw, batt_kwh, batt_kw, gen_kw, BATT_RT_EFF)
    total_load = ctx["load_kw"] * ctx["pv"].shape[0]
    served = total_load - e_unmet
    served_fraction = served / total_load if total_load else 0.0

    fuel_gal = e_gas / (GEN_ELEC_EFF * GEN_HHV_KWH_PER_GAL) if e_gas > 0 else 0.0
    co2_tonnes = fuel_gal * DIESEL_KG_CO2_PER_GAL / 1000.0

    capex = (pv_kw * COST_PV_PER_KW + wind_kw * COST_WIND_PER_KW
             + batt_kwh * COST_BATT_PER_KWH + batt_kw * COST_BATT_PER_KW
             + gen_kw * COST_GEN_PER_KW)
    om_annual = pv_kw * OM_PV + wind_kw * OM_WIND + gen_kw * OM_GEN
    fuel_annual = fuel_gal * FUEL_EUR_PER_GAL
    batt_replace = (batt_kwh * 50.0 + batt_kw * 90.0) * DISC10  # cheaper replacement
    lcc = capex + PWF * (om_annual + fuel_annual) + batt_replace

    lead = ctx["lead"]
    built_leads = []
    if pv_kw > 1.0:
        built_leads.append(lead["PV"])
    if wind_kw > 1.0:
        built_leads.append(lead["Wind"])
    if batt_kwh > 1.0:
        built_leads.append(lead["ElectricStorage"])
    if gen_kw > 1.0:
        built_leads.append(lead["Generator"])
    buildout = max(built_leads) if built_leads else 0.0

    w = ctx["weights"]
    fit = (w["cost"] * lcc / COST_SCALE
           + w["co2"] * co2_tonnes / CO2_SCALE
           + w["time"] * buildout / TIME_SCALE)
    if served_fraction < ctx["min_load_met"]:
        fit += 1.0e3 * (ctx["min_load_met"] - served_fraction)

    metrics = dict(pv_kw=pv_kw, wind_kw=wind_kw, batt_kwh=batt_kwh, batt_kw=batt_kw,
                   gen_kw=gen_kw, e_pv=e_pv, e_wind=e_wind, e_batt=e_batt, e_gas=e_gas,
                   e_unmet=e_unmet, total_load=total_load, served_fraction=served_fraction,
                   co2_tonnes=co2_tonnes, lcc=lcc, capex=capex, buildout=buildout, fuel_gal=fuel_gal)
    return fit, metrics


def run_ga(ctx, pop=60, gens=50, seed=0, elite=2):
    rng = np.random.default_rng(seed)
    lo = np.array([0.0, 0.0, 0.0, 0.0])
    hi = np.array([ctx["pv_max"], ctx["wind_max"], ctx["batt_max"], ctx["gen_max"]])
    P = lo + rng.random((pop, 4)) * (hi - lo)
    # seed one generator-heavy individual to guarantee an early feasible point
    P[0] = np.array([0.0, 0.0, 0.0, ctx["load_kw"] * 1.2])

    def fits(pop_arr):
        out = np.empty(len(pop_arr))
        for i in range(len(pop_arr)):
            out[i], _ = evaluate(pop_arr[i], ctx)
        return out

    f = fits(P)
    for _ in range(gens):
        order = np.argsort(f)
        newP = [P[order[i]].copy() for i in range(elite)]  # elitism
        while len(newP) < pop:
            # tournament selection
            a, b = rng.integers(0, pop, 2)
            p1 = P[a] if f[a] < f[b] else P[b]
            a, b = rng.integers(0, pop, 2)
            p2 = P[a] if f[a] < f[b] else P[b]
            # BLX-0.5 crossover
            alpha = 0.5
            lo2 = np.minimum(p1, p2)
            hi2 = np.maximum(p1, p2)
            d = hi2 - lo2
            child = rng.uniform(lo2 - alpha * d, hi2 + alpha * d)
            # gaussian mutation
            if rng.random() < 0.3:
                child += rng.normal(0, 0.1, 4) * (hi - lo)
            child = np.clip(child, lo, hi)
            newP.append(child)
        P = np.array(newP)
        f = fits(P)

    best = P[int(np.argmin(f))]
    fit, metrics = evaluate(best, ctx)
    return best, fit, metrics


def representative_week(ctx, ind):
    """Return the 168-hour window with the lowest renewable availability (most stressed)."""
    pv_kw, wind_kw, batt_kwh, gen_kw = ind
    batt_kw = batt_kwh / BATT_DURATION_H
    n = ctx["pv"].shape[0]
    pv_l = np.zeros(n); wind_l = np.zeros(n); batt_l = np.zeros(n)
    gas_l = np.zeros(n); unmet_l = np.zeros(n)
    dispatch_series(ctx["load_kw"], ctx["pv"], ctx["wind"], pv_kw, wind_kw,
                    batt_kwh, batt_kw, gen_kw, BATT_RT_EFF, pv_l, wind_l, batt_l, gas_l, unmet_l)
    renew = pv_kw * ctx["pv"] + wind_kw * ctx["wind"]
    nweeks = n // 168
    sums = [renew[w * 168:(w + 1) * 168].sum() for w in range(nweeks)]
    w = int(np.argmin(sums))
    s, e = w * 168, w * 168 + 168
    return {
        "week_start_hour": s,
        "description": "lowest-renewable (most gas/battery reliant) week of the year",
        "load_kw": [ctx["load_kw"]] * 168,
        "served_by": {
            "pv": [round(x, 2) for x in pv_l[s:e]],
            "wind": [round(x, 2) for x in wind_l[s:e]],
            "battery": [round(x, 2) for x in batt_l[s:e]],
            "gas": [round(x, 2) for x in gas_l[s:e]],
            "unmet": [round(x, 2) for x in unmet_l[s:e]],
        },
    }


def load_city_context(city, load_kw=1000.0, weights=None, min_load_met=0.80,
                      pv_acres=50.0, wind_acres=200.0):
    weights = weights or {"time": 0.50, "cost": 0.35, "co2": 0.15}
    pv_db = json.load(open(DATA / "pv_production_factors.json"))
    wind_db = json.load(open(DATA / "wind_production_factors.json"))
    leads = json.load(open(DATA / "lead_times.json"))["lead_times_days"]
    lead_years = {k: v / 365.0 for k, v in leads.items()}
    pv = np.asarray(pv_db[city]["production_factor_series"], dtype=np.float64)
    wind = np.asarray(wind_db[city]["production_factor_series"], dtype=np.float64)
    return {
        "city": city,
        "lat": pv_db[city]["latitude"], "lon": pv_db[city]["longitude"],
        "load_kw": load_kw, "pv": pv, "wind": wind, "lead": lead_years,
        "weights": weights, "min_load_met": min_load_met,
        "pv_max": pv_acres / 0.006, "wind_max": wind_acres / 0.03,
        "batt_max": 60000.0, "gen_max": load_kw * 3.0,
    }
