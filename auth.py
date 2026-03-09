"""
Simple authentication module for Control Plane 3.
Uses SQLite to store users. Passwords hashed with bcrypt via passlib.
"""
import sqlite3
import os
import hashlib
import secrets
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "controlplane.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_users_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            is_active INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            expires_at TEXT NOT NULL
        )
    """)
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
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, hash_password(password))
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def login_user(username: str, password: str) -> str:
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE username=? AND is_active=1", (username,)).fetchone()
    conn.close()
    if row and verify_password(password, row["password_hash"]):
        token = secrets.token_urlsafe(32)
        from datetime import timedelta
        expires = (datetime.utcnow() + timedelta(hours=24)).isoformat()
        conn = get_db()
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?,?,?)",
                     (token, row["id"], expires))
        conn.commit()
        conn.close()
        return token
    return None

def get_user_from_token(token: str) -> dict:
    if not token:
        return None
    conn = get_db()
    row = conn.execute("""
        SELECT u.id, u.username FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token=? AND s.expires_at > datetime('now')
    """, (token,)).fetchone()
    conn.close()
    return dict(row) if row else None

def logout_token(token: str):
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    conn.commit()
    conn.close()
