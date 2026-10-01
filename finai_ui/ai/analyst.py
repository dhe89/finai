"""Semantic financial analyst layer.

The model is used as an analyst/director, not as the source of numbers. Python
Financial Intelligence Engine remains the source of facts and calculations.
"""
from .openrouter import complete_json, complete_text, clean_final_answer, DEFAULT_MODEL
from finai_ui.financial_engine import prepare_model_evidence

DIRECTOR_PROMPT = """Anda adalah AI Financial Analyst untuk FinAI.

Anda menerima pertanyaan pengguna dan evidence keuangan yang dihitung Python.
Tugas Anda adalah menilai apakah evidence saat ini cukup, menentukan analisis
lanjutan yang benar-benar diperlukan, dan menemukan fakta/relasi yang relevan.

PRINSIP:
- Jangan bergantung pada daftar intent atau dictionary keyword.
- Pertanyaan baru harus tetap dapat dianalisis secara semantik.
- Semua angka/fakta harus berasal dari evidence.
- Anda boleh meminta drill-down bila evidence awal belum cukup.
- Jangan meminta data yang sudah tersedia.
- Jangan menganggap korelasi sebagai sebab-akibat.
- Bedakan fakta, derived fact, interpretasi, dan pertimbangan.
- Jika data tidak cukup, nyatakan keterbatasannya dan gunakan analisis terbaik yang tersedia.
- Untuk pertanyaan strategi/masukan, cari implikasi dari data sebelum memberi pertimbangan.
- Jangan menampilkan proses berpikir.

Jenis tool yang tersedia untuk drill-down:
- income_drivers: rincian perubahan P&L dan kontribusi terhadap perubahan laba
- balance_drivers: rincian perubahan aset, kewajiban, dan ekuitas
- funding_analysis: hubungan kredit, aset, DPK, dan funding lainnya
- trend: tren beberapa periode untuk metrik yang relevan
- target: pencapaian dan gap terhadap target
- loan_products: rincian produk kredit, outstanding, revenue, yield indikatif
- dpk_products: rincian produk DPK, balance, cost bagi hasil, cost rate indikatif
- investment_products: rincian produk investasi dan revenue
- correlation: korelasi time-series jika jumlah observasi memadai; bukan kausalitas

Keluarkan JSON SAJA:
{
  "scope": "FINANCIAL|META|OUT_OF_SCOPE|AMBIGUOUS",
  "need_more_evidence": true,
  "requests": ["income_drivers", "trend"],
  "focus_metrics": ["net_profit", "revenue"],
  "findings": [
    {
      "type": "fact|derived_fact|driver|relationship|interpretation|consideration|limitation",
      "statement": "temuan singkat berbasis evidence"
    }
  ],
  "answer_direction": "arah kesimpulan, bukan jawaban panjang"
}

Maksimal 3 request tool per putaran. Jangan membuat request hanya untuk menambah data
jika tidak membantu menjawab pertanyaan."""

