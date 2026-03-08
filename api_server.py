from fastapi import FastAPI, Request, Cookie, Form, Header
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import psycopg2
import psycopg2.extras
import os, subprocess, os, csv, io, json, datetime
from typing import Optional
from auth import init_users_table, login_user, get_user_from_token, logout_token, create_user
from report_generator import generate_report
from api_keys import init_api_keys_table, create_api_key, validate_api_key, list_api_keys, revoke_api_key

init_users_table()
init_api_keys_table()

def create_default_admin():
    return  # now handled by init_users_table

create_default_admin()

app = FastAPI(title="Control Plane 3", description="MTCP LLM Safety Benchmarking Platform")
templates = Jinja2Templates(directory="templates")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "controlplane.db")
PROBES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probes_200.json")

def get_db():
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(os.environ.get("DATABASE_URL", ""))
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn

def current_user(session=None):
    return get_user_from_token(session) if session else None

def is_admin_user(session=None):
    """Returns True only if the logged-in user has is_admin=True in the database."""
    if not session: return False
    user = get_user_from_token(session)
    if not user: return False
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT is_admin FROM users WHERE username=%s", (user,))
        row = cur.fetchone()
        conn.close()
        return bool(row and row['is_admin'])
    except:
        return False

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

# ── Insurance-grade metrics helper ───────────────────────────────────────────

def compute_insurance_metrics(cur, model=None, temperature=None):
    """
    Computes breach_rate, enforcement_reliability, mean_turns_to_breach,
    expected_breaches_per_1m for a given model (and optionally temperature).
    """
    where = []
    params = []
    if model:
        where.append("r.model = %s")
        params.append(model)
    if temperature is not None:
        where.append("r.temperature = %s")
        params.append(temperature)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    cur.execute(f"""
        SELECT
            COUNT(res.id) as total,
            SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN res.outcome='SAFETY_HARD_STOP' THEN 1 ELSE 0 END) as hard_stops
        FROM runs r LEFT JOIN results res ON r.id=res.run_id
        {where_sql}
    """, params)
    row = dict(cur.fetchone())
    total = row['total'] or 0
    passed = row['passed'] or 0
    hard_stops = row['hard_stops'] or 0

    # Breach rate: % of probes that hard-stopped (persistent violation)
    breach_rate = round((hard_stops / total * 100), 1) if total > 0 else 0.0

    # Enforcement reliability: % that either completed or hard-stopped (system responded correctly)
    enforcement_reliability = round(((passed + hard_stops) / total * 100), 1) if total > 0 else 0.0

    # Mean turns to breach: uses recovery_latency as proxy for turn at which breach occurred
    and_or = "AND" if where_sql else "WHERE"
    cur.execute(f"""
        SELECT AVG(res.recovery_latency::numeric)
        FROM runs r LEFT JOIN results res ON r.id=res.run_id
        {where_sql} {and_or} res.outcome='SAFETY_HARD_STOP'
        AND res.recovery_latency IS NOT NULL AND res.recovery_latency::numeric > 0
    """, params)
    mtb_row = cur.fetchone()
    mtb_val = list(mtb_row.values())[0] if mtb_row else None
    mean_turns_to_breach = round(float(mtb_val), 1) if mtb_val else None

    # Expected breaches per 1M tokens (actuarial projection, ~500 tokens per probe)
    expected_breaches_per_1m = int(round((breach_rate / 100) * (1_000_000 / 500), 0)) if breach_rate else 0

    return {
        'breach_rate': breach_rate,
        'enforcement_reliability': enforcement_reliability,
        'mean_turns_to_breach': mean_turns_to_breach,
        'expected_breaches_per_1m': expected_breaches_per_1m,
    }

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
    cur = conn.cursor()
    cur.execute("SELECT id, username, created_at, is_active FROM users ORDER BY id")
    users = [dict(r) for r in cur.fetchall()]
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
    if not is_admin_user(session): return RedirectResponse("/", status_code=302)
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
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM results")
    total_results = list(cur.fetchone().values())[0]
    cur.execute("SELECT COUNT(DISTINCT model) FROM runs")
    total_models = list(cur.fetchone().values())[0]
    cur.execute("SELECT COUNT(*) FROM runs")
    total_runs = list(cur.fetchone().values())[0]
    cur.execute("SELECT r.model, ROUND((100.0 * SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END) / NULLIF(COUNT(res.id),0))::numeric, 1) as pass_rate FROM runs r LEFT JOIN results res ON r.id=res.run_id WHERE r.model IS NOT NULL AND r.model != ''  GROUP BY r.model ORDER BY pass_rate DESC")
    model_rows = []
    for row in cur.fetchall():
        d = dict(row); pr = float(d.get('pass_rate') or 0)
        if pr >= 95: d['grade'] = 'A+'
        elif pr >= 90: d['grade'] = 'A'
        elif pr >= 80: d['grade'] = 'B'
        elif pr >= 70: d['grade'] = 'C'
        elif pr >= 60: d['grade'] = 'D'
        else: d['grade'] = 'F'
        model_rows.append(d)
    conn.close()
    best_grade = model_rows[0]['grade'] if model_rows else '?'
    return templates.TemplateResponse("index.html", {"request": request, "user": user, "total_results": total_results, "total_models": total_models, "total_runs": total_runs, "model_rows": model_rows, "best_grade": best_grade})

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
    recent_runs = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) FROM runs")
    total_runs = list(cur.fetchone().values())[0]
    cur.execute("SELECT COUNT(*) FROM results")
    total_results = list(cur.fetchone().values())[0]
    cur.execute("SELECT COUNT(*) FROM results WHERE outcome='SAFETY_HARD_STOP'")
    hard_stops = list(cur.fetchone().values())[0]
    # Model pass rates for bar chart (main runs only)
    cur.execute("""
        SELECT r.model, ROUND(100.0*SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END)/COUNT(*),1) as pass_rate
        FROM runs r JOIN results res ON r.id=res.run_id
        WHERE (r.dataset IS NULL OR r.dataset='main')
        GROUP BY r.model ORDER BY pass_rate DESC
    """)
    model_rows = [{"model": row["model"], "pass_rate": float(row["pass_rate"])} for row in cur.fetchall()]

    # Control probe results
    cur.execute("""
        SELECT r.model, SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END) as passed,
               COUNT(*) as total,
               ROUND(100.0*SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END)/COUNT(*),1) as pass_rate
        FROM runs r JOIN results res ON r.id=res.run_id
        WHERE r.dataset='ctrl'
        GROUP BY r.model ORDER BY pass_rate DESC
    """)
    ctrl_rows = [{"model": row["model"], "passed": row["passed"], "total": row["total"], "pass_rate": float(row["pass_rate"])} for row in cur.fetchall()]

    conn.close()
    return templates.TemplateResponse("stats.html", {"request": request, "data": {"outcomes": outcome_rows, "by_temperature": temp_rows, "recent_runs": recent_runs, "total_runs": total_runs, "total_results": total_results, "hard_stops": hard_stops}, "user": user, "model_rows": model_rows, "ctrl_rows": ctrl_rows})

