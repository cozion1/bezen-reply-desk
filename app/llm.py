"""Model access. Vultr Serverless Inference is OpenAI-compatible; Anthropic is a declared fallback."""
import json
import os
import re

import httpx

VULTR_BASE = os.environ.get("VULTR_INFERENCE_BASE", "https://api.vultrinference.com/v1")


class ModelError(RuntimeError):
    pass


def provider() -> str:
    if os.environ.get("VULTR_INFERENCE_KEY"):
        return "vultr"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "none"


def model_name() -> str:
    if provider() == "vultr":
        return os.environ.get("VULTR_MODEL", "")
    if provider() == "anthropic":
        return os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")
    return "none"


def _vultr(system: str, user: str) -> str:
    r = httpx.post(
        f"{VULTR_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['VULTR_INFERENCE_KEY']}"},
        json={
            "model": model_name(),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2,
            # The model reasons before it answers; a small budget is spent before any JSON appears.
            "max_tokens": 4000,
        },
        timeout=120,
    )
    if r.status_code != 200:
        raise ModelError(f"Vultr inference HTTP {r.status_code}: {r.text[:200]}")
    choice = r.json()["choices"][0]
    if not choice["message"].get("content") and choice.get("finish_reason") == "length":
        raise ModelError("model ran out of tokens while reasoning")
    return choice["message"]["content"]


def _anthropic(system: str, user: str) -> str:
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": model_name(),
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "max_tokens": 2500,
        },
        timeout=90,
    )
    if r.status_code != 200:
        raise ModelError(f"Anthropic HTTP {r.status_code}: {r.text[:200]}")
    # Newer models can return thinking blocks first; read only text blocks.
    return "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")


def complete_json(system: str, user: str) -> dict:
    p = provider()
    if p == "none":
        raise ModelError("no model configured: set VULTR_INFERENCE_KEY (and VULTR_MODEL) or ANTHROPIC_API_KEY")
    call = _vultr if p == "vultr" else _anthropic
    try:
        raw = call(system, user)
    except (ModelError, httpx.HTTPError):
        raw = call(system, user)  # one transport retry; a second failure is reported
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ModelError(f"model did not return JSON: {raw[:200]}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise ModelError(f"bad JSON from model: {e}") from e
