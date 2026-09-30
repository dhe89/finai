from pathlib import Path
import re
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="FinAI", layout="wide", initial_sidebar_state="collapsed")

BASE_DIR = Path(__file__).resolve().parent
FRONTEND = BASE_DIR / "finai_ui" / "frontend"

PAGE_MAP = {
    "kinerja": FRONTEND / "pages" / "kinerja.html",
    "financial_report": FRONTEND / "pages" / "financial_report.html",
    "data_detail": FRONTEND / "pages" / "data_detail.html",
    "setting": FRONTEND / "pages" / "setting.html",
}

page = st.query_params.get("page", "kinerja")
if page not in PAGE_MAP:
    page = "kinerja"

template = (FRONTEND / "index.html").read_text(encoding="utf-8")
css = (FRONTEND / "css" / "main.css").read_text(encoding="utf-8")
js = (FRONTEND / "js" / "app.js").read_text(encoding="utf-8")
sidebar = (FRONTEND / "layout" / "sidebar.html").read_text(encoding="utf-8")
mobile_header = (FRONTEND / "layout" / "header.html").read_text(encoding="utf-8")
ai_chat = (FRONTEND / "layout" / "ai_chat.html").read_text(encoding="utf-8")


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

sidebar = mark_active(sidebar, page)

page_parts = []
for page_name, page_path in PAGE_MAP.items():
    content = page_path.read_text(encoding="utf-8")
    content = content.replace('id="desktopAI"', 'class="desktop-ai-trigger"')
    content = content.replace('class="desktop-ai-trigger desktop-ai-trigger"', 'class="desktop-ai-trigger"')
    active_class = " active" if page_name == page else ""
    page_parts.append(f'<div class="page-view{active_class}" data-page-view="{page_name}">{content}</div>')

page_stack = '<div class="page-stack">' + ''.join(page_parts) + '</div>'

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
