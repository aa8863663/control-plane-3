import json
import hashlib
import os
from datetime import datetime

def sha256_text(text: str) -> str:
    """Computes and returns the SHA-256 hash of the input text."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def _write_artifact(filename: str, entry: dict) -> dict:
    """Handles the common logic for writing artifacts to a JSON file."""
    entry['timestamp'] = datetime.utcnow().isoformat() + 'Z'
    entry_str = json.dumps(entry, sort_keys=True)
    entry['hash_sha256'] = sha256_text(entry_str)

    data = []
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
                if not isinstance(data, list):
                    data = [data]
        except (json.JSONDecodeError, FileNotFoundError):
            data = []

    data.append(entry)
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    return entry

def log_artifact(filename: str, entry: dict) -> dict:
    """Legacy support function for general artifact logging."""
    return _write_artifact(filename, entry)

def write_state_breach_snapshot(path: str, entry: dict) -> dict:
    """Saves a state breach snapshot to the specified path."""
    return _write_artifact(path, entry)

def write_hard_stop_receipt(path: str, entry: dict) -> dict:
    """Saves a hard stop receipt to the specified path."""
    return _write_artifact(path, entry)

print('artifact_writer.py updated with log_artifact wrapper.')
