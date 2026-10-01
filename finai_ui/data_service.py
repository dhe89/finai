from pathlib import Path
from html import escape
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIR = BASE_DIR / "finai_ui" / "frontend"
PAGES_DIR = FRONTEND_DIR / "pages"

_DATA_FILES = {
    "SUMMARY": DATA_DIR / "monthly_summary.csv",
    "BS": DATA_DIR / "balance_sheet.csv",
    "IS": DATA_DIR / "income_statement.csv",
    "TARGETS": DATA_DIR / "monthly_targets.csv",
    "LOANS": DATA_DIR / "loan_detail.csv",
    "INVESTMENTS": DATA_DIR / "investment_detail.csv",
    "DPK": DATA_DIR / "dpk_detail.csv",
    "OTHER": DATA_DIR / "other_funding_detail.csv",
    "AUDIT": DATA_DIR / "audit_checks.csv",
}


def _read_data_files():
    return {name: pd.read_csv(path) for name, path in _DATA_FILES.items()}


def _data_mtimes():
    return {name: path.stat().st_mtime_ns for name, path in _DATA_FILES.items()}


_data = _read_data_files()
_data_mtimes_snapshot = _data_mtimes()
SUMMARY = _data["SUMMARY"]
BS = _data["BS"]
IS = _data["IS"]
TARGETS = _data["TARGETS"]
LOANS = _data["LOANS"]
INVESTMENTS = _data["INVESTMENTS"]
DPK = _data["DPK"]
OTHER = _data["OTHER"]
AUDIT = _data["AUDIT"]

PERIODS = SUMMARY["period"].tolist()
LATEST_PERIOD = PERIODS[-1]
START_PERIOD = PERIODS[0]
UNIT = "Rp miliar"


def ensure_data_fresh():
    """Reload simulation CSVs when GitHub/Streamlit provides a newer file.

    This avoids requiring a manual Streamlit reboot just because the CSV dataset
    changed. If no file changed, the already-loaded DataFrames are reused.
    """
    global _data_mtimes_snapshot, SUMMARY, BS, IS, TARGETS, LOANS, INVESTMENTS, DPK, OTHER, AUDIT
    global PERIODS, LATEST_PERIOD, START_PERIOD

    current_mtimes = _data_mtimes()
    if current_mtimes == _data_mtimes_snapshot:
        return False

    refreshed = _read_data_files()
    SUMMARY = refreshed["SUMMARY"]
    BS = refreshed["BS"]
    IS = refreshed["IS"]
    TARGETS = refreshed["TARGETS"]
    LOANS = refreshed["LOANS"]
    INVESTMENTS = refreshed["INVESTMENTS"]
    DPK = refreshed["DPK"]
    OTHER = refreshed["OTHER"]
    AUDIT = refreshed["AUDIT"]
    PERIODS = SUMMARY["period"].tolist()
    LATEST_PERIOD = PERIODS[-1]
    START_PERIOD = PERIODS[0]
    _data_mtimes_snapshot = current_mtimes
    return True


def fmt(v, d=1):
    if v is None or pd.isna(v):
        return "-"
    return f"{float(v):,.{d}f}"


def pct(v):
    return f"{float(v):.2f}%"


def period_label(p):
    return pd.to_datetime(p + "-01").strftime("%B %Y")


def prev_period(p):
    return PERIODS[max(0, PERIODS.index(p) - 1)]


def yoy_period(p):
    y, m = p.split("-")
    q = f"{int(y) - 1:04d}-{m}"
    return q if q in PERIODS else PERIODS[0]


def srow(p):
    return SUMMARY.loc[SUMMARY.period.eq(p)].iloc[0]


def target(p, metric):
    q = TARGETS[(TARGETS.period == p) & (TARGETS.metric == metric)]
    return None if q.empty else float(q.iloc[0].target)


def ach(actual, target_value, inverse=False):
    if target_value is None or target_value == 0 or pd.isna(target_value):
        return None
    if inverse:
        return target_value / actual * 100 if actual else None
    return actual / target_value * 100


