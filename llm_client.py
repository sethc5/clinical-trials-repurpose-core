"""
llm_client.py — Unified LLM client for clinical-trials-repurpose-core.

Routes all LLM calls through OpenRouter (OpenAI-compatible API), replacing
the previous per-module `anthropic.Anthropic()` pattern. Model defaults to
google/gemini-2.5-flash-lite; override via OPENROUTER_MODEL env var or
pass model= explicitly. Anthropic model names are mapped automatically.

Usage:
    text = llm_client.complete(prompt)
    data = llm_client.complete_json(prompt)   # returns parsed dict/list

Required env: OPENROUTER_API_KEY (in .env file, never committed)
Optional env: OPENROUTER_MODEL  (override default model)
Optional env: OPENROUTER_FALLBACK_MODELS (comma-separated fallback model IDs)
Optional env: OPENROUTER_PROVIDER_SORT (e.g. price, throughput)
Optional env: OPENROUTER_ALLOW_FALLBACKS (true/false)
Optional env: OPENROUTER_REQUIRE_PARAMETERS (true/false)
Optional env: OPENROUTER_DATA_COLLECTION (allow/deny)
Optional env: OPENROUTER_ZDR (true/false)
Optional env: OPENROUTER_ONLY_PROVIDERS (comma-separated provider slugs)
Optional env: OPENROUTER_IGNORE_PROVIDERS (comma-separated provider slugs)
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

log = logging.getLogger(__name__)

# Load .env if present (don't require python-dotenv)
_env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

_DEFAULT_MODEL = "google/gemini-2.5-flash-lite"

# Map Anthropic model names that may be passed from config_schema to OpenRouter equivalents
_ANTHROPIC_MODEL_MAP: dict[str, str] = {
    "claude-opus-4-20250514":    "anthropic/claude-opus-4",
    "claude-sonnet-4-20250514":  "anthropic/claude-sonnet-4",
    "claude-haiku-3-5-20241022": "anthropic/claude-haiku-3-5",
    "claude-3-5-sonnet-20241022":"anthropic/claude-3-5-sonnet",
    "claude-3-opus-20240229":    "anthropic/claude-3-opus",
}


def _resolve_model(model: str | None) -> str:
    raw = model or os.getenv("OPENROUTER_MODEL") or _DEFAULT_MODEL
    return _ANTHROPIC_MODEL_MAP.get(raw, raw)


def _parse_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    s = raw.strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off"}:
        return False
    return None


def _parse_csv_env(name: str) -> list[str]:
    raw = os.getenv(name, "")
    if not raw.strip():
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def _build_extra_body() -> dict[str, Any]:
    provider: dict[str, Any] = {}

    sort = os.getenv("OPENROUTER_PROVIDER_SORT", "").strip()
    if sort:
        provider["sort"] = sort

    allow_fallbacks = _parse_bool(os.getenv("OPENROUTER_ALLOW_FALLBACKS"))
    if allow_fallbacks is not None:
        provider["allow_fallbacks"] = allow_fallbacks

    require_parameters = _parse_bool(os.getenv("OPENROUTER_REQUIRE_PARAMETERS"))
    if require_parameters is not None:
        provider["require_parameters"] = require_parameters

    data_collection = os.getenv("OPENROUTER_DATA_COLLECTION", "").strip().lower()
    if data_collection in {"allow", "deny"}:
        provider["data_collection"] = data_collection

    zdr = _parse_bool(os.getenv("OPENROUTER_ZDR"))
    if zdr is not None:
        provider["zdr"] = zdr

    only = _parse_csv_env("OPENROUTER_ONLY_PROVIDERS")
    if only:
        provider["only"] = only

    ignore = _parse_csv_env("OPENROUTER_IGNORE_PROVIDERS")
    if ignore:
        provider["ignore"] = ignore

    extra_body: dict[str, Any] = {}
    if provider:
        extra_body["provider"] = provider

    fallback_models = _parse_csv_env("OPENROUTER_FALLBACK_MODELS")
    if fallback_models:
        extra_body["models"] = fallback_models

    return extra_body


def complete(
    prompt: str,
    system: str = "",
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> str:
    """Send a prompt, return response text. Raises on API error."""
    from openai import OpenAI

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise EnvironmentError(
            "OPENROUTER_API_KEY not set. Add it to .env or export it."
        )

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    req: dict[str, Any] = {
        "model": _resolve_model(model),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    extra_body = _build_extra_body()
    if extra_body:
        req["extra_body"] = extra_body
        log.debug("openrouter extra_body=%s", extra_body)

    resp = client.chat.completions.create(**req)
    return resp.choices[0].message.content or ""


def complete_json(
    prompt: str,
    system: str = "",
    model: str | None = None,
    temperature: float = 0.1,
) -> Any:
    """
    Send a prompt expecting JSON back. Strips markdown fences, parses, returns
    dict/list. Raises json.JSONDecodeError if response is not valid JSON.
    """
    raw = complete(prompt, system=system, model=model, temperature=temperature)
    raw = raw.strip()
    # Strip ```json ... ``` fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)
