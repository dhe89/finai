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
    """Final guardrail: leakage, emptiness, and clearly unsupported absolute numbers."""
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
        # Percentages and ratios are often derived by the model from evidence.
        if "%" in token:
            continue
        if digits not in re.sub(r"[^\d]", "", evidence_text):
            suspicious.append(token)

    if suspicious:
        return {
            "ok": False,
            "reason": "Jawaban memuat angka yang tidak ditemukan di evidence.",
            "suspicious_numbers": suspicious[:5],
        }
    return {"ok": True}


def _fmt(v):
    return f"Rp {float(v):,.2f} miliar"


def _analytical_python_fallback(evidence, question=""):
    """Useful deterministic analysis when the LLM provider is unavailable.

    This is deliberately richer than the old one-line fallback. It never claims
    a causal relationship that is not supported by the data. The LLM remains the
    preferred analyst; this function only keeps the application useful during
    provider failures/timeouts.
    """
    q = " ".join(str(question or "").lower().split())
    cur = evidence.get("current", {}) or {}
    period = evidence.get("selected_period")
    mom = (evidence.get("comparisons") or {}).get("mom", {}).get("metrics", {})
    yoy = (evidence.get("comparisons") or {}).get("yoy", {}).get("metrics", {})
    tools = evidence.get("analysis_tools", {}) or {}

    # Profit diagnosis
    if any(x in q for x in ["kenapa laba", "mengapa laba", "faktor", "sehat", "laba meningkat"]):
        inc = tools.get("income_drivers") or {}
        monthly = inc.get("monthly_flow") or {}
        drivers = inc.get("monthly_flow_drivers") or []
        support = [x for x in drivers if x.get("profit_direction") == "support"]
        pressure = [x for x in drivers if x.get("profit_direction") == "pressure"]
        p = cur.get("net_profit", {}).get("value")
        yoyp = (yoy.get("net_profit") or {}).get("change", {}).get("percent")
        momflow = monthly.get("net_profit", {}).get("change", {}).get("percent")
        parts = []
        if p is not None:
            parts.append(f"Laba bersih kumulatif sampai {period} sebesar {_fmt(p)}.")
        if monthly.get("net_profit"):
            mf = monthly["net_profit"]
            parts.append(
                f"Laba yang dibukukan selama {period} sekitar {_fmt(mf.get('current_flow', 0))}, "
                f"dibanding {_fmt(mf.get('previous_flow', 0))} pada bulan sebelumnya ({'naik' if (momflow or 0) >= 0 else 'turun'} {abs(momflow or 0):.2f}%)."
            )
        if support:
            top = support[:3]
            parts.append("Penopang utama bulan berjalan antara lain " + "; ".join(
                f"{x['line_item']} {('+' if x['current_flow'] >= 0 else '')}{_fmt(x['current_flow'])}" for x in top
            ) + ".")
        if pressure:
            top = pressure[:3]
            parts.append("Tekanan utama berasal dari " + "; ".join(
                f"{x['line_item']} {_fmt(x['current_flow'])}" for x in top
            ) + ".")
        if yoyp is not None:
            parts.append(f"Secara YoY kumulatif, laba tumbuh {yoyp:.2f}%.")
        parts.append("Data ini mendukung kesimpulan bahwa kenaikan laba perlu dilihat sebagai hasil bersih antara penopang pendapatan dan tekanan biaya; data yang tersedia belum cukup untuk menyatakan satu faktor sebagai penyebab tunggal.")
        return " ".join(parts)

    # Asset/funding diagnosis
    if any(x in q for x in ["pertumbuhan aset", "menopang pertumbuhan aset", "aset september", "kredit dan funding", "funding"]):
        bal = tools.get("balance_drivers") or {}
        fund = tools.get("funding_analysis") or {}
        asset = (bal.get("drivers") or {}).get("asset", [])[:4]
        liab = (bal.get("drivers") or {}).get("kewajiban", [])[:4]
        vals = fund.get("values", {})
        ratios = fund.get("ratios", {})
        text = [f"Total aset {period} sebesar {_fmt(cur.get('total_assets', {}).get('value', 0))}."]
        if asset:
            text.append("Perubahan aset terutama berasal dari " + "; ".join(
                f"{x['line_item']} {x['change']['absolute']:+,.2f} miliar" for x in asset[:3]
            ) + ".")
        if vals.get("total_credit") is not None and vals.get("total_dpk") is not None:
            text.append(
                f"Kredit sebesar {_fmt(vals['total_credit'])} setara {ratios.get('credit_to_asset_percent', 0):.2f}% aset, "
                f"sedangkan DPK sebesar {_fmt(vals['total_dpk'])} dengan kredit/DPK sekitar {ratios.get('credit_to_dpk_percent', 0):.2f}%.")
        if liab:
            text.append("Pada sisi pendanaan, perubahan terbesar antara lain " + "; ".join(
                f"{x['line_item']} {x['change']['absolute']:+,.2f} miliar" for x in liab[:3]
            ) + ".")
        text.append("Struktur tersebut menunjukkan sumber pendanaan yang tersedia dalam data, tetapi belum cukup untuk menyimpulkan kecukupan likuiditas secara menyeluruh.")
        return " ".join(text)

    # Target/sustainability diagnosis
    if any(x in q for x in ["target laba", "target tahun 2026", "dipertahankan", "risiko", "sampai akhir tahun"]):
        targets = evidence.get("target_analysis") or []
        profit = next((x for x in targets if x.get("metric") == "Net Profit"), None)
        trend = tools.get("trend", {}).get("periods", [])
        text = []
        if profit:
            text.append(
                f"Laba bersih {period} sebesar {_fmt(profit['actual'])}, dibanding target {_fmt(profit['target'])}; "
                f"pencapaian {profit['achievement_percent']:.2f}% dan gap {profit['gap']:+,.2f} miliar."
            )
        # Current quality/efficiency signals
        for key, label in [("revenue", "pendapatan"), ("operating_expense", "beban operasional"), ("npl_ratio", "NPL"), ("ckpn_coverage", "CKPN Coverage")]:
            if key in cur:
                text.append(f"{label.capitalize()} saat ini {cur[key]['value']:.2f}{'%' if cur[key]['unit'] == '%' else ' miliar'}.")
        text.append("Pencapaian target saat ini sangat dekat dengan target, tetapi keberlanjutannya tetap perlu dipantau melalui tren laba, pendapatan, beban, serta indikator kualitas aset yang tersedia.")
        return " ".join(text)

    # Generic factual fallback
    if "net_profit" in cur:
        return f"Laba bersih kumulatif sampai {period} sebesar {_fmt(cur['net_profit']['value'])}."
    return "Data tersedia, tetapi analisis yang lebih spesifik belum dapat disusun dari data yang tersedia."


