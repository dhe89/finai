"""Semantic intent routing for FinAI.

The router does not see financial data. Its only job is to translate a user's
natural-language question into a small, validated vocabulary that Python can
use to build deterministic evidence.
"""
import json
import re
import requests
import streamlit as st

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openrouter/free"

ALLOWED = {
    "scope": ["FINANCIAL", "META", "OUT_OF_SCOPE", "AMBIGUOUS"],
    "intent": [
        "LOOKUP", "OVERVIEW", "COMPARISON", "TREND", "DIAGNOSIS",
        "BREAKDOWN", "TARGET", "UNKNOWN"
    ],
    "metric": [
        "net_profit", "total_assets", "total_credit", "total_investment",
        "total_dpk", "total_other_funding", "revenue", "operating_expense",
        "ckpn", "npl_ratio", "ckpn_coverage", "low_cost_funding",
        "interest_income", "interest_expense", "other_operating_income",
        "other_operating_expense", "overview", "unknown"
    ],
    "dimension": [
        "income_statement_lines", "balance_sheet_lines", "loan_products",
        "investment_products", "dpk_products", "targets", "none"
    ],
    "focus": ["income", "expense", "asset", "liability", "equity", "none"],
}

SYSTEM_PROMPT = """Anda adalah semantic intent router untuk FinAI.
Tugas Anda BUKAN menjawab pertanyaan dan BUKAN mencari angka. Tugas Anda hanya
menerjemahkan bahasa natural pengguna menjadi intent terstruktur agar Python
bisa mengambil evidence dari CSV.

WAJIB:
- Jangan membuat angka, periode, fakta, atau jawaban.
- Jangan menjelaskan alasan.
- Kembalikan JSON SAJA, tanpa markdown dan tanpa teks lain.
- Gunakan hanya nilai dari daftar yang diizinkan.
- Jika maksud tidak jelas, gunakan scope AMBIGUOUS dan intent UNKNOWN.
- Jika pertanyaan bukan tentang data/keuangan FinAI, gunakan OUT_OF_SCOPE.
- Pertanyaan seperti "perkenalkan dirimu", "siapa kamu", atau "apa itu FinAI"
  adalah META.
- Untuk pertanyaan yang meminta kondisi/ringkasan kinerja, gunakan OVERVIEW dan
  metric overview.
- Untuk pertanyaan satu nilai, gunakan LOOKUP.
- Untuk membandingkan dua periode atau menanyakan naik/turun, gunakan COMPARISON.
- Untuk perkembangan beberapa periode, gunakan TREND.
- Untuk "kenapa/mengapa" atau diagnosis penyebab berdasarkan angka, gunakan DIAGNOSIS.
- Untuk pertanyaan "yang paling besar/menyumbang/tertinggi/terendah" atau rincian,
  gunakan BREAKDOWN dan pilih dimension yang sesuai.
- Untuk target/pencapaian, gunakan TARGET dan dimension targets.
- Metric adalah konsep yang diminta, bukan kata literal. Contoh: "berapa laba"
  -> net_profit; "posisi dana pihak ketiga" -> total_dpk.
- Jika pengguna menyebut item laporan yang spesifik seperti Kas, Modal, Pendapatan
  Bunga KPR Subsidi, jangan memaksa menjadi metric umum; gunakan dimension yang
  sesuai dan biarkan Python mencari line item yang benar.
- Untuk pertanyaan BREAKDOWN, gunakan focus: pendapatan/income -> income, beban/biaya ->
  expense, aset -> asset, kewajiban/liabilitas -> liability, modal/ekuitas -> equity.
  Jika tidak jelas, gunakan none.

JSON yang wajib dikembalikan:
{
  "scope": "FINANCIAL|META|OUT_OF_SCOPE|AMBIGUOUS",
  "intent": "LOOKUP|OVERVIEW|COMPARISON|TREND|DIAGNOSIS|BREAKDOWN|TARGET|UNKNOWN",
  "metric": "...satu nilai dari daftar...",
  "dimension": "...satu nilai dari daftar...",
  "focus": "income|expense|asset|liability|equity|none",
  "needs_clarification": true,
  "confidence": 0.0
}
"""


def _api_key():
    try:
        key = st.secrets.get("OPENROUTER_API_KEY", "") or st.secrets.get("api_key", "")
        return str(key).strip() if key else None
    except Exception:
        return None


def _extract_json(text):
    text = str(text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _valid(result):
    if not isinstance(result, dict):
        return None
    scope = result.get("scope")
    intent = result.get("intent")
    metric = result.get("metric")
    dimension = result.get("dimension")
    focus = result.get("focus", "none")
    if scope not in ALLOWED["scope"] or intent not in ALLOWED["intent"]:
        return None
    if metric not in ALLOWED["metric"] or dimension not in ALLOWED["dimension"] or focus not in ALLOWED["focus"]:
        return None
    return {
        "scope": scope,
        "intent": intent,
        "metric": metric,
        "dimension": dimension,
        "focus": focus,
        "needs_clarification": bool(result.get("needs_clarification", False)),
        "confidence": max(0.0, min(1.0, float(result.get("confidence", 0.0)))),
        "source": "LLM_INTENT",
    }


def classify_question(question, model=DEFAULT_MODEL, timeout=20):
    """Return a validated intent object. No financial data is sent to the router."""
    q = str(question or "").strip()
    if not q:
        return {
            "scope": "AMBIGUOUS", "intent": "UNKNOWN", "metric": "unknown",
            "dimension": "none", "focus": "none", "needs_clarification": True, "confidence": 1.0,
            "source": "LOCAL_EMPTY",
        }

    key = _api_key()
    if not key:
        return None

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": q},
        ],
        "temperature": 0.0,
        "max_tokens": 180,
        "reasoning": {"exclude": True},
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://demuy89.streamlit.app",
        "X-Title": "FinAI - Semantic Intent Router",
    }
    try:
        response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=timeout)
        if response.status_code != 200:
            return None
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        content = (choices[0].get("message") or {}).get("content", "")
        return _valid(_extract_json(content))
    except Exception:
        return None
