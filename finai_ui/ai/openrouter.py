"""Reliable OpenRouter client for FinAI.

The LLM is the intelligence layer. This module is deliberately defensive:
- supports Streamlit Secrets, environment variables and a nested [openrouter] secret;
- uses current free models when the configured model is unavailable/rate-limited;
- retries transient 429/5xx failures;
- uses OpenRouter structured JSON output for the semantic director;
- never exposes the API key to the UI.
"""
import json
import os
import re
import time
import requests
import streamlit as st

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")
FALLBACK_MODELS = [
    DEFAULT_MODEL,
    "google/gemma-4-31b-it:free",
    "google/gemma-3-12b-it:free",
    "openrouter/free",
]


def _secret_value(name):
    try:
        value = st.secrets.get(name, "")
        if value:
            return str(value).strip()
        nested = st.secrets.get("openrouter", {})
        if nested:
            try:
                value = nested.get(name, "") or nested.get(name.lower(), "")
            except Exception:
                value = ""
            if value:
                return str(value).strip()
    except Exception:
        pass
    return ""


def get_api_key():
    # Streamlit Cloud normally uses secrets, but supporting env variables makes
    # local/server deployment behave consistently.
    return (
        _secret_value("OPENROUTER_API_KEY")
        or _secret_value("api_key")
        or os.getenv("OPENROUTER_API_KEY", "").strip()
        or os.getenv("OPENROUTER_API_KEY_FINAI", "").strip()
        or None
    )


def _headers(title="FinAI"):
    key = get_api_key()
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://finai-tes.streamlit.app",
        "X-Title": title,
    }


def _content_from_response(data):
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, list):
        content = "".join(
            str(x.get("text", "")) if isinstance(x, dict) else str(x)
            for x in content
        )
    return str(content or "").strip()


def _strip_fences(text):
    text = str(text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_json(text):
    text = _strip_fences(text)
    try:
        return json.loads(text)
    except Exception:
        # Non-greedy object extraction handles models that add a short sentence
        # around the JSON payload.
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except Exception:
            return None


def _candidate_models(model):
    requested = []
    for candidate in [model, os.getenv("OPENROUTER_MODEL", "")]:
        if candidate and candidate not in requested:
            requested.append(candidate)
    for candidate in FALLBACK_MODELS:
        if candidate and candidate not in requested:
            requested.append(candidate)
    return requested


def _error_message(response):
    try:
        payload = response.json()
        err = payload.get("error") or {}
        code = err.get("code")
        msg = err.get("message") or response.text
        return f"HTTP {response.status_code}{' [' + str(code) + ']' if code else ''}: {msg}"
    except Exception:
        return f"HTTP {response.status_code}: {response.text[:500]}"


def _post(candidate, payload, timeout):
    last_error = None
    # Small bounded retry. Free endpoints can return 429/5xx transiently.
    for attempt in range(2):
        try:
            response = requests.post(
                OPENROUTER_URL,
                headers=_headers(payload.get("_title", "FinAI")),
                json={k: v for k, v in payload.items() if k != "_title"},
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt == 0:
                time.sleep(0.8)
                continue
            return None, f"network error: {last_error}"

        if response.status_code == 200:
            return response, None

        last_error = _error_message(response)
        if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
            if attempt == 0:
                time.sleep(0.8)
                continue
        return response, last_error
    return None, last_error or "unknown provider error"


def complete_text(system_prompt, user_prompt, model=DEFAULT_MODEL, timeout=75,
                  max_tokens=1400, temperature=0.1, title="FinAI"):
    key = get_api_key()
    if not key:
        return {
            "ok": False,
            "error": "OPENROUTER_API_KEY tidak ditemukan. Tambahkan secret OPENROUTER_API_KEY di Streamlit Cloud.",
            "error_code": "missing_api_key",
        }

    errors = []
    for candidate in _candidate_models(model):
        payload = {
            "model": candidate,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            # Keep internal reasoning hidden from the response. This does not
            # disable the model's ability to reason; it only excludes reasoning
            # tokens/details from what is returned to the application.
            "reasoning": {"exclude": True},
            "_title": title,
        }
        response, error = _post(candidate, payload, timeout)
        if response is None or response.status_code != 200:
            errors.append(f"{candidate}: {error or 'provider error'}")
            continue
        try:
            content = _content_from_response(response.json())
            if content:
                return {"ok": True, "content": content, "model": candidate}
            errors.append(f"{candidate}: empty content")
        except Exception as exc:
            errors.append(f"{candidate}: invalid response: {exc}")

    return {
        "ok": False,
        "error": "; ".join(errors[-5:]) or "Model tidak mengembalikan jawaban.",
        "error_code": "provider_unavailable",
    }


def complete_json(system_prompt, user_prompt, model=DEFAULT_MODEL, timeout=60,
                  max_tokens=900, title="FinAI Planner"):
    # OpenRouter documents response_format support for the current Gemma free
    # models and openrouter/free. It greatly improves director reliability.
    key = get_api_key()
    if not key:
        return {
            "ok": False,
            "error": "OPENROUTER_API_KEY tidak ditemukan. Tambahkan secret OPENROUTER_API_KEY di Streamlit Cloud.",
            "error_code": "missing_api_key",
        }

    errors = []
    for candidate in _candidate_models(model):
        payload = {
            "model": candidate,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
            "reasoning": {"exclude": True},
            "response_format": {"type": "json_object"},
            "_title": title,
        }
        response, error = _post(candidate, payload, timeout)
        if response is None or response.status_code != 200:
            errors.append(f"{candidate}: {error or 'provider error'}")
            continue
        try:
            raw = _content_from_response(response.json())
            parsed = extract_json(raw)
            if isinstance(parsed, dict):
                return {"ok": True, "data": parsed, "model": candidate}
            errors.append(f"{candidate}: invalid JSON output")
        except Exception as exc:
            errors.append(f"{candidate}: invalid response: {exc}")

    # Some providers can reject response_format despite advertising JSON. Make
    # one final plain-text attempt through the router, then parse the result.
    plain = complete_text(
        system_prompt + "\nWAJIB keluarkan object JSON valid saja, tanpa markdown.",
        user_prompt,
        model="openrouter/free",
        timeout=timeout,
        max_tokens=max_tokens,
        temperature=0,
        title=title + " JSON fallback",
    )
    if plain.get("ok"):
        parsed = extract_json(plain.get("content", ""))
        if isinstance(parsed, dict):
            return {"ok": True, "data": parsed, "model": plain.get("model")}
        errors.append("openrouter/free: JSON fallback tidak valid")
    else:
        errors.append(plain.get("error", "JSON fallback gagal"))

    return {
        "ok": False,
        "error": "; ".join(errors[-6:]),
        "error_code": "director_unavailable",
    }


def clean_final_answer(content):
    """Remove obvious leaked meta/reasoning, never expose internal planning."""
    text = str(content or "").strip()
    if not text:
        return ""

    lowered = text.lower()
    for marker in ["jawaban final:", "jawaban akhir:", "final answer:"]:
        idx = lowered.rfind(marker)
        if idx >= 0:
            text = text[idx + len(marker):].strip()
            lowered = text.lower()

    forbidden = [
        "the user is asking multiple questions", "first question:",
        "second question:", "third question:", "fourth question:",
        "chain of thought", "thinking process", "internal reasoning",
        "let's analyze", "mari kita cek", "analysis:", "reasoning:",
    ]
    if any(x in lowered for x in forbidden):
        return ""
    return text
