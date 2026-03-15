import os, json, io, csv, subprocess
from typing import Optional
from datetime import datetime

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Request, Form, Cookie, Header
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI(title="Control Plane 3", description="MTCP LLM Safety Benchmarking Platform")
templates = Jinja2Templates(directory="templates")

PROBES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probes_200.json")
PROBES_CTRL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probes_control_20.json")

# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    conn = psycopg2.connect(os.environ.get("DATABASE_URL", ""))
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn

# ── Auth helpers ──────────────────────────────────────────────────────────────

import hashlib, secrets

def hash_password(p): return hashlib.sha256(p.encode()).hexdigest()

def get_user_from_token(token):
    if not token: return None
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT u.id, u.username, u.is_admin
            FROM sessions s JOIN users u ON s.user_id = u.id
            WHERE s.token = %s
        """, (token,))
        row = cur.fetchone(); conn.close()
        return dict(row) if row else None
    except: return None

def current_user(session=None):
    return get_user_from_token(session) if session else None

def is_admin(session=None):
    u = current_user(session)
    return bool(u and u.get("is_admin"))

def require_login(session):
    u = current_user(session)
    if not u: return None, RedirectResponse("/login", status_code=302)
    return u, None

def require_admin(session):
    u = current_user(session)
    if not u: return None, RedirectResponse("/login", status_code=302)
    if not u.get("is_admin"): return None, RedirectResponse("/", status_code=302)
    return u, None

def get_auth(session=None, x_api_key=None):
    if session:
        u = get_user_from_token(session)
        if u: return u
    if x_api_key:
        import hashlib
        hashed = hashlib.sha256(x_api_key.encode()).hexdigest()
        try:
            conn = get_db(); cur = conn.cursor()
            cur.execute("SELECT id FROM api_keys WHERE key_hash=%s", (hashed,))
            row = cur.fetchone(); conn.close()
            if row: return {"id": None, "username": "api", "is_admin": False}
        except: pass
    return None

# ── Grade helper ──────────────────────────────────────────────────────────────

def grade(pct):
    if pct >= 90: return "A"
    if pct >= 80: return "B"
    if pct >= 70: return "C"
    if pct >= 60: return "D"
    return "F"


# ── Leaderboard / Evidence Helpers ───────────────────────────────────────────

def get_leaderboard_data():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            ru.model,
            COALESCE(NULLIF(ru.provider, ''), 'Unknown') AS provider,
            ROUND(
                CAST(
                    100.0 * SUM(CASE WHEN r.outcome = 'COMPLETED' THEN 1 ELSE 0 END)
                    AS NUMERIC
                ) / NULLIF(COUNT(*), 0),
                1
            ) AS pass_rate,
            ROUND(
                CAST(
                    100.0 * SUM(CASE WHEN r.outcome = 'COMPLETED' AND ru.temperature = 0.0 THEN 1 ELSE 0 END)
                    AS NUMERIC
                ) / NULLIF(SUM(CASE WHEN ru.temperature = 0.0 THEN 1 ELSE 0 END), 0),
                1
            ) AS t0,
            ROUND(
                CAST(
                    100.0 * SUM(CASE WHEN r.outcome = 'COMPLETED' AND ru.temperature = 0.2 THEN 1 ELSE 0 END)
                    AS NUMERIC
                ) / NULLIF(SUM(CASE WHEN ru.temperature = 0.2 THEN 1 ELSE 0 END), 0),
                1
            ) AS t2,
            ROUND(
                CAST(
                    100.0 * SUM(CASE WHEN r.outcome = 'COMPLETED' AND ru.temperature = 0.5 THEN 1 ELSE 0 END)
                    AS NUMERIC
                ) / NULLIF(SUM(CASE WHEN ru.temperature = 0.5 THEN 1 ELSE 0 END), 0),
                1
            ) AS t5,
            ROUND(
                CAST(
                    100.0 * SUM(CASE WHEN r.outcome = 'COMPLETED' AND ru.temperature = 0.8 THEN 1 ELSE 0 END)
                    AS NUMERIC
                ) / NULLIF(SUM(CASE WHEN ru.temperature = 0.8 THEN 1 ELSE 0 END), 0),
                1
            ) AS t8
        FROM results r
        JOIN runs ru ON r.run_id = ru.id
        WHERE ru.dataset IS DISTINCT FROM 'ctrl'
        GROUP BY ru.model, COALESCE(NULLIF(ru.provider, ''), 'Unknown')
        ORDER BY pass_rate DESC, ru.model
    """)
    rows = cur.fetchall()

    cur.execute("""
        SELECT
            ru.model,
            ROUND(
                CAST(
                    100.0 * SUM(CASE WHEN r.outcome = 'COMPLETED' THEN 1 ELSE 0 END)
                    AS NUMERIC
                ) / NULLIF(COUNT(*), 0),
                1
            ) AS ctrl_rate
        FROM results r
        JOIN runs ru ON r.run_id = ru.id
        WHERE ru.dataset = 'ctrl'
        GROUP BY ru.model
    """)
    ctrl_map = {}
    for row in cur.fetchall():
        ctrl_map[row["model"]] = float(row["ctrl_rate"] or 0)

    conn.close()

    models = []
    for row in rows:
        main_rate = float(row["pass_rate"] or 0)
        ctrl_rate = float(ctrl_map.get(row["model"], 0))
        t0 = float(row["t0"] or 0)
        t2 = float(row["t2"] or 0)
        t5 = float(row["t5"] or 0)
        t8 = float(row["t8"] or 0)
        variance = round(max(t0, t2, t5, t8) - min(t0, t2, t5, t8), 1)
        models.append({
            "model": row["model"],
            "provider": row["provider"],
            "pass_rate": round(main_rate, 1),
            "ctrl_rate": round(ctrl_rate, 1),
            "drop": round(ctrl_rate - main_rate, 1),
            "t0": round(t0, 1),
            "t2": round(t2, 1),
            "t5": round(t5, 1),
            "t8": round(t8, 1),
            "variance": variance,
            "grade": grade(main_rate),
        })

    return models

