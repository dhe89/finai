# FinAI LLM Test Log

During testing, FinAI writes one JSON object per chat request to:

`logs/finai_llm_test.jsonl`

Each record contains:
- user question and selected period
- semantic plan produced by the LLM
- evidence requested by the LLM
- evidence actually returned by Python and sent to the analyst
- final LLM answer
- every provider/model/stage attempt, status, category, latency and error

The log contains no API keys. It is runtime diagnostic data and should normally be excluded from Git history.

Optional Streamlit download:
set `FINAI_ENABLE_TEST_LOG_DOWNLOAD=true` in Streamlit Secrets. The existing UI is unchanged when this setting is absent.
