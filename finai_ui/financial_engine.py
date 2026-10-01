from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd

from finai_ui import data_service as ds


SUMMARY_LABELS = {
    "total_assets": "Total aset",
    "total_credit": "Total kredit",
    "total_investment": "Total investasi",
    "total_dpk": "Total DPK",
    "total_other_funding": "Dana lainnya",
    "net_profit": "Laba bersih",
    "revenue": "Pendapatan",
    "operating_expense": "Beban operasional",
    "ckpn": "CKPN",
    "npl_ratio": "NPL",
    "ckpn_coverage": "CKPN Coverage",
    "low_cost_funding": "Low Cost Funding",
}

PERCENT_METRICS = {"npl_ratio", "ckpn_coverage", "low_cost_funding"}

def _period_df(df, period):
    if df is None or df.empty or "period" not in df.columns:
        return df.iloc[0:0] if df is not None else pd.DataFrame()
    return df[df["period"].astype(str).eq(str(period))].copy()


def _safe_float(v):
    try:
        if pd.isna(v):
            return None
        return float(v)
    except Exception:
        return None


def _change(current, previous):
    if current is None or previous is None:
        return None
    delta = current - previous
    return {
        "absolute": delta,
        "percent": (delta / previous * 100) if previous != 0 else None,
    }


def _summary_snapshot(period):
    row = ds.srow(period)
    result = {}
    for key, label in SUMMARY_LABELS.items():
        value = _safe_float(row.get(key))
        if value is not None:
            result[key] = {"label": label, "value": value, "unit": "%" if key in PERCENT_METRICS else "Rp miliar"}
    return result


def _summary_comparison(current, other, relation):
    a = _summary_snapshot(current)
    b = _summary_snapshot(other)
    result = {"period": other, "relation": relation, "metrics": {}}
    for key in a:
        if key in b:
            result["metrics"][key] = {
                "label": a[key]["label"],
                "current": a[key]["value"],
                "comparison": b[key]["value"],
                "change": _change(a[key]["value"], b[key]["value"]),
                "unit": a[key]["unit"],
            }
    return result


def _target_snapshot(period):
    rows = _period_df(ds.TARGETS, period)
    out = []
    if rows.empty:
        return out
    for _, r in rows.iterrows():
        metric = str(r.get("metric", ""))
        target = _safe_float(r.get("target"))
        out.append({
            "metric": metric,
            "target_type": str(r.get("target_type", "")),
            "target": target,
        })
    return out


def _target_analysis(period):
    actual = _summary_snapshot(period)
    targets = _target_snapshot(period)
    actual_map = {v["label"]: v["value"] for v in actual.values()}
    aliases = {
        "Total Asset": "Total aset",
        "Total Credit": "Total kredit",
        "Total Investment": "Total investasi",
        "Total DPK": "Total DPK",
        "Total Other Funding": "Dana lainnya",
        "Total Revenue": "Pendapatan",
        "Net Profit": "Laba bersih",
        "Operating Expense": "Beban operasional",
        "NPL Ratio %": "NPL",
        "CKPN Coverage %": "CKPN Coverage",
        "Low Cost Funding %": "Low Cost Funding",
        "CKPN": "CKPN",
    }
    out = []
    for item in targets:
        target = item["target"]
        actual_value = actual_map.get(aliases.get(item["metric"], item["metric"]))
        if actual_value is None:
            continue
        gap = _change(actual_value, target)
        out.append({
            **item,
            "actual": actual_value,
            "gap": gap["absolute"] if gap else None,
            "achievement_percent": (actual_value / target * 100) if target not in (None, 0) else None,
            "status": "above" if actual_value >= target else "below",
        })
    return out


