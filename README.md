# FinAI UI Prototype — Reset Baseline

This is a clean reset from the original pure-Python FinAI prototype.

## Structure
- `app.py` — Streamlit host/router
- `finai_ui/frontend/index.html` — master HTML shell
- `finai_ui/frontend/css/main.css` — visual baseline
- `finai_ui/frontend/js/app.js` — UI state + dummy AI chat
- `finai_ui/frontend/layout/` — reusable fragments
- `finai_ui/frontend/pages/` — multipage HTML views

## Pages
- Dashboard Kinerja
- Laporan Keuangan
- Rincian Data
- Setting Parameter

## AI
The assistant is a local JavaScript simulation:
- type a message
- press Enter or Send
- the user bubble appears
- a dummy AI response appears shortly afterward
- no API key or external AI service is needed

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

The original prototype's visual baseline is retained: green/lime palette, typography, cards, tables, sidebar geometry, AI overlay, and transition timings.

## Baseline v1 — Mobile Layer Architecture

`finai-main-4.zip` is the new baseline for subsequent work.

The shell hierarchy is intentionally flat:
- mobile header
- sidebar
- page content
- mobile backdrop
- AI overlay

The sidebar is a permanent sibling of the page content. JavaScript no longer
re-parents the sidebar between containers.

Mobile layer order:
1. Sidebar
2. Shadow/backdrop
3. FinAI mobile header
4. Page content

The sidebar and backdrop share the same top/bottom boundary. The FinAI header
uses the same top boundary and has a 74px visual height. The native Streamlit
toolbar/header remains outside this component.

The mobile hamburger and AI buttons are icon-only, without circular button
containers.
