import streamlit as st
import requests
import html
import re
import json

st.set_page_config(
    page_title="FinAI — Financial Intelligence",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# OPENROUTER
# ============================================================

def get_api_key():
    try:
        if "OPENROUTER_API_KEY" in st.secrets:
            return st.secrets["OPENROUTER_API_KEY"]
        if "api_key" in st.secrets:
            return st.secrets["api_key"]
    except Exception:
        pass
    return None

OPENROUTER_API_KEY = get_api_key()

# Free-first routing. If a specific free provider is rate-limited,
# the app tries the next model and finally OpenRouter's free router.
FREE_MODELS = ["openrouter/free"]
SYSTEM_PROMPT = (
    "You are FinAI, a Financial Intelligence Assistant. "
    "Answer in clear, concise Indonesian unless the user uses another language. "
    "Use only the supplied financial context. Do not invent figures. "
    "Distinguish facts from interpretation. If data is insufficient, say so. "
    "Keep answers practical and suitable for management-level financial analysis."
)

FINANCIAL_CONTEXT = (
    "Reporting period: September 2026\n"
    "Current: Total Assets 190,510.7; Total Credit 104,549.2; "
    "Total DPK 158,545.5; Net Profit 699.1.\n"
    "Previous month: Total Assets 194,349.9; Total Credit 106,885.6; "
    "Total DPK 163,153.8; Net Profit 812.4.\n"
    "Target: Total Assets 192,871.1; Total Credit 101,808.3; "
    "Total DPK 160,414.1; Net Profit 727.1.\n"
    "Profitability: Revenue 1,255.2; Operating Expense 556.1; "
    "CKPN 207.9; Net Profit 699.1.\n"
    "Asset Quality: NPL Ratio 4.2%; Target NPL 2.2%; "
    "CKPN Coverage 115.9%; Target Coverage 110.0%; "
    "Low Cost Funding 77.4%; Target 81.0%.\n"
    "Historical: Last year Net Profit 890.5; Last year NPL 3.6%; "
    "Last year CKPN Coverage 107.0%."
)


def call_openrouter(messages, max_tokens=500):
    if not OPENROUTER_API_KEY:
        return (
            "API key OpenRouter belum ditemukan. "
            "Pastikan Streamlit Secrets berisi OPENROUTER_API_KEY "
            "atau api_key."
        )

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://demuy89.streamlit.app",
        # Keep HTTP header value ASCII-only. Python/urllib3 otherwise can
        # raise UnicodeEncodeError when sending non-Latin-1 characters.
        "X-Title": "FinAI - Financial Intelligence",
    }

    errors = []

    for model in FREE_MODELS:
        try:
            response = requests.post(
                url,
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": max_tokens,
                },
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                choices = data.get("choices", [])
                if choices:
                    message = choices[0].get("message", {}) or {}
                    answer = message.get("content")
                    if isinstance(answer, list):
                        answer = "".join(
                            str(part.get("text", "")) if isinstance(part, dict) else str(part)
                            for part in answer
                        )
                    # Some reasoning-capable responses may expose text in
                    # another message field. Accept it instead of treating
                    # the successful API response as empty.
                    if not answer:
                        answer = message.get("reasoning") or choices[0].get("text")
                    if isinstance(answer, list):
                        answer = "".join(str(x) for x in answer)
                    if answer:
                        return str(answer).strip()
                errors.append(f"{model}: empty response")
                continue

            try:
                err = response.json().get("error", {})
                message = err.get("message", response.text)
            except Exception:
                message = response.text

            # Authentication/configuration errors will not be fixed by trying
            # another model. Other routing/provider errors can be retried.
            errors.append(f"{model} HTTP {response.status_code}: {message}")
            if response.status_code in (401, 403):
                break

        except requests.RequestException as exc:
            errors.append(f"{model}: {exc}")

    return "LLM belum dapat merespons saat ini. Detail: " + " | ".join(errors[-3:])


if "messages" not in st.session_state:
    st.session_state.messages = []

if "llm_test_result" not in st.session_state:
    st.session_state.llm_test_result = None

if "last_finai_nonce" not in st.session_state:
    st.session_state.last_finai_nonce = None

if "ai_open" not in st.session_state:
    st.session_state.ai_open = False

