"""FinAI agent orchestration.

Core principle:
- Python is the auditable financial evidence/calculation layer.
- LLM is the intelligence layer that understands the question, decides what
  evidence is needed, interprets relationships, and synthesizes the conclusion.
- There is NO analytical Python fallback. A failed LLM analysis must never be
  presented as if it were Financial Intelligence.
"""
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


def _apply_requested_tools(evidence, requests, period, used):
    added = []
    tools = evidence.setdefault("analysis_tools", {})
    for request in requests[:3]:
        request = str(request)
        if request in used:
            continue
        expanded = expand_evidence(evidence, request, period)
        used.add(request)
        if expanded is not None:
            tools[request] = expanded
            added.append(request)
    return added


def _llm_unavailable_message():
    return (
        "Saya belum dapat menyelesaikan analisis ini dengan andal karena lapisan "
        "analisis AI sedang tidak tersedia. Saya tidak akan menggantinya dengan "
        "jawaban angka yang dapat menyesatkan. Silakan coba kembali."
    )


def run_financial_analysis(question, selected_period=None, model=DEFAULT_MODEL):
    question = str(question or "").strip()
    if not question:
        return {"ok": False, "answer": "Silakan masukkan pertanyaan.", "stage": "validation"}

    if _meta(question):
        return {
            "ok": True,
            "answer": "Saya FinAI, asisten Financial Intelligence untuk membantu menganalisis data keuangan yang tersedia di aplikasi.",
            "stage": "meta",
            "model_used": False,
        }

    try:
        period = ds.resolve_period(selected_period)
        evidence = build_evidence(question, period, plan=None)
        if evidence.get("status") != "READY":
            return {"ok": True, "answer": evidence.get("message", "Data yang diperlukan belum tersedia."), "stage": "data", "model_used": False}

        # Every non-meta question goes through the semantic director. This removes
        # brittle keyword-based routing and lets the model decide FACT vs ANALYSIS.
        director = inspect(question, evidence, context=[], model=model)
        if not director.get("ok"):
            # A factual lookup is the only safe case where Python may answer when
            # the LLM is unavailable. The deterministic engine remains the source
            # of the fact; it is not presented as an analytical conclusion.
            if str(question).lower().strip().startswith(("berapa ", "berapa nilai ", "berapa jumlah ")):
                return {
                    "ok": True,
                    "answer": fallback_answer(evidence, question=question, analytical=False),
                    "stage": "python_fact_safe_fallback",
                    "evidence": evidence,
                    "model_used": False,
                    "warning": "LLM unavailable; factual lookup only.",
                }
            return {
                "ok": True,
                "answer": _llm_unavailable_message(),
                "stage": "llm_director_unavailable",
                "evidence": evidence,
                "model_used": False,
                "warning": director.get("error", "LLM director unavailable"),
            }

        analysis = director.get("analysis", {})
        scope = str(analysis.get("scope", "FINANCIAL")).upper()
        if scope == "META":
            return {"ok": True, "answer": "Saya FinAI, asisten Financial Intelligence untuk membantu menganalisis data keuangan yang tersedia di aplikasi.", "stage": "meta", "model_used": True}
        if scope == "OUT_OF_SCOPE":
            return {"ok": True, "answer": "Pertanyaan tersebut berada di luar cakupan FinAI. Saya fokus pada analisis data dan informasi keuangan yang tersedia di aplikasi.", "stage": "scope", "model_used": True}
        if scope == "AMBIGUOUS":
            return {"ok": True, "answer": "Saya belum dapat menentukan fokus analisis dari pertanyaan tersebut. Mohon sebutkan metrik atau kondisi keuangan yang ingin dianalisis.", "stage": "ambiguous", "model_used": True}

        findings = list(analysis.get("findings", []) or [])
        used_requests = set()
        # Agent loop: up to two evidence-planning rounds. The LLM decides what it
        # needs; Python executes only explicit, auditable tools.
        for round_no in range(2):
            requests = [str(r) for r in (analysis.get("requests", []) or [])[:3]]
            if requests:
                _apply_requested_tools(evidence, requests, period, used_requests)

            need_more = bool(analysis.get("need_more_evidence"))
            if not need_more or round_no == 1:
                break

            next_director = inspect(question, evidence, context=findings, model=model)
            if not next_director.get("ok"):
                return {
                    "ok": True,
                    "answer": _llm_unavailable_message(),
                    "stage": "llm_planner_unavailable",
                    "evidence": evidence,
                    "findings": findings,
                    "model_used": False,
                    "warning": next_director.get("error", "LLM planner unavailable"),
                }
            analysis = next_director.get("analysis", {})
            findings.extend(analysis.get("findings", []) or [])

        final = synthesize(question, evidence, findings, model=model)
        if not final.get("ok"):
            return {
                "ok": True,
                "answer": _llm_unavailable_message(),
                "stage": "llm_synthesis_unavailable",
                "evidence": evidence,
                "findings": findings,
                "model_used": False,
                "warning": final.get("error", "LLM synthesis unavailable"),
            }

        answer = final.get("content", "").strip()
        checked = verify_answer(question, answer, evidence)
        if not checked.get("ok"):
            retry = synthesize(question, evidence, findings, model=model, retry=True)
            if retry.get("ok"):
                answer = retry.get("content", "").strip()
                checked = verify_answer(question, answer, evidence)
                if checked.get("ok"):
                    return {
                        "ok": True,
                        "answer": answer,
                        "stage": "analyst_agent_retry",
                        "evidence": evidence,
                        "findings": findings,
                        "model": retry.get("model"),
                        "model_used": True,
                    }
            return {
                "ok": True,
                "answer": "Saya belum dapat memastikan jawaban analitis tersebut secara andal dari evidence yang tersedia. Saya tidak akan menggantinya dengan jawaban angka yang tidak menjawab pertanyaan.",
                "stage": "verification_failed",
                "evidence": evidence,
                "findings": findings,
                "model_used": True,
                "warning": checked.get("reason", "verification failed"),
            }

        return {
            "ok": True,
            "answer": answer,
            "stage": "analyst_agent",
            "evidence": evidence,
            "findings": findings,
            "model": final.get("model"),
            "model_used": True,
        }
    except Exception as exc:
        return {
            "ok": True,
            "answer": "Terjadi kendala saat memproses analisis. FinAI tidak akan mengganti analisis tersebut dengan jawaban angka yang berpotensi menyesatkan.",
            "stage": "runtime_error",
            "error": str(exc),
            "model_used": False,
        }
