"""Multi-provider LLM gateway for FinAI.

This module is intentionally based on the CURRENT FinAI repository architecture:
Python builds deterministic financial evidence, while a real LLM produces the
interpretation. The router discovers currently available models instead of
hard-coding a model that may disappear or be unavailable.

Provider order:
    Gemini -> Groq -> OpenRouter

Model selection:
    - GEMINI_MODEL / GROQ_MODEL / OPENROUTER_MODEL may optionally pin a model.
    - If not pinned, the router discovers models from the provider API.
    - OpenRouter is restricted to currently free ($0 input/output) models.
"""
from __future__ import annotations

import json
import time
from typing import Any

import requests

from .financial_context import build_analysis_context


DEFAULT_PROVIDER_ORDER = ["gemini", "groq", "openrouter"]

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


class ProviderError(Exception):
    def __init__(self, provider: str, status_code: int | str | None, detail: str):
        self.provider = provider
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


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
    result = [x for x in requested if x in DEFAULT_PROVIDER_ORDER]

    # Keep all providers available unless the user intentionally supplied an
    # order. This prevents an accidental typo from disabling the router.
    return result or DEFAULT_PROVIDER_ORDER.copy()


def _configured_model(provider: str) -> str | None:
    return _secret(f"{provider.upper()}_MODEL")