def agg(df, p, key, value, extra=None):
    x = df[df.period.eq(p)].groupby(key, as_index=False)[value].sum()
    if extra:
        y = df[df.period.eq(p)].groupby(key, as_index=False)[extra].sum()
        x = x.merge(y, on=key, how="left")
    return x.sort_values(value, ascending=False)


def esc(v):
    return escape(str(v))


def load_template(name):
    return (PAGES_DIR / name).read_text(encoding="utf-8")


def fill(template, **values):
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template


def shell_values(p):
    return {"PERIOD": esc(period_label(p)), "UNIT": esc(UNIT)}



# --- CSV auto-refresh layer ---
_CSV_FILES = [
    "monthly_summary.csv", "balance_sheet.csv", "income_statement.csv",
    "monthly_targets.csv", "loan_detail.csv", "investment_detail.csv",
    "dpk_detail.csv", "other_funding_detail.csv", "account_lifecycle.csv",
    "account_status_monthly.csv", "audit_checks.csv"
]
_CSV_CACHE = {}
_CSV_MTIME = {}

def refresh_csv_data():
    """Reload every simulation CSV whose file modification time changed."""
    for _name in _CSV_FILES:
        _path = DATA_DIR / _name
        if not _path.exists():
            continue
        _mtime = _path.stat().st_mtime_ns
        if _CSV_MTIME.get(_name) != _mtime:
            _CSV_CACHE[_name] = pd.read_csv(_path)
            _CSV_MTIME[_name] = _mtime
    # Keep legacy module-level DataFrame names synchronized.
    globals()["SUMMARY"] = _CSV_CACHE.get("monthly_summary.csv", pd.DataFrame())
    globals()["BS"] = _CSV_CACHE.get("balance_sheet.csv", pd.DataFrame())
    globals()["IS"] = _CSV_CACHE.get("income_statement.csv", pd.DataFrame())
    globals()["TARGETS"] = _CSV_CACHE.get("monthly_targets.csv", pd.DataFrame())
    globals()["LOANS"] = _CSV_CACHE.get("loan_detail.csv", pd.DataFrame())
    globals()["INVESTMENTS"] = _CSV_CACHE.get("investment_detail.csv", pd.DataFrame())
    globals()["DPK"] = _CSV_CACHE.get("dpk_detail.csv", pd.DataFrame())
    globals()["OTHER_FUNDING"] = _CSV_CACHE.get("other_funding_detail.csv", pd.DataFrame())
    globals()["LIFECYCLE"] = _CSV_CACHE.get("account_lifecycle.csv", pd.DataFrame())
    globals()["STATUS_MONTHLY"] = _CSV_CACHE.get("account_status_monthly.csv", pd.DataFrame())
    globals()["AUDIT"] = _CSV_CACHE.get("audit_checks.csv", pd.DataFrame())
    return True



def format_period_id(period_id):
    if not period_id:
        return "Latest"
    try:
        return pd.to_datetime(str(period_id) + "-01").strftime("%B %Y")
    except Exception:
        return str(period_id)

# --- Latest period detection ---
_PERIOD_COLUMNS = ("Period", "period", "Month", "month", "Date", "date", "Reporting Period")

def _period_series(df):
    if df is None or df.empty:
        return pd.Series(dtype="datetime64[ns]")
    for col in _PERIOD_COLUMNS:
        if col in df.columns:
            raw = df[col]
            # First try normal datetime parsing, then YYYY-MM strings.
            parsed = pd.to_datetime(raw, errors="coerce")
            if parsed.notna().any():
                return parsed
            parsed = pd.to_datetime(raw.astype(str), format="%Y-%m", errors="coerce")
            if parsed.notna().any():
                return parsed
    return pd.Series([pd.NaT] * len(df), index=df.index)

def get_latest_period():
    """Return the latest reporting period available in monthly_summary.csv."""
    refresh_csv_data()
    df = _summary_df() if "_summary_df" in globals() else globals().get("SUMMARY", pd.DataFrame())
    s = _period_series(df)
    if s.notna().any():
        return s.max().strftime("%Y-%m")
    return None

