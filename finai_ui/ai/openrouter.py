import json
import re
import requests
import streamlit as st

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemma-3-12b-it:free"
FALLBACK_MODELS = [DEFAULT_MODEL, "openrouter/free"]


def get_api_key():
    try:
        key = st.secrets.get("OPENROUTER_API_KEY", "") or st.secrets.get("api_key", "")
        return str(key).strip() if key else None
    except Exception:
        return None


def _headers(title="FinAI"):
    key = get_api_key()
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://demuy89.streamlit.app",
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
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except Exception:
            return None


def complete_text(system_prompt, user_prompt, model=DEFAULT_MODEL, timeout=60,
                  max_tokens=1200, temperature=0.1, title="FinAI"):
    key = get_api_key()
    if not key:
        return {"ok": False, "error": "API key OpenRouter belum ditemukan di Streamlit Secrets."}

    models = [model] if model else []
    for candidate in FALLBACK_MODELS:
        if candidate not in models:
            models.append(candidate)

    errors = []
    for candidate in models:
        payload = {
            "model": candidate,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "reasoning": {"exclude": True},
        }
        try:
            response = requests.post(
                OPENROUTER_URL,
                headers=_headers(title),
                json=payload,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            errors.append(f"{candidate}: {exc}")
            continue

        if response.status_code != 200:
            try:
                err = response.json().get("error", {})
                msg = err.get("message") or response.text
            except Exception:
                msg = response.text
            errors.append(f"{candidate}: HTTP {response.status_code} {msg}")
            continue

        try:
            content = _content_from_response(response.json())
            if content:
                return {"ok": True, "content": content, "model": candidate}
            errors.append(f"{candidate}: empty content")
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")

    return {"ok": False, "error": "; ".join(errors[-3:]) or "Model tidak mengembalikan jawaban."}


def complete_json(system_prompt, user_prompt, model=DEFAULT_MODEL, timeout=45,
                  max_tokens=700, title="FinAI Planner"):
    response = complete_text(
        system_prompt,
        user_prompt,
        model=model,
        timeout=timeout,
        max_tokens=max_tokens,
        temperature=0.0,
        title=title,
    )
    if not response.get("ok"):
        return response

    try:
        parsed = extract_json(response.get("content", ""))
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Gagal membaca JSON terstruktur: {exc}",
            "raw": response.get("content", ""),
            "model": response.get("model"),
        }
    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "error": "Model tidak mengembalikan object JSON.",
            "raw": response.get("content", ""),
            "model": response.get("model"),
        }
    return {"ok": True, "data": parsed, "model": response.get("model")}


def clean_final_answer(content):
    """Remove obvious leaked meta/reasoning, never expose internal planning."""
    text = str(content or "").strip()
    if not text:
        return ""

    # If a provider unexpectedly emits a final-answer wrapper, keep only that part.
    lowered = text.lower()
    for marker in ["jawaban final:", "jawaban akhir:", "final answer:"]:
        idx = lowered.rfind(marker)
        if idx >= 0:
            text = text[idx + len(marker):].strip()
            lowered = text.lower()

    forbidden = [
        "the user is asking multiple questions",
        "first question:",
        "second question:",
        "third question:",
        "fourth question:",
        "chain of thought",
        "thinking process",
        "internal reasoning",
        "let's analyze",
        "mari kita cek",
        "analysis:",
        "reasoning:",
    ]
    if any(x in lowered for x in forbidden):
        return ""
    return text
