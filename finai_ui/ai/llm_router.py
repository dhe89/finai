"""Multi-provider LLM gateway for FinAI.

The router never replaces an LLM with deterministic Python text. Python prepares
facts/evidence; a real LLM must produce the final financial-intelligence answer.
"""
from __future__ import annotations

import json
from typing import Any

import requests
from .financial_context import build_analysis_context

DEFAULT_PROVIDER_ORDER = ["gemini", "groq", "openrouter"]
DEFAULT_MODELS = {
    "gemini": "gemini-3.8-flash",
    "groq": "openai/gpt-oss-20b",
    "openrouter": "openrouter/free",
}

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


def _model(provider: str) -> str:
    return _secret(f"{provider.upper()}_MODEL") or DEFAULT_MODELS[provider]


def _messages_for_context(messages: list[dict[str, Any]], evidence: dict[str, Any]) -> list[dict[str, str]]:
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


def _call_openai_compatible(provider: str, api_key: str, messages: list[dict[str, Any]], timeout: int) -> str:
    if provider == "groq":
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    else:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://finai-tes.streamlit.app",
            "X-Title": "FinAI",
        }

    payload = {
        "model": _model(provider),
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1200,
    }
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


def _call_gemini(api_key: str, messages: list[dict[str, Any]], timeout: int) -> str:
    model = _model("gemini")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"Content-Type": "application/json"}

    contents = []
    for message in messages:
        role = "model" if message["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": message["content"]}]})

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1200},
    }
    response = requests.post(url, params={"key": api_key}, headers=headers, json=payload, timeout=timeout)
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


class ProviderError(Exception):
    def __init__(self, provider: str, status_code: int | None, detail: str):
        self.provider = provider
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _api_key(provider: str) -> str | None:
    return _secret({"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "openrouter": "OPENROUTER_API_KEY"}[provider])


def _build_messages(user_messages: list[dict[str, Any]], evidence: dict[str, Any]) -> list[dict[str, str]]:
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


def chat(messages: list[dict[str, Any]], selected_period: str | None = None, timeout: int = 30) -> dict[str, Any]:
    """Call providers in order and fail over on provider/API errors.

    There is intentionally no Python-generated final-answer fallback.
    """
    question = ""
    for item in reversed(messages):
        if item.get("role") == "user":
            question = str(item.get("content", "")).strip()
            break

    evidence = build_analysis_context(question, selected_period)
    if evidence.get("status") != "OK":
        return {"ok": False, "error": evidence.get("message", "Evidence finansial tidak tersedia."), "provider": None, "attempts": []}

    llm_messages = _build_messages(messages, evidence)
    attempts = []

    for provider in _provider_order():
        key = _api_key(provider)
        if not key:
            attempts.append({"provider": provider, "status": "missing_key"})
            continue
        try:
            if provider == "gemini":
                content = _call_gemini(key, llm_messages[1:], timeout)
            else:
                content = _call_openai_compatible(provider, key, llm_messages, timeout)
            return {
                "ok": True,
                "content": content,
                "provider": provider,
                "model": _model(provider),
                "period": evidence.get("period"),
                "attempts": attempts,
            }
        except (ProviderError, requests.RequestException) as exc:
            if isinstance(exc, ProviderError):
                attempts.append({"provider": provider, "status": exc.status_code, "error": exc.detail})
            else:
                attempts.append({"provider": provider, "status": "network_error", "error": str(exc)[:500]})
            continue
        except Exception as exc:
            attempts.append({"provider": provider, "status": "unexpected_error", "error": str(exc)[:500]})
            continue

    return {
        "ok": False,
        "error": "Semua provider LLM gagal merespons. FinAI tidak akan menggantinya dengan jawaban Python agar tidak menghasilkan analisis palsu.",
        "provider": None,
        "attempts": attempts,
    }
