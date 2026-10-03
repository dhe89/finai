"""FinAI multi-provider LLM router with planner-driven selective evidence.

Flow:
    User question
        -> LLM Evidence Planner (metadata dictionary only)
        -> Python Evidence Engine (numbers/calculations)
        -> LLM Financial Analyst (evidence only)
        -> answer

The planner never receives financial values. Python is the only component that
retrieves/calculates financial facts. The final analyst cannot request arbitrary
files; it can only reason over the validated evidence returned by Python.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

import requests

from .evidence_catalog import EVIDENCE_CATALOG
from .evidence_engine import build_catalog_context, execute_evidence_plan
from .financial_knowledge import knowledge_for_llm
from .intelligence_layer import normalize_scope, attach_scope_to_requests
from .test_logger import append_chat_log

DEFAULT_PROVIDER_ORDER = ["groq", "gemini", "openrouter"]

# Explicitly excluded model. It has been observed returning reasoning/thinking
# without a usable final answer during FinAI testing. Keep the exclusion narrow
# so other OpenRouter models remain available when explicitly configured.
EXCLUDED_MODELS = {"apodex/apodex-1.1-mini:free"}
DEFAULT_MODELS = {"groq": "", "openrouter": "", "gemini": ""}
DISCOVERY_TIMEOUT = 15
MAX_MODELS_PER_PROVIDER = 8
RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}

PLANNER_SYSTEM_PROMPT = """Anda adalah Evidence Planner untuk FinAI.
Tugas Anda adalah menerjemahkan pertanyaan pengguna menjadi SEMANTIC PLAN dan daftar evidence yang harus diminta ke Python. Anda tidak menjawab pertanyaan dan tidak menghitung angka.

PRIORITAS UTAMA:
1. Pahami objek pertanyaan, periode, scope waktu, dan jenis analisis sebelum memilih evidence.
2. Jika pengguna meminta rentang/perkembangan/trend dari A sampai B, WAJIB meminta SEMUA periode bulanan di antara A dan B. Endpoint saja tidak cukup.
3. Jika pengguna meminta "kenapa", "mengapa", "driver", atau "penyebab", minta metric utama DAN komponen/driver yang dapat menguji penjelasan tersebut. Jangan menyimpulkan sebab hanya dari korelasi.
4. Gunakan definisi, hubungan, dan forbidden_inferences dalam financial knowledge.
5. Untuk target, pastikan actual dan target berada pada periode yang comparable.
6. Gunakan evidence seminimal mungkin tetapi lengkap untuk pertanyaan. Untuk diagnosis, lebih baik evidence bertahap daripada menebak.
7. Hanya gunakan evidence ID yang ada di katalog.
8. Output JSON valid saja.

SCOPE TYPE:
POINT = satu periode; COMPARISON = dua/perbandingan; RANGE = seluruh periode dalam interval; TREND = pola lintas periode; YTD = perkembangan/akumulasi tahun berjalan; DIAGNOSIS = mencari driver; TARGET_ANALYSIS = actual vs target; SCENARIO = analisis asumsi.

Untuk RANGE/TREND/YTD, isi scope.include_all_periods=true, start_period, end_period, granularity=MONTHLY.

Schema:
{
  "scope": {"scope_type":"RANGE","start_period":"2026-01","end_period":"2026-09","granularity":"MONTHLY","include_all_periods":true,"analysis":["TREND","MOM","TURNING_POINT"]},
  "requests": [{"id":"summary_kpi","period":"2026-09","start_period":"2026-01","end_period":"2026-09","granularity":"MONTHLY","include_all_periods":true,"comparisons":["trend"],"fields":[],"lines":[],"products":[]} ]
}
"""

ANALYST_SYSTEM_PROMPT = """Anda adalah FinAI, Financial Intelligence Assistant untuk analisis keuangan.

Python adalah sumber kebenaran untuk angka, periode, dan perhitungan. Financial Knowledge adalah sumber definisi dan batas interpretasi. Evidence yang dikirim adalah satu-satunya dasar faktual.

