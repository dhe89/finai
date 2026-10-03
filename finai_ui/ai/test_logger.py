\
"""Structured FinAI LLM test logger with optional persistent GitHub sync.

Local runtime log:
    logs/finai_llm_test.jsonl

Optional GitHub sync is enabled only when FINAI_GITHUB_LOG_SYNC is truthy and
FINAI_GITHUB_TOKEN is available (Streamlit Secrets or environment variable).
The GitHub copy is historical: each chat request appends one JSONL record to
logs/finai_llm_test.jsonl in the configured repository.

No API keys/tokens are written into the log record.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import requests

_LOCK = threading.Lock()
_LOG_ENV = "FINAI_TEST_LOG_PATH"
_DEFAULT_LOG = Path(__file__).resolve().parents[2] / "logs" / "finai_llm_test.jsonl"
_GITHUB_API = "https://api.github.com"
_GITHUB_TIMEOUT = 20


def _config(name: str, default: str = "") -> str:
    """Read Streamlit Secret first, then process environment."""
    value = ""
    try:
        import streamlit as st
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    if value is None or not str(value).strip():
        value = os.getenv(name, default)
    return str(value).strip() if value is not None else default


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def log_path() -> Path:
    configured = _config(_LOG_ENV)
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


def _github_settings() -> dict[str, str] | None:
    """Return GitHub settings when sync is explicitly enabled and configured."""
    if not _truthy(_config("FINAI_GITHUB_LOG_SYNC")):
        return None
    token = _config("FINAI_GITHUB_TOKEN")
    repo = _config("FINAI_GITHUB_REPO")
    branch = _config("FINAI_GITHUB_BRANCH", "main") or "main"
    path = _config("FINAI_GITHUB_LOG_PATH", "logs/finai_llm_test.jsonl") or "logs/finai_llm_test.jsonl"
    if not token or not repo or "/" not in repo:
        return None
    return {
        "token": token,
        "repo": repo,
        "branch": branch,
        "path": path.lstrip("/"),
    }


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "FinAI-LLM-Test-Logger",
        "Content-Type": "application/json",
    }


def _github_sync_text(text: str) -> dict[str, Any]:
    """Append text to the configured GitHub Contents API file.

    Returns a diagnostic dict safe to include in the runtime log. The token is
    never included. A short retry handles a concurrent update (HTTP 409).
    """
    cfg = _github_settings()
    if cfg is None:
        if _truthy(_config("FINAI_GITHUB_LOG_SYNC")):
            return {"enabled": True, "status": "not_configured", "error": "GitHub sync enabled but token/repository configuration is incomplete."}
        return {"enabled": False, "status": "disabled"}

    url = f"{_GITHUB_API}/repos/{cfg['repo']}/contents/{cfg['path']}"
    headers = _github_headers(cfg["token"])
    payload_text = text

    for attempt in range(2):
        try:
            get_resp = requests.get(
                url,
                headers=headers,
                params={"ref": cfg["branch"]},
                timeout=_GITHUB_TIMEOUT,
            )
            sha = None
            existing = ""
            if get_resp.status_code == 200:
                body = get_resp.json()
                sha = body.get("sha")
                # GitHub Contents API returns base64 content for normal-sized files.
                encoded = body.get("content") or ""
                if encoded:
                    existing = base64.b64decode("".join(str(encoded).split())).decode("utf-8")
            elif get_resp.status_code != 404:
                detail = get_resp.text[:500]
                return {"enabled": True, "status": "get_failed", "http_status": get_resp.status_code, "error": detail}

            combined = existing + payload_text
            encoded_content = base64.b64encode(combined.encode("utf-8")).decode("ascii")
            put_body = {
                "message": "Append FinAI LLM test log",
                "content": encoded_content,
                "branch": cfg["branch"],
            }
            if sha:
                put_body["sha"] = sha

            put_resp = requests.put(url, headers=headers, json=put_body, timeout=_GITHUB_TIMEOUT)
            if put_resp.status_code in (200, 201):
                data = put_resp.json() if put_resp.content else {}
                return {
                    "enabled": True,
                    "status": "synced",
                    "http_status": put_resp.status_code,
                    "commit": ((data.get("commit") or {}).get("sha") or "")[:12],
                    "path": cfg["path"],
                }
            if put_resp.status_code == 409 and attempt == 0:
                # Another request updated the file between GET and PUT. Re-read
                # and retry once with the new SHA.
                continue
            return {"enabled": True, "status": "put_failed", "http_status": put_resp.status_code, "error": put_resp.text[:500]}
        except requests.RequestException as exc:
            return {"enabled": True, "status": "network_error", "error": str(exc)[:500]}
        except Exception as exc:
            return {"enabled": True, "status": "unexpected_error", "error": str(exc)[:500]}

    return {"enabled": True, "status": "conflict_retry_exhausted"}


def append_chat_log(*, question: str, selected_period: str | None, response: dict[str, Any]) -> str:
    """Append one complete diagnostic record locally and optionally to GitHub."""
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
        "evidence_history": _safe(response.get("evidence_history")),
        "final_answer": response.get("content") if response.get("ok") else None,
        "error": response.get("error") if not response.get("ok") else None,
        "llm_attempts": _safe(response.get("attempts", [])),
    }
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"

    # Local write is always attempted first. This keeps the diagnostic record
    # available even when GitHub is temporarily unavailable.
    with _LOCK:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    sync_result = _github_sync_text(line)
    # Add sync status to the local record only on a best-effort sidecar file so
    # the GitHub payload remains exactly the diagnostic record above. This avoids
    # a second GitHub commit just to report its own status.
    if sync_result.get("status") not in {"disabled", "synced"}:
        try:
            diag_path = path.with_name(path.stem + "_sync_errors.jsonl")
            with _LOCK:
                with diag_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({
                        "timestamp_utc": record["timestamp_utc"],
                        "question": question,
                        "github_sync": sync_result,
                    }, ensure_ascii=False, separators=(",", ":")) + "\n")
        except Exception:
            pass
    return str(path)


def read_log_bytes() -> bytes:
    path = log_path()
    if not path.exists():
        return b""
    with _LOCK:
        return path.read_bytes()