@app.get("/api/actuarial", response_class=HTMLResponse)
def actuarial_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    if not is_admin_user(session): return RedirectResponse("/", status_code=302)
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT r.temperature, COUNT(res.id) as total, SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END) as passed, SUM(CASE WHEN res.outcome='SAFETY_HARD_STOP' THEN 1 ELSE 0 END) as failed, AVG(CAST(res.recovery_latency AS FLOAT)) as avg_latency FROM runs r LEFT JOIN results res ON r.id=res.run_id WHERE (r.dataset IS NULL OR r.dataset='main') GROUP BY r.temperature ORDER BY r.temperature")
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
    if not is_admin_user(session): return RedirectResponse("/", status_code=302)
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM results"); total_results = list(cur.fetchone().values())[0]
    cur.execute("SELECT COUNT(*) FROM runs"); total_runs = list(cur.fetchone().values())[0]
    cur.execute("""
        SELECT r.model, r.temperature, COUNT(res.id) as results,
               SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END) as passed,
               SUM(CASE WHEN res.outcome='SAFETY_HARD_STOP' THEN 1 ELSE 0 END) as hard_stops
        FROM runs r LEFT JOIN results res ON r.id=res.run_id
        GROUP BY r.model, r.temperature ORDER BY r.model, r.temperature
    """)
    breakdown = [dict(r) for r in cur.fetchall()]
    conn.close()
    note = "Token tracking not available for imported benchmark runs. Showing result counts only."
    return templates.TemplateResponse("costs.html", {
        "request": request, "user": user,
        "data": {"total_results": total_results, "total_runs": total_runs,
                 "total_tokens": "N/A", "breakdown": breakdown, "note": note}
    })

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
    if not is_admin_user(session): return RedirectResponse("/", status_code=302)
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM runs"); run_count = list(cur.fetchone().values())[0]
        cur.execute("SELECT COUNT(*) FROM results"); result_count = list(cur.fetchone().values())[0]
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
    cur.execute("SELECT * FROM results ORDER BY created_at DESC LIMIT %s", (limit,))
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


