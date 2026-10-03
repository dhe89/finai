from pathlib import Path
import html
import json
import re
import streamlit as st

from finai_ui.ai.llm_router import chat as llm_chat
from finai_ui.ai.markdown_renderer import render_markdown
from finai_ui.ai.test_logger import read_log_bytes
from finai_ui.data_service import (
    LATEST_PERIOD,
    render_page,
    ensure_data_fresh,
    get_latest_period,
    available_periods,
)

st.set_page_config(page_title="FinAI", layout="wide", initial_sidebar_state="collapsed")

BASE_DIR = Path(__file__).resolve().parent
FRONTEND = BASE_DIR / "finai_ui" / "frontend"

PAGE_MAP = {"kinerja", "financial_report", "data_detail", "setting"}

LLM_PROVIDER_LABELS = {
    "gemini": "Google Gemini",
    "groq": "Groq",
    "openrouter": "OpenRouter",
    "LLM Router": "LLM Router",
}

# ------------------------------------------------------------------
# SERVER STATE
# ------------------------------------------------------------------
ensure_data_fresh()
latest_period = get_latest_period() or LATEST_PERIOD
available = available_periods()

st.session_state.setdefault("chat_messages", [])
st.session_state.setdefault("ai_open", False)
st.session_state.setdefault("last_chat_trigger", None)
st.session_state.setdefault("page", "kinerja")
if st.session_state.get("period") not in available:
    st.session_state["period"] = latest_period

# ------------------------------------------------------------------
# CUSTOM COMPONENT V2
# ------------------------------------------------------------------
# Streamlit Components V2 run in the main app DOM (not an iframe) and provide
# a supported JS -> Python event channel. This replaces the fragile URL/query
# transport used by the previous prototype.
try:
    import streamlit.components.v2 as components_v2
except ImportError as exc:
    st.error("Streamlit Components V2 tidak tersedia. Gunakan Streamlit >= 1.51.")
    raise


def mark_active(source_html: str, active_page: str) -> str:
    """Mark exactly one navigation item as active for the current page."""
    def repl(match):
        attrs = match.group(1)
        active = f'data-page="{active_page}"' in attrs
        return '<div class="nav-item' + (" active" if active else "") + '"' + attrs + ">"

    # Important: the closing quote of class is outside the optional `active`
    # token. The previous regex missed every item, leaving Dashboard active.
    return re.sub(
        r'<div class="nav-item(?: active)?"(\s+data-page="[^"]+"\s+tabindex="0")>',
        repl,
        source_html,
    )


