"""
API Key management for Control Plane 3.
Allows external tools to call the platform API using a key instead of a session cookie.
"""
import sqlite3, os, secrets, hashlib
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "controlplane.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_api_keys_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT UNIQUE NOT NULL,
            key_prefix TEXT NOT NULL,
            label TEXT,
            user_id INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            last_used TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

def create_api_key(user_id: int, label: str = "") -> str:
    raw_key = "cp3_" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12]
    conn = get_db()
    conn.execute(
        "INSERT INTO api_keys (key_hash, key_prefix, label, user_id) VALUES (?,?,?,?)",
        (key_hash, key_prefix, label, user_id)
    )
    conn.commit()
    conn.close()
    return raw_key

def validate_api_key(raw_key: str) -> dict:
    if not raw_key or not raw_key.startswith("cp3_"):
        return None
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    conn = get_db()
    row = conn.execute("""
        SELECT ak.id, ak.user_id, u.username FROM api_keys ak
        JOIN users u ON ak.user_id = u.id
        WHERE ak.key_hash=? AND ak.is_active=1
    """, (key_hash,)).fetchone()
    if row:
        conn.execute("UPDATE api_keys SET last_used=? WHERE key_hash=?",
                     (datetime.utcnow().isoformat(), key_hash))
        conn.commit()
    conn.close()
    return dict(row) if row else None

def list_api_keys(user_id: int) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, key_prefix, label, created_at, last_used, is_active FROM api_keys WHERE user_id=? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def revoke_api_key(key_id: int, user_id: int):
    conn = get_db()
    conn.execute("UPDATE api_keys SET is_active=0 WHERE id=? AND user_id=?", (key_id, user_id))
    conn.commit()
    conn.close()
