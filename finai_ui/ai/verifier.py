import re
import math

def _numbers(text):
    # Capture common Indonesian financial numbers while avoiding years.
    found = []
    for raw in re.findall(r"(?<![\w])(?:Rp\s*)?[-+]?\d[\d.,]*(?:\s*(?:miliar|triliun|%))?", str(text), flags=re.I):
        cleaned = raw.strip()
        if len(cleaned) <= 1:
            continue
        found.append(cleaned)
    return found


def _contains_internal_meta(text):
    low = str(text or "").lower()
    markers = [
        "evidence", "planner", "chain of thought", "thinking process",
        "reasoning", "llm", "model mengatakan", "prompt",
        "the user is asking", "first question:", "second question:",
    ]
    return any(m in low for m in markers)


def verify_answer(question, answer, evidence):
    """Deterministic guardrail, not a second reasoning model.

    It checks obvious leakage and whether cited financial numbers are present in
    the evidence. It does not attempt to prove the semantic correctness of every
    sentence.
    """
    text = str(answer or "").strip()
    if not text:
        return {"ok": False, "reason": "Jawaban kosong."}

    if _contains_internal_meta(text):
        return {"ok": False, "reason": "Jawaban mengandung metadata/internal reasoning."}

    # Exact financial numbers appearing in answer should exist somewhere in the
    # serialized evidence. This is intentionally conservative.
    evidence_text = str(evidence)
    suspicious = []
    for token in _numbers(text):
        if re.search(r"\d", token):
            digits = re.sub(r"[^\d]", "", token)
            if len(digits) >= 2 and digits not in re.sub(r"[^\d]", "", evidence_text):
                # Skip common percentages/years that may be derived legitimately.
                if "%" not in token and not re.fullmatch(r"20\d{2}", digits):
                    suspicious.append(token)

    if suspicious:
        return {
            "ok": False,
            "reason": "Jawaban memuat angka yang tidak ditemukan di evidence.",
            "suspicious_numbers": suspicious[:5],
        }

    return {"ok": True}


def fallback_answer(evidence):
    """Minimal deterministic fallback if analyst model fails."""
    current = evidence.get("current", {})
    period = evidence.get("selected_period")
    if not current:
        return "Data yang diperlukan belum tersedia."

    # Prefer net profit when present because it is the most common diagnostic query.
    if "net_profit" in current:
        npv = current["net_profit"]["value"]
        parts = [f"Laba bersih {period}: Rp {npv:,.2f} miliar."]
        mom = ((evidence.get("comparisons") or {}).get("mom") or {}).get("metrics", {})
        if "net_profit" in mom:
            ch = mom["net_profit"]["change"]
            if ch and ch.get("percent") is not None:
                direction = "naik" if ch["percent"] >= 0 else "turun"
                parts.append(f"Secara MoM, laba {direction} {abs(ch['percent']):.2f}%.")
        drivers = evidence.get("income_statement_changes_mom") or []
        if drivers:
            top = drivers[:3]
            parts.append(
                "Perubahan terbesar pada P&L antara lain " +
                "; ".join(
                    f"{x['line_item']} ({x['change']['absolute']:+,.2f} miliar)"
                    for x in top
                ) + "."
            )
        return " ".join(parts)
    return "Data tersedia, tetapi belum cukup untuk membentuk kesimpulan yang andal."
