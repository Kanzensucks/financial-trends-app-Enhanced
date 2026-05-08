"""
valuation.py — Valuation tab for 10K Analyser.
Contains: CSV logger, yfinance fetcher, DCF calculator, and render_valuation_tab.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOG_PATH = str(Path(__file__).parent / "data" / "valuation_log.csv")

CSV_HEADER = [
    "timestamp",
    "ticker",
    "method",
    "fair_value",
    "current_price",
    "verdict",
    "analyst_target",
    "analyst_verdict",
    "discount_rate",
]


# ---------------------------------------------------------------------------
# CSV logger helpers
# ---------------------------------------------------------------------------


def _ensure_log() -> None:
    """Create data/ directory and write CSV header if the file is empty or missing."""
    global LOG_PATH
    try:
        Path(LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        import tempfile
        LOG_PATH = str(Path(tempfile.gettempdir()) / "valuation_log.csv")
    path = Path(LOG_PATH)
    if not path.exists() or path.stat().st_size == 0:
        with open(LOG_PATH, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADER)


def _analyst_verdict(analyst_target: Optional[float], current_price: Optional[float]) -> str:
    """Derive a simple analyst verdict from consensus target vs live price."""
    if analyst_target is None or current_price is None or current_price == 0:
        return "MISSING"
    ratio = analyst_target / current_price
    if ratio > 1.10:
        return "UNDER"
    if ratio < 0.90:
        return "OVER"
    return "FAIR"


def log_run(
    ticker: str,
    method: str,
    fair_value: float,
    current_price: float,
    verdict: str,
    analyst_target: Optional[float] = None,
    discount_rate: Optional[float] = None,
) -> None:
    """Append one row to the valuation log CSV."""
    _ensure_log()
    av = _analyst_verdict(analyst_target, current_price)
    row = [
        datetime.now(timezone.utc).isoformat(),
        ticker,
        method,
        fair_value,
        current_price,
        verdict,
        analyst_target if analyst_target is not None else "",
        av,
        discount_rate if discount_rate is not None else "",
    ]
    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(row)


# ---------------------------------------------------------------------------
# yfinance data fetcher
# ---------------------------------------------------------------------------


@st.cache_data(ttl=600)
def _fetch_yf(ticker: str) -> dict:
    """
    Fetch live market data from yfinance.
    Returns a dict with keys:
        live_price, analyst_target, shares_outstanding, net_debt, fcf_history
    Never raises — missing values are returned as None.
    """
    result = {
        "live_price": None,
        "analyst_target": None,
        "analyst_low": None,
        "analyst_high": None,
        "analyst_count": None,
        "shares_outstanding": None,
        "net_debt": None,
        "fcf_history": [],
    }
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info

        result["live_price"] = info.get("currentPrice") or info.get("regularMarketPrice")
        result["analyst_target"] = info.get("targetMeanPrice")
        result["analyst_low"] = info.get("targetLowPrice")
        result["analyst_high"] = info.get("targetHighPrice")
        result["analyst_count"] = info.get("numberOfAnalystOpinions")
        result["shares_outstanding"] = info.get("sharesOutstanding")

        total_debt = info.get("totalDebt") or 0
        cash = info.get("totalCash") or 0
        result["net_debt"] = total_debt - cash

        cf = yf.Ticker(ticker).cashflow
        if cf is not None and not cf.empty:
            fcf_row = None
            for label in ["Free Cash Flow", "FreeCashFlow"]:
                if label in cf.index:
                    fcf_row = cf.loc[label]
                    break
            if fcf_row is None:
                op_cf = cf.loc["Operating Cash Flow"] if "Operating Cash Flow" in cf.index else None
                capex = cf.loc["Capital Expenditure"] if "Capital Expenditure" in cf.index else None
                if op_cf is not None and capex is not None:
                    fcf_row = op_cf + capex
            if fcf_row is not None:
                result["fcf_history"] = [float(v) for v in fcf_row.dropna().values[:5]]
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Groq AI client + DCF explainer
# ---------------------------------------------------------------------------


def _groq_client():
    """Return a Groq client if an API key is available, else None."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets.get("GROQ_API_KEY") or None
        except Exception:
            api_key = None
    if not api_key:
        return None
    try:
        from groq import Groq
        return Groq(api_key=api_key)
    except Exception:
        return None


@st.cache_data(ttl=3600)
def _explain_dcf_cached(
    api_key: str,
    ticker: str,
    fair_value: float,
    current_price: float,
    verdict: str,
    discount_rate: float,
) -> Optional[str]:
    """Cached inner call — api_key passed explicitly so st.secrets is not accessed inside."""
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        prompt = (
            f"You are a finance tutor. In exactly 2-3 short sentences, explain what this DCF "
            f"valuation means for {ticker}. "
            f"Fair value: ${fair_value:.2f}. Current price: ${current_price:.2f}. "
            f"Verdict: {verdict}. Discount rate: {discount_rate:.1%}. "
            f"Be concise. No jargon. One brief caveat about DCF reliability. "
            f"No buy/sell recommendation. Do not exceed 100 words total."
        )
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return None


