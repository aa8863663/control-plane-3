"""
PDF report generator for Control Plane 3.
Generates a styled HTML report, then converts to PDF using WeasyPrint if available,
otherwise saves as HTML.
"""
import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "controlplane.db")

def get_report_data():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM runs")
    total_runs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM results")
    total_results = cur.fetchone()[0]
    cur.execute("SELECT outcome, COUNT(*) as count FROM results GROUP BY outcome ORDER BY count DESC")
    outcomes = [dict(r) for r in cur.fetchall()]
    cur.execute("""
        SELECT r.temperature,
               COUNT(res.id) as total,
               SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END) as passed,
               SUM(CASE WHEN res.outcome='SAFETY_HARD_STOP' THEN 1 ELSE 0 END) as failed,
               AVG(res.recovery_latency) as avg_latency
        FROM runs r LEFT JOIN results res ON r.id=res.run_id
        GROUP BY r.temperature ORDER BY r.temperature
    """)
    by_temp = []
    for row in cur.fetchall():
        r = dict(row)
        total = r['total'] or 0
        passed = r['passed'] or 0
        r['pass_rate'] = round((passed/total*100), 1) if total > 0 else 0.0
        r['avg_latency'] = round(r['avg_latency'], 2) if r['avg_latency'] else 'N/A'
        by_temp.append(r)
    cur.execute("""
        SELECT r.model, r.temperature, COUNT(res.id) as total,
               SUM(CASE WHEN res.outcome='COMPLETED' THEN 1 ELSE 0 END) as passed
        FROM runs r LEFT JOIN results res ON r.id=res.run_id
        GROUP BY r.model, r.temperature ORDER BY r.model, r.temperature
    """)
    by_model = []
    for row in cur.fetchall():
        r = dict(row)
        total = r['total'] or 0
        passed = r['passed'] or 0
        r['pass_rate'] = round((passed/total*100), 1) if total > 0 else 0.0
        by_model.append(r)
    conn.close()
    return {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "total_runs": total_runs,
        "total_results": total_results,
        "outcomes": outcomes,
        "by_temperature": by_temp,
        "by_model": by_model,
    }

def generate_html_report(data):
    rows_outcomes = "".join(f"<tr><td>{r['outcome']}</td><td>{r['count']}</td></tr>" for r in data['outcomes'])
    rows_temp = "".join(
        f"<tr><td>{r['temperature']}</td><td>{r['total']}</td><td>{r['passed']}</td><td>{r['failed']}</td><td>{r['pass_rate']}%</td><td>{r['avg_latency']}</td></tr>"
        for r in data['by_temperature']
    )
    rows_model = "".join(
        f"<tr><td>{r['model']}</td><td>{r['temperature']}</td><td>{r['total']}</td><td>{r['passed']}</td><td>{r['pass_rate']}%</td></tr>"
        for r in data['by_model']
    )
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Control Plane 3 — Benchmark Report</title>
<style>
  body {{ font-family: Arial, sans-serif; color: #1F3864; margin: 40px; }}
  h1 {{ color: #1F3864; border-bottom: 3px solid #2E74B5; padding-bottom: 8px; }}
  h2 {{ color: #2E74B5; margin-top: 32px; }}
  .meta {{ color: #888; font-size: 13px; margin-bottom: 32px; }}
  .stats {{ display: flex; gap: 24px; margin-bottom: 32px; }}
  .stat {{ background: #f5f8fc; border-radius: 8px; padding: 16px 24px; text-align: center; }}
  .stat strong {{ display: block; font-size: 32px; color: #2E74B5; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; }}
  th {{ background: #1F3864; color: white; padding: 10px 14px; text-align: left; }}
  td {{ padding: 9px 14px; border-bottom: 1px solid #eef1f7; }}
  tr:last-child td {{ border-bottom: none; }}
  .footer {{ margin-top: 48px; font-size: 12px; color: #aaa; border-top: 1px solid #eee; padding-top: 12px; }}
</style>
</head>
<body>
<h1>Control Plane 3 — Benchmark Report</h1>
<div class="meta">Generated: {data['generated_at']} &nbsp;|&nbsp; DOI: https://doi.org/10.17605/OSF.IO/DXGK5 &nbsp;|&nbsp; Copyright (c) 2026 aa8863663. All Rights Reserved.</div>
<div class="stats">
  <div class="stat"><strong>{data['total_runs']}</strong>Total Runs</div>
  <div class="stat"><strong>{data['total_results']}</strong>Total Results</div>
  <div class="stat"><strong>{len(data['outcomes'])}</strong>Outcome Types</div>
</div>
<h2>Outcomes</h2>
<table><tr><th>Outcome</th><th>Count</th></tr>{rows_outcomes}</table>
<h2>Results by Temperature</h2>
<table><tr><th>Temperature</th><th>Total</th><th>Passed</th><th>Failed</th><th>Pass Rate</th><th>Avg Latency</th></tr>{rows_temp}</table>
<h2>Model Comparison</h2>
<table><tr><th>Model</th><th>Temperature</th><th>Total</th><th>Passed</th><th>Pass Rate</th></tr>{rows_model}</table>
<div class="footer">Control Plane 3 &nbsp;|&nbsp; github.com/aa8863663/control-plane-3 &nbsp;|&nbsp; All Rights Reserved</div>
</body>
</html>"""

def generate_report(output_path="report.pdf"):
    data = get_report_data()
    html = generate_html_report(data)
    html_path = output_path.replace(".pdf", ".html")
    with open(html_path, "w") as f:
        f.write(html)
    try:
        import weasyprint
        weasyprint.HTML(string=html).write_pdf(output_path)
        print(f"PDF report saved: {output_path}")
        return output_path
    except ImportError:
        print(f"WeasyPrint not available. HTML report saved: {html_path}")
        return html_path

if __name__ == "__main__":
    generate_report()