def _api_key(provider: str) -> str | None:
    names = {
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    return _secret(names[provider])


def _diagnostic_reason(provider: str, status_code: int | str | None, detail: str = "") -> str:
    code = str(status_code) if status_code is not None else ""

    if code == "401":
        return "API key ditolak atau tidak valid (401)."
    if code == "403":
        return "Akses ditolak oleh provider (403); cek project, izin, atau API key."
    if code == "404":
        return "Model/endpoint tidak ditemukan (404)."
    if code == "408":
        return "Request timeout (408)."
    if code == "429":
        return "Kena rate limit/quota (429). Router mencoba kandidat berikutnya."
    if code == "400":
        return "Request ditolak sebagai bad request (400); cek payload/model."
    if code == "network_error":
        return "Koneksi ke provider gagal atau timeout."
    if code == "missing_key":
        return "API key tidak ditemukan di Streamlit Secrets."
    if code == "model_discovery":
        return "Tidak berhasil mendapatkan daftar model yang tersedia dari provider."
    if code == "no_model":
        return "Tidak ada model yang kompatibel/tersedia untuk request ini."
    if code.startswith("5"):
        return f"Provider mengalami server error ({code})."
    if code == "unexpected_error":
        return "Terjadi error internal yang tidak terduga."

    # Keep provider payload out of the UI. The detailed error is retained
    # separately in the attempt record for debugging.
    return "Provider tidak berhasil merespons."


def _get_json(url: str, headers: dict[str, str], params: dict[str, Any] | None, timeout: int, provider: str) -> dict[str, Any]:
    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise ProviderError(provider, "network_error", str(exc)[:500]) from exc

    if response.status_code != 200:
        raise ProviderError(provider, response.status_code, response.text[:1000])

    try:
        data = response.json()
    except Exception as exc:
        raise ProviderError(provider, response.status_code, f"Invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ProviderError(provider, response.status_code, "Response JSON bukan object.")

    return data


# ---------------------------------------------------------------------------
# Dynamic model discovery
# ---------------------------------------------------------------------------

def _gemini_models(api_key: str, timeout: int) -> list[str]:
    """Return currently listed Gemini models supporting generateContent."""
    models: list[dict[str, Any]] = []
    page_token: str | None = None

    for _ in range(5):
        params: dict[str, Any] = {"pageSize": 100}
        if page_token:
            params["pageToken"] = page_token

        data = _get_json(
            "https://generativelanguage.googleapis.com/v1beta/models",
            {"x-goog-api-key": api_key},
            params,
            timeout,
            "gemini",
        )

        page = data.get("models") or []
        if isinstance(page, list):
            models.extend(item for item in page if isinstance(item, dict))

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    result = []
    for item in models:
        supported = item.get("supportedGenerationMethods") or []
        name = str(item.get("name") or "")
        if "generateContent" in supported and name.startswith("models/"):
            result.append(name.split("/", 1)[1])

    # Remove duplicates while retaining provider order.
    return list(dict.fromkeys(result))


def _groq_models(api_key: str, timeout: int) -> list[str]:
    """Return active Groq model IDs."""
    data = _get_json(
        "https://api.groq.com/openai/v1/models",
        {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        None,
        timeout,
        "groq",
    )

    result = []
    for item in data.get("data") or []:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if model_id and item.get("active", True):
            result.append(model_id)

    return list(dict.fromkeys(result))


def _is_zero_price(value: Any) -> bool:
    try:
        return float(value) == 0.0
    except (TypeError, ValueError):
        return str(value).strip() in {"0", "0.0", "0.00"}


def _openrouter_models(api_key: str, timeout: int) -> list[str]:
    """Return currently listed OpenRouter models with $0 input/output pricing."""
    data = _get_json(
        "https://openrouter.ai/api/v1/models",
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        None,
        timeout,
        "openrouter",
    )

    result = []
    for item in data.get("data") or []:
        if not isinstance(item, dict):
            continue

        model_id = str(item.get("id") or "").strip()
        pricing = item.get("pricing") or {}

        free_by_price = _is_zero_price(pricing.get("prompt")) and _is_zero_price(
            pricing.get("completion")
        )
        free_by_id = model_id.endswith(":free")

        if not model_id or not (free_by_price or free_by_id):
            continue

        # Prefer models capable of text -> text. The API has changed its
        # metadata shape over time, so absence of architecture metadata does
        # not automatically disqualify a model.
        architecture = item.get("architecture") or {}
        input_modalities = architecture.get("input_modalities")
        output_modalities = architecture.get("output_modalities")

        if input_modalities and "text" not in input_modalities:
            continue
        if output_modalities and "text" not in output_modalities:
            continue

        result.append(model_id)

    return list(dict.fromkeys(result))


def _preference_score(provider: str, model: str) -> tuple[int, str]:
    """Stable preference only; availability is always determined by discovery."""
    m = model.lower()

    if provider == "gemini":
        preferred = [
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3-flash",
        ]
        for index, name in enumerate(preferred):
            if m == name:
                return (0 + index, m)
        if "flash" in m:
            return (20, m)
        if "pro" in m:
            return (40, m)
        return (80, m)

    if provider == "groq":
        preferred = [
            "openai/gpt-oss-20b",
            "openai/gpt-oss-120b",
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
        ]
        for index, name in enumerate(preferred):
            if m == name:
                return (index, m)
        if "chat" in m or "llama" in m or "qwen" in m:
            return (20, m)
        return (80, m)

    # OpenRouter: preference does not affect whether a model is eligible.
    # Only zero-priced discovered models enter this list.
    preferred_terms = [
        "nemotron",
        "qwen",
        "deepseek",
        "gemma",
        "llama",
        "mistral",
        "gpt-oss",
    ]
    for index, term in enumerate(preferred_terms):
        if term in m:
            return (index, m)
    return (50, m)


def _select_models(provider: str, discovered: list[str], configured: str | None) -> list[str]:
    """Choose a small, deterministic candidate list from discovered models.

    A configured model gets first priority only when it is actually present in
    the provider's live model list. No hard-coded model is used as a fallback.
    """
    if not discovered:
        return []

    candidates = list(discovered)
    ordered: list[str] = []

    if configured and configured in candidates:
        ordered.append(configured)
        candidates.remove(configured)

    candidates.sort(key=lambda model: _preference_score(provider, model))

    # One model is normally enough. A second live model is useful for testing
    # when the first candidate is temporarily rate-limited.
    ordered.extend(candidates[:1])
    return list(dict.fromkeys(ordered))


def _discover_provider_models(provider: str, api_key: str, timeout: int) -> list[str]:
    if provider == "gemini":
        discovered = _gemini_models(api_key, timeout)
    elif provider == "groq":
        discovered = _groq_models(api_key, timeout)
    elif provider == "openrouter":
        discovered = _openrouter_models(api_key, timeout)
    else:
        discovered = []

    return _select_models(provider, discovered, _configured_model(provider))


# ---------------------------------------------------------------------------
# LLM calls
# ---------------------------------------------------------------------------

def _messages_for_context(
    messages: list[dict[str, Any]], evidence: dict[str, Any]
) -> tuple[list[dict[str, str]], str]:
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
        content = "".join(
            str(part.get("text", "")) if isinstance(part, dict) else str(part)
            for part in content
        )

    if not content:
        content = message.get("reasoning") or choices[0].get("text")

    return str(content).strip() if content else None


def _call_openai_compatible(
    provider: str,
    model: str,
    api_key: str,
    messages: list[dict[str, Any]],
    timeout: int,
) -> str:
    if provider == "groq":
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    else:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://finai-tes.streamlit.app",
            "X-Title": "FinAI",
        }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1200,
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise ProviderError(provider, "network_error", str(exc)[:500]) from exc

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


def _call_gemini(
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    timeout: int,
) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    contents = []
    for message in messages:
        role = "model" if message["role"] == "assistant" else "user"
        contents.append(
            {
                "role": role,
                "parts": [{"text": message["content"]}],
            }
        )

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1200,
        },
    }

    try:
        response = requests.post(
            url,
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise ProviderError("gemini", "network_error", str(exc)[:500]) from exc

    if response.status_code != 200:
        raise ProviderError("gemini", response.status_code, response.text[:1000])

    try:
        data = response.json()
        candidates = data.get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts") or []
        content = "".join(
            str(part.get("text", ""))
            for part in parts
            if isinstance(part, dict)
        )
    except Exception as exc:
        raise ProviderError("gemini", response.status_code, f"Invalid JSON: {exc}") from exc

    if not content.strip():
        raise ProviderError("gemini", response.status_code, "Response tidak berisi content.")

    return content.strip()


# ---------------------------------------------------------------------------
# Public router
# ---------------------------------------------------------------------------

def _build_messages(
    user_messages: list[dict[str, Any]], evidence: dict[str, Any]
) -> list[dict[str, str]]:
    history, evidence_text = _messages_for_context(user_messages, evidence)

    context_message = (
        "FINANCIAL EVIDENCE (gunakan sebagai satu-satunya sumber fakta):\n"
        + evidence_text
        + "\n\nTugas: jawab pertanyaan pengguna berdasarkan evidence dan konteks percakapan."
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": context_message},
    ]


def _append_attempt(
    attempts: list[dict[str, Any]],
    provider: str,
    model: str,
    status: int | str,
    latency_ms: int,
    reason: str,
    error: str | None = None,
) -> None:
    item: dict[str, Any] = {
        "provider": provider,
        "model": model or "-",
        "status": status,
        "latency_ms": latency_ms,
        "reason": reason,
    }
    if error:
        item["error"] = error[:500]
    attempts.append(item)


def chat(
    messages: list[dict[str, Any]],
    selected_period: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Build evidence, discover live models, and fail over across providers.

    No Python-generated answer is used as an LLM fallback.
    """
    question = ""
    for item in reversed(messages):
        if item.get("role") == "user":
            question = str(item.get("content", "")).strip()
            break

    evidence = build_analysis_context(question, selected_period)

    if evidence.get("status") != "OK":
        return {
            "ok": False,
            "error": evidence.get(
                "message",
                "Evidence finansial tidak tersedia.",
            ),
            "provider": None,
            "attempts": [],
        }

    llm_messages = _build_messages(messages, evidence)
    attempts: list[dict[str, Any]] = []

    for provider in _provider_order():
        started_discovery = time.perf_counter()
        key = _api_key(provider)

        if not key:
            _append_attempt(
                attempts,
                provider,
                "-",
                "missing_key",
                0,
                _diagnostic_reason(provider, "missing_key"),
            )
            continue

        try:
            models = _discover_provider_models(provider, key, timeout)
        except ProviderError as exc:
            discovery_latency = int((time.perf_counter() - started_discovery) * 1000)
            _append_attempt(
                attempts,
                provider,
                _configured_model(provider) or "auto",
                "model_discovery",
                discovery_latency,
                _diagnostic_reason(provider, "model_discovery"),
                str(exc.detail),
            )
            continue
        except Exception as exc:
            discovery_latency = int((time.perf_counter() - started_discovery) * 1000)
            _append_attempt(
                attempts,
                provider,
                _configured_model(provider) or "auto",
                "model_discovery",
                discovery_latency,
                _diagnostic_reason(provider, "model_discovery"),
                str(exc),
            )
            continue

        if not models:
            discovery_latency = int((time.perf_counter() - started_discovery) * 1000)
            _append_attempt(
                attempts,
                provider,
                _configured_model(provider) or "auto",
                "no_model",
                discovery_latency,
                _diagnostic_reason(provider, "no_model"),
            )
            continue

        for model in models:
            started = time.perf_counter()

            try:
                if provider == "gemini":
                    content = _call_gemini(
                        key,
                        model,
                        llm_messages[1:],
                        timeout,
                    )
                else:
                    content = _call_openai_compatible(
                        provider,
                        model,
                        key,
                        llm_messages,
                        timeout,
                    )

                latency_ms = int((time.perf_counter() - started) * 1000)

                return {
                    "ok": True,
                    "content": content,
                    "provider": provider,
                    "model": model,
                    "latency_ms": latency_ms,
                    "attempt": len(attempts) + 1,
                    "fallback": len(attempts) > 0,
                    "period": evidence.get("period"),
                    "attempts": attempts,
                }

            except ProviderError as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                _append_attempt(
                    attempts,
                    provider,
                    model,
                    exc.status_code if exc.status_code is not None else "error",
                    latency_ms,
                    _diagnostic_reason(provider, exc.status_code, exc.detail),
                    exc.detail,
                )
                continue

            except Exception as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                _append_attempt(
                    attempts,
                    provider,
                    model,
                    "unexpected_error",
                    latency_ms,
                    _diagnostic_reason(provider, "unexpected_error"),
                    str(exc),
                )
                continue

    return {
        "ok": False,
        "error": (
            "Semua provider/model LLM gagal merespons. FinAI tidak akan "
            "menggantinya dengan jawaban Python agar tidak menghasilkan analisis palsu."
        ),
        "provider": None,
        "attempts": attempts,
    }
