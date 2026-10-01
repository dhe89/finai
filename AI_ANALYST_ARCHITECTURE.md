# FinAI — Dynamic Financial Analyst Architecture

## Tujuan
FinAI bukan chatbot yang menghafal intent. FinAI menggunakan LLM sebagai **semantic analyst/director** dan Python sebagai **Financial Intelligence Engine** yang menjadi sumber fakta, perhitungan, dan drill-down.

## Alur

```text
User Question
     │
     ▼
Semantic Analyst / Director
     │
     ├── scope
     ├── findings awal
     └── request tool bila perlu
     │
     ▼
Python Financial Intelligence Engine
     │
     ├── comparison
     ├── trend
     ├── target
     ├── driver / decomposition
     ├── balance & funding relationship
     ├── product economics
     └── correlation (bila relevan)
     │
     ▼
Bounded Agent Loop (maks. 3 putaran)
     │
     ▼
Final Analyst Synthesis
     │
     ▼
Deterministic Verifier
     │
     ▼
Final Answer
```

## Prinsip
1. Tidak ada intent dictionary sebagai pusat arsitektur.
2. Planner/semantic director **bukan gate**. Jika LLM gagal, FinAI tetap melakukan analisis dengan evidence awal dan default toolset.
3. LLM tidak menjadi sumber angka.
4. Semua angka dan perhitungan berasal dari Python.
5. LLM boleh meminta drill-down secara dinamis.
6. Maksimal 3 putaran agent dan maksimal 3 tool request per putaran untuk menjaga biaya/latency.
7. Korelasi tidak boleh dipresentasikan sebagai kausalitas.
8. Fakta, derived fact, driver, interpretation, consideration, dan limitation harus dibedakan secara konseptual.
9. Reasoning internal tidak ditampilkan kepada user.
10. Jawaban akhir harus Bahasa Indonesia dan menjawab pertanyaan aktif saja.

## Tool yang tersedia
- `income_drivers`
- `balance_drivers`
- `funding_analysis`
- `trend`
- `target`
- `loan_products`
- `dpk_products`
- `investment_products`
- `correlation`

Tool baru dapat ditambahkan tanpa membuat intent baru.

## Evidence hierarchy
- **Fact:** angka/data langsung.
- **Derived fact:** hasil perhitungan Python, misalnya MoM/YoY/gap.
- **Driver:** komponen yang memberikan kontribusi terhadap perubahan.
- **Relationship:** hubungan antar metrik/struktur.
- **Interpretation:** makna yang didukung data.
- **Consideration:** implikasi/asumsi yang diberi penanda.
- **Limitation:** hal yang tidak dapat dipastikan karena data tidak tersedia.

## Guardrail
Verifier memeriksa output internal, jawaban kosong, dan angka yang tidak dapat ditelusuri ke evidence. Jika analyst gagal, deterministic fallback hanya memberikan fakta yang dapat dipastikan dari evidence.
