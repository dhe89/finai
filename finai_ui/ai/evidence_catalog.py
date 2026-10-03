"""FinAI evidence dictionary.

This file contains metadata only: what financial data exists, how it is
related, and which deterministic transformations Python can perform.
The LLM remains responsible for user intent, evidence selection and analysis.
"""
from __future__ import annotations
from typing import Any
from .financial_knowledge import knowledge_for_llm

COMPARISONS = {
    "mom": "Month-over-month. For balance-sheet/stock metrics compare period-end values. For income-statement/P&L metrics compare monthly flows derived from cumulative/YTD values.",
    "yoy": "Year-over-year. Standard P&L YoY compares cumulative/YTD values for the same month. If the planner explicitly requests monthly-flow YoY, use monthly_yoy.",
    "monthly_yoy": "Monthly-flow YoY. For P&L compare the individual month's flow in the current year against the same month's flow in the prior year.",
    "ytd": "Year-to-date. P&L values are already cumulative/YTD, so use the ending cumulative value and never sum cumulative monthly observations.",
    "target": "Perbandingan aktual terhadap target periode aktif.",
    "trend": "Deret historis bulanan. For P&L performance/ranking, use monthly flows, not cumulative levels.",
}

EVIDENCE_CATALOG: dict[str, dict[str, Any]] = {
    "summary_kpi": {
        "description": "KPI bulanan tingkat bank: aset, kredit, investasi, funding, pendapatan, beban, CKPN, laba, NPL dan coverage.",
        "source": "monthly_summary.csv",
        "fields": ["total_assets", "total_credit", "total_investment", "total_dpk", "total_other_funding", "net_profit", "npl_ratio", "ckpn_coverage", "low_cost_funding", "revenue", "operating_expense", "ckpn"],
        "comparisons": ["mom", "yoy", "monthly_yoy", "ytd", "target", "trend"],
        "semantics": {
            "stock_metrics": ["total_assets", "total_credit", "total_investment", "total_dpk", "total_other_funding", "npl_ratio", "ckpn_coverage", "low_cost_funding"],
            "cumulative_pnl_metrics": ["revenue", "operating_expense", "ckpn", "net_profit"],
            "rule": "For cumulative_pnl_metrics, monthly_flow(period)=cumulative(period)-cumulative(previous_period). MoM/trend/month ranking use monthly_flow; YTD and standard YoY use cumulative values. Python only performs the requested deterministic transformation; the LLM decides why that evidence is relevant."
        },
    },
    "balance_sheet": {
        "description": "Neraca bulanan per line item. Values are period-end stock balances.",
        "source": "balance_sheet.csv", "fields": ["statement", "line_item", "amount"], "comparisons": ["mom", "yoy", "trend"],
        "semantics": {"value_type": "STOCK", "rule": "Compare period-end balances directly; do not convert to monthly flow."},
    },
    "income_statement": {
        "description": "Laba rugi bulanan per line item. Source amounts are cumulative/YTD amounts.",
        "source": "income_statement.csv", "fields": ["line_item", "amount"], "comparisons": ["mom", "yoy", "monthly_yoy", "ytd", "trend"],
        "semantics": {
            "value_type": "CUMULATIVE_YTD",
            "monthly_flow_formula": "monthly_flow(period)=cumulative(period)-cumulative(previous_period)",
            "mom_rule": "Compare current monthly_flow with previous monthly_flow, not current cumulative with previous cumulative.",
            "yoy_rule": "For normal YoY, compare cumulative value at the same month across years. If the user explicitly asks monthly YoY, derive monthly flow for both years.",
            "ytd_rule": "Use the ending cumulative observation. Never sum cumulative monthly observations.",
            "trend_rule": "For monthly trend, highest/lowest month, best/worst month and turning-point analysis, rank and interpret monthly_flow.",
            "scope_rule": "For any requested range, Python must return every requested period. Endpoints alone are insufficient.",
        },
    },
    "loan_products": {"description": "Rincian kredit per produk: outstanding, facility, kolektibilitas, rate, revenue dan status.", "source": "loan_detail.csv", "fields": ["product_type", "facility_amount", "outstanding", "collectibility", "rate_pa", "total_revenue", "status"], "comparisons": ["mom", "yoy", "trend"]},
    "investment_products": {"description": "Rincian investasi/penempatan per jenis: amount, kolektibilitas, rate, revenue dan status.", "source": "investment_detail.csv", "fields": ["investment_type", "investment_amount", "collectibility", "rate_pa", "total_revenue", "status"], "comparisons": ["mom", "yoy", "trend"]},
    "dpk_products": {"description": "Rincian DPK per produk: balance, rate, biaya bagi hasil dan status.", "source": "dpk_detail.csv", "fields": ["product_type", "balance", "rate_pa", "total_cost_bagi_hasil", "status"], "comparisons": ["mom", "yoy", "trend"]},
    "other_funding": {"description": "Rincian funding lain: balance, rate, biaya bagi hasil dan status.", "source": "other_funding_detail.csv", "fields": ["product_type", "balance", "rate_pa", "total_cost_bagi_hasil", "status"], "comparisons": ["mom", "yoy", "trend"]},
    "targets": {"description": "Target bulanan untuk asset, credit, investment, DPK, other funding, revenue, net profit, low-cost funding, operating expense, NPL dan coverage.", "source": "monthly_targets.csv", "fields": ["target_type", "metric", "target"], "comparisons": ["target", "trend"]},
    "audit_checks": {"description": "Hasil pemeriksaan konsistensi dataset, termasuk Assets = Liabilities + Equity.", "source": "audit_checks.csv", "fields": ["check", "difference", "status"], "comparisons": ["trend"]},
    "account_lifecycle": {"description": "Lifecycle account: record, product, start period dan close period.", "source": "account_lifecycle.csv", "fields": ["record_type", "record_no", "product_type", "start_period", "close_period"], "comparisons": []},
    "account_status": {"description": "Status bulanan account: NEW, ACTIVE, CLOSED, NOT_STARTED.", "source": "account_status_monthly.csv", "fields": ["record_type", "record_no", "product_type", "period", "status"], "comparisons": ["trend"]},
}

