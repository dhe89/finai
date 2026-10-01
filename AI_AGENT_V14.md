# FinAI AI Agent v14 — Reliability & Analytical Evidence Update

## Tujuan
Memastikan AI Financial Analyst benar-benar dapat melakukan analisis, tetapi tidak menjadi rapuh ketika semantic director atau provider LLM gagal.

## Perubahan utama
1. **Semantic director bukan gate**.
   - Evidence analitis dasar sekarang selalu dibangun oleh Python.
   - Jika director gagal, final synthesis tetap dapat berjalan.

2. **Base analytical evidence diperkuat**.
   - P&L dibedakan antara angka kumulatif/YTD dan monthly flow.
   - Driver laba menggunakan monthly flow, bukan salah memberi label perubahan kumulatif sebagai pertumbuhan MoM.
   - Balance-sheet drivers, funding structure, trend, dan target tersedia sejak awal.

3. **LLM context diperkecil**.
   - `prepare_model_evidence()` mengirim evidence yang ringkas dan relevan.
   - Raw evidence tetap disimpan untuk audit/verifikasi.

4. **Latency dikurangi**.
   - Pertanyaan faktual sederhana dijawab deterministik oleh Python.
   - Pertanyaan analitis menggunakan maksimal satu semantic-director pass, satu focused drill-down pass, lalu final synthesis.

5. **Fallback diperbaiki**.
   - Jika LLM unavailable/timeout, fallback tidak lagi sekadar mengulang satu angka.
   - Python dapat menyusun analisis deterministik berbasis driver, monthly flow, balance/funding, dan target.
   - Fallback tidak dipresentasikan sebagai jawaban LLM.

6. **Final synthesis retry**.
   - Jika jawaban pertama gagal guardrail, satu retry dengan prompt yang lebih sederhana dilakukan sebelum fallback.

7. **Verifier tetap aktif**.
   - Memblokir internal reasoning/metadata leakage.
   - Memeriksa angka absolut yang jelas tidak didukung evidence.

## Prinsip data penting
Dataset P&L bersifat kumulatif melalui bulan berjalan. Karena itu:

- `778.85` = laba bersih kumulatif sampai September 2026.
- `81.26` = laba yang dibukukan selama September 2026 (`778.85 - 697.59`).
- Pertumbuhan laba bulanan September terhadap Agustus dihitung dari monthly flow, yaitu sekitar `4.38%` (`81.26` dibanding `77.85`), bukan 11.65%.

## File utama yang berubah
- `finai_ui/financial_engine.py`
- `finai_ui/ai/orchestrator.py`
- `finai_ui/ai/analyst.py`
- `finai_ui/ai/verifier.py`
- `tests/test_financial_agent.py`
