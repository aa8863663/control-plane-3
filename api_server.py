from fastapi import FastAPI, Request, Cookie, Form, Header
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import sqlite3, subprocess, os, csv, io, json
from typing import Optional
from auth import init_users_table, login_user, get_user_from_token, logout_token, create_user
from report_generator import generate_report
from api_keys import init_api_keys_table, create_api_key, validate_api_key, list_api_keys, revoke_api_key

init_users_table()
init_api_keys_table()

def create_default_admin():
    try:
        conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), "controlplane.db"))
        conn.row_factory = sqlite3.Row
        existing = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
        if not existing:
            import hashlib, secrets
            salt = secrets.token_hex(16)
            h = hashlib.sha256((salt + "admin123").encode()).hexdigest()
            pw = f"{salt}:{h}"
            conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ('admin', pw))
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"Admin init warning: {e}")

create_default_admin()

app = FastAPI(title="Control Plane 3", description="MTCP LLM Safety Benchmarking Platform")
templates = Jinja2Templates(directory="templates")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "controlplane.db")
PROBES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probes_200.json")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def current_user(session=None):
    return get_user_from_token(session) if session else None

def get_auth(session: Optional[str] = None, x_api_key: Optional[str] = None):
    if session:
        u = get_user_from_token(session)
        if u: return u
    if x_api_key:
        u = validate_api_key(x_api_key)
        if u: return u
    return None

class RunRequest(BaseModel):
    data: str; api: str; model: str; temperature: float = 0.0; runs: int = 1

# ── Auth ─────────────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    token = login_user(username, password)
    if token:
        resp = RedirectResponse("/", status_code=302)
        resp.set_cookie("session", token, httponly=True, max_age=86400)
        return resp
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password."})

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None, "success": None})

@app.post("/register")
def register_post(request: Request, username: str = Form(...), password: str = Form(...), confirm: str = Form(...)):
    if password != confirm:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Passwords do not match.", "success": None})
    if len(password) < 6:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Password must be at least 6 characters.", "success": None})
    if create_user(username, password):
        return templates.TemplateResponse("register.html", {"request": request, "error": None, "success": "Account created! You can now log in."})
    return templates.TemplateResponse("register.html", {"request": request, "error": "Username already taken.", "success": None})

@app.get("/logout")
def logout(session: Optional[str] = Cookie(default=None)):
    logout_token(session)
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("session")
    return resp

# ── Admin ─────────────────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, session: Optional[str] = Cookie(default=None), new_key: str = None):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    conn = get_db()
    users = [dict(r) for r in conn.execute("SELECT id, username, created_at, is_active FROM users ORDER BY id").fetchall()]
    conn.close()
    keys = list_api_keys(user["id"])
    return templates.TemplateResponse("admin.html", {"request": request, "user": user, "users": users, "api_keys": keys, "new_key": request.query_params.get("new_key")})

@app.post("/admin/create-key")
def admin_create_key(request: Request, session: Optional[str] = Cookie(default=None), label: str = Form("")):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    new_key = create_api_key(user["id"], label)
    return RedirectResponse(f"/admin?new_key={new_key}", status_code=302)

@app.post("/admin/revoke-key")
def admin_revoke_key(request: Request, session: Optional[str] = Cookie(default=None), key_id: int = Form(...)):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    revoke_api_key(key_id, user["id"])
    return RedirectResponse("/admin", status_code=302)

# ── Probe Editor ──────────────────────────────────────────────────────────────

