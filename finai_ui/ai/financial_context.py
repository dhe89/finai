"""Backward-compatible entry points for FinAI evidence generation."""
from __future__ import annotations
from typing import Any
from .evidence_engine import execute_evidence_plan


def build_analysis_context(question: str, selected_period: str | None = None) -> dict[str, Any]:
    """Legacy compatibility: request the broad baseline evidence.

    New chat flows should use the planner-driven execute_evidence_plan() instead.
    """
    plan = {"requests": [
        {"id": "summary_kpi", "comparisons": ["mom", "yoy", "target"]},
        {"id": "balance_sheet", "comparisons": ["mom"]},
        {"id": "income_statement", "comparisons": ["mom"]},
        {"id": "loan_products", "comparisons": ["mom"]},
        {"id": "dpk_products", "comparisons": ["mom"]},
    ]}
    return execute_evidence_plan(plan, selected_period)