def get_latest_date():
    """Return latest available reporting date/period as a pandas Timestamp."""
    refresh_csv_data()
    df = _summary_df() if "_summary_df" in globals() else globals().get("SUMMARY", pd.DataFrame())
    s = _period_series(df)
    return s.max() if s.notna().any() else None

def filter_latest_period(df):
    """Return rows for the latest reporting period of the supplied dataframe."""
    if df is None or df.empty:
        return df
    latest = get_latest_period()
    s = _period_series(df)
    if latest and s.notna().any():
        return df.loc[s.dt.strftime("%Y-%m") == latest].copy()
    return df

def get_previous_period():
    """Return the immediately preceding period available in monthly_summary.csv."""
    refresh_csv_data()
    df = _summary_df() if "_summary_df" in globals() else globals().get("SUMMARY", pd.DataFrame())
    s = _period_series(df)
    vals = sorted(s.dropna().dt.to_period("M").unique())
    if len(vals) >= 2:
        return str(vals[-2])
    return None

def render_kinerja(p=LATEST_PERIOD):
    refresh_csv_data()
    current_period = get_latest_period()
    refresh_csv_data()
    s = srow(p)
    prev = srow(prev_period(p))
    last = srow(yoy_period(p))

    cards = []
    for label, key in [
        ("Total Assets", "total_assets"),
        ("Total Credit", "total_credit"),
        ("Total DPK", "total_dpk"),
        ("Net Profit", "net_profit"),
    ]:
        actual = float(s[key])
        previous = float(prev[key])
        change = (actual / previous - 1) * 100 if previous else 0
        cards.append(
            f'<div class="card metric"><div class="metric-label">{label}</div>'
            f'<div class="metric-value">{fmt(actual)}</div>'
            f'<div class="metric-change">{change:+.2f}% vs last month</div></div>'
        )

    rows = [
        ("ASSET", "Total Asset", "total_assets", "Total Asset", False),
        ("", "Total Credit", "total_credit", "Total Credit", False),
        ("", "Total Investment", "total_investment", "Total Investment", False),
        ("FUNDING", "Total DPK", "total_dpk", "Total DPK", False),
        ("", "Total Other Funding", "total_other_funding", "Total Other Funding", False),
        ("", "Low Cost Funding %", "low_cost_funding", "Low Cost Funding %", False),
        ("PROFITABILITY", "Revenue", "revenue", "Total Revenue", False),
        ("", "Operating Expense", "operating_expense", "Operating Expense", True),
        ("", "CKPN", "ckpn", None, True),
        ("", "Net Profit", "net_profit", "Net Profit", False),
        ("ASSET QUALITY", "NPL Ratio", "npl_ratio", "NPL Ratio %", True),
        ("", "CKPN Coverage", "ckpn_coverage", "CKPN Coverage %", False),
    ]

    table_rows = []
    for section, label, key, target_metric, inverse in rows:
        if section:
            table_rows.append(f'<tr class="section"><td colspan="6">{section}</td></tr>')
        actual = float(s[key])
        previous = float(prev[key])
        yearly = float(last[key])
        target_value = target(p, target_metric) if target_metric else None
        achievement = ach(actual, target_value, inverse)
        table_rows.append(
            f'<tr><td>{esc(label)}</td><td>{fmt(yearly)}</td><td>{fmt(previous)}</td>'
            f'<td>{fmt(actual)}</td><td>{fmt(target_value)}</td>'
            f'<td>{fmt(achievement) + "%" if achievement is not None else "-"}</td></tr>'
        )

    profitability = (
        f'<div class="kpi"><span class="kpi-label">Revenue</span><span class="kpi-value">{fmt(s.revenue)}</span></div>'
        f'<div class="kpi"><span class="kpi-label">Operating Expense</span><span class="kpi-value">{fmt(s.operating_expense)}</span></div>'
        f'<div class="kpi"><span class="kpi-label">Net Profit</span><span class="kpi-value">{fmt(s.net_profit)}</span></div>'
    )
    asset_quality = (
        f'<div class="kpi"><span class="kpi-label">NPL Ratio</span><span class="kpi-value">{pct(s.npl_ratio)}</span></div>'
        f'<div class="kpi"><span class="kpi-label">CKPN Coverage</span><span class="kpi-value">{pct(s.ckpn_coverage)}</span></div>'
        f'<div class="kpi"><span class="kpi-label">Low Cost Funding</span><span class="kpi-value">{pct(s.low_cost_funding)}</span></div>'
    )

    template = load_template("kinerja.html")
    return fill(
        template,
        PAGE_TITLE="Overview",
        PAGE_SUBTITLE=f"Financial performance overview for {esc(period_label(p))}",
        METRIC_CARDS="".join(cards),
        PERFORMANCE_ROWS="".join(table_rows),
        PROFITABILITY=profitability,
        ASSET_QUALITY=asset_quality,
        **shell_values(p),
    )


