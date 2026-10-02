"""Financial semantic knowledge used by the FinAI planner and analyst.

This module contains definitions and interpretation guardrails, not financial values.
The goal is to stop the LLM from treating similarly named metrics as interchangeable
and to make valid diagnostic paths explicit.
"""
from __future__ import annotations
from typing import Any

METRIC_KNOWLEDGE: dict[str, dict[str, Any]] = {
    "total_assets": {
        "definition": "Total assets reported by the bank for the period.",
        "category": "balance_sheet_asset",
        "unit": "Rp miliar",
        "related": ["total_credit", "total_investment", "total_dpk", "total_other_funding"],
        "interpretation": ["growth indicates an increase in the asset base, subject to composition analysis"],
        "caution": ["asset growth alone does not establish profitability or efficiency"],
    },
    "total_credit": {
        "definition": "Total outstanding credit/financing at the reporting date.",
        "category": "earning_asset",
        "unit": "Rp miliar",
        "related": ["loan_products", "revenue", "npl_ratio", "ckpn", "ckpn_coverage"],
        "interpretation": ["growth indicates credit portfolio expansion when supported by the evidence"],
        "caution": ["credit growth does not by itself prove revenue or profit growth is caused by credit growth"],
    },
    "total_investment": {
        "definition": "Total investment/placement balance available in the summary data.",
        "category": "earning_asset",
        "unit": "Rp miliar",
        "related": ["investment_products", "revenue"],
        "caution": ["do not infer investment return quality from balance alone"],
    },
    "total_dpk": {
        "definition": "Total third-party funds/deposits in the available DPK data.",
        "category": "funding",
        "unit": "Rp miliar",
        "related": ["dpk_products", "low_cost_funding", "operating_expense"],
        "caution": ["balance growth does not by itself establish lower funding cost"],
    },
    "low_cost_funding": {
        "definition": "Share of funding classified as low-cost funding in the available KPI data.",
        "category": "funding_mix_ratio",
        "unit": "%",
        "related": ["total_dpk", "dpk_products"],
        "interpretation": ["higher share means a larger proportion of funding is classified as low-cost under the dataset definition"],
        "caution": ["do not equate the ratio directly with total funding cost without cost evidence"],
    },
    "revenue": {
        "definition": "Revenue/income KPI reported in monthly summary data.",
        "category": "income",
        "unit": "Rp miliar",
        "related": ["income_statement", "loan_products", "investment_products", "net_profit"],
        "interpretation": ["growth is an observed income movement; driver attribution requires component evidence"],
        "caution": ["do not attribute revenue growth to credit growth without driver evidence"],
    },
    "operating_expense": {
        "definition": "Operating expense KPI reported in monthly summary data.",
        "category": "expense",
        "unit": "Rp miliar",
        "related": ["income_statement", "net_profit"],
        "interpretation": ["growth indicates higher reported operating expense"],
        "caution": ["do not call a period efficient solely because profit increased"],
    },
    "ckpn": {
        "definition": "Credit impairment/provision amount available in the financial data.",
        "category": "credit_impairment_expense",
        "unit": "Rp miliar",
        "related": ["npl_ratio", "ckpn_coverage", "net_profit", "income_statement"],
        "interpretation": ["an increase means a larger reported provision amount, subject to sign/convention in the source data"],
        "forbidden_inferences": ["CKPN is not non-interest income", "CKPN increase does not automatically mean NPL increased", "CKPN decrease does not automatically mean credit quality improved"],
    },
    "ckpn_coverage": {
        "definition": "Coverage ratio relating available credit-loss reserves to the relevant non-performing exposure base under the dataset definition.",
        "category": "credit_risk_coverage_ratio",
        "unit": "%",
        "related": ["ckpn", "npl_ratio", "total_credit"],
        "interpretation": ["a lower ratio is an observed reduction in coverage; adequacy requires context on NPL and reserve composition"],
        "forbidden_inferences": ["CKPN coverage is not revenue", "a lower coverage ratio does not automatically mean profit fell", "a higher coverage ratio does not automatically mean credit quality improved"],
    },
    "npl_ratio": {
        "definition": "Non-performing loan ratio in the available KPI data.",
        "category": "asset_quality_ratio",
        "unit": "%",
        "related": ["total_credit", "loan_products", "ckpn", "ckpn_coverage"],
        "interpretation": ["a lower NPL ratio is an improvement in the asset-quality indicator itself"],
        "caution": ["NPL turun tidak otomatis berarti seluruh risiko gagal bayar turun", "do not claim that all default risk fell without supporting evidence on balances, recoveries, write-offs or composition"],
    },
    "net_profit": {
        "definition": "Net profit reported for the period in the available income statement/summary data.",
        "category": "profitability",
        "unit": "Rp miliar",
        "related": ["revenue", "operating_expense", "ckpn", "income_statement"],
        "diagnostic_path": ["revenue", "operating_expense", "income_statement", "ckpn"],
        "caution": ["profit growth alone does not establish efficiency or sustainability"],
    },
    "loan_products": {
        "definition": "Credit portfolio detail by product, including outstanding, revenue and selected risk/rate fields.",
        "category": "product_driver",
        "related": ["total_credit", "revenue", "npl_ratio"],
    },
    "investment_products": {
        "definition": "Investment/placement detail by type, including balance and revenue fields where available.",
        "category": "product_driver",
        "related": ["total_investment", "revenue"],
    },
    "dpk_products": {
        "definition": "DPK/funding detail by product, including balances, rates and funding cost fields.",
        "category": "funding_driver",
        "related": ["total_dpk", "low_cost_funding"],
    },
    "other_funding": {
        "definition": "Other funding detail by product/type with balance and funding cost fields.",
        "category": "funding_driver",
        "related": ["total_other_funding"],
    },
}

SEMANTIC_RULES = [
    "Observed movement is not the same as causal explanation.",
    "A metric may only be interpreted according to its definition and related evidence.",
    "When a user asks why/how a driver changed, request component evidence before making a causal claim.",
    "For range/trend questions, retrieve every available period inside the requested interval; endpoints alone are insufficient.",
    "Do not compare a monthly actual with a full-year target or YTD actual with monthly target unless the periods are explicitly comparable.",
    "Percentage-point changes apply to ratios; percent changes apply to amounts or growth rates as appropriate.",
    "If evidence is incomplete, say so and identify the missing evidence rather than filling the gap from general knowledge.",
]

DIAGNOSTIC_PATHS = {
    "profitability": [
        ["net_profit", "revenue", "operating_expense"],
        ["net_profit", "income_statement"],
        ["net_profit", "ckpn"],
    ],
    "credit_growth": [
        ["total_credit", "loan_products"],
        ["total_credit", "revenue", "loan_products"],
        ["total_credit", "npl_ratio", "ckpn", "ckpn_coverage"],
    ],
    "funding": [
        ["total_dpk", "low_cost_funding", "dpk_products"],
        ["total_other_funding", "other_funding"],
    ],
}


def knowledge_for_llm() -> dict[str, Any]:
    return {
        "metrics": METRIC_KNOWLEDGE,
        "semantic_rules": SEMANTIC_RULES,
        "diagnostic_paths": DIAGNOSTIC_PATHS,
    }
