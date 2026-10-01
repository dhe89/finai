from .planner import plan_question
from .analyst import analyze
from .verifier import verify_answer, fallback_answer
from .openrouter import DEFAULT_MODEL
from finai_ui.financial_engine import build_evidence
from finai_ui import data_service as ds


META_PHRASES = [
    "perkenalkan dirimu", "perkenalkan diri", "siapa kamu", "siapa anda",
    "apa itu finai", "apa itu fin ai",
]


def _meta(question):
    q = " ".join(str(question or "").lower().split())
    return any(x in q for x in META_PHRASES)



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

    period = ds.resolve_period(selected_period)
    plan_result = plan_question(question, period, model=model)

    # The planner is deliberately semantic rather than keyword/dictionary based.
    # If it cannot classify the domain, fail closed instead of guessing.
    if not plan_result.get("ok"):
        return {
            "ok": True,
            "answer": "Saya belum dapat memproses pertanyaan tersebut dengan andal saat ini. Silakan coba lagi.",
            "stage": "planner_error",
        }

    plan = plan_result["plan"]
    scope = str(plan.get("scope", "FINANCIAL")).upper()
    if scope == "META":
        return {
            "ok": True,
            "answer": "Saya FinAI, asisten Financial Intelligence untuk membantu menganalisis data keuangan yang tersedia di aplikasi.",
            "stage": "meta",
        }
    if scope == "OUT_OF_SCOPE":
        return {
            "ok": True,
            "answer": "Pertanyaan tersebut berada di luar cakupan FinAI. Saya fokus pada analisis data dan informasi keuangan yang tersedia di aplikasi.",
            "stage": "scope",
        }
    if scope == "AMBIGUOUS":
        return {
            "ok": True,
            "answer": "Pertanyaannya belum cukup jelas untuk dianalisis. Silakan jelaskan fokus yang ingin dianalisis, misalnya kinerja laba, aset, kredit, pendanaan, kualitas aset, atau target.",
            "stage": "clarification",
        }

    evidence = build_evidence(question, period, plan)
    if evidence.get("status") != "READY":
        return {
            "ok": True,
            "answer": evidence.get("message", "Data yang diperlukan belum tersedia."),
            "stage": "data",
            "plan": plan,
        }

    analysis = analyze(question, evidence, plan, model=model)
    if analysis.get("ok"):
        answer = analysis.get("content", "").strip()
        checked = verify_answer(question, answer, evidence)
        if checked.get("ok"):
            return {
                "ok": True,
                "answer": answer,
                "stage": "analyst",
                "plan": plan,
                "evidence": evidence,
                "model": analysis.get("model"),
            }

    # Never expose planner/model internals to the user.
    fallback = fallback_answer(evidence)
    return {
        "ok": True,
        "answer": fallback,
        "stage": "fallback",
        "plan": plan,
        "evidence": evidence,
        "warning": analysis.get("error") if isinstance(analysis, dict) else None,
    }
