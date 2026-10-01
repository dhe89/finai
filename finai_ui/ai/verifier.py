import re


def _numbers(text):
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
        "chain of thought", "thinking process", "internal reasoning", "reasoning:",
        "the user is asking", "first question:", "second question:", "third question:",
        "fourth question:", "analysis director", "analysis plan", "planner:",
        "evidence json", "prompt:", "llm", "model mengatakan",
    ]
    return any(m in low for m in markers)


def verify_answer(question, answer, evidence):
    """Deterministic final guardrail.

    This is intentionally not a second reasoning model. It checks output leakage,
    empty answers, and unsupported numeric tokens. It does not claim to prove
    semantic correctness of every sentence.
    """
    text = str(answer or "").strip()
    if not text:
        return {"ok": False, "reason": "Jawaban kosong."}
    if _contains_internal_meta(text):
        return {"ok": False, "reason": "Jawaban mengandung metadata/internal reasoning."}

    evidence_text = str(evidence)
    suspicious = []
    for token in _numbers(text):
        digits = re.sub(r"[^\d]", "", token)
        if len(digits) < 2 or re.fullmatch(r"20\d{2}", digits):
            continue
        if "%" in token:
            # Percentages can be derived from evidence. Accept them because the
            # evidence contains the underlying values even if formatting differs.
            continue
        if digits not in re.sub(r"[^\d]", "", evidence_text):
            suspicious.append(token)

    if suspicious:
        return {"ok": False, "reason": "Jawaban memuat angka yang tidak ditemukan di evidence.", "suspicious_numbers": suspicious[:5]}
    return {"ok": True}


def fallback_answer(evidence, question=""):
    """Safe deterministic answer if the analyst layer fails.

    It is intentionally modest: it answers only facts that can be selected
    directly from the evidence and never fabricates a diagnosis.
    """
    current = evidence.get("current", {})
    period = evidence.get("selected_period")
    if not current:
        return "Data yang diperlukan belum tersedia."

    q = " ".join(str(question or "").lower().split())

    def has(*terms):
        return any(t in q for t in terms)

    if has("laba", "profit") and "net_profit" in current:
        npv = current["net_profit"]["value"]
        parts = [f"Laba bersih {period}: Rp {npv:,.2f} miliar."]
        mom = (evidence.get("comparisons") or {}).get("mom", {}).get("metrics", {})
        yoy = (evidence.get("comparisons") or {}).get("yoy", {}).get("metrics", {})
        if "net_profit" in mom and mom["net_profit"].get("change", {}).get("percent") is not None:
            ch = mom["net_profit"]["change"]["percent"]
            parts.append(f"Secara MoM, laba {'naik' if ch >= 0 else 'turun'} {abs(ch):.2f}%.")
        if "net_profit" in yoy and yoy["net_profit"].get("change", {}).get("percent") is not None:
            ch = yoy["net_profit"]["change"]["percent"]
            parts.append(f"Secara YoY, laba {'naik' if ch >= 0 else 'turun'} {abs(ch):.2f}%.")
        return " ".join(parts)

    metric_map = [
        (("aset", "asset"), "total_assets", "Total aset"),
        (("kredit", "loan"), "total_credit", "Total kredit"),
        (("dpk", "dana pihak ketiga"), "total_dpk", "Total DPK"),
        (("investasi", "investment"), "total_investment", "Total investasi"),
        (("pendapatan", "revenue"), "revenue", "Pendapatan"),
        (("beban operasional", "operating expense"), "operating_expense", "Beban operasional"),
    ]
    for terms, key, label in metric_map:
        if has(*terms) and key in current:
            return f"{label} {period}: Rp {current[key]['value']:,.2f} miliar."

    # If the evidence already contains a target analysis, provide the most
    # relevant target fact without pretending to give a strategic conclusion.
    if has("target") and evidence.get("target_analysis"):
        items = evidence["target_analysis"]
        profit = next((x for x in items if str(x.get("metric", "")).lower() in {"net profit", "laba bersih"}), None)
        if profit:
            status = "di atas" if profit.get("status") == "above" else "di bawah"
            return (
                f"Laba bersih {period} sebesar Rp {profit.get('actual', 0):,.2f} miliar, "
                f"{status} target Rp {profit.get('target', 0):,.2f} miliar "
                f"dengan pencapaian {profit.get('achievement_percent', 0):,.2f}%."
            )

    return "Data tersedia, tetapi belum cukup untuk membentuk kesimpulan yang andal."
