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


def normalize_periods(values):
    """Return unique YYYY-MM periods sorted chronologically."""
    out = []
    for value in values or []:
        try:
            out.append(pd.to_datetime(str(value) + "-01").strftime("%Y-%m"))
        except Exception:
            try:
                out.append(pd.to_datetime(value).strftime("%Y-%m"))
            except Exception:
                continue
    return sorted(set(out))


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

PERIODS = normalize_periods(SUMMARY["period"].tolist()) if "period" in SUMMARY.columns else []
LATEST_PERIOD = PERIODS[-1] if PERIODS else None
START_PERIOD = PERIODS[0] if PERIODS else None
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
    PERIODS = normalize_periods(SUMMARY["period"].tolist()) if "period" in SUMMARY.columns else []
    LATEST_PERIOD = PERIODS[-1] if PERIODS else None
    START_PERIOD = PERIODS[0] if PERIODS else None
    _data_mtimes_snapshot = current_mtimes
    return True


def fmt(v, d=1):
    if v is None or pd.isna(v):
        return "-"
    return f"{float(v):,.{d}f}"


def pct(v):
    return f"{float(v):.2f}%"


def period_label(p):
    return pd.to_datetime(str(p) + "-01").strftime("%B %Y")


def available_periods():
    refresh_csv_data()
    return normalize_periods(SUMMARY["period"].tolist()) if "period" in SUMMARY.columns else []


def resolve_period(p=None):
    periods = available_periods()
    if not periods:
        return None
    if p and str(p) in periods:
        return str(p)
    return periods[-1]


def prev_period(p):
    periods = available_periods()
    p = resolve_period(p)
    if not p or p not in periods:
        return p
    idx = periods.index(p)
    return periods[idx - 1] if idx > 0 else p


def yoy_period(p):
    periods = available_periods()
    p = resolve_period(p)
    if not p:
        return p
    y, m = p.split("-")
    q = f"{int(y) - 1:04d}-{m}"
    return q if q in periods else periods[0]


def srow(p):
    p = resolve_period(p)
    rows = SUMMARY.loc[SUMMARY.period.astype(str).eq(p)]
    return rows.iloc[0]


def period_selector_html(p):
    """Render the shared reporting-period selector used by every page."""
    periods = available_periods()
    selected = resolve_period(p)
    options = []
    for item in periods:
        sel = " selected" if item == selected else ""
        options.append(f'<option value="{esc(item)}"{sel}>{esc(period_label(item))}</option>')
    return (
        '<label class="period-picker" title="Pilih periode pelaporan">'
        '<span class="period-picker-label">Periode</span>'
        '<select id="periodSelect" class="period-select" aria-label="Pilih periode pelaporan">'
        + "".join(options) +
        '</select>'
        '<span class="period-chevron">⌄</span>'
        '</label>'
    )


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
    selected = resolve_period(p)
    return {
        "PERIOD": esc(period_label(selected)),
        "UNIT": esc(UNIT),
        "PERIOD_SELECTOR": period_selector_html(selected),
    }



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
    df = globals().get("SUMMARY", pd.DataFrame())
    s = _period_series(df)
    if s.notna().any():
        return s.max().strftime("%Y-%m")
    return None

def get_latest_date():
    """Return latest available reporting date/period as a pandas Timestamp."""
    refresh_csv_data()
    df = globals().get("SUMMARY", pd.DataFrame())
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
    df = globals().get("SUMMARY", pd.DataFrame())
    s = _period_series(df)
    vals = sorted(s.dropna().dt.to_period("M").unique())
    if len(vals) >= 2:
        return str(vals[-2])
    return None

def render_kinerja(p=None):
    refresh_csv_data()
    p = resolve_period(p)
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


