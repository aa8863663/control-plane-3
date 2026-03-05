#!/bin/bash

# -----------------------------
# Full API Setup for Control-Plane
# -----------------------------
# This script will:
# 1. Create a backup of your current api_server.py
# 2. Replace it with a clean working version
# 3. Ensure templates exist (actuarial, costs, health, index, stats)
# 4. Install Python dependencies if needed
# 5. Give instructions to run the server

# Go to the project directory
cd ~/Desktop/control-plane-3 || exit

# Backup current api_server.py
if [ -f api_server.py ]; then
    cp api_server.py api_server.py.bak_$(date +%Y%m%d_%H%M%S)
    echo "[Backup] api_server.py saved."
fi

# Create a clean api_server.py
cat > api_server.py << 'EOF'
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import sqlite3
import subprocess
import os

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# -------------------------
# POST model for benchmarks
# -------------------------
class RunRequest(BaseModel):
    data: str
    api: str
    model: str
    temperature: float = 0.0
    runs: int = 1

# -------------------------
# Database connection
# -------------------------
DB_PATH = "controlplane.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# -------------------------
# Home page
# -------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# -------------------------
# Stats page
# -------------------------
@app.get("/api/stats", response_class=HTMLResponse)
def stats_page(request: Request):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name, value FROM stats")  # Replace with your real stats table
    rows = cur.fetchall()
    data = [dict(row) for row in rows] if rows else []
    conn.close()
    return templates.TemplateResponse("stats.html", {"request": request, "data": data})

# -------------------------
# Actuarial page
# -------------------------
@app.get("/api/actuarial", response_class=HTMLResponse)
def actuarial_page(request: Request):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM actuarial")  # Replace with your real actuarial table
    rows = cur.fetchall()
    data = [dict(row) for row in rows] if rows else []
    conn.close()
    return templates.TemplateResponse("actuarial.html", {"request": request, "data": data})

# -------------------------
# Costs page
# -------------------------
@app.get("/api/costs", response_class=HTMLResponse)
def costs_page(request: Request):
    conn = get_db()
    cur = conn.cursor()
    # Use SUM with COALESCE to handle missing columns
    cur.execute("""
        SELECT 
            COALESCE(SUM(total_tokens), 0) AS total_tokens,
            COALESCE(SUM(cost), 0) AS total_cost
        FROM results
    """)
    row = cur.fetchone()
    data = {"total_tokens": row["total_tokens"], "total_cost": row["total_cost"]} if row else {"total_tokens":0,"total_cost":0}
    conn.close()
    return templates.TemplateResponse("costs.html", {"request": request, "data": data})

# -------------------------
# Health page
# -------------------------
@app.get("/health", response_class=HTMLResponse)
def health_page(request: Request):
    data = {"status": "OK"}
    return templates.TemplateResponse("health.html", {"request": request, "data": data})

# -------------------------
# Run benchmark
# -------------------------
@app.post("/run")
def run_benchmark(request: RunRequest):
    command = [
        "python3",
        "llm_safety_platform.py",
        "--data", request.data,
        "--api", request.api,
        "--model", request.model,
        "--temperature", str(request.temperature),
        "--runs", str(request.runs),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    return {
        "success": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
EOF

echo "[Success] api_server.py replaced with clean version."

# -------------------------
# Ensure template files exist
# -------------------------
TEMPLATES=("index.html" "stats.html" "actuarial.html" "costs.html" "health.html")

for file in "${TEMPLATES[@]}"; do
    if [ ! -f templates/$file ]; then
        cat > templates/$file << EOF_HTML
<!DOCTYPE html>
<html>
<head>
  <title>${file%.*}</title>
</head>
<body>
  <h1>${file%.*}</h1>
  <pre>{{ data | tojson(indent=2) }}</pre>
  <p><a href="/">Back to Home</a></p>
</body>
</html>
EOF_HTML
        echo "[Template] Created templates/$file"
    fi
done

# -------------------------
# Install dependencies
# -------------------------
echo "[Setup] Installing dependencies..."
pip3 install fastapi uvicorn jinja2 pydantic sqlite3 --upgrade

echo ""
echo "-------------------------------------------------"
echo "✅ Full API setup complete!"
echo "Run server with:"
echo "python3 -m uvicorn api_server:app --reload"
echo "Open endpoints:"
echo "Home: http://127.0.0.1:8000/"
echo "Stats: http://127.0.0.1:8000/api/stats"
echo "Actuarial: http://127.0.0.1:8000/api/actuarial"
echo "Costs: http://127.0.0.1:8000/api/costs"
echo "Health: http://127.0.0.1:8000/health"
echo "Benchmark POST: http://127.0.0.1:8000/run"
echo "-------------------------------------------------"