# ── Startup ───────────────────────────────────────────────────────────────────

from scheduled_runs import start_scheduler

@app.on_event("startup")
def startup():
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, is_admin BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE, created_at TIMESTAMP DEFAULT NOW())""")
        cur.execute("""CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY, token TEXT UNIQUE NOT NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT NOW())""")
        cur.execute("""CREATE TABLE IF NOT EXISTS user_provider_keys (
            id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL,
            provider TEXT NOT NULL, key_value TEXT NOT NULL,
            UNIQUE(user_id, provider))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS api_keys (
            id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            key_hash TEXT NOT NULL, key_prefix TEXT NOT NULL,
            label TEXT, is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(), last_used TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS evaluation_requests (
            id SERIAL PRIMARY KEY,
            name TEXT,
            organisation TEXT,
            contact_email TEXT NOT NULL,
            model_name TEXT,
            provider TEXT,
            endpoint_details TEXT,
            evaluation_objective TEXT,
            notes TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        )""")
        # users table migrations
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS organisation TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS intended_use_case TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS notes TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_approved BOOLEAN DEFAULT FALSE")
        # evaluation_requests table migrations
        cur.execute("ALTER TABLE evaluation_requests ADD COLUMN IF NOT EXISTS name TEXT")
        cur.execute("ALTER TABLE evaluation_requests ADD COLUMN IF NOT EXISTS model_name TEXT")
        cur.execute("ALTER TABLE evaluation_requests ADD COLUMN IF NOT EXISTS provider TEXT")
        cur.execute("ALTER TABLE evaluation_requests ADD COLUMN IF NOT EXISTS endpoint_details TEXT")
        cur.execute("ALTER TABLE evaluation_requests ADD COLUMN IF NOT EXISTS evaluation_objective TEXT")
        conn.commit(); conn.close()
    except Exception as e:
        print(f"Startup warning: {e}")
    start_scheduler()

# ── PUBLIC ────────────────────────────────────────────────────────────────────

@app.get("/landing", response_class=HTMLResponse)
def landing_page(request: Request):
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT COUNT(DISTINCT id) AS n FROM runs")
        total_runs = cur.fetchone()['n'] or 0
        cur.execute("SELECT COUNT(DISTINCT model) AS n FROM runs")
        total_models = cur.fetchone()['n'] or 0
        cur.execute("SELECT COUNT(*) AS n FROM results")
        total_results = cur.fetchone()['n'] or 0
        cur.execute("""
            SELECT MIN(pct), MAX(pct) FROM (
                SELECT ROUND(CAST(100.0*SUM(CASE WHEN outcome='COMPLETED' THEN 1 ELSE 0 END) AS NUMERIC)
                       /NULLIF(COUNT(*),0),1) as pct
                FROM results r JOIN runs ru ON r.run_id=ru.id
                WHERE ru.dataset IS DISTINCT FROM 'ctrl'
                GROUP BY ru.model) sub""")
        row = cur.fetchone(); vals = list(row.values()) if row else [0,0]; mn = vals[0] or 0; mx = vals[1] or 0
        conn.close()
    except Exception as e:
        print(f"Landing error: {e}"); total_runs=0; total_models=0; total_results=0; mn=0; mx=0
    return templates.TemplateResponse("landing.html", {
        "request": request, "total_runs": total_runs,
        "total_models": total_models, "total_results": f"{total_results:,}",
        "pass_range": f"{mn}–{mx}%"})

@app.get("/public-leaderboard", response_class=HTMLResponse)
@app.get("/public", response_class=HTMLResponse)
def public_redirect():
    return RedirectResponse(url="/evidence/public-findings", status_code=301)

@app.get("/evidence/dashboard", response_class=HTMLResponse)
def evidence_dashboard_redirect():
    return RedirectResponse(url="/dashboard", status_code=301)

@app.get("/benchmark", response_class=HTMLResponse)
def benchmark_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/evidence/public-findings", status_code=301)

@app.get("/evidence/public-findings", response_class=HTMLResponse)
def evidence_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    models = get_leaderboard_data()
    return templates.TemplateResponse(
        "evidence.html",
        {
            "request": request,
            "user": user,
            "active": "evidence",
            "models": models
        }
    )

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT id, username, password_hash, is_admin FROM users WHERE username=%s AND is_active=TRUE", (username,))
        u = cur.fetchone(); conn.close()
        if u and u["password_hash"] == hash_password(password):
            token = secrets.token_urlsafe(32)
            conn2 = get_db(); cur2 = conn2.cursor()
            cur2.execute("INSERT INTO sessions (token, user_id) VALUES (%s,%s)", (token, u["id"]))
            conn2.commit(); conn2.close()
            resp = RedirectResponse("/", status_code=302)
            resp.set_cookie("session", token, httponly=True, samesite="lax")
            return resp
    except Exception as e:
        print(f"Login error: {e}")
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password."})

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None, "success": None})

# ── Email helper ──────────────────────────────────────────────────────────────

def send_email(subject: str, body: str):
    import smtplib
    from email.mime.text import MIMEText
    smtp_user = os.environ.get("ZOHO_SMTP_USER", "")
    smtp_pass = os.environ.get("ZOHO_SMTP_PASSWORD", "")
    notify_to = os.environ.get("NOTIFY_EMAIL", "admin@mtcp.live")
    if not smtp_user or not smtp_pass:
        print("Email not configured — skipping notification")
        return
    try:
        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = notify_to
        with smtplib.SMTP_SSL("smtp.zoho.eu", 465) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [notify_to], msg.as_string())
        print(f"Email sent: {subject}")
    except Exception as e:
        print(f"Email error: {e}")

@app.post("/register")
def register_post(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    organisation: str = Form(...),
    intended_use_case: str = Form(...),
    notes: str = Form(""),
    password: str = Form(...),
    confirm_password: str = Form(...)
):
    if password != confirm_password:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Passwords do not match.", "success": None})
    if len(password) < 6:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Password must be at least 6 characters.", "success": None})
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash, is_active, is_approved, full_name, email, organisation, intended_use_case, notes) VALUES (%s,%s,FALSE,FALSE,%s,%s,%s,%s,%s)",
            (email, hash_password(password), full_name, email, organisation, intended_use_case, notes)
        )
        conn.commit(); conn.close()
        send_email(
            subject=f"[MTCP] New registration: {full_name}",
            body=f"New registration request:\n\nName: {full_name}\nEmail: {email}\nOrganisation: {organisation}\nUse case: {intended_use_case}\nNotes: {notes or chr(8212)}\n\nApprove at: https://mtcp.live/admin"
        )
        return templates.TemplateResponse("register.html", {"request": request, "error": None, "success": "Account request submitted. You will be notified when approved."})
    except Exception as e:
        return templates.TemplateResponse("register.html", {"request": request, "error": "An account with this email already exists.", "success": None})

@app.get("/logout")
def logout(session: Optional[str] = Cookie(default=None)):
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE token=%s", (session,))
        conn.commit(); conn.close()
    except: pass
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("session")
    return resp

# ── AUTHENTICATED ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def homepage(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user:
        return RedirectResponse("/landing", status_code=302)
    models = get_leaderboard_data()
    stats = {"total_models": len(models)}
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "active": "platform",
            "models": models,
            "stats": stats
        }
    )

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, session: Optional[str] = Cookie(default=None)):
    user, redir = require_login(session)
    if redir:
        return redir
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM results WHERE run_id IN (SELECT id FROM runs WHERE dataset IS DISTINCT FROM 'ctrl')")
        total_results = cur.fetchone()['n'] or 0
        cur.execute("SELECT COUNT(DISTINCT id) AS n FROM runs WHERE dataset IS DISTINCT FROM 'ctrl'")
        total_runs = cur.fetchone()['n'] or 0
        cur.execute("SELECT COUNT(DISTINCT model) AS n FROM runs WHERE dataset IS DISTINCT FROM 'ctrl'")
        total_models = cur.fetchone()['n'] or 0
        cur.execute("""
            SELECT model, ROUND(CAST(100.0*SUM(CASE WHEN outcome='COMPLETED' THEN 1 ELSE 0 END) AS NUMERIC)/NULLIF(COUNT(*),0),1) as pass_rate
            FROM results r JOIN runs ru ON r.run_id=ru.id
            WHERE ru.dataset IS DISTINCT FROM 'ctrl'
            GROUP BY model ORDER BY pass_rate DESC""")
        rows = cur.fetchall(); conn.close()
        model_rows = [{"model": r["model"], "pass_rate": float(r["pass_rate"] or 0), "grade": grade(float(r["pass_rate"] or 0))} for r in rows]
        best_grade = model_rows[0]["grade"] if model_rows else "N/A"
    except Exception as e:
        print("Dashboard error: {0}".format(e))
        total_results = 0; total_runs = 0; total_models = 0; model_rows = []; best_grade = "N/A"
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user, "active": "dashboard",
        "total_results": total_results, "total_runs": total_runs,
        "total_models": total_models, "best_grade": best_grade, "model_rows": model_rows})

@app.get("/model-cards", response_class=HTMLResponse)
def model_cards(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    models = get_leaderboard_data()
    return templates.TemplateResponse(
        "model_cards.html",
        {
            "request": request,
            "user": user,
            "active": "models",
            "models": models
        }
    )

@app.get("/model-cards/{model_name}", response_class=HTMLResponse)
def model_card_single(request: Request, model_name: str, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    models = get_leaderboard_data()
    model = None
    for item in models:
        if item["model"] == model_name:
            model = item
            break
    if model is None:
        return HTMLResponse("Model not found", status_code=404)
    return templates.TemplateResponse(
        "model_card_single.html",
        {
            "request": request,
            "user": user,
            "active": "models",
            "model": model
        }
    )

@app.get("/methodology", response_class=HTMLResponse)
def methodology_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    return templates.TemplateResponse(
        "methodology.html",
        {
            "request": request,
            "user": user,
            "active": "methodology"
        }
    )

@app.get("/buyer-brief", response_class=HTMLResponse)
def buyer_brief_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    return templates.TemplateResponse("buyer_brief.html", {"request": request, "user": user, "active": "buyer-brief"})

@app.get("/request-evaluation", response_class=HTMLResponse)
def request_evaluation_get(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    return templates.TemplateResponse(
        "request_evaluation.html",
        {
            "request": request,
            "user": user,
            "active": "request",
            "success": False,
            "contact_email": None,
            "error": None
        }
    )

@app.post("/request-evaluation", response_class=HTMLResponse)
def request_evaluation_post(
    request: Request,
    name: str = Form(...),
    organisation: str = Form(...),
    contact_email: str = Form(...),
    model_name: str = Form(...),
    provider: str = Form(...),
    endpoint_details: str = Form(""),
    evaluation_objective: str = Form(...),
    notes: str = Form(""),
    session: Optional[str] = Cookie(default=None)
):
    user = current_user(session)
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO evaluation_requests
                (name, organisation, contact_email, model_name, provider, endpoint_details, evaluation_objective, notes, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (name, organisation, contact_email, model_name, provider, endpoint_details, evaluation_objective, notes, "pending")
        )
        conn.commit(); conn.close()
        send_email(
            subject=f"[MTCP] New evaluation request: {model_name}",
            body=f"New evaluation request:\n\nName: {name}\nOrganisation: {organisation}\nEmail: {contact_email}\nProvider: {provider}\nModel: {model_name}\nEndpoint: {endpoint_details or chr(8212)}\nObjective: {evaluation_objective}\nNotes: {notes or chr(8212)}\n\nReview at: https://mtcp.live/admin"
        )
        return templates.TemplateResponse(
            "request_evaluation.html",
            {
                "request": request,
                "user": user,
                "active": "request",
                "success": True,
                "contact_email": contact_email,
                "error": None
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "request_evaluation.html",
            {
                "request": request,
                "user": user,
                "active": "request",
                "success": False,
                "contact_email": None,
                "error": "Submission failed: {0}".format(str(e))
            }
        )

@app.get("/leaderboard", response_class=HTMLResponse)
def leaderboard(request: Request, session: Optional[str] = Cookie(default=None)):
    user, redir = require_login(session)
    if redir: return redir
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT ru.model, ru.temperature, ru.provider,
                   COUNT(*) as total,
                   SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) as passed,
                   SUM(CASE WHEN r.outcome='SAFETY_HARD_STOP' THEN 1 ELSE 0 END) as hard_stops,
                   ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) AS NUMERIC)/NULLIF(COUNT(*),0),1) as pass_rate
            FROM results r JOIN runs ru ON r.run_id=ru.id
            WHERE ru.dataset IS DISTINCT FROM 'ctrl'
            GROUP BY ru.model, ru.temperature, ru.provider ORDER BY pass_rate DESC""")
        rows = cur.fetchall(); conn.close()
        lb = []
        for r in rows:
            pr = float(r["pass_rate"] or 0)
            total = r["total"] or 0
            hard_stops = r["hard_stops"] or 0
            lb.append({"model": r["model"], "temperature": float(r["temperature"] or 0),
                       "provider": r["provider"] or "—",
                       "pass_rate": pr, "grade": grade(pr), "passed": r["passed"] or 0,
                       "hard_stops": hard_stops, "total": total,
                       "breach_rate": round(100.0*hard_stops/total,1) if total>0 else None})
    except Exception as e:
        print(f"Leaderboard error: {e}"); lb = []
    return templates.TemplateResponse("leaderboard.html", {
        "request": request, "user": user, "active": "leaderboard", "leaderboard": lb})

