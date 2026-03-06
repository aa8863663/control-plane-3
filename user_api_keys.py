# user_api_keys.py
# Per-user encrypted API key storage for Control Plane 3
# Drop this file into ~/Downloads/cp3/ alongside api_server.py
#
# Install dependency first:
#   pip3 install cryptography
#
# Then add to api_server.py:
#   from user_api_keys import router as keys_router, get_user_keys
#   app.include_router(keys_router)

import os
import base64
import sqlite3
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from cryptography.fernet import Fernet

# ---------------------------------------------------------------------------
# Encryption setup
# ---------------------------------------------------------------------------
# On first run, if USER_KEYS_SECRET is not set, a key is generated and printed.
# Add the printed value to your .env file as USER_KEYS_SECRET=<value>

def _get_fernet() -> Fernet:
    secret = os.environ.get("USER_KEYS_SECRET")
    if not secret:
        # Generate a new key and warn — only happens once
        new_key = Fernet.generate_key().decode()
        print(f"\n[user_api_keys] WARNING: USER_KEYS_SECRET not set.")
        print(f"[user_api_keys] Add this to your .env file:")
        print(f"  USER_KEYS_SECRET={new_key}\n")
        return Fernet(new_key.encode())
    return Fernet(secret.encode())


def encrypt_key(plaintext: str) -> str:
    """Encrypt an API key string. Returns base64-encoded ciphertext."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_key(ciphertext: str) -> str:
    """Decrypt a stored API key. Returns plaintext."""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

SUPPORTED_PROVIDERS = [
    "groq",
    "anthropic",
    "openai",
    "google",
    "mistral",
    "cohere",
    "huggingface",
]

DB_PATH = os.path.join(os.path.dirname(__file__), "controlplane.db")


def _get_db():
    return sqlite3.connect(DB_PATH)


def init_user_keys_table():
    """Create the user_api_keys table if it doesn't exist. Call at startup."""
    with _get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_api_keys (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                provider    TEXT    NOT NULL,
                encrypted_key TEXT  NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, provider)
            )
        """)
        conn.commit()


def save_user_key(user_id: int, provider: str, plaintext_key: str) -> None:
    """Encrypt and upsert a user's API key for a given provider."""
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")
    encrypted = encrypt_key(plaintext_key)
    with _get_db() as conn:
        conn.execute("""
            INSERT INTO user_api_keys (user_id, provider, encrypted_key, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, provider)
            DO UPDATE SET encrypted_key = excluded.encrypted_key,
                          updated_at = CURRENT_TIMESTAMP
        """, (user_id, provider, encrypted))
        conn.commit()


def remove_user_key(user_id: int, provider: str) -> None:
    """Delete a user's stored key for a provider."""
    with _get_db() as conn:
        conn.execute(
            "DELETE FROM user_api_keys WHERE user_id = ? AND provider = ?",
            (user_id, provider)
        )
        conn.commit()


def get_user_keys(user_id: int, decrypt: bool = False) -> dict:
    """
    Return a dict of {provider: value} for a user.
    If decrypt=False, values are masked placeholders (safe for templates).
    If decrypt=True, values are plaintext keys (use only at benchmark runtime).
    """
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT provider, encrypted_key FROM user_api_keys WHERE user_id = ?",
            (user_id,)
        ).fetchall()

    result = {}
    for provider, enc_key in rows:
        if decrypt:
            try:
                result[provider] = decrypt_key(enc_key)
            except Exception:
                result[provider] = None  # corrupted — treat as missing
        else:
            result[provider] = "••••••••••••••••"  # masked placeholder
    return result


def get_decrypted_key(user_id: int, provider: str) -> Optional[str]:
    """Get a single decrypted key for use at benchmark runtime."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT encrypted_key FROM user_api_keys WHERE user_id = ? AND provider = ?",
            (user_id, provider)
        ).fetchone()
    if not row:
        return None
    try:
        return decrypt_key(row[0])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# FastAPI router — add to api_server.py with app.include_router(keys_router)
# ---------------------------------------------------------------------------

router = APIRouter()


class SaveKeyRequest(BaseModel):
    provider: str
    key: str


class RemoveKeyRequest(BaseModel):
    provider: str


def _current_user_id(request: Request) -> int:
    """
    Extract user_id from session. Adjust this to match your existing
    auth.py session handling in api_server.py.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