def explain_dcf(
    ticker: str,
    fair_value: float,
    current_price: float,
    verdict: str,
    discount_rate: float,
) -> Optional[str]:
    """
    Ask Groq Llama to explain the DCF result in plain English.
    Resolves the API key outside the cache boundary, then delegates to the
    cached inner function. Returns None silently if no key or call fails.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets.get("GROQ_API_KEY") or None
        except Exception:
            api_key = None
    if not api_key:
        return None
    return _explain_dcf_cached(api_key, ticker, fair_value, current_price, verdict, discount_rate)


# ---------------------------------------------------------------------------
# DCF calculator
# ---------------------------------------------------------------------------


def calculate_dcf(
    fcf_history: list,
    shares_outstanding: float,
    net_debt: float,
    discount_rate: float,
    terminal_growth: float,
    years_projected: int,
    growth_y1_3: float,
    growth_y4_5: float,
) -> dict:
    """
    Discounted Cash Flow valuation.

    Args:
        fcf_history:        Historical FCF values, most recent first.
        shares_outstanding: Total shares outstanding.
        net_debt:           Total debt minus cash.
        discount_rate:      WACC / required rate of return (decimal, e.g. 0.10).
        terminal_growth:    Perpetuity growth rate (decimal, e.g. 0.025).
        years_projected:    Number of years to project (3-10).
        growth_y1_3:        FCF growth rate for years 1-3 (decimal).
        growth_y4_5:        FCF growth rate for years 4+ (decimal).

    Returns:
        dict with keys: fair_value, projected_fcfs, terminal_value, present_values.

    Raises:
        ValueError: if discount_rate <= terminal_growth.
    """
    if discount_rate <= terminal_growth:
        raise ValueError(
            f"Discount rate ({discount_rate:.1%}) must be greater than "
            f"terminal growth rate ({terminal_growth:.1%})."
        )

    base_fcf = fcf_history[0]

    projected_fcfs: list = []
    for year in range(1, years_projected + 1):
        growth = growth_y1_3 if year <= 3 else growth_y4_5
        if year == 1:
            fcf = base_fcf * (1 + growth)
        else:
            fcf = projected_fcfs[-1] * (1 + growth)
        projected_fcfs.append(fcf)

    present_values: list = []
    for year, fcf in enumerate(projected_fcfs, start=1):
        pv = fcf / (1 + discount_rate) ** year
        present_values.append(pv)

    fcf_final = projected_fcfs[-1]
    terminal_value = fcf_final * (1 + terminal_growth) / (discount_rate - terminal_growth)
    pv_terminal = terminal_value / (1 + discount_rate) ** years_projected

    enterprise_value = sum(present_values) + pv_terminal
    equity_value = enterprise_value - net_debt
    fair_value = equity_value / shares_outstanding

    return {
        "fair_value": fair_value,
        "projected_fcfs": projected_fcfs,
        "terminal_value": terminal_value,
        "present_values": present_values,
    }


def _dcf_sensitivity_chart(
    fcf_history: list,
    shares_outstanding: float,
    net_debt: float,
    terminal_growth: float,
    years_projected: int,
    growth_y1_3: float,
    growth_y4_5: float,
    current_price: float,
) -> go.Figure:
    """Plotly line chart of DCF fair value as discount rate sweeps 5%-15%."""
    rates = [r / 100 for r in range(5, 16)]
    fair_values = []
    for r in rates:
        try:
            result = calculate_dcf(
                fcf_history, shares_outstanding, net_debt,
                r, terminal_growth, years_projected, growth_y1_3, growth_y4_5,
            )
            fair_values.append(result["fair_value"])
        except ValueError:
            fair_values.append(None)

    rate_labels = [f"{int(r * 100)}%" for r in rates]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=rate_labels,
        y=fair_values,
        mode="lines+markers",
        name="DCF Fair Value",
        line=dict(color="#38BDF8", width=2),
        marker=dict(size=7, color="#38BDF8"),
    ))

    fig.add_hline(
        y=current_price,
        line_dash="dash",
        line_color="#F87171",
        annotation_text=f"Current price  ${current_price:,.2f}",
        annotation_position="top left",
        annotation_font_color="#F87171",
    )

    fig.update_layout(
        title="Sensitivity: DCF Fair Value vs Discount Rate",
        xaxis_title="Discount Rate (WACC)",
        yaxis_title="Fair Value per Share (USD)",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#CBD5E1"),
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(gridcolor="#1E293B", tickprefix="$"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        margin=dict(t=50, b=40, l=60, r=20),
    )

    return fig


# ---------------------------------------------------------------------------
# Valuation tab renderer
# ---------------------------------------------------------------------------


def render_valuation_tab(
    ticker: str,
    company_name: str,
    financials_dict: dict,
) -> None:
    """
    Render the Valuation tab inside the 10K Analyser dashboard.

    Args:
        ticker:          Exchange ticker symbol (e.g. "AAPL").
        company_name:    Human-readable company name for display.
        financials_dict: The financial data dict already loaded by the app.
    """
    _start_eval_if_due()
    st.subheader(f"Valuation — {company_name} ({ticker.upper()})")

    # ------------------------------------------------------------------
    # Fetch live data
    # ------------------------------------------------------------------
    with st.spinner("Fetching live market data…"):
        yf_data = _fetch_yf(ticker)

    # Guard: invalid ticker — show nothing
    if yf_data["live_price"] is None and yf_data["analyst_target"] is None:
        st.warning("⚠️ Please enter a valid US stock ticker in the sidebar (e.g. AAPL, MSFT, NVDA).")
        return

    live_price: Optional[float] = yf_data["live_price"]
    analyst_target: Optional[float] = yf_data["analyst_target"]
    analyst_count: Optional[int] = yf_data["analyst_count"]
    shares_outstanding: Optional[float] = yf_data["shares_outstanding"]
    net_debt: float = yf_data["net_debt"] or 0.0
    fcf_history: list = yf_data["fcf_history"] or []

    # ------------------------------------------------------------------
    # Banner: live price + analyst consensus
    # ------------------------------------------------------------------
    price_str = f"${live_price:,.2f}" if live_price else "—"

    if analyst_target and live_price:
        upside_pct = (analyst_target / live_price - 1) * 100
        sign = "+" if upside_pct >= 0 else ""
        target_str = f"${analyst_target:,.2f} ({sign}{upside_pct:.1f}% upside)"
    elif analyst_target:
        target_str = f"${analyst_target:,.2f}"
    else:
        target_str = "—"

    # Upside colour: green if positive, red if negative
    if analyst_target and live_price:
        upside_color = "#4ADE80" if upside_pct >= 0 else "#F87171"
        upside_html = f'<span style="color:{upside_color};font-weight:600">{sign}{upside_pct:.1f}%</span>'
        target_display = f'${analyst_target:,.2f} <span style="font-size:12px;color:#94A3B8">({upside_html} upside)</span>'
    else:
        target_display = '<span style="color:#475569">—</span>'

    # Build tooltip text using real data — no guessing
    analyst_count_str = f"{int(analyst_count)} analysts" if analyst_count else "analyst count unavailable"
    consensus_tip = f"Yahoo Finance&#10;{analyst_count_str}"
    verdict_tip   = f"Yahoo Finance&#10;{analyst_count_str}"

    st.markdown(
        f'''<div style="display:flex;gap:0;margin-bottom:8px">
          <div style="flex:1;background:#0F1C2E;border:1px solid #1E3A5F;border-radius:10px 0 0 10px;
                      padding:16px 24px">
            <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;
                        color:#38BDF8;margin-bottom:4px">Live Price</div>
            <div style="font-size:26px;font-weight:700;color:#F1F5F9">{price_str}</div>
          </div>
          <div style="flex:1;background:#0F1C2E;border:1px solid #1E3A5F;border-left:none;border-radius:0;
                      padding:16px 24px">
            <div style="display:flex;align-items:center;gap:6px;font-size:11px;
                        text-transform:uppercase;letter-spacing:1px;color:#38BDF8;margin-bottom:4px">
              Analyst Consensus
              <span class="banner-tip" data-tip="{consensus_tip}" style="
                display:inline-flex;align-items:center;justify-content:center;
                width:14px;height:14px;border-radius:50%;border:1.5px solid #475569;
                color:#475569;font-size:9px;font-weight:700;cursor:default;flex-shrink:0;">i</span>
            </div>
            <div style="font-size:26px;font-weight:700;color:#F1F5F9">{target_display}</div>
          </div>
          <div style="flex:1;background:#0F1C2E;border:1px solid #1E3A5F;border-left:none;border-radius:0 10px 10px 0;
                      padding:16px 24px">
            <div style="display:flex;align-items:center;gap:6px;font-size:11px;
                        text-transform:uppercase;letter-spacing:1px;color:#38BDF8;margin-bottom:4px">
              Analyst Verdict
              <span class="banner-tip" data-tip="{verdict_tip}" style="
                display:inline-flex;align-items:center;justify-content:center;
                width:14px;height:14px;border-radius:50%;border:1.5px solid #475569;
                color:#475569;font-size:9px;font-weight:700;cursor:default;flex-shrink:0;">i</span>
            </div>
            <div style="font-size:20px;font-weight:700;color:#F1F5F9">{
                "🟢 Undervalued" if analyst_target and live_price and analyst_target > live_price * 1.10
                else "🔴 Overvalued" if analyst_target and live_price and analyst_target < live_price * 0.90
                else "🟡 Fairly Valued" if analyst_target and live_price
                else "— No Data"
            }</div>
          </div>
        </div>
        <style>
          .banner-tip {{ position:relative; }}
          .banner-tip:hover {{ border-color:#38BDF8 !important; color:#38BDF8 !important; }}
          .banner-tip:hover::after {{
            content: attr(data-tip);
            position: absolute;
            left: 20px; top: -4px;
            background: #0F1C2E;
            color: #CBD5E1;
            border: 1px solid #38BDF8;
            border-radius: 8px;
            padding: 10px 14px;
            font-size: 12px;
            font-weight: 400;
            line-height: 1.6;
            white-space: pre;
            width: auto;
            z-index: 9999;
            box-shadow: 0 8px 24px rgba(0,0,0,0.7);
          }}
        </style>''',
        unsafe_allow_html=True,
    )

    st.divider()

    # ------------------------------------------------------------------
    # DCF assumption sliders
    # ------------------------------------------------------------------
    st.markdown("#### DCF Assumptions")

    def _info_tooltip(slider_label: str, text: str) -> str:
        """Return a slider label string with an inline ⓘ tooltip icon."""
        return slider_label  # label passed to st.slider directly — tooltip injected separately

    def _hint(label: str, text: str) -> None:
        """Inject an ⓘ icon tooltip — call BEFORE the slider so it renders inline with label."""
        pass  # replaced by _slider_with_tip below

    def _slider_with_tip(label: str, tip: str, **kwargs):
        """Render a slider label with an ⓘ circle tooltip icon beside it."""
        st.markdown(
            f'''<div style="display:flex;align-items:center;gap:6px;
                             margin-bottom:4px;font-size:14px;color:#FAFAFA;font-weight:400">
              {label}
              <span class="dcf-info-tip" data-tip="{tip}" style="
                display:inline-flex;align-items:center;justify-content:center;
                width:15px;height:15px;border-radius:50%;
                border:1.5px solid #475569;color:#475569;
                font-size:9px;font-weight:700;cursor:default;
                flex-shrink:0;line-height:1;">i</span>
            </div>
            <style>
              .dcf-info-tip {{ position:relative; }}
              .dcf-info-tip:hover {{ border-color:#38BDF8 !important; color:#38BDF8 !important; }}
              .dcf-info-tip:hover::after {{
                content: attr(data-tip);
                position: absolute;
                left: 20px; top: -4px;
                background: #0F1C2E;
                color: #CBD5E1;
                border: 1px solid #38BDF8;
                border-radius: 8px;
                padding: 12px 16px;
                font-size: 12px;
                font-weight: 400;
                line-height: 1.6;
                white-space: normal;
                width: 300px;
                z-index: 9999;
                box-shadow: 0 8px 24px rgba(0,0,0,0.7);
              }}
            </style>''',
            unsafe_allow_html=True,
        )
        # Render the actual slider with an empty label (label already rendered above)
        return st.slider("​", **kwargs)

    stats = _fcf_growth_stats(fcf_history)
    has_stats = bool(stats)

    # Build hint strings based on actual historical data
    if has_stats:
        avg_pct      = stats["avg"] * 100
        recent_pct   = stats["recent"] * 100
        sug_near_pct = stats["suggested_near"] * 100
        sug_long_pct = stats["suggested_long"] * 100
        n            = stats["n_years"]
        g13_hint = (
            f"{ticker} historical FCF growth — "
            f"<b>{n}-yr avg: {avg_pct:+.1f}%</b>, "
            f"recent 2-yr: {recent_pct:+.1f}%. "
            f"Suggested: <b>{sug_near_pct:.1f}%</b>"
        )
        g45_hint = (
            f"Suggested long-run rate based on {ticker} history: "
            f"<b>{sug_long_pct:.1f}%</b>. "
            f"Should be lower than years 1–3 as growth tapers."
        )
    else:
        g13_hint = "Insufficient FCF history to compute a stock-specific recommendation. Typical range: 4–12%."
        g45_hint = "Typical range: 2–6%. Should be lower than years 1–3."

    col_left, col_right = st.columns(2, gap="large")

    with col_left:
        discount_rate = _slider_with_tip(
            "Discount rate (WACC)",
            "Typical range: 8-12%. Use ~8% for large stable blue-chips, ~10-12% for cyclical or mid-cap firms. Higher = more conservative valuation.",
            min_value=5, max_value=15, value=10, step=1,
            format="%d%%", key="dcf_discount",
        ) / 100

        terminal_growth = _slider_with_tip(
            "Terminal growth rate",
            "Typical range: 2-3% (long-run GDP growth). Must stay below your discount rate. Avoid exceeding 3% as it implies perpetual above-economy growth.",
            min_value=0.0, max_value=4.0, value=2.5, step=0.5,
            format="%.1f%%", key="dcf_term",
        ) / 100

        years_projected = _slider_with_tip(
            "Years projected",
            "Typical range: 5-10 years. Use 5 for mature predictable businesses. Use 7-10 only with high confidence in long-term growth visibility.",
            min_value=3, max_value=10, value=5, step=1,
            key="dcf_years",
        )

    with col_right:
        growth_y1_3 = _slider_with_tip(
            "FCF growth — years 1–3",
            g13_hint.replace("<b>", "").replace("</b>", ""),
            min_value=-5.0, max_value=20.0, value=6.0, step=0.5,
            format="%.1f%%", key="dcf_g13",
        ) / 100

        growth_y4_5 = _slider_with_tip(
            "FCF growth — years 4+",
            g45_hint.replace("<b>", "").replace("</b>", ""),
            min_value=-5.0, max_value=15.0, value=4.0, step=0.5,
            format="%.1f%%", key="dcf_g45",
        ) / 100

    st.divider()

    # ------------------------------------------------------------------
    # Calculate button
    # ------------------------------------------------------------------
    if st.button("Calculate", type="primary", key="valuation_calculate_btn"):

        # Guard: need at least 3 years of FCF history
        if len(fcf_history) < 3:
            st.error(
                "⚠️ Not enough FCF history to run a DCF — need at least 3 years of data. "
                "This company may not report sufficient free cash flow history via yfinance."
            )
            return

        # Guard: missing market data
        if not live_price or not shares_outstanding:
            st.error("⚠️ Missing live price or shares outstanding — cannot compute fair value.")
            return

        # Run DCF
        try:
            dcf = calculate_dcf(
                fcf_history=fcf_history,
                shares_outstanding=shares_outstanding,
                net_debt=net_debt,
                discount_rate=discount_rate,
                terminal_growth=terminal_growth,
                years_projected=years_projected,
                growth_y1_3=growth_y1_3,
                growth_y4_5=growth_y4_5,
            )
        except ValueError as e:
            st.error(f"⚠️ DCF error: {e}")
            return

        fair_value: float = dcf["fair_value"]

        # Verdict
        if fair_value > live_price * 1.10:
            verdict = "UNDER"
            verdict_color = "#4ADE80"
            verdict_label = "🟢 UNDERVALUED"
        elif fair_value < live_price * 0.90:
            verdict = "OVER"
            verdict_color = "#F87171"
            verdict_label = "🔴 OVERVALUED"
        else:
            verdict = "FAIR"
            verdict_color = "#FACC15"
            verdict_label = "🟡 FAIRLY VALUED"

        # Results row
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric(
                label="DCF Fair Value",
                value=f"${fair_value:,.2f}",
                delta=f"{(fair_value / live_price - 1) * 100:+.1f}% vs current",
            )
        with m2:
            st.metric(label="Current Price", value=f"${live_price:,.2f}")
        with m3:
            st.markdown(
                f'<div style="padding-top:8px">'
                f'<div style="font-size:12px;color:#94A3B8;margin-bottom:4px">Verdict</div>'
                f'<div style="font-size:22px;font-weight:700;color:{verdict_color}">'
                f"{verdict_label}</div></div>",
                unsafe_allow_html=True,
            )

        # Sensitivity chart + AI explanation side by side
        chart_col, ai_col = st.columns([2, 1], gap="large")

        with chart_col:
            fig = _dcf_sensitivity_chart(
                fcf_history=fcf_history,
                shares_outstanding=shares_outstanding,
                net_debt=net_debt,
                terminal_growth=terminal_growth,
                years_projected=years_projected,
                growth_y1_3=growth_y1_3,
                growth_y4_5=growth_y4_5,
                current_price=live_price,
            )
            st.plotly_chart(fig, width='stretch')

        with ai_col:
            ai_text = explain_dcf(
                ticker=ticker,
                fair_value=round(fair_value, 2),
                current_price=round(live_price, 2),
                verdict=verdict,
                discount_rate=discount_rate,
            )
            if ai_text:
                st.markdown(
                    f'<div style="margin-top:48px;padding:16px;background:#0F1C2E;'
                    f'border:1px solid #1E3A5F;border-radius:10px;color:#CBD5E1;'
                    f'font-size:13px;line-height:1.6">'
                    f'<div style="font-size:12px;color:#38BDF8;font-weight:600;'
                    f'margin-bottom:8px">\u2728 AI Insight</div>'
                    f'{ai_text}</div>',
                    unsafe_allow_html=True,
                )

        # Log the run
        try:
            log_run(
                ticker=ticker,
                method="DCF",
                fair_value=fair_value,
                current_price=live_price,
                verdict=verdict,
                analyst_target=analyst_target,
                discount_rate=discount_rate,
            )
        except Exception:
            pass

# ---------------------------------------------------------------------------
# FCF growth stats helper (used by both UI and eval)
# ---------------------------------------------------------------------------


def _fcf_growth_stats(fcf_hist: list) -> dict:
    """
    Given FCF history (most recent first), compute suggested growth rates.
    Returns a dict with suggested_near, suggested_long, avg, recent, n_years, yoy.
    Returns {} if insufficient data.
    """
    clean = [v for v in fcf_hist if v and v != 0]
    if len(clean) < 2:
        return {}
    chron = list(reversed(clean))
    yoy = []
    for i in range(1, len(chron)):
        if chron[i - 1] > 0:
            yoy.append((chron[i] - chron[i - 1]) / chron[i - 1])
    if not yoy:
        return {}
    avg = sum(yoy) / len(yoy)
    recent = sum(yoy[-2:]) / len(yoy[-2:]) if len(yoy) >= 2 else yoy[-1]
    suggested_near = max(-0.05, min(0.20, recent * 0.6 + avg * 0.4))
    suggested_long = max(-0.05, min(0.15, avg * 0.5 + 0.03 * 0.5))
    return {
        "n_years": len(yoy),
        "avg": avg,
        "recent": recent,
        "suggested_near": suggested_near,
        "suggested_long": suggested_long,
        "yoy": yoy,
    }


# ---------------------------------------------------------------------------
# Evaluation engine — Analyst Consensus as Ground Truth
# ---------------------------------------------------------------------------

EVAL_LOG_PATH = str(Path(__file__).parent / "data" / "eval_results.csv")

EVAL_CSV_HEADER = [
    "timestamp", "ticker", "sector",
    "live_price", "dcf_fair_value",
    "analyst_low", "analyst_high",
    "dcf_verdict", "in_range", "pct_above_high", "pct_below_low",
    "discount_rate", "terminal_growth", "years_projected",
    "growth_y1_3", "growth_y4_5", "note",
]

_EVAL_TICKERS = [
    # Technology (20)
    "AAPL", "MSFT", "NVDA", "META", "INTC",
    "GOOGL", "TSLA", "AMD",  "QCOM", "AVGO",
    "TXN",  "CRM",  "ORCL", "ADBE", "CSCO",
    "IBM",  "NOW",  "AMAT", "MU",   "INTU",
    # Healthcare (15)
    "JNJ",  "UNH",  "PFE",  "ABBV", "MRK",
    "TMO",  "DHR",  "BMY",  "GILD", "AMGN",
    "CVS",  "MDT",  "SYK",  "ISRG", "ZTS",
    # Consumer (20)
    "AMZN", "WMT",  "COST", "MCD",  "NKE",
    "HD",   "LOW",  "TGT",  "TJX",  "SBUX",
    "CMG",  "F",    "GM",   "PG",   "KO",
    "PEP",  "PM",   "CL",   "BKNG", "ABNB",
    # Energy (10)
    "XOM",  "CVX",  "COP",  "SLB",  "EOG",
    "PSX",  "VLO",  "MPC",  "OXY",  "HAL",
    # Industrials (15)
    "CAT",  "HON",  "GE",   "UPS",  "BA",
    "MMM",  "DE",   "EMR",  "ITW",  "PH",
    "RTX",  "LMT",  "NOC",  "GD",   "FDX",
    # Communication (10)
    "DIS",  "NFLX", "CMCSA","TMUS", "T",
    "VZ",   "CHTR", "PARA", "WBD",  "SNAP",
    # Materials (5)
    "LIN",  "APD",  "SHW",  "FCX",  "NEM",
    # Utilities (5)
    "NEE",  "DUK",  "SO",   "AEP",  "EXC",
]

_SECTOR_MAP = {
    # Technology
    "AAPL": "Technology",  "MSFT": "Technology",  "NVDA": "Technology",
    "META": "Technology",  "INTC": "Technology",  "GOOGL": "Technology",
    "TSLA": "Technology",  "AMD":  "Technology",  "QCOM": "Technology",
    "AVGO": "Technology",  "TXN":  "Technology",  "CRM":  "Technology",
    "ORCL": "Technology",  "ADBE": "Technology",  "CSCO": "Technology",
    "IBM":  "Technology",  "NOW":  "Technology",  "AMAT": "Technology",
    "MU":   "Technology",  "INTU": "Technology",
    # Healthcare
    "JNJ":  "Healthcare",  "UNH":  "Healthcare",  "PFE":  "Healthcare",
    "ABBV": "Healthcare",  "MRK":  "Healthcare",  "TMO":  "Healthcare",
    "DHR":  "Healthcare",  "BMY":  "Healthcare",  "GILD": "Healthcare",
    "AMGN": "Healthcare",  "CVS":  "Healthcare",  "MDT":  "Healthcare",
    "SYK":  "Healthcare",  "ISRG": "Healthcare",  "ZTS":  "Healthcare",
    # Consumer
    "AMZN": "Consumer",    "WMT":  "Consumer",    "COST": "Consumer",
    "MCD":  "Consumer",    "NKE":  "Consumer",    "HD":   "Consumer",
    "LOW":  "Consumer",    "TGT":  "Consumer",    "TJX":  "Consumer",
    "SBUX": "Consumer",    "CMG":  "Consumer",    "F":    "Consumer",
    "GM":   "Consumer",    "PG":   "Consumer",    "KO":   "Consumer",
    "PEP":  "Consumer",    "PM":   "Consumer",    "CL":   "Consumer",
    "BKNG": "Consumer",    "ABNB": "Consumer",
    # Energy
    "XOM":  "Energy",      "CVX":  "Energy",      "COP":  "Energy",
    "SLB":  "Energy",      "EOG":  "Energy",      "PSX":  "Energy",
    "VLO":  "Energy",      "MPC":  "Energy",      "OXY":  "Energy",
    "HAL":  "Energy",
    # Industrials
    "CAT":  "Industrials", "HON":  "Industrials", "GE":   "Industrials",
    "UPS":  "Industrials", "BA":   "Industrials", "MMM":  "Industrials",
    "DE":   "Industrials", "EMR":  "Industrials", "ITW":  "Industrials",
    "PH":   "Industrials", "RTX":  "Industrials", "LMT":  "Industrials",
    "NOC":  "Industrials", "GD":   "Industrials", "FDX":  "Industrials",
    # Communication
    "DIS":  "Communication", "NFLX": "Communication", "CMCSA": "Communication",
    "TMUS": "Communication", "T":    "Communication", "VZ":    "Communication",
    "CHTR": "Communication", "PARA": "Communication", "WBD":   "Communication",
    "SNAP": "Communication",
    # Materials
    "LIN":  "Materials",   "APD":  "Materials",   "SHW":  "Materials",
    "FCX":  "Materials",   "NEM":  "Materials",
    # Utilities
    "NEE":  "Utilities",   "DUK":  "Utilities",   "SO":   "Utilities",
    "AEP":  "Utilities",   "EXC":  "Utilities",
}

# Sector-based discount rates matching the UI tooltip guidance:
# ~8% large stable blue-chips, ~10-12% cyclical/growth/mid-cap
_SECTOR_DISCOUNT = {
    "Technology":    0.10,
    "Healthcare":    0.09,
    "Consumer":      0.09,
    "Energy":        0.11,
    "Industrials":   0.10,
    "Communication": 0.10,
    "Materials":     0.10,
    "Utilities":     0.08,
}

_EVAL_DCF_DEFAULTS = {
    "terminal_growth": 0.025,
    "years_projected": 5,
    # growth_y1_3 and growth_y4_5 are computed per-ticker from FCF history
    # fallbacks used when FCF history is insufficient
    "growth_y1_3": 0.06,
    "growth_y4_5": 0.04,
}


def run_eval_and_export() -> tuple:
    """
    Run DCF on all 30 eval tickers, compare against analyst consensus,
    write results to data/eval_results.csv, and return (rows, summary_dict).
    """
    # Ensure data/ dir exists
    global EVAL_LOG_PATH
    try:
        Path(EVAL_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        import tempfile
        EVAL_LOG_PATH = str(Path(tempfile.gettempdir()) / "eval_results.csv")

    rows = []
    ts = datetime.now(timezone.utc).isoformat()

    for ticker in _EVAL_TICKERS:
        sector = _SECTOR_MAP.get(ticker, "Unknown")
        row = {
            "timestamp":       ts,
            "ticker":          ticker,
            "sector":          sector,
            "live_price":      "",
            "dcf_fair_value":  "",
            "analyst_low":     "",
            "analyst_high":    "",
            "dcf_verdict":     "",
            "in_range":        "",
            "pct_above_high":  "",
            "pct_below_low":   "",
            "discount_rate":   _SECTOR_DISCOUNT.get(sector, 0.10),
            "terminal_growth": _EVAL_DCF_DEFAULTS["terminal_growth"],
            "years_projected": _EVAL_DCF_DEFAULTS["years_projected"],
            "growth_y1_3":     _EVAL_DCF_DEFAULTS["growth_y1_3"],
            "growth_y4_5":     _EVAL_DCF_DEFAULTS["growth_y4_5"],
            "note":            "",
        }
        try:
            yf_data = _fetch_yf(ticker)
            live_price     = yf_data["live_price"]
            analyst_target = yf_data["analyst_target"]
            analyst_low    = yf_data["analyst_low"]
            analyst_high   = yf_data["analyst_high"]
            fcf_history    = yf_data["fcf_history"] or []
            shares         = yf_data["shares_outstanding"]
            net_debt       = yf_data["net_debt"] or 0.0

            row["live_price"]     = round(live_price, 2)     if live_price     else ""
            row["analyst_low"]  = round(analyst_low, 2)  if analyst_low  else ""
            row["analyst_high"]   = round(analyst_high, 2)   if analyst_high   else ""

            if len(fcf_history) < 3:
                row["note"] = "Skipped: FCF history < 3 years"
            elif not live_price or not shares:
                row["note"] = "Skipped: missing price or shares"
            elif analyst_target is None:
                row["note"] = "Skipped: no analyst target"
            elif sector == "Financials":
                row["dcf_fair_value"] = None
                row["dcf_verdict"]    = "N/A"
                row["in_range"]       = "SKIP"
                row["note"]           = "DCF not meaningful for banks — FCF concept does not apply"
            else:
                # Use recommended rates: sector discount + FCF-derived growth rates
                discount_rate = _SECTOR_DISCOUNT.get(sector, 0.10)
                stats = _fcf_growth_stats(fcf_history)
                growth_y1_3 = stats["suggested_near"] if stats else _EVAL_DCF_DEFAULTS["growth_y1_3"]
                growth_y4_5 = stats["suggested_long"] if stats else _EVAL_DCF_DEFAULTS["growth_y4_5"]

                row["discount_rate"] = discount_rate
                row["growth_y1_3"]   = round(growth_y1_3, 4)
                row["growth_y4_5"]   = round(growth_y4_5, 4)

                dcf = calculate_dcf(
                    fcf_history=fcf_history,
                    shares_outstanding=shares,
                    net_debt=net_debt,
                    discount_rate=discount_rate,
                    terminal_growth=_EVAL_DCF_DEFAULTS["terminal_growth"],
                    years_projected=_EVAL_DCF_DEFAULTS["years_projected"],
                    growth_y1_3=growth_y1_3,
                    growth_y4_5=growth_y4_5,
                )
                fv = dcf["fair_value"]
                dcf_fair_value = fv
                row["dcf_fair_value"] = round(fv, 2)

                if fv > live_price * 1.10:
                    dcf_verdict = "UNDER"
                elif fv < live_price * 0.90:
                    dcf_verdict = "OVER"
                else:
                    dcf_verdict = "FAIR"

                row["dcf_verdict"] = dcf_verdict

                if analyst_low is None or analyst_high is None:
                    row["in_range"] = "SKIP"
                    row["note"] = "no analyst range"
                elif analyst_low <= dcf_fair_value <= analyst_high:
                    row["in_range"]       = "YES"
                    row["pct_above_high"] = "In Range"
                    row["pct_below_low"]  = "In Range"
                elif dcf_fair_value < analyst_low:
                    row["in_range"]      = "NO"
                    row["pct_below_low"] = round((dcf_fair_value / analyst_low - 1) * 100, 2)
                else:
                    row["in_range"]       = "NO"
                    row["pct_above_high"] = round((dcf_fair_value / analyst_high - 1) * 100, 2)

        except Exception as e:
            row["note"] = f"Error: {e}"

        rows.append(row)

    # Write CSV
    with open(EVAL_LOG_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EVAL_CSV_HEADER)
        writer.writeheader()
        writer.writerows(rows)

    # Compute summary
    scored    = [r for r in rows if r["in_range"] in ("YES", "NO")]
    n_in      = sum(1 for r in rows if r["in_range"] == "YES")
    n_below   = sum(1 for r in rows if r["in_range"] == "NO" and r["pct_below_low"] != "")
    n_above   = sum(1 for r in rows if r["in_range"] == "NO" and r["pct_above_high"] != "")
    n_skipped = len(rows) - len(scored)

    print(f"Total scored:      {len(scored)}")
    print(f"In range (YES):    {n_in}")
    print(f"Below range:       {n_below}")
    print(f"Above range:       {n_above}")
    print(f"Skipped:           {n_skipped}")

    summary = {
        "total":    len(rows),
        "scored":   len(scored),
        "in_range": n_in,
        "below":    n_below,
        "above":    n_above,
        "skipped":  n_skipped,
        "path":     EVAL_LOG_PATH,
    }
    return rows, summary



# ---------------------------------------------------------------------------
# Auto-run eval in background on module load
# ---------------------------------------------------------------------------

def _run_eval_background() -> None:
    """Run eval silently in a background thread. Never raises."""
    try:
        run_eval_and_export()
    except Exception:
        pass


def _start_eval_if_due() -> None:
    """
    Launch the eval in a background thread once per Streamlit session.
    Uses session_state as a guard so it only fires once per browser session,
    not on every rerun triggered by slider moves.
    """
    import threading
    if not st.session_state.get("_eval_started"):
        st.session_state["_eval_started"] = True
        t = threading.Thread(target=_run_eval_background, daemon=True)
        t.start()