from pathlib import Path
import html
import json
import re
import streamlit as st

from finai_ui.ai.openrouter import chat as openrouter_chat

st.set_page_config(page_title="FinAI", layout="wide", initial_sidebar_state="collapsed")

BASE_DIR = Path(__file__).resolve().parent
FRONTEND = BASE_DIR / "finai_ui" / "frontend"

PAGE_MAP = {
    "kinerja": FRONTEND / "pages" / "kinerja.html",
    "financial_report": FRONTEND / "pages" / "financial_report.html",
    "data_detail": FRONTEND / "pages" / "data_detail.html",
    "setting": FRONTEND / "pages" / "setting.html",
}

# ------------------------------------------------------------------
# SERVER STATE
# ------------------------------------------------------------------
st.session_state.setdefault("chat_messages", [])
st.session_state.setdefault("ai_open", False)
st.session_state.setdefault("last_chat_trigger", None)
st.session_state.setdefault("page", "kinerja")

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
            <span class="muted">I'm your Financial AI Assistant.<br>How can I help you today?</span>
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
            blocks.append(f'<div class="msg"><div class="bot">✦</div><div class="msgtext">{content}</div></div>')
    return "".join(blocks)


sidebar = (FRONTEND / "layout" / "sidebar.html").read_text(encoding="utf-8")
header = (FRONTEND / "layout" / "header.html").read_text(encoding="utf-8")
ai_chat = (FRONTEND / "layout" / "ai_chat.html").read_text(encoding="utf-8")
css = (FRONTEND / "css" / "main.css").read_text(encoding="utf-8")
js = (FRONTEND / "js" / "app.js").read_text(encoding="utf-8")

page = st.session_state.page
sidebar = mark_active(sidebar, page)
page_content = PAGE_MAP[page].read_text(encoding="utf-8")
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

result = finai_component(
    key="finai_shell",
    data={
        "page": page,
        "ai_open": bool(st.session_state.ai_open),
        "messages": messages,
        "mobile": False,
    },
    default={},
    width="stretch",
    height="content",
    on_navigate_change=lambda: None,
    on_ai_change=lambda: None,
    on_chat_change=lambda: None,
)

# ------------------------------------------------------------------
# EVENTS FROM BROWSER
# ------------------------------------------------------------------
nav_event = getattr(result, "navigate", None)
ai_event = getattr(result, "ai", None)
chat_event = getattr(result, "chat", None)

if nav_event:
    target = str(nav_event)
    if target in PAGE_MAP:
        st.session_state.page = target
        st.session_state.ai_open = False
        st.rerun()

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

        response = openrouter_chat(st.session_state.chat_messages)
        if response.get("ok"):
            answer = response.get("content", "").strip()
        else:
            answer = "⚠️ " + response.get("error", "LLM belum dapat merespons saat ini.")
        st.session_state.chat_messages.append({"role": "assistant", "content": answer})
        st.rerun()
