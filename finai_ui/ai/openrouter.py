"""OpenRouter gateway for FinAI.

The gateway is intentionally provider-tolerant. A provider/model failure must
not be confused with an application failure, and an LLM failure must never be
replaced by analytical Python output.
"""
import json
import logging
import os
import re
import time
import requests
import streamlit as st

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")
# Router first: OpenRouter can choose a currently healthy free endpoint. Explicit
# models remain as deterministic fallbacks when the router cannot serve.
FALLBACK_MODELS = [
    "openrouter/free",
    DEFAULT_MODEL,
    "google/gemma-4-31b-it:free",
    "google/gemma-3-12b-it:free",
]

log = logging.getLogger("finai.llm")


def _secret_value(name):
    """Read secrets safely across Streamlit Cloud/local configurations."""
    try:
        # Direct key: st.secrets behaves like a mapping.
        value = st.secrets.get(name, "")
        if value:
            return str(value).strip()
    except Exception as exc:
        log.debug("st.secrets direct lookup failed: %s", exc)

    try:
        # Some deployments store keys under [openrouter].
        nested = st.secrets.get("openrouter", {})
        if nested:
            for key_name in (name, name.lower(), "OPENROUTER_API_KEY", "api_key"):
                try:
                    value = nested.get(key_name, "")
                except Exception:
                    value = ""
                if value:
                    return str(value).strip()
    except Exception as exc:
        log.debug("st.secrets nested lookup failed: %s", exc)
    return ""


def get_api_key():
    return (
        _secret_value("OPENROUTER_API_KEY")
        or _secret_value("OPENROUTER_API_KEY_FINAI")
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
        parts = []
        for item in content:
            if isinstance(item, dict):
                # OpenAI-compatible providers may return {type,text} or nested
                # text objects. Ignore non-text parts.
                text = item.get("text")
                if text:
                    parts.append(str(text))
            elif item:
                parts.append(str(item))
        content = "".join(parts)
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
        # Balanced-ish object extraction. Keep it conservative so a random
        # sentence containing braces is not mistaken for the payload.
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return None


def _candidate_models(model):
    result = []
    for candidate in ["openrouter/free", model, os.getenv("OPENROUTER_MODEL", "")]:
        if candidate and candidate not in result:
            result.append(candidate)
    for candidate in FALLBACK_MODELS:
        if candidate and candidate not in result:
            result.append(candidate)
    return result


def _error_message(response):
    try:
        payload = response.json()
        err = payload.get("error") or {}
        code = err.get("code")
        msg = err.get("message") or response.text
        return f"HTTP {response.status_code}{' [' + str(code) + ']' if code else ''}: {msg}"
    except Exception:
        return f"HTTP {response.status_code}: {response.text[:500]}"


def _post(payload, timeout):
    """POST with one bounded retry for transient provider errors."""
    last_error = None
    for attempt in range(2):
        try:
            response = requests.post(
                OPENROUTER_URL,
                headers=_headers(payload.get("_title", "FinAI")),
                json={k: v for k, v in payload.items() if k != "_title"},
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_error = f"network_error: {exc}"
            if attempt == 0:
                time.sleep(0.6)
                continue
            return None, last_error

        if 200 <= response.status_code < 300:
            return response, None

        last_error = _error_message(response)
        if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
            if attempt == 0:
                time.sleep(0.8)
                continue
        return response, last_error
    return None, last_error or "unknown_provider_error"


def _base_payload(candidate, system_prompt, user_prompt, max_tokens, temperature):
    # IMPORTANT: do not send provider-specific reasoning controls by default.
    # They caused otherwise valid OpenAI-compatible endpoints to reject the
    # request. The UI never receives hidden reasoning regardless.
    return {
        "model": candidate,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }


def complete_text(system_prompt, user_prompt, model=DEFAULT_MODEL, timeout=75,
                  max_tokens=1400, temperature=0.1, title="FinAI"):
    key = get_api_key()
    if not key:
        return {
            "ok": False,
            "error": "OPENROUTER_API_KEY tidak ditemukan.",
            "error_code": "missing_api_key",
        }

    errors = []
    for candidate in _candidate_models(model):
        payload = _base_payload(candidate, system_prompt, user_prompt, max_tokens, temperature)
        payload["_title"] = title
        response, error = _post(payload, timeout)
        if response is None or not (200 <= response.status_code < 300):
            errors.append(f"{candidate}: {error or 'provider_error'}")
            continue
        try:
            data = response.json()
            content = _content_from_response(data)
            if content:
                return {"ok": True, "content": content, "model": candidate}
            errors.append(f"{candidate}: empty_content")
        except Exception as exc:
            errors.append(f"{candidate}: invalid_response: {exc}")

    log.error("LLM text request failed: %s", " | ".join(errors[-6:]))
    return {
        "ok": False,
        "error": "; ".join(errors[-6:]) or "Model tidak mengembalikan jawaban.",
        "error_code": "provider_unavailable",
    }


def complete_json(system_prompt, user_prompt, model=DEFAULT_MODEL, timeout=60,
                  max_tokens=900, title="FinAI Planner"):
    key = get_api_key()
    if not key:
        return {
            "ok": False,
            "error": "OPENROUTER_API_KEY tidak ditemukan.",
            "error_code": "missing_api_key",
        }

    errors = []
    for candidate in _candidate_models(model):
        payload = _base_payload(candidate, system_prompt, user_prompt, max_tokens, 0)
        payload["response_format"] = {"type": "json_object"}
        payload["_title"] = title
        response, error = _post(payload, timeout)
        if response is None or not (200 <= response.status_code < 300):
            errors.append(f"{candidate}: {error or 'provider_error'}")
            continue
        try:
            raw = _content_from_response(response.json())
            parsed = extract_json(raw)
            if isinstance(parsed, dict):
                return {"ok": True, "data": parsed, "model": candidate}
            errors.append(f"{candidate}: invalid_json_output")
        except Exception as exc:
            errors.append(f"{candidate}: invalid_response: {exc}")

    # Last compatibility path: plain text, but explicitly request JSON in the
    # prompt. This catches providers that reject response_format even though the
    # selected model normally supports it.
    plain = complete_text(
        system_prompt + "\nKeluarkan object JSON valid saja, tanpa markdown dan tanpa kalimat pembuka.",
        user_prompt,
        model="openrouter/free",
        timeout=timeout,
        max_tokens=max_tokens,
        temperature=0,
        title=title + " JSON compatibility",
    )
    if plain.get("ok"):
        parsed = extract_json(plain.get("content", ""))
        if isinstance(parsed, dict):
            return {"ok": True, "data": parsed, "model": plain.get("model")}
        errors.append("openrouter/free: compatibility_json_invalid")
    else:
        errors.append(plain.get("error", "compatibility_request_failed"))

    log.error("LLM JSON request failed: %s", " | ".join(errors[-8:]))
    return {
        "ok": False,
        "error": "; ".join(errors[-8:]),
        "error_code": "director_unavailable",
    }


def clean_final_answer(content):
    """Remove obvious leaked meta/reasoning; never expose internal planning."""
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
        "analysis:", "reasoning:",
    ]
    if any(x in lowered for x in forbidden):
        return ""
    return text