def _group_statement(period, kind):
    df = _period_df(ds.IS if kind == "income_statement" else ds.BS, period)
    if df.empty:
        return []
    if kind == "income_statement":
        # Generic grouping: preserve exact line items and add semantic buckets
        rows = []
        for _, r in df.iterrows():
            item = str(r.line_item)
            if item.startswith("Pendapatan Bunga"):
                bucket = "Pendapatan Bunga"
            elif item.startswith("Beban Bunga"):
                bucket = "Beban Bunga"
            elif item.startswith("Pendapatan Operasional Lainnya"):
                bucket = "Pendapatan Operasional Lainnya"
            elif item == "Pendapatan Investasi":
                bucket = "Pendapatan Investasi"
            elif item.startswith("Beban Operasional Lainnya"):
                bucket = "Beban Operasional Lainnya"
            elif item == "Laba Bersih":
                bucket = "Laba Bersih"
            else:
                bucket = "Lainnya"
            rows.append({"line_item": item, "bucket": bucket, "amount": _safe_float(r.amount)})
        return rows
    return [
        {
            "statement": str(r.statement),
            "line_item": str(r.line_item),
            "amount": _safe_float(r.amount),
        }
        for _, r in df.iterrows()
    ]


def _group_changes(current_rows, previous_rows):
    def by_item(rows):
        return {r["line_item"]: r.get("amount") for r in rows}
    cur = by_item(current_rows)
    prev = by_item(previous_rows)
    out = []
    for item, value in cur.items():
        if value is None or item not in prev or prev[item] is None:
            continue
        ch = _change(value, prev[item])
        if ch:
            out.append({
                "line_item": item,
                "current": value,
                "previous": prev[item],
                "change": ch,
            })
    return sorted(out, key=lambda x: abs(x["change"]["absolute"] or 0), reverse=True)


def _top_contributors(period, previous_period):
    cur = _group_statement(period, "income_statement")
    prev = _group_statement(previous_period, "income_statement")
    changes = _group_changes(cur, prev)
    # Classify directional effect on profit without claiming causality.
    for x in changes:
        item = x["line_item"].lower()
        delta = x["change"]["absolute"] or 0
        is_expense = item.startswith("beban ")
        x["profit_direction"] = "pressure" if is_expense and delta > 0 else (
            "support" if (not is_expense and delta > 0) else (
                "support" if is_expense and delta < 0 else "pressure"
            )
        )
    return changes[:15]


def _bs_relationships(period, previous_period):
    cur = _group_statement(period, "balance_sheet")
    prev = _group_statement(previous_period, "balance_sheet")
    changes = _group_changes(cur, prev)
    assets = [x for x in changes if next((r["statement"] for r in cur if r["line_item"] == x["line_item"]), "") == "Asset"]
    liabilities = [x for x in changes if next((r["statement"] for r in cur if r["line_item"] == x["line_item"]), "") == "Kewajiban"]
    equity = [x for x in changes if next((r["statement"] for r in cur if r["line_item"] == x["line_item"]), "") == "Ekuitas"]
    return {
        "asset_drivers": assets[:10],
        "liability_drivers": liabilities[:10],
        "equity_drivers": equity[:10],
    }



def _income_summary(period):
    rows = _group_statement(period, "income_statement")
    buckets = {}
    for r in rows:
        bucket = r["bucket"]
        buckets[bucket] = buckets.get(bucket, 0.0) + (r.get("amount") or 0.0)
    # The source data is cumulative for P&L through the selected month.
    derived_profit = (
        buckets.get("Pendapatan Bunga", 0)
        - buckets.get("Beban Bunga", 0)
        + buckets.get("Pendapatan Operasional Lainnya", 0)
        + buckets.get("Pendapatan Investasi", 0)
        - buckets.get("Beban Operasional Lainnya", 0)
    )
    return {
        "period": period,
        "basis": "cumulative through selected month",
        "buckets": buckets,
        "derived_profit": derived_profit,
    }


def _income_summary_change(current, previous):
    a = _income_summary(current)
    b = _income_summary(previous)
    changes = {}
    for key, value in a["buckets"].items():
        if key in b["buckets"]:
            changes[key] = _change(value, b["buckets"][key])
    changes["derived_profit"] = _change(a["derived_profit"], b["derived_profit"])
    return {
        "current": a,
        "previous": b,
        "changes": changes,
    }


