#!/usr/bin/env python3
import argparse, csv, os, sqlite3, sys
from datetime import datetime

DB_DEFAULT = os.getenv("CONTROLPLANE_DB", "controlplane.db")
PRICE_DEFAULT = float(os.getenv("PRICE_PER_1K", "0.01"))

def connect(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def fetchall(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()

def totals(conn):
    row = fetchall(conn, """
        SELECT
          COUNT(DISTINCT r.id) AS runs,
          COUNT(res.id)        AS results,
          COALESCE(SUM(res.total_tokens),0) AS tokens
        FROM runs r
        LEFT JOIN results res ON res.run_id = r.id
    """)[0]
    return int(row["runs"]), int(row["results"]), int(row["tokens"])

def by_temperature(conn):
    return fetchall(conn, """
        SELECT
          r.temperature AS temperature,
          COUNT(DISTINCT r.id) AS runs,
          COUNT(res.id) AS results,
          COALESCE(SUM(res.total_tokens),0) AS tokens,
          COALESCE(AVG(res.total_tokens),0) AS avg_tokens,
          COALESCE(SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END),0) AS pass,
          COALESCE(SUM(CASE WHEN res.outcome='SAFETY_HARD_STOP' THEN 1 ELSE 0 END),0) AS fail
        FROM runs r
        LEFT JOIN results res ON res.run_id = r.id
        GROUP BY r.temperature
        ORDER BY r.temperature
    """)

def by_run(conn, limit=50):
    return fetchall(conn, """
        SELECT
          r.id AS run_id,
          r.created_at AS created_at,
          r.temperature AS temperature,
          r.model AS model,
          COUNT(res.id) AS results,
          COALESCE(SUM(res.total_tokens),0) AS tokens
        FROM runs r
        LEFT JOIN results res ON res.run_id = r.id
        GROUP BY r.id
        ORDER BY r.created_at DESC
        LIMIT ?
    """, (limit,))

def cmd_cost(args):
    conn = connect(args.db)
    runs, results, tokens = totals(conn)
    total_cost = (tokens/1000.0) * args.price_per_1k

    bt = by_temperature(conn)
    br = by_run(conn, limit=args.limit_runs)

    print("\n=== TOTALS ===")
    print(f"DB: {args.db}")
    print(f"Runs: {runs}   Results: {results}   Tokens: {tokens}")
    print(f"Price per 1k tokens: {args.price_per_1k}")
    print(f"Estimated cost: {total_cost:.4f}\n")

    print("=== BY TEMPERATURE ===")
    print("temp   runs  results  pass  fail  tokens   avg_tokens   est_cost")
    for r in bt:
        tok = int(r["tokens"])
        est = (tok/1000.0) * args.price_per_1k
        print(f"{r['temperature']!s:<5}  {int(r['runs']):<4}  {int(r['results']):<7}  {int(r['pass']):<4}  {int(r['fail']):<4}  {tok:<7}  {float(r['avg_tokens']):>10.1f}   {est:>8.4f}")

    print(f"\n=== LATEST RUNS (up to {args.limit_runs}) ===")
    print("run_id        created_at                 temp  model        results  tokens  est_cost")
    for r in br:
        tok = int(r["tokens"])
        est = (tok/1000.0) * args.price_per_1k
        created = (r["created_at"] or "")[:26]
        model = (r["model"] or "None")[:10]
        print(f"{str(r['run_id'])[:12]:<12}  {created:<26}  {str(r['temperature']):<4}  {model:<10}  {int(r['results']):<7}  {tok:<6}  {est:>8.4f}")

    if args.export_csv:
        out = args.export_csv
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["generated_at", datetime.utcnow().isoformat()+"Z"])
            w.writerow(["db", args.db])
            w.writerow(["price_per_1k", args.price_per_1k])
            w.writerow([])
            w.writerow(["temp","runs","results","pass","fail","tokens","avg_tokens","est_cost"])
            for r in bt:
                tok = int(r["tokens"])
                w.writerow([
                    r["temperature"], int(r["runs"]), int(r["results"]), int(r["pass"]), int(r["fail"]),
                    tok, float(r["avg_tokens"]), (tok/1000.0)*args.price_per_1k
                ])
            w.writerow([])
            w.writerow(["run_id","created_at","temperature","model","results","tokens","est_cost"])
            for r in br:
                tok = int(r["tokens"])
                w.writerow([
                    r["run_id"], r["created_at"], r["temperature"], r["model"],
                    int(r["results"]), tok, (tok/1000.0)*args.price_per_1k
                ])
        print(f"\n✅ Wrote CSV: {out}")

    conn.close()

def cmd_pdf(args):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception as e:
        print("❌ reportlab not available:", e)
        sys.exit(1)

    conn = connect(args.db)
    runs, results, tokens = totals(conn)
    total_cost = (tokens/1000.0) * args.price_per_1k
    rows = by_temperature(conn)
    conn.close()

    c = canvas.Canvas(args.out, pagesize=letter)
    w, h = letter
    y = h - 60

    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, y, "Control-Plane Audit Report")
    y -= 24
    c.setFont("Helvetica", 10)
    c.drawString(72, y, f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    y -= 18
    c.drawString(72, y, f"Database: {args.db}")
    y -= 28

    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Summary")
    y -= 16
    c.setFont("Helvetica", 10)
    c.drawString(72, y, f"Runs: {runs}    Results: {results}")
    y -= 14
    c.drawString(72, y, f"Total tokens: {tokens}    Price/1k: {args.price_per_1k}    Est. cost: {total_cost:.4f}")
    y -= 26

    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "By Temperature")
    y -= 16

    c.setFont("Helvetica-Bold", 9)
    header = ["Temp","Runs","Results","Pass","Fail","Tokens","AvgTok","EstCost"]
    x = [72, 110, 150, 205, 240, 285, 350, 410]
    for i, htxt in enumerate(header):
        c.drawString(x[i], y, htxt)
    y -= 12
    c.setFont("Helvetica", 9)

    for r in rows:
        tok = int(r["tokens"])
        est = (tok/1000.0)*args.price_per_1k
        vals = [
            r["temperature"], int(r["runs"]), int(r["results"]), int(r["pass"]), int(r["fail"]),
            tok, f"{float(r['avg_tokens']):.1f}", f"{est:.4f}"
        ]
        for i, v in enumerate(vals):
            c.drawString(x[i], y, str(v))
        y -= 12
        if y < 80:
            c.showPage()
            y = h - 60
            c.setFont("Helvetica", 9)

    c.showPage()
    c.save()
    print(f"✅ Wrote PDF: {args.out}")

