from __future__ import annotations

from typing import Any
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

    # Rich deterministic base analysis is always available to the analyst.
    # This prevents the semantic director from becoming a single point of failure.
    evidence["analysis_tools"] = {
        "income_drivers": _tool_income_drivers(primary),
        "balance_drivers": _tool_balance_drivers(primary),
        "funding_analysis": _tool_funding_analysis(primary),
        "trend": _tool_trend(primary, 18),
        "target": _tool_target(primary),
    }

    evidence["product_data"] = _product_aggregation(primary)

    if plan and plan.get("correlation_analysis"):
        evidence["correlation_analysis"] = _correlations(primary, 18)

    # Add focused line-item change analysis for the concepts likely relevant to the question.
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

# ---------------------------------------------------------------------------
# Dynamic analytical tools
# ---------------------------------------------------------------------------



def _pnl_monthly_flow(period):
    """Convert cumulative P&L balances into the amount generated in the month.

    monthly_summary/income_statement P&L values are cumulative through the
    selected month. Therefore a raw Aug->Sep delta is September's monthly
    amount, not a MoM growth rate. This helper makes that distinction explicit.
    """
    periods = ds.available_periods()
    if period not in periods:
        return {}
    idx = periods.index(period)
    if idx == 0:
        return {}
    previous = periods[idx - 1]
    previous_previous = periods[idx - 2] if idx >= 2 else None
    cur = _summary_snapshot(period)
    prev = _summary_snapshot(previous)
    prevprev = _summary_snapshot(previous_previous) if previous_previous else {}
    out = {}
    for key in ["net_profit", "revenue", "operating_expense", "ckpn"]:
        if key not in cur or key not in prev:
            continue
        current_flow = cur[key]["value"] - prev[key]["value"]
        previous_flow = None
        change = None
        if previous_previous and key in prevprev:
            previous_flow = prev[key]["value"] - prevprev[key]["value"]
            change = _change(current_flow, previous_flow)
        out[key] = {
            "label": cur[key]["label"],
            "period": period,
            "previous_period": previous,
            "current_flow": current_flow,
            "previous_flow": previous_flow,
            "change": change,
            "unit": cur[key]["unit"],
        }
    return out


def _pnl_monthly_line_drivers(period):
    periods = ds.available_periods()
    if period not in periods:
        return []
    idx = periods.index(period)
    if idx == 0:
        return []
    prev = periods[idx - 1]
    prevprev = periods[idx - 2] if idx >= 2 else None
    cur_rows = _group_statement(period, "income_statement")
    prev_rows = _group_statement(prev, "income_statement")
    prevprev_rows = _group_statement(prevprev, "income_statement") if prevprev else []
    cur_map = {r["line_item"]: r.get("amount") for r in cur_rows}
    prev_map = {r["line_item"]: r.get("amount") for r in prev_rows}
    prevprev_map = {r["line_item"]: r.get("amount") for r in prevprev_rows}
    out = []
    for item, cumulative in cur_map.items():
        if cumulative is None or item not in prev_map or prev_map[item] is None:
            continue
        current_flow = cumulative - prev_map[item]
        previous_flow = None
        if prevprev and item in prevprev_map and prevprev_map[item] is not None:
            previous_flow = prev_map[item] - prevprev_map[item]
        is_expense = item.startswith("Beban")
        out.append({
            "line_item": item,
            "current_flow": current_flow,
            "previous_flow": previous_flow,
            "change": _change(current_flow, previous_flow) if previous_flow is not None else None,
            "profit_direction": "pressure" if is_expense and current_flow >= 0 else ("support" if not is_expense and current_flow >= 0 else "mixed"),
        })
    # Exclude the total profit line from the driver list.
    out = [x for x in out if x["line_item"] != "Laba Bersih"]
    return sorted(out, key=lambda x: abs(x.get("current_flow") or 0), reverse=True)

