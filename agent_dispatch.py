#!/usr/bin/env python3
"""
agent_dispatch.py — Route tasks to the best worker model.

Default routing:
  code / debug / analyse  →  groq      / llama-3.3-70b-versatile
  summarise / write       →  groq      / moonshotai/kimi-k2-instruct-0905
  fast / quick            →  cerebras  / llama3.1-8b
  research / detailed     →  cohere    / command-r-plus-08-2024

Usage:
    python3 agent_dispatch.py --task "summarise the current state of the MTCP project"
    python3 agent_dispatch.py --task "debug this function" --type code
    python3 agent_dispatch.py --task "quick answer" --provider cerebras
    python3 agent_dispatch.py --task "deep research" --provider cohere
    python3 agent_dispatch.py --task "..." --provider groq --model moonshotai/kimi-k2-instruct-0905
"""

import argparse
import sys
from model_call import call

# Task type → (provider, model)
ROUTING = {
    "code":      ("groq",     "llama-3.3-70b-versatile"),
    "debug":     ("groq",     "llama-3.3-70b-versatile"),
    "analyse":   ("groq",     "llama-3.3-70b-versatile"),
    "summarise": ("groq",     "moonshotai/kimi-k2-instruct-0905"),
    "write":     ("groq",     "moonshotai/kimi-k2-instruct-0905"),
    "fast":      ("cerebras", "llama3.1-8b"),
    "quick":     ("cerebras", "llama3.1-8b"),
    "research":  ("cohere",   "command-r-plus-08-2024"),
    "detailed":  ("cohere",   "command-r-plus-08-2024"),
}

TASK_TYPES = list(ROUTING)

# Default model per provider when --provider overrides routing
PROVIDER_DEFAULTS = {
    "groq":     "llama-3.3-70b-versatile",
    "cerebras": "llama3.1-8b",
    "cohere":   "command-r-plus-08-2024",
}

SYSTEM_PROMPTS = {
    "groq/llama-3.3-70b-versatile": (
        "You are a senior software engineer and reasoning expert. "
        "Be precise, concise, and show your reasoning where helpful."
    ),
    "groq/moonshotai/kimi-k2-instruct-0905": (
        "You are a clear, structured technical writer. "
        "Produce well-organised, accurate summaries and prose."
    ),
    "cerebras/llama3.1-8b": (
        "You are a fast, helpful assistant. Be concise."
    ),
    "cohere/command-r-plus-08-2024": (
        "You are a thorough research assistant. "
        "Provide detailed, well-sourced, structured answers."
    ),
}

DEFAULT_SYSTEM = "You are a knowledgeable technical assistant. Be precise and well-organised."

MTCP_CONTEXT = """
You are working on the MTCP (Model Trust & Control Platform) project, codebase at control-plane-3.
Key facts:
- FastAPI backend (api_server.py), PostgreSQL on Neon
- Benchmarks 27+ LLMs on safety/constraint adherence using probes_200.json (200 probes) and probes_control_20.json (20 ctrl probes)
- 4 temperatures tested: T=0.0, 0.2, 0.5, 0.8
- Weekly scheduler (scheduled_runs.py) fires every Monday 02:00 UTC
- Leaderboard at mtcp.live/evidence/public-findings
- Current status: T=0.2 and T=0.8 columns are all 0.0% — awaiting benchmark runs for those temps
- Recent fix: constraint_detector.py dict-response crash (pushed 2026-03-28, commit 83b0590)
- 41/62 runner jobs failed as of March 11 run; root cause under investigation (likely import crash)
- 4 new models pending first run: magistral-medium-latest, gemini-2.5-flash, kimi-k2-instruct-0905, deepseek-r1-distill-qwen-32b
- Bedrock Claude ctrl probes (eu-west-2) also pending
"""

def infer_task_type(task_text: str) -> str:
    """Guess task type from free-text if --type not provided."""
    t = task_text.lower()
    if any(w in t for w in ["summar", "overview", "state of", "status", "recap"]):
        return "summarise"
    if any(w in t for w in ["write", "draft", "compose", "document"]):
        return "write"
    if any(w in t for w in ["debug", "fix", "error", "crash", "bug", "traceback"]):
        return "debug"
    if any(w in t for w in ["analys", "analyz", "review", "evaluat", "assess"]):
        return "analyse"
    if any(w in t for w in ["research", "detail", "in-depth", "thorough"]):
        return "research"
    if any(w in t for w in ["quick", "fast", "brief", "short"]):
        return "fast"
    return "code"  # default


def dispatch(task: str, task_type: str = None, provider_override: str = None,
             model_override: str = None) -> str:
    resolved_type = task_type or infer_task_type(task)
    if resolved_type not in ROUTING:
        raise ValueError(f"Unknown task type '{resolved_type}'. Choose from: {TASK_TYPES}")

    default_provider, default_model = ROUTING[resolved_type]

    if provider_override:
        if provider_override not in PROVIDER_DEFAULTS:
            raise ValueError(f"Unknown provider '{provider_override}'. Choose from: {list(PROVIDER_DEFAULTS)}")
        provider = provider_override
        model = model_override or PROVIDER_DEFAULTS[provider]
    else:
        provider = default_provider
        model = model_override or default_model

    system = SYSTEM_PROMPTS.get(f"{provider}/{model}", DEFAULT_SYSTEM)

    # Inject project context for summarise/analyse/research tasks
    if resolved_type in ("summarise", "analyse", "research", "detailed"):
        full_prompt = f"{MTCP_CONTEXT}\n\nTask: {task}"
    else:
        full_prompt = task

    print(f"[dispatch] type={resolved_type}  provider={provider}  model={model}")
    print()

    return call(provider, model, full_prompt, system=system)


def main():
    parser = argparse.ArgumentParser(description="Route a task to the best worker model.")
    parser.add_argument("--task",     required=True, help="The task or prompt text")
    parser.add_argument("--type",     choices=TASK_TYPES, default=None,
                        help=f"Task type (auto-inferred if omitted): {TASK_TYPES}")
    parser.add_argument("--provider", choices=list(PROVIDER_DEFAULTS), default=None,
                        help="Force a provider: groq, cerebras, cohere")
    parser.add_argument("--model",    default=None,
                        help="Override the model ID (uses provider default if omitted)")
    args = parser.parse_args()

    try:
        result = dispatch(args.task, task_type=args.type,
                          provider_override=args.provider, model_override=args.model)
    except EnvironmentError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(result)


if __name__ == "__main__":
    main()
