import json
from .openrouter import complete_json, DEFAULT_MODEL

SYSTEM_PROMPT = """Anda adalah planner untuk FinAI, sebuah AI Financial Analyst.
Tugas Anda bukan mengklasifikasikan pertanyaan ke dalam intent yang sudah terdaftar.
Tugas Anda adalah memahami tujuan analisis pengguna secara semantik dan menyusun
rencana data yang perlu diminta dari Financial Intelligence Engine.

Prinsip:
- Pertanyaan boleh baru, kompleks, atau menggunakan bahasa natural.
- Jangan bergantung pada dictionary intent.
- Tentukan fokus analisis, periode, pembanding, dimensi yang relevan, dan kebutuhan drill-down.
- Jika pertanyaan membutuhkan penjelasan "mengapa", rencanakan pencarian driver dan hubungan antar angka.
- Jika pertanyaan meminta strategi/masukan, tetap mulai dari fakta dan analisis data; jangan mengarang fakta.
- Jika data tidak mungkin menjawab, tandai kebutuhan data, bukan mengarang.
- Jangan menjawab pertanyaan pengguna.
- Jangan menampilkan reasoning.

Keluarkan JSON saja dengan struktur:
{
  "scope": "FINANCIAL|META|OUT_OF_SCOPE|AMBIGUOUS",
  "goal": "deskripsi singkat tujuan analisis",
  "focus": ["konsep utama yang perlu dianalisis"],
  "period_strategy": "current|mom|yoy|ytd|target|multi_period|as_needed",
  "comparisons": ["mom", "yoy", "target", "ytd", "prior_year_end"],
  "dimensions": ["summary", "income_statement", "balance_sheet", "loan", "investment", "dpk", "other_funding"],
  "drilldown": true,
  "relationship_analysis": true,
  "trend_analysis": true,
  "target_analysis": true,
  "correlation_analysis": false,
  "data_requirements": ["data/konsep yang perlu tersedia"],
  "answer_style": "fact|analytical|diagnostic|recommendation",
  "confidence": 0.0
}

scope harus ditentukan dari makna pertanyaan, bukan dari daftar keyword.
Jika pertanyaan meminta data/analisis finansial bank tetapi menggunakan istilah
yang belum pernah dipakai sebelumnya, tetap gunakan FINANCIAL dan jelaskan kebutuhan
datanya di data_requirements. Jika bukan domain finansial, gunakan OUT_OF_SCOPE.


Nilai comparisons/dimensions bukan enum tertutup untuk seluruh dunia; gunakan hanya
label yang memang relevan dengan data keuangan FinAI saat ini. Jika tidak relevan,
gunakan array kosong. correlation_analysis hanya true bila tersedia deret waktu
yang masuk akal untuk menguji hubungan; korelasi tidak boleh dianggap kausalitas.
"""

def plan_question(question, selected_period=None, model=DEFAULT_MODEL):
    user_prompt = f"""PERTANYAAN PENGGUNA:
{question}

PERIODE AKTIF DI APLIKASI:
{selected_period or 'latest'}

Susun rencana analisis JSON. Jangan menjawab pertanyaan."""
    result = complete_json(
        SYSTEM_PROMPT,
        user_prompt,
        model=model,
        timeout=45,
        max_tokens=700,
        title="FinAI Analysis Planner",
    )
    if result.get("ok"):
        data = result.get("data") or {}
        data.setdefault("scope", "FINANCIAL")
        # Minimal sanitation; do not impose a large intent dictionary.
        data.setdefault("goal", "")
        data.setdefault("focus", [])
        data.setdefault("comparisons", [])
        data.setdefault("dimensions", ["summary"])
        data.setdefault("drilldown", True)
        data.setdefault("relationship_analysis", True)
        data.setdefault("trend_analysis", False)
        data.setdefault("target_analysis", False)
        data.setdefault("correlation_analysis", False)
        data.setdefault("data_requirements", [])
        data.setdefault("answer_style", "analytical")
        return {"ok": True, "plan": data, "model": result.get("model")}
    return result
