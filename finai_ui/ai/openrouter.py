"""FinAI LLM gateway.

Design rule for FinAI v18:
- One simple OpenAI-compatible text path is the primary LLM path.
- No JSON planner is required for the financial answer.
- Provider failures are returned with a diagnostic code so they cannot be
  mistaken for an analytical failure.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests
import streamlit as st

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
MODEL_FALLBACKS = [
    DEFAULT_MODEL,
    "openrouter/free",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-3-12b-it:free",
]

log = logging.getLogger("finai.llm")


def _secret_value(*names: str) -> str:
    # Streamlit Cloud can expose secrets as flat keys or nested TOML sections.
    try:
        for name in names:
            value = st.secrets.get(name, "")
            if value:
                return str(value).strip()
    except Exception as exc:
        log.debug("flat secret lookup failed: %s", exc)

    try:
        nested = st.secrets.get("openrouter", {})
        if nested:
            for name in names:
                for key in (name, name.lower()):
                    value = nested.get(key, "")
                    if value:
                        return str(value).strip()
    except Exception as exc:
        log.debug("nested secret lookup failed: %s", exc)

    return ""


def get_api_key() -> str | None:
    key = _secret_value(
        "OPENROUTER_API_KEY",
        "OPENROUTER_API_KEY_FINAI",
        "api_key",
    )
    if not key:
        key = (
            os.getenv("OPENROUTER_API_KEY", "").strip()
            or os.getenv("OPENROUTER_API_KEY_FINAI", "").strip()
        )
    return key or None


def _models(preferred: str | None = None) -> list[str]:
    result: list[str] = []
    for model in [preferred, os.getenv("OPENROUTER_MODEL", "")] + MODEL_FALLBACKS:
        if model and model not in result:
            result.append(model)
    return result


def _headers(title: str) -> dict[str, str]:
    key = get_api_key()
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://finai-tes.streamlit.app",
        "X-Title": title,
    }


def _extract_error(response: requests.Response) -> tuple[str, str]:
    """Return (diagnostic_code, human-readable provider error)."""
    try:
        body: Any = response.json()
        error = body.get("error") or {}
        code = str(error.get("code") or response.status_code)
        message = str(error.get("message") or response.text[:500])
        metadata = error.get("metadata") or {}
        limit_source = metadata.get("limit_source")
        if limit_source:
            message = f"{message} (limit_source={limit_source})"
    except Exception:
        code = str(response.status_code)
        message = response.text[:500]

    mapping = {
        "401": "invalid_api_key",
        "402": "provider_payment_or_budget",
        "403": "forbidden",
        "404": "model_not_found",
        "408": "timeout",
        "429": "rate_limited",
        "500": "provider_server_error",
        "502": "provider_bad_gateway",
        "503": "provider_unavailable",
        "524": "provider_timeout",
        "529": "provider_overloaded",
    }
    return mapping.get(code, f"http_{code}"), message


def complete_text(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    timeout: int = 90,
    max_tokens: int = 2400,
    temperature: float = 0.15,
    title: str = "FinAI",
) -> dict[str, Any]:
    """Call a normal text completion. No JSON mode, no planner dependency."""
    if not get_api_key():
        return {
            "ok": False,
            "error_code": "missing_api_key",
            "error": "OPENROUTER_API_KEY tidak ditemukan di Streamlit Secrets.",
        }

    errors: list[str] = []
    for candidate in _models(model):
        payload = {
            "model": candidate,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            response = requests.post(
                OPENROUTER_URL,
                headers=_headers(title),
                json=payload,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            errors.append(f"{candidate}: network_error: {exc}")
            continue

        if not 200 <= response.status_code < 300:
            code, message = _extract_error(response)
            errors.append(f"{candidate}: {code}: {message}")
            # Retry the next model for model/provider/rate-limit/server failures.
            continue

        try:
            data = response.json()
            choices = data.get("choices") or []
            message = (choices[0].get("message") or {}) if choices else {}
            content = message.get("content", "")
            if isinstance(content, list):
                content = "".join(
                    str(x.get("text", "")) if isinstance(x, dict) else str(x)
                    for x in content
                )
            content = str(content or "").strip()
            if content:
                return {
                    "ok": True,
                    "content": content,
                    "model": data.get("model") or candidate,
                    "usage": data.get("usage") or {},
                }
            errors.append(f"{candidate}: empty_content")
        except Exception as exc:
            errors.append(f"{candidate}: invalid_response: {exc}")

    log.error("FinAI LLM failed: %s", " | ".join(errors))
    # Classify the combined failure for the application. Keep provider details
    # in the server log; only a concise actionable message reaches the user.
    if any("invalid_api_key" in x for x in errors):
        code = "invalid_api_key"
    elif any("rate_limited" in x for x in errors):
        code = "rate_limited"
    elif any("model_not_found" in x for x in errors):
        code = "model_not_found"
    elif any("network_error" in x for x in errors):
        code = "network_error"
    else:
        code = "llm_unavailable"

    return {
        "ok": False,
        "error_code": code,
        "error": " | ".join(errors[-5:]) or "LLM tidak mengembalikan respons.",
    }


def health_check(model: str | None = None) -> dict[str, Any]:
    """Minimal real LLM call used to distinguish app/data issues from LLM issues."""
    return complete_text(
        "Anda adalah health check FinAI. Jawab hanya: LLM_OK",
        "Tes koneksi FinAI.",
        model=model,
        timeout=30,
        max_tokens=10,
        temperature=0,
        title="FinAI LLM Health Check",
    )