def render_financial_report(p=LATEST_PERIOD):
    refresh_csv_data()
    current_period = get_latest_period()
    refresh_csv_data()
    pp = prev_period(p)
    current_is = IS[IS.period.eq(p)]
    previous_is = dict(zip(IS[IS.period.eq(pp)].line_item, IS[IS.period.eq(pp)].amount))

    income_rows = []
    for _, row in current_is.iterrows():
        income_rows.append(
            f'<tr><td>{esc(row.line_item)}</td><td>{fmt(previous_is.get(row.line_item))}</td>'
            f'<td>{fmt(row.amount)}</td></tr>'
        )

    current_bs = BS[BS.period.eq(p)]
    previous_bs = dict(zip(BS[BS.period.eq(pp)].line_item, BS[BS.period.eq(pp)].amount))
    balance_rows = []
    for statement in ["Asset", "Kewajiban", "Ekuitas"]:
        balance_rows.append(f'<tr class="section"><td colspan="3">{statement.upper()}</td></tr>')
        for _, row in current_bs[current_bs.statement.eq(statement)].iterrows():
            balance_rows.append(
                f'<tr><td>{esc(row.line_item)}</td><td>{fmt(previous_bs.get(row.line_item))}</td>'
                f'<td>{fmt(row.amount)}</td></tr>'
            )

    audit_status = "PASS" if (AUDIT.status == "PASS").all() else "CHECK"
    template = load_template("financial_report.html")
    return fill(
        template,
        INCOME_STATEMENT_ROWS="".join(income_rows),
        BALANCE_SHEET_ROWS="".join(balance_rows),
        DATA_STATUS=f"Simulation Data · Audit {audit_status}",
        **shell_values(p),
    )


def product_summary_card(title, df, p, key, value, extra):
    data = agg(df, p, key, value, extra)
    rows = "".join(
        f'<tr><td>{esc(row[key])}</td><td>{fmt(row[value])}</td><td>{fmt(row[extra])}</td></tr>'
        for _, row in data.iterrows()
    )
    return (
        f'<section class="card table-card"><div class="table-head"><div>'
        f'<div class="table-title">{esc(title)}</div>'
        f'<div class="caption">Product aggregation for selected period · {len(df[df.period.eq(p)])} active records</div>'
        f'</div></div><div class="data-wrap"><table><thead><tr>'
        f'<th>Product Type</th><th>Balance / Amount</th><th>Revenue / Cost</th></tr></thead><tbody>{rows}</tbody></table></div></section>'
    )


