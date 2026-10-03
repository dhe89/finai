"""Structured FinAI LLM test logger.

Writes one JSON object per chat request to logs/finai_llm_test.jsonl.
The log is intentionally human-readable and contains no API keys.
It captures:
- user question
- semantic/evidence plan requested by the LLM
- evidence actually returned by Python
- final LLM answer
- every provider/model/stage attempt
- timing and errors

The file is JSONL so it can be appended safely without rewriting previous tests.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_LOG_ENV = "FINAI_TEST_LOG_PATH"
_DEFAULT_LOG = Path(__file__).resolve().parents[2] / "logs" / "finai_llm_test.jsonl"


def log_path() -> Path:
    configured = os.getenv(_LOG_ENV, "").strip()
    return Path(configured).expanduser() if configured else _DEFAULT_LOG


def _safe(value: Any, max_chars: int | None = None) -> Any:
    """Make arbitrary response data JSON-safe without leaking secrets."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            key = str(k).lower()
            if any(secret in key for secret in ("api_key", "apikey", "authorization", "token", "secret")):
                out[str(k)] = "[REDACTED]"
            else:
                out[str(k)] = _safe(v, max_chars)
        return out
    if isinstance(value, list):
        return [_safe(v, max_chars) for v in value]
    if isinstance(value, tuple):
        return [_safe(v, max_chars) for v in value]
    if isinstance(value, str):
        return value[:max_chars] if max_chars else value
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def append_chat_log(*, question: str, selected_period: str | None, response: dict[str, Any]) -> str:
    """Append one complete chat diagnostic record and return the log path."""
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "question": question,
        "selected_period": selected_period,
        "success": bool(response.get("ok")),
        "provider": response.get("provider"),
        "model": response.get("model"),
        "planner_source": response.get("planner_source"),
        "evidence_rounds": response.get("evidence_rounds"),
        "evidence_request_count": response.get("evidence_request_count"),
        "semantic_plan": _safe(response.get("plan")),
        "evidence_requested": _safe(response.get("evidence_requested")),
        "evidence_sent_to_analyst": _safe(response.get("evidence_sent_to_analyst")),
        "final_answer": response.get("content") if response.get("ok") else None,
        "error": response.get("error") if not response.get("ok") else None,
        "llm_attempts": _safe(response.get("attempts", [])),
    }
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with _LOCK:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    return str(path)


def read_log_bytes() -> bytes:
    path = log_path()
    if not path.exists():
        return b""
    with _LOCK:
        return path.read_bytes()
