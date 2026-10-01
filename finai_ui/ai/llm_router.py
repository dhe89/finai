"""Multi-provider LLM gateway for FinAI.

Python prepares evidence/calculations; a real LLM produces the final analysis.
This module adds runtime model discovery, quota-aware retries/fallbacks and a
full attempt history for testing.
"""
from __future__ import annotations

import json
import time
from typing import Any

import requests
from .financial_context import build_analysis_context

DEFAULT_PROVIDER_ORDER = ["gemini", "groq", "openrouter"]
DEFAULT_MODELS = {"gemini": "", "groq": "", "openrouter": ""}
DISCOVERY_TIMEOUT = 15
MAX_MODELS_PER_PROVIDER = 8
RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}

SYSTEM_PROMPT = """Anda adalah FinAI, Financial Intelligence Assistant untuk analisis keuangan.

Peran Anda BUKAN sekadar menyebut angka. Anda harus menggunakan evidence yang diberikan
untuk menjelaskan apa yang terjadi, perubahan material, kemungkinan driver yang didukung
data, kualitas pertumbuhan, risiko/hal yang perlu dipantau, dan langkah analisis lanjutan
jika relevan.

ATURAN KERAS:
1. Evidence adalah satu-satunya sumber fakta dan angka. Jangan mengarang angka.
2. Python menghitung angka dan perubahan; Anda melakukan reasoning dan interpretasi.
3. Bedakan FAKTA, INTERPRETASI, dan HAL YANG MASIH PERLU DIVERIFIKASI.
4. Jangan menyatakan sebab-akibat sebagai fakta jika evidence hanya menunjukkan korelasi/perubahan.
5. Untuk pertanyaan "kenapa", identifikasi driver paling material dari data P&L/balance/product movement.
6. Jika diminta membandingkan, gunakan MoM dan YoY bila tersedia. Jangan mengarang YoY jika periodenya tidak tersedia.
7. Jika ditanya apakah pertumbuhan sehat, nilai berdasarkan indikator yang tersedia dan sebutkan keterbatasannya.
8. Jika ditanya target/performa sampai akhir tahun, jangan membuat forecast numerik kecuali data yang diperlukan tersedia. Anda boleh menjelaskan risiko dan indikator yang perlu dipantau.
9. Jangan menggunakan pengetahuan umum sebagai fakta tentang bank/perusahaan yang tidak ada di evidence.
10. Jangan menampilkan chain-of-thought, self-talk, proses internal, atau label seperti Analysis/Thinking.
11. Jawaban harus dalam Bahasa Indonesia, profesional tetapi natural.
12. Untuk pertanyaan sederhana, jawab langsung. Untuk pertanyaan analitis, berikan struktur ringkas yang membantu pengambilan keputusan.
13. Jangan mengulang seluruh evidence. Ambil hanya angka dan perubahan yang relevan.
"""


def _secret(name: str) -> str | None:
    try:
        import streamlit as st
        value = st.secrets.get(name, "")
        return str(value).strip() if value else None
    except Exception:
        return None


def _provider_order() -> list[str]:
    raw = _secret("FINAI_PROVIDER_ORDER")
    if not raw:
        return DEFAULT_PROVIDER_ORDER.copy()
    requested = [x.strip().lower() for x in raw.split(",") if x.strip()]
    return [x for x in requested if x in DEFAULT_PROVIDER_ORDER] or DEFAULT_PROVIDER_ORDER.copy()


