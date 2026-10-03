"""Selective evidence engine for the FinAI planner -> Python -> analyst loop.

Python owns retrieval and deterministic calculations. The LLM owns intent,
meaning, evidence selection and interpretation. Income-statement values in
source files are cumulative/YTD, so monthly performance is derived from the
current cumulative value minus the real prior-month cumulative value.
"""
from __future__ import annotations
from typing import Any
import pandas as pd

from finai_ui import data_service as ds
from .evidence_catalog import EVIDENCE_CATALOG, COMPARISONS, catalog_for_llm
from .intelligence_layer import normalize_scope, periods_between, attach_scope_to_requests, evidence_coverage

PNL_SUMMARY_FIELDS = {"revenue", "operating_expense", "ckpn", "net_profit"}


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
    x = df.copy()
    x = x.where(pd.notna(x), None)
    return x.to_dict("records")


def _range_rows(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if df is None or df.empty or "period" not in df.columns:
        return pd.DataFrame()
    x = df.copy()
    x["period"] = x["period"].astype(str)
    return x[x.period.between(start, end)].sort_values("period")


def _prev_period(period: str) -> str | None:
    p = ds.prev_period(period)
    return None if p == period else p


def _statement_value(df: pd.DataFrame, period: str, line_item: str) -> float | None:
    if df is None or df.empty:
        return None
    x = df[(df.period.astype(str) == str(period)) & (df.line_item.astype(str) == str(line_item))]
    if x.empty or pd.isna(x.iloc[-1].amount):
        return None
    return float(x.iloc[-1].amount)


def _summary_value(period: str, field: str) -> float | None:
    try:
        row = ds.srow(period)
        if field not in row.index or pd.isna(row[field]):
            return None
        return float(row[field])
    except Exception:
        return None


def _pnl_monthly_flow(period: str, field: str) -> float | None:
    """Return one month's P&L flow from a cumulative/YTD summary field."""
    current = _summary_value(period, field)
    previous_period = _prev_period(period)
    previous = _summary_value(previous_period, field) if previous_period else None
    if current is None or previous is None:
        return None
    return current - previous


def _pnl_flow_comparison(period: str, field: str) -> dict[str, Any]:
    """Build one deterministic monthly-flow comparison for a P&L KPI."""
    previous_period = _prev_period(period)
    current_flow = _pnl_monthly_flow(period, field)
    previous_flow = _pnl_monthly_flow(previous_period, field) if previous_period else None
    return {
        "current_cumulative": _summary_value(period, field),
        "previous_cumulative": _summary_value(previous_period, field) if previous_period else None,
        "current_monthly_flow": current_flow,
        "previous_monthly_flow": previous_flow,
        "change_absolute": (current_flow - previous_flow) if current_flow is not None and previous_flow is not None else None,
        "change_percent": ((current_flow - previous_flow) / abs(previous_flow) * 100)
            if current_flow is not None and previous_flow not in (None, 0) else None,
    }


def _flow_from_cumulative(df: pd.DataFrame, value_col: str = "amount") -> pd.DataFrame:
    """Derive monthly flow for an income-statement dataframe.

    If the requested range starts in the middle of a year, the previous month
    outside the range is looked up so the first requested month still receives
    a valid flow. No business interpretation is performed here.
    """
    if df is None or df.empty or "period" not in df.columns or value_col not in df.columns:
        return pd.DataFrame()
    x = df.copy()
    x["period"] = x["period"].astype(str)
    x = x.sort_values("period")
    rows = []
    for line, g in x.groupby("line_item", dropna=False) if "line_item" in x.columns else [(None, x)]:
        g = g.sort_values("period").copy()
        for _, r in g.iterrows():
            p = str(r["period"])
            cur = r[value_col]
            if pd.isna(cur):
                flow = None
                prev_value = None
            else:
                pp = _prev_period(p)
                prev_value = None
                if pp:
                    prior = g[g["period"].eq(pp)]
                    if not prior.empty and not pd.isna(prior.iloc[-1][value_col]):
                        prev_value = float(prior.iloc[-1][value_col])
                    elif "line_item" in x.columns:
                        prev_value = _statement_value(ds.IS, pp, str(line))
                flow = float(cur) - prev_value if prev_value is not None else None
            item = {
                "period": p,
                "cumulative": float(cur) if not pd.isna(cur) else None,
                "previous_cumulative": prev_value,
                "monthly_flow": flow,
            }
            if line is not None:
                item["line_item"] = str(line)
            rows.append(item)
    return pd.DataFrame(rows)


def _statement_rows(df: pd.DataFrame, p: str, line_filter: set[str]) -> pd.DataFrame:
    x = df[df.period.astype(str).eq(p)].copy()
    if line_filter:
        x = x[x.line_item.astype(str).isin(line_filter)]
    return x


def _statement_block(df: pd.DataFrame, period: str, comparisons: list[str], requested_lines: list[str] | None = None,
                     start_period: str | None = None, end_period: str | None = None,
                     include_all_periods: bool = False) -> dict[str, Any]:
    end_period = ds.resolve_period(end_period or period)
    start_period = ds.resolve_period(start_period or end_period)
    line_filter = set(str(x) for x in (requested_lines or []))
    current_df = _statement_rows(df, end_period, line_filter)
    result: dict[str, Any] = {"period": end_period, "current": _clean_records(current_df)}

    is_pnl = df is ds.IS
    if is_pnl:
        prev = _prev_period(end_period)
        if prev:
            prev_df = _statement_rows(df, prev, line_filter)
            result["previous_month"] = _clean_records(prev_df)
            cur_map = {str(r.line_item): float(r.amount) for _, r in current_df.iterrows() if pd.notna(r.amount)}
            prev_map = {str(r.line_item): float(r.amount) for _, r in prev_df.iterrows() if pd.notna(r.amount)}
            changes = []
            for name, cumulative_now in cur_map.items():
                if name not in prev_map:
                    continue
                flow_now = cumulative_now - prev_map[name]
                pp = _prev_period(prev)
                flow_prev = None
                if pp:
                    prior = _statement_value(ds.IS, pp, name)
                    if prior is not None:
                        flow_prev = prev_map[name] - prior
                changes.append({
                    "line_item": name,
                    "current_cumulative": cumulative_now,
                    "previous_cumulative": prev_map[name],
                    "current_monthly_flow": flow_now,
                    "previous_monthly_flow": flow_prev,
                    "change_absolute": (flow_now - flow_prev) if flow_prev is not None else None,
                    "change_percent": ((flow_now-flow_prev)/abs(flow_prev)*100) if flow_prev not in (None, 0) else None,
                })
            result["mom_changes"] = changes
        if "ytd" in comparisons:
            result["ytd"] = _clean_records(current_df[[c for c in ["line_item", "amount"] if c in current_df.columns]])
    else:
        for label, p in _comparison_periods(end_period, comparisons).items():
            if not p:
                continue
            comparison_rows = _statement_rows(df, p, line_filter)
            result[label] = _clean_records(comparison_rows)
            old_map = {str(r.line_item): float(r.amount) for _, r in comparison_rows.iterrows() if pd.notna(r.amount)}
            derived = []
            for _, r in current_df.iterrows():
                name, now = str(r.line_item), r.amount
                old = old_map.get(name)
                if pd.isna(now) or old is None:
                    continue
                derived.append({"line_item": name, "current": float(now), "comparison": old,
                                "change_absolute": float(now)-old,
                                "change_percent": ((float(now)-old)/abs(old)*100) if old else None})
            result[label + "_changes"] = derived

    if is_pnl and "yoy" in comparisons:
        yoy_period = f"{int(end_period[:4])-1:04d}-{end_period[5:]}"
        if yoy_period in ds.available_periods():
            yoy_df = _statement_rows(df, yoy_period, line_filter)
            result["same_month_last_year"] = _clean_records(yoy_df)
            old_map = {str(r.line_item): float(r.amount) for _, r in yoy_df.iterrows() if pd.notna(r.amount)}
            result["yoy_changes"] = []
            for _, r in current_df.iterrows():
                name, now = str(r.line_item), r.amount
                old = old_map.get(name)
                if pd.isna(now) or old is None:
                    continue
                result["yoy_changes"].append({
                    "line_item": name,
                    "current_cumulative": float(now),
                    "comparison_cumulative": old,
                    "change_absolute": float(now)-old,
                    "change_percent": ((float(now)-old)/abs(old)*100) if old else None,
                })

            # Explicit monthly-flow YoY is available to the analyst if requested.
            if "monthly_yoy" in comparisons:
                result["monthly_yoy_changes"] = []
                for _, r in current_df.iterrows():
                    name = str(r.line_item)
                    current_flow = _statement_value(ds.IS, end_period, name)
                    current_prev = _statement_value(ds.IS, _prev_period(end_period), name) if _prev_period(end_period) else None
                    prior_flow = _statement_value(ds.IS, yoy_period, name)
                    prior_prev_period = _prev_period(yoy_period)
                    prior_prev = _statement_value(ds.IS, prior_prev_period, name) if prior_prev_period else None
                    if None in (current_flow, current_prev, prior_flow, prior_prev):
                        continue
                    cf, pf = current_flow-current_prev, prior_flow-prior_prev
                    result["monthly_yoy_changes"].append({
                        "line_item": name,
                        "current_monthly_flow": cf,
                        "prior_year_monthly_flow": pf,
                        "change_absolute": cf-pf,
                        "change_percent": ((cf-pf)/abs(pf)*100) if pf else None,
                    })

    if include_all_periods or start_period != end_period or "trend" in comparisons:
        x = _range_rows(df, start_period, end_period)
        if line_filter:
            x = x[x.line_item.astype(str).isin(line_filter)]
        result["periods"] = sorted(x.period.astype(str).unique().tolist()) if not x.empty else []
        result["range"] = _clean_records(x.sort_values(["period", "line_item"]))
        result["period_count"] = len(result["periods"])
        if is_pnl:
            flow_source = x.copy()
            if start_period:
                pp = _prev_period(start_period)
                if pp:
                    extra = _statement_rows(df, pp, line_filter)
                    flow_source = pd.concat([extra, flow_source], ignore_index=True).drop_duplicates(["period", "line_item"], keep="last")
            flow = _flow_from_cumulative(flow_source)
            flow = flow[flow.period.between(start_period, end_period)] if not flow.empty else flow
            result["monthly_flow_series"] = _clean_records(flow)
            if not flow.empty:
                result["highest_monthly_flow"] = _clean_records(flow.dropna(subset=["monthly_flow"]).sort_values("monthly_flow", ascending=False).head(20))
                result["lowest_monthly_flow"] = _clean_records(flow.dropna(subset=["monthly_flow"]).sort_values("monthly_flow", ascending=True).head(20))
        else:
            changes = []
            if not x.empty:
                for line, g in x.groupby("line_item"):
                    g = g.sort_values("period")
                    vals = g[["period", "amount"]].to_dict("records")
                    for i in range(1, len(vals)):
                        a, b = float(vals[i-1]["amount"]), float(vals[i]["amount"])
                        changes.append({"line_item": str(line), "period": str(vals[i]["period"]),
                                        "previous_period": str(vals[i-1]["period"]), "change_absolute": b-a,
                                        "change_percent": ((b-a)/abs(a)*100) if a else None})
            result["mom_series"] = changes
    return result


def _summary_block(period: str, comparisons: list[str], fields: list[str] | None = None,
                   start_period: str | None = None, end_period: str | None = None,
                   include_all_periods: bool = False) -> dict[str, Any]:
    fields = fields or EVIDENCE_CATALOG["summary_kpi"]["fields"]
    end_period = ds.resolve_period(end_period or period)
    start_period = ds.resolve_period(start_period or end_period)
    cur = ds.srow(end_period)
    result: dict[str, Any] = {"current": {k: float(cur[k]) for k in fields if k in cur.index}, "period": end_period}

    if include_all_periods or start_period != end_period or "trend" in comparisons:
        x = _range_rows(ds.SUMMARY, start_period, end_period)
        cols = ["period"] + [f for f in fields if f in x.columns]
        rows = _clean_records(x[cols]) if not x.empty else []
        result["periods"] = [str(r["period"]) for r in rows]
        result["range"] = rows
        result["period_count"] = len(rows)
        trend = []
        for i in range(len(rows)):
            if i == 0:
                continue
            prev_row, now_row = rows[i-1], rows[i]
            item = {"period": now_row["period"], "previous_period": prev_row["period"]}
            for f in fields:
                a, b = prev_row.get(f), now_row.get(f)
                if a is None or b is None:
                    continue
                if f in PNL_SUMMARY_FIELDS:
                    # IMPORTANT: for P&L, current/previous performance means
                    # monthly flows. This uses the actual previous cumulative
                    # observations and therefore also works across Jan/year-end.
                    current_flow = _pnl_monthly_flow(str(now_row["period"]), f)
                    previous_flow = _pnl_monthly_flow(str(prev_row["period"]), f)
                    item[f] = {
                        "current_cumulative": float(b),
                        "previous_cumulative": float(a),
                        "current_monthly_flow": current_flow,
                        "previous_monthly_flow": previous_flow,
                        "change_absolute": (current_flow-previous_flow) if current_flow is not None and previous_flow is not None else None,
                        "change_percent": ((current_flow-previous_flow)/abs(previous_flow)*100)
                            if current_flow is not None and previous_flow not in (None, 0) else None,
                    }
                else:
                    item[f] = {
                        "current": float(b),
                        "previous": float(a),
                        "change_absolute": float(b)-float(a),
                        "change_percent": ((float(b)-float(a))/abs(float(a))*100) if float(a) != 0 else None,
                    }
            trend.append(item)
        result["mom_series"] = trend

        # For P&L summary ranges, expose the same authoritative monthly-flow
        # representation used by income_statement evidence.
        flow_series = []
        for row in rows:
            p = str(row["period"])
            entry = {"period": p}
            for f in fields:
                if f in PNL_SUMMARY_FIELDS:
                    entry[f] = {
                        "cumulative": _summary_value(p, f),
                        "monthly_flow": _pnl_monthly_flow(p, f),
                    }
            flow_series.append(entry)
        result["monthly_flow_series"] = flow_series

        # These rankings are only calculated for P&L fields and remain evidence,
        # not an interpretation. The analyst still decides what "best" means.
        result["pnl_monthly_flow_extremes"] = {}
        for f in fields:
            if f not in PNL_SUMMARY_FIELDS:
                continue
            candidates = [(str(r["period"]), _pnl_monthly_flow(str(r["period"]), f)) for r in rows]
            candidates = [(p, v) for p, v in candidates if v is not None]
            if candidates:
                result["pnl_monthly_flow_extremes"][f] = {
                    "highest": {"period": max(candidates, key=lambda z: z[1])[0], "monthly_flow": max(candidates, key=lambda z: z[1])[1]},
                    "lowest": {"period": min(candidates, key=lambda z: z[1])[0], "monthly_flow": min(candidates, key=lambda z: z[1])[1]},
                }

    for label, p in _comparison_periods(end_period, comparisons).items():
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
                "achievement_percent": (float(cur.get(str(r.metric))) / float(r.target) * 100)
                    if str(r.metric) in cur.index and float(r.target) != 0 else None,
            }
            for _, r in t.iterrows()
        }
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
            if c in cols:
                agg_map[c] = "mean"
        return _clean_records(x.groupby(key, as_index=False).agg(agg_map))
    result: dict[str, Any] = {"period": end_period, "current": aggregate(end_period)}
    for label, p in _comparison_periods(end_period, comparisons).items():
        if p:
            result[label] = aggregate(p)
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
    """Validate and execute evidence requests; never infer user intent."""
    ds.ensure_data_fresh()
    plan = normalize_scope(plan or {}, selected_period)
    plan = attach_scope_to_requests(plan)
    period = ds.resolve_period(selected_period)
    requests = plan.get("requests") if isinstance(plan, dict) else None
    if not isinstance(requests, list):
        requests = []
    scope = plan.get("scope") or {}
    evidence: dict[str, Any] = {
        "status": "OK", "period": period, "unit": ds.UNIT,
        "scope": scope, "requested": [], "blocks": {},
    }
    for raw in requests[:10]:
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
        start = raw.get("start_period") or scope.get("start_period") or item_period
        end = raw.get("end_period") or scope.get("end_period") or item_period
        include_all = bool(raw.get("include_all_periods", scope.get("include_all_periods", False)))
        available = ds.available_periods()
        if start not in available:
            start = item_period
        if end not in available:
            end = item_period
        if start > end:
            start, end = end, start
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
        evidence["requested"].append({
            "id": evidence_id, "period": item_period, "start_period": start,
            "end_period": end, "include_all_periods": include_all,
            "comparisons": comparisons, "analysis": raw.get("analysis", scope.get("analysis", [])),
        })
        evidence["blocks"][evidence_id] = block
    if not evidence["blocks"]:
        evidence["status"] = "NO_EVIDENCE_REQUESTED"
    if scope.get("include_all_periods"):
        evidence["coverage"] = evidence_coverage(evidence, scope.get("start_period"), scope.get("end_period"))
    return evidence


def build_catalog_context() -> dict[str, Any]:
    ds.ensure_data_fresh()
    return catalog_for_llm(ds.available_periods(), ds.get_latest_period())
