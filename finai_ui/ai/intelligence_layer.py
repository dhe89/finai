"""Semantic planning helpers for FinAI.

The LLM chooses meaning and evidence requirements; Python validates scope and
normalizes the request so range questions cannot silently collapse to endpoints.
Python does not infer user intent or select evidence on its own.
"""
from __future__ import annotations
from typing import Any
from finai_ui import data_service as ds

SCOPE_TYPES = {"POINT", "COMPARISON", "RANGE", "TREND", "YTD", "DIAGNOSIS", "TARGET_ANALYSIS", "SCENARIO"}
ANALYSIS_TYPES = {"SNAPSHOT", "MOM", "YOY", "YTD", "TREND", "DRIVER_ANALYSIS", "TARGET_GAP", "TARGET_HISTORY", "TURNING_POINT", "HIGHEST_LOWEST", "CONTRIBUTION", "SCENARIO"}


def normalize_scope(plan: dict[str, Any], selected_period: str | None) -> dict[str, Any]:
    plan = dict(plan or {})
    scope = dict(plan.get("scope") or {})
    scope_type = str(scope.get("scope_type") or plan.get("scope_type") or "POINT").upper()
    if scope_type not in SCOPE_TYPES:
        scope_type = "POINT"

    periods = ds.available_periods()
    active = ds.resolve_period(selected_period)
    start = str(scope.get("start_period") or plan.get("start_period") or "").strip()
    end = str(scope.get("end_period") or plan.get("end_period") or "").strip()
    if end not in periods:
        end = active

    # For YTD the semantic start is January of the requested ending year.
    # This is normalization of an explicit YTD scope, not intent inference.
    if scope_type == "YTD" and not start and end:
        start = f"{end[:4]}-01"
    elif start not in periods:
        start = end

    if start and end and start > end:
        start, end = end, start

    # Explicitly supplied distinct endpoints always require the complete range.
    if start and end and start != end and scope_type == "POINT":
        scope_type = "RANGE"

    include_all = bool(scope.get("include_all_periods", plan.get("include_all_periods", False)))
    if start and end and start != end:
        include_all = True
    if scope_type in {"RANGE", "TREND", "YTD", "DIAGNOSIS", "TARGET_ANALYSIS"}:
        include_all = True

    granularity = str(scope.get("granularity") or "MONTHLY").upper()
    if granularity not in {"MONTHLY", "PERIOD"}:
        granularity = "MONTHLY"

    analysis = scope.get("analysis") or plan.get("analysis") or []
    if not isinstance(analysis, list):
        analysis = []
    analysis = [str(x).upper() for x in analysis if str(x).upper() in ANALYSIS_TYPES]
    if scope_type == "COMPARISON" and not analysis:
        analysis = ["MOM"]
    if scope_type in {"RANGE", "TREND"} and "TREND" not in analysis:
        analysis.insert(0, "TREND")
    if scope_type == "YTD" and "YTD" not in analysis:
        analysis.append("YTD")

    scope.update({
        "scope_type": scope_type,
        "start_period": start,
        "end_period": end,
        "granularity": granularity,
        "include_all_periods": include_all,
        "analysis": list(dict.fromkeys(analysis)),
    })
    plan["scope"] = scope
    plan["scope_type"] = scope_type
    return plan


def periods_between(start: str | None, end: str | None) -> list[str]:
    periods = ds.available_periods()
    if not start or not end:
        return []
    return [p for p in periods if start <= p <= end]


def attach_scope_to_requests(plan: dict[str, Any]) -> dict[str, Any]:
    """Propagate normalized scope; never choose evidence semantics."""
    scope = plan.get("scope") or {}
    out = dict(plan)
    reqs = []
    for raw in plan.get("requests", []) if isinstance(plan.get("requests"), list) else []:
        if not isinstance(raw, dict):
            continue
        r = dict(raw)
        if scope.get("include_all_periods"):
            r["start_period"] = scope.get("start_period")
            r["end_period"] = scope.get("end_period")
            r["granularity"] = scope.get("granularity", "MONTHLY")
            r["include_all_periods"] = True
        if "trend" not in r.get("comparisons", []) and "TREND" in scope.get("analysis", []):
            r["comparisons"] = list(r.get("comparisons", [])) + ["trend"]
        r.setdefault("analysis", scope.get("analysis", []))
        reqs.append(r)
    out["requests"] = reqs
    return out


def evidence_coverage(evidence: dict[str, Any], requested_start: str | None, requested_end: str | None) -> dict[str, Any]:
    requested = periods_between(requested_start, requested_end)
    blocks = evidence.get("blocks") or {}
    coverage: dict[str, Any] = {}
    for key, block in blocks.items():
        got = block.get("periods") if isinstance(block, dict) else None
        if not isinstance(got, list):
            got = []
        got = [str(x) for x in got]
        missing = [p for p in requested if p not in got]
        coverage[key] = {
            "requested_periods": len(requested),
            "returned_periods": len([p for p in got if p in requested]),
            "missing_periods": missing,
            "complete": not missing,
        }
    return {"requested_range": [requested_start, requested_end], "coverage": coverage}
