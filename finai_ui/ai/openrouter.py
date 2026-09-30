import requests
import streamlit as st

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openrouter/free"

SYSTEM_PROMPT = (
    "You are FinAI, a Financial Intelligence Assistant. "
    "Answer clearly and concisely in Indonesian unless the user uses another language. "
    "For this connectivity test, answer the user's question directly. "
    "Do not claim access to financial data that has not been supplied."
)


def get_api_key():
    try:
        if "OPENROUTER_API_KEY" in st.secrets:
            return str(st.secrets["OPENROUTER_API_KEY"]).strip()
        if "api_key" in st.secrets:
            return str(st.secrets["api_key"]).strip()
    except Exception:
        return None
    return None


def chat(messages, model=DEFAULT_MODEL, timeout=30):
    """Send a chat request to OpenRouter without exposing the API key to JS."""
    api_key = get_api_key()
    if not api_key:
        return {
            "ok": False,
            "error": "API key OpenRouter belum ditemukan di Streamlit Secrets."
        }

    payload_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
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
        return {
            "ok": False,
            "error": f"OpenRouter HTTP {response.status_code}: {message}"
        }

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
            return {"ok": False, "error": "OpenRouter mengembalikan jawaban kosong."}

        return {"ok": True, "content": str(content).strip()}
    except Exception as exc:
        return {"ok": False, "error": f"Gagal membaca response OpenRouter: {exc}"}
