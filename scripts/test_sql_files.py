#!/usr/bin/env python3
"""Runs every SELECT in src/sql/*.sql against the demo schema (UPDATEs are skipped).
Usage: python3 scripts/test_sql_files.py <profile> <warehouse_id> <catalog> <schema>"""
import json, os, re, subprocess, sys, pathlib
profile, wh, cat, sch = sys.argv[1:5]
root = pathlib.Path(__file__).resolve().parents[1] / "src" / "sql"
names = r"\b(v_[a-z_]+|forecast_assumptions|forecast_scenarios|dim_[a-z_]+)\b"
stmts = []
for f in sorted(root.glob("*.sql")):
    body = "\n".join(l for l in f.read_text().splitlines() if not l.strip().startswith("--"))
    for s in [x.strip() for x in body.split(";") if x.strip()]:
        if s.upper().startswith(("UPDATE", "INSERT", "DELETE")):
            continue
        s = re.sub(r"(FROM|JOIN)\s+" + names, lambda m: f"{m.group(1)} `{cat}`.`{sch}`.{m.group(2)}", s)
        s = re.sub(r"TABLE\(SELECT (.*?) FROM " + names, lambda m: f"TABLE(SELECT {m.group(1)} FROM `{cat}`.`{sch}`.{m.group(2)}", s)
        stmts.append((f.name, s.replace(":p_net_usd_per_dbu", f"(SELECT srti_net_price_with_addon FROM `{cat}`.`{sch}`.v_price)")))
out = subprocess.run(["databricks", "experimental", "aitools", "tools", "query", "--output", "json", "--profile", profile]
                     + [s for _, s in stmts], capture_output=True, text=True, env={**os.environ, "DATABRICKS_WAREHOUSE_ID": wh})
bad = 0
for (fn, _), r in zip(stmts, json.loads(out.stdout)):
    ok = r["state"] == "SUCCEEDED" and (r.get("rows") or [])
    bad += not ok
    print(f"{'OK ' if ok else 'ERR'} {fn:32s} rows={len(r.get('rows') or []):4d} {str(r.get('error') or '')[:300]}")
sys.exit(1 if bad else 0)
