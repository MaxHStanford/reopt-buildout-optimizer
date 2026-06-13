#!/usr/bin/env bash
#
# run_optimization.sh - one-command, fully parameterized REopt buildout-time optimization.
#
# Solves the Munich/Germany energy-system optimization on the labmate's buildout-time REopt
# fork (cost + CO2 + deployment-time), running locally in the julia_api Docker container.
#
# PARAMETERS (all optional; sensible defaults):
#   --time-weight F        weight on deployment time   (default 0.50)
#   --cost-weight F        weight on lifecycle cost     (default 0.35)
#   --co2-weight F         weight on CO2 emissions      (default 0.15)
#                          (weights are normalized to sum to 1)
#   --city NAME            location (German city w/ wind+solar data, default Munich)
#   --grid on|off          grid access (off => off-grid island)          (default on)
#   --pv on|off            allow solar PV                                 (default on)
#   --wind on|off          allow wind                                    (default on)
#   --battery on|off       allow battery storage                         (default on)
#   --generator on|off     allow grid-parallel gas generator             (default off)
#   --pv-acres F           land area for PV  -> caps PV size              (default 50)
#   --wind-acres F         land area for wind -> caps wind size           (default 200)
#   --annual-kwh F         annual electric load                          (default 8000000)
#   --load-profile NAME    DOE reference building                        (default Hospital)
#   --energy-rate F        blended energy rate EUR/kWh                    (default 0.26)
#   --demand-rate F        blended demand rate EUR/kW                     (default 12)
#   --analysis-years N     financial horizon                             (default 25)
#   --no-dashboard         skip HTML/PNG dashboard generation
#   --help                 show this help
#
# Cities with data: run `python3 assemble_scenario.py --city ?` (see data/wind_production_factors.json)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTDIR="$SCRIPT_DIR/output"
JULIA_URL="${JULIA_URL:-http://localhost:8081/reopt}"   # warm Julia REopt server
KEYS_FILE="$SCRIPT_DIR/../REopt_API/keys.py"

# split script-only flags from builder args
BUILDER_ARGS=()
DASHBOARD=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-dashboard) DASHBOARD=0; shift ;;
    --out) OUTDIR="$2"; shift 2 ;;
    --help|-h) sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) BUILDER_ARGS+=("$1"); shift ;;
  esac
done
# resolve OUTDIR to an absolute path
mkdir -p "$OUTDIR"; OUTDIR="$(cd "$OUTDIR" && pwd)"

echo "==> 1/3 Assembling scenario"
python3 "$SCRIPT_DIR/assemble_scenario.py" "${BUILDER_ARGS[@]}" --out "$OUTDIR"

# API key for PVWatts (PV production factor); Wind uses our local series
APIKEY="$(grep developer_nrel_gov_key "$KEYS_FILE" | head -1 | sed "s/.*=\s*'\(.*\)'.*/\1/")"

echo "==> 2/3 Solving on warm Julia server ($JULIA_URL)"
python3 "$SCRIPT_DIR/post_solve.py" "$OUTDIR" "$APIKEY" "$JULIA_URL"

if [[ "$DASHBOARD" == "1" ]]; then
  echo "==> 3/3 Building dashboard"
  python3 "$SCRIPT_DIR/build_dashboard.py" "$OUTDIR" || echo "(dashboard HTML step failed)"
  if command -v google-chrome >/dev/null 2>&1; then
    google-chrome --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
      --force-device-scale-factor=1.5 --window-size=1360,2400 --virtual-time-budget=9000 \
      --screenshot="$OUTDIR/dashboard.png" "file://$OUTDIR/dashboard.html" >/dev/null 2>&1 \
      && echo "    dashboard.png written" || echo "    (PNG render skipped)"
  fi
else
  echo "==> 3/3 Dashboard skipped"
fi

echo "==> Summary"
python3 - "$OUTDIR/results.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
def g(s,k):
    v=d.get(s,{}).get(k); return v if v is not None else 0.0
print("  status:", d.get("status"))
for t,lab in [("PV","PV kW"),("Wind","Wind kW"),("Generator","Gen kW"),("CHP","CHP kW")]:
    print(f"    {lab:10}: {g(t,'size_kw'):.0f}")
print(f"    Battery   : {g('ElectricStorage','size_kwh'):.0f} kWh")
print(f"  system_buildout_time_years: {g('Site','system_buildout_time_years')}")
fin=d.get('Financial',{})
print(f"  lcc: {fin.get('lcc')}   lcc_bau: {fin.get('lcc_bau')}")
print(f"  annual CO2 tonnes: {d.get('Site',{}).get('annual_emissions_tonnes_CO2')}")
PY
echo "Done. Artifacts in: $OUTDIR"