@app.get("/probes", response_class=HTMLResponse)
def probe_editor(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    with open(PROBES_PATH) as f:
        probes = json.load(f)
    return templates.TemplateResponse("probe_editor.html", {"request": request, "user": user, "probes": probes, "success": None})

@app.post("/probes/add")
def probe_add(request: Request, session: Optional[str] = Cookie(default=None),
              probe_id: str = Form(...), vector: str = Form(...),
              turn_1: str = Form(...), turn_2_correction: str = Form(...), turn_3_correction: str = Form(...),
              constraint_type: str = Form(...), constraint_value: str = Form(...)):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    with open(PROBES_PATH) as f:
        probes = json.load(f)
    try:
        val = json.loads(constraint_value)
    except:
        val = constraint_value
    probes.append({"probe_id": probe_id, "vector": vector, "turn_1": turn_1,
                   "turn_2_correction": turn_2_correction, "turn_3_correction": turn_3_correction,
                   "constraints": {constraint_type: val}})
    with open(PROBES_PATH, "w") as f:
        json.dump(probes, f, indent=2)
    return templates.TemplateResponse("probe_editor.html", {"request": request, "user": user, "probes": probes, "success": f"Probe {probe_id} added successfully."})

@app.post("/probes/delete")
def probe_delete(request: Request, session: Optional[str] = Cookie(default=None), probe_id: str = Form(...)):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    with open(PROBES_PATH) as f:
        probes = json.load(f)
    probes = [p for p in probes if p["probe_id"] != probe_id]
    with open(PROBES_PATH, "w") as f:
        json.dump(probes, f, indent=2)
    return RedirectResponse("/probes", status_code=302)

# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def home(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.get("/run-benchmark", response_class=HTMLResponse)
def run_benchmark_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("run_benchmark.html", {"request": request, "user": user})

@app.get("/stats", response_class=HTMLResponse)
@app.get("/api/stats", response_class=HTMLResponse)
def stats_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT outcome, COUNT(*) as count FROM results GROUP BY outcome ORDER BY count DESC")
    outcome_rows = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT r.temperature, COUNT(DISTINCT r.id) as num_runs, COUNT(res.id) as total_results FROM runs r LEFT JOIN results res ON r.id=res.run_id GROUP BY r.temperature ORDER BY r.temperature")
    temp_rows = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT id, created_at, temperature, python_version FROM runs ORDER BY created_at DESC LIMIT 10")
    recent_runs = [dict(r) for r in cur.fetchall()]; conn.close()
    return templates.TemplateResponse("stats.html", {"request": request, "data": {"outcomes": outcome_rows, "by_temperature": temp_rows, "recent_runs": recent_runs}, "user": user})

@app.get("/api/actuarial", response_class=HTMLResponse)
def actuarial_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT r.temperature, COUNT(res.id) as total, SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END) as passed, SUM(CASE WHEN res.outcome='SAFETY_HARD_STOP' THEN 1 ELSE 0 END) as failed, AVG(res.recovery_latency) as avg_latency FROM runs r LEFT JOIN results res ON r.id=res.run_id GROUP BY r.temperature ORDER BY r.temperature")
    data = []
    for row in cur.fetchall():
        r = dict(row); total = r['total'] or 0; passed = r['passed'] or 0
        r['pass_rate'] = round((passed/total*100),1) if total>0 else 0.0
        r['avg_latency'] = round(r['avg_latency'],2) if r['avg_latency'] else None
        data.append(r)
    conn.close()
    return templates.TemplateResponse("actuarial.html", {"request": request, "data": data, "user": user})

@app.get("/api/costs", response_class=HTMLResponse)
def costs_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM results"); total_results = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM runs"); total_runs = cur.fetchone()[0]
    try:
        cur.execute("SELECT SUM(total_tokens) FROM results"); total_tokens = cur.fetchone()[0] or 0
        cur.execute("SELECT r.temperature, COUNT(res.id) as results, SUM(res.total_tokens) as total_tokens FROM runs r LEFT JOIN results res ON r.id=res.run_id GROUP BY r.temperature ORDER BY r.temperature")
        note = None
    except:
        total_tokens = 0
        cur.execute("SELECT r.temperature, COUNT(res.id) as results FROM runs r LEFT JOIN results res ON r.id=res.run_id GROUP BY r.temperature ORDER BY r.temperature")
        note = "Token columns not present in this schema version. Run new benchmarks to populate."
    breakdown = [dict(r) for r in cur.fetchall()]; conn.close()
    return templates.TemplateResponse("costs.html", {"request": request, "data": {"total_results": total_results, "total_runs": total_runs, "total_tokens": total_tokens, "breakdown": breakdown, "note": note}, "user": user})