ATURAN KERAS:
1. Jangan mengarang angka, periode, produk, formula, atau fakta.
2. Bedakan FAKTA, PERHITUNGAN, INTERPRETASI, ASUMSI/IMPLIKASI, dan KETERBATASAN bila relevan.
3. Observasi perubahan tidak otomatis membuktikan sebab-akibat. Gunakan bahasa seperti "sejalan dengan", "berkorelasi", atau "belum dapat dipastikan" bila driver belum terbukti.
4. Patuhi forbidden_inferences dari Financial Knowledge. Contoh: CKPN bukan pendapatan non-bunga; NPL turun tidak otomatis berarti seluruh risiko gagal bayar turun; laba naik tidak otomatis berarti efisiensi membaik.
5. Untuk pertanyaan range/trend, analisis SELURUH periode yang tersedia dalam range, bukan hanya awal dan akhir. Gunakan pola bulanan, perubahan, turning point, highest/lowest bila tersedia.
6. Jangan membandingkan periode yang tidak comparable, misalnya actual bulanan dengan target full-year atau YTD dengan target bulanan.
7. Jika evidence tidak lengkap, sebutkan periode/data yang hilang dan jangan menutup gap dengan asumsi tak terukur.
8. Untuk pertanyaan "kenapa", fokus pada driver material yang benar-benar didukung evidence. Jika belum cukup, katakan bahwa penyebab belum dapat dipastikan.
9. Untuk estimasi/skenario, pisahkan hasil estimasi dari fakta aktual dan nyatakan asumsi terukur.
10. Bahasa Indonesia, profesional tetapi natural. Jangan menyebut chain-of-thought atau proses internal secara mentah.
"""


def _secret(name: str) -> str | None:
    try:
        import streamlit as st
        value = st.secrets.get(name, "")
        return str(value).strip() if value else None
    except Exception:
        return None


def _provider_order() -> list[str]:
    raw = _secret("FINAI_PROVIDER_ORDER")
    if not raw:
        return DEFAULT_PROVIDER_ORDER.copy()
    requested = [x.strip().lower() for x in raw.split(",") if x.strip()]
    return [x for x in requested if x in DEFAULT_PROVIDER_ORDER] or DEFAULT_PROVIDER_ORDER.copy()


def _api_key(provider: str) -> str | None:
    return _secret({"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "openrouter": "OPENROUTER_API_KEY"}[provider])


def _configured_model(provider: str) -> str | None:
    return _secret(f"{provider.upper()}_MODEL") or None


class ProviderError(Exception):
    def __init__(self, provider: str, status_code: int | None, detail: str):
        self.provider = provider
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _error_category(status: int | None, detail: str) -> str:
    text = (detail or "").lower()
    if status == 401:
        return "authentication"
    if status == 403:
        return "access_denied_or_billing_required" if any(x in text for x in ("quota", "billing", "permission", "denied", "disabled")) else "access_denied"
    if status == 404:
        return "model_or_endpoint_unavailable"
    if status == 429:
        if any(x in text for x in ("daily", "rpd", "quota", "resource_exhausted", "exhausted")):
            return "daily_quota_or_quota_exhausted"
        return "rate_limit"
    if status in {500, 502, 503, 504}:
        return "temporary_provider_error"
    if status == 408:
        return "timeout"
    return "provider_error"


def _retry_delay(status: int | None, attempt: int) -> float:
    if status == 429:
        return min(2.0, 0.5 * (2 ** max(0, attempt - 1)))
    return min(3.0, 0.75 * (2 ** max(0, attempt - 1)))


def _openrouter_models(api_key: str) -> list[str]:
    configured = _configured_model("openrouter")
    if configured and configured.strip().lower() in {x.lower() for x in EXCLUDED_MODELS}:
        return []
    r = requests.get("https://openrouter.ai/api/v1/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=DISCOVERY_TIMEOUT)
    if r.status_code != 200:
        raise ProviderError("openrouter", r.status_code, r.text[:1000])
    if configured:
        return [configured]
    models = []
    for item in r.json().get("data") or []:
        mid = str(item.get("id", "")).strip()
        pricing = item.get("pricing") or {}
        try:
            free = float(pricing.get("prompt", 1)) == 0 and float(pricing.get("completion", 1)) == 0
        except (TypeError, ValueError):
            free = False
        if mid and free and mid.lower() not in {x.lower() for x in EXCLUDED_MODELS}:
            models.append(mid)
    return models[:MAX_MODELS_PER_PROVIDER]


def _groq_models(api_key: str) -> list[str]:
    r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=DISCOVERY_TIMEOUT)
    if r.status_code != 200:
        raise ProviderError("groq", r.status_code, r.text[:1000])
    configured = _configured_model("groq")
    if configured:
        return [configured]
    models = []
    for item in r.json().get("data") or []:
        mid = str(item.get("id", "")).strip()
        if mid and not any(x in mid.lower() for x in ("whisper", "tts", "guard")):
            models.append(mid)
    preferred = "openai/gpt-oss-20b"
    models.sort(key=lambda x: (0 if x == preferred else 1, x))
    return models[:MAX_MODELS_PER_PROVIDER]


GEMINI_FREE_TEXT_MODELS = {
    "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash",
    "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3-flash-preview",
    "gemini-2.5-flash", "gemini-2.5-flash-lite",
}


def _gemini_models(api_key: str) -> list[str]:
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": api_key, "pageSize": 100}, timeout=DISCOVERY_TIMEOUT)
    if r.status_code != 200:
        raise ProviderError("gemini", r.status_code, r.text[:1000])
    configured = _configured_model("gemini")
    if configured:
        return [configured.replace("models/", "")]
    available = set()
    for item in r.json().get("models") or []:
        name = str(item.get("name", "")).replace("models/", "").strip()
        methods = item.get("supportedGenerationMethods") or []
        if name in GEMINI_FREE_TEXT_MODELS and "generateContent" in methods:
            available.add(name)
    preferred = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.8-flash"]
    return [x for x in preferred if x in available][:MAX_MODELS_PER_PROVIDER]


def _discover_models(provider: str, api_key: str) -> list[str]:
    if provider == "gemini": return _gemini_models(api_key)
    if provider == "groq": return _groq_models(api_key)
    return _openrouter_models(api_key)


def _strip_thinking_blocks(text: str) -> str:
    """Remove explicit thinking blocks while preserving the final answer."""
    value = str(text or "")
    # Common formats emitted by reasoning models. Do not display internal
    # reasoning in the chat; only the final content is allowed through.
    value = re.sub(r"<think>.*?</think>", "", value, flags=re.I | re.S)
    value = re.sub(r"<analysis>.*?</analysis>", "", value, flags=re.I | re.S)
    value = re.sub(r"^\s*(?:thinking|reasoning|analysis)\s*:\s*", "", value, flags=re.I)
    return value.strip()


def _extract_openai_content(data: dict[str, Any]) -> str | None:
    choices = data.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in content)
    # IMPORTANT: never fall back to message.reasoning. Reasoning is not the
    # final answer and must not be displayed or used as the analyst response.
    if not content:
        return None
    content = _strip_thinking_blocks(str(content))
    return content or None


def _call_openai_compatible(provider: str, api_key: str, model: str, messages: list[dict[str, str]], timeout: int, max_tokens: int) -> str:
    if provider == "groq":
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    else:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "HTTP-Referer": "https://finai-tes.streamlit.app", "X-Title": "FinAI"}
    payload = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens}
    if provider == "openrouter":
        # Explicitly disable provider-side reasoning where supported. The
        # response parser also rejects reasoning-only responses as a second
        # safety layer.
        payload["reasoning"] = {"enabled": False}
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if response.status_code != 200:
        raise ProviderError(provider, response.status_code, response.text[:1000])
    try:
        data = response.json()
    except Exception as exc:
        raise ProviderError(provider, response.status_code, f"Invalid JSON: {exc}") from exc
    content = _extract_openai_content(data)
    if not content:
        raise ProviderError(provider, response.status_code, "Response tidak berisi final content (reasoning-only/empty response ditolak).")
    return content


def _call_gemini(api_key: str, model: str, messages: list[dict[str, str]], timeout: int, max_tokens: int) -> str:
    model = model.replace("models/", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    contents = []
    system_text = ""
    for message in messages:
        if message["role"] == "system":
            system_text += message["content"] + "\n"
            continue
        role = "model" if message["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": message["content"]}]})
    payload = {"system_instruction": {"parts": [{"text": system_text.strip()}]}, "contents": contents, "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens}}
    response = requests.post(url, params={"key": api_key}, headers={"Content-Type": "application/json"}, json=payload, timeout=timeout)
    if response.status_code != 200:
        raise ProviderError("gemini", response.status_code, response.text[:1000])
    try:
        data = response.json()
        candidates = data.get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts") or []
        content = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
    except Exception as exc:
        raise ProviderError("gemini", response.status_code, f"Invalid JSON: {exc}") from exc
    if not content.strip():
        raise ProviderError("gemini", response.status_code, "Response tidak berisi content.")
    return content.strip()


def _call(provider: str, key: str, model: str, messages: list[dict[str, str]], timeout: int, max_tokens: int) -> str:
    if provider == "gemini": return _call_gemini(key, model, messages, timeout, max_tokens)
    return _call_openai_compatible(provider, key, model, messages, timeout, max_tokens)


def _recent_history(messages: list[dict[str, Any]], limit: int = 6) -> list[dict[str, str]]:
    out = []
    for m in messages[-limit:]:
        role = str(m.get("role", "user"))
        if role in {"user", "assistant"}:
            out.append({"role": role, "content": str(m.get("content", ""))})
    return out


def _extract_json(text: str) -> dict[str, Any] | None:
    text = str(text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except Exception:
            return None


def _validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    valid = []
    raw_scope = plan.get("scope") if isinstance(plan, dict) else {}
    for req in plan.get("requests", []) if isinstance(plan.get("requests"), list) else []:
        if not isinstance(req, dict): continue
        eid = str(req.get("id", "")).strip()
        if eid not in EVIDENCE_CATALOG: continue
        comparisons = [str(x).lower() for x in req.get("comparisons", []) if str(x).lower() in {"mom", "yoy", "ytd", "target", "trend"}]
        clean = {"id": eid, "comparisons": list(dict.fromkeys(comparisons))[:5]}
        for field in ("period", "start_period", "end_period", "granularity"):
            value = req.get(field)
            if value: clean[field] = str(value)
        clean["include_all_periods"] = bool(req.get("include_all_periods", False))
        for field in ("fields", "lines", "products"):
            value = req.get(field)
            if isinstance(value, list): clean[field] = [str(x) for x in value[:60]]
        valid.append(clean)
    out = {"scope": raw_scope if isinstance(raw_scope, dict) else {}, "requests": valid[:10]}
    return normalize_scope(out, None)


def _heuristic_plan(question: str, selected_period: str | None = None) -> dict[str, Any]:
    """Conservative fallback. It selects evidence only; it never creates facts."""
    q = question.lower()
    period = selected_period
    req = [{"id": "summary_kpi", "comparisons": ["mom", "yoy"]}]
    scope_type = "POINT"
    analysis = ["SNAPSHOT"]
    # Detect common range language without hard-coding specific questions.
    import re as _re
    years = _re.findall(r"(20\d{2})", q)
    months = {"januari":"01","februari":"02","maret":"03","april":"04","mei":"05","juni":"06","juli":"07","agustus":"08","september":"09","oktober":"10","november":"11","desember":"12"}
    found = [(months[m], y) for m in months for y in years if m in q]
    if any(x in q for x in ("sepanjang", "dari awal", "perkembangan", "trend", "tren", "januari sampai", "hingga")) and len(found) >= 2:
        found = sorted(set(found), key=lambda z: (z[1], z[0]))
        start_p, end_p = f"{found[0][1]}-{found[0][0]}", f"{found[-1][1]}-{found[-1][0]}"
        scope_type, analysis = "RANGE", ["TREND", "MOM", "TURNING_POINT"]
    else:
        start_p = end_p = period
    if any(x in q for x in ("laba", "profit", "revenue", "pendapatan", "beban", "ckpn")):
        req.append({"id": "income_statement", "comparisons": ["mom", "yoy", "trend"] if scope_type == "RANGE" else ["mom", "yoy"]})
    if any(x in q for x in ("aset", "neraca", "liabilitas", "modal", "funding", "dpk")):
        req.append({"id": "balance_sheet", "comparisons": ["mom", "yoy", "trend"] if scope_type == "RANGE" else ["mom", "yoy"]})
    if any(x in q for x in ("kredit", "loan", "npl", "produk", "kpr", "konstruksi", "modal kerja")):
        req.append({"id": "loan_products", "comparisons": ["mom", "yoy", "trend"] if scope_type == "RANGE" else ["mom", "yoy"]})
    if any(x in q for x in ("dpk", "deposito", "tabungan", "giro", "cost of fund", "funding")):
        req.append({"id": "dpk_products", "comparisons": ["mom", "yoy", "trend"] if scope_type == "RANGE" else ["mom", "yoy"]})
    if any(x in q for x in ("target", "rkap", "achievement", "pencapaian")):
        req.append({"id": "targets", "comparisons": ["target", "trend"]})
        scope_type = "TARGET_ANALYSIS" if scope_type == "POINT" else scope_type
        analysis.append("TARGET_GAP")
    plan = {"scope": {"scope_type": scope_type, "start_period": start_p, "end_period": end_p, "granularity": "MONTHLY", "include_all_periods": scope_type == "RANGE", "analysis": analysis}, "requests": req}
    return normalize_scope(_validate_plan(plan), selected_period)


def _attempt_record(provider: str, model: str | None, status: Any, category: str, error: str | None, latency: float, stage: str, retry: int = 0):
    return {"provider": provider, "model": model, "status": status, "category": category, "error": error, "latency": round(latency, 2), "stage": stage, "retry": retry}


def _plan_messages(messages: list[dict[str, Any]], catalog: dict[str, Any], selected_period: str | None = None) -> list[dict[str, str]]:
    question = next((str(m.get("content", "")) for m in reversed(messages) if m.get("role") == "user"), "")
    context = {"catalog": catalog, "active_period": selected_period, "knowledge": knowledge_for_llm()}
    return [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": "FINAI PLANNING CONTEXT (metadata + semantic knowledge):\n" + json.dumps(context, ensure_ascii=False, separators=(",", ":")) + "\n\nPERTANYAAN USER:\n" + question},
    ]


def _followup_plan_messages(question: str, plan: dict[str, Any], evidence: dict[str, Any], catalog: dict[str, Any]) -> list[dict[str, str]]:
    prompt = PLANNER_SYSTEM_PROMPT + "\n\nAnda sekarang melakukan EVIDENCE SUFFICIENCY CHECK. Evidence berikut adalah hasil Python. Jika sudah cukup, output requests=[] dan keep=true. Jika belum cukup, minta evidence tambahan yang benar-benar diperlukan. Jangan mengubah fakta.\n"
    payload = {"question": question, "current_plan": plan, "evidence": evidence, "catalog": catalog, "knowledge": knowledge_for_llm()}
    return [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}]


def _analyst_messages(messages: list[dict[str, Any]], plan: dict[str, Any], evidence: dict[str, Any]) -> list[dict[str, str]]:
    history = _recent_history(messages, 6)
    payload = "VALIDATED EVIDENCE REQUEST PLAN:\n" + json.dumps(plan, ensure_ascii=False, separators=(",", ":"))
    payload += "\n\nFINANCIAL KNOWLEDGE / INTERPRETATION GUARDRAILS:\n" + json.dumps(knowledge_for_llm(), ensure_ascii=False, separators=(",", ":"))
    payload += "\n\nFINANCIAL EVIDENCE FROM PYTHON:\n" + json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
    payload += "\n\nJawab pertanyaan user berdasarkan evidence. Untuk range, analisis semua periode yang dikirim."
    return [{"role": "system", "content": ANALYST_SYSTEM_PROMPT}, *history, {"role": "user", "content": payload}]


def chat(messages: list[dict[str, Any]], selected_period: str | None = None, timeout: int = 30) -> dict[str, Any]:
    question = next((str(item.get("content", "")).strip() for item in reversed(messages) if item.get("role") == "user"), "")
    catalog = build_catalog_context()
    attempts: list[dict[str, Any]] = []
    max_rounds = 3

    for provider in _provider_order():
        key = _api_key(provider)
        if not key:
            attempts.append(_attempt_record(provider, None, "missing_key", "missing_key", "API key tidak ditemukan di Streamlit Secrets.", 0, "provider"))
            continue
        try:
            models = _discover_models(provider, key)
        except (ProviderError, requests.RequestException) as exc:
            if isinstance(exc, ProviderError):
                attempts.append(_attempt_record(provider, None, exc.status_code, _error_category(exc.status_code, exc.detail), exc.detail[:1000], 0, "discovery"))
            else:
                attempts.append(_attempt_record(provider, None, "discovery_network_error", "network_error", str(exc)[:500], 0, "discovery"))
            continue
        if not models:
            attempts.append(_attempt_record(provider, None, "no_models", "no_usable_models", "Tidak ditemukan model yang dapat digunakan.", 0, "discovery"))
            continue

        for model in models:
            plan = None
            retry_index = 0
            while True:
                started = time.perf_counter()
                try:
                    planner_raw = _call(provider, key, model, _plan_messages(messages, catalog, selected_period), timeout, 900)
                    plan = _validate_plan(_extract_json(planner_raw) or {})
                    plan = normalize_scope(plan, selected_period)
                    plan = attach_scope_to_requests(plan)
                    if not plan["requests"]:
                        raise ProviderError(provider, 200, "Planner returned no valid evidence requests.")
                    attempts.append(_attempt_record(provider, model, 200, "planner_success", None, time.perf_counter()-started, "planner", retry_index))
                    break
                except ProviderError as exc:
                    attempts.append(_attempt_record(provider, model, exc.status_code, _error_category(exc.status_code, exc.detail), exc.detail[:1000], time.perf_counter()-started, "planner", retry_index))
                    if exc.status_code in RETRYABLE_STATUSES and retry_index < 1 and _error_category(exc.status_code, exc.detail) not in {"daily_quota_or_quota_exhausted", "rate_limit"}:
                        retry_index += 1; time.sleep(_retry_delay(exc.status_code, retry_index)); continue
                    break
                except requests.RequestException as exc:
                    attempts.append(_attempt_record(provider, model, "network_error", "network_error", str(exc)[:500], time.perf_counter()-started, "planner")); break
                except Exception as exc:
                    attempts.append(_attempt_record(provider, model, "planner_error", "planner_error", str(exc)[:500], time.perf_counter()-started, "planner")); break

            planner_source = "LLM"
            if not plan:
                plan = _heuristic_plan(question, selected_period)
                planner_source = "HEURISTIC_FALLBACK"

            # Iterative evidence loop. The first planner sees metadata only; follow-up
            # planners see the returned evidence so they can identify missing drivers.
            evidence = execute_evidence_plan(plan, selected_period)
            round_no = 1
            evidence_history = [evidence]
            while round_no < max_rounds and evidence.get("status") == "OK":
                scope = plan.get("scope") or {}
                # For a range, Python coverage is the primary sufficiency signal.
                incomplete = any(not x.get("complete", True) for x in (evidence.get("coverage", {}).get("coverage", {}) or {}).values())
                if scope.get("include_all_periods") and incomplete:
                    # Re-execute with normalized range requests; do not let the LLM shrink the range.
                    plan = attach_scope_to_requests(normalize_scope(plan, selected_period))
                    evidence = execute_evidence_plan(plan, selected_period)
                    evidence_history.append(evidence)
                    if not any(not x.get("complete", True) for x in (evidence.get("coverage", {}).get("coverage", {}) or {}).values()):
                        break
                # Ask the planner whether more evidence is needed. This is deliberately
                # limited to two follow-up rounds to avoid loops/cost explosions.
                started = time.perf_counter()
                try:
                    follow_raw = _call(provider, key, model, _followup_plan_messages(question, plan, evidence, catalog), timeout, 900)
                    follow = _validate_plan(_extract_json(follow_raw) or {})
                    follow = normalize_scope(follow, selected_period)
                    follow = attach_scope_to_requests(follow)
                    attempts.append(_attempt_record(provider, model, 200, "evidence_check_success", None, time.perf_counter()-started, f"evidence_check_{round_no}"))
                    if not follow.get("requests"):
                        break
                    # Keep the original scope authoritative for range questions.
                    if (plan.get("scope") or {}).get("include_all_periods"):
                        follow["scope"] = plan["scope"]
                        follow = attach_scope_to_requests(follow)
                    plan["requests"] = plan.get("requests", []) + follow.get("requests", [])
                    # Deduplicate by evidence id + scope so extra requests add only new evidence.
                    merged = []
                    seen = set()
                    for r in plan["requests"]:
                        key_id = (r.get("id"), r.get("start_period"), r.get("end_period"), tuple(r.get("comparisons", [])))
                        if key_id not in seen:
                            seen.add(key_id); merged.append(r)
                    plan["requests"] = merged[:10]
                    evidence = execute_evidence_plan(plan, selected_period)
                    round_no += 1
                except (ProviderError, requests.RequestException, Exception) as exc:
                    detail = getattr(exc, "detail", str(exc))
                    status = getattr(exc, "status_code", "evidence_check_error")
                    attempts.append(_attempt_record(provider, model, status, _error_category(status if isinstance(status, int) else None, str(detail)), str(detail)[:500], time.perf_counter()-started, f"evidence_check_{round_no}"))
                    break

            if evidence.get("status") != "OK":
                attempts.append(_attempt_record(provider, model, "no_evidence", "no_evidence", "Planner tidak menghasilkan evidence yang dapat dieksekusi.", 0, "evidence"))
                continue

            started = time.perf_counter()
            try:
                answer = _call(provider, key, model, _analyst_messages(messages, plan, evidence), timeout, 2200)
                attempts.append(_attempt_record(provider, model, 200, "success", None, time.perf_counter()-started, "analyst"))
                result = {"ok": True, "content": answer, "provider": provider, "model": model,
                        "period": evidence.get("period"), "planner_source": planner_source,
                        "plan": plan, "evidence_request_count": len(evidence.get("requested", [])),
                        "evidence_rounds": round_no, "attempts": attempts,
                        "evidence_requested": evidence.get("requested", []),
                        "evidence_sent_to_analyst": evidence,
                        "evidence_history": evidence_history}
                append_chat_log(question=question, selected_period=selected_period, response=result)
                return result
            except ProviderError as exc:
                attempts.append(_attempt_record(provider, model, exc.status_code, _error_category(exc.status_code, exc.detail), exc.detail[:1000], time.perf_counter()-started, "analyst")); continue
            except requests.RequestException as exc:
                attempts.append(_attempt_record(provider, model, "network_error", "network_error", str(exc)[:500], time.perf_counter()-started, "analyst")); continue
            except Exception as exc:
                attempts.append(_attempt_record(provider, model, "unexpected_error", "unexpected_error", str(exc)[:500], time.perf_counter()-started, "analyst")); continue

    result = {"ok": False, "error": "Semua provider/model LLM gagal menyelesaikan planner → evidence → evidence-check → analyst. FinAI tidak menggantinya dengan jawaban Python agar tidak menghasilkan analisis palsu.", "provider": None, "attempts": attempts, "plan": None, "evidence_requested": [], "evidence_sent_to_analyst": None, "evidence_rounds": 0}
    append_chat_log(question=question, selected_period=selected_period, response=result)
    return result

