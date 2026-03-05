import os, io, csv, sqlite3
from datetime import datetime
from fastapi.responses import HTMLResponse, StreamingResponse

# Import your core API app (keeps that file clean)
import finishline_app

app = finishline_app.app  # reuse the same FastAPI instance

# Remove any existing "/" routes from the shared app so our HTML homepage wins.
def _remove_root_routes():
    try:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/"]
    except Exception:
        pass

_remove_root_routes()


DB_DEFAULT = os.getenv("CONTROLPLANE_DB", getattr(finishline_app, "DB_DEFAULT", "controlplane.db"))
PRICE_DEFAULT = float(os.getenv("PRICE_PER_1K", getattr(finishline_app, "PRICE_DEFAULT", "0.01")))

def _conn(db: str):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return c

def _by_temp(db: str):
    conn = _conn(db)
    cur = conn.cursor()
    cur.execute("""
      SELECT r.temperature AS temperature,
             COUNT(DISTINCT r.id) AS runs,
             COUNT(res.id) AS results,
             COALESCE(SUM(res.total_tokens),0) AS tokens,
             COALESCE(AVG(res.total_tokens),0) AS avg_tokens
      FROM runs r LEFT JOIN results res ON res.run_id=r.id
      GROUP BY r.temperature
      ORDER BY r.temperature
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

@app.get("/", response_class=HTMLResponse)
def home():
    # HTML dashboard that calls /stats and renders it
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>ControlPlane Dashboard</title>
  <style>
    body { font-family: -apple-system, system-ui, Segoe UI, Roboto, Arial; padding: 24px; }
    .row { display:flex; gap:12px; flex-wrap:wrap; margin: 12px 0 20px; }
    .card { border:1px solid #ddd; border-radius:12px; padding:12px 14px; min-width: 180px; }
    table { border-collapse: collapse; width: 100%; margin-top: 12px; }
    th, td { border-bottom: 1px solid #eee; padding: 8px 10px; text-align: left; font-size: 14px; }
    th { font-weight: 600; }
    code { background:#f6f6f6; padding:2px 6px; border-radius:8px; }
    a.btn { display:inline-block; margin-right:10px; padding:8px 12px; border:1px solid #ddd; border-radius:10px; text-decoration:none; }
  </style>
</head>
<body>
  <h1>ControlPlane Dashboard</h1>
  <div class="row">
    <a class="btn" href="/docs">API Docs</a>
    <a class="btn" href="/download/csv">Download CSV</a>
    <a class="btn" href="/download/pdf">Download PDF</a>
    <a class="btn" href="/stats">Raw JSON (/stats)</a>
  </div>

  <div class="row">
    <div class="card"><div><b>DB</b></div><div id="db">…</div></div>
    <div class="card"><div><b>Runs</b></div><div id="runs">…</div></div>
    <div class="card"><div><b>Results</b></div><div id="results">…</div></div>
    <div class="card"><div><b>Tokens</b></div><div id="tokens">…</div></div>
    <div class="card"><div><b>Est. Cost</b></div><div id="cost">…</div></div>
  </div>

  <h2>By Temperature</h2>
  <table>
    <thead>
      <tr>
        <th>Temp</th><th>Runs</th><th>Results</th><th>Tokens</th><th>AvgTok</th><th>EstCost</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>

  <p style="margin-top:16px;color:#555">
    Endpoints: <code>/health</code> <code>/stats</code> <code>/costs</code> <code>/docs</code>
  </p>

<script>
async function load() {
  const res = await fetch('/stats');
  const data = await res.json();

  document.getElementById('db').textContent = data.db;
  document.getElementById('runs').textContent = data.total.runs;
  document.getElementById('results').textContent = data.total.results;
  document.getElementById('tokens').textContent = data.total.tokens;
  document.getElementById('cost').textContent = (data.total.est_cost ?? 0).toFixed(4);

  const tb = document.getElementById('tbody');
  tb.innerHTML = '';
  for (const r of data.by_temperature) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${r.temperature}</td>
      <td>${r.runs}</td>
      <td>${r.results}</td>
      <td>${r.tokens}</td>
      <td>${(r.avg_tokens ?? 0).toFixed(1)}</td>
      <td>${(r.est_cost ?? 0).toFixed(4)}</td>
    `;
    tb.appendChild(tr);
  }
}
load();
</script>
</body>
</html>"""

@app.get("/download/csv")
def download_csv(db: str = DB_DEFAULT, price_per_1k: float = PRICE_DEFAULT):
    db = os.getenv("CONTROLPLANE_DB", db)
    price_per_1k = float(os.getenv("PRICE_PER_1K", str(price_per_1k)))

    rows = _by_temp(db)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["generated_at", datetime.utcnow().isoformat()+"Z"])
    w.writerow(["db", db])
    w.writerow(["price_per_1k", price_per_1k])
    w.writerow([])
    w.writerow(["temperature","runs","results","tokens","avg_tokens","est_cost"])
    for r in rows:
        tok = int(r["tokens"])
        w.writerow([r["temperature"], int(r["runs"]), int(r["results"]), tok, float(r["avg_tokens"]), (tok/1000.0)*price_per_1k])

    data = buf.getvalue().encode("utf-8")
    headers = {"Content-Disposition": "attachment; filename=controlplane_costs.csv"}
    return StreamingResponse(io.BytesIO(data), media_type="text/csv", headers=headers)