def fallback_answer(evidence, question="", analytical=False):
    """Fallback that is explicit about the requested question and still useful."""
    if analytical:
        return _analytical_python_fallback(evidence, question)

    current = evidence.get("current", {})
    period = evidence.get("selected_period")
    if not current:
        return "Data yang diperlukan belum tersedia."

    q = " ".join(str(question or "").lower().split())
    if any(x in q for x in ["laba", "profit"]):
        npv = current.get("net_profit", {}).get("value")
        if npv is not None:
            monthly = (evidence.get("analysis_tools") or {}).get("income_drivers", {}).get("monthly_flow", {})
            if monthly.get("net_profit"):
                mf = monthly["net_profit"]
                return (
                    f"Laba bersih kumulatif sampai {period}: {_fmt(npv)}. "
                    f"Laba yang dibukukan selama {period}: {_fmt(mf.get('current_flow', 0))}."
                )
            return f"Laba bersih kumulatif sampai {period}: {_fmt(npv)}."

    metric_map = [
        (("aset", "asset"), "total_assets", "Total aset"),
        (("kredit", "loan"), "total_credit", "Total kredit"),
        (("dpk", "dana pihak ketiga"), "total_dpk", "Total DPK"),
        (("investasi", "investment"), "total_investment", "Total investasi"),
        (("pendapatan", "revenue"), "revenue", "Pendapatan"),
    ]
    for terms, key, label in metric_map:
        if any(t in q for t in terms) and key in current:
            return f"{label} {period}: {_fmt(current[key]['value'])}."

    return "Data tersedia, tetapi belum cukup untuk membentuk kesimpulan yang andal."