@app.get("/stats", response_class=HTMLResponse)
@app.get("/api/stats", response_class=HTMLResponse)
def stats_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user, redir = require_login(session)
    if redir: return redir
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT COUNT(DISTINCT id) AS n FROM runs WHERE dataset IS DISTINCT FROM 'ctrl'")
        total_runs = cur.fetchone()['n'] or 0
        cur.execute("SELECT COUNT(*) AS n FROM results WHERE run_id IN (SELECT id FROM runs WHERE dataset IS DISTINCT FROM 'ctrl')")
        total_results = cur.fetchone()['n'] or 0
        cur.execute("SELECT COUNT(*) AS n FROM results WHERE outcome='SAFETY_HARD_STOP' AND run_id IN (SELECT id FROM runs WHERE dataset IS DISTINCT FROM 'ctrl')")
        hard_stops = cur.fetchone()['n'] or 0
        cur.execute("""
            SELECT ru.model, ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) AS NUMERIC)/NULLIF(COUNT(*),0),1) as avg_pass_rate
            FROM results r JOIN runs ru ON r.run_id=ru.id
            WHERE ru.dataset IS DISTINCT FROM 'ctrl'
            GROUP BY ru.model ORDER BY avg_pass_rate DESC""")
        model_stats = [{"model": r["model"], "pass_rate": float(r["avg_pass_rate"] or 0)} for r in cur.fetchall()]
        cur.execute("""
            SELECT ru.model, COUNT(*) as total,
                   SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) as passed,
                   ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) AS NUMERIC)/NULLIF(COUNT(*),0),1) as pass_rate
            FROM results r JOIN runs ru ON r.run_id=ru.id
            WHERE ru.dataset='ctrl'
            GROUP BY ru.model ORDER BY pass_rate DESC""")
        ctrl_stats = [{"model": r["model"], "total": r["total"], "passed": r["passed"], "pass_rate": float(r["pass_rate"] or 0)} for r in cur.fetchall()]
        cur.execute("""
            SELECT ru.temperature,
                   ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) AS NUMERIC)/NULLIF(COUNT(*),0),1) as pass_rate,
                   COUNT(*) as total
            FROM results r JOIN runs ru ON r.run_id=ru.id
            WHERE ru.dataset IS DISTINCT FROM 'ctrl'
            GROUP BY ru.temperature ORDER BY ru.temperature""")
        temp_breakdown = [{"temperature": float(r["temperature"] or 0), "pass_rate": float(r["pass_rate"] or 0), "total": r["total"]} for r in cur.fetchall()]

        cur.execute("""
            SELECT ru.model,
                   ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) AS NUMERIC)/NULLIF(COUNT(*),0),1) as main_rate
            FROM results r JOIN runs ru ON r.run_id=ru.id
            WHERE ru.dataset IS DISTINCT FROM 'ctrl'
            GROUP BY ru.model""")
        main_map = {r["model"]: float(r["main_rate"] or 0) for r in cur.fetchall()}
        cur.execute("""
            SELECT ru.model,
                   ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) AS NUMERIC)/NULLIF(COUNT(*),0),1) as ctrl_rate
            FROM results r JOIN runs ru ON r.run_id=ru.id
            WHERE ru.dataset='ctrl'
            GROUP BY ru.model""")
        bis_stats = []
        for r in cur.fetchall():
            model = r["model"]
            ctrl = float(r["ctrl_rate"] or 0)
            main = main_map.get(model, 0)
            gap = round(main - ctrl, 1)
            bis = round(max(0, 100 - gap), 1)
            bis_stats.append({"model": model, "main_rate": main, "ctrl_rate": ctrl, "gap": gap, "bis": bis})
        bis_stats.sort(key=lambda x: x["bis"], reverse=True)

        cur.execute("""
            SELECT ru.model, ru.temperature,
                   ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) AS NUMERIC)/NULLIF(COUNT(*),0),1) as pass_rate
            FROM results r JOIN runs ru ON r.run_id=ru.id
            WHERE ru.dataset IS DISTINCT FROM 'ctrl'
            GROUP BY ru.model, ru.temperature ORDER BY ru.model, ru.temperature""")
        from collections import defaultdict
        import statistics
        temp_map = defaultdict(list)
        for r in cur.fetchall():
            temp_map[r["model"]].append(float(r["pass_rate"] or 0))
        tsi_stats = []
        for model, rates in temp_map.items():
            if len(rates) >= 2:
                stdev = round(statistics.stdev(rates), 1)
                tsi = round(max(0, 100 - stdev * 2), 1)
                tsi_stats.append({"model": model, "rates": rates, "stdev": stdev, "tsi": tsi,
                                   "min_rate": min(rates), "max_rate": max(rates)})
        tsi_stats.sort(key=lambda x: x["tsi"], reverse=True)

        conn.close()
    except Exception as e:
        print(f"Stats error: {e}"); total_runs=0; total_results=0; hard_stops=0; model_stats=[]; ctrl_stats=[]; temp_breakdown=[]; bis_stats=[]; tsi_stats=[]
    return templates.TemplateResponse("stats.html", {
        "request": request, "user": user, "active": "stats",
        "total_runs": total_runs, "total_results": total_results, "hard_stops": hard_stops,
        "model_stats": model_stats, "ctrl_stats": ctrl_stats, "temp_breakdown": temp_breakdown,
        "bis_stats": bis_stats, "tsi_stats": tsi_stats, "model_count": len(model_stats)})

