import os, sqlite3
from fastapi import FastAPI

DB_DEFAULT = os.getenv("CONTROLPLANE_DB", "controlplane.db")
PRICE_DEFAULT = float(os.getenv("PRICE_PER_1K", "0.01"))

app = FastAPI(title="ControlPlane Stats")

@app.get("/")
def root():
    return {
        "ok": True,
        "endpoints": ["/health", "/stats", "/costs", "/docs"]
    }


def _conn(db: str):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return c

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/stats")
def stats(db: str = DB_DEFAULT, price_per_1k: float = PRICE_DEFAULT):
    db = os.getenv("CONTROLPLANE_DB", db)
    price_per_1k = float(os.getenv("PRICE_PER_1K", str(price_per_1k)))

    conn = _conn(db)
    cur = conn.cursor()

    cur.execute("""
      SELECT COUNT(DISTINCT r.id) AS runs,
             COUNT(res.id)        AS results,
             COALESCE(SUM(res.total_tokens),0) AS tokens
      FROM runs r LEFT JOIN results res ON res.run_id=r.id
    """)
    row = cur.fetchone()
    runs, results, tokens = int(row["runs"]), int(row["results"]), int(row["tokens"])
    total_cost = (tokens/1000.0) * price_per_1k

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
    by_temp = []
    for r in cur.fetchall():
      tok = int(r["tokens"])
      by_temp.append({
        "temperature": r["temperature"],
        "runs": int(r["runs"]),
        "results": int(r["results"]),
        "tokens": tok,
        "avg_tokens": float(r["avg_tokens"]),
        "est_cost": (tok/1000.0) * price_per_1k
      })

    conn.close()
    return {
      "db": db,
      "price_per_1k": price_per_1k,
      "total": {"runs": runs, "results": results, "tokens": tokens, "est_cost": total_cost},
      "by_temperature": by_temp
    }

@app.get("/costs")
def costs(db: str = DB_DEFAULT, price_per_1k: float = PRICE_DEFAULT):
    return stats(db=db, price_per_1k=price_per_1k)
