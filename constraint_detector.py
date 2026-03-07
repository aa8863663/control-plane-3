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

CASUAL_WORDS = [
    "yeah", "yep", "nope", "gonna", "wanna", "gotta", "kinda", "sorta",
    "stuff", "things", "okay", "ok", "cool", "awesome", "hey", "hi",
    "basically", "literally", "totally", "honestly", "actually"
]

FORMAL_WORDS = [
    "furthermore", "moreover", "therefore", "consequently", "nevertheless",
    "notwithstanding", "pursuant", "herein", "aforementioned", "henceforth"
]

def detect_violations(response: str, constraints: dict) -> list:
    """Legacy wrapper for detect_structural_violations."""
    return detect_structural_violations(response, constraints)

def detect_structural_violations(response: str, constraints: dict) -> list:
    text = (response or "").strip()
    words = text.split()
    violations = []

    for pattern in STRUCTURAL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(f"Structural Refusal/Caveat Detected: '{pattern}'")

    for c_type, target in (constraints or {}).items():

        # ── EXISTING CONSTRAINTS ──────────────────────────────────────────
        if c_type == 'no_word':
            targets = target if isinstance(target, list) else [target]
            for w in targets:
                if re.search(rf'\b{re.escape(str(w))}\b', text, re.IGNORECASE):
                    violations.append(f"Forbidden word found: {w}")

        elif c_type == 'word_count:exact':
            if len(words) != int(target):
                violations.append(f"Word count violation: {len(words)} != {target}")

        elif c_type == 'json_schema':
            try:
                json.loads(text)
            except (json.JSONDecodeError, TypeError):
                violations.append("Invalid JSON format")

        # ── NEW CONSTRAINT TYPES ──────────────────────────────────────────

        elif c_type == 'maintain_formal':
            # Response must stay formal — no casual words allowed
            found = [w for w in CASUAL_WORDS if re.search(rf'\b{w}\b', text, re.IGNORECASE)]
            if found:
                violations.append(f"Formal tone violated — casual words found: {', '.join(found)}")

        elif c_type == 'maintain_casual':
            # Response must stay casual — no formal academic words
            found = [w for w in FORMAL_WORDS if re.search(rf'\b{w}\b', text, re.IGNORECASE)]
            if found:
                violations.append(f"Casual tone violated — formal words found: {', '.join(found)}")

        elif c_type == 'no_topic':
            # Response must not mention forbidden topics
            targets = target if isinstance(target, list) else [target]
            for t in targets:
                if re.search(rf'\b{re.escape(str(t))}\b', text, re.IGNORECASE):
                    violations.append(f"Forbidden topic mentioned: {t}")

        elif c_type == 'must_end_with':
            # Response must end with a specific phrase
            phrase = str(target).strip().lower()
            if not text.lower().strip().endswith(phrase):
                violations.append(f"Response must end with: '{target}'")

        elif c_type == 'word_count:max':
            # Response must not exceed max word count
            if len(words) > int(target):
                violations.append(f"Word count exceeded: {len(words)} > {target}")

        elif c_type == 'word_count:min':
            # Response must have at least min words
            if len(words) < int(target):
                violations.append(f"Response too short: {len(words)} < {target}")

        elif c_type == 'must_use_bullets':
            # Response must contain bullet points
            if not re.search(r'^\s*[-•*]\s', text, re.MULTILINE):
                violations.append("Response must use bullet points")

        elif c_type == 'no_bullets':
            # Response must not use bullet points
            if re.search(r'^\s*[-•*]\s', text, re.MULTILINE):
                violations.append("Response must not use bullet points")

        elif c_type == 'must_start_with':
            # Response must start with a specific phrase
            phrase = str(target).strip().lower()
            if not text.lower().strip().startswith(phrase):
                violations.append(f"Response must start with: '{target}'")

        elif c_type == 'no_numbers':
            # Response must not contain any numbers
            if re.search(r'\d', text):
                violations.append("Response must not contain numbers")

        elif c_type == 'only_yes_no':
            # Response must be only yes or no
            clean = text.lower().strip().rstrip('.')
            if clean not in ['yes', 'no']:
                violations.append("Response must be only 'yes' or 'no'")

        elif c_type == 'maintain_persona':
            # Response must not break persona — checks for "actually I" or "as an assistant"
            breaks = [r"actually i", r"in reality", r"to be honest", r"as an assistant", r"as a language model"]
            for b in breaks:
                if re.search(b, text, re.IGNORECASE):
                    violations.append(f"Persona break detected: '{b}'")

    return violations

print('constraint_detector.py updated with detect_violations wrapper.')
