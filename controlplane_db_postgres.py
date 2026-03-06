"""
controlplane_db.py — PostgreSQL version
Replaces SQLite with psycopg2 for persistent storage on Neon
"""

import os
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            key_hash TEXT NOT NULL,
            name TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id SERIAL PRIMARY KEY,
            model TEXT,
            temperature REAL,
            status TEXT,
            python_version TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
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

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Database tables initialised")


def create_default_admin():
    """Create admin user if not exists."""
    import hashlib, secrets
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = 'admin'")
        existing = cur.fetchone()
        if not existing:
            salt = secrets.token_hex(16)
            h = hashlib.sha256((salt + "admin123").encode()).hexdigest()
            pw = f"{salt}:{h}"
            cur.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                ('admin', pw)
            )
            conn.commit()
            print("✅ Admin user created")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Admin init warning: {e}")


if __name__ == "__main__":
    init_db()
    create_default_admin()
