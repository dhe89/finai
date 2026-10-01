"""Build compact, evidence-first context for FinAI's LLM reasoning layer.

Python is responsible for selecting periods and calculating deterministic deltas.
The LLM is responsible for interpretation, explanation, and management-oriented
reasoning. This module deliberately does not generate the final answer.
"""
from __future__ import annotations

import re
from typing import Any

from finai_ui import data_service as ds

_MONTHS = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5,
    "juni": 6, "juli": 7, "agustus": 8, "september": 9, "oktober": 10,
    "november": 11, "desember": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}

_KPIS = [
    "total_assets", "total_credit", "total_investment", "total_dpk",
    "total_other_funding", "net_profit", "revenue", "operating_expense",
    "ckpn", "npl_ratio", "ckpn_coverage", "low_cost_funding",
]


def _period_from_question(question: str) -> str | None:
    text = str(question or "").lower()
    found = []
    for match in re.finditer(r"\b([a-z]+)\s+(20\d{2})\b", text):
        month = _MONTHS.get(match.group(1))
        if month:
            found.append(f"{int(match.group(2)):04d}-{month:02d}")
    for match in re.finditer(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", text):
        found.append(f"{match.group(1)}-{match.group(2)}")
    for period in found:
        if period in ds.available_periods():
            return period
    return None


def _row(period: str) -> dict[str, float]:
    row = ds.srow(period)
    return {key: float(row[key]) for key in _KPIS if key in row.index}


def _changes(current: dict[str, float], previous: dict[str, float]) -> dict[str, dict[str, float | None]]:
    result: dict[str, dict[str, float | None]] = {}
    for key, value in current.items():
        old = previous.get(key)
        if old is None:
            continue
        delta = value - old
        result[key] = {
            "absolute": delta,
            "percent": (delta / old * 100.0) if old else None,
        }
    return result


def _line_item_changes(current_period: str, previous_period: str) -> list[dict[str, Any]]:
    """Return the largest P&L line-item movements, without assigning causality."""
    current = ds.IS[ds.IS.period.eq(current_period)].copy()
    previous = ds.IS[ds.IS.period.eq(previous_period)].copy()
    if current.empty or previous.empty:
        return []

    old = dict(zip(previous.line_item.astype(str), previous.amount.astype(float)))
    rows = []
    for _, row in current.iterrows():
        name = str(row.line_item)
        value = float(row.amount)
        if name not in old:
            continue
        prior = old[name]
        delta = value - prior
        rows.append({
            "line_item": name,
            "current": value,
            "previous": prior,
            "change_absolute": delta,
            "change_percent": (delta / prior * 100.0) if prior else None,
        })
    rows.sort(key=lambda item: abs(item["change_absolute"]), reverse=True)
    return rows[:10]


def _product_changes(df, period: str, previous_period: str, key: str, value: str, extra: str) -> list[dict[str, Any]]:
    cur = ds.agg(df, period, key, value, extra)
    prev = ds.agg(df, previous_period, key, value, extra)
    if cur.empty:
        return []
    old = {str(row[key]): {value: float(row[value]), extra: float(row[extra])} for _, row in prev.iterrows()}
    rows = []
    for _, row in cur.iterrows():
        name = str(row[key])
        current_value = float(row[value])
        previous_value = old.get(name, {}).get(value)
        current_extra = float(row[extra])
        previous_extra = old.get(name, {}).get(extra)
        rows.append({
            key: name,
            value: current_value,
            "previous_" + value: previous_value,
            "change_" + value: (current_value - previous_value) if previous_value is not None else None,
            extra: current_extra,
            "previous_" + extra: previous_extra,
            "change_" + extra: (current_extra - previous_extra) if previous_extra is not None else None,
        })
    rows.sort(key=lambda item: abs(item.get("change_" + value) or 0), reverse=True)
    return rows[:8]


def build_analysis_context(question: str, selected_period: str | None = None) -> dict[str, Any]:
    """Create a bounded evidence pack for LLM reasoning."""
    ds.ensure_data_fresh()
    explicit = _period_from_question(question)
    period = explicit or ds.resolve_period(selected_period)
    if not period:
        return {"status": "NO_DATA", "message": "Periode data tidak tersedia."}

    periods = ds.available_periods()
    previous = ds.prev_period(period)
    year_ago = f"{int(period[:4]) - 1:04d}-{period[5:]}"
    if year_ago not in periods:
        year_ago = None

    current = _row(period)
    previous_row = _row(previous) if previous else {}
    year_ago_row = _row(year_ago) if year_ago else {}

    targets = {}
    target_rows = ds.TARGETS[ds.TARGETS.period.eq(period)]
    for _, row in target_rows.iterrows():
        metric = str(row.metric)
        targets[metric] = float(row.target)

    return {
        "status": "OK",
        "period": period,
        "period_label": ds.period_label(period),
        "unit": ds.UNIT,
        "current_kpi": current,
        "previous_month": {
            "period": previous,
            "kpi": previous_row,
            "changes": _changes(current, previous_row),
        },
        "same_month_last_year": {
            "period": year_ago,
            "kpi": year_ago_row,
            "changes": _changes(current, year_ago_row) if year_ago else {},
        },
        "targets": targets,
        "p_and_l_movements_vs_previous_month": _line_item_changes(period, previous) if previous else [],
        "product_movements": {
            "credit": _product_changes(ds.LOANS, period, previous, "product_type", "outstanding", "total_revenue") if previous else [],
            "investment": _product_changes(ds.INVESTMENTS, period, previous, "investment_type", "investment_amount", "total_revenue") if previous else [],
            "dpk": _product_changes(ds.DPK, period, previous, "product_type", "balance", "total_cost_bagi_hasil") if previous else [],
            "other_funding": _product_changes(ds.OTHER, period, previous, "product_type", "balance", "total_cost_bagi_hasil") if previous else [],
        },
        "balance_sheet_lines": ds.BS[ds.BS.period.eq(period)].to_dict("records"),
        "income_statement_lines": ds.IS[ds.IS.period.eq(period)].to_dict("records"),
    }
