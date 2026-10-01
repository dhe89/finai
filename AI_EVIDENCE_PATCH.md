# FinAI — AI Evidence-First Patch

Baseline: `finai-main-9`

## Tujuan
Mengubah pipeline AI agar Python menjadi sumber fakta/evidence. LLM hanya menyusun jawaban berdasarkan evidence yang diberikan Python.

## File yang berubah
1. `app.py`
2. `finai_ui/data_service.py`
3. `finai_ui/ai/openrouter.py`

## File yang TIDAK berubah
- HTML
- CSS
- JavaScript
- seluruh CSV/data simulasi
- struktur folder
- requirements.txt

## Perubahan utama
- Validasi pertanyaan dilakukan sebelum OpenRouter dipanggil.
- Pertanyaan di luar scope diblokir.
- Pertanyaan ambigu diminta klarifikasi.
- Periode eksplisit dibaca oleh Python; jika tidak tersedia, request dihentikan.
- Metrik yang belum tersedia (contoh ROA/ROE/CAR) tidak ditebak.
- Evidence diambil langsung dari CSV oleh Python.
- Evidence dibuat minimal sesuai kebutuhan pertanyaan, bukan seluruh dashboard.
- Python menghitung perubahan absolut dan persentase untuk perbandingan.
- Untuk diagnosis laba, Python menyediakan komponen P&L yang relevan.
- LLM dilarang menggunakan angka dari jawaban assistant sebelumnya sebagai fakta.
- Reasoning/chain-of-thought dari provider tidak dikirim ke user.
- Temperature LLM diturunkan menjadi 0.0 untuk respons lebih deterministik.
- Jawaban menggunakan bahasa Indonesia.

## Hasil uji lokal
PASS:
- fakta sederhana: `Berapa laba September 2026?`
- diagnosis: `Kenapa laba September 2026 turun?`
- perbandingan periode
- metrik tidak tersedia: ROA
- periode tidak tersedia
- pertanyaan ambigu
- pertanyaan di luar scope
- line item laporan keuangan: Kas
- target laba