def render_financial_report(p=None):
    refresh_csv_data()
    p = resolve_period(p)
    pp = prev_period(p)

    # --------------------------------------------------------------
    # Balance Sheet: left panel, grouped as Asset / Kewajiban / Ekuitas
    # with parent totals calculated from their child line items.
    # --------------------------------------------------------------
    current_bs = BS[BS.period.eq(p)]
    previous_bs = dict(zip(BS[BS.period.eq(pp)].line_item, BS[BS.period.eq(pp)].amount))

    bs_groups = [
        ("ASSET", "Asset"),
        ("KEWAJIBAN", "Kewajiban"),
        ("EKUITAS", "Ekuitas"),
    ]
    balance_rows = []
    bs_totals = {}

    for label, statement in bs_groups:
        group = current_bs[current_bs.statement.eq(statement)]
        prev_group = BS[(BS.period.eq(pp)) & (BS.statement.eq(statement))]
        current_total = float(group.amount.sum()) if not group.empty else 0.0
        previous_total = float(prev_group.amount.sum()) if not prev_group.empty else 0.0
        bs_totals[statement] = (previous_total, current_total)

        # Parent row carries the subtotal; do not repeat it below the children.
        balance_rows.append(
            f'<tr class="section parent-total"><td>{label}</td>'
            f'<td>{fmt(previous_total)}</td><td>{fmt(current_total)}</td></tr>'
        )
        for _, row in group.iterrows():
            balance_rows.append(
                f'<tr><td>{esc(row.line_item)}</td><td>{fmt(previous_bs.get(row.line_item))}</td>'
                f'<td>{fmt(row.amount)}</td></tr>'
            )

    # --------------------------------------------------------------
    # Income Statement: right panel, grouped as requested.
    # Pendapatan Investasi is presented under Pendapatan Operasional
    # Lainnya so that every income/expense component participates in
    # the requested profit formula:
    # Pendapatan Bunga - Beban Bunga + Pendapatan Operasional Lainnya
    # - Beban Operasional Lainnya.
    # --------------------------------------------------------------
    current_is = IS[IS.period.eq(p)]
    previous_is = dict(zip(IS[IS.period.eq(pp)].line_item, IS[IS.period.eq(pp)].amount))

    income_groups = [
        ("PENDAPATAN BUNGA", lambda x: x.startswith("Pendapatan Bunga")),
        ("BEBAN BUNGA", lambda x: x.startswith("Beban Bunga")),
        (
            "PENDAPATAN OPERASIONAL LAINNYA",
            lambda x: x.startswith("Pendapatan Operasional Lainnya") or x == "Pendapatan Investasi",
        ),
        ("BEBAN OPERASIONAL LAINNYA", lambda x: x.startswith("Beban Operasional Lainnya")),
    ]

    income_rows = []
    income_totals = {}
    for label, matcher in income_groups:
        group = current_is[current_is.line_item.map(matcher)]
        prev_group = IS[IS.period.eq(pp) & IS.line_item.map(matcher)]
        current_total = float(group.amount.sum()) if not group.empty else 0.0
        previous_total = float(prev_group.amount.sum()) if not prev_group.empty else 0.0
        income_totals[label] = (previous_total, current_total)

        # Parent row carries the subtotal; do not repeat it below the children.
        income_rows.append(
            f'<tr class="section parent-total"><td>{label}</td>'
            f'<td>{fmt(previous_total)}</td><td>{fmt(current_total)}</td></tr>'
        )
        for _, row in group.iterrows():
            income_rows.append(
                f'<tr><td>{esc(row.line_item)}</td><td>{fmt(previous_is.get(row.line_item))}</td>'
                f'<td>{fmt(row.amount)}</td></tr>'
            )

    # Profit is explicitly derived from the four grouped totals.
    previous_profit = (
        income_totals["PENDAPATAN BUNGA"][0]
        - income_totals["BEBAN BUNGA"][0]
        + income_totals["PENDAPATAN OPERASIONAL LAINNYA"][0]
        - income_totals["BEBAN OPERASIONAL LAINNYA"][0]
    )
    current_profit = (
        income_totals["PENDAPATAN BUNGA"][1]
        - income_totals["BEBAN BUNGA"][1]
        + income_totals["PENDAPATAN OPERASIONAL LAINNYA"][1]
        - income_totals["BEBAN OPERASIONAL LAINNYA"][1]
    )
    # Profit is itself the parent subtotal for the LABA RUGI group.
    income_rows.append(
        f'<tr class="section parent-total profit-total"><td>LABA RUGI</td>'
        f'<td>{fmt(previous_profit)}</td><td>{fmt(current_profit)}</td></tr>'
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


def render_data_detail(p=None):
    refresh_csv_data()
    p = resolve_period(p)
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


def render_setting(p=None):
    refresh_csv_data()
    p = resolve_period(p)
    selected = srow(p)
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
        LATEST_ASSETS=fmt(selected.total_assets),
        LATEST_NET_PROFIT=fmt(selected.net_profit),
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


# ---------------------------------------------------------------------------
# AI EVIDENCE LAYER
# ---------------------------------------------------------------------------
# Python is the source of truth. The LLM receives only the evidence returned
# by these functions and is never asked to discover figures from raw context.

_MONTH_NAMES = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5,
    "juni": 6, "juli": 7, "agustus": 8, "september": 9, "oktober": 10,
    "november": 11, "desember": 12,
    "january": 1, "february": 2, "march": 3, "may": 5, "june": 6,
    "july": 7, "august": 8, "october": 10, "december": 12,
}

