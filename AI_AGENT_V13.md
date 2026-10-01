# FinAI AI Agent v13

## Implemented
- Removed `finai_ui/ai/planner.py` from the critical architecture.
- Added semantic analyst/director that can request analytical tools dynamically.
- Added bounded agent loop (maximum 3 inspection rounds).
- Added dynamic financial tools for P&L drivers, balance-sheet drivers, funding, trend, target, loan products, DPK, investments, and correlation.
- Added compact model-evidence layer to reduce context size.
- Added findings collection and final synthesis.
- Strengthened verifier and deterministic fallback.
- Preserved UI/frontend and CSV data.

## GitHub changes
### Delete
- `finai_ui/ai/planner.py`
- `AI_RUNTIME_FIX_V12.md`

### Add
- `tests/test_financial_agent.py`
- `AI_AGENT_V13.md`

### Replace
- `app.py`
- `README.md`
- `DATA_FLOW.md`
- `AI_ANALYST_ARCHITECTURE.md`
- `finai_ui/ai/analyst.py`
- `finai_ui/ai/openrouter.py`
- `finai_ui/ai/orchestrator.py`
- `finai_ui/ai/verifier.py`
- `finai_ui/financial_engine.py`

### Keep unchanged
- `finai_ui/frontend/`
- `data/`
- `build_data.py`
- `requirements.txt`
- `finai_ui/data_service.py`

## Validation
The repository compiles successfully and the local financial-engine tests pass. Live LLM behavior must still be tested after deployment because the LLM provider is external.