def _api_key(provider: str) -> str | None:
    return _secret({"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "openrouter": "OPENROUTER_API_KEY"}[provider])


def _configured_model(provider: str) -> str | None:
    return _secret(f"{provider.upper()}_MODEL") or None


def _model(provider: str) -> str:
    """Compatibility helper; dynamic discovery is preferred."""
    return _configured_model(provider) or DEFAULT_MODELS[provider]


def _messages_for_context(messages: list[dict[str, Any]], evidence: dict[str, Any]):
    evidence_text = json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
    history = []
    for message in messages[-10:]:
        role = str(message.get("role", "user"))
        if role not in {"user", "assistant"}:
            continue
        history.append({"role": role, "content": str(message.get("content", ""))})
    return history, evidence_text


def _extract_openai_content(data: dict[str, Any]) -> str | None:
    choices = data.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in content)
    if not content:
        content = message.get("reasoning") or choices[0].get("text")
    return str(content).strip() if content else None


class ProviderError(Exception):
    def __init__(self, provider: str, status_code: int | None, detail: str):
        self.provider = provider
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _error_category(status: int | None, detail: str) -> str:
    text = (detail or "").lower()
    if status == 401:
        return "authentication"
    if status == 403:
        if any(x in text for x in ("quota", "billing", "permission", "denied", "disabled")):
            return "access_denied_or_billing_required"
        return "access_denied"
    if status == 404:
        return "model_or_endpoint_unavailable"
    if status == 429:
        if any(x in text for x in ("daily", "rpd", "quota", "resource_exhausted", "exhausted")):
            return "daily_quota_or_quota_exhausted"
        return "rate_limit"
    if status in {500, 502, 503, 504}:
        return "temporary_provider_error"
    if status == 408:
        return "timeout"
    return "provider_error"


def _retry_delay(status: int | None, attempt: int) -> float:
    # Keep testing fast; daily quota must never be retried repeatedly.
    if status == 429:
        return min(2.0, 0.5 * (2 ** max(0, attempt - 1)))
    return min(3.0, 0.75 * (2 ** max(0, attempt - 1)))


def _openrouter_models(api_key: str) -> list[str]:
    r = requests.get("https://openrouter.ai/api/v1/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=DISCOVERY_TIMEOUT)
    if r.status_code != 200:
        raise ProviderError("openrouter", r.status_code, r.text[:1000])
    data = r.json().get("data") or []
    configured = _configured_model("openrouter")
    if configured:
        return [configured]
    models = []
    for item in data:
        mid = str(item.get("id", "")).strip()
        pricing = item.get("pricing") or {}
        if not mid:
            continue
        try:
            free = float(pricing.get("prompt", 1)) == 0 and float(pricing.get("completion", 1)) == 0
        except (TypeError, ValueError):
            free = False
        if free:
            models.append(mid)
    return models[:MAX_MODELS_PER_PROVIDER]


def _groq_models(api_key: str) -> list[str]:
    r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=DISCOVERY_TIMEOUT)
    if r.status_code != 200:
        raise ProviderError("groq", r.status_code, r.text[:1000])
    configured = _configured_model("groq")
    if configured:
        return [configured]
    data = r.json().get("data") or []
    models = []
    for item in data:
        mid = str(item.get("id", "")).strip()
        if mid and "whisper" not in mid.lower() and "tts" not in mid.lower():
            models.append(mid)
    # Stable, explicit fallback first when it exists.
    preferred = "openai/gpt-oss-20b"
    models.sort(key=lambda x: (0 if x == preferred else 1, x))
    return models[:MAX_MODELS_PER_PROVIDER]


# Gemini text-generation models that are intended for the free Developer API tier.
# The Gemini Models API also exposes image/TTS/live/embedding models. Those must NOT
# enter FinAI's text router even when they advertise generateContent.
GEMINI_FREE_TEXT_MODELS = {
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
}


def _gemini_models(api_key: str) -> list[str]:
    r = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        params={"key": api_key, "pageSize": 100},
        timeout=DISCOVERY_TIMEOUT,
    )
    if r.status_code != 200:
        raise ProviderError("gemini", r.status_code, r.text[:1000])

    configured = _configured_model("gemini")
    if configured:
        configured = configured.replace("models/", "")
        # Keep an explicit override possible for testing, but do not invent/fallback
        # to a hard-coded model when no override is supplied.
        return [configured]

    data = r.json().get("models") or []
    available = {}

    for item in data:
        name = str(item.get("name", "")).strip()
        methods = item.get("supportedGenerationMethods") or []
        if not name or "generateContent" not in methods:
            continue

        if name.startswith("models/"):
            name = name.split("/", 1)[1]

        # Only models explicitly classified by this router as free text models.
        # This prevents image/TTS/live/embedding models from being selected.
        if name in GEMINI_FREE_TEXT_MODELS:
            available[name] = item

    # Order follows current FinAI testing priority: normal Flash first, then
    # lighter models, then legacy/preview models. Actual availability is still
    # determined by the Models API response above.
    preferred_order = [
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-3.8-flash",
    ]

    return [model for model in preferred_order if model in available][:MAX_MODELS_PER_PROVIDER]


def _discover_models(provider: str, api_key: str) -> list[str]:
    if provider == "gemini":
        return _gemini_models(api_key)
    if provider == "groq":
        return _groq_models(api_key)
    return _openrouter_models(api_key)


def _call_openai_compatible(provider: str, api_key: str, model: str, messages: list[dict[str, Any]], timeout: int) -> str:
    if provider == "groq":
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    else:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "HTTP-Referer": "https://finai-tes.streamlit.app", "X-Title": "FinAI"}
    payload = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": 1200}
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if response.status_code != 200:
        raise ProviderError(provider, response.status_code, response.text[:1000])
    try:
        data = response.json()
    except Exception as exc:
        raise ProviderError(provider, response.status_code, f"Invalid JSON: {exc}") from exc
    content = _extract_openai_content(data)
    if not content:
        raise ProviderError(provider, response.status_code, "Response tidak berisi content.")
    return content