# Messages are rendered inside the AI overlay. The iframe sends the user's
# question through the page query string; Python processes it server-side so
# the OpenRouter API key never reaches browser JavaScript.
finai_query = st.query_params.get("finai_q")
finai_nonce = st.query_params.get("finai_n")
if finai_query:
    finai_query = str(finai_query).strip()
    finai_nonce = str(finai_nonce or "").strip()
    # Nonce-based deduplication lets the user send the exact same question
    # again while preventing a browser refresh from submitting it twice.
    if finai_query and finai_nonce and st.session_state.get("last_finai_nonce") != finai_nonce:
        st.session_state.ai_open = True
        st.session_state.last_finai_nonce = finai_nonce
        st.session_state.messages.append({"role": "user", "content": finai_query})

        llm_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": "Dashboard financial context:\n" + FINANCIAL_CONTEXT},
        ]
        # Keep the request small and predictable for free models.
        llm_messages.extend(st.session_state.messages[-8:])

        answer = call_openrouter(llm_messages, max_tokens=350)
        st.session_state.messages.append({"role": "assistant", "content": answer})

        try:
            if "finai_q" in st.query_params:
                del st.query_params["finai_q"]
            if "finai_n" in st.query_params:
                del st.query_params["finai_n"]
        except Exception:
            pass
        st.rerun()


# ============================================================
# FINAL UI
# ============================================================

