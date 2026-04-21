"""10K Analyser - Streamlit web app.

What this file does, top to bottom:
  1. Build the sidebar (search box, years slider, $B/$M toggle)
  2. Resolve the user's query to a ticker (ticker OR company name)
  3. Download SEC data for that ticker and compute YoY / TTM / ratios
  4. Render the company header and the four big "TTM" metric cards
  5. Render the AI Key Insights panel (if a Groq API key is configured)
  6. Render five tabs: Income / Balance Sheet / Cash Flow / Ratios / Raw Data

The actual data-handling logic lives in three supporting files:
  sec_client.py   - downloads and caches SEC company facts
  extract.py      - turns raw XBRL into clean quarterly tables
  metrics.py      - computes YoY, TTM, and financial ratios
  charts.py       - builds Plotly figures
  ai_layer.py     - calls Groq Llama for plain-English insights
"""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

import styles
from ai_layer import get_key_insights, get_statement_commentary, summarize_df_for_llm
from charts import ratio_line_chart, trend_chart, ttm_chart, yoy_chart
from extract import build_all
from metrics import add_ttm, add_yoy, compute_ratios
from sec_client import fuzzy_resolve, get_company_facts, load_tickers_map, resolve_ticker


# =========================================================================== #
# 0. Page setup
# =========================================================================== #

st.set_page_config(
    page_title="10K Analyser",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
styles.inject()


# =========================================================================== #
# 1. Metric display order
# =========================================================================== #
# These lists control which metrics appear in each tab and the order they
# appear in. Each entry is (column_name, friendly_label).

INCOME_METRICS = [
    ("Revenue", "Revenue"),
    ("CostOfRevenue", "Cost of Revenue"),
    ("GrossProfit", "Gross Profit"),
    ("OperatingIncome", "Operating Income"),
    ("NetIncome", "Net Income"),
]

BALANCE_METRICS = [
    ("Assets", "Total Assets"),
    ("CurrentAssets", "Current Assets"),
    ("Liabilities", "Total Liabilities"),
    ("CurrentLiabilities", "Current Liabilities"),
    ("Equity", "Stockholders Equity"),
    ("Cash", "Cash & Equivalents"),
    ("LongTermDebt", "Long-Term Debt"),
    ("SharesOutstanding", "Shares Outstanding"),
]

CASHFLOW_METRICS = [
    ("OperatingCF", "Operating Cash Flow"),
    ("InvestingCF", "Investing Cash Flow"),
    ("FinancingCF", "Financing Cash Flow"),
    ("CapEx", "Capital Expenditure"),
    ("FCF", "Free Cash Flow"),
]

RATIO_METRICS_PCT = [
    ("GrossMargin", "Gross Margin"),
    ("OperatingMargin", "Operating Margin"),
    ("NetMargin", "Net Margin"),
    ("FCFMargin", "FCF Margin"),
    ("ROA", "Return on Assets"),
    ("ROE", "Return on Equity"),
]

RATIO_METRICS_ABS = [
    ("CurrentRatio", "Current Ratio"),
    ("DebtToEquity", "Debt / Equity"),
]

# Chart hover/modebar options, applied to every Plotly chart in the app.
CHART_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}


# =========================================================================== #
# 2. Small formatting helpers
# =========================================================================== #

def nice_company_name(raw_name: str) -> str:
    """SEC returns names like 'NVIDIA CORP'. Convert to 'Nvidia Corp' while
    leaving names that were already mixed-case alone."""
    if not raw_name:
        return raw_name

    letters = [c for c in raw_name if c.isalpha()]
    if not letters or not all(c.isupper() for c in letters):
        return raw_name

    fixes = {"Corp": "Corp", "Inc": "Inc", "Plc": "PLC", "Llc": "LLC", "Ltd": "Ltd"}
    result = raw_name.title()
    for wrong, right in fixes.items():
        result = re.sub(rf"\b{wrong}\b\.?", right, result)
    return result


def fmt_money(value, divisor: float, suffix: str) -> str:
    """Format a raw USD number as '$1.23B' (or '($1.23B)' for negatives)."""
    if value is None or pd.isna(value):
        return "—"
    scaled = value / divisor
    if scaled < 0:
        return f"(${-scaled:,.2f}{suffix})"
    return f"${scaled:,.2f}{suffix}"