@app.get("/certificate", response_class=HTMLResponse)
def certificate_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user, redir = require_login(session)
    if redir: return redir
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT ru.model, ru.temperature, COUNT(*) as total,
                   SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) as passed,
                   SUM(CASE WHEN r.outcome='SAFETY_HARD_STOP' THEN 1 ELSE 0 END) as hard_stops,
                   ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) AS NUMERIC)/NULLIF(COUNT(*),0),1) as pass_rate
            FROM results r JOIN runs ru ON r.run_id=ru.id
            WHERE ru.dataset IS DISTINCT FROM 'ctrl'
            GROUP BY ru.model, ru.temperature ORDER BY pass_rate DESC""")
        rows = cur.fetchall(); conn.close()
        cert_rows = [{"model": r["model"], "temperature": float(r["temperature"] or 0),
                      "pass_rate": float(r["pass_rate"] or 0), "grade": grade(float(r["pass_rate"] or 0)),
                      "passed": r["passed"] or 0, "hard_stops": r["hard_stops"] or 0, "total": r["total"] or 0} for r in rows]
    except Exception as e:
        print(f"Certificate error: {e}"); cert_rows=[]
    return templates.TemplateResponse("certificate.html", {
        "request": request, "user": user, "active": "certificate", "rows": cert_rows})

@app.get("/api/compare", response_class=HTMLResponse)
def compare_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user, redir = require_login(session)
    if redir: return redir
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT ru.model, ru.temperature,
                   ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) AS NUMERIC)/NULLIF(COUNT(*),0),1) as pass_rate
            FROM results r JOIN runs ru ON r.run_id=ru.id
            WHERE ru.dataset IS DISTINCT FROM 'ctrl'
            GROUP BY ru.model, ru.temperature ORDER BY ru.model, ru.temperature""")
        data = [{"model": r["model"], "temperature": float(r["temperature"] or 0), "pass_rate": float(r["pass_rate"] or 0)} for r in cur.fetchall()]
        conn.close()
    except Exception as e:
        print(f"Compare error: {e}"); data=[]
    return templates.TemplateResponse("compare.html", {
        "request": request, "user": user, "active": "compare", "compare_data": data})

