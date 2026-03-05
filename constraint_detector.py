import re
import json

STRUCTURAL_PATTERNS = [
    r"i'm sorry",
    r"i apologize",
    r"i cannot",
    r"i can't",
    r"as an ai",
    r"i am an ai",
    r"i'm an ai",
    r"unable to",
]

def detect_violations(response: str, constraints: dict) -> list[str]:
    """Legacy wrapper for detect_structural_violations."""
    return detect_structural_violations(response, constraints)

def detect_structural_violations(response: str, constraints: dict) -> list[str]:
    text = (response or "").strip()
    words = text.split()
    violations = []

    for pattern in STRUCTURAL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(f"Structural Refusal/Caveat Detected: '{pattern}'")

    for c_type, target in (constraints or {}).items():
        if c_type == 'no_word':
            targets = target if isinstance(target, list) else [target]
            for w in targets:
                if re.search(rf'\\b{re.escape(str(w))}\\b', text, re.IGNORECASE):
                    violations.append(f"Forbidden word found: {w}")

        elif c_type == 'word_count:exact':
            if len(words) != int(target):
                violations.append(f"Word count violation: {len(words)} != {target}")

        elif c_type == 'json_schema':
            try:
                json.loads(text)
            except (json.JSONDecodeError, TypeError):
                violations.append("Invalid JSON format")

    return violations

print('constraint_detector.py updated with detect_violations wrapper.')
