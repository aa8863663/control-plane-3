#!/usr/bin/env python3
"""
model_call.py — Thin wrapper for LLM API calls (Groq, Cerebras, Cohere).

Usage:
    from model_call import call

    text = call("groq",     "llama-3.3-70b-versatile",      "Explain recursion")
    text = call("cerebras", "llama3.1-8b",                  "Quick summary")
    text = call("cohere",   "command-r-plus-08-2024",        "Research this topic")
"""

import os
from openai import OpenAI

PROVIDERS = {
    "groq": {
        "base_url":      "https://api.groq.com/openai/v1",
        "env_key":       "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
    },
    "cerebras": {
        "base_url":      "https://api.cerebras.ai/v1",
        "env_key":       "CEREBRAS_API_KEY",
        "default_model": "llama3.1-8b",
    },
    "cohere": {
        "base_url":      "https://api.cohere.com/compatibility/v1",
        "env_key":       "COHERE_API_KEY",
        "default_model": "command-r-plus-08-2024",
    },
    "deepseek": {
        "base_url":      "https://api.deepseek.com",
        "env_key":       "DEEPSEEK_API_KEY",
        "default_model": "deepseek-reasoner",
    },
    "kimi": {
        "base_url":      "https://api.moonshot.cn/v1",
        "env_key":       "KIMI_API_KEY",
        "default_model": "moonshot-v1-8k",
    },
}


def call(provider: str, model: str, prompt: str, system: str = None) -> str:
    """
    Call a provider and return the response text.

    Args:
        provider: "groq", "cerebras", "cohere", "deepseek", or "kimi"
        model:    Model ID (pass None to use provider default)
        prompt:   User message
        system:   Optional system prompt

    Returns:
        Response text as a string.
    """
    cfg = PROVIDERS.get(provider)
    if cfg is None:
        raise ValueError(f"Unknown provider '{provider}'. Choose from: {list(PROVIDERS)}")

    api_key = os.environ.get(cfg["env_key"])
    if not api_key:
        raise EnvironmentError(f"Missing env var {cfg['env_key']} for provider '{provider}'")

    client = OpenAI(api_key=api_key, base_url=cfg["base_url"])

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(
        model=model or cfg["default_model"],
        messages=messages,
    )

    return resp.choices[0].message.content or ""
