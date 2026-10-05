from pathlib import Path
import html
import json
import re
import streamlit as st

from finai_ui.ai.llm_router import chat as llm_chat
from finai_ui.ai.markdown_renderer import render_markdown
from finai_ui.ai.test_logger import read_log_bytes
from finai_ui.data_service import LATEST_PERIOD, render_page, ensure_data_fresh, get_latest_period, available_periods

st.set_page_config(page_title="FinAI", layout="wide", initial_sidebar_state="collapsed")
BASE_DIR = Path(__file__).resolve().parent
FRONTEND = BASE_DIR / "finai_ui" / "frontend"
PAGE_MAP = {"kinerja", "financial_report", "data_detail", "setting"}
LLM_PROVIDER_LABELS = {"gemini": "Google Gemini", "groq": "Groq", "openrouter": "OpenRouter", "LLM Router": "LLM Router"}

ensure_data_fresh()
latest_period = get_latest_period() or LATEST_PERIOD
available = available_periods()
st.session_state.setdefault("chat_messages", [])
st.session_state.setdefault("ai_open", False)
st.session_state.setdefault("last_chat_trigger", None)
st.session_state.setdefault("page", "kinerja")
if st.session_state.get("period") not in available:
    st.session_state["period"] = latest_period

try:
    import streamlit.components.v2 as components_v2
except ImportError:
    st.error("Streamlit Components V2 tidak tersedia. Gunakan Streamlit >= 1.51.")
    raise


def mark_active(source_html: str, active_page: str) -> str:
    def repl(match):
        attrs = match.group(1)
        active = f'data-page="{active_page}"' in attrs
        return '<div class="nav-item' + (" active" if active else "") + '"' + attrs + ">"
    return re.sub(r'<div class="nav-item(?: active)?"(\s+data-page="[^"]+"\s+tabindex="0")>', repl, source_html)


def render_chat_messages() -> str:
    if not st.session_state.chat_messages:
        return '<div class="msg welcome"><div class="bot">✦</div><div class="msgtext"><b>Hi there! 👋</b><br><span class="muted">I\'m PETA, your Financial AI Assistant.<br>How can I help you today?</span></div></div>'
    blocks = []
    for message in st.session_state.chat_messages[-30:]:
        role = message.get("role")
        if role == "user":
            content = html.escape(str(message.get("content", ""))).replace("\n", "<br>")
            blocks.append(f'<div class="msg user"><div class="bubble">{content}</div></div>')
        elif role == "assistant":
            meta = message.get("meta") or {}
            provider_raw = str(meta.get("provider", ""))
            provider = html.escape(LLM_PROVIDER_LABELS.get(provider_raw, provider_raw))
            model = html.escape(str(meta.get("model", "")))
            latency_ms = meta.get("latency_ms")
            parts = []
            if provider and model: parts.append(f"{provider} · {model}")
            elif provider: parts.append(provider)
            if isinstance(latency_ms, (int, float)): parts.append(f"{latency_ms / 1000:.1f}s")
            metadata_html = f'<div class="ai-meta">{" · ".join(parts)}</div>' if parts else ""
            content = render_markdown(str(message.get("content", "")))
            blocks.append(f'<div class="msg"><div class="bot">✦</div><div class="msgtext"><div class="ai-answer">{content}</div>{metadata_html}</div></div>')
    return "".join(blocks)


sidebar = (FRONTEND / "layout" / "sidebar.html").read_text(encoding="utf-8")
header = (FRONTEND / "layout" / "header.html").read_text(encoding="utf-8")
ai_chat = (FRONTEND / "layout" / "ai_chat.html").read_text(encoding="utf-8")
css = (FRONTEND / "css" / "main.css").read_text(encoding="utf-8")
css += "\n" + (FRONTEND / "css" / "ui_overrides.css").read_text(encoding="utf-8")
css += "\n" + (FRONTEND / "css" / "layout_fix.css").read_text(encoding="utf-8")
css += """
:host{display:block!important;width:100%!important;max-width:100%!important;min-width:0!important;margin:0!important;padding:0!important;box-sizing:border-box!important}
#finai-root{width:100%!important;max-width:none!important;min-width:0!important}
"""
js = (FRONTEND / "js" / "app.js").read_text(encoding="utf-8")

page = st.session_state.page
sidebar = mark_active(sidebar, page)
page_content = render_page(page, st.session_state.period)
ai_chat = ai_chat.replace("{{CHAT_MESSAGES}}", render_chat_messages())
html_content = f'''<div id="finai-root">
  {header}
  {sidebar}
  <div id="app" class="app">{page_content}</div>
  <div id="mobileOverlay" class="mobile-overlay" aria-hidden="true"></div>
  {ai_chat}
</div>'''

finai_component = components_v2.component("finai_ui.finai_shell", html=html_content, css=css, js=js, isolate_styles=True)

result = finai_component(
    key="finai_shell",
    data={"page": page, "period": st.session_state.period, "ai_open": bool(st.session_state.ai_open), "messages": st.session_state.chat_messages[-30:], "mobile": False},
    default={"period": st.session_state.period, "navigate": st.session_state.page},
    width="stretch",
    height="stretch",
    on_period_change=lambda: None,
    on_navigate_change=lambda: None,
    on_ai_change=lambda: None,
    on_chat_change=lambda: None,
)

ai_event = getattr(result, "ai", None)
chat_event = getattr(result, "chat", None)
if ai_event:
    action = ai_event.get("action") if isinstance(ai_event, dict) else str(ai_event)
    if action == "open": st.session_state.ai_open = True; st.rerun()
    if action == "close": st.session_state.ai_open = False; st.rerun()
if chat_event:
    text = str(chat_event.get("text", "")).strip() if isinstance(chat_event, dict) else str(chat_event).strip()
    nonce = str(chat_event.get("nonce", "")) if isinstance(chat_event, dict) else ""
    if text and nonce != st.session_state.last_chat_trigger:
        st.session_state.last_chat_trigger = nonce
        st.session_state.ai_open = True
        st.session_state.chat_messages.append({"role": "user", "content": text})
        response = llm_chat(st.session_state.chat_messages, selected_period=st.session_state.period)
        st.session_state.chat_messages.append({"role": "assistant", "content": response.get("content", "⚠️ " + response.get("error", "LLM belum dapat merespons saat ini.")), "meta": {"provider": response.get("provider", "LLM Router"), "model": response.get("model", ""), "latency_ms": response.get("latency_ms"), "attempts": response.get("attempts", [])}})
        st.rerun()