RELATIONSHIPS = [
    "loan_products.outstanding -> balance_sheet.Kredit",
    "investment_products.investment_amount -> balance_sheet.Penempatan",
    "dpk_products.balance -> balance_sheet.Giro/Tabungan/Deposito",
    "other_funding.balance -> balance_sheet.Pinjamanyangditerima/SuratBerhargaDiterbitkan",
    "loan_products.total_revenue -> income_statement pendapatan bunga kredit menurut produk",
    "investment_products.total_revenue -> income_statement pendapatan investasi/penempatan",
    "dpk_products.total_cost_bagi_hasil -> income_statement beban funding terkait",
    "other_funding.total_cost_bagi_hasil -> income_statement beban funding terkait",
    "income_statement line items -> revenue/operating expense/net profit KPI",
    "balance_sheet -> assets, liabilities and equity structure",
]

FORMULAS = {
    "mom_pct": "(current - previous_month) / abs(previous_month) * 100; for P&L monthly performance, current and previous_month mean monthly_flow, not cumulative values",
    "monthly_pnl_flow": "cumulative(period) - cumulative(previous_period)",
    "monthly_pnl_flow_change": "monthly_flow(current) - monthly_flow(previous_month)",
    "yoy_pct": "(current - same_month_last_year) / abs(same_month_last_year) * 100; standard P&L YoY uses same-month cumulative values",
    "monthly_yoy_pct": "(monthly_flow(current_year) - monthly_flow(prior_year)) / abs(monthly_flow(prior_year)) * 100",
    "ytd_pnl": "ending cumulative value at the requested period; never sum cumulative monthly observations",
    "gap_to_target_pct": "(actual - target) / abs(target) * 100",
    "achievement_pct": "actual / target * 100",
    "contribution_to_change_pct": "component_change / total_change * 100 when denominator is non-zero",
    "net_profit_bridge": "revenue - operating_expense - other applicable income/expense components, according to available income statement lines",
    "asset_funding_bridge": "asset movement can be decomposed against credit, investment and other balance-sheet movements available in evidence",
}


def catalog_for_llm(periods: list[str], latest_period: str | None) -> dict[str, Any]:
    return {
        "purpose": "Dictionary of available financial evidence. No financial values are included here.",
        "available_periods": periods, "latest_period": latest_period,
        "evidence": EVIDENCE_CATALOG, "comparisons": COMPARISONS,
        "relationships": RELATIONSHIPS, "formulas": FORMULAS,
        "knowledge": knowledge_for_llm(),
        "scope_schema": {
            "scope_type": ["POINT", "COMPARISON", "RANGE", "TREND", "YTD", "DIAGNOSIS", "TARGET_ANALYSIS", "SCENARIO"],
            "granularity": ["MONTHLY", "PERIOD"],
            "include_all_periods": "Must be true for RANGE/TREND/YTD questions. Retrieve every available period between start_period and end_period.",
            "analysis": ["SNAPSHOT", "MOM", "YOY", "YTD", "TREND", "DRIVER_ANALYSIS", "TARGET_GAP", "TARGET_HISTORY", "TURNING_POINT", "HIGHEST_LOWEST", "CONTRIBUTION", "SCENARIO"],
        },
        "request_schema": {"id": "valid evidence ID", "period": "primary/end period YYYY-MM", "start_period": "YYYY-MM when range is required", "end_period": "YYYY-MM when range is required", "granularity": "MONTHLY or PERIOD", "include_all_periods": "boolean", "comparisons": "subset of mom,yoy,monthly_yoy,ytd,target,trend", "fields": "optional list", "lines": "optional list", "products": "optional list"},
        "rules": [
            "Planner may request only evidence IDs listed in evidence.",
            "Planner must identify scope and analytical purpose before selecting evidence.",
            "For RANGE/TREND/YTD, include_all_periods must be true and start_period/end_period must be populated.",
            "Endpoints are not a substitute for a requested range.",
            "Income statement source amounts are cumulative/YTD. Never interpret a cumulative P&L amount as one month's performance.",
            "For P&L MoM, monthly trend, highest/lowest month and turning points, use Python's monthly_flow evidence.",
            "For P&L YTD and standard YoY, use cumulative values at the relevant ending/same-month periods; never sum cumulative months.",
            "Use monthly_yoy only when the user asks for individual-month YoY performance.",
            "When the question asks why/how/driver, the planner should request component evidence before causal interpretation.",
            "Python is authoritative for numbers and deterministic calculations only. It must not infer user intent, decide what a question means, or generate the final interpretation.",
            "The analyst LLM must perform the reasoning and final interpretation from the evidence supplied by Python.",
        ],
    }