def render_data_detail(p=LATEST_PERIOD):
    refresh_csv_data()
    current_period = get_latest_period()
    refresh_csv_data()
    sections = []
    for title, df, key, value, extra in [
        ("Produk Kredit", LOANS, "product_type", "outstanding", "total_revenue"),
        ("Produk Investasi", INVESTMENTS, "investment_type", "investment_amount", "total_revenue"),
        ("Dana Pihak Ketiga", DPK, "product_type", "balance", "total_cost_bagi_hasil"),
        ("Dana Lainnya", OTHER, "product_type", "balance", "total_cost_bagi_hasil"),
    ]:
        data = agg(df, p, key, value, extra)
        rows = "".join(
            f'<tr><td>{esc(row[key])}</td><td>{fmt(row[value])}</td><td>{fmt(row[extra])}</td></tr>'
            for _, row in data.iterrows()
        )
        sections.append(
            f'<section class="card table-card"><div class="table-head"><div>'
            f'<div class="table-title">{esc(title)}</div>'
            f'<div class="caption">{len(df[df.period.eq(p)])} active records · aggregated by product</div>'
            f'</div></div><div class="data-wrap"><table><thead><tr>'
            f'<th>Product Type</th><th>Balance / Amount</th><th>Revenue / Cost</th></tr></thead><tbody>{rows}</tbody></table></div></section>'
        )

    loan_rows = []
    for _, row in LOANS[LOANS.period.eq(p)].sort_values("outstanding", ascending=False).iterrows():
        loan_rows.append(
            f'<tr><td>{esc(row.loan_no)}</td><td>{esc(row.product_type)}</td><td>{fmt(row.facility_amount)}</td>'
            f'<td>{fmt(row.outstanding)}</td><td>{int(row.collectibility)}</td><td>{float(row.rate_pa):.2f}%</td>'
            f'<td>{fmt(row.total_revenue)}</td><td>{esc(row.status)}</td></tr>'
        )

    investment_rows = []
    for _, row in INVESTMENTS[INVESTMENTS.period.eq(p)].sort_values("investment_amount", ascending=False).iterrows():
        investment_rows.append(
            f'<tr><td>{esc(row.investment_no)}</td><td>{esc(row.investment_type)}</td><td>{fmt(row.investment_amount)}</td>'
            f'<td>{int(row.collectibility)}</td><td>{float(row.rate_pa):.2f}%</td><td>{fmt(row.total_revenue)}</td><td>{esc(row.status)}</td></tr>'
        )

    dpk_rows = []
    for _, row in DPK[DPK.period.eq(p)].sort_values("balance", ascending=False).iterrows():
        dpk_rows.append(
            f'<tr><td>{esc(row.account_no)}</td><td>{esc(row.product_type)}</td><td>{fmt(row.balance)}</td>'
            f'<td>{float(row.rate_pa):.2f}%</td><td>{fmt(row.total_cost_bagi_hasil)}</td><td>{esc(row.status)}</td></tr>'
        )

    other_rows = []
    for _, row in OTHER[OTHER.period.eq(p)].sort_values("balance", ascending=False).iterrows():
        other_rows.append(
            f'<tr><td>{esc(row.account_no)}</td><td>{esc(row.product_type)}</td><td>{fmt(row.balance)}</td>'
            f'<td>{float(row.rate_pa):.2f}%</td><td>{fmt(row.total_cost_bagi_hasil)}</td><td>{esc(row.status)}</td></tr>'
        )

    detail_tables = f'''
<section class="card table-card"><div class="table-head"><div><div class="table-title">Rincian Produk Kredit</div><div class="caption">{len(loan_rows)} active monthly records</div></div></div>
<div class="data-wrap"><table><thead><tr><th>Nomor Loan</th><th>Product Type</th><th>Facility Amount</th><th>Outstanding</th><th>Collectibility</th><th>Rate p.a.</th><th>Total Revenue</th><th>Status</th></tr></thead><tbody>{''.join(loan_rows)}</tbody></table></div></section>
<section class="card table-card"><div class="table-head"><div><div class="table-title">Rincian Produk Investasi</div><div class="caption">{len(investment_rows)} active monthly records</div></div></div>
<div class="data-wrap"><table><thead><tr><th>Nomor Investment</th><th>Investment Type</th><th>Investment Amount</th><th>Collectibility</th><th>Rate p.a.</th><th>Total Revenue</th><th>Status</th></tr></thead><tbody>{''.join(investment_rows)}</tbody></table></div></section>
<section class="card table-card"><div class="table-head"><div><div class="table-title">Rincian Dana Pihak Ketiga</div><div class="caption">{len(dpk_rows)} active monthly records</div></div></div>
<div class="data-wrap"><table><thead><tr><th>Nomor Account</th><th>Product Type</th><th>Balance</th><th>Rate p.a.</th><th>Total Cost / Bagi Hasil</th><th>Status</th></tr></thead><tbody>{''.join(dpk_rows)}</tbody></table></div></section>
<section class="card table-card"><div class="table-head"><div><div class="table-title">Rincian Dana Lainnya</div><div class="caption">{len(other_rows)} active monthly records</div></div></div>
<div class="data-wrap"><table><thead><tr><th>Nomor Account</th><th>Product Type</th><th>Balance</th><th>Rate p.a.</th><th>Total Cost / Bagi Hasil</th><th>Status</th></tr></thead><tbody>{''.join(other_rows)}</tbody></table></div></section>'''

    summaries = "".join([
        product_summary_card("Produk Kredit", LOANS, p, "product_type", "outstanding", "total_revenue"),
        product_summary_card("Produk Investasi", INVESTMENTS, p, "investment_type", "investment_amount", "total_revenue"),
        product_summary_card("Dana Pihak Ketiga", DPK, p, "product_type", "balance", "total_cost_bagi_hasil"),
        product_summary_card("Dana Lainnya", OTHER, p, "product_type", "balance", "total_cost_bagi_hasil"),
    ])

    template = load_template("data_detail.html")
    return fill(template, PRODUCT_SUMMARIES=summaries, DETAIL_TABLES=detail_tables, **shell_values(p))


