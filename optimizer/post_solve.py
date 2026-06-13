#!/usr/bin/env python3
"""POST a scenario to the warm Julia REopt server (port 8081) and save results.

Usage: python3 post_solve.py <output_dir> <api_key> [julia_url]

Using the already-running warm Julia process avoids the multi-minute JIT compilation
that a fresh `julia` process pays on every run, so solves finish in well under a minute.
"""
import json
import sys
import time
import urllib.request
import urllib.error

outdir = sys.argv[1]
api_key = sys.argv[2] if len(sys.argv) > 2 else ""
url = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:8081/reopt"

d = json.load(open(f"{outdir}/scenario.json"))
if api_key:
    d["api_key"] = api_key  # consumed by the endpoint to set PVWatts key

body = json.dumps(d).encode()
req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})

t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=900) as r:
        resp = json.load(r)
except urllib.error.HTTPError as e:
    detail = e.read().decode(errors="replace")
    try:
        body = json.loads(detail)
        res = body.get("results", {})
        json.dump(res, open(f"{outdir}/results.json", "w"))  # save for inspection
        msgs = res.get("Messages", {})
        print(f"Julia /reopt HTTP {e.code} | status: {res.get('status')}")
        print("  errors:", json.dumps(msgs.get("errors", []))[:1200])
        print("  warnings:", json.dumps(msgs.get("warnings", []))[:500])
    except Exception:
        print(f"Julia /reopt HTTP {e.code}: {detail[:1200]}")
    sys.exit(1)
except urllib.error.URLError as e:
    print(f"Could not reach Julia server at {url}: {e}\n"
          "Is the julia_api container up? (docker ps)")
    sys.exit(1)

results = resp.get("results", resp)
json.dump(results, open(f"{outdir}/results.json", "w"))
print(f"  solved in {time.time()-t0:.1f}s  | status: {results.get('status')}"
      f"  | reopt {resp.get('reopt_version','?')}")
