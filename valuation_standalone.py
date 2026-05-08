"""
valuation_standalone.py — Standalone DCF valuation tool (no frontend).

Usage:
    python valuation_standalone.py --ticker AAPL
    python valuation_standalone.py --ticker MSFT --discount_rate 10 --terminal_growth 2.5 --years 5
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional


# ---------------------------------------------------------------------------
# FCF growth stats
# ---------------------------------------------------------------------------

def _fcf_growth_stats(fcf_hist: list) -> dict:
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
    }


# ---------------------------------------------------------------------------
# yfinance fetcher
# ---------------------------------------------------------------------------

def fetch_yf(ticker: str) -> dict:
    import time
    result = {
        "live_price": None,
        "analyst_target": None,
        "analyst_low": None,
        "analyst_high": None,
        "shares_outstanding": None,
        "net_debt": 0.0,
        "fcf_history": [],
    }
    try:
        import yfinance as yf
        t = yf.Ticker(ticker.upper())
        info = t.info
        if not info or len(info) <= 2:
            time.sleep(2)
            t = yf.Ticker(ticker.upper())
            info = t.info

        result["live_price"]        = info.get("currentPrice") or info.get("regularMarketPrice")
        result["analyst_target"]    = info.get("targetMeanPrice")
        result["analyst_low"]       = info.get("targetLowPrice")
        result["analyst_high"]      = info.get("targetHighPrice")
        result["shares_outstanding"] = info.get("sharesOutstanding")

        total_debt = info.get("totalDebt") or 0
        cash       = info.get("totalCash") or 0
        result["net_debt"] = total_debt - cash

        cf = t.cashflow
        if cf is not None and not cf.empty:
            fcf_row = None
            for label in ["Free Cash Flow", "FreeCashFlow"]:
                if label in cf.index:
                    fcf_row = cf.loc[label]
                    break
            if fcf_row is None:
                op_cf  = cf.loc["Operating Cash Flow"] if "Operating Cash Flow" in cf.index else None
                capex  = cf.loc["Capital Expenditure"] if "Capital Expenditure" in cf.index else None
                if op_cf is not None and capex is not None:
                    fcf_row = op_cf + capex
            if fcf_row is not None:
                result["fcf_history"] = [float(v) for v in fcf_row.dropna().values[:5]]
    except Exception as e:
        print(f"  [warning] yfinance error: {e}", file=sys.stderr)

    return result


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
    if discount_rate <= terminal_growth:
        raise ValueError(
            f"Discount rate ({discount_rate:.1%}) must be greater than "
            f"terminal growth rate ({terminal_growth:.1%})."
        )
    base_fcf = fcf_history[0]
    projected_fcfs = []
    for year in range(1, years_projected + 1):
        growth = growth_y1_3 if year <= 3 else growth_y4_5
        fcf = base_fcf * (1 + growth) if year == 1 else projected_fcfs[-1] * (1 + growth)
        projected_fcfs.append(fcf)

    present_values = [fcf / (1 + discount_rate) ** yr for yr, fcf in enumerate(projected_fcfs, 1)]
    fcf_final      = projected_fcfs[-1]
    terminal_value = fcf_final * (1 + terminal_growth) / (discount_rate - terminal_growth)
    pv_terminal    = terminal_value / (1 + discount_rate) ** years_projected
    equity_value   = sum(present_values) + pv_terminal - net_debt
    fair_value     = equity_value / shares_outstanding
    return {"fair_value": fair_value, "projected_fcfs": projected_fcfs, "terminal_value": terminal_value}


# ---------------------------------------------------------------------------
# Sector defaults
# ---------------------------------------------------------------------------

_SECTOR_DISCOUNT = {
    "Technology": 0.10, "Healthcare": 0.09, "Consumer": 0.09,
    "Energy": 0.11, "Industrials": 0.10, "Communication": 0.10,
    "Materials": 0.10, "Utilities": 0.08,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Standalone DCF valuation tool")
    parser.add_argument("--ticker",          required=True,       help="US stock ticker, e.g. AAPL")
    parser.add_argument("--discount_rate",   type=float, default=None, help="WACC %% (default: 10)")
    parser.add_argument("--terminal_growth", type=float, default=2.5,  help="Terminal growth rate %% (default: 2.5)")
    parser.add_argument("--years",           type=int,   default=5,    help="Years projected (default: 5)")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    print(f"\n{'='*55}")
    print(f"  DCF Valuation — {ticker}")
    print(f"{'='*55}")

    print("  Fetching live data from yfinance...")
    data = fetch_yf(ticker)

    live_price    = data["live_price"]
    analyst_low   = data["analyst_low"]
    analyst_high  = data["analyst_high"]
    shares        = data["shares_outstanding"]
    net_debt      = data["net_debt"]
    fcf_history   = data["fcf_history"]

    if not live_price:
        print("  ERROR: Could not fetch live price. Check the ticker and try again.")
        sys.exit(1)

    print(f"  Live price:        ${live_price:,.2f}")
    if analyst_low and analyst_high:
        print(f"  Analyst range:     ${analyst_low:,.2f} – ${analyst_high:,.2f}")
    else:
        print("  Analyst range:     not available")
    print(f"  FCF history:       {len(fcf_history)} years")

    if len(fcf_history) < 3:
        print("\n  ERROR: Fewer than 3 years of FCF history — cannot run DCF.")
        sys.exit(1)
    if not shares:
        print("\n  ERROR: Shares outstanding not available.")
        sys.exit(1)

    # Growth rates from historical FCF
    stats       = _fcf_growth_stats(fcf_history)
    growth_y1_3 = stats["suggested_near"] if stats else 0.06
    growth_y4_5 = stats["suggested_long"] if stats else 0.04
    discount    = (args.discount_rate / 100) if args.discount_rate else 0.10
    terminal    = args.terminal_growth / 100

    print(f"\n  --- DCF Assumptions ---")
    print(f"  Discount rate:     {discount:.1%}")
    print(f"  Terminal growth:   {terminal:.1%}")
    print(f"  Years projected:   {args.years}")
    print(f"  FCF growth y1-3:   {growth_y1_3:.1%}  (from historical CAGR)")
    print(f"  FCF growth y4+:    {growth_y4_5:.1%}  (from historical CAGR)")

    try:
        result     = calculate_dcf(fcf_history, shares, net_debt, discount, terminal, args.years, growth_y1_3, growth_y4_5)
        fair_value = result["fair_value"]
    except ValueError as e:
        print(f"\n  ERROR: {e}")
        sys.exit(1)

    pct_vs_price = (fair_value / live_price - 1) * 100
    if fair_value > live_price * 1.10:
        verdict = "UNDERVALUED"
    elif fair_value < live_price * 0.90:
        verdict = "OVERVALUED"
    else:
        verdict = "FAIRLY VALUED"

    print(f"\n  --- Results ---")
    print(f"  DCF fair value:    ${fair_value:,.2f}  ({pct_vs_price:+.1f}% vs current price)")
    print(f"  Verdict:           {verdict}")

    if analyst_low and analyst_high:
        if analyst_low <= fair_value <= analyst_high:
            range_result = "YES — within analyst range"
        elif fair_value < analyst_low:
            pct_below = (fair_value / analyst_low - 1) * 100
            range_result = f"NO — {pct_below:.1f}% below analyst low (${analyst_low:,.2f})"
        else:
            pct_above = (fair_value / analyst_high - 1) * 100
            range_result = f"NO — {pct_above:+.1f}% above analyst high (${analyst_high:,.2f})"
        print(f"  In analyst range:  {range_result}")

    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