HTML = r'''
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<style>
*{box-sizing:border-box}
button{font:inherit;cursor:pointer}
:root{--green:#005642;--green2:#08735d;--lime:#b7f51d;--bg:#f4f7f5;--line:#e7ece9;--muted:#8d9793}
.finai-root{position:relative;width:100%;height:calc(100vh - 110px);min-height:680px;background:#f4f7f5;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#18211f;overflow:hidden}.app{position:relative;width:100%;height:100%;min-height:0;display:grid;grid-template-columns:250px minmax(0,1fr);background:var(--bg);overflow:hidden;align-items:stretch}
.app.left-collapsed{grid-template-columns:72px minmax(0,1fr)}
.left{position:relative;background:var(--green);color:#fff;padding:18px 14px 18px;min-width:0;height:100%;align-self:stretch;overflow:hidden;z-index:20}
.sidebar-head{height:42px;display:flex;align-items:center;justify-content:space-between;gap:8px;margin:0 2px 24px}
.brand{display:flex;align-items:center;gap:10px;font-size:20px;font-weight:800;white-space:nowrap;min-width:0}
.brand-mark{width:30px;height:30px;border-radius:9px;background:var(--lime);color:var(--green);display:grid;place-items:center;font-weight:900;flex:none}
.sidebar-toggle{width:34px;height:34px;border-radius:10px;border:1px solid #ffffff30;background:#ffffff18;color:#fff;display:grid;place-items:center;font-size:19px;line-height:1;flex:none;position:relative;z-index:50;pointer-events:auto;touch-action:manipulation}
.nav{display:flex;flex-direction:column;gap:8px}
.nav-item{height:46px;border-radius:13px;display:flex;align-items:center;gap:12px;padding:0 12px;color:#d9ece6;font-size:14px;font-weight:650;white-space:nowrap}
.nav-item.active{background:#14765f;color:#fff}
.nav-icon{width:22px;text-align:center;flex:none;font-size:14px}
.app.left-collapsed .brand-text,.app.left-collapsed .nav-text,.app.left-collapsed .config-text,.app.left-collapsed .config-pill,.app.left-collapsed .status{display:none}
.app.left-collapsed .sidebar-head{justify-content:center;margin-left:0;margin-right:0}
.app.left-collapsed .brand{justify-content:center}
.app.left-collapsed .sidebar-toggle{position:absolute;top:22px;right:7px;width:26px;height:26px;border-radius:8px;font-size:15px;background:#ffffff18}
.app.left-collapsed .brand-mark{width:32px;height:32px}
.app.left-collapsed .nav-item{justify-content:center;padding:0}
.config{position:absolute;left:14px;right:14px;bottom:18px;border-top:1px solid #ffffff1f;padding-top:15px;color:#9ac3b8;font-size:9px;letter-spacing:1.3px}
.config-pill{margin-top:9px;padding:7px 9px;border-radius:7px;background:#fff;color:#60736e;letter-spacing:0;font-size:9px}
.status{margin-top:8px;color:#d2e7e1;font-size:9px;letter-spacing:0}
.dot{display:inline-block;width:5px;height:5px;border-radius:50%;background:var(--lime);margin-right:5px}
.main{position:relative;min-width:0;height:100%;min-height:0;overflow:auto;padding:28px clamp(20px,3vw,44px) 44px}
.desktop-header{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:20px;min-height:42px}
.desktop-header-left{display:flex;align-items:center;gap:10px;min-width:0}
.desktop-app-name{font-size:13px;font-weight:800;color:#65716c}
.desktop-ai-trigger{width:40px;height:40px;border-radius:50%;border:1px solid #e4e9e6;background:#fff;color:var(--green);display:grid;place-items:center;box-shadow:0 4px 12px #0000000d;font-size:18px}
.topbar{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:20px}
.eyebrow{color:#a0aaa6;font-size:9px;letter-spacing:2px;font-weight:700}.title{font-size:31px;line-height:1.05;font-weight:800;margin:3px 0 0}.subtitle{color:#9aa49f;font-size:11px;margin-top:7px}.period{background:#eff6d9;color:#6c7d42;border-radius:18px;padding:10px 15px;font-size:10px;font-weight:700;white-space:nowrap}
.metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:14px}.card{background:#fff;border:1px solid #edf0ef;border-radius:17px;box-shadow:0 7px 20px #1e41370b}.metric{padding:17px}.metric-label{color:#909b97;font-size:10px}.metric-value{font-size:22px;font-weight:800;margin-top:6px}.metric-change{color:#a78282;font-size:8px;margin-top:5px}
.table-card{overflow:hidden}.table-head{display:flex;justify-content:space-between;align-items:center;padding:16px 17px 12px}.table-title{font-size:14px;font-weight:800}.caption{font-size:8px;color:#9ba5a1;margin-top:3px}.switcher{background:#f0f6df;color:#718044;border-radius:18px;padding:8px 12px;font-size:9px;font-weight:700}.data-wrap{overflow-x:auto}table{width:100%;min-width:680px;border-collapse:collapse;font-size:8px}th{color:#a1aaa7;font-weight:600;padding:8px 12px;text-align:right;border-top:1px solid var(--line)}th:first-child,td:first-child{text-align:left}td{color:#737d79;padding:10px 12px;text-align:right;border-top:1px solid #edf0ef}tr.section td{background:#eef5ef;color:#64806f;font-size:9px;letter-spacing:1.5px;font-weight:800;text-align:left;padding:8px 12px}
.bottom{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:12px}.small{padding:16px}.small-title{font-size:12px;font-weight:800}.kpi{display:flex;justify-content:space-between;margin-top:15px;font-size:9px}.kpi-label{color:#68736f}.kpi-value{font-size:11px;font-weight:800}
.ai{position:absolute;z-index:200;top:0;right:0;bottom:0;height:100%;width:min(390px,42%);background:#fff;border-left:1px solid #e2e9e5;display:flex;flex-direction:column;overflow:hidden;box-shadow:-14px 0 40px #00000016;transform:translateX(105%);opacity:0;visibility:hidden;transition:transform .24s ease,opacity .18s ease,visibility .24s ease}
.ai.open{transform:translateX(0);opacity:1;visibility:visible}
.ai-head{position:relative;z-index:2;flex:none;padding:14px 14px 12px;min-height:66px;border-bottom:1px solid #edf0ef;display:flex;justify-content:space-between;align-items:flex-start}.ai-title{font-size:16px;font-weight:800}.ai-status{color:#9ba49f;font-size:8px;margin-top:5px}.ai-close{position:relative;z-index:3;flex:none;width:38px;height:38px;border:0;border-radius:50%;background:#f0f2f1;color:#7c8581;font-size:22px;display:grid;place-items:center}.ai-body{padding:24px 18px;overflow:auto;flex:1;min-height:0;overscroll-behavior:contain}.msg{display:flex;gap:10px;margin-bottom:22px}.msg.user{justify-content:flex-end;padding-left:28px}.msg.user .bubble{display:block;max-width:min(82%,300px);padding:10px 13px;border-radius:14px 14px 4px 14px;background:#005642;color:#fff;font-size:11px;line-height:1.45;word-break:break-word;box-shadow:0 3px 10px #00564218}.msg.user.local-pending .bubble{background:#005642;color:#fff}.bot{width:22px;height:22px;border-radius:50%;background:var(--green);color:var(--lime);display:grid;place-items:center;flex:none;font-size:11px}.msgtext{font-size:11px;line-height:1.55;flex:1;min-width:0;max-width:calc(100% - 32px);overflow-wrap:anywhere;word-break:break-word}.ai-response{color:#2f3936}.ai-response>div{margin:0 0 6px}.ai-response ul{margin:4px 0 8px;padding-left:18px}.ai-response li{margin:0 0 4px}.ai-response code{background:#f1f4f2;border-radius:4px;padding:1px 4px;font-size:.92em}.md-spacer{height:3px}.muted{color:#9ba49f}.ai-foot{padding:10px 14px 14px;border-top:1px solid #edf0ef}.ai-input-row{display:flex;gap:8px}.ai-input{flex:1;min-width:0;border:1px solid #e1e5e3;border-radius:10px;padding:11px 12px;color:#18211f;font-size:10px;outline:none}.ai-input:focus{border-color:#9bb8ae}.ai-send{width:42px;border:0;border-radius:10px;background:var(--lime);color:#25410d;font-size:15px;font-weight:800}.ai-send:disabled{opacity:.55;cursor:wait}.send{width:100%;border:0;border-radius:9px;padding:10px;background:var(--lime);color:#25410d;font-size:9px;font-weight:800}
.mobile-head{display:none}
.finai-root.mobile-view{height:auto;min-height:100dvh;overflow:visible}.finai-root.mobile-view .app,.finai-root.mobile-view .app.left-collapsed{display:block;min-height:100dvh;height:auto;overflow:visible}
.finai-root.mobile-view .left{position:fixed;z-index:300;inset:0 auto 0 0;width:min(82vw,320px);height:100dvh;transform:translateX(-105%);transition:transform .25s ease;box-shadow:12px 0 40px #0003;padding:18px 16px}
.finai-root.mobile-view .left.mobile-open{transform:translateX(0)}
.finai-root.mobile-view .main{padding:96px 18px 38px;overflow:visible}
.finai-root.mobile-view .desktop-header{display:none}
.finai-root.mobile-view .mobile-head{display:flex;position:fixed;top:0;left:0;right:0;height:74px;z-index:250;background:#fff;border-bottom:1px solid #edf0ef;align-items:center;justify-content:center}
.finai-root.mobile-view .mobile-menu{position:absolute;left:18px;top:16px;width:42px;height:42px;border-radius:50%;border:1px solid #e7ebe9;background:#fff;font-size:21px;color:#66716d}
.finai-root.mobile-view .mobile-brand{display:flex;align-items:center;gap:8px;font-size:17px;font-weight:800}
.finai-root.mobile-view .mobile-ai{position:absolute;right:18px;top:16px;width:42px;height:42px;border-radius:50%;border:1px solid #e7ebe9;background:#fff;color:var(--green);font-size:17px}
.finai-root.mobile-view .mobile-overlay{display:none;position:fixed;inset:0;z-index:280;background:#00302655}
.finai-root.mobile-view .mobile-overlay.show{display:block}
.finai-root.mobile-view .ai-head{padding-top:max(14px,env(safe-area-inset-top));min-height:70px}.finai-root.mobile-view .ai-body{padding-bottom:20px}.finai-root.mobile-view .ai-foot{padding-bottom:max(14px,env(safe-area-inset-bottom))}.finai-root.mobile-view .main{width:100%;max-width:100%;overflow-x:hidden}
.finai-root.mobile-view .ai{position:fixed;z-index:500;top:0;right:0;bottom:0;left:0;width:100vw;height:100dvh;min-height:0;border:0;box-shadow:none}
@media(max-width:800px){
 .finai-root{height:auto;min-height:100dvh;overflow:visible}.app,.app.left-collapsed{display:block;min-height:100dvh;height:auto;overflow:visible}
 .left{position:fixed;z-index:300;inset:0 auto 0 0;width:min(78vw,320px);height:100dvh;transform:translateX(-105%);transition:transform .25s ease;box-shadow:12px 0 40px #0003;padding:18px 16px}
 .left.mobile-open{transform:translateX(0)}.app.left-collapsed .left{padding:18px 16px}.app.left-collapsed .brand-text,.app.left-collapsed .nav-text,.app.left-collapsed .config-text,.app.left-collapsed .config-pill,.app.left-collapsed .status{display:inline}.app.left-collapsed .sidebar-head{justify-content:space-between;margin-left:2px;margin-right:2px}.app.left-collapsed .brand{justify-content:flex-start}.app.left-collapsed .sidebar-toggle{position:static;width:34px;height:34px;border-radius:10px;font-size:19px;background:#ffffff12}.app.left-collapsed .nav-item{justify-content:flex-start;padding:0 12px}
 .main{padding:96px 18px 38px;overflow:visible}.desktop-header{display:none}.topbar{margin-bottom:20px}.title{font-size:29px}.metrics{gap:12px}.metric{padding:17px}.metric-value{font-size:20px}.bottom{grid-template-columns:1fr}
 .mobile-head{display:flex;position:fixed;top:0;left:0;right:0;height:74px;z-index:250;background:#fff;border-bottom:1px solid #edf0ef;align-items:center;justify-content:center}.mobile-menu{position:absolute;left:18px;top:16px;width:42px;height:42px;border-radius:50%;border:1px solid #e7ebe9;background:#fff;font-size:21px;color:#66716d}.mobile-brand{display:flex;align-items:center;gap:8px;font-size:17px;font-weight:800}.mobile-ai{position:absolute;right:18px;top:16px;width:42px;height:42px;border-radius:50%;border:1px solid #e7ebe9;background:#fff;color:var(--green);font-size:17px}
 .ai{z-index:500;inset:0;width:100vw;height:100dvh;border:0;box-shadow:none}.mobile-overlay{display:none;position:fixed;inset:0;z-index:280;background:#00302655}.mobile-overlay.show{display:block}
}
@media(min-width:801px){
  .mobile-head,.mobile-overlay{display:none}
  .finai-root{height:calc(100vh - 110px);min-height:680px;overflow:hidden}
  .app{height:100%;min-height:0;grid-template-columns:250px minmax(0,1fr)}
  .app.left-collapsed{grid-template-columns:72px minmax(0,1fr)}
  .left,.main{height:100%;min-height:0}
  .ai{top:0;bottom:0;height:100%;min-height:0}
}

.ai-thinking .msgtext{display:flex;align-items:center;gap:7px;color:#6f7b76}.thinking-label{font-size:12px}.thinking-dots{display:inline-flex;gap:3px;align-items:center}.thinking-dots i{width:4px;height:4px;border-radius:50%;background:#0b765f;animation:finaiDot 1.1s infinite ease-in-out}.thinking-dots i:nth-child(2){animation-delay:.15s}.thinking-dots i:nth-child(3){animation-delay:.3s}@keyframes finaiDot{0%,70%,100%{opacity:.25;transform:translateY(0)}35%{opacity:1;transform:translateY(-2px)}}
</style>
</head>
<body>
<div id="finaiRoot" class="finai-root">
<div id="app" class="app">
  <aside id="left" class="left">
    <div class="sidebar-head"><div class="brand"><span class="brand-mark">✦</span><span class="brand-text">FinAI</span></div><button type="button" id="leftToggle" class="sidebar-toggle" aria-label="Collapse navigation" aria-expanded="true">☰</button></div>
    <nav class="nav">
      <div class="nav-item active"><span class="nav-icon">▣</span><span class="nav-text">Dashboard Kinerja</span></div>
      <div class="nav-item"><span class="nav-icon">▤</span><span class="nav-text">Laporan Keuangan</span></div>
      <div class="nav-item"><span class="nav-icon">◉</span><span class="nav-text">Rincian Data</span></div>
      <div class="nav-item"><span class="nav-icon">⚙</span><span class="nav-text">Setting Parameter</span></div>
    </nav>
    <div class="config"><span class="config-text">AI CONFIGURATION</span><div class="config-pill">OpenRouter · Free LLM</div><div class="status"><span class="dot"></span>Financial Intelligence</div></div>
  </aside>

  <main class="main">
    <div class="desktop-header"><div class="desktop-header-left"><div class="desktop-app-name">FinAI</div></div><button type="button" id="desktopAI" class="desktop-ai-trigger" aria-label="Open AI Assistant" title="Open AI Assistant">✦</button></div>
    <div class="topbar"><div><div class="eyebrow">FINANCIAL INTELLIGENCE</div><div class="title">Overview</div><div class="subtitle">Financial performance overview for September 2026</div></div><div class="period">September 2026⌄</div></div>
    <div class="metrics">
      <div class="card metric"><div class="metric-label">Total Assets</div><div class="metric-value">190,510.7</div><div class="metric-change">-1.98% vs last month</div></div>
      <div class="card metric"><div class="metric-label">Total Credit</div><div class="metric-value">104,549.2</div><div class="metric-change">-2.19% vs last month</div></div>
      <div class="card metric"><div class="metric-label">Total DPK</div><div class="metric-value">158,545.5</div><div class="metric-change">-2.82% vs last month</div></div>
      <div class="card metric"><div class="metric-label">Net Profit</div><div class="metric-value">699.1</div><div class="metric-change">-13.94% vs last month</div></div>
    </div>
    <section class="card table-card"><div class="table-head"><div><div class="table-title">Performance Overview</div><div class="caption">Current position, historical context and target achievement</div></div><div class="switcher">Monthly · YTD · YoY</div></div><div class="data-wrap"><table><thead><tr><th>Keterangan</th><th>Tahun Lalu</th><th>Bulan Lalu</th><th>Bulan Ini</th><th>Target</th><th>Ach.</th></tr></thead><tbody>
      <tr class="section"><td colspan="6">ASSET</td></tr><tr><td>Total Asset</td><td>173,731.1</td><td>194,349.9</td><td>190,510.7</td><td>192,871.1</td><td>98.8%</td></tr><tr><td>Total Credit</td><td>122,208.6</td><td>106,885.6</td><td>104,549.2</td><td>101,808.3</td><td>102.7%</td></tr><tr><td>Total Investment</td><td>76,318.9</td><td>79,825.3</td><td>79,599.7</td><td>80,855.6</td><td>98.4%</td></tr>
      <tr class="section"><td colspan="6">FUNDING</td></tr><tr><td>Total DPK</td><td>146,764.4</td><td>163,153.8</td><td>158,545.5</td><td>160,414.1</td><td>98.8%</td></tr><tr><td>Total Other Funding</td><td>4,460.0</td><td>4,980.0</td><td>5,045.0</td><td>5,040.0</td><td>100.1%</td></tr><tr><td>Low Cost Funding %</td><td>88.3</td><td>78.0</td><td>77.4</td><td>81.0</td><td>95.6%</td></tr>
      <tr class="section"><td colspan="6">PROFITABILITY</td></tr><tr><td>Revenue</td><td>1,373.4</td><td>1,274.2</td><td>1,255.2</td><td>1,378.0</td><td>91.1%</td></tr><tr><td>Operating Expense</td><td>482.9</td><td>461.8</td><td>556.1</td><td>535.4</td><td>103.9%</td></tr><tr><td>CKPN</td><td>210.9</td><td>106.9</td><td>207.9</td><td>198.0</td><td>105.0%</td></tr><tr><td>Net Profit</td><td>890.5</td><td>812.4</td><td>699.1</td><td>727.1</td><td>96.1%</td></tr>
      <tr class="section"><td colspan="6">ASSET QUALITY</td></tr><tr><td>NPL Ratio</td><td>3.6</td><td>0.0</td><td>4.2</td><td>2.2</td><td>190.9%</td></tr><tr><td>CKPN Coverage</td><td>107.0</td><td>114.3</td><td>115.9</td><td>110.0</td><td>105.4%</td></tr>
    </tbody></table></div></section>
    <div class="bottom"><div class="card small"><div class="small-title">Profitability</div><div class="caption">Revenue, expense and net profit</div><div class="kpi"><span class="kpi-label">Revenue</span><span class="kpi-value">1,255.2</span></div><div class="kpi"><span class="kpi-label">Operating Expense</span><span class="kpi-value">556.1</span></div><div class="kpi"><span class="kpi-label">Net Profit</span><span class="kpi-value">699.1</span></div></div><div class="card small"><div class="small-title">Asset Quality</div><div class="caption">Risk indicators and coverage</div><div class="kpi"><span class="kpi-label">NPL Ratio</span><span class="kpi-value">4.20%</span></div><div class="kpi"><span class="kpi-label">CKPN Coverage</span><span class="kpi-value">115.93%</span></div><div class="kpi"><span class="kpi-label">Low Cost Funding</span><span class="kpi-value">77.40%</span></div></div></div>
  </main>

  <aside id="ai" class="ai" aria-hidden="true">
    <div class="ai-head"><div><div class="ai-title">AI Assistant</div><div class="ai-status"><span class="dot"></span>Ready to assist</div></div><button id="aiClose" class="ai-close" aria-label="Close AI Assistant">×</button></div>
    <div id="aiBody" class="ai-body">__AI_MESSAGES__</div>
    <div class="ai-foot"><div class="ai-input-row"><input id="aiInput" class="ai-input" placeholder="Tanyakan sesuatu tentang kinerja keuangan..." autocomplete="off"><button id="aiSend" class="ai-send" aria-label="Send">↑</button></div></div>
  </aside>
</div>

<div class="mobile-head"><button type="button" id="mobileMenu" class="mobile-menu" aria-label="Open navigation">☰</button><div class="mobile-brand"><span class="brand-mark">✦</span>FinAI</div><button type="button" id="mobileAI" class="mobile-ai" aria-label="Open AI Assistant">✦</button></div>
<div id="mobileOverlay" class="mobile-overlay"></div>
</div>

<script>
const root=document.getElementById('finaiRoot');
const app=document.getElementById('app');
const left=document.getElementById('left');
const ai=document.getElementById('ai');
const leftToggle=document.getElementById('leftToggle');
const aiClose=document.getElementById('aiClose');
const desktopAI=document.getElementById('desktopAI');
const mobileAI=document.getElementById('mobileAI');
const mobileMenu=document.getElementById('mobileMenu');
const overlay=document.getElementById('mobileOverlay');
const aiBody=document.getElementById('aiBody');
const aiInput=document.getElementById('aiInput');
const aiSend=document.getElementById('aiSend');
let leftCollapsed=false;
function parentWidth(){try{return window.parent.innerWidth||window.innerWidth;}catch(e){return window.innerWidth;}}
function isMobile(){return parentWidth()<=800;}
function syncMobileClass(){root.classList.toggle('mobile-view',isMobile());}
function setAI(open){ai.classList.toggle('open',!!open);ai.setAttribute('aria-hidden',String(!open));if(open){setTimeout(()=>aiInput.focus(),250);}}
function setSidebarCollapsed(collapsed){
  leftCollapsed=!!collapsed;
  app.classList.toggle('left-collapsed',leftCollapsed);
  leftToggle.textContent='☰';
  leftToggle.setAttribute('aria-expanded',String(!leftCollapsed));
  leftToggle.setAttribute('aria-label',leftCollapsed?'Expand navigation':'Collapse navigation');
}
function toggleSidebar(){
  if(isMobile()){
    const open=!left.classList.contains('mobile-open');
    left.classList.toggle('mobile-open',open);
    overlay.classList.toggle('show',open);
  }else{
    setSidebarCollapsed(!leftCollapsed);
  }
}
function syncResponsive(){
  syncMobileClass();
  if(isMobile()){
    app.classList.remove('left-collapsed');
    leftCollapsed=false;
    overlay.classList.toggle('show',left.classList.contains('mobile-open'));
  }else{
    left.classList.remove('mobile-open');
    overlay.classList.remove('show');
    setSidebarCollapsed(leftCollapsed);
  }
}
function addLocalUserBubble(text){
  const row=document.createElement('div');
  row.className='msg user local-pending';
  row.innerHTML='<div class="bubble"></div>';
  row.querySelector('.bubble').textContent=text;
  aiBody.appendChild(row);
  aiBody.scrollTop=aiBody.scrollHeight;
}

function addThinkingBubble(){
  const row=document.createElement('div');
  row.className='msg ai-thinking';
  row.innerHTML='<div class="bot">✦</div><div class="msgtext"><span class="thinking-label">FinAI sedang menganalisis</span><span class="thinking-dots"><i></i><i></i><i></i></span></div>';
  aiBody.appendChild(row);
  aiBody.scrollTop=aiBody.scrollHeight;
  return row;
}

const SERVER_MESSAGES=__SERVER_MESSAGES_JSON__;
const CHAT_KEY='finai_chat_history_v2';

function readLocalHistory(){
  try{
    const raw=localStorage.getItem(CHAT_KEY);
    const parsed=raw?JSON.parse(raw):[];
    return Array.isArray(parsed)?parsed:[];
  }catch(e){return [];}
}
function writeLocalHistory(messages){
  try{
    localStorage.setItem(CHAT_KEY,JSON.stringify((messages||[]).slice(-50)));
  }catch(e){}
}
function mergeServerHistory(localMsgs, serverMsgs){
  const local=Array.isArray(localMsgs)?localMsgs:[];
  const server=Array.isArray(serverMsgs)?serverMsgs:[];
  if(!server.length) return local.slice(-50);

  // Server history is authoritative after an AI response has completed.
  // The only time local history should be newer is immediately after the
  // user submits a message and before the server finishes processing it.
  if(server.length >= local.length) return server.slice(-50);

  // Preserve a locally pending message while the server is processing it.
  return local.slice(-50);
}
function escapeText(value){
  return String(value ?? '');
}
function renderMessageList(messages){
  const greeting=`<div class="msg"><div class="bot">✦</div><div class="msgtext"><b>Hi there! 👋</b><br><span class="muted">I'm your Financial AI Assistant.<br>Ask me about the dashboard performance.</span></div></div>`;
  aiBody.innerHTML=greeting;
  for(const m of (messages||[])){
    if(!m || !m.role || !m.content) continue;
    const row=document.createElement('div');
    row.className='msg'+(m.role==='user'?' user':'');
    if(m.role==='user'){
      const bubble=document.createElement('div');
      bubble.className='bubble';
      bubble.textContent=escapeText(m.content);
      row.appendChild(bubble);
    }else{
      row.innerHTML='<div class="bot">✦</div><div class="msgtext ai-response"></div>';
      const box=row.querySelector('.msgtext');
      const safe=escapeText(m.content)
        .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
        .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
        .replace(/\n/g,'<br>');
      box.innerHTML=safe;
    }
    aiBody.appendChild(row);
  }
  aiBody.scrollTop=aiBody.scrollHeight;
}

function hydrateHistory(){
  const local=readLocalHistory();
  const merged=mergeServerHistory(local,SERVER_MESSAGES);

  // Once Python has produced a response, synchronize the browser history.
  if(Array.isArray(SERVER_MESSAGES) && SERVER_MESSAGES.length >= local.length){
    writeLocalHistory(merged);
  }

  renderMessageList(merged);
}

function sendMessage(){
  const text=aiInput.value.trim();
  if(!text || aiSend.disabled)return;

  aiSend.disabled=true;
  aiInput.disabled=true;
  aiInput.value='';

  // Immediate visual acknowledgement.
  addLocalUserBubble(text);
  addThinkingBubble();

  const local=readLocalHistory();
  local.push({role:'user',content:text});
  writeLocalHistory(local);

  const nonce=Date.now().toString(36)+'_'+Math.random().toString(36).slice(2,8);

  // Build the URL from the current top-level document. Do NOT use
  // components.html, window.parent, or window.top here. This app uses
  // st.html, so this is a normal page navigation and cannot create
  // another copy of the Streamlit application inside an iframe.
  const target=new URL(window.location.href);
  target.searchParams.set('finai_q',text);
  target.searchParams.set('finai_n',nonce);

  // Navigation happens directly from the click/Enter event so browsers
  // cannot treat it as an unsolicited iframe navigation.
  window.location.assign(target.toString());
}

leftToggle.addEventListener('pointerup',(e)=>{e.preventDefault();e.stopPropagation();toggleSidebar();});
leftToggle.addEventListener('keydown',(e)=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();toggleSidebar();}});
aiClose.addEventListener('click',()=>setAI(false));
desktopAI.addEventListener('click',()=>setAI(true));
mobileAI.addEventListener('click',()=>setAI(true));
mobileMenu.addEventListener('click',(e)=>{e.preventDefault();e.stopPropagation();toggleSidebar();});
overlay.addEventListener('click',()=>{left.classList.remove('mobile-open');overlay.classList.remove('show');});
aiSend.addEventListener('click',sendMessage);
aiInput.addEventListener('keydown',e=>{if(e.key==='Enter')sendMessage();});
window.addEventListener('resize',syncResponsive);
window.addEventListener('orientationchange',syncResponsive);
setSidebarCollapsed(false);
hydrateHistory();
setAI(__AI_OPEN__);
syncResponsive();
</script>
</body>
</html>
'''

# Render chat history directly in the single Streamlit page. No iframe is
# created, so submitting a second message cannot recursively create another
# copy of the application.
server_messages_json = json.dumps(st.session_state.messages, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
HTML = HTML.replace("__AI_MESSAGES__", "")
HTML = HTML.replace("__SERVER_MESSAGES_JSON__", server_messages_json)
HTML = HTML.replace("__AI_OPEN__", "true" if st.session_state.ai_open else "false")

st.html(HTML, unsafe_allow_javascript=True)