def fmt_pct(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value * 100:.1f}%"


# =========================================================================== #
# 3. Sidebar: search + filters
# =========================================================================== #
# The sidebar is fully reactive. Typing a new search query re-resolves the
# ticker, and changing the years slider or the unit selector re-renders the
# page immediately. No "Load" button needed.

# Remember the currently loaded ticker across reruns
if "ticker" not in st.session_state:
    st.session_state["ticker"] = "AAPL"
    st.session_state["ticker_display"] = "Apple Inc."
    st.session_state["last_query"] = ""
    st.session_state["resolve_error"] = None

# Pre-load the tickers map in the background so the first search is instant
try:
    load_tickers_map()
except Exception:
    pass

with st.sidebar:
    st.markdown("### 10K Analyser")
    st.caption("SEC EDGAR · 10yr quarterly · YoY & TTM trends")
    st.markdown("---")

    st.markdown(
        '<div class="search-label">Search ticker or company name</div>',
        unsafe_allow_html=True,
    )
    query = st.text_input(
        "search_query",
        value="",
        placeholder="e.g. AAPL, apple, nvidia, johnson",
        label_visibility="collapsed",
        key="search_box",
    )
    st.caption("Type a ticker or company name and press **Enter**")
    years = st.slider("Years of history", 3, 15, 10)
    unit_choice = st.selectbox("Unit", ["$B", "$M"], index=0)

    if st.session_state["resolve_error"]:
        st.error(st.session_state["resolve_error"])

    st.caption(f"Currently loaded: **{st.session_state['ticker_display']}**")

    st.markdown("---")
    st.caption(
        "Data source: free SEC EDGAR XBRL company-facts API. "
        "No signup, no API key. US-listed companies only."
    )

# Convert the $B/$M toggle to a divisor and suffix used everywhere
unit_divisor = 1e9 if unit_choice == "$B" else 1e6
unit_suffix = unit_choice[-1]  # "B" or "M"


# Resolve the search query only when it actually changes (so moving the
# years slider doesn't re-trigger a ticker lookup)
if query.strip() and query != st.session_state["last_query"]:
    st.session_state["last_query"] = query
    try:
        match = fuzzy_resolve(query)
        tickers = load_tickers_map()

        # Look for the canonical (no-dash) ticker for this CIK
        canonical_ticker = None
        for ticker_key, info in tickers.items():
            if info["cik"] == match["cik"] and "-" not in ticker_key:
                canonical_ticker = ticker_key
                break
        if canonical_ticker is None:
            for ticker_key, info in tickers.items():
                if info["cik"] == match["cik"]:
                    canonical_ticker = ticker_key
                    break

        st.session_state["ticker"] = canonical_ticker or query.upper()
        st.session_state["ticker_display"] = match["name"]
        st.session_state["resolve_error"] = None
    except ValueError:
        st.session_state["resolve_error"] = (
            f"Couldn't find '{query}'. Try a US stock ticker like AAPL, "
            f"or a company name like 'apple' or 'microsoft'."
        )

ticker = st.session_state["ticker"]


# =========================================================================== #
# 4. Fetch data from SEC and compute derived columns
# =========================================================================== #

try:
    ticker_info = resolve_ticker(ticker)
except Exception:
    st.error(f"Couldn't find '{ticker}'. Try a US stock ticker like AAPL, or a company name like 'apple'.")
    st.stop()

