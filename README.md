# FinAI

FinAI adalah prototype **AI Financial Analyst** untuk menganalisis data keuangan bank yang tersedia pada aplikasi.

## Arsitektur AI
FinAI menggunakan pola dynamic analysis:

```text
Question
  ↓
Semantic Analyst
  ↓
Python Financial Intelligence Engine
  ↓
Dynamic Drill-down (bounded)
  ↓
Analyst Synthesis
  ↓
Verifier
  ↓
Final Answer
```

FinAI tidak bergantung pada daftar intent sebagai pusat logika. Model dapat meminta analisis tambahan sesuai pertanyaan, sedangkan Python menghitung dan menyediakan fakta.

## Struktur AI
- `finai_ui/financial_engine.py` — data access, calculation, comparison, trend, driver, relationship, product economics, correlation.
- `finai_ui/ai/analyst.py` — semantic analysis director dan final synthesis.
- `finai_ui/ai/orchestrator.py` — bounded agent loop.
- `finai_ui/ai/verifier.py` — deterministic guardrail dan fallback.
- `finai_ui/ai/openrouter.py` — provider client.

## UI
Frontend/mobile/desktop merupakan baseline dan tidak menjadi bagian dari refactor AI ini.

## Data
CSV pada folder `data/` tetap menjadi sumber data prototype.