def _tool_income_drivers(period):
    periods = ds.available_periods()
    if period not in periods:
        return {"available": False, "reason": "periode tidak tersedia"}
    idx = periods.index(period)
    previous = periods[idx - 1] if idx > 0 else None
    yoy = f"{int(period[:4])-1:04d}-{period[5:7]}"
    if yoy not in periods:
        yoy = None
    monthly_flow = _pnl_monthly_flow(period)
    out = {
        "period": period,
        "basis_note": "P&L pada data sumber bersifat kumulatif (YTD). Monthly flow dihitung sebagai selisih kumulatif bulan berjalan dengan bulan sebelumnya.",
        "monthly_flow": monthly_flow,
        "monthly_flow_drivers": _pnl_monthly_line_drivers(period)[:20],
        "mom_cumulative": _top_contributors(period, previous) if previous else [],
        "yoy_cumulative": _group_changes(_group_statement(period, "income_statement"), _group_statement(yoy, "income_statement"))[:15] if yoy else [],
        "interpretation_rule": "Beban pada monthly flow memberi tekanan laba; pendapatan pada monthly flow memberi dukungan. Ini adalah kontribusi perubahan, bukan bukti kausalitas tunggal.",
    }
    return out


def _tool_balance_drivers(period):
    periods = ds.available_periods()
    idx = periods.index(period) if period in periods else -1
    previous = periods[idx - 1] if idx > 0 else None
    cur = _group_statement(period, "balance_sheet")
    prev = _group_statement(previous, "balance_sheet") if previous else []
    changes = _group_changes(cur, prev) if previous else []
    by_statement = {}
    for statement in ["Asset", "Kewajiban", "Ekuitas"]:
        items = [x for x in changes if next((r["statement"] for r in cur if r["line_item"] == x["line_item"]), "") == statement]
        by_statement[statement.lower()] = items[:15]
    return {
        "period": period,
        "previous_period": previous,
        "drivers": by_statement,
    }


def _tool_funding_analysis(period):
    snap = _summary_snapshot(period)
    values = {k: x["value"] for k, x in snap.items()}
    total_assets = values.get("total_assets")
    credit = values.get("total_credit")
    dpk = values.get("total_dpk")
    other = values.get("total_other_funding")
    return {
        "period": period,
        "values": {
            "total_assets": total_assets,
            "total_credit": credit,
            "total_dpk": dpk,
            "total_other_funding": other,
        },
        "ratios": {
            "credit_to_asset_percent": (credit / total_assets * 100) if total_assets else None,
            "dpk_to_asset_percent": (dpk / total_assets * 100) if total_assets else None,
            "credit_to_dpk_percent": (credit / dpk * 100) if dpk else None,
            "credit_minus_dpk": (credit - dpk) if credit is not None and dpk is not None else None,
            "credit_minus_customer_and_other_funding": (credit - dpk - (other or 0)) if credit is not None and dpk is not None else None,
        },
        "note": "Rasio/selisih menggambarkan struktur pendanaan pada periode tersebut; bukan bukti kecukupan likuiditas secara menyeluruh.",
    }


def _tool_trend(period, months=18):
    return {
        "periods": _trend(period, months),
        "months_used": months,
    }


def _tool_target(period):
    return {
        "period": period,
        "targets": _target_analysis(period),
    }


def _tool_product(period, kind):
    data = _product_aggregation(period)
    key = {
        "loan_products": "loan_products",
        "dpk_products": "dpk_products",
        "investment_products": "investment_products",
    }[kind]
    rows = data.get(key, [])
    enriched = []
    for row in rows:
        item = dict(row)
        if kind == "loan_products":
            outstanding = item.get("outstanding")
            revenue = item.get("total_revenue")
            item["revenue_to_outstanding_percent"] = (revenue / outstanding * 100) if outstanding else None
            item["interpretation"] = "yield pendapatan indikatif, bukan laba produk"
        elif kind == "dpk_products":
            balance = item.get("balance")
            cost = item.get("total_cost_bagi_hasil")
            item["cost_to_balance_percent"] = (cost / balance * 100) if balance else None
            item["interpretation"] = "cost rate indikatif, bukan total cost of funding yang disetahunkan"
        elif kind == "investment_products":
            amount = item.get("investment_amount")
            revenue = item.get("total_revenue")
            item["revenue_to_amount_percent"] = (revenue / amount * 100) if amount else None
            item["interpretation"] = "yield pendapatan indikatif, bukan laba investasi"
        enriched.append(item)
    return {"period": period, "products": enriched}