with st.spinner(f"Loading SEC filings for {ticker}..."):
    try:
        facts = get_company_facts(ticker_info["cik"])
    except Exception:
        st.error("SEC didn't respond — check your internet connection and try again.")
        st.stop()

    statements = build_all(facts, years=years)
    income = statements["income"]
    balance = statements["balance"]
    cashflow = statements["cashflow"]

    # Compute Free Cash Flow = Operating CF - CapEx, so the chart has it too
    if "OperatingCF" in cashflow.columns:
        capex_values = cashflow["CapEx"].fillna(0) if "CapEx" in cashflow.columns else 0
        cashflow["FCF"] = cashflow["OperatingCF"] - capex_values

    # Add Year-over-Year % columns for every metric we'll chart
    for col in ("Revenue", "CostOfRevenue", "GrossProfit", "OperatingIncome", "NetIncome"):
        if col in income.columns:
            income = add_yoy(income, col)
    for col in ("Assets", "CurrentAssets", "Liabilities", "CurrentLiabilities", "Equity", "Cash", "LongTermDebt"):
        if col in balance.columns:
            balance = add_yoy(balance, col)
    for col in ("OperatingCF", "InvestingCF", "FinancingCF", "CapEx", "FCF"):
        if col in cashflow.columns:
            cashflow = add_yoy(cashflow, col)

    # Add Trailing-Twelve-Months columns (flow statements only -
    # a balance-sheet snapshot is already a point-in-time value)
    for col in ("Revenue", "CostOfRevenue", "GrossProfit", "OperatingIncome", "NetIncome"):
        if col in income.columns:
            income = add_ttm(income, col)
    for col in ("OperatingCF", "InvestingCF", "FinancingCF", "CapEx", "FCF"):
        if col in cashflow.columns:
            cashflow = add_ttm(cashflow, col)

    # Compute ratios from the raw statements (before YoY/TTM columns were added)
    ratios = compute_ratios(statements["income"], statements["balance"], statements["cashflow"])


# =========================================================================== #
# 5. Company info — sidebar card (always visible) + main area header
# =========================================================================== #

display_name = nice_company_name(facts.get("entityName") or ticker_info["name"])
industry = facts.get("sicDescription", "")
latest_filing_date = income["end"].max().strftime("%Y-%m-%d") if not income.empty else "n/a"

welcome_hint = ""
if st.session_state.get("last_query", "") == "":
    welcome_hint = '<div style="color:#94A3B8;font-size:13px;margin-top:6px">Search any US-listed company in the sidebar to explore 10 years of quarterly financials.</div>'

