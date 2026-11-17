#!/usr/bin/env python3
"""Runs every dashboard dataset query against the deployed schema (qualifying bare view names).
Usage: python3 scripts/test_dashboard_queries.py <profile> <warehouse_id> <catalog> <schema> [dashboard.lvdash.json]
"""
import json, re, subprocess, sys, pathlib
profile, wh, cat, sch = sys.argv[1:5]
dash = sys.argv[5] if len(sys.argv) > 5 else "src/dashboards/genie_finops.lvdash.json"
d = json.loads((pathlib.Path(__file__).resolve().parents[1] / dash).read_text())
names = r"\b(v_[a-z_]+|forecast_assumptions|forecast_scenarios|dim_[a-z_]+|agg_[a-z_]+)\b"
sqls = []
for ds in d["datasets"]:
    sql = "".join(ds["queryLines"])
    sql = re.sub(r"(FROM|JOIN)\s+" + names, lambda m: f"{m.group(1)} `{cat}`.`{sch}`.{m.group(2)}", sql)
    sqls.append((ds["name"], sql))
out = subprocess.run(["databricks", "experimental", "aitools", "tools", "query", "--output", "json", "--profile", profile]
                     + [s for _, s in sqls], capture_output=True, text=True, env={**__import__("os").environ, "DATABRICKS_WAREHOUSE_ID": wh})
res = json.loads(out.stdout)
bad = 0
for (name, _), r in zip(sqls, res):
    rows = r.get("rows") or []
    ok = r["state"] == "SUCCEEDED" and len(rows) > 0
    bad += not ok
    print(f"{'OK ' if ok else 'ERR'} {name:20s} rows={len(rows):4d} {r.get('error') or ''} {json.dumps(rows[:1])[:160]}")
sys.exit(1 if bad else 0)
