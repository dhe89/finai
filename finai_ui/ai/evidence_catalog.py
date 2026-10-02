"""FinAI evidence dictionary.

This file contains *metadata only*: what financial data exists, how it is
related, and which deterministic comparison/formula operations Python can
perform. It intentionally contains no financial values.
"""
from __future__ import annotations

from typing import Any

COMPARISONS = {
    "mom": "Month-over-month: periode aktif dibanding bulan sebelumnya.",
    "yoy": "Year-over-year: periode aktif dibanding bulan yang sama tahun sebelumnya.",
    "ytd": "Year-to-date: akumulasi/posisi berjalan tahun kalender sampai periode aktif bila konsep metrik mendukung.",
    "target": "Perbandingan aktual terhadap target periode aktif.",
    "trend": "Deret historis bulanan untuk melihat arah/perubahan beberapa periode.",
}

EVIDENCE_CATALOG: dict[str, dict[str, Any]] = {
    "summary_kpi": {
        "description": "KPI bulanan tingkat bank: aset, kredit, investasi, funding, pendapatan, beban, CKPN, laba, NPL dan coverage.",
        "source": "monthly_summary.csv",
        "fields": [
            "total_assets", "total_credit", "total_investment", "total_dpk",
            "total_other_funding", "net_profit", "npl_ratio", "ckpn_coverage",
            "low_cost_funding", "revenue", "operating_expense", "ckpn",
        ],
        "comparisons": ["mom", "yoy", "ytd", "target", "trend"],
    },
    "balance_sheet": {
        "description": "Neraca bulanan per line item.",
        "source": "balance_sheet.csv",
        "fields": ["statement", "line_item", "amount"],
        "comparisons": ["mom", "yoy", "trend"],
    },
    "income_statement": {
        "description": "Laba rugi bulanan per line item, termasuk pendapatan produk, fee, beban funding, beban operasional, CKPN dan laba bersih.",
        "source": "income_statement.csv",
        "fields": ["line_item", "amount"],
        "comparisons": ["mom", "yoy", "ytd", "trend"],
    },
    "loan_products": {
        "description": "Rincian kredit per produk: outstanding, facility, kolektibilitas, rate, revenue dan status.",
        "source": "loan_detail.csv",
        "fields": ["product_type", "facility_amount", "outstanding", "collectibility", "rate_pa", "total_revenue", "status"],
        "comparisons": ["mom", "yoy", "trend"],
    },
    "investment_products": {
        "description": "Rincian investasi/penempatan per jenis: amount, kolektibilitas, rate, revenue dan status.",
        "source": "investment_detail.csv",
        "fields": ["investment_type", "investment_amount", "collectibility", "rate_pa", "total_revenue", "status"],
        "comparisons": ["mom", "yoy", "trend"],
    },
    "dpk_products": {
        "description": "Rincian DPK per produk: balance, rate, biaya bagi hasil dan status.",
        "source": "dpk_detail.csv",
        "fields": ["product_type", "balance", "rate_pa", "total_cost_bagi_hasil", "status"],
        "comparisons": ["mom", "yoy", "trend"],
    },
    "other_funding": {
        "description": "Rincian funding lain: balance, rate, biaya bagi hasil dan status.",
        "source": "other_funding_detail.csv",
        "fields": ["product_type", "balance", "rate_pa", "total_cost_bagi_hasil", "status"],
        "comparisons": ["mom", "yoy", "trend"],
    },
    "targets": {
        "description": "Target bulanan untuk asset, credit, investment, DPK, other funding, revenue, net profit, low-cost funding, operating expense, NPL dan coverage.",
        "source": "monthly_targets.csv",
        "fields": ["target_type", "metric", "target"],
        "comparisons": ["target", "trend"],
    },
    "audit_checks": {
        "description": "Hasil pemeriksaan konsistensi dataset, termasuk Assets = Liabilities + Equity.",
        "source": "audit_checks.csv",
        "fields": ["check", "difference", "status"],
        "comparisons": ["trend"],
    },
    "account_lifecycle": {
        "description": "Lifecycle account: record, product, start period dan close period.",
        "source": "account_lifecycle.csv",
        "fields": ["record_type", "record_no", "product_type", "start_period", "close_period"],
        "comparisons": [],
    },
    "account_status": {
        "description": "Status bulanan account: NEW, ACTIVE, CLOSED, NOT_STARTED.",
        "source": "account_status_monthly.csv",
        "fields": ["record_type", "record_no", "product_type", "period", "status"],
        "comparisons": ["trend"],
    },
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
    "mom_pct": "(current - previous_month) / abs(previous_month) * 100",
    "yoy_pct": "(current - same_month_last_year) / abs(same_month_last_year) * 100",
    "gap_to_target_pct": "(actual - target) / abs(target) * 100",
    "achievement_pct": "actual / target * 100",
    "contribution_to_change_pct": "component_change / total_change * 100 when denominator is non-zero",
    "net_profit_bridge": "revenue - operating_expense - other applicable income/expense components, according to available income statement lines",
    "asset_funding_bridge": "asset movement can be decomposed against credit, investment and other balance-sheet movements available in evidence",
}


def catalog_for_llm(periods: list[str], latest_period: str | None) -> dict[str, Any]:
    """Return the metadata dictionary supplied to the planning LLM."""
    return {
        "purpose": "Dictionary of available financial evidence. No financial values are included here.",
        "available_periods": periods,
        "latest_period": latest_period,
        "evidence": EVIDENCE_CATALOG,
        "comparisons": COMPARISONS,
        "relationships": RELATIONSHIPS,
        "formulas": FORMULAS,
        "rules": [
            "Planner may request only evidence IDs listed in evidence.",
            "Planner should request the minimum evidence needed to answer the question.",
            "Planner may request multiple comparison modes for the same evidence.",
            "Python is authoritative for numbers and calculations; LLM never invents values.",
        ],
    }