@app.get("/download/pdf")
def download_pdf(db: str = DB_DEFAULT, price_per_1k: float = PRICE_DEFAULT):
    db = os.getenv("CONTROLPLANE_DB", db)
    price_per_1k = float(os.getenv("PRICE_PER_1K", str(price_per_1k)))

    # reportlab is installed for you already, but keep this safe:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    rows = _by_temp(db)

    # Totals
    conn = _conn(db)
    cur = conn.cursor()
    cur.execute("""
      SELECT COUNT(DISTINCT r.id) AS runs,
             COUNT(res.id)        AS results,
             COALESCE(SUM(res.total_tokens),0) AS tokens
      FROM runs r LEFT JOIN results res ON res.run_id=r.id
    """)
    t = cur.fetchone()
    conn.close()
    runs, results, tokens = int(t["runs"]), int(t["results"]), int(t["tokens"])
    total_cost = (tokens/1000.0) * price_per_1k

    pdf_buf = io.BytesIO()
    c = canvas.Canvas(pdf_buf, pagesize=letter)
    w, h = letter
    y = h - 60

    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, y, "ControlPlane Audit Report")
    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(72, y, f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    y -= 14
    c.drawString(72, y, f"DB: {db}")
    y -= 22

    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Summary")
    y -= 14
    c.setFont("Helvetica", 10)
    c.drawString(72, y, f"Runs: {runs}   Results: {results}   Tokens: {tokens}")
    y -= 14
    c.drawString(72, y, f"Price/1k: {price_per_1k}   Est. cost: {total_cost:.4f}")
    y -= 22

    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "By Temperature")
    y -= 14

    c.setFont("Helvetica-Bold", 9)
    headers = ["Temp","Runs","Results","Tokens","AvgTok","EstCost"]
    xs = [72, 115, 160, 220, 290, 350]
    for i, htxt in enumerate(headers):
        c.drawString(xs[i], y, htxt)
    y -= 12
    c.setFont("Helvetica", 9)

    for r in rows:
        tok = int(r["tokens"])
        est = (tok/1000.0) * price_per_1k
        vals = [r["temperature"], int(r["runs"]), int(r["results"]), tok, f"{float(r['avg_tokens']):.1f}", f"{est:.4f}"]
        for i, v in enumerate(vals):
            c.drawString(xs[i], y, str(v))
        y -= 12
        if y < 80:
            c.showPage()
            y = h - 60
            c.setFont("Helvetica", 9)

    c.save()
    pdf_buf.seek(0)
    headers = {"Content-Disposition": "attachment; filename=controlplane_report.pdf"}
    return StreamingResponse(pdf_buf, media_type="application/pdf", headers=headers)
