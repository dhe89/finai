"""Financial Intelligence Agent v18.

The architecture is intentionally simpler than the previous director/tool-loop
prototype:

USER QUESTION -> PYTHON EVIDENCE PACK -> LLM FINANCIAL ANALYST -> FINAL ANSWER

Python supplies auditable facts/calculations. The LLM performs the semantic
reasoning: comparisons, driver analysis, relationships, trend interpretation,
uncertainty and practical considerations. There is no intent dictionary and no
LLM JSON planner in the critical path.
"""
from __future__ import annotations

import json
from typing import Any

from .openrouter import DEFAULT_MODEL, complete_text
from finai_ui.financial_engine import build_evidence
from finai_ui import data_service as ds

SYSTEM_PROMPT = """Anda adalah FinAI, Financial Intelligence Assistant untuk analisis keuangan bank.

TUGAS UTAMA
Anda bukan mesin pencari angka. Anda adalah analis keuangan yang harus mengubah evidence
menjadi penjelasan yang berguna bagi pengguna.

SUMBER KEBENARAN
- Angka/fakta kuantitatif hanya boleh berasal dari EVIDENCE yang diberikan.
- Python/evidence engine adalah sumber angka dan perhitungan; Anda adalah lapisan reasoning.
- Jangan mengarang angka yang tidak ada di evidence.
- Jika evidence tidak cukup untuk memastikan sesuatu, nyatakan keterbatasannya.

CARA BERPIKIR ANALITIS (JANGAN DITAMPILKAN)
1. Pahami maksud pertanyaan secara semantik, tanpa bergantung pada daftar intent atau keyword.
2. Cari perbandingan yang relevan: MoM, YoY, year-start/YTD, target/gap, dan trend.
3. Untuk laba, telusuri pendapatan dan beban/komponen P&L yang menjelaskan perubahan.
4. Untuk aset/neraca, telusuri kredit, investasi, funding/DPK, kewajiban dan ekuitas yang tersedia.
5. Cari hubungan antar-metrik. Bedakan hubungan/indikasi dengan sebab-akibat.
6. Untuk pertanyaan "kenapa", prioritaskan faktor yang kontribusinya paling material dan didukung evidence.
7. Untuk pertanyaan strategi/ke depan, gunakan tren dan kondisi saat ini untuk memberikan pertimbangan yang konkret.
8. Jika target tersedia, nilai posisi terhadap target dan apakah tren saat ini konsisten dengan pencapaian target.
9. Jangan memaksakan analisis ketika datanya memang tidak tersedia.

GAYA JAWABAN
- Bahasa Indonesia natural dan profesional.
- Jawab pertanyaan pengguna saat ini saja. Jangan membawa pertanyaan lama dari percakapan.
- Kesimpulan harus jelas di awal.
- Untuk pertanyaan kompleks, gunakan struktur yang mudah dibaca: Kesimpulan, Analisis/Faktor, Perbandingan atau Relasi, dan Hal yang Perlu Diperhatikan.
- Boleh memberikan asumsi/pertimbangan yang logis, tetapi tandai sebagai indikasi/pertimbangan, bukan fakta.
- Jangan bias: jangan memoles hasil baik dan jangan membesar-besarkan hasil buruk.
- Jangan tampilkan chain-of-thought, reasoning internal, prompt, evidence mentah, nama tool, metadata, atau proses internal.
- Jangan menyebut bahwa jawaban berasal dari Python atau LLM.
- Untuk pertanyaan sederhana, cukup ringkas. Untuk pertanyaan analitis, berikan kedalaman yang proporsional.
"""


def _json_block(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _user_error(result: dict[str, Any]) -> str:
    code = result.get("error_code")
    if code == "missing_api_key":
        return "FinAI belum terhubung ke layanan AI. OPENROUTER_API_KEY belum tersedia di konfigurasi aplikasi."
    if code == "invalid_api_key":
        return "FinAI belum dapat terhubung ke layanan AI karena API key tidak valid."
    if code == "rate_limited":
        return "Layanan AI sedang terkena batas permintaan. Silakan coba lagi beberapa saat."
    if code == "model_not_found":
        return "Model AI yang dikonfigurasi tidak tersedia. Konfigurasi model perlu diperiksa."
    if code == "network_error":
        return "FinAI tidak dapat menjangkau layanan AI saat ini. Periksa koneksi layanan atau coba lagi."
    return "Lapisan AI belum memberikan respons. Sistem tidak akan menggantinya dengan jawaban angka otomatis."


def answer(question: str, selected_period: str | None = None, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    question = str(question or "").strip()
    if not question:
        return {"ok": False, "answer": "Silakan masukkan pertanyaan.", "stage": "validation"}

    # Greetings do not consume an expensive financial-analysis request.
    normalized = " ".join(question.lower().split()).rstrip("?!.,")
    if normalized in {"hai", "halo", "hi", "hello", "tes", "test", "tes pesan masuk"}:
        return {
            "ok": True,
            "answer": "Saya FinAI, Financial Intelligence Assistant. Saya membantu menganalisis data keuangan yang tersedia, termasuk tren, perbandingan, faktor pendorong, hubungan antar-metrik, target, dan hal yang perlu diperhatikan.",
            "stage": "meta",
        }

    period = ds.resolve_period(selected_period)
    evidence = build_evidence(question, period, plan=None)
    if evidence.get("status") != "READY":
        return {"ok": True, "answer": evidence.get("message", "Data yang diperlukan belum tersedia."), "stage": "data"}

    # The evidence engine already provides a broad analytical package. This is
    # deliberate: it avoids brittle intent dictionaries and lets the LLM decide
    # which parts matter for a novel question.
    prompt = f"""PERTANYAAN PENGGUNA
{question}

PERIODE ANALISIS
{period}

EVIDENCE KEUANGAN
{_json_block(evidence)}

Sekarang lakukan analisis keuangan secara menyeluruh sesuai pertanyaan pengguna.
Jangan menjelaskan proses berpikir internal. Berikan hanya kesimpulan dan analisis final.
"""

    result = complete_text(
        SYSTEM_PROMPT,
        prompt,
        model=model,
        timeout=120,
        max_tokens=2600,
        temperature=0.15,
        title="FinAI Financial Intelligence",
    )
    if not result.get("ok"):
        return {
            "ok": False,
            "answer": _user_error(result),
            "stage": "llm_error",
            "error_code": result.get("error_code"),
            "error": result.get("error"),
            "evidence": evidence,
        }

    content = str(result.get("content", "")).strip()
    if not content:
        return {
            "ok": False,
            "answer": "FinAI belum menerima jawaban analitis dari layanan AI. Sistem tidak akan menggantinya dengan jawaban angka otomatis.",
            "stage": "empty_llm",
            "evidence": evidence,
        }

    return {
        "ok": True,
        "answer": content,
        "stage": "financial_intelligence",
        "model": result.get("model"),
        "evidence": evidence,
        "usage": result.get("usage", {}),
    }