@app.get("/run-evaluation", response_class=HTMLResponse)
def run_benchmark_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user, redir = require_login(session)
    if redir: return redir
    return templates.TemplateResponse("run_benchmark.html", {"request": request, "user": user, "active": "run"})

# ── ADMIN ─────────────────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, session: Optional[str] = Cookie(default=None), new_key: Optional[str] = None):
    user, redir = require_admin(session)
    if redir: return redir
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT id, username, is_admin, is_active, created_at FROM users ORDER BY id")
        users = [{"id": u["id"], "username": u["username"], "is_admin": u["is_admin"], "is_active": u["is_active"],
                  "created_at": u["created_at"].strftime('%Y-%m-%d') if u["created_at"] else "—"} for u in cur.fetchall()]
        pending_users = [u for u in users if not u["is_active"] and not u["is_admin"]]
        cur.execute("SELECT COUNT(DISTINCT id) AS n FROM runs")
        total_runs = cur.fetchone()['n'] or 0
        cur.execute("SELECT COUNT(*) AS n FROM results")
        total_results = cur.fetchone()['n'] or 0
        cur.execute("SELECT id, key_prefix, label, is_active, created_at, last_used FROM api_keys ORDER BY created_at DESC")
        api_keys = [{"id": k["id"], "key_prefix": k["key_prefix"], "label": k["label"],
                     "is_active": k["is_active"],
                     "created_at": k["created_at"].strftime('%Y-%m-%d') if k["created_at"] else "—",
                     "last_used": k["last_used"].strftime('%Y-%m-%d') if k["last_used"] else None} for k in cur.fetchall()]
        conn.close()
    except Exception as e:
        print(f"Admin error: {e}"); users=[]; total_runs=0; total_results=0; api_keys=[]
    return templates.TemplateResponse("admin.html", {
        "request": request, "user": user, "active": "admin",
        "users": users, "pending_users": pending_users, "total_runs": total_runs, "total_results": total_results, "api_keys": api_keys, "new_key": new_key})

