# FinAI Data Flow

```text
CSV
 │
 ▼
data_service.py
 │
 ▼
financial_engine.py
 │
 ├── initial evidence
 └── dynamic analytical tools
        │
        ▼
ai/analyst.py
 │
 ├── inspect()
 │      └── memilih kebutuhan drill-down
 │
 └── synthesize()
        │
        ▼
ai/orchestrator.py
 │
 ├── bounded loop
 ├── expand_evidence()
 └── verifier
        │
        ▼
Streamlit chat
```

Chat history hanya untuk tampilan UI. History tidak dikirim sebagai daftar pertanyaan sebelumnya kepada model.

## Failure behavior
- Director gagal → gunakan default analytical context.
- Tool gagal → agent tetap dapat melanjutkan dengan evidence yang tersedia.
- Final analyst gagal → deterministic fallback.
- Exception runtime → UI menerima pesan bersih, bukan menggantung pada typing indicator.
