#!/bin/bash
cd ~/Desktop/control-plane-3

# Create templates folder
mkdir -p templates

# Create api_server.py
cat > api_server.py << 'EOF'
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import sqlite3
import subprocess
import os

app = FastAPI()
templates = Jinja2Templates(directory="templates")
DB_PATH = "controlplane.db"

def init_db():
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            t1 INTEGER,
            t2 INTEGER,
            t3 INTEGER,
            total_tokens INTEGER,
            cost REAL
        )
        """)
        conn.commit()
        conn.close()

init_db()

class RunRequest(BaseModel):
    data: str
    api: str
    model: str
    temperature: float = 0.0
    runs: int = 1

@app.get("/", response_class=HTMLResponse)
def home_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/actuarial", response_class=HTMLResponse)
def actuarial_page(request: Request):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM results")
        rows = cur.fetchall()
        data = [dict(row) for row in rows] if rows else []
    except:
        data = []
    finally:
        conn.close()
    return templates.TemplateResponse("actuarial.html", {"request": request, "data": data})

@app.get("/api/costs", response_class=HTMLResponse)
def costs_page(request: Request):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("SELECT SUM(total_tokens), SUM(cost) FROM results")
        row = cur.fetchone()
        total_tokens = row[0] if row[0] else 0
        total_cost = row[1] if row[1] else 0
    except:
        total_tokens = 0
        total_cost = 0
    finally:
        conn.close()
    data = {"total_tokens": total_tokens, "total_cost": total_cost}
    return templates.TemplateResponse("costs.html", {"request": request, "data": data})

@app.get("/stats", response_class=HTMLResponse)
def stats_page(request: Request):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM results")
        rows = cur.fetchall()
        data = [dict(row) for row in rows] if rows else []
    except:
        data = []
    finally:
        conn.close()
    return templates.TemplateResponse("stats.html", {"request": request, "data": data})

@app.get("/health", response_class=HTMLResponse)
def health_page(request: Request):
    data = {"status": "OK"}
    return templates.TemplateResponse("health.html", {"request": request, "data": data})

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

echo "✅ api_server.py created. Now add HTML templates manually or with another script."