@app.get("/api/compare", response_class=HTMLResponse)
def compare_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT r.model, r.temperature, COUNT(res.id) as total, SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END) as passed, SUM(CASE WHEN res.outcome='SAFETY_HARD_STOP' THEN 1 ELSE 0 END) as failed FROM runs r LEFT JOIN results res ON r.id=res.run_id GROUP BY r.model, r.temperature ORDER BY r.model, r.temperature")
    data = []
    for row in cur.fetchall():
        r = dict(row); total = r['total'] or 0; passed = r['passed'] or 0
        r['pass_rate'] = round((passed/total*100),1) if total>0 else 0.0
        data.append(r)
    conn.close()
    return templates.TemplateResponse("compare.html", {"request": request, "data": data, "user": user})

@app.get("/health", response_class=HTMLResponse)
def health_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM runs"); run_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM results"); result_count = cur.fetchone()[0]
        conn.close(); db_status = "OK"
    except Exception as e:
        db_status = f"ERROR: {e}"; run_count = 0; result_count = 0
    return templates.TemplateResponse("health.html", {"request": request, "data": {"status": "OK" if db_status=="OK" else "DEGRADED", "db_status": db_status, "run_count": run_count, "result_count": result_count}, "user": user})

# ── API (session or API key) ──────────────────────────────────────────────────

@app.get("/api/runs")
def api_runs(session: Optional[str] = Cookie(default=None), x_api_key: Optional[str] = Header(default=None)):
    if not get_auth(session, x_api_key): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM runs ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]; conn.close(); return rows

@app.get("/api/results")
def api_results(limit: int = 50, session: Optional[str] = Cookie(default=None), x_api_key: Optional[str] = Header(default=None)):
    if not get_auth(session, x_api_key): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM results ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]; conn.close(); return rows

@app.get("/api/export-csv")
def export_csv(session: Optional[str] = Cookie(default=None), x_api_key: Optional[str] = Header(default=None)):
    if not get_auth(session, x_api_key): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT res.id, r.model, r.temperature, r.created_at as run_date,
               res.probe_id, res.outcome, res.recovery_latency, res.t1, res.t2, res.t3
        FROM results res JOIN runs r ON res.run_id=r.id ORDER BY res.created_at DESC
    """)
    rows = cur.fetchall(); conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id","model","temperature","run_date","probe_id","outcome","recovery_latency","t1","t2","t3"])
    for row in rows:
        writer.writerow(list(row))
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=cp3_results.csv"})

@app.post("/run")
def run_benchmark_api(req: RunRequest, session: Optional[str] = Cookie(default=None), x_api_key: Optional[str] = Header(default=None)):
    if not get_auth(session, x_api_key): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    result = subprocess.run(["python3", "llm_safety_platform.py", "--data", req.data, "--api", req.api,
                             "--model", req.model, "--temperature", str(req.temperature), "--runs", str(req.runs)],
                            capture_output=True, text=True)
    return {"success": result.returncode==0, "stdout": result.stdout, "stderr": result.stderr}

@app.get("/api/export-report")
def export_report(session: Optional[str] = Cookie(default=None), x_api_key: Optional[str] = Header(default=None)):
    if not get_auth(session, x_api_key): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    path = generate_report("/tmp/cp3_report.pdf")
    if path.endswith(".pdf"): return FileResponse(path, media_type="application/pdf", filename="control-plane-3-report.pdf")
    return FileResponse(path, media_type="text/html", filename="control-plane-3-report.html")