@app.get("/ctrl-probes", response_class=HTMLResponse)
def ctrl_probes_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT r.model,
               SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END) as passed,
               COUNT(*) as total,
               ROUND(100.0*SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END)/COUNT(*),1) as pass_rate
        FROM runs r JOIN results res ON r.id=res.run_id
        WHERE r.dataset='ctrl'
        GROUP BY r.model ORDER BY pass_rate DESC
    """)
    ctrl_rows = [{"model": row["model"], "passed": row["passed"], "total": row["total"], "pass_rate": float(row["pass_rate"])} for row in cur.fetchall()]

    # Get main benchmark avg for comparison
    cur.execute("""
        SELECT r.model, ROUND(100.0*SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END)/COUNT(*),1) as pass_rate
        FROM runs r JOIN results res ON r.id=res.run_id
        WHERE r.dataset IS NULL OR r.dataset='main'
        GROUP BY r.model
    """)
    main_rates = {row["model"]: float(row["pass_rate"]) for row in cur.fetchall()}
    for row in ctrl_rows:
        row["main_pass_rate"] = main_rates.get(row["model"], "N/A")

    conn.close()
    return templates.TemplateResponse("ctrl_probes.html", {"request": request, "user": user, "ctrl_rows": ctrl_rows})

@app.get("/landing", response_class=HTMLResponse)
def landing_page(request: Request):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM results")
    total_results = list(cur.fetchone().values())[0]
    cur.execute("SELECT COUNT(DISTINCT model) FROM runs WHERE model IS NOT NULL AND model != ''")
    total_models = list(cur.fetchone().values())[0]
    cur.execute("""SELECT r.model, ROUND((100.0 * SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END) / NULLIF(COUNT(res.id),0))::numeric, 1) as pass_rate FROM runs r LEFT JOIN results res ON r.id=res.run_id WHERE r.model IS NOT NULL AND r.model != '' GROUP BY r.model ORDER BY pass_rate DESC""")
    model_rows = []
    for row in cur.fetchall():
        d = dict(row); pr = float(d.get('pass_rate') or 0)
        if pr >= 95: d['grade'] = 'A+'
        elif pr >= 90: d['grade'] = 'A'
        elif pr >= 80: d['grade'] = 'B'
        elif pr >= 70: d['grade'] = 'C'
        elif pr >= 60: d['grade'] = 'D'
        else: d['grade'] = 'F'
        model_rows.append(d)
    cur.execute("SELECT COUNT(*) FROM runs WHERE dataset IS NULL OR dataset='main'")
    _row = cur.fetchone(); total_runs = list(_row.values())[0] if _row else 0
    rates = [float(r['pass_rate']) for r in model_rows if r.get('pass_rate')]
    pass_range = f"{min(rates):.1f}%–{max(rates):.1f}%" if rates else 'N/A'
    conn.close()
    best_grade = model_rows[0]['grade'] if model_rows else '?'
    top_model = model_rows[0]['model'] if model_rows else '?'
    top_score = model_rows[0]['pass_rate'] if model_rows else 0
    return templates.TemplateResponse("landing.html", {"request": request, "total_results": total_results, "total_models": total_models, "total_runs": total_runs, "pass_range": pass_range, "model_rows": model_rows, "best_grade": best_grade, "top_model": top_model, "top_score": top_score})

# ── Public leaderboard (NO login required) ───────────────────────────────────

@app.get("/public-leaderboard", response_class=HTMLResponse)
def public_leaderboard(request: Request):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT r.model,
               COUNT(res.id) as total,
               SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END) as passed,
               SUM(CASE WHEN res.outcome='SAFETY_HARD_STOP' THEN 1 ELSE 0 END) as hard_stops,
               ROUND((100.0 * SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END) / NULLIF(COUNT(res.id),0))::numeric, 1) as pass_rate,
               ROUND(AVG(res.recovery_latency::numeric), 2) as avg_latency
        FROM runs r LEFT JOIN results res ON r.id=res.run_id
        WHERE r.model IS NOT NULL AND r.model != ''
        GROUP BY r.model ORDER BY pass_rate DESC
    """)
    rows = cur.fetchall()
    leaderboard = []
    for row in rows:
        d = dict(row)
        pr = float(d.get("pass_rate") or 0)
        if pr >= 95: d["grade"] = "A+"
        elif pr >= 90: d["grade"] = "A"
        elif pr >= 80: d["grade"] = "B"
        elif pr >= 70: d["grade"] = "C"
        elif pr >= 60: d["grade"] = "D"
        else: d["grade"] = "F"
        d.update(compute_insurance_metrics(cur, model=d['model']))
        leaderboard.append(d)
    conn.close()
    return templates.TemplateResponse("leaderboard.html", {
        "request": request, "user": None, "leaderboard": leaderboard
    })

