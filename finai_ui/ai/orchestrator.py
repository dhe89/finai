"""FinAI orchestration: deterministic evidence -> optional semantic direction -> synthesis."""
from .analyst import inspect, synthesize
from .verifier import verify_answer, fallback_answer
from .openrouter import DEFAULT_MODEL
from finai_ui.financial_engine import build_evidence, expand_evidence
from finai_ui import data_service as ds

META_PHRASES = [
    "perkenalkan dirimu", "perkenalkan diri", "siapa kamu", "siapa anda",
    "apa itu finai", "apa itu fin ai",
]


def _meta(question):
    q = " ".join(str(question or "").lower().split())
    return any(x in q for x in META_PHRASES)


def _is_simple_fact_question(question):
    """Detect only obvious one-metric lookups; this is not a financial intent system."""
    q = " ".join(str(question or "").lower().split())
    analytical_markers = [
        "kenapa", "mengapa", "bagaimana", "apa faktor", "faktor apa", "paling berpengaruh",
        "bandingkan", "dibandingkan", "apakah", "risiko", "strategi", "perlu diperhatikan",
        "menopang", "sehat", "tren", "target", "hubungan", "korelasi", "dampak", "pengaruh",
        "efisiensi", "penyebab", "kontribusi", "sustainable", "sustainability",
    ]
    if any(x in q for x in analytical_markers):
        return False
    # Simple question forms such as "berapa laba/aset/kredit ...?" remain Python-only.
    return q.startswith("berapa ") or q.startswith("berapa nilai ") or q.startswith("berapa jumlah ")


def _apply_requested_tools(evidence, requests, period):
    added = []
    tools = evidence.setdefault("analysis_tools", {})
    for request in requests[:4]:
        if request in tools:
            continue
        expanded = expand_evidence(evidence, request, period)
        if expanded is not None:
            tools[request] = expanded
            added.append(request)
    return added


def run_financial_analysis(question, selected_period=None, model=DEFAULT_MODEL):
    question = str(question or "").strip()
    if not question:
        return {"ok": False, "answer": "Silakan masukkan pertanyaan.", "stage": "validation"}

    if _meta(question):
        return {
            "ok": True,
            "answer": "Saya FinAI, asisten Financial Intelligence untuk membantu menganalisis data keuangan yang tersedia di aplikasi.",
            "stage": "meta",
        }

    try:
        period = ds.resolve_period(selected_period)
        evidence = build_evidence(question, period, plan=None)
        if evidence.get("status") != "READY":
            return {"ok": True, "answer": evidence.get("message", "Data yang diperlukan belum tersedia."), "stage": "data"}

        # Exact/simple lookups do not need an LLM. This is deliberate: it is faster,
        # deterministic and avoids spending model calls where interpretation adds no value.
        if _is_simple_fact_question(question):
            return {
                "ok": True,
                "answer": fallback_answer(evidence, question=question, analytical=False),
                "stage": "python_fact",
                "evidence": evidence,
                "model_used": False,
            }

        findings = []
        seen_requests = set()

        # The semantic director is advisory, not a gate. One call is enough to
        # decide whether the already-rich base evidence needs a focused drill-down.
        director = inspect(question, evidence, context=findings, model=model)
        if director.get("ok"):
            analysis = director.get("analysis", {})
            scope = str(analysis.get("scope", "FINANCIAL")).upper()
            findings.extend(analysis.get("findings", []))
            requests = [r for r in analysis.get("requests", []) if r not in seen_requests]
            if scope == "META":
                return {"ok": True, "answer": "Saya FinAI, asisten Financial Intelligence untuk membantu menganalisis data keuangan yang tersedia di aplikasi.", "stage": "meta"}
            if scope == "OUT_OF_SCOPE":
                return {"ok": True, "answer": "Pertanyaan tersebut berada di luar cakupan FinAI. Saya fokus pada analisis data dan informasi keuangan yang tersedia di aplikasi.", "stage": "scope"}
            _apply_requested_tools(evidence, requests, period)
        else:
            # Do not stop. Base evidence already contains financial drivers, trends,
            # target and balance/funding analysis, so synthesis can proceed.
            requests = []

        # The base evidence is already rich; one focused drill-down pass keeps
        # latency bounded while still allowing the model to choose additional
        # analyses dynamically.

        analysis = synthesize(question, evidence, findings, model=model)
        if analysis.get("ok"):
            answer = analysis.get("content", "").strip()
            checked = verify_answer(question, answer, evidence)
            if checked.get("ok"):
                return {
                    "ok": True,
                    "answer": answer,
                    "stage": "analyst_agent",
                    "evidence": evidence,
                    "findings": findings,
                    "model": analysis.get("model"),
                    "model_used": True,
                }

            # One clean retry is preferable to immediately falling back to a shallow
            # answer when the model produced a useful answer that failed a guardrail.
            retry = synthesize(question, evidence, findings, model=model, retry=True)
            if retry.get("ok"):
                retry_answer = retry.get("content", "").strip()
                retry_check = verify_answer(question, retry_answer, evidence)
                if retry_check.get("ok"):
                    return {
                        "ok": True,
                        "answer": retry_answer,
                        "stage": "analyst_agent_retry",
                        "evidence": evidence,
                        "findings": findings,
                        "model": retry.get("model"),
                        "model_used": True,
                    }

        # If the provider is unavailable, keep the user-facing answer useful, but
        # do not pretend it came from the LLM. The fallback performs real Python
        # financial analysis using the same evidence package.
        fallback = fallback_answer(evidence, question=question, analytical=True)
        return {
            "ok": True,
            "answer": fallback,
            "stage": "python_analytical_fallback",
            "evidence": evidence,
            "findings": findings,
            "model_used": False,
            "warning": "LLM synthesis unavailable; deterministic financial analysis used.",
        }
    except Exception as exc:
        return {
            "ok": True,
            "answer": "Terjadi kendala saat memproses analisis. Data dasar masih tersedia, tetapi kesimpulan belum dapat disusun dengan andal.",
            "stage": "runtime_error",
            "error": str(exc),
        }
