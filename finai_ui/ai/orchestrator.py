"""FinAI orchestration: semantic analysis -> Python tools -> synthesis -> verification."""
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


def _generic_analysis_context():
    return {
        "scope": "FINANCIAL",
        "need_more_evidence": True,
        "requests": ["income_drivers", "balance_drivers", "trend"],
        "focus_metrics": [],
        "findings": [],
        "answer_direction": "Analisis berdasarkan evidence yang tersedia.",
    }


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
        # Planner is deliberately removed from the critical path. The first
        # evidence package is broad and the analyst can request focused tools.
        evidence = build_evidence(question, period, plan=None)
        if evidence.get("status") != "READY":
            return {"ok": True, "answer": evidence.get("message", "Data yang diperlukan belum tersedia."), "stage": "data"}

        findings = []
        seen_requests = set()
        scope = "FINANCIAL"

        # Agent loop: inspect -> tool call -> inspect. Bounded to avoid latency/cost explosion.
        for iteration in range(3):
            director = inspect(question, evidence, context=findings, model=model)
            if director.get("ok"):
                analysis = director.get("analysis", {})
                scope = str(analysis.get("scope", "FINANCIAL")).upper()
                findings.extend(analysis.get("findings", []))
                requests = [r for r in analysis.get("requests", []) if r not in seen_requests]
            else:
                # If the semantic director fails, continue with a deterministic
                # analytical default instead of blocking the user.
                analysis = _generic_analysis_context()
                requests = [r for r in analysis["requests"] if r not in seen_requests]

            if scope == "META":
                return {"ok": True, "answer": "Saya FinAI, asisten Financial Intelligence untuk membantu menganalisis data keuangan yang tersedia di aplikasi.", "stage": "meta"}
            if scope == "OUT_OF_SCOPE":
                return {"ok": True, "answer": "Pertanyaan tersebut berada di luar cakupan FinAI. Saya fokus pada analisis data dan informasi keuangan yang tersedia di aplikasi.", "stage": "scope"}
            if scope == "AMBIGUOUS":
                # Only clarify if the director is confident that no useful
                # financial interpretation is possible.
                if not findings:
                    return {"ok": True, "answer": "Pertanyaannya belum cukup jelas untuk dianalisis. Silakan jelaskan fokus atau metrik yang ingin dianalisis.", "stage": "clarification"}

            if not requests or iteration == 2:
                break

            for request in requests[:3]:
                seen_requests.add(request)
                expanded = expand_evidence(evidence, request, period)
                if expanded:
                    evidence.setdefault("analysis_tools", {})[request] = expanded

            # If no tool added anything, stop the loop.
            if not requests:
                break

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
                    "iterations": min(3, len(seen_requests) + 1),
                    "model": analysis.get("model"),
                }

        fallback = fallback_answer(evidence, question=question)
        return {
            "ok": True,
            "answer": fallback,
            "stage": "fallback",
            "evidence": evidence,
            "findings": findings,
            "warning": analysis.get("error") if isinstance(analysis, dict) else None,
        }
    except Exception:
        return {
            "ok": True,
            "answer": "Terjadi kendala saat memproses analisis. Silakan coba lagi.",
            "stage": "runtime_error",
        }