def render_chat_messages() -> str:
    if not st.session_state.chat_messages:
        return """
        <div class="msg welcome">
          <div class="bot">✦</div>
          <div class="msgtext"><b>Hi there! 👋</b><br>
            <span class="muted">I'm PETA, your Financial AI Assistant.<br>How can I help you today?</span>
          </div>
        </div>
        """

    blocks = []
    for message in st.session_state.chat_messages[-30:]:
        role = message.get("role")
        content = html.escape(str(message.get("content", ""))).replace("\n", "<br>")
        if role == "user":
            blocks.append(f'<div class="msg user"><div class="bubble">{content}</div></div>')
        elif role == "assistant":
            meta = message.get("meta") or {}
            provider_raw = str(meta.get("provider", ""))
            provider = html.escape(LLM_PROVIDER_LABELS.get(provider_raw, provider_raw))
            model = html.escape(str(meta.get("model", "")))
            latency_ms = meta.get("latency_ms")
            attempt = meta.get("attempt")
            fallback = bool(meta.get("fallback"))

            meta_parts = []
            if provider and model:
                meta_parts.append(f"{provider} · {model}")
            elif provider:
                meta_parts.append(provider)
            if isinstance(latency_ms, (int, float)):
                meta_parts.append(f"{latency_ms / 1000:.1f}s")
            if fallback and isinstance(attempt, int):
                meta_parts.append(f"Fallback #{attempt}")

            metadata_html = (
                f'<div class="ai-meta">{" · ".join(meta_parts)}</div>'
                if meta_parts else ""
            )

            attempts = meta.get("attempts") or []
            # Full provider history is visible for testing. Include the final
            # successful provider as the last attempt.
            attempt_history = list(attempts)
            if provider_raw and provider_raw != "LLM Router":
                attempt_history.append({
                    "provider": provider_raw,
                    "model": model,
                    "status": "success",
                    "latency_ms": latency_ms,
                    "reason": "Provider berhasil menghasilkan jawaban.",
                })
            diagnostic_html = ""
            if attempt_history:
                rows = []
                for idx, attempt_info in enumerate(attempt_history, start=1):
                    p_raw = str(attempt_info.get("provider", ""))
                    p_label = html.escape(LLM_PROVIDER_LABELS.get(p_raw, p_raw))
                    m_label = html.escape(str(attempt_info.get("model", "")))
                    status_raw = str(attempt_info.get("status", ""))
                    reason = html.escape(str(attempt_info.get("reason", "Provider gagal.")))
                    elapsed = attempt_info.get("latency_ms")
                    elapsed_text = f"{elapsed / 1000:.1f}s" if isinstance(elapsed, (int, float)) else "-"
                    if status_raw == "success":
                        icon, status_label, status_class = "✅", "Berhasil", "ok"
                    elif status_raw == "missing_key":
                        icon, status_label, status_class = "⏭️", "Tidak dicoba", ""
                    else:
                        icon, status_label, status_class = "❌", status_raw, ""
                    rows.append(
                        f'<div class="ai-attempt"><b>#{idx} {p_label}</b> · {m_label}'
                        f'<br><span class="ai-attempt-status {status_class}">{icon} {html.escape(status_label)} · {elapsed_text}</span>'
                        f'<br><span class="ai-attempt-reason">{reason}</span></div>'
                    )
                diagnostic_html = (
                    '<details class="ai-diagnostics"><summary>🔎 Riwayat percobaan LLM</summary>'
                    + "".join(rows) + '</details>'
                )
            # Only the presentation layer is changed: LLM answer content is
            # rendered as safe Markdown instead of showing raw ###/** markers.
            content = render_markdown(str(message.get("content", "")))
            blocks.append(
                f'<div class="msg"><div class="bot">✦</div>'
                f'<div class="msgtext"><div class="ai-answer">{content}</div>{metadata_html}{diagnostic_html}</div></div>'
            )
    return "".join(blocks)


sidebar = (FRONTEND / "layout" / "sidebar.html").read_text(encoding="utf-8")
header = (FRONTEND / "layout" / "header.html").read_text(encoding="utf-8")
ai_chat = (FRONTEND / "layout" / "ai_chat.html").read_text(encoding="utf-8")
css = (FRONTEND / "css" / "main.css").read_text(encoding="utf-8")
css += "\n" + (FRONTEND / "css" / "ui_overrides.css").read_text(encoding="utf-8")
js = (FRONTEND / "js" / "app.js").read_text(encoding="utf-8")

page = st.session_state.page
sidebar = mark_active(sidebar, page)
page_content = render_page(page, st.session_state.period)
ai_chat = ai_chat.replace("{{CHAT_MESSAGES}}", render_chat_messages())

# Keep the shell hierarchy deliberately flat.
# Desktop: root grid = sidebar + page content.
# Mobile: sidebar/backdrop/header become fixed siblings, which removes the
# stacking-context problem caused by moving the drawer in/out of #app.
html_content = f"""<div id="finai-root">
  {header}
  {sidebar}
  <div id="app" class="app">
    {page_content}
  </div>
  <div id="mobileOverlay" class="mobile-overlay" aria-hidden="true"></div>
  {ai_chat}
</div>"""


