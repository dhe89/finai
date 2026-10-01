# FinAI — Financial Intelligence Analyst

FinAI adalah prototype financial intelligence untuk simulasi bank syariah. **Baseline UI desktop/mobile tidak diubah** pada pekerjaan data ini; perubahan difokuskan pada konten, dataset, rendering halaman, dan evidence AI.

## Struktur

- `app.py` — Streamlit host/router dan event bridge.
- `finai_ui/data_service.py` — loader, agregasi, rendering konten, dan evidence context.
- `finai_ui/frontend/` — shell UI, CSS, JS, layout dan page assets. Dipertahankan dari baseline UI.
- `data/` — dataset simulasi dan hasil audit pembentukan data.

## Profil simulasi

Semua nominal menggunakan **Rp miliar**.

- Modal: Rp6.000 miliar (Rp6 triliun)
- Target aset September 2026: Rp80.000 miliar
- Target kredit September 2026: Rp60.000 miliar
- Target DPK September 2026: Rp65.000 miliar
- Target laba bersih tahunan 2026: Rp1.000 miliar
- Coverage data: Januari 2024 sampai September 2026

## Dataset

- `monthly_summary.csv` — KPI bulanan dashboard.
- `balance_sheet.csv` — laporan posisi neraca.
- `income_statement.csv` — laporan laba rugi.
- `monthly_targets.csv` — target bulanan growth, profitability, efficiency dan quality.
- `loan_detail.csv` — rincian kredit bulanan.
- `investment_detail.csv` — rincian investasi bulanan.
- `dpk_detail.csv` — rincian rekening DPK bulanan.
- `other_funding_detail.csv` — rincian dana lainnya bulanan.
- `account_lifecycle.csv` — master lifecycle account.
- `account_status_monthly.csv` — status NEW/ACTIVE/CLOSED/NOT_STARTED per bulan.
- `audit_checks.csv` — hasil cross-check pembentukan data.

## Konsistensi

Data dibentuk dengan hubungan berikut:

1. Detail kredit = posisi Kredit di neraca.
2. Detail investasi = posisi Penempatan di neraca.
3. Detail DPK = Giro + Tabungan + Deposito di neraca.
4. Aset = Kewajiban + Ekuitas setiap bulan.
5. Laba Tahun Berjalan di neraca = akumulasi Laba Bersih tahun berjalan sampai bulan tersebut.
6. Pendapatan/beban produk berasal dari detail produk.
7. Lifecycle account mencakup account baru, account aktif dan account yang ditutup.
8. `audit_checks.csv` dibuat pada saat pembentukan data; seluruh check harus PASS sebelum dataset dipakai aplikasi.

## AI Architecture

FinAI menggunakan arsitektur **Financial Analyst**, bukan intent/dictionary router.

Alur runtime:

```text
User Question
     ↓
Semantic Analysis Planner (LLM)
     ↓
Financial Intelligence Engine (Python)
     ↓
MoM / YoY / Year-start / Target / Trend / Driver / Relationship / Drill-down
     ↓
AI Financial Analyst (LLM)
     ↓
Deterministic Verifier
     ↓
Final Answer
```

Planner memahami pertanyaan secara semantik dan menentukan data/analisis yang dibutuhkan. Planner tidak menentukan daftar intent tetap. Python menjadi source of truth untuk angka, perhitungan, perubahan, kontribusi dan hubungan data. Analyst kemudian menjelaskan temuan, memberi konteks dan pertimbangan tanpa mengubah fakta. Verifier mencegah kebocoran reasoning dan angka yang tidak ditemukan di evidence.

### Prinsip

- Tidak ada ketergantungan pada `intent.py` atau dictionary intent.
- Pertanyaan baru dapat dipahami secara semantik oleh planner.
- Python melakukan perhitungan dan menyediakan evidence yang dapat diaudit.
- Analyst boleh melakukan interpretasi dan memberikan pertimbangan, tetapi asumsi harus diberi penanda dan tidak boleh disajikan sebagai fakta.
- Korelasi tidak dianggap sebagai kausalitas.
- Chat history hanya untuk UI; tidak dikirim sebagai rangkaian pertanyaan lama ke analyst.
- Reasoning internal tidak ditampilkan kepada user.
- Jika model gagal, aplikasi menggunakan fallback deterministic yang aman.


## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```