def render_setting(p=LATEST_PERIOD):
    latest = srow(p)
    audit_pass = int((AUDIT.status == "PASS").sum())
    audit_total = len(AUDIT)
    audit_status = "PASS" if audit_pass == audit_total else "CHECK"

    template = load_template("setting.html")
    return fill(
        template,
        START_PERIOD=esc(period_label(START_PERIOD)),
        LATEST_PERIOD=esc(period_label(LATEST_PERIOD)),
        CAPITAL=fmt(6000),
        TARGET_ASSETS=fmt(80000),
        TARGET_CREDIT=fmt(60000),
        TARGET_DPK=fmt(65000),
        AUDIT_STATUS=audit_status,
        AUDIT_TOTAL=f"{audit_pass}/{audit_total} PASS",
        LATEST_ASSETS=fmt(latest.total_assets),
        LATEST_NET_PROFIT=fmt(latest.net_profit),
        **shell_values(p),
    )


def render_page(page, p=LATEST_PERIOD):
    ensure_data_fresh()
    renderers = {
        "kinerja": render_kinerja,
        "financial_report": render_financial_report,
        "data_detail": render_data_detail,
        "setting": render_setting,
    }
    return renderers[page](p)


def build_financial_context(p=LATEST_PERIOD):
    ensure_data_fresh()
    s = srow(p)
    pp = prev_period(p)
    keys = [
        "total_assets", "total_credit", "total_investment", "total_dpk",
        "total_other_funding", "net_profit", "revenue", "operating_expense",
        "ckpn", "npl_ratio", "ckpn_coverage", "low_cost_funding",
    ]
    return {
        "period": p,
        "unit": UNIT,
        "kpi": {k: float(s[k]) for k in keys},
        "previous_month": {k: float(srow(pp)[k]) for k in keys},
        "balance_sheet": BS[BS.period.eq(p)].to_dict("records"),
        "income_statement": IS[IS.period.eq(p)].to_dict("records"),
        "targets": TARGETS[TARGETS.period.eq(p)].to_dict("records"),
        "loan_products": agg(LOANS, p, "product_type", "outstanding", "total_revenue").to_dict("records"),
        "investment_products": agg(INVESTMENTS, p, "investment_type", "investment_amount", "total_revenue").to_dict("records"),
        "dpk_products": agg(DPK, p, "product_type", "balance", "total_cost_bagi_hasil").to_dict("records"),
        "other_funding_products": agg(OTHER, p, "product_type", "balance", "total_cost_bagi_hasil").to_dict("records"),
    }

# Initial load
refresh_csv_data()


# Compatibility value: derived from the current CSV, never hardcoded.
LATEST_PERIOD = get_latest_period()
