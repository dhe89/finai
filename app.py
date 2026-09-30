from pathlib import Path
import re
import json
import streamlit as st
import streamlit.components.v1 as components

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

# Chat state stays server-side. The browser only sends the user's text through
# the query string; the OpenRouter API key never reaches JavaScript.
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "ai_open" not in st.session_state:
    st.session_state.ai_open = False
if "last_chat_nonce" not in st.session_state:
    st.session_state.last_chat_nonce = None

page = st.query_params.get("page", "kinerja")
if page not in PAGE_MAP:
    page = "kinerja"

chat_query = st.query_params.get("finai_q")
chat_nonce = st.query_params.get("finai_n")

if chat_query:
    chat_query = str(chat_query).strip()
    chat_nonce = str(chat_nonce or "").strip()

    if chat_query and chat_nonce and chat_nonce != st.session_state.last_chat_nonce:
        st.session_state.last_chat_nonce = chat_nonce
        st.session_state.ai_open = True
        st.session_state.chat_messages.append({"role": "user", "content": chat_query})

        result = openrouter_chat(st.session_state.chat_messages)
        if result.get("ok"):
            answer = result["content"]
        else:
            answer = "⚠️ " + result.get("error", "LLM belum dapat merespons saat ini.")

        st.session_state.chat_messages.append({"role": "assistant", "content": answer})

    # Remove the one-shot transport parameters so a browser refresh does not
    # submit the same question again.
    try:
        st.query_params.pop("finai_q", None)
        st.query_params.pop("finai_n", None)
    except Exception:
        pass
    st.rerun()


def mark_active(html, active_page):
    def repl(match):
        attrs = match.group(1)
        active = f'data-page="{active_page}"' in attrs
        return '<div class="nav-item' + (' active' if active else '') + '"' + attrs + '>'

    return re.sub(
        r'<div class="nav-item(?: active)?(\s+data-page="[^"]+"\s+tabindex="0")>',
        repl,
        html,
    )


def esc_json(value):
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


template = (FRONTEND / "index.html").read_text(encoding="utf-8")
css = (FRONTEND / "css" / "main.css").read_text(encoding="utf-8")
js = (FRONTEND / "js" / "app.js").read_text(encoding="utf-8")
sidebar = (FRONTEND / "layout" / "sidebar.html").read_text(encoding="utf-8")
mobile_header = (FRONTEND / "layout" / "header.html").read_text(encoding="utf-8")
ai_chat = (FRONTEND / "layout" / "ai_chat.html").read_text(encoding="utf-8")

sidebar = mark_active(sidebar, page)

page_parts = []
for page_name, page_path in PAGE_MAP.items():
    content = page_path.read_text(encoding="utf-8")
    content = content.replace('id="desktopAI"', 'class="desktop-ai-trigger"')
    content = content.replace('class="desktop-ai-trigger desktop-ai-trigger"', 'class="desktop-ai-trigger"')
    active_class = " active" if page_name == page else ""
    page_parts.append(f'<div class="page-view{active_class}" data-page-view="{page_name}">{content}</div>')

page_stack = '<div class="page-stack">' + ''.join(page_parts) + '</div>'

chat_json = esc_json(st.session_state.chat_messages[-30:])
ai_open = "true" if st.session_state.ai_open else "false"
ai_chat = ai_chat.replace("{{CHAT_MESSAGES}}", chat_json).replace("{{AI_OPEN}}", ai_open).replace("{{AI_OPEN_CLASS}}", "" if st.session_state.ai_open else "closed").replace("{{AI_HIDDEN}}", "false" if st.session_state.ai_open else "true")

# Tell JS the page selected by the server. This does not alter the existing UI.
js = js.replace("const SERVER_PAGE = null;", f"const SERVER_PAGE = {json.dumps(page)};")

# Preserve the baseline layout and only inject the AI transport/state values.
document = (
    template
    .replace("{{CSS}}", css)
    .replace("{{SIDEBAR}}", sidebar)
    .replace("{{PAGE_CONTENT}}", page_stack)
    .replace("{{AI_CHAT}}", ai_chat)
    .replace("{{MOBILE_HEADER}}", mobile_header)
    .replace("{{JS}}", js)
)

components.html(document, height=1550, scrolling=True)
