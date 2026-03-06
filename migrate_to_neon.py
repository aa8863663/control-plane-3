"""
migrate_to_neon.py
Copies all data from local SQLite controlplane.db into Neon PostgreSQL.
Run once: python3 migrate_to_neon.py
"""

import os
import sqlite3
import psycopg2
import psycopg2.extras

# --- CONFIG ---
SQLITE_PATH = os.path.expanduser("~/Downloads/cp3/controlplane.db")
DATABASE_URL = "postgresql://neondb_owner:npg_1XSlWuIhZ5Md@ep-sweet-art-al0epskk-pooler.c-3.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

print("Connecting to SQLite...")
sqlite_conn = sqlite3.connect(SQLITE_PATH)
sqlite_conn.row_factory = sqlite3.Row
sqlite_cur = sqlite_conn.cursor()

print("Connecting to Neon PostgreSQL...")
pg_conn = psycopg2.connect(DATABASE_URL)
pg_cur = pg_conn.cursor()

# --- CREATE TABLES ---
print("Creating tables...")
pg_cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
    )
""")

pg_cur.execute("""
    CREATE TABLE IF NOT EXISTS api_keys (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        key_hash TEXT NOT NULL,
        name TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    )
""")

pg_cur.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        id SERIAL PRIMARY KEY,
        model TEXT,
        temperature REAL,
        status TEXT,
        python_version TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    )
""")

pg_cur.execute("""
    CREATE TABLE IF NOT EXISTS results (
        id SERIAL PRIMARY KEY,
        run_id INTEGER REFERENCES runs(id),
        probe_id TEXT,
        outcome TEXT,
        recovery_latency TEXT,
        t1 TEXT,
        t2 TEXT,
        t3 TEXT,
        total_tokens INTEGER,
        created_at TIMESTAMP DEFAULT NOW()
    )
""")

pg_conn.commit()
print("✅ Tables created")

# --- MIGRATE USERS ---
print("Migrating users...")
sqlite_cur.execute("SELECT * FROM users")
users = sqlite_cur.fetchall()
user_id_map = {}
for u in users:
    try:
        pg_cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s) ON CONFLICT (username) DO NOTHING RETURNING id",
            (u['username'], u['password_hash'])
        )
        result = pg_cur.fetchone()
        if result:
            user_id_map[u['id']] = result[0]
        else:
            pg_cur.execute("SELECT id FROM users WHERE username = %s", (u['username'],))
            user_id_map[u['id']] = pg_cur.fetchone()[0]
    except Exception as e:
        print(f"  User {u['username']} error: {e}")
pg_conn.commit()
print(f"✅ {len(users)} users migrated")

# --- MIGRATE RUNS ---
print("Migrating runs...")
sqlite_cur.execute("SELECT * FROM runs")
runs = sqlite_cur.fetchall()
run_id_map = {}
for r in runs:
    try:
        pg_cur.execute(
            "INSERT INTO runs (model, temperature, status, python_version, created_at) VALUES (%s, %s, %s, %s, NOW()) RETURNING id",
            (r['model'], r['temperature'], r.get('status', 'COMPLETED'), r.get('python_version', '3.9'))
        )
        new_id = pg_cur.fetchone()[0]
        run_id_map[r['id']] = new_id
    except Exception as e:
        print(f"  Run {r['id']} error: {e}")
pg_conn.commit()
print(f"✅ {len(runs)} runs migrated")

# --- MIGRATE RESULTS ---
print("Migrating results...")
sqlite_cur.execute("SELECT * FROM results")
results = sqlite_cur.fetchall()
count = 0
for res in results:
    try:
        new_run_id = run_id_map.get(res['run_id'])
        if not new_run_id:
            continue
        pg_cur.execute(
            "INSERT INTO results (run_id, probe_id, outcome, recovery_latency, t1, t2, t3, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())",
            (new_run_id, res['probe_id'], res['outcome'], res.get('recovery_latency'), res.get('t1'), res.get('t2'), res.get('t3'))
        )
        count += 1
    except Exception as e:
        print(f"  Result {res['id']} error: {e}")
pg_conn.commit()
print(f"✅ {count} results migrated")

sqlite_conn.close()
pg_conn.close()
print("\n🎉 Migration complete! All data is now in Neon PostgreSQL.")