st.markdown(
    f"""
    <div class="company-header">
      <span class="company-name">{display_name}</span><span class="company-ticker">{ticker}</span>
      <div class="company-sub">{industry or 'Unknown industry'} · CIK {ticker_info['cik']} · Latest filing {latest_filing_date}</div>
      {welcome_hint}
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================================== #
# 6. AI Key Insights panel (top of page, powered by Groq)
# =========================================================================== #

if not income.empty:
    ai_summaries = {
        "income": summarize_df_for_llm(income, ["Revenue", "GrossProfit", "OperatingIncome", "NetIncome"]),
        "balance": summarize_df_for_llm(balance, ["Assets", "Equity", "Cash", "LongTermDebt"]) if not balance.empty else {},
        "cashflow": summarize_df_for_llm(cashflow, ["OperatingCF", "FCF"]) if not cashflow.empty else {},
    }
    bullets = get_key_insights(ticker, ai_summaries)

    html_parts = ['<div class="card"><h3>✨ AI Key Insights</h3>']
    if bullets:
        for bullet in bullets:
            clean = bullet.lstrip("•-* ").strip()
            if clean:
                html_parts.append(
                    f'<div class="insight-bullet"><span class="insight-dot">●</span>{clean}</div>'
                )
    else:
        html_parts.append(
            '<div class="placeholder">AI insights are available when you add a free Groq API key. '
            "See the README for setup instructions (takes 2 minutes). "
            "Charts and data work fine without it.</div>"
        )
    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)


# =========================================================================== #
# 7. TTM metric cards (the four headline numbers under the header)
# =========================================================================== #

def latest_ttm(df: pd.DataFrame, col: str) -> tuple:
    """Return (latest TTM value, YoY% of that TTM) for a column, or (None, None)."""
    ttm_col = f"{col}_ttm"
    yoy_col = f"{col}_ttm_yoy"
    if df.empty or ttm_col not in df.columns:
        return None, None
    non_empty = df.dropna(subset=[ttm_col])
    if non_empty.empty:
        return None, None
    latest_row = non_empty.iloc[-1]
    return latest_row.get(ttm_col), latest_row.get(yoy_col)


def metric_card_html(label: str, value, yoy) -> str:
    """Render one big headline metric card as HTML."""
    value_text = fmt_money(value, unit_divisor, unit_suffix)
    if value is None or pd.isna(value):
        value_text = '<span style="color:#475569">Not reported</span>'
    delta_html = ""
    if pd.notna(yoy):
        is_positive = yoy >= 0
        cls = "metric-delta metric-delta-pos" if is_positive else "metric-delta metric-delta-neg"
        arrow = "▲" if is_positive else "▼"
        delta_html = f'<div class="{cls}">{arrow} {yoy * 100:+.1f}% YoY</div>'
    return (
        f'<div class="metric-card">'
        f'<div class="metric-label">{label} <span style="color:#475569">· trailing 12 months</span></div>'
        f'<div class="metric-value">{value_text}</div>'
        f"{delta_html}"
        f"</div>"
    )


if not income.empty:
    revenue_ttm, revenue_yoy = latest_ttm(income, "Revenue")
    netinc_ttm, netinc_yoy = latest_ttm(income, "NetIncome")
    opinc_ttm, opinc_yoy = latest_ttm(income, "OperatingIncome")
    fcf_ttm, fcf_yoy = (None, None)
    if not cashflow.empty:
        fcf_ttm, fcf_yoy = latest_ttm(cashflow, "FCF")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(metric_card_html("Revenue", revenue_ttm, revenue_yoy), unsafe_allow_html=True)
    with col2:
        st.markdown(metric_card_html("Net Income", netinc_ttm, netinc_yoy), unsafe_allow_html=True)
    with col3:
        st.markdown(metric_card_html("Operating Inc.", opinc_ttm, opinc_yoy), unsafe_allow_html=True)
    with col4:
        st.markdown(metric_card_html("Free Cash Flow", fcf_ttm, fcf_yoy), unsafe_allow_html=True)
    st.write("")


# =========================================================================== #
# 8. Tab rendering helpers
# =========================================================================== #

def empty_chart_placeholder(message: str = "No data reported for this metric"):
    """Draw a dashed box instead of an empty chart frame."""
    st.markdown(
        f'<div style="padding:32px 12px;text-align:center;color:#475569;'
        f'background:#0F1421;border:1px dashed #1E293B;border-radius:10px;'
        f'font-size:12px;margin-bottom:12px">{message}</div>',
        unsafe_allow_html=True,
    )


def draw_metric_block(df: pd.DataFrame, col: str, label: str, show_ttm: bool):
    """Draw the chart stack for one metric: header, trend bars, YoY, TTM."""
    st.markdown(f'<div class="chart-header">{label}</div>', unsafe_allow_html=True)

    if col not in df.columns or df[col].dropna().empty:
        empty_chart_placeholder(f"{label} is not reported by this company")
        return

    # 1. Quarterly trend bars
    trend_fig = trend_chart(df, col, unit_divisor, unit_suffix)
    if trend_fig:
        st.plotly_chart(trend_fig, width="stretch", config=CHART_CONFIG)

    # 2. YoY % change bars
    st.markdown(
        '<div class="chart-sublabel">'
        '<abbr class="tip" title="Year-over-Year: this quarter compared to the same quarter one year ago">YoY</abbr>'
        ' % change (same quarter vs one year ago)</div>',
        unsafe_allow_html=True,
    )
    yoy_fig = yoy_chart(df, col)
    if yoy_fig:
        st.plotly_chart(yoy_fig, width="stretch", config=CHART_CONFIG)
    else:
        empty_chart_placeholder("Need ≥5 quarters of data for YoY")

    # 3. TTM area line (flow statements only)
    if show_ttm:
        st.markdown(
            '<div class="chart-sublabel">'
            '<abbr class="tip" title="Trailing Twelve Months: sum of the last 4 quarters, giving an annualized view">TTM</abbr>'
            ' (trailing twelve months)</div>',
            unsafe_allow_html=True,
        )
        ttm_fig = ttm_chart(df, col, unit_divisor, unit_suffix)
        if ttm_fig:
            st.plotly_chart(ttm_fig, width="stretch", config=CHART_CONFIG)
        else:
            empty_chart_placeholder("Need ≥4 quarters of data for TTM")


def draw_chart_grid(df: pd.DataFrame, metrics: list[tuple[str, str]], show_ttm: bool):
    """Arrange metric blocks in a responsive 2-column grid."""
    present = [(c, l) for c, l in metrics if c in df.columns and df[c].notna().any()]
    if not present:
        st.info(
            "This company doesn't report the standard GAAP concepts for this "
            "statement. Check the Raw Data tab for whatever IS reported."
        )
        return

    for i in range(0, len(present), 2):
        columns = st.columns(2, gap="large")
        for j, (col, label) in enumerate(present[i : i + 2]):
            with columns[j]:
                draw_metric_block(df, col, label, show_ttm)


def draw_ai_commentary(ticker: str, statement: str, summary: dict):
    """If Groq is configured, show its 2-3 sentence commentary for this statement."""
    text = get_statement_commentary(ticker, statement, summary)
    if text:
        st.markdown(
            f'<div class="ai-commentary"><span class="ai-tag">🤖 AI Trend</span>{text}</div>',
            unsafe_allow_html=True,
        )


# =========================================================================== #
# 9. Pivot table helper (for the "Show table" expanders and Raw Data tab)
# =========================================================================== #

def pivot_statement_html(
    df: pd.DataFrame,
    metrics: list[tuple[str, str]],
    title: str,
    mode: str = "money",
    divisor: float = 1e9,
    suffix: str = "B",
) -> str:
    """Render a statement in the classic finance layout: metrics down the
    left, newest period on the left of the period columns."""
    empty_shell = (
        f'<div class="stmt-wrap"><div class="stmt-title">{title}</div>'
        f'<div style="padding:18px;color:#64748B">No data</div></div>'
    )
    if df is None or df.empty:
        return empty_shell

    # Newest period on the LEFT (user preference)
    sorted_df = df.sort_values("end", ascending=False).copy()
    sorted_df["period"] = sorted_df.apply(
        lambda r: f"FY{int(r['fy'])} {r['fp']}" if pd.notna(r.get("fy")) else str(r.get("fp", "")),
        axis=1,
    )

    present = [(c, lbl) for c, lbl in metrics if c in sorted_df.columns]
    if not present:
        return empty_shell

    # Build the table header
    period_headers = "".join(f"<th>{p}</th>" for p in sorted_df["period"].tolist())
    header_html = f"<thead><tr><th>Metric</th>{period_headers}</tr></thead>"

    # Build one row per metric
    body_rows = []
    for col, label in present:
        cell_html = []
        for value in sorted_df[col].tolist():
            if value is None or pd.isna(value):
                cell_html.append('<td class="muted">—</td>')
                continue
            if mode == "money":
                text = fmt_money(value, divisor, suffix)
                css = "neg" if value < 0 else ""
            elif mode == "pct":
                text = fmt_pct(value)
                css = "pos" if value >= 0 else "neg"
            else:  # plain number (e.g. Current Ratio 1.06x, Debt/Equity 0.87x)
                text = f"{value:,.2f}x"
                css = ""
            cell_html.append(f'<td class="{css}">{text}</td>')
        body_rows.append(f"<tr><td>{label}</td>{''.join(cell_html)}</tr>")

    body_html = f"<tbody>{''.join(body_rows)}</tbody>"
    return (
        f'<div class="stmt-wrap">'
        f'<div class="stmt-title">{title}</div>'
        f'<table class="stmt-table">{header_html}{body_html}</table>'
        f"</div>"
    )


# =========================================================================== #
# 10. Render the five tabs
# =========================================================================== #

tab_income, tab_balance, tab_cashflow, tab_ratios, tab_raw = st.tabs(
    ["📈  Income", "🏦  Balance Sheet", "💵  Cash Flow", "📊  Ratios", "🗂  Raw Data"]
)


# --- Income Statement ------------------------------------------------------- #
with tab_income:
    if income.empty:
        st.info("No income statement data available.")
    else:
        draw_ai_commentary(
            ticker,
            "income statement",
            summarize_df_for_llm(income, ["Revenue", "GrossProfit", "OperatingIncome", "NetIncome"]),
        )
        draw_chart_grid(
            income,
            [
                ("Revenue", "Revenue"),
                ("GrossProfit", "Gross Profit"),
                ("OperatingIncome", "Operating Income"),
                ("NetIncome", "Net Income"),
            ],
            show_ttm=True,
        )
        with st.expander("Show income statement table"):
            st.markdown(
                pivot_statement_html(income, INCOME_METRICS, "Income Statement", "money", unit_divisor, unit_suffix),
                unsafe_allow_html=True,
            )


# --- Balance Sheet ---------------------------------------------------------- #
with tab_balance:
    if balance.empty:
        st.info("No balance sheet data available.")
    else:
        draw_ai_commentary(
            ticker,
            "balance sheet",
            summarize_df_for_llm(balance, ["Assets", "Equity", "Cash", "LongTermDebt"]),
        )
        draw_chart_grid(
            balance,
            [
                ("Assets", "Total Assets"),
                ("Equity", "Stockholders Equity"),
                ("Cash", "Cash & Equivalents"),
                ("LongTermDebt", "Long-Term Debt"),
            ],
            show_ttm=False,  # TTM doesn't apply to balance-sheet snapshots
        )
        with st.expander("Show balance sheet table"):
            st.markdown(
                pivot_statement_html(balance, BALANCE_METRICS, "Balance Sheet", "money", unit_divisor, unit_suffix),
                unsafe_allow_html=True,
            )


# --- Cash Flow Statement ---------------------------------------------------- #
with tab_cashflow:
    if cashflow.empty:
        st.info("No cash flow data available.")
    else:
        draw_ai_commentary(
            ticker,
            "cash flow statement",
            summarize_df_for_llm(cashflow, ["OperatingCF", "FCF", "InvestingCF", "FinancingCF"]),
        )
        draw_chart_grid(
            cashflow,
            [
                ("OperatingCF", "Operating Cash Flow"),
                ("FCF", "Free Cash Flow"),
                ("InvestingCF", "Investing Cash Flow"),
                ("FinancingCF", "Financing Cash Flow"),
            ],
            show_ttm=True,
        )
        with st.expander("Show cash flow table"):
            st.markdown(
                pivot_statement_html(cashflow, CASHFLOW_METRICS, "Cash Flow Statement", "money", unit_divisor, unit_suffix),
                unsafe_allow_html=True,
            )


# --- Ratios ----------------------------------------------------------------- #
with tab_ratios:
    if ratios.empty:
        st.info("Insufficient data to compute ratios.")
    else:
        # Percent-style ratios first (margins, returns)
        for i in range(0, len(RATIO_METRICS_PCT), 2):
            columns = st.columns(2, gap="large")
            for j, (col, label) in enumerate(RATIO_METRICS_PCT[i : i + 2]):
                if col not in ratios.columns:
                    continue
                with columns[j]:
                    st.markdown(f'<div class="chart-header">{label}</div>', unsafe_allow_html=True)
                    fig = ratio_line_chart(ratios, col, is_pct=True)
                    if fig:
                        st.plotly_chart(fig, width="stretch", config=CHART_CONFIG)

        # Absolute-number ratios (current ratio, debt/equity)
        columns = st.columns(2, gap="large")
        for j, (col, label) in enumerate(RATIO_METRICS_ABS):
            if col not in ratios.columns:
                continue
            with columns[j]:
                st.markdown(f'<div class="chart-header">{label}</div>', unsafe_allow_html=True)
                fig = ratio_line_chart(ratios, col, is_pct=False)
                if fig:
                    st.plotly_chart(fig, width="stretch", config=CHART_CONFIG)

        with st.expander("Show ratios table"):
            st.markdown(
                pivot_statement_html(ratios, RATIO_METRICS_PCT, "Margins & Returns", "pct"),
                unsafe_allow_html=True,
            )
            st.markdown(
                pivot_statement_html(ratios, RATIO_METRICS_ABS, "Liquidity & Leverage", "number"),
                unsafe_allow_html=True,
            )


# --- Raw Data --------------------------------------------------------------- #
with tab_raw:
    show_ttm = st.toggle("Show annualized (trailing 12 months) instead of single quarters", value=False)

    def replace_with_ttm(df: pd.DataFrame, metric_keys: list[str]) -> pd.DataFrame:
        """Build a view where each metric column is replaced by its TTM column."""
        if df.empty:
            return df
        view = df[["end", "fy", "fp"]].copy()
        for key in metric_keys:
            ttm_col = f"{key}_ttm"
            if ttm_col in df.columns:
                view[key] = df[ttm_col]
        return view

    if show_ttm:
        income_view = replace_with_ttm(income, [c for c, _ in INCOME_METRICS])
        cashflow_view = replace_with_ttm(cashflow, [c for c, _ in CASHFLOW_METRICS])
        balance_view = balance  # TTM not meaningful for balance sheet
        ratios_view = ratios    # TTM not meaningful for ratios
    else:
        income_view, balance_view, cashflow_view, ratios_view = income, balance, cashflow, ratios

    st.markdown(
        pivot_statement_html(income_view, INCOME_METRICS, "Income Statement", "money", unit_divisor, unit_suffix),
        unsafe_allow_html=True,
    )
    st.markdown(
        pivot_statement_html(balance_view, BALANCE_METRICS, "Balance Sheet", "money", unit_divisor, unit_suffix),
        unsafe_allow_html=True,
    )
    st.markdown(
        pivot_statement_html(cashflow_view, CASHFLOW_METRICS, "Cash Flow Statement", "money", unit_divisor, unit_suffix),
        unsafe_allow_html=True,
    )
    st.markdown(
        pivot_statement_html(ratios_view, RATIO_METRICS_PCT, "Margins & Returns", "pct"),
        unsafe_allow_html=True,
    )
    st.markdown(
        pivot_statement_html(ratios_view, RATIO_METRICS_ABS, "Liquidity & Leverage", "number"),
        unsafe_allow_html=True,
    )

    # Downloads — one Excel file with a separate sheet per statement,
    # plus individual CSV buttons if someone just needs one table.
    st.markdown("---")
    st.markdown('<div class="chart-header">Downloads</div>', unsafe_allow_html=True)

    # Excel file with multiple sheets
    from io import BytesIO
    excel_buffer = BytesIO()
    sheet_data = [
        ("Income Statement", income_view, INCOME_METRICS),
        ("Balance Sheet", balance_view, BALANCE_METRICS),
        ("Cash Flow", cashflow_view, CASHFLOW_METRICS),
        ("Ratios", ratios_view, RATIO_METRICS_PCT + RATIO_METRICS_ABS),
    ]
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        for sheet_name, df, metrics in sheet_data:
            if df is None or df.empty:
                continue
            # Build a clean export: only the metric columns we display, with
            # a readable period label and friendly column names.
            export = df.sort_values("end", ascending=False).copy()
            export["Period"] = export.apply(
                lambda r: f"FY{int(r['fy'])} {r['fp']}" if pd.notna(r.get("fy")) else "",
                axis=1,
            )
            cols_to_export = ["Period"]
            rename_map = {}
            for col_key, col_label in metrics:
                if col_key in export.columns:
                    cols_to_export.append(col_key)
                    rename_map[col_key] = col_label
            export = export[cols_to_export].rename(columns=rename_map)
            export.to_excel(writer, sheet_name=sheet_name, index=False)
    excel_buffer.seek(0)

    col_xl, col_csv1, col_csv2, col_csv3, col_csv4 = st.columns(5)
    with col_xl:
        st.download_button(
            "📊 Excel (all sheets)",
            excel_buffer.getvalue(),
            file_name=f"{ticker}_financials.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with col_csv1:
        if not income_view.empty:
            st.download_button("📈 Income CSV", income_view.to_csv(index=False), file_name=f"{ticker}_income.csv", mime="text/csv")
    with col_csv2:
        if not balance_view.empty:
            st.download_button("🏦 Balance CSV", balance_view.to_csv(index=False), file_name=f"{ticker}_balance.csv", mime="text/csv")
    with col_csv3:
        if not cashflow_view.empty:
            st.download_button("💵 Cash Flow CSV", cashflow_view.to_csv(index=False), file_name=f"{ticker}_cashflow.csv", mime="text/csv")
    with col_csv4:
        if not ratios_view.empty:
            st.download_button("📊 Ratios CSV", ratios_view.to_csv(index=False), file_name=f"{ticker}_ratios.csv", mime="text/csv")