def cmd_api(args):
    # uvicorn reload requires an import string (module:app)
    # We pass db/price via env so the module-level app can read them.
    import subprocess, sys

    env = os.environ.copy()
    env["CONTROLPLANE_DB"] = args.db
    env["PRICE_PER_1K"] = str(args.price_per_1k)

    cmd = [sys.executable, "-m", "uvicorn", "finishline:app", "--host", args.host, "--port", str(args.port)]
    if args.reload:
        cmd.append("--reload")

    subprocess.run(cmd, env=env, check=True)

def main():
    ap = argparse.ArgumentParser(prog="finishline.py", description="One-file finish line: cost + CSV + PDF + API")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_cost = sub.add_parser("cost", help="Print cost/token stats (+ optional CSV)")
    p_cost.add_argument("--db", default=DB_DEFAULT)
    p_cost.add_argument("--price-per-1k", type=float, default=PRICE_DEFAULT)
    p_cost.add_argument("--export-csv", default="", help="write CSV to this path (optional)")
    p_cost.add_argument("--limit-runs", type=int, default=50)
    p_cost.set_defaults(func=cmd_cost)

    p_pdf = sub.add_parser("pdf", help="Generate audit PDF")
    p_pdf.add_argument("--db", default=DB_DEFAULT)
    p_pdf.add_argument("--out", default="audit_report.pdf")
    p_pdf.add_argument("--price-per-1k", type=float, default=PRICE_DEFAULT)
    p_pdf.set_defaults(func=cmd_pdf)

    p_api = sub.add_parser("api", help="Run API server (/health /stats /costs)")
    p_api.add_argument("--db", default=DB_DEFAULT)
    p_api.add_argument("--price-per-1k", type=float, default=PRICE_DEFAULT)
    p_api.add_argument("--host", default="127.0.0.1")
    p_api.add_argument("--port", type=int, default=8000)
    p_api.add_argument("--reload", action="store_true")
    p_api.set_defaults(func=cmd_api)

    args = ap.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
