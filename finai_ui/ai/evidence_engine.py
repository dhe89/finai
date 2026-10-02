"""Selective evidence engine for the FinAI planner -> Python -> analyst loop.

Python owns retrieval and deterministic calculations. The engine also enforces
range semantics so an LLM cannot accidentally answer a Jan-Sep question using
only January and September.
"""
from __future__ import annotations
from typing import Any
import pandas as pd

from finai_ui import data_service as ds
from .evidence_catalog import EVIDENCE_CATALOG, COMPARISONS, catalog_for_llm
from .intelligence_layer import normalize_scope, periods_between, attach_scope_to_requests, evidence_coverage


def _period_from_request(request: dict[str, Any], fallback: str | None) -> str:
    requested = str(request.get("period") or request.get("end_period") or fallback or "")
    return ds.resolve_period(requested)


def _comparison_periods(period: str, comparisons: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    if "mom" in comparisons:
        p = ds.prev_period(period)
        out["previous_month"] = None if p == period else p
    if "yoy" in comparisons:
        periods = ds.available_periods()
        y = f"{int(period[:4]) - 1:04d}-{period[5:]}"
        out["same_month_last_year"] = y if y in periods else None
    return out


def _clean_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    result = df.copy().where(pd.notna(df.copy()), None)
    return result.to_dict("records")


def _range_rows(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if df is None or df.empty or "period" not in df.columns:
        return pd.DataFrame()
    x = df.copy()
    x["period"] = x["period"].astype(str)
    return x[x.period.between(start, end)].sort_values("period")


def _summary_block(period: str, comparisons: list[str], fields: list[str] | None = None,
                   start_period: str | None = None, end_period: str | None = None,
                   include_all_periods: bool = False) -> dict[str, Any]:
    fields = fields or EVIDENCE_CATALOG["summary_kpi"]["fields"]
    end_period = ds.resolve_period(end_period or period)
    start_period = ds.resolve_period(start_period or end_period)
    result: dict[str, Any] = {}

    cur = ds.srow(end_period)
    result["current"] = {k: float(cur[k]) for k in fields if k in cur.index}
    result["period"] = end_period

    if include_all_periods or start_period != end_period or "trend" in comparisons:
        x = _range_rows(ds.SUMMARY, start_period, end_period)
        cols = ["period"] + [f for f in fields if f in x.columns]
        rows = _clean_records(x[cols]) if not x.empty else []
        result["periods"] = [str(r["period"]) for r in rows]
        result["range"] = rows
        result["period_count"] = len(rows)
        # Deterministic month-to-month movements for each requested KPI.
        trend = []
        for i in range(1, len(rows)):
            prev, now = rows[i - 1], rows[i]
            item = {"period": now["period"], "previous_period": prev["period"]}
            for f in fields:
                a, b = now.get(f), prev.get(f)
                if a is None or b is None:
                    continue
                item[f] = {"current": float(a), "previous": float(b),
                           "change_absolute": float(a) - float(b),
                           "change_percent": ((float(a)-float(b))/abs(float(b))*100) if float(b) != 0 else None}
            trend.append(item)
        result["mom_series"] = trend
        if rows:
            first = rows[0]
            result["change_from_start"] = {}
            for f in fields:
                a, b = first.get(f), rows[-1].get(f)
                if a is not None and b is not None:
                    result["change_from_start"][f] = {
                        "start": float(a), "end": float(b),
                        "change_absolute": float(b)-float(a),
                        "change_percent": ((float(b)-float(a))/abs(float(a))*100) if float(a) != 0 else None,
                    }
    cmp_periods = _comparison_periods(end_period, comparisons)
    for label, p in cmp_periods.items():
        if p:
            row = ds.srow(p)
            result[label] = {k: float(row[k]) for k in fields if k in row.index}
    if "target" in comparisons:
        t = ds.TARGETS[ds.TARGETS.period.astype(str).eq(end_period)]
        result["target"] = {str(r.metric): float(r.target) for _, r in t.iterrows()}
        result["target_gap"] = {
            str(r.metric): {
                "actual": float(cur.get(str(r.metric))) if str(r.metric) in cur.index else None,
                "target": float(r.target),
                "gap": float(cur.get(str(r.metric))) - float(r.target) if str(r.metric) in cur.index else None,
                "achievement_percent": (float(cur.get(str(r.metric))) / float(r.target) * 100) if str(r.metric) in cur.index and float(r.target) != 0 else None,
            } for _, r in t.iterrows()
        }
    return result


def _statement_block(df: pd.DataFrame, period: str, comparisons: list[str], requested_lines: list[str] | None = None,
                     start_period: str | None = None, end_period: str | None = None,
                     include_all_periods: bool = False) -> dict[str, Any]:
    end_period = ds.resolve_period(end_period or period)
    start_period = ds.resolve_period(start_period or end_period)
    line_filter = set(str(x) for x in (requested_lines or []))

    def rows(p: str) -> list[dict[str, Any]]:
        x = df[df.period.astype(str).eq(p)].copy()
        if line_filter:
            x = x[x.line_item.astype(str).isin(line_filter)]
        return _clean_records(x)

    current_rows = rows(end_period)
    result: dict[str, Any] = {"period": end_period, "current": current_rows}
    for label, p in _comparison_periods(end_period, comparisons).items():
        if not p:
            continue
        comparison_rows = rows(p)
        result[label] = comparison_rows
        old_map = {str(r.get("line_item")): float(r.get("amount")) for r in comparison_rows if r.get("amount") is not None}
        derived = []
        for r in current_rows:
            name, now = str(r.get("line_item")), r.get("amount")
            old = old_map.get(name)
            if now is None or old is None:
                continue
            derived.append({"line_item": name, "current": float(now), "comparison": float(old),
                            "change_absolute": float(now)-float(old),
                            "change_percent": ((float(now)-float(old))/abs(float(old))*100) if old != 0 else None})
        result[label + "_changes"] = derived

    if "ytd" in comparisons:
        year = end_period[:4]
        x = df[df.period.astype(str).str.startswith(year)].copy()
        if line_filter:
            x = x[x.line_item.astype(str).isin(line_filter)]
        result["ytd"] = _clean_records(x.groupby("line_item", as_index=False).amount.sum())

    if include_all_periods or start_period != end_period or "trend" in comparisons:
        x = _range_rows(df, start_period, end_period)
        if line_filter:
            x = x[x.line_item.astype(str).isin(line_filter)]
        result["periods"] = sorted(x.period.astype(str).unique().tolist()) if not x.empty else []
        result["range"] = _clean_records(x.sort_values(["period", "line_item"]))
        result["period_count"] = len(result["periods"])
        # Per-line month-over-month changes.
        changes = []
        if not x.empty:
            for line, g in x.groupby("line_item"):
                g = g.sort_values("period")
                vals = g[["period", "amount"]].to_dict("records")
                for i in range(1, len(vals)):
                    a, b = float(vals[i-1]["amount"]), float(vals[i]["amount"])
                    changes.append({"line_item": str(line), "period": str(vals[i]["period"]),
                                    "previous_period": str(vals[i-1]["period"]), "change_absolute": b-a,
                                    "change_percent": ((b-a)/abs(a)*100) if a != 0 else None})
        result["mom_series"] = changes
    return result


def _product_block(kind: str, period: str, comparisons: list[str], products: list[str] | None = None,
                   start_period: str | None = None, end_period: str | None = None,
                   include_all_periods: bool = False) -> dict[str, Any]:
    config = {
        "loan_products": (ds.LOANS, "product_type", "outstanding", ["total_revenue", "facility_amount", "collectibility", "rate_pa"]),
        "investment_products": (ds.INVESTMENTS, "investment_type", "investment_amount", ["total_revenue", "collectibility", "rate_pa"]),
        "dpk_products": (ds.DPK, "product_type", "balance", ["total_cost_bagi_hasil", "rate_pa"]),
        "other_funding": (ds.OTHER, "product_type", "balance", ["total_cost_bagi_hasil", "rate_pa"]),
    }[kind]
    df, key, value, extras = config
    wanted = set(str(x) for x in (products or []))
    end_period = ds.resolve_period(end_period or period)
    start_period = ds.resolve_period(start_period or end_period)

    def aggregate(p: str) -> list[dict[str, Any]]:
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

    result: dict[str, Any] = {"period": end_period, "current": aggregate(end_period)}
    for label, p in _comparison_periods(end_period, comparisons).items():
        if p: result[label] = aggregate(p)

    if include_all_periods or start_period != end_period or "trend" in comparisons:
        periods = periods_between(start_period, end_period)
        result["periods"] = periods
        result["range"] = [{"period": p, "rows": aggregate(p)} for p in periods]
        result["period_count"] = len(periods)
    return result


def _targets_block(period: str, comparisons: list[str], start_period: str | None = None,
                   end_period: str | None = None, include_all_periods: bool = False) -> dict[str, Any]:
    end_period = ds.resolve_period(end_period or period)
    start_period = ds.resolve_period(start_period or end_period)
    x = ds.TARGETS[ds.TARGETS.period.astype(str).eq(end_period)].copy()
    result: dict[str, Any] = {"period": end_period, "current": _clean_records(x)}
    if include_all_periods or start_period != end_period or "trend" in comparisons:
        y = _range_rows(ds.TARGETS, start_period, end_period)
        result["periods"] = sorted(y.period.astype(str).unique().tolist()) if not y.empty else []
        result["range"] = _clean_records(y)
        result["period_count"] = len(result["periods"])
    return result


def _audit_block(period: str) -> dict[str, Any]:
    return {"current": _clean_records(ds.AUDIT[ds.AUDIT.period.astype(str).eq(period)].copy())}


def execute_evidence_plan(plan: dict[str, Any], selected_period: str | None) -> dict[str, Any]:
    """Validate and execute evidence requests, enforcing normalized range scope."""
    ds.ensure_data_fresh()
    plan = normalize_scope(plan or {}, selected_period)
    plan = attach_scope_to_requests(plan)
    period = ds.resolve_period(selected_period)
    requests = plan.get("requests") if isinstance(plan, dict) else None
    if not isinstance(requests, list): requests = []
    scope = plan.get("scope") or {}
    evidence: dict[str, Any] = {
        "status": "OK", "period": period, "unit": ds.UNIT,
        "scope": scope, "requested": [], "blocks": {},
    }

    for raw in requests[:10]:
        if not isinstance(raw, dict): continue
        evidence_id = str(raw.get("id", "")).strip()
        if evidence_id not in EVIDENCE_CATALOG: continue
        item_period = _period_from_request(raw, period)
        comparisons = [c for c in raw.get("comparisons", []) if c in COMPARISONS]
        if not comparisons:
            comparisons = ["mom"] if evidence_id not in {"targets", "audit_checks"} else ["target"]
        products = raw.get("products") if isinstance(raw.get("products"), list) else None
        lines = raw.get("lines") if isinstance(raw.get("lines"), list) else None
        start = raw.get("start_period") or scope.get("start_period") or item_period
        end = raw.get("end_period") or scope.get("end_period") or item_period
        include_all = bool(raw.get("include_all_periods", scope.get("include_all_periods", False)))
        if start not in ds.available_periods(): start = item_period
        if end not in ds.available_periods(): end = item_period
        if start > end: start, end = end, start

        kwargs = dict(start_period=start, end_period=end, include_all_periods=include_all)
        if evidence_id == "summary_kpi":
            block = _summary_block(item_period, comparisons, raw.get("fields"), **kwargs)
        elif evidence_id == "balance_sheet":
            block = _statement_block(ds.BS, item_period, comparisons, lines, **kwargs)
        elif evidence_id == "income_statement":
            block = _statement_block(ds.IS, item_period, comparisons, lines, **kwargs)
        elif evidence_id in {"loan_products", "investment_products", "dpk_products", "other_funding"}:
            block = _product_block(evidence_id, item_period, comparisons, products, **kwargs)
        elif evidence_id == "targets":
            block = _targets_block(item_period, comparisons, **kwargs)
        elif evidence_id == "audit_checks":
            block = _audit_block(item_period)
        elif evidence_id == "account_lifecycle":
            block = {"rows": _clean_records(getattr(ds, "LIFECYCLE", pd.DataFrame()).copy())}
        elif evidence_id == "account_status":
            x = getattr(ds, "STATUS_MONTHLY", pd.DataFrame())
            x = x[x.period.astype(str).eq(item_period)].copy() if not x.empty else x
            block = {"current": _clean_records(x)}
        else:
            continue
        evidence["requested"].append({"id": evidence_id, "period": item_period, "start_period": start,
                                      "end_period": end, "include_all_periods": include_all, "comparisons": comparisons})
        evidence["blocks"][evidence_id] = block

    if not evidence["blocks"]:
        evidence["status"] = "NO_EVIDENCE_REQUESTED"
    if scope.get("include_all_periods"):
        evidence["coverage"] = evidence_coverage(evidence, scope.get("start_period"), scope.get("end_period"))
    return evidence


def build_catalog_context() -> dict[str, Any]:
    ds.ensure_data_fresh()
    return catalog_for_llm(ds.available_periods(), ds.get_latest_period())
