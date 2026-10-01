# FinAI Simulation Data

Unit: **Rp juta?** No — all financial amounts are **Rp miliar** (Rp bn), so 80,000 = Rp80 triliun.

Coverage: January 2024 through September 2026. Detail records are monthly snapshots with dynamic account lifecycle (new, active, closed).

Files:
- `monthly_summary.csv` — monthly dashboard KPIs.
- `balance_sheet.csv` — monthly balance sheet lines.
- `income_statement.csv` — monthly income statement lines.
- `monthly_targets.csv` — monthly targets by metric.
- `loan_detail.csv` — monthly loan-level detail.
- `investment_detail.csv` — monthly investment-level detail.
- `dpk_detail.csv` — monthly DPK account detail.
- `other_funding_detail.csv` — monthly other-funding detail.
- `account_lifecycle.csv` — lifecycle master for simulated accounts.
- `audit_checks.csv` — formation-time consistency checks.

The dataset is designed so loan/investment/DPK details reconcile to the corresponding balance-sheet positions, while the balance sheet always satisfies Assets = Liabilities + Equity. The balance-sheet current-year profit is reconciled to cumulative monthly net profit for the same year.