def _financial_relationships(period):
    snap = _summary_snapshot(period)
    v = {k: x["value"] for k, x in snap.items()}
    return {
        "profitability": {
            "net_profit_margin_percent": (v["net_profit"] / v["revenue"] * 100) if v.get("revenue") else None,
            "operating_expense_to_revenue_percent": (v["operating_expense"] / v["revenue"] * 100) if v.get("revenue") else None,
        },
        "balance_structure": {
            "credit_to_asset_percent": (v["total_credit"] / v["total_assets"] * 100) if v.get("total_assets") else None,
            "investment_to_asset_percent": (v["total_investment"] / v["total_assets"] * 100) if v.get("total_assets") else None,
            "dpk_to_asset_percent": (v["total_dpk"] / v["total_assets"] * 100) if v.get("total_assets") else None,
            "credit_to_dpk_percent": (v["total_credit"] / v["total_dpk"] * 100) if v.get("total_dpk") else None,
        },
        "funding_gap": {
            "credit_minus_dpk": (v["total_credit"] - v["total_dpk"]) if v.get("total_credit") is not None and v.get("total_dpk") is not None else None,
            "credit_plus_investment_minus_dpk": (
                v["total_credit"] + v["total_investment"] - v["total_dpk"]
            ) if all(v.get(k) is not None for k in ["total_credit", "total_investment", "total_dpk"]) else None,
        },
        "asset_quality": {
            "npl_ratio_percent": v.get("npl_ratio"),
            "ckpn_coverage_percent": v.get("ckpn_coverage"),
        },
    }


def _relationship_change(current, previous):
    a = _financial_relationships(current)
    b = _financial_relationships(previous)
    def flatten(obj, prefix=""):
        out = {}
        for k, val in obj.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(val, dict):
                out.update(flatten(val, key))
            else:
                out[key] = val
        return out
    fa, fb = flatten(a), flatten(b)
    return {
        k: _change(fa[k], fb[k])
        for k in fa
        if k in fb and fa[k] is not None and fb[k] is not None
    }


def _product_aggregation(period):
    result = {}
    for name, df, key, value, extra in [
        ("loan_products", ds.LOANS, "product_type", "outstanding", "total_revenue"),
        ("investment_products", ds.INVESTMENTS, "investment_type", "investment_amount", "total_revenue"),
        ("dpk_products", ds.DPK, "product_type", "balance", "total_cost_bagi_hasil"),
        ("other_funding_products", ds.OTHER, "product_type", "balance", "total_cost_bagi_hasil"),
    ]:
        if df is None or df.empty:
            continue
        x = df[df.period.astype(str).eq(str(period))].groupby(key, as_index=False)[[value, extra]].sum()
        x = x.sort_values(value, ascending=False)
        result[name] = [
            {key: str(r[key]), value: _safe_float(r[value]), extra: _safe_float(r[extra])}
            for _, r in x.head(20).iterrows()
        ]
    return result


def _trend(period, months=12):
    periods = ds.available_periods()
    if period not in periods:
        return []
    idx = periods.index(period)
    selected = periods[max(0, idx - months + 1):idx + 1]
    rows = []
    for p in selected:
        snap = _summary_snapshot(p)
        rows.append({
            "period": p,
            "metrics": {k: v["value"] for k, v in snap.items()},
        })
    return rows


def _correlations(period, months=18):
    periods = ds.available_periods()
    if period not in periods:
        return {}
    idx = periods.index(period)
    selected = periods[max(0, idx - months + 1):idx + 1]
    keys = ["net_profit", "revenue", "operating_expense", "total_credit", "total_dpk", "total_assets", "ckpn"]
    frame = []
    for p in selected:
        row = ds.srow(p)
        frame.append({k: _safe_float(row.get(k)) for k in keys})
    df = pd.DataFrame(frame)
    corr = df.corr(numeric_only=True)
    out = {}
    for a in keys:
        out[a] = {}
        for b in keys:
            if a != b and a in corr.index and b in corr.columns:
                val = corr.loc[a, b]
                out[a][b] = None if pd.isna(val) else round(float(val), 4)
    return {
        "periods_used": selected,
        "pearson": out,
        "warning": "Korelasi menunjukkan hubungan linear pada periode yang diamati; bukan bukti hubungan sebab-akibat.",
    }