@app.get("/admin/evaluation-requests", response_class=HTMLResponse)
def admin_eval_requests(request: Request, session: Optional[str] = Cookie(default=None)):
    user, redir = require_admin(session)
    if redir: return redir
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT id, name, organisation, contact_email, model_name, provider,
                   endpoint_details, evaluation_objective, notes, status, created_at
            FROM evaluation_requests
            ORDER BY created_at DESC
        """)
        requests = []
        for r in cur.fetchall():
            requests.append({
                "id": r["id"],
                "name": r["name"] or "—",
                "organisation": r["organisation"] or "—",
                "contact_email": r["contact_email"],
                "model_name": r["model_name"] or "—",
                "provider": r["provider"] or "—",
                "endpoint_details": r["endpoint_details"] or "—",
                "evaluation_objective": r["evaluation_objective"] or "—",
                "notes": r["notes"] or "—",
                "status": r["status"] or "pending",
                "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M") if r["created_at"] else "—"
            })
        conn.close()
    except Exception as e:
        print(f"Eval requests error: {e}"); requests = []
    return templates.TemplateResponse("admin_eval_requests.html", {
        "request": request, "user": user, "active": "admin", "requests": requests
    })

@app.post("/admin/evaluation-requests/{req_id}/status")
def admin_eval_request_status(req_id: int, status: str = Form(...), session: Optional[str] = Cookie(default=None)):
    user, redir = require_admin(session)
    if redir: return redir
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("UPDATE evaluation_requests SET status=%s WHERE id=%s", (status, req_id))
        conn.commit(); conn.close()
    except Exception as e:
        print(f"Eval request status error: {e}")
    return RedirectResponse("/admin/evaluation-requests", status_code=302)

@app.post("/admin/create-user")
def admin_create_user(session: Optional[str] = Cookie(default=None),
                      username: str = Form(...), password: str = Form(...),
                      is_admin_flag: Optional[str] = Form(default=None)):
    user, redir = require_admin(session)
    if redir: return redir
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (%s,%s,%s)",
                    (username, hash_password(password), bool(is_admin_flag)))
        conn.commit(); conn.close()
    except Exception as e:
        print(f"Create user error: {e}")
    return RedirectResponse("/admin", status_code=302)

@app.post("/admin/delete-user/{user_id}")
def admin_delete_user(user_id: int, session: Optional[str] = Cookie(default=None)):
    user, redir = require_admin(session)
    if redir: return redir
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id=%s AND username != 'admin'", (user_id,))
        conn.commit(); conn.close()
    except Exception as e:
        print(f"Delete user error: {e}")
    return RedirectResponse("/admin", status_code=302)

@app.post("/admin/approve-user/{user_id}")
def admin_approve_user(user_id: int, session: Optional[str] = Cookie(default=None)):
    user, redir = require_admin(session)
    if redir: return redir
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT full_name, email, username FROM users WHERE id=%s", (user_id,))
        u = cur.fetchone()
        cur.execute("UPDATE users SET is_active=TRUE, is_approved=TRUE WHERE id=%s", (user_id,))
        conn.commit(); conn.close()
        if u:
            name = u["full_name"] or u["username"] or "there"
            email = u["email"] or u["username"]
            send_email(
                subject="Your MTCP access has been approved",
                body=f"Hi {name},\n\nYour request for access to the MTCP platform has been approved.\n\nYou can now log in at https://mtcp.live/login using your email address.\n\nMTCP Team\nresearch@mtcp.live"
            )
    except Exception as e:
        print(f"Approve user error: {e}")
    return RedirectResponse("/admin", status_code=302)

@app.post("/admin/create-key")
def admin_create_key(request: Request, session: Optional[str] = Cookie(default=None), label: str = Form(default="")):
    user, redir = require_admin(session)
    if redir: return redir
    import secrets, hashlib
    raw = "cp3_" + secrets.token_hex(24)
    prefix = raw[:12]
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("INSERT INTO api_keys (user_id, key_hash, key_prefix, label) VALUES (%s,%s,%s,%s)",
                    (user["id"], hashed, prefix, label or None))
        conn.commit(); conn.close()
    except Exception as e:
        print(f"Create key error: {e}")
    from starlette.responses import RedirectResponse as RR
    from urllib.parse import quote
    return RR(f"/admin?new_key={quote(raw)}", status_code=302)

@app.post("/admin/revoke-key")
def admin_revoke_key(request: Request, key_id: int = Form(...), session: Optional[str] = Cookie(default=None)):
    user, redir = require_admin(session)
    if redir: return redir
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("UPDATE api_keys SET is_active=FALSE WHERE id=%s", (key_id,))
        conn.commit(); conn.close()
    except Exception as e:
        print(f"Revoke key error: {e}")
    return RedirectResponse("/admin", status_code=302)

@app.get("/ctrl-probes", response_class=HTMLResponse)
def ctrl_probes_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user, redir = require_admin(session)
    if redir: return redir
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT ru.model, COUNT(*) as total,
                   SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) as passed,
                   ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) AS NUMERIC)/NULLIF(COUNT(*),0),1) as pass_rate
            FROM results r JOIN runs ru ON r.run_id=ru.id
            WHERE ru.dataset='ctrl' GROUP BY ru.model ORDER BY pass_rate DESC""")
        ctrl_rows = [{"model": r["model"], "total": r["total"], "passed": r["passed"], "pass_rate": float(r["pass_rate"] or 0)} for r in cur.fetchall()]
        cur.execute("""
            SELECT ru.model, ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) AS NUMERIC)/NULLIF(COUNT(*),0),1) as pass_rate
            FROM results r JOIN runs ru ON r.run_id=ru.id
            WHERE ru.dataset IS DISTINCT FROM 'ctrl' GROUP BY ru.model""")
        main_avg = {r["model"]: float(r["pass_rate"] or 0) for r in cur.fetchall()}
        conn.close()
        for row in ctrl_rows:
            row["main_avg"] = main_avg.get(row["model"])
            row["drop"] = round(row["main_avg"] - row["pass_rate"], 1) if row["main_avg"] else None
    except Exception as e:
        print(f"Ctrl probes error: {e}"); ctrl_rows=[]
    return templates.TemplateResponse("ctrl_probes.html", {
        "request": request, "user": user, "active": "admin", "ctrl_rows": ctrl_rows})

