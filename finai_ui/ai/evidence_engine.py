"""Selective evidence engine for the FinAI planner -> Python -> analyst loop."""
from __future__ import annotations

from typing import Any
import pandas as pd

from finai_ui import data_service as ds
from .evidence_catalog import EVIDENCE_CATALOG, COMPARISONS, catalog_for_llm


def _period_from_request(request: dict[str, Any], fallback: str | None) -> str:
    requested = str(request.get("period") or fallback or "")
    return ds.resolve_period(requested)


def _comparison_periods(period: str, comparisons: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    if "mom" in comparisons:
        out["previous_month"] = ds.prev_period(period)
    if "yoy" in comparisons:
        periods = ds.available_periods()
        y = f"{int(period[:4]) - 1:04d}-{period[5:]}"
        out["same_month_last_year"] = y if y in periods else None
    return out


def _clean_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    result = df.copy()
    result = result.where(pd.notna(result), None)
    return result.to_dict("records")


def _numeric_compare(cur: pd.DataFrame, old: pd.DataFrame, key: str, value: str) -> list[dict[str, Any]]:
    if cur.empty:
        return []
    c = cur.groupby(key, as_index=False)[value].sum()
    o = old.groupby(key, as_index=False)[value].sum() if not old.empty else pd.DataFrame(columns=[key, value])
    old_map = {str(r[key]): float(r[value]) for _, r in o.iterrows()}
    rows = []
    for _, r in c.iterrows():
        name = str(r[key]); now = float(r[value]); prev = old_map.get(name)
        rows.append({key: name, "current": now, "previous": prev,
                     "change_absolute": now - prev if prev is not None else None,
                     "change_percent": ((now - prev) / abs(prev) * 100) if prev not in (None, 0) else None})
    rows.sort(key=lambda x: abs(x.get("change_absolute") or 0), reverse=True)
    return rows


def _summary_block(period: str, comparisons: list[str], fields: list[str] | None = None) -> dict[str, Any]:
    fields = fields or EVIDENCE_CATALOG["summary_kpi"]["fields"]
    periods = ds.available_periods()
    cur = ds.srow(period)
    result = {k: float(cur[k]) for k in fields if k in cur.index}
    cmp_periods = _comparison_periods(period, comparisons)
    for label, p in cmp_periods.items():
        if p:
            row = ds.srow(p)
            result[label] = {k: float(row[k]) for k in fields if k in row.index}
    if "target" in comparisons:
        result["target"] = {str(r.metric): float(r.target) for _, r in ds.TARGETS[ds.TARGETS.period.eq(period)].iterrows()}
    if "trend" in comparisons:
        trend = ds.SUMMARY[ds.SUMMARY.period.astype(str).isin(periods)].copy()
        trend = trend[trend.period.astype(str) <= period].tail(12)
        result["trend_12m"] = _clean_records(trend[["period"] + [f for f in fields if f in trend.columns]])
    return result


def _statement_block(df: pd.DataFrame, period: str, comparisons: list[str], requested_lines: list[str] | None = None) -> dict[str, Any]:
    cmp_periods = _comparison_periods(period, comparisons)
    line_filter = set(str(x) for x in (requested_lines or []))
    def rows(p):
        x = df[df.period.astype(str).eq(p)].copy()
        if line_filter:
            x = x[x.line_item.astype(str).isin(line_filter)]
        return _clean_records(x)

    current_rows = rows(period)
    result = {"current": current_rows}
    for label, p in cmp_periods.items():
        if not p:
            continue
        comparison_rows = rows(p)
        result[label] = comparison_rows
        old_map = {str(r.get("line_item")): float(r.get("amount")) for r in comparison_rows if r.get("amount") is not None}
        derived = []
        for r in current_rows:
            name = str(r.get("line_item")); now = r.get("amount"); old = old_map.get(name)
            if now is None or old is None:
                continue
            derived.append({
                "line_item": name,
                "current": float(now),
                "comparison": float(old),
                "change_absolute": float(now) - float(old),
                "change_percent": ((float(now) - float(old)) / abs(float(old)) * 100) if float(old) != 0 else None,
            })
        result[label + "_changes"] = derived
    if "ytd" in comparisons:
        year = period[:4]
        x = df[df.period.astype(str).str.startswith(year)].copy()
        if line_filter:
            x = x[x.line_item.astype(str).isin(line_filter)]
        result["ytd"] = _clean_records(x.groupby("line_item", as_index=False).amount.sum())
    return result


def _product_block(kind: str, period: str, comparisons: list[str], products: list[str] | None = None) -> dict[str, Any]:
    config = {
        "loan_products": (ds.LOANS, "product_type", "outstanding", ["total_revenue", "facility_amount", "collectibility", "rate_pa"]),
        "investment_products": (ds.INVESTMENTS, "investment_type", "investment_amount", ["total_revenue", "collectibility", "rate_pa"]),
        "dpk_products": (ds.DPK, "product_type", "balance", ["total_cost_bagi_hasil", "rate_pa"]),
        "other_funding": (ds.OTHER, "product_type", "balance", ["total_cost_bagi_hasil", "rate_pa"]),
    }[kind]
    df, key, value, extras = config
    wanted = set(str(x) for x in (products or []))
    def aggregate(p):
        x = df[df.period.astype(str).eq(p)].copy()
        if wanted:
            x = x[x[key].astype(str).isin(wanted)]
        if x.empty:
            return []
        cols = [key, value] + extras
        cols = [c for c in cols if c in x.columns]
        agg_map = {c: "sum" for c in cols if c not in {key, "collectibility", "rate_pa", "status"}}
        for c in ["collectibility", "rate_pa"]:
            if c in cols: agg_map[c] = "mean"
        return _clean_records(x.groupby(key, as_index=False).agg(agg_map))
    result = {"current": aggregate(period)}
    for label, p in _comparison_periods(period, comparisons).items():
        if p: result[label] = aggregate(p)
    if "trend" in comparisons:
        result["periods"] = ds.available_periods()
    return result


def _targets_block(period: str, comparisons: list[str]) -> dict[str, Any]:
    x = ds.TARGETS[ds.TARGETS.period.astype(str).eq(period)].copy()
    result = {"current": _clean_records(x)}
    if "trend" in comparisons:
        result["trend"] = _clean_records(ds.TARGETS[ds.TARGETS.period.astype(str).str.startswith(period[:4])].copy())
    return result


def _audit_block(period: str) -> dict[str, Any]:
    return {"current": _clean_records(ds.AUDIT[ds.AUDIT.period.astype(str).eq(period)].copy())}


def execute_evidence_plan(plan: dict[str, Any], selected_period: str | None) -> dict[str, Any]:
    """Validate and execute only the evidence requests approved by the catalog."""
    ds.ensure_data_fresh()
    period = ds.resolve_period(selected_period)
    requests = plan.get("requests") if isinstance(plan, dict) else None
    if not isinstance(requests, list):
        requests = []
    evidence: dict[str, Any] = {
        "status": "OK",
        "period": period,
        "unit": ds.UNIT,
        "requested": [],
        "blocks": {},
    }
    for raw in requests[:8]:
        if not isinstance(raw, dict):
            continue
        evidence_id = str(raw.get("id", "")).strip()
        if evidence_id not in EVIDENCE_CATALOG:
            continue
        item_period = _period_from_request(raw, period)
        comparisons = [c for c in raw.get("comparisons", []) if c in COMPARISONS]
        if not comparisons:
            comparisons = ["mom"] if evidence_id not in {"targets", "audit_checks"} else ["target"]
        products = raw.get("products") if isinstance(raw.get("products"), list) else None
        lines = raw.get("lines") if isinstance(raw.get("lines"), list) else None
        if evidence_id == "summary_kpi":
            block = _summary_block(item_period, comparisons, raw.get("fields"))
        elif evidence_id == "balance_sheet":
            block = _statement_block(ds.BS, item_period, comparisons, lines)
        elif evidence_id == "income_statement":
            block = _statement_block(ds.IS, item_period, comparisons, lines)
        elif evidence_id in {"loan_products", "investment_products", "dpk_products", "other_funding"}:
            block = _product_block(evidence_id, item_period, comparisons, products)
        elif evidence_id == "targets":
            block = _targets_block(item_period, comparisons)
        elif evidence_id == "audit_checks":
            block = _audit_block(item_period)
        elif evidence_id == "account_lifecycle":
            block = {"rows": _clean_records(ds.LIFECYCLE.copy())}
        elif evidence_id == "account_status":
            x = ds.STATUS_MONTHLY[ds.STATUS_MONTHLY.period.astype(str).eq(item_period)].copy()
            block = {"current": _clean_records(x)}
        else:
            continue
        evidence["requested"].append({"id": evidence_id, "period": item_period, "comparisons": comparisons})
        evidence["blocks"][evidence_id] = block
    if not evidence["blocks"]:
        evidence["status"] = "NO_EVIDENCE_REQUESTED"
    return evidence


def build_catalog_context() -> dict[str, Any]:
    ds.ensure_data_fresh()
    return catalog_for_llm(ds.available_periods(), ds.get_latest_period())