def build_evidence(question, period, plan):
    """Build a rich, deterministic evidence package for the analyst.

    The LLM decides what it needs semantically; this engine supplies a broad,
    auditable analytical context. No intent dictionary is required.
    """
    ds.refresh_csv_data()
    primary = ds.resolve_period(period)
    periods = ds.available_periods()
    if not primary:
        return {"status": "NO_DATA", "message": "Periode data tidak tersedia."}

    idx = periods.index(primary)
    previous = periods[idx - 1] if idx > 0 else None
    yoy = None
    y, m = primary.split("-")
    candidate = f"{int(y)-1:04d}-{m}"
    if candidate in periods:
        yoy = candidate

    evidence = {
        "status": "READY",
        "source": "CSV simulation data via Python Financial Intelligence Engine",
        "question": question,
        "selected_period": primary,
        "unit": ds.UNIT,
        "periods": {
            "current": primary,
            "previous_month": previous,
            "same_month_prior_year": yoy,
            "year_start": next((p for p in periods if p.startswith(f"{y}-")), None),
        },
        "current": _summary_snapshot(primary),
        "comparisons": {},
        "target_analysis": _target_analysis(primary),
        "income_statement": _group_statement(primary, "income_statement"),
        "income_summary": _income_summary(primary),
        "financial_relationships": _financial_relationships(primary),
        "balance_sheet": _group_statement(primary, "balance_sheet"),
        "trend_12m": _trend(primary, 12),
        "data_capabilities": {
            "product_profitability": False,
            "loan_revenue": True,
            "dpk_cost": True,
            "formal_causal_model": False,
        },
    }

    if previous:
        evidence["comparisons"]["mom"] = _summary_comparison(primary, previous, "previous_month")
        evidence["income_statement_changes_mom"] = _top_contributors(primary, previous)
        evidence["income_summary_changes_mom"] = _income_summary_change(primary, previous)
        evidence["financial_relationship_changes_mom"] = _relationship_change(primary, previous)
        evidence["balance_sheet_changes_mom"] = _bs_relationships(primary, previous)

    if yoy:
        evidence["comparisons"]["yoy"] = _summary_comparison(primary, yoy, "same_month_prior_year")
        evidence["income_summary_changes_yoy"] = _income_summary_change(primary, yoy)
        evidence["financial_relationship_changes_yoy"] = _relationship_change(primary, yoy)

    # YTD is represented by the cumulative monthly summary for P&L metrics.
    # For point-in-time balance sheet metrics, compare with year-start instead.
    year_start = evidence["periods"]["year_start"]
    if year_start and year_start != primary:
        evidence["comparisons"]["year_start"] = _summary_comparison(primary, year_start, "year_start")

    evidence["product_data"] = _product_aggregation(primary)

    if plan and plan.get("correlation_analysis"):
        evidence["correlation_analysis"] = _correlations(primary, 18)

    # Add focused line-item change analysis for the concepts the planner identified.
    focus_text = " ".join(str(x) for x in (plan or {}).get("focus", []))
    dimensions = set((plan or {}).get("dimensions", []) or [])
    if previous and (
        "laba" in focus_text.lower()
        or "profit" in focus_text.lower()
        or "pendapatan" in focus_text.lower()
        or "beban" in focus_text.lower()
        or "income" in focus_text.lower()
        or "diagn" in focus_text.lower()
        or "strategy" in focus_text.lower()
    ):
        evidence["profit_driver_analysis"] = {
            "period": primary,
            "comparison_period": previous,
            "largest_changes": evidence.get("income_statement_changes_mom", [])[:12],
        }

    # Keep the payload bounded while retaining analytical richness.
    evidence["income_statement"] = sorted(
        evidence["income_statement"],
        key=lambda x: abs(x.get("amount") or 0),
        reverse=True,
    )[:40]
    evidence["balance_sheet"] = sorted(
        evidence["balance_sheet"],
        key=lambda x: abs(x.get("amount") or 0),
        reverse=True,
    )[:40]

    return evidence