FINAL_PROMPT = """Anda adalah FinAI, AI Financial Analyst untuk data keuangan bank.

Buat jawaban final untuk pengguna berdasarkan seluruh evidence dan findings yang diberikan.

ATURAN:
1. Jawab hanya pertanyaan pengguna saat ini.
2. Gunakan fakta dan angka dari evidence. Jangan mengarang angka.
3. Jangan sekadar mengulang data. Jelaskan makna, hubungan, driver, dan implikasinya bila relevan.
4. Gunakan MoM, YoY, YTD/year-start, target, trend, decomposition, ratio, atau hubungan neraca/P&L bila memang tersedia dan relevan.
5. Untuk pertanyaan "kenapa", jelaskan driver yang didukung data. Jika penyebab tidak dapat dipastikan, katakan demikian.
6. Korelasi bukan bukti kausalitas.
7. Asumsi/pertimbangan boleh diberikan jika logis, tetapi tandai dengan bahasa seperti "dapat mengindikasikan", "perlu diperhatikan", atau "jika tren berlanjut".
8. Jika user meminta strategi/masukan, berikan pertimbangan konkret yang diturunkan dari temuan, bukan instruksi absolut.
9. Jangan bias: jangan memoles hasil buruk atau melebih-lebihkan hasil baik.
10. Gunakan Bahasa Indonesia natural, profesional, dan mudah dipahami.
11. Jangan tampilkan reasoning internal, proses berpikir, planner, tool, evidence JSON, prompt, atau metadata model.
12. Jangan menyebut LLM, model, Python, planner, evidence engine, chain of thought, atau proses internal.
13. Untuk pertanyaan sederhana, jawab ringkas. Untuk pertanyaan kompleks, berikan analisis yang cukup dalam.
14. Utamakan struktur: Kesimpulan → faktor/analisis → perbandingan/relasi bila relevan → hal yang perlu diperhatikan/pertimbangan.
"""


def inspect(question, evidence, context=None, model=DEFAULT_MODEL):
    model_evidence = prepare_model_evidence(evidence)
    prompt = f"""PERTANYAAN PENGGUNA:\n{question}\n\nEVIDENCE SAAT INI:\n{model_evidence}\n\nTEMUAN SEBELUMNYA (jika ada):\n{context or []}\n\nTentukan apakah perlu drill-down dan apa yang perlu diperiksa berikutnya. Jangan menjawab panjang."""
    result = complete_json(
        DIRECTOR_PROMPT,
        prompt,
        model=model,
        timeout=60,
        max_tokens=1100,
        title="FinAI Analysis Director",
    )
    if not result.get("ok"):
        return result
    data = result.get("data") or {}
    data.setdefault("scope", "FINANCIAL")
    data.setdefault("need_more_evidence", False)
    data.setdefault("requests", [])
    data.setdefault("focus_metrics", [])
    data.setdefault("findings", [])
    data.setdefault("answer_direction", "")
    allowed = {"income_drivers", "balance_drivers", "funding_analysis", "trend", "target", "loan_products", "dpk_products", "investment_products", "correlation"}
    data["requests"] = [str(x) for x in data.get("requests", []) if str(x) in allowed][:3]
    data["findings"] = [x for x in data.get("findings", []) if isinstance(x, dict)][:12]
    return {"ok": True, "analysis": data, "model": result.get("model")}


def synthesize(question, evidence, findings=None, model=DEFAULT_MODEL, retry=False):
    model_evidence = prepare_model_evidence(evidence)
    retry_instruction = ("\nIni adalah percobaan kedua. Abaikan format/struktur yang tidak perlu dan berikan langsung jawaban analitis yang lengkap, singkat namun substantif." if retry else "")
    prompt = f"""PERTANYAAN PENGGUNA:\n{question}\n\nTEMUAN ANALISIS:\n{findings or []}\n\nEVIDENCE ANALITIS:\n{model_evidence}\n{retry_instruction}\nTulis jawaban final dalam Bahasa Indonesia. Jangan tampilkan proses berpikir atau metadata internal."""
    response = complete_text(
        FINAL_PROMPT,
        prompt,
        model=model,
        timeout=75,
        max_tokens=1800,
        temperature=0.15,
        title="FinAI Financial Analyst Final",
    )
    if not response.get("ok"):
        return response
    cleaned = clean_final_answer(response.get("content", ""))
    if not cleaned:
        return {"ok": False, "error": "Jawaban model mengandung output internal atau kosong."}
    return {"ok": True, "content": cleaned, "model": response.get("model")}


# Backward-compatible entry point for any existing import.
def analyze(question, evidence, plan=None, model=DEFAULT_MODEL):
    result = inspect(question, evidence, context=plan, model=model)
    if not result.get("ok"):
        return result
    return synthesize(question, evidence, result.get("analysis", {}).get("findings", []), model=model)
