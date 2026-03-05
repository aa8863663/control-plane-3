#!/bin/bash
echo "========================================="
echo "CONTROL-PLANE 3 DASHBOARD SETUP"
echo "========================================="

# Ensure templates folder exists
mkdir -p templates

# Stats page
cat <<'HTML' > templates/stats.html
<!DOCTYPE html>
<html>
<head>
<title>Stats Dashboard</title>
<style>
body { font-family: Arial, sans-serif; margin: 20px; background:#f2f2f2; }
h1 { color:#2c3e50; }
.card { background:white; padding:20px; border-radius:10px; margin:10px 0; box-shadow:0 2px 5px rgba(0,0,0,0.1); }
</style>
</head>
<body>
<h1>Stats Dashboard</h1>
<div class="card">Total Runs: {{ total_runs }}</div>
<div class="card">Total Entries: {{ total_entries }}</div>
<div class="card">Total Breaches: {{ total_breaches }}</div>
<div class="card">Pass Rate: {{ pass_rate }}%</div>
</body>
</html>
HTML

# Health page
cat <<'HTML' > templates/health.html
<!DOCTYPE html>
<html>
<head>
<title>Health Check</title>
</head>
<body>
<h1>Server Health</h1>
<p>Status: {{ status }}</p>
</body>
</html>
HTML

# Actuarial page
cat <<'HTML' > templates/actuarial.html
<!DOCTYPE html>
<html>
<head>
<title>Actuarial Metrics</title>
</head>
<body>
<h1>Actuarial Metrics</h1>
<pre>{{ data | tojson(indent=2) }}</pre>
</body>
</html>
HTML

# Costs page
cat <<'HTML' > templates/costs.html
<!DOCTYPE html>
<html>
<head>
<title>Cost Metrics</title>
</head>
<body>
<h1>Cost Metrics</h1>
<div>Total Runs: {{ runs }}</div>
<div>Total Tokens: {{ tokens }}</div>
<div>Estimated Cost (USD): {{ estimated_cost_usd }}</div>
</body>
</html>
HTML

# Update api_server.py
cat <<'PY' > api_server.py
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import sqlite3, json
from pathlib import Path

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/stats", response_class=HTMLResponse)
def stats(request: Request):
    conn = sqlite3.connect("controlplane.db")
    cur = conn.cursor()
    total_runs = cur.execute("SELECT COUNT(DISTINCT run_id) FROM results").fetchone()[0]
    total_entries = cur.execute("SELECT COUNT(*) FROM results").fetchone()[0]
    total_breaches = cur.execute("SELECT COUNT(*) FROM results WHERE outcome LIKE '%BREACH%'").fetchone()[0]
    conn.close()
    pass_rate = round((total_entries - total_breaches)/total_entries*100, 2) if total_entries else 0
    return templates.TemplateResponse("stats.html", {
        "request": request,
        "total_runs": total_runs,
        "total_entries": total_entries,
        "total_breaches": total_breaches,
        "pass_rate": pass_rate
    })

@app.get("/health", response_class=HTMLResponse)
def health(request: Request):
    return templates.TemplateResponse("health.html", {"request": request, "status": "ok"})

@app.get("/api/actuarial", response_class=HTMLResponse)
def actuarial(request: Request):
    p = Path("run_summary.json")
    data = json.loads(p.read_text()) if p.exists() else {"error": "run actuarial_metrics.py first"}
    return templates.TemplateResponse("actuarial.html", {"request": request, "data": data})

@app.get("/api/costs", response_class=HTMLResponse)
def costs(request: Request):
    conn = sqlite3.connect("controlplane.db")
    cur = conn.cursor()
    total_tokens = cur.execute("SELECT SUM(total_tokens) FROM results").fetchone()[0] or 0
    runs = cur.execute("SELECT COUNT(DISTINCT run_id) FROM results").fetchone()[0]
    conn.close()
    cost = round((total_tokens / 1000) * 0.01, 2)
    return templates.TemplateResponse("costs.html", {
        "request": request,
        "runs": runs,
        "tokens": total_tokens,
        "estimated_cost_usd": cost
    })
PY

chmod +x setup_dashboard.sh
echo "Setup complete. Run ./setup_dashboard.sh to apply and start server."
