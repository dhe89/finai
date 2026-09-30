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
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "last_chat_nonce" not in st.session_state:
    st.session_state.last_chat_nonce = None

page = str(st.query_params.get("page", "kinerja"))
if page not in PAGE_MAP:
    page = "kinerja"

# AI open state is primarily controlled in the browser. When a message is
# submitted, ai=1 is sent together with the one-shot message transport so the
# overlay remains open after the Streamlit rerun.
ai_param = str(st.query_params.get("ai", "0")) == "1"

# ------------------------------------------------------------------
# CHAT TRANSPORT: browser -> Streamlit -> OpenRouter -> browser
# ------------------------------------------------------------------
chat_query = st.query_params.get("finai_q")
chat_nonce = str(st.query_params.get("finai_n", "")).strip()

if chat_query is not None:
    chat_query = str(chat_query).strip()

    if chat_query and chat_nonce and chat_nonce != st.session_state.last_chat_nonce:
        st.session_state.last_chat_nonce = chat_nonce
        st.session_state.chat_messages.append({"role": "user", "content": chat_query})

        result = openrouter_chat(st.session_state.chat_messages)
        if result.get("ok"):
            answer = result["content"]
        else:
            answer = "⚠️ " + result.get("error", "LLM belum dapat merespons saat ini.")

        st.session_state.chat_messages.append({"role": "assistant", "content": answer})

    # One-shot transport parameters must be removed before rerun so a refresh
    # never submits the same message twice.
    try:
        st.query_params.pop("finai_q", None)
        st.query_params.pop("finai_n", None)
        st.query_params["ai"] = "1"
    except Exception:
        pass

    st.rerun()


def mark_active(source_html, active_page):
    def repl(match):
        attrs = match.group(1)
        active = f'data-page="{active_page}"' in attrs
        return '<div class="nav-item' + (" active" if active else "") + '"' + attrs + ">"

    return re.sub(
        r'<div class="nav-item(?: active)?(\s+data-page="[^"]+"\s+tabindex="0")>',
        repl,
        source_html,
    )


def render_chat_messages():
    """Render chat bubbles as normal HTML so they survive iframe reloads."""
    if not st.session_state.chat_messages:
        return """
        <div class="msg">
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
            # AI responses are plain text except for the small formatting we
            # explicitly add below. Escape first so model output cannot inject
            # arbitrary HTML into the page.
            blocks.append(f'<div class="msg"><div class="bot">✦</div><div class="msgtext">{content}</div></div>')

    return "".join(blocks)


def js_json(value):
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


template = (FRONTEND / "index.html").read_text(encoding="utf-8")
css = (FRONTEND / "css" / "main.css").read_text(encoding="utf-8")
js = (FRONTEND / "js" / "app.js").read_text(encoding="utf-8")
sidebar = (FRONTEND / "layout" / "sidebar.html").read_text(encoding="utf-8")
mobile_header = (FRONTEND / "layout" / "header.html").read_text(encoding="utf-8")
ai_chat = (FRONTEND / "layout" / "ai_chat.html").read_text(encoding="utf-8")
page_content = PAGE_MAP[page].read_text(encoding="utf-8")

sidebar = mark_active(sidebar, page)
ai_chat = ai_chat.replace("{{CHAT_MESSAGES}}", render_chat_messages())

# The JS must not blindly execute setAI(false) after the server has restored a
# chat session. This was the main reason the overlay closed immediately after
# sending a message.
js = js.replace("const SERVER_AI_OPEN = false;", f"const SERVER_AI_OPEN = {str(ai_param).lower()};")
js = js.replace("const SERVER_PAGE = null;", f"const SERVER_PAGE = {json.dumps(page)};")

# The visual baseline is deliberately untouched: same CSS, same HTML shell,
# same sidebar/header/page fragments, same component height.
document = (
    template
    .replace("{{CSS}}", css)
    .replace("{{SIDEBAR}}", sidebar)
    .replace("{{PAGE_CONTENT}}", page_content)
    .replace("{{AI_CHAT}}", ai_chat)
    .replace("{{MOBILE_HEADER}}", mobile_header)
    .replace("{{JS}}", js)
)

# Streamlit's native st.html is not iframe-isolated, so the existing frontend
# JavaScript can control navigation/query parameters reliably. Keep the legacy
# component fallback for older Streamlit versions that do not expose st.html.
try:
    st.html(document, unsafe_allow_javascript=True)
except (AttributeError, TypeError):
    import streamlit.components.v1 as components
    components.html(document, height=1550, scrolling=True)