_METRIC_ALIASES = {
    "net_profit": ["laba bersih", "laba rugi", "laba", "net profit", "profit"],
    "total_assets": ["total aset", "total asset", "aset"],
    "total_credit": ["total kredit", "kredit", "pembiayaan", "pembiayaan kredit"],
    "total_investment": ["total investasi", "investasi", "penempatan"],
    "total_dpk": ["total dpk", "dpk", "dana pihak ketiga"],
    "total_other_funding": ["dana lainnya", "other funding", "pendanaan lainnya"],
    "revenue": ["revenue", "pendapatan", "total pendapatan"],
    "operating_expense": ["beban operasional", "biaya operasional", "operating expense", "opex"],
    "ckpn": ["ckpn", "cadangan kerugian penurunan nilai"],
    "npl_ratio": ["npl", "npf", "npl ratio", "npf ratio", "rasio npl", "rasio npf"],
    "ckpn_coverage": ["ckpn coverage", "coverage ckpn", "cakupan ckpn"],
    "low_cost_funding": ["low cost funding", "lcf", "dana murah"],
}

_FINANCIAL_TERMS = set(sum(_METRIC_ALIASES.values(), [])) | {
    "neraca", "balance sheet", "laba rugi", "income statement", "pendapatan bunga",
    "beban bunga", "pendapatan investasi", "fee based", "kualitas aset", "kualitas kredit",
    "kolektibilitas", "collectibility", "target", "efisiensi", "margin", "revenue",
    "aset", "liabilitas", "kewajiban", "ekuitas", "modal", "loan", "kredit", "investasi",
    "tabungan", "giro", "deposito", "dana", "account", "loan", "portfolio", "produk",
    "profitabilitas", "profitability", "pertumbuhan", "growth", "ytd", "yoy",
}

_OUT_OF_SCOPE_TERMS = {
    "presiden", "politik", "partai", "pemilu", "sepak bola", "bola", "film", "musik",
    "resep", "masakan", "cuaca", "game", "pacar", "jodoh", "password", "instagram",
}


def _normalise_text(text):
    return " ".join(str(text or "").lower().strip().split())


