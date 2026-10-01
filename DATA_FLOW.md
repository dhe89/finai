# FinAI Data Flow

This prototype uses one source of truth for both web content and AI evidence.

## Runtime flow

```text
/data/*.csv
     |
     v
finai_ui/data_service.py
     |
     +--------------------+---------------------+
     |                    |                     |
     v                    v                     v
HTML page templates     Dashboard/Reports    AI evidence context
     |
     v
Streamlit Components V2
     |
     v
Browser
```

## Page templates

- `frontend/pages/kinerja.html`
- `frontend/pages/financial_report.html`
- `frontend/pages/data_detail.html`
- `frontend/pages/setting.html`

These files intentionally contain placeholders such as `{{METRIC_CARDS}}` and `{{INCOME_STATEMENT_ROWS}}`, not hard-coded simulation figures.

## Data service

`finai_ui/data_service.py` is responsible for:

1. Loading CSV files.
2. Selecting the reporting period.
3. Aggregating product detail.
4. Rendering the page templates.
5. Building the financial evidence context used by the AI.

This prevents the dashboard, reports, detail pages and AI from maintaining separate copies of the same financial numbers.