@router.post("/api/user-keys/save")
async def api_save_key(body: SaveKeyRequest, request: Request):
    user_id = _current_user_id(request)
    if body.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {body.provider}")
    if len(body.key.strip()) < 8:
        raise HTTPException(status_code=400, detail="Key too short")
    save_user_key(user_id, body.provider, body.key.strip())
    return {"status": "saved", "provider": body.provider}


@router.post("/api/user-keys/remove")
async def api_remove_key(body: RemoveKeyRequest, request: Request):
    user_id = _current_user_id(request)
    remove_user_key(user_id, body.provider)
    return {"status": "removed", "provider": body.provider}


@router.get("/api-keys-settings")
async def api_keys_page(request: Request):
    """
    Render the API keys settings page.
    In api_server.py, replace this stub with your Jinja2 TemplateResponse pattern.
    """
    from fastapi.responses import HTMLResponse
    user_id = _current_user_id(request)
    # keys dict has masked values — safe to pass to template
    keys = get_user_keys(user_id, decrypt=False)
    # Return template — swap for your Jinja2 pattern e.g.:
    # return templates.TemplateResponse("api_keys_settings.html",
    #     {"request": request, "keys": keys, "current_user": ...})
    return {"keys": keys}  # placeholder


# ---------------------------------------------------------------------------
# Provider runner integration
# ---------------------------------------------------------------------------
# In llm_safety_platform.py, replace hardcoded os.environ key lookups with:
#
#   from user_api_keys import get_decrypted_key
#
#   def get_api_key_for_run(user_id: int, provider: str) -> str:
#       # 1. Try user's saved key first
#       key = get_decrypted_key(user_id, provider)
#       # 2. Fall back to server .env (for admin/your own runs)
#       if not key:
#           env_map = {
#               "groq":        "GROQ_API_KEY",
#               "anthropic":   "ANTHROPIC_API_KEY",
#               "openai":      "OPENAI_API_KEY",
#               "google":      "GOOGLE_API_KEY",
#               "mistral":     "MISTRAL_API_KEY",
#               "cohere":      "COHERE_API_KEY",
#               "huggingface": "HUGGINGFACE_API_KEY",
#           }
#           key = os.environ.get(env_map.get(provider, ""), "")
#       if not key:
#           raise ValueError(f"No API key found for provider: {provider}")
#       return key


# ---------------------------------------------------------------------------
# New provider API clients
# ---------------------------------------------------------------------------
# Add these to llm_safety_platform.py alongside your existing groq/anthropic clients.
# Install: pip3 install openai google-generativeai mistralai cohere huggingface_hub

def call_openai(prompt: str, model: str, temperature: float, api_key: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=1000,
    )
    return response.choices[0].message.content


def call_google(prompt: str, model: str, temperature: float, api_key: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    m = genai.GenerativeModel(model)
    response = m.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=1000,
        )
    )
    return response.text


def call_mistral(prompt: str, model: str, temperature: float, api_key: str) -> str:
    from mistralai import Mistral
    client = Mistral(api_key=api_key)
    response = client.chat.complete(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=1000,
    )
    return response.choices[0].message.content


def call_cohere(prompt: str, model: str, temperature: float, api_key: str) -> str:
    import cohere
    client = cohere.Client(api_key=api_key)
    response = client.chat(
        model=model,
        message=prompt,
        temperature=temperature,
    )
    return response.text


def call_huggingface(prompt: str, model: str, temperature: float, api_key: str) -> str:
    from huggingface_hub import InferenceClient
    client = InferenceClient(token=api_key)
    response = client.text_generation(
        prompt,
        model=model,
        temperature=temperature,
        max_new_tokens=1000,
    )
    return response


# Map provider name → caller function (add to your existing dispatch logic)
PROVIDER_CALLERS = {
    "openai":      call_openai,
    "google":      call_google,
    "mistral":     call_mistral,
    "cohere":      call_cohere,
    "huggingface": call_huggingface,
    # groq and anthropic already handled in llm_safety_platform.py
}
