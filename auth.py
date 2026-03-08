"""
Authentication module for Control Plane 3.
Uses Neon PostgreSQL for users and sessions — survives Render deploys.
Passwords hashed with sha256 + salt.
"""
import os
import hashlib
import secrets
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "")

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn

def init_users_table():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            is_active INTEGER DEFAULT 1,
            is_admin BOOLEAN DEFAULT FALSE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP NOT NULL
        )
    """)
    conn.commit()
    # ensure default admin exists
    cur.execute("SELECT id FROM users WHERE username=%s", ("admin",))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (%s, %s, TRUE)",
            ("admin", hash_password("admin123"))
        )
        conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{h}"

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, h = stored_hash.split(":", 1)
        return hashlib.sha256((salt + password).encode()).hexdigest() == h
    except Exception:
        return False

def create_user(username: str, password: str) -> bool:
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
            (username, hash_password(password))
        )
        conn.commit()
        conn.close()
        return True
    except psycopg2.IntegrityError:
        return False

def login_user(username: str, password: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username=%s AND is_active=1", (username,))
    row = cur.fetchone()
    conn.close()
    if row and verify_password(password, row["password_hash"]):
        token = secrets.token_urlsafe(32)
        expires = (datetime.utcnow() + timedelta(hours=24)).isoformat()
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (%s, %s, %s)",
            (token, row["id"], expires)
        )
        conn.commit()
        conn.close()
        return token
    return None

def get_user_from_token(token: str):
    if not token:
        return None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT u.id, u.username FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.token=%s AND s.expires_at > NOW()
        """, (token,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None

def logout_token(token: str):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE token=%s", (token,))
        conn.commit()
        conn.close()
    except Exception:
        pass
