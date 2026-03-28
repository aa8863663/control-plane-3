# ============================================================
# CP3 PLATFORM TRANSITION — NEW ROUTES
# Add these to api_server.py
# ============================================================
# Required imports to add at top of api_server.py if not present:
#   from fastapi.responses import HTMLResponse, RedirectResponse
#   from fastapi import Form
#   import psycopg2.extras
# ============================================================

# ── LEADERBOARD DATA HELPER ──────────────────────────────────
def get_leaderboard_data(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            ru.model,
            MODE() WITHIN GROUP (
                ORDER BY COALESCE(NULLIF(ru.provider, ''), 'Unknown')
            ) AS provider,
            ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END)
                AS NUMERIC)/NULLIF(COUNT(*),0),1) as pass_rate,
            ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' AND ru.temperature=0.0 THEN 1 ELSE 0 END)
                AS NUMERIC)/NULLIF(SUM(CASE WHEN ru.temperature=0.0 THEN 1 ELSE 0 END),0),1) as t0,
            ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' AND ROUND(ru.temperature::numeric,1)=0.2 THEN 1 ELSE 0 END)
                AS NUMERIC)/NULLIF(SUM(CASE WHEN ROUND(ru.temperature::numeric,1)=0.2 THEN 1 ELSE 0 END),0),1) as t2,
            ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' AND ru.temperature=0.5 THEN 1 ELSE 0 END)
                AS NUMERIC)/NULLIF(SUM(CASE WHEN ru.temperature=0.5 THEN 1 ELSE 0 END),0),1) as t5,
            ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' AND ROUND(ru.temperature::numeric,1)=0.8 THEN 1 ELSE 0 END)
                AS NUMERIC)/NULLIF(SUM(CASE WHEN ROUND(ru.temperature::numeric,1)=0.8 THEN 1 ELSE 0 END),0),1) as t8,
            COUNT(*) as total
        FROM results r
        JOIN runs ru ON r.run_id = ru.id
        WHERE ru.dataset IS DISTINCT FROM 'ctrl'
        GROUP BY ru.model
        ORDER BY pass_rate DESC
    """)
    rows = cur.fetchall()

    cur.execute("""
        SELECT ru.model,
            ROUND(CAST(100.0*SUM(CASE WHEN r.outcome='COMPLETED' THEN 1 ELSE 0 END)
                AS NUMERIC)/NULLIF(COUNT(*),0),1) as ctrl_rate
        FROM results r
        JOIN runs ru ON r.run_id = ru.id
        WHERE ru.dataset = 'ctrl'
        GROUP BY ru.model
    """)
    ctrl = {r['model']: r['ctrl_rate'] for r in cur.fetchall()}

    def grade(rate):
        if rate >= 95: return 'A'
        if rate >= 90: return 'A'
        if rate >= 80: return 'B'
        if rate >= 70: return 'C'
        if rate >= 60: return 'D'
        return 'F'

    result = []
    for i, row in enumerate(rows):
        main = float(row['pass_rate'] or 0)
        ctrl_r = float(ctrl.get(row['model'], 0) or 0)
        t0 = float(row['t0'] or 0)
        t8 = float(row['t8'] or 0)
        variance = round(abs(t0 - t8), 1)
        result.append({
            'model': row['model'],
            'provider': row['provider'] or 'Unknown',
            'pass_rate': main,
            'ctrl_rate': ctrl_r,
            'drop': round(ctrl_r - main, 1),
            't0': t0, 't2': float(row['t2'] or 0),
            't5': float(row['t5'] or 0), 't8': t8,
            'variance': variance,
            'grade': grade(main),
        })
    return result


# ── NEW HOMEPAGE ─────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def homepage_v2(request: Request):
    conn = get_db_conn()
    models = get_leaderboard_data(conn)
    conn.close()
    return templates.TemplateResponse("landing_v2.html", {
        "request": request,
        "models": list(enumerate(models)),
    })


# ── EVIDENCE / PUBLIC FINDINGS ───────────────────────────────
@app.get("/evidence/public-findings", response_class=HTMLResponse)
async def evidence(request: Request):
    conn = get_db_conn()
    models = get_leaderboard_data(conn)
    conn.close()
    return templates.TemplateResponse("evidence.html", {
        "request": request,
        "models": list(enumerate(models)),
    })

# Keep old /public route as redirect
@app.get("/public", response_class=HTMLResponse)
async def public_redirect():
    return RedirectResponse(url="/evidence/public-findings", status_code=301)


# ── MODEL CARDS INDEX ────────────────────────────────────────
@app.get("/model-cards", response_class=HTMLResponse)
async def model_cards(request: Request):
    conn = get_db_conn()
    models = get_leaderboard_data(conn)
    conn.close()
    return templates.TemplateResponse("model_cards.html", {
        "request": request,
        "models": models,
    })


# ── SINGLE MODEL CARD ────────────────────────────────────────
@app.get("/model-cards/{model_name}", response_class=HTMLResponse)
async def model_card_single(request: Request, model_name: str):
    conn = get_db_conn()
    models = get_leaderboard_data(conn)
    conn.close()
    model = next((m for m in models if m['model'] == model_name), None)
    if not model:
        return HTMLResponse("Model not found", status_code=404)
    return templates.TemplateResponse("model_card_single.html", {
        "request": request,
        "model": model,
    })


# ── METHODOLOGY ──────────────────────────────────────────────
@app.get("/methodology", response_class=HTMLResponse)
async def methodology(request: Request):
    return templates.TemplateResponse("methodology.html", {"request": request})


# ── REQUEST EVALUATION (GET) ─────────────────────────────────
@app.get("/request-evaluation", response_class=HTMLResponse)
async def request_eval_get(request: Request):
    return templates.TemplateResponse("request_evaluation.html", {
        "request": request,
        "success": False,
        "error": None,
    })


# ── REQUEST EVALUATION (POST) ────────────────────────────────
@app.post("/request-evaluation", response_class=HTMLResponse)
async def request_eval_post(
    request: Request,
    organisation: str = Form(...),
    contact_email: str = Form(...),
    model_identifier: str = Form(...),
    deployment_context: str = Form(...),
    evaluation_objective: str = Form(...),
    timeline: str = Form(...),
    vectors: str = Form("full"),
    notes: str = Form(""),
):
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO evaluation_requests
                (company, contact_email, models_of_interest, use_case, timeline, status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            organisation,
            contact_email,
            model_identifier,
            f"Context: {deployment_context}\nObjective: {evaluation_objective}\nVectors: {vectors}\nNotes: {notes}",
            timeline,
            'pending',
        ))
        conn.commit()
        conn.close()
        return templates.TemplateResponse("request_evaluation.html", {
            "request": request,
            "success": True,
            "contact_email": contact_email,
            "error": None,
        })
    except Exception as e:
        return templates.TemplateResponse("request_evaluation.html", {
            "request": request,
            "success": False,
            "error": f"Submission failed: {str(e)}",
        })