def _tool_correlation(period, months=18):
    periods = ds.available_periods()
    usable = [p for p in periods if p <= period][-months:] if period in periods else []
    if len(usable) < 6:
        return {"available": False, "reason": "Observasi time-series kurang dari 6 periode."}
    result = _correlations(period, months)
    result["available"] = True
    return result


def expand_evidence(evidence, request, period=None):
    """Execute a bounded, auditable analytical tool requested by the AI.

    The AI chooses *which* analysis is relevant; Python performs the actual
    calculation. Unknown requests are ignored rather than interpreted loosely.
    """
    primary = ds.resolve_period(period or evidence.get("selected_period"))
    if not primary:
        return None
    tools = {
        "income_drivers": lambda: _tool_income_drivers(primary),
        "balance_drivers": lambda: _tool_balance_drivers(primary),
        "funding_analysis": lambda: _tool_funding_analysis(primary),
        "trend": lambda: _tool_trend(primary, 18),
        "target": lambda: _tool_target(primary),
        "loan_products": lambda: _tool_product(primary, "loan_products"),
        "dpk_products": lambda: _tool_product(primary, "dpk_products"),
        "investment_products": lambda: _tool_product(primary, "investment_products"),
        "correlation": lambda: _tool_correlation(primary, 18),
    }
    fn = tools.get(str(request))
    if not fn:
        return None
    try:
        return fn()
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def prepare_model_evidence(evidence):
    """Create a compact, decision-oriented evidence view for the LLM.

    The full evidence remains in memory for audit/verification. The model sees
    only the most decision-relevant fields first; focused tools add detail when
    the analyst requests it.
    """
    if not isinstance(evidence, dict):
        return evidence

    def compact_comparisons(raw):
        out = {}
        preferred = {"net_profit", "revenue", "operating_expense", "total_assets", "total_credit", "total_dpk", "npl_ratio", "ckpn_coverage"}
        for relation, item in (raw or {}).items():
            metrics = item.get("metrics", {}) if isinstance(item, dict) else {}
            selected = {}
            for key, value in metrics.items():
                if key in preferred:
                    selected[key] = value
            if selected:
                out[relation] = {"period": item.get("period"), "relation": item.get("relation"), "metrics": selected}
        return out

    trend = evidence.get("trend_12m") or []
    trend_keys = {"net_profit", "revenue", "operating_expense", "total_assets", "total_credit", "total_dpk", "npl_ratio"}
    compact_trend = [
        {"period": row.get("period"), "metrics": {k: v for k, v in (row.get("metrics") or {}).items() if k in trend_keys}}
        for row in trend
    ]

    products = {}
    for key, rows in (evidence.get("product_data") or {}).items():
        products[key] = rows[:3] if isinstance(rows, list) else rows

    tools = evidence.get("analysis_tools", {}) or {}
    income_tool = tools.get("income_drivers", {}) or {}
    balance_tool = tools.get("balance_drivers", {}) or {}
    compact_tools = {
        "income_drivers": {
            "basis_note": income_tool.get("basis_note"),
            "monthly_flow": income_tool.get("monthly_flow", {}),
            "monthly_flow_drivers": (income_tool.get("monthly_flow_drivers") or [])[:5],
            "yoy_cumulative": (income_tool.get("yoy_cumulative") or [])[:5],
            "interpretation_rule": income_tool.get("interpretation_rule"),
        },
        "balance_drivers": {
            "period": balance_tool.get("period"),
            "previous_period": balance_tool.get("previous_period"),
            "drivers": {k: (v or [])[:4] for k, v in (balance_tool.get("drivers") or {}).items()},
        },
        "funding_analysis": tools.get("funding_analysis", {}),
        "trend": {"periods": (tools.get("trend", {}).get("periods") or [])[-9:]},
        "target": tools.get("target", {}),
    }

    return {
        "status": evidence.get("status"),
        "question": evidence.get("question"),
        "selected_period": evidence.get("selected_period"),
        "unit": evidence.get("unit"),
        "periods": evidence.get("periods"),
        "current": evidence.get("current"),
        "comparisons": compact_comparisons(evidence.get("comparisons")),
        "target_analysis": evidence.get("target_analysis"),
        "financial_relationships": evidence.get("financial_relationships"),
        "trend_12m": compact_trend[-9:],
        "product_data": products,
        "data_capabilities": evidence.get("data_capabilities"),
        "analysis_tools": compact_tools,
    }