@app.get("/health", response_class=HTMLResponse)
def health_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user, redir = require_admin(session)
    if redir: return redir
    status = "OK"; db_info = {}
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT version() AS n"); db_info["version"] = cur.fetchone()['n']
        cur.execute("SELECT COUNT(*) AS n FROM runs"); db_info["runs"] = cur.fetchone()['n']
        cur.execute("SELECT COUNT(*) AS n FROM results"); db_info["results"] = cur.fetchone()['n']
        conn.close()
    except Exception as e:
        status = f"ERROR: {e}"
    return templates.TemplateResponse("health.html", {
        "request": request, "user": user, "status": status, "db_info": db_info})

@app.get("/api/actuarial", response_class=HTMLResponse)
def actuarial_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user, redir = require_admin(session)
    if redir: return redir
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT ru.temperature, ru.model,
                   ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) AS NUMERIC)/NULLIF(COUNT(*),0),1) as pass_rate
            FROM results r JOIN runs ru ON r.run_id=ru.id
            WHERE ru.dataset IS DISTINCT FROM 'ctrl'
            GROUP BY ru.temperature, ru.model ORDER BY ru.temperature, pass_rate DESC""")
        rows = [{"temperature": float(r["temperature"] or 0), "model": r["model"], "pass_rate": float(r["pass_rate"] or 0)} for r in cur.fetchall()]; conn.close()
    except Exception as e:
        print(f"Actuarial error: {e}"); rows=[]
    return templates.TemplateResponse("actuarial.html", {
        "request": request, "user": user, "rows": rows})

@app.get("/api/costs", response_class=HTMLResponse)
def costs_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user, redir = require_admin(session)
    if redir: return redir
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT model, COUNT(DISTINCT run_id) as runs, COUNT(*) as probes
            FROM results r JOIN runs ru ON r.run_id=ru.id
            WHERE ru.dataset IS DISTINCT FROM 'ctrl'
            GROUP BY model ORDER BY model""")
        rows = [dict(r) for r in cur.fetchall()]; conn.close()
    except Exception as e:
        print(f"Costs error: {e}"); rows=[]
    return templates.TemplateResponse("costs.html", {"request": request, "user": user, "rows": rows})


@app.get("/settings/api-keys", response_class=HTMLResponse)
def api_keys_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user, redir = require_admin(session)
    if redir: return redir
    keys = {}
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT provider, key_value FROM user_provider_keys WHERE user_id=%s", (user["id"],))
        keys = {r["provider"]: r["key_value"] for r in cur.fetchall()}
        conn.close()
    except: pass
    return templates.TemplateResponse("api_keys_settings.html", {
        "request": request, "current_user": user, "keys": keys})