messages = st.session_state.chat_messages[-30:]

finai_component = components_v2.component(
    "finai_ui.finai_shell",
    html=html_content,
    css=css,
    js=js,
    isolate_styles=True,
)

# Optional test-log download. Disabled by default so the existing UI remains unchanged.
try:
    _log_download_enabled = str(st.secrets.get("FINAI_ENABLE_TEST_LOG_DOWNLOAD", "")).lower() in {"1", "true", "yes", "on"}
except Exception:
    _log_download_enabled = False
if _log_download_enabled:
    with st.expander("Testing · LLM Log", expanded=False):
        st.download_button(
            "Download finai_llm_test.jsonl",
            data=read_log_bytes(),
            file_name="finai_llm_test.jsonl",
            mime="application/json",
            disabled=not bool(read_log_bytes()),
            key="download_finai_llm_test_log",
        )

# ------------------------------------------------------------------
# COMPONENT STATE CALLBACKS
# ------------------------------------------------------------------
# Period and navigation represent persistent UI state. They must not be
# one-shot triggers because the selected period remains active while the user
# changes pages and makes further selections. Streamlit Components V2 executes
# these callbacks during the rerun caused by setStateValue().
def _on_period_change():
    component_state = st.session_state.get("finai_shell")
    selected = getattr(component_state, "period", None) if component_state else None
    if selected is not None and str(selected) in available:
        st.session_state.period = str(selected)
        st.session_state.ai_open = False


def _on_navigate_change():
    component_state = st.session_state.get("finai_shell")
    target = getattr(component_state, "navigate", None) if component_state else None
    if target is not None and str(target) in PAGE_MAP:
        st.session_state.page = str(target)
        st.session_state.ai_open = False


result = finai_component(
    key="finai_shell",
    data={
        "page": page,
        "period": st.session_state.period,
        "ai_open": bool(st.session_state.ai_open),
        "messages": messages,
        "mobile": False,
    },
    default={
        "period": st.session_state.period,
        "navigate": st.session_state.page,
    },
    width="stretch",
    height="content",
    on_period_change=_on_period_change,
    on_navigate_change=_on_navigate_change,
    on_ai_change=lambda: None,
    on_chat_change=lambda: None,
)

# AI/chat remain one-shot actions. Period/navigation are handled exclusively
# by their state callbacks above.
ai_event = getattr(result, "ai", None)
chat_event = getattr(result, "chat", None)

if ai_event:
    value = ai_event
    if isinstance(value, dict):
        action = value.get("action")
    else:
        action = str(value)
    if action == "open":
        st.session_state.ai_open = True
        st.rerun()
    elif action == "close":
        st.session_state.ai_open = False
        st.rerun()

if chat_event:
    if isinstance(chat_event, dict):
        text = str(chat_event.get("text", "")).strip()
        nonce = str(chat_event.get("nonce", ""))
    else:
        text = str(chat_event).strip()
        nonce = ""

    if text and nonce != st.session_state.last_chat_trigger:
        st.session_state.last_chat_trigger = nonce
        st.session_state.ai_open = True
        st.session_state.chat_messages.append({"role": "user", "content": text})

        response = llm_chat(st.session_state.chat_messages, selected_period=st.session_state.period)
        if response.get("ok"):
            answer = response.get("content", "").strip()
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": answer,
                "meta": {
                    "provider": response.get("provider"),
                    "model": response.get("model"),
                    "latency_ms": response.get("latency_ms"),
                    "attempt": response.get("attempt"),
                    "fallback": response.get("fallback", False),
                    "attempts": response.get("attempts", []),
                },
            })
        else:
            answer = "⚠️ " + response.get("error", "LLM belum dapat merespons saat ini.")
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": answer,
                "meta": {
                    "provider": "LLM Router",
                    "model": "Tidak ada provider yang berhasil",
                    "attempts": response.get("attempts", []),
                },
            })
        st.rerun()
