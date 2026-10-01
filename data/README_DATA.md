# FinAI Simulation Data

Unit: **Rp miliar**. Therefore `80,000` = **Rp80 triliun**.

Coverage: **January 2024 through September 2026** (33 monthly periods).

The dataset is a simulated Islamic banking prototype with formation-time accounting and data-integrity controls.

## Main files

- `monthly_summary.csv` — monthly dashboard KPIs.
- `balance_sheet.csv` — monthly statement of financial position.
- `income_statement.csv` — monthly income statement detail.
- `monthly_targets.csv` — monthly targets for growth, profitability, efficiency and quality.
- `loan_detail.csv` — monthly loan-level snapshots.
- `investment_detail.csv` — monthly investment-level snapshots.
- `dpk_detail.csv` — monthly DPK account snapshots.
- `other_funding_detail.csv` — monthly other-funding snapshots.
- `account_lifecycle.csv` — simulated account/facility start and close periods.
- `account_status_monthly.csv` — explicit `NEW`, `ACTIVE`, `CLOSED`, and `NOT_STARTED` status by month.
- `audit_checks.csv` — formation-time reconciliation and sanity checks.

## Source-of-truth principle

The web pages and AI evidence use the same CSV dataset through `finai_ui/data_service.py`.

```text
CSV Simulation Data
        |
        +--> Dashboard Kinerja
        +--> Laporan Keuangan
        +--> Rincian Data
        +--> Setting / Audit Status
        +--> AI Financial Evidence
```

The HTML files under `finai_ui/frontend/pages/` are templates only. They contain no simulation figures. `data_service.py` loads the appropriate template and injects the current-period data.

## Accounting controls

The formation-time audit includes, among others:

- Assets = Liabilities + Equity.
- Current-year YTD net profit = Balance Sheet `Laba Tahun Berjalan`.
- Income Statement arithmetic.
- Credit detail = Balance Sheet Credit.
- Investment detail = Balance Sheet Penempatan.
- DPK detail = Giro + Tabungan + Deposito.
- Loan Outstanding <= Facility Amount.
- Non-negative investment, DPK and other-funding balances.
- Non-negative product rates.

All generated audit checks must be `PASS` before the dataset is accepted.