def _call_gemini(api_key: str, model: str, messages: list[dict[str, Any]], timeout: int) -> str:
    model = model.replace("models/", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    contents = []
    for message in messages:
        # system is supplied separately; avoid sending it as user content.
        if message["role"] == "system":
            continue
        role = "model" if message["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": message["content"]}]})
    payload = {"system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]}, "contents": contents, "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1200}}
    response = requests.post(url, params={"key": api_key}, headers={"Content-Type": "application/json"}, json=payload, timeout=timeout)
    if response.status_code != 200:
        raise ProviderError("gemini", response.status_code, response.text[:1000])
    try:
        data = response.json()
        candidates = data.get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts") or []
        content = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
    except Exception as exc:
        raise ProviderError("gemini", response.status_code, f"Invalid JSON: {exc}") from exc
    if not content.strip():
        raise ProviderError("gemini", response.status_code, "Response tidak berisi content.")
    return content.strip()


def _build_messages(user_messages: list[dict[str, Any]], evidence: dict[str, Any]) -> list[dict[str, str]]:
    history, evidence_text = _messages_for_context(user_messages, evidence)
    context_message = "FINANCIAL EVIDENCE (gunakan sebagai satu-satunya sumber fakta):\n" + evidence_text + "\n\nTugas: jawab pertanyaan pengguna berdasarkan evidence dan konteks percakapan."
    return [{"role": "system", "content": SYSTEM_PROMPT}, *history, {"role": "user", "content": context_message}]


def _attempt_record(provider: str, model: str | None, status: Any, category: str, error: str | None, latency: float, retry: int = 0):
    return {"provider": provider, "model": model, "status": status, "category": category, "error": error, "latency": round(latency, 2), "retry": retry}


def chat(messages: list[dict[str, Any]], selected_period: str | None = None, timeout: int = 30) -> dict[str, Any]:
    question = next((str(item.get("content", "")).strip() for item in reversed(messages) if item.get("role") == "user"), "")
    evidence = build_analysis_context(question, selected_period)
    if evidence.get("status") != "OK":
        return {"ok": False, "error": evidence.get("message", "Evidence finansial tidak tersedia."), "provider": None, "attempts": []}

    llm_messages = _build_messages(messages, evidence)
    attempts: list[dict[str, Any]] = []

    for provider in _provider_order():
        key = _api_key(provider)
        if not key:
            attempts.append(_attempt_record(provider, None, "missing_key", "missing_key", "API key tidak ditemukan di Streamlit Secrets.", 0))
            continue
        try:
            models = _discover_models(provider, key)
        except (ProviderError, requests.RequestException) as exc:
            if isinstance(exc, ProviderError):
                attempts.append(_attempt_record(provider, None, exc.status_code, _error_category(exc.status_code, exc.detail), exc.detail[:1000], 0))
            else:
                attempts.append(_attempt_record(provider, None, "discovery_network_error", "network_error", str(exc)[:500], 0))
            continue
        except Exception as exc:
            attempts.append(_attempt_record(provider, None, "discovery_error", "discovery_error", str(exc)[:500], 0))
            continue

        if not models:
            attempts.append(_attempt_record(provider, None, "no_models", "no_usable_models", "Tidak ditemukan model yang dapat digunakan.", 0))
            continue

        for model in models:
            # Daily quota errors should not be retried for the same model.  A transient 429/503 may be retried once.
            max_retries = 1
            retry_index = 0
            while True:
                started = time.perf_counter()
                try:
                    if provider == "gemini":
                        content = _call_gemini(key, model, llm_messages, timeout)
                    else:
                        content = _call_openai_compatible(provider, key, model, llm_messages, timeout)
                    latency = time.perf_counter() - started
                    attempts.append(_attempt_record(provider, model, 200, "success", None, latency, retry_index))
                    return {"ok": True, "content": content, "provider": provider, "model": model, "period": evidence.get("period"), "attempts": attempts}
                except ProviderError as exc:
                    latency = time.perf_counter() - started
                    category = _error_category(exc.status_code, exc.detail)
                    attempts.append(_attempt_record(provider, model, exc.status_code, category, exc.detail[:1000], latency, retry_index))
                    if exc.status_code in RETRYABLE_STATUSES and category not in {"daily_quota_or_quota_exhausted", "rate_limit"} and retry_index < max_retries:
                        retry_index += 1
                        time.sleep(_retry_delay(exc.status_code, retry_index))
                        continue
                    # A 429 caused by quota/rate limit should move on quickly; do not burn testing time.
                    break
                except requests.RequestException as exc:
                    latency = time.perf_counter() - started
                    attempts.append(_attempt_record(provider, model, "network_error", "network_error", str(exc)[:500], latency, retry_index))
                    break
                except Exception as exc:
                    latency = time.perf_counter() - started
                    attempts.append(_attempt_record(provider, model, "unexpected_error", "unexpected_error", str(exc)[:500], latency, retry_index))
                    break

    return {
        "ok": False,
        "error": "Semua provider/model LLM gagal merespons. FinAI tidak akan menggantinya dengan jawaban Python agar tidak menghasilkan analisis palsu. Lihat Riwayat percobaan LLM untuk status dan alasan tiap percobaan.",
        "provider": None,
        "attempts": attempts,
    }