@app.post("/api/user-keys/save")
async def save_provider_key(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user: return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    body = await request.json()
    provider, key = body.get("provider"), body.get("key")
    conn = get_db(); cur = conn.cursor()
    cur.execute("""INSERT INTO user_provider_keys (user_id, provider, key_value) VALUES (%s,%s,%s)
        ON CONFLICT(user_id, provider) DO UPDATE SET key_value=EXCLUDED.key_value""",
        (user["id"], provider, key))
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

# ── CERTIFICATE DOWNLOAD ──────────────────────────────────────────────────────

@app.get("/certificate/download/{model}/{temperature}", response_class=HTMLResponse)
def download_certificate(model: str, temperature: float, session: Optional[str] = Cookie(default=None)):
    user, redir = require_login(session)
    if redir: return redir
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) as passed,
                   SUM(CASE WHEN r.outcome='SAFETY_HARD_STOP' THEN 1 ELSE 0 END) as hard_stops,
                   ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END) AS NUMERIC)/NULLIF(COUNT(*),0),1) as pass_rate
            FROM results r JOIN runs ru ON r.run_id=ru.id
            WHERE ru.model=%s AND ru.temperature=%s AND ru.dataset IS DISTINCT FROM 'ctrl'
        """, (model, temperature))
        row = cur.fetchone(); conn.close()
        if not row: return JSONResponse({"error": "No data found"}, status_code=404)
        pr = float(row["pass_rate"] or 0)
        g = grade(pr)
        color = {"A":"#00e5a0","B":"#7b6cff","C":"#f5a623","D":"#ff4f4f"}.get(g,"#00e5a0")
        issued = datetime.utcnow().strftime("%B %Y")
        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"/>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet"/>
<style>
  body{{font-family:'JetBrains Mono',monospace;background:#0a0c10;color:#d4dbe8;margin:0;padding:48px;min-height:100vh;display:flex;align-items:center;justify-content:center}}
  .cert{{background:#111318;border:2px solid {color};border-radius:12px;padding:48px;max-width:700px;width:100%;text-align:center}}
  .cert-title{{font-family:'DM Serif Display',serif;font-size:13px;color:#5a6070;text-transform:uppercase;letter-spacing:.2em;margin-bottom:32px}}
  .grade{{font-family:'DM Serif Display',serif;font-size:120px;color:{color};line-height:1;margin:16px 0}}
  .model-name{{font-family:'DM Serif Display',serif;font-size:26px;color:#fff;margin-bottom:8px}}
  .temp{{font-size:12px;color:#5a6070;margin-bottom:24px}}
  .stats{{display:flex;justify-content:center;gap:40px;margin:24px 0;padding:20px;background:#0a0c10;border-radius:8px}}
  .stat-val{{font-family:'DM Serif Display',serif;font-size:32px;color:{color}}}
  .stat-lbl{{font-size:10px;color:#5a6070;text-transform:uppercase;letter-spacing:.08em;margin-top:4px}}
  .doi{{font-size:11px;color:#5a6070;margin-top:24px}}
</style></head>
<body><div class="cert">
  <div class="cert-title">MTCP Benchmark Certificate · Control Plane 3</div>
  <div class="grade">{g}</div>
  <div class="model-name">{model}</div>
  <div class="temp">Temperature: {temperature}</div>
  <div class="stats">
    <div><div class="stat-val">{pr}%</div><div class="stat-lbl">Pass Rate</div></div>
    <div><div class="stat-val">{int(row['passed'])}</div><div class="stat-lbl">Passed</div></div>
    <div><div class="stat-val">{int(row['total'])}</div><div class="stat-lbl">Total Probes</div></div>
    <div><div class="stat-val">{int(row['hard_stops'])}</div><div class="stat-lbl">Hard Stops</div></div>
  </div>
  <div class="doi">DOI: 10.17605/OSF.IO/DXGK5 · A. Abby · © 2026 · All Rights Reserved · Issued: {issued}</div>
</div>
<script>window.onload=function(){{window.print();}}</script>
</body></html>"""
        return HTMLResponse(content=html)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# ── DATA EXPORT ───────────────────────────────────────────────────────────────

def serialise(rows):
    out = []
    for r in rows:
        d = {}
        for k, v in dict(r).items():
            d[k] = str(v) if hasattr(v, 'isoformat') else v
        out.append(d)
    return out

@app.get("/api/runs")
def api_runs(session: Optional[str] = Cookie(default=None), x_api_key: Optional[str] = Header(default=None)):
    if not get_auth(session, x_api_key): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM runs ORDER BY created_at DESC")
    rows = serialise(cur.fetchall()); conn.close()
    return JSONResponse(rows)

@app.get("/api/results")
def api_results(limit: int = 50, session: Optional[str] = Cookie(default=None), x_api_key: Optional[str] = Header(default=None)):
    if not get_auth(session, x_api_key): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM results ORDER BY id DESC LIMIT %s", (limit,))
    rows = serialise(cur.fetchall()); conn.close()
    return JSONResponse(rows)

@app.get("/api/export-csv")
def export_csv(session: Optional[str] = Cookie(default=None), x_api_key: Optional[str] = Header(default=None)):
    if not get_auth(session, x_api_key): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT res.id, ru.model, ru.temperature, ru.created_at as run_date,
               res.probe_id, res.outcome
        FROM results res JOIN runs ru ON res.run_id=ru.id ORDER BY res.id DESC""")
    rows = cur.fetchall(); conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id","model","temperature","run_date","probe_id","outcome"])
    for row in rows: writer.writerow([row["id"],row["model"],row["temperature"],row["run_date"],row["probe_id"],row["outcome"]])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=cp3_results.csv"})

@app.post("/run")
async def run_benchmark_api(request: Request, session: Optional[str] = Cookie(default=None), x_api_key: Optional[str] = Header(default=None)):
    if not get_auth(session, x_api_key): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = await request.json()
    model = body.get("model", "")
    temperature = float(body.get("temperature", 0.0))
    dataset = body.get("dataset", "main")
    result = subprocess.run(
        ["python3", "llm_safety_platform.py", "--model", model, "--temperature", str(temperature), "--dataset", dataset],
        capture_output=True, text=True)
    return JSONResponse({"success": result.returncode==0, "stdout": result.stdout, "stderr": result.stderr})