# ── Private leaderboard (login required) ─────────────────────────────────────

@app.get("/leaderboard", response_class=HTMLResponse)
def leaderboard(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT r.model,
               COUNT(res.id) as total,
               SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END) as passed,
               SUM(CASE WHEN res.outcome='SAFETY_HARD_STOP' THEN 1 ELSE 0 END) as hard_stops,
               ROUND((100.0 * SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END) / NULLIF(COUNT(res.id),0))::numeric, 1) as pass_rate,
               ROUND(AVG(res.recovery_latency::numeric), 2) as avg_latency
        FROM runs r LEFT JOIN results res ON r.id=res.run_id
        WHERE r.model IS NOT NULL AND r.model != ''
        GROUP BY r.model ORDER BY pass_rate DESC
    """)
    rows = cur.fetchall()
    leaderboard = []
    for row in rows:
        d = dict(row)
        pr = float(d.get("pass_rate") or 0)
        if pr >= 95: d["grade"] = "A+"
        elif pr >= 90: d["grade"] = "A"
        elif pr >= 80: d["grade"] = "B"
        elif pr >= 70: d["grade"] = "C"
        elif pr >= 60: d["grade"] = "D"
        else: d["grade"] = "F"
        d.update(compute_insurance_metrics(cur, model=d['model']))
        leaderboard.append(d)
    conn.close()
    return templates.TemplateResponse("leaderboard.html", {
        "request": request, "user": user, "leaderboard": leaderboard
    })

# ── Certificate page ──────────────────────────────────────────────────────────

@app.get("/certificate", response_class=HTMLResponse)
def certificate(request: Request, session: Optional[str] = Cookie(default=None), model: str = ""):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT r.model, r.temperature,
               COUNT(res.id) as total,
               SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END) as passed,
               ROUND((100.0 * SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END) / NULLIF(COUNT(res.id),0))::numeric, 1) as pass_rate,
               SUM(CASE WHEN res.outcome='SAFETY_HARD_STOP' THEN 1 ELSE 0 END) as hard_stops
        FROM runs r LEFT JOIN results res ON r.id=res.run_id
        WHERE r.model IS NOT NULL AND r.model != ''
        GROUP BY r.model, r.temperature ORDER BY pass_rate DESC
    """)
    all_rows = []
    for row in cur.fetchall():
        d = dict(row)
        d.update(compute_insurance_metrics(cur, model=d['model'], temperature=d['temperature']))
        all_rows.append(d)

    # If specific model selected via ?model=name||temp
    selected_row = None
    selected_temp = None
    if model and '||' in model:
        parts = model.split('||')
        sel_model = parts[0]
        sel_temp = float(parts[1])
        for r in all_rows:
            if r['model'] == sel_model and float(r['temperature']) == sel_temp:
                selected_row = r
                selected_temp = sel_temp
                break

    conn.close()
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return templates.TemplateResponse("certificate.html", {
        "request": request,
        "user": user,
        "rows": all_rows,
        "selected_row": selected_row,
        "selected_model": model,
        "selected_temp": selected_temp,
        "now": now,
    })

@app.get("/certificate/download/{model}/{temperature}")
def certificate_download(model: str, temperature: str, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user: return RedirectResponse("/login", status_code=302)
    from certificate_pdf import generate_certificate_pdf
    path = generate_certificate_pdf(model=model, temperature=float(temperature))
    return FileResponse(path, media_type="application/pdf",
                        filename=f"MTCP_Certificate_{model}_T{temperature}.pdf")

@app.get("/settings/api-keys", response_class=HTMLResponse)
def api_keys_settings_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not is_admin_user(session):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("api_keys_settings.html", {
        "request": request,
        "current_user": user,
        "keys": {}
    })

@app.post("/api/user-keys/save")
async def save_provider_key(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user: return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    body = await request.json()
    provider, key = body.get("provider"), body.get("key")
    conn = get_db(); cur = conn.cursor()
    cur.execute(
        "INSERT INTO user_provider_keys (user_id, provider, key_value) VALUES (%s,%s,%s) ON CONFLICT(user_id, provider) DO UPDATE SET key_value=EXCLUDED.key_value",
        (user["id"], provider, key)
    )
    conn.commit(); conn.close()
    return JSONResponse({"ok": True})

@app.post("/api/user-keys/remove")
async def remove_provider_key(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user: return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    body = await request.json()
    provider = body.get("provider")
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM user_provider_keys WHERE user_id=%s AND provider=%s", (user["id"], provider))
    conn.commit(); conn.close()
    return JSONResponse({"ok": True})
