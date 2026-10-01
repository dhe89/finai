import requests
import streamlit as st

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openrouter/free"

SYSTEM_PROMPT = (
    "You are FinAI, a Financial Intelligence Assistant. "
    "Answer clearly and concisely in Indonesian unless the user uses another language. "
    "Use only the supplied financial context. Do not invent figures. "
    "Distinguish facts from interpretation. If data is insufficient, say so. "
    "Keep answers practical and suitable for management-level financial analysis."
)


def get_api_key():
    try:
        key = st.secrets.get("OPENROUTER_API_KEY", "")
        if not key:
            key = st.secrets.get("api_key", "")
        return str(key).strip() if key else None
    except Exception:
        return None


def chat(messages, model=DEFAULT_MODEL, timeout=45, financial_context=None):
    """Call OpenRouter server-side and optionally include the selected period's financial context.

    The financial_context argument is optional to preserve compatibility with older callers.
    """
    api_key = get_api_key()
    if not api_key:
        return {"ok": False, "error": "API key OpenRouter belum ditemukan di Streamlit Secrets."}

    system_content = SYSTEM_PROMPT
    if financial_context:
        system_content += "\n\nFINANCIAL CONTEXT FOR THE SELECTED PERIOD:\n" + str(financial_context)

    payload_messages = [{"role": "system", "content": system_content}]
    payload_messages.extend(messages[-12:])

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://demuy89.streamlit.app",
        "X-Title": "FinAI - Financial Intelligence",
    }

    payload = {
        "model": model,
        "messages": payload_messages,
        "temperature": 0.2,
        "max_tokens": 500,
    }

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return {"ok": False, "error": f"Koneksi ke OpenRouter gagal: {exc}"}

    if response.status_code != 200:
        try:
            error_data = response.json().get("error", {})
            message = error_data.get("message") or response.text
        except Exception:
            message = response.text
        return {"ok": False, "error": f"OpenRouter HTTP {response.status_code}: {message}"}

    try:
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return {"ok": False, "error": "OpenRouter mengembalikan response tanpa choices."}

        message = choices[0].get("message") or {}
        content = message.get("content")

        if isinstance(content, list):
            content = "".join(
                str(part.get("text", "")) if isinstance(part, dict) else str(part)
                for part in content
            )

        if not content:
            content = message.get("reasoning") or choices[0].get("text")

        if not content:
            return {"ok": False, "error": "OpenRouter mengembalikan jawaban kosong."}

        return {"ok": True, "content": str(content).strip()}
    except Exception as exc:
        return {"ok": False, "error": f"Gagal membaca response OpenRouter: {exc}"}