def _detect_period_mentions(text):
    """Detect explicit month/year mentions and return YYYY-MM periods."""
    import re
    text = _normalise_text(text)
    found = []
    # Indonesian/English month names + year.
    month_pattern = "|".join(sorted((re.escape(x) for x in _MONTH_NAMES), key=len, reverse=True))
    for m in re.finditer(rf"\b({month_pattern})\s+(20\d{{2}})\b", text, flags=re.I):
        month = _MONTH_NAMES[m.group(1).lower()]
        period = f"{int(m.group(2)):04d}-{month:02d}"
        if period not in found:
            found.append(period)
    # YYYY-MM format.
    for m in re.finditer(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", text):
        period = f"{m.group(1)}-{m.group(2)}"
        if period not in found:
            found.append(period)
    return found


def _detect_metrics(text):
    text = _normalise_text(text)
    hits = []
    for metric, aliases in _METRIC_ALIASES.items():
        if any(alias in text for alias in aliases):
            hits.append(metric)
    return hits


def _has_financial_term(text):
    text = _normalise_text(text)
    if any(term in text for term in _FINANCIAL_TERMS):
        return True
    # Treat every statement/target line item in the actual CSV as financial
    # vocabulary, so questions such as “berapa kas?” or “berapa modal?” are
    # not incorrectly blocked as out-of-scope.
    for df in (BS, IS, TARGETS):
        if df is not None and not df.empty:
            for col in ("line_item", "metric", "category"):
                if col in df.columns:
                    terms = [
                        _normalise_text(v) for v in df[col].dropna().astype(str).unique()
                    ]
                    if any(term and term in text for term in terms):
                        return True
    return False


def _is_assistant_meta(text):
    """Questions about FinAI itself can be answered without financial evidence."""
    text = _normalise_text(text)
    return any(term in text for term in [
        "perkenalkan dirimu", "perkenalkan diri", "siapa kamu",
        "siapa anda", "apa itu finai", "apa itu fin ai",
    ])


def _is_out_of_scope(text):
    """Fail closed for non-financial questions before they reach the LLM."""
    text = _normalise_text(text)
    if _is_assistant_meta(text):
        return False
    if any(term in text for term in _OUT_OF_SCOPE_TERMS) and not _has_financial_term(text):
        return True
    # If a question has no financial vocabulary at all, it is not a FinAI
    # financial question. Do not let the LLM guess or answer from general knowledge.
    return not _has_financial_term(text)


def _period_records(df, period):
    if df is None or df.empty or "period" not in df.columns:
        return df.iloc[0:0] if df is not None else pd.DataFrame()
    return df[df.period.astype(str).eq(str(period))].copy()


def _summary_evidence(period, metrics=None, include_overview=False):
    row = srow(period)
    all_values = {
        "total_assets": float(row.total_assets),
        "total_credit": float(row.total_credit),
        "total_investment": float(row.total_investment),
        "total_dpk": float(row.total_dpk),
        "total_other_funding": float(row.total_other_funding),
        "net_profit": float(row.net_profit),
        "revenue": float(row.revenue),
        "operating_expense": float(row.operating_expense),
        "ckpn": float(row.ckpn),
        "npl_ratio": float(row.npl_ratio),
        "ckpn_coverage": float(row.ckpn_coverage),
        "low_cost_funding": float(row.low_cost_funding),
    }
    selected = all_values if include_overview else {
        key: all_values[key] for key in (metrics or []) if key in all_values
    }
    return {
        "period": period,
        "unit": UNIT,
        "kpi": selected,
    }


def _income_group_totals(period):
    df = _period_records(IS, period)
    groups = {
        "pendapatan_bunga": df[df.line_item.astype(str).str.startswith("Pendapatan Bunga")].amount.sum(),
        "beban_bunga": df[df.line_item.astype(str).str.startswith("Beban Bunga")].amount.sum(),
        "pendapatan_operasional_lainnya": df[
            df.line_item.astype(str).str.startswith("Pendapatan Operasional Lainnya")
            | df.line_item.astype(str).eq("Pendapatan Investasi")
        ].amount.sum(),
        "beban_operasional_lainnya": df[df.line_item.astype(str).str.startswith("Beban Operasional Lainnya")].amount.sum(),
    }
    groups["laba_rugi_hasil_perhitungan"] = (
        groups["pendapatan_bunga"] - groups["beban_bunga"]
        + groups["pendapatan_operasional_lainnya"] - groups["beban_operasional_lainnya"]
    )
    return {k: float(v) for k, v in groups.items()}


def _metric_value(period, metric):
    row = srow(period)
    if metric in row.index:
        return float(row[metric])
    return None


def _comparison_periods(question, primary):
    """Return explicit comparison period(s) or the natural previous period."""
    q = _normalise_text(question)
    explicit = [p for p in _detect_period_mentions(q) if p != primary]
    if explicit:
        return explicit[:2]
    if any(x in q for x in ["bulan lalu", "month over month", "mom", "mom", "vs bulan lalu"]):
        return [prev_period(primary)]
    if any(x in q for x in ["tahun lalu", "year over year", "yoy", "vs tahun lalu"]):
        return [yoy_period(primary)]
    if any(x in q for x in ["bandingkan", "dibandingkan", "compare", "perubahan", "naik", "turun"]):
        return [prev_period(primary)]
    return []


def _compact_text(value):
    import re
    return re.sub(r"[^a-z0-9]+", "", _normalise_text(value))


def _statement_line_evidence(question, period, comparison_periods):
    """Find exact/near-exact CSV statement line items mentioned by the user."""
    q_compact = _compact_text(question)
    matches = []
    for df_name, df in (("balance_sheet", BS), ("income_statement", IS)):
        if df is None or df.empty:
            continue
        for item in sorted(df.line_item.dropna().astype(str).unique(), key=len, reverse=True):
            item_compact = _compact_text(item)
            if item_compact and item_compact in q_compact:
                rows = _period_records(df, period)
                hit = rows[rows.line_item.astype(str).eq(item)]
                if hit.empty:
                    continue
                record = {
                    "statement": df_name,
                    "line_item": item,
                    "period": period,
                    "amount": float(hit.iloc[0].amount),
                }
                if comparison_periods:
                    record["comparison"] = []
                    for cp in comparison_periods:
                        ch = _period_records(df, cp)
                        ch = ch[ch.line_item.astype(str).eq(item)]
                        if not ch.empty:
                            previous = float(ch.iloc[0].amount)
                            current = record["amount"]
                            delta = current - previous
                            record["comparison"].append({
                                "period": cp,
                                "amount": previous,
                                "change_absolute": delta,
                                "change_percent": (delta / previous * 100) if previous else None,
                            })
                matches.append(record)
                break
    return matches

def _direct_answer(question, evidence):
    """Return a deterministic answer for simple factual questions.

    This keeps the LLM out of one-number lookups, eliminating reasoning leakage
    and preventing the model from reinterpreting an exact Python result.
    """
    q = _normalise_text(question)
    if any(x in q for x in [
        "kenapa", "mengapa", "bagaimana", "bandingkan", "dibandingkan",
        "perubahan", "naik", "turun", "pertumbuhan", "target", "pencapaian",
    ]):
        return None
    if evidence.get("comparison"):
        return None
    period_label = evidence.get("selected_period_label") or evidence.get("selected_period")
    unit = evidence.get("unit", UNIT)

    # Exact statement-line matches take priority over broad aliases such as
    # “pendapatan” or “beban”, otherwise a specific line could be answered with
    # the total KPI instead of the requested child item.
    lines = evidence.get("statement_lines") or []
    if len(lines) == 1:
        item = lines[0]
        return f"{item['line_item']} {period_label}: Rp {float(item['amount']):,.2f} miliar."

    kpi = (evidence.get("current") or {}).get("kpi") or {}
    labels = {
        "net_profit": "Laba bersih", "total_assets": "Total aset",
        "total_credit": "Total kredit", "total_investment": "Total investasi",
        "total_dpk": "Total DPK", "total_other_funding": "Dana lainnya",
        "revenue": "Pendapatan", "operating_expense": "Beban operasional",
        "ckpn": "CKPN", "npl_ratio": "NPL",
        "ckpn_coverage": "CKPN Coverage", "low_cost_funding": "Low Cost Funding",
    }
    if len(kpi) == 1:
        key, value = next(iter(kpi.items()))
        label = labels.get(key, key.replace("_", " ").title())
        if key in {"npl_ratio", "ckpn_coverage", "low_cost_funding"}:
            return f"{label} {period_label}: {float(value):.2f}%."
        return f"{label} {period_label}: Rp {float(value):,.2f} miliar."

    return None


def build_financial_evidence(question, selected_period=None):
    """Validate a question and build deterministic evidence from CSV data.

    Returns a small structured object consumed by the LLM. It intentionally
    does not expose the whole dataset, so the model cannot choose a different
    period or manufacture facts from unrelated rows.
    """
    refresh_csv_data()
    q = _normalise_text(question)
    if not q:
        return {"status": "AMBIGUOUS", "message": "Pertanyaan belum diisi."}

    if _is_assistant_meta(q):
        return {
            "status": "META",
            "message": "Saya FinAI, asisten Financial Intelligence yang menjawab pertanyaan berdasarkan data keuangan yang tersedia di aplikasi.",
        }

    if _is_out_of_scope(q):
        return {
            "status": "OUT_OF_SCOPE",
            "message": "Pertanyaan berada di luar cakupan FinAI. FinAI hanya menjawab berdasarkan data dan informasi keuangan yang tersedia.",
        }

    periods = available_periods()
    mentioned = _detect_period_mentions(q)
    if mentioned:
        unavailable = [x for x in mentioned if x not in periods]
        if unavailable:
            return {
                "status": "NO_DATA",
                "period": unavailable[0],
                "message": f"Data untuk periode {format_period_id(unavailable[0])} tidak tersedia.",
            }
        primary = mentioned[0]
    else:
        primary = resolve_period(selected_period)

    if not primary:
        return {"status": "NO_DATA", "message": "Periode data belum tersedia."}

    metrics = _detect_metrics(q)
    # A specific financial metric that is not present in the supported evidence
    # model must fail closed rather than being guessed by the LLM.
    unsupported_metrics = [
        "roa", "roe", "car", "casa", "nim", "cost to income", "cir",
        "fdr", "ldr", "nsfr", "lcr", "capital adequacy", "capital ratio",
    ]
    if any(x in q for x in unsupported_metrics):
        return {
            "status": "NO_DATA",
            "period": primary,
            "message": f"Data untuk metrik yang ditanyakan pada periode {format_period_id(primary)} belum tersedia dalam evidence FinAI.",
        }

    # A broad dashboard request is allowed; a vague question without a
    # recognizable financial subject is not passed to the LLM.
    broad_terms = ["kinerja keuangan", "overview", "ringkasan", "dashboard", "kondisi keuangan"]
    statement_hint = bool(_statement_line_evidence(q, primary, []))
    if not metrics and not statement_hint and not any(x in q for x in broad_terms):
        return {
            "status": "AMBIGUOUS",
            "message": "Pertanyaan masih ambigu. Sebutkan metrik atau informasi yang ingin dilihat, misalnya laba, aset, kredit, DPK, pendapatan, CKPN, NPL, atau target.",
        }

    comparison = _comparison_periods(q, primary)
    overview_requested = not metrics and any(x in q for x in broad_terms)
    evidence = {
        "source": "CSV simulation data via Python",
        "selected_period": primary,
        "selected_period_label": format_period_id(primary),
        "unit": UNIT,
        "requested_metrics": metrics or ["overview"],
        "current": _summary_evidence(primary, metrics=metrics, include_overview=overview_requested),
        "comparison": [],
    }

    for cp in comparison:
        if cp and cp in periods:
            current_ev = evidence["current"]["kpi"]
            comparison_ev = _summary_evidence(cp, metrics=metrics, include_overview=overview_requested)
            # Python calculates changes so the LLM only needs to explain them.
            changes = {}
            for key, current_value in current_ev.items():
                previous_value = comparison_ev["kpi"].get(key)
                if previous_value is None:
                    continue
                delta = float(current_value) - float(previous_value)
                changes[key] = {
                    "absolute": delta,
                    "percent": (delta / float(previous_value) * 100) if float(previous_value) != 0 else None,
                }
            comparison_ev["changes_vs_selected_period"] = changes
            evidence["comparison"].append(comparison_ev)

    statement_lines = _statement_line_evidence(q, primary, comparison)
    if statement_lines:
        evidence["statement_lines"] = statement_lines

    # P&L grouped evidence is supplied whenever the question concerns profit,
    # revenue, expense, income statement, or diagnosis of a profit movement.
    if any(x in q for x in [
        "laba", "profit", "pendapatan", "revenue", "beban", "biaya", "ckpn",
        "laba rugi", "income statement", "kenapa", "mengapa", "turun", "naik",
    ]):
        # For diagnosis/comparison, add only the P&L components needed to
        # explain the movement. A simple "berapa laba" does not need the full P&L.
        if any(x in q for x in ["kenapa", "mengapa", "turun", "naik", "bandingkan", "dibandingkan", "perubahan", "laba rugi", "income statement"]):
            evidence["income_statement_groups"] = _income_group_totals(primary)
            for cp in comparison:
                if cp and cp in periods:
                    current_groups = evidence["income_statement_groups"]
                    comparison_groups = _income_group_totals(cp)
                    group_changes = {}
                    for key, current_value in current_groups.items():
                        previous_value = comparison_groups.get(key)
                        if previous_value is None:
                            continue
                        delta = float(current_value) - float(previous_value)
                        group_changes[key] = {
                            "absolute": delta,
                            "percent": (delta / float(previous_value) * 100) if float(previous_value) != 0 else None,
                        }
                    evidence.setdefault("comparison_income_statement_groups", []).append({
                        "period": cp,
                        "values": comparison_groups,
                        "changes_vs_selected_period": group_changes,
                    })

    # Product aggregation is included only when the question asks about a
    # product/portfolio, preventing irrelevant data from entering the prompt.
    if not statement_lines and any(x in q for x in ["rincian kredit", "rincian pembiayaan", "produk kredit", "produk pembiayaan", "portfolio kredit", "portofolio kredit", "kpr", "loan"]):
        evidence["loan_products"] = agg(LOANS, primary, "product_type", "outstanding", "total_revenue").to_dict("records")
    if not statement_lines and any(x in q for x in ["rincian investasi", "produk investasi", "portfolio investasi", "portofolio investasi", "penempatan", "surat berharga"]):
        evidence["investment_products"] = agg(INVESTMENTS, primary, "investment_type", "investment_amount", "total_revenue").to_dict("records")
    if not statement_lines and any(x in q for x in ["rincian dpk", "rincian dana pihak ketiga", "produk dpk", "giro", "tabungan", "deposito"]):
        evidence["dpk_products"] = agg(DPK, primary, "product_type", "balance", "total_cost_bagi_hasil").to_dict("records")

    # Target evidence is included only when target/performance is requested.
    if "target" in q or "pencapaian" in q or "achievement" in q or "efisiensi" in q:
        target_df = _period_records(TARGETS, primary)
        if metrics:
            target_map = {
                "total_assets": "Total Asset",
                "total_credit": "Total Credit",
                "total_investment": "Total Investment",
                "total_dpk": "Total DPK",
                "total_other_funding": "Total Other Funding",
                "net_profit": "Net Profit",
                "revenue": "Total Revenue",
                "operating_expense": "Operating Expense",
                "npl_ratio": "NPL Ratio %",
                "ckpn_coverage": "CKPN Coverage %",
                "low_cost_funding": "Low Cost Funding %",
            }
            wanted = [target_map[m] for m in metrics if m in target_map]
            if wanted:
                target_df = target_df[target_df.metric.isin(wanted)]
        evidence["targets"] = target_df.to_dict("records")

    # If a comparison is requested but no valid comparison period exists, do
    # not let the model guess a benchmark.
    if any(x in q for x in ["bandingkan", "dibandingkan", "vs", "perubahan", "naik", "turun", "pertumbuhan"]):
        if not evidence["comparison"]:
            return {
                "status": "NO_DATA",
                "message": f"Data pembanding untuk periode {format_period_id(primary)} tidak tersedia.",
            }

    evidence["status"] = "READY"
    direct = _direct_answer(q, evidence)
    if direct:
        evidence["direct_answer"] = direct
    return evidence


def build_financial_context(p=None):
    """Backward-compatible context builder for non-AI consumers.

    New AI calls should use build_financial_evidence(question, p) instead.
    """
    ensure_data_fresh()
    p = resolve_period(p)
    return build_financial_evidence("ringkasan kinerja keuangan", p)

# Initial load
refresh_csv_data()


# Compatibility value: derived from the current CSV, never hardcoded.
LATEST_PERIOD = get_latest_period()
