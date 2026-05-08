"""
valuation_standalone.py — Standalone DCF valuation tool (no frontend).

Usage:
    python valuation_standalone.py                        # runs 5 default tickers
    python valuation_standalone.py --ticker AAPL          # run a specific ticker
    python valuation_standalone.py --ticker MSFT --discount_rate 9 --years 7
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
    return {
        "suggested_near": max(-0.05, min(0.20, recent * 0.6 + avg * 0.4)),
        "suggested_long": max(-0.05, min(0.15, avg * 0.5 + 0.03 * 0.5)),
    }


# ---------------------------------------------------------------------------
# yfinance fetcher
# ---------------------------------------------------------------------------

def fetch_yf(ticker: str) -> dict:
    import time
    result = {
        "live_price": None, "analyst_low": None, "analyst_high": None,
        "shares_outstanding": None, "net_debt": 0.0, "fcf_history": [],
    }
    try:
        import yfinance as yf
        t = yf.Ticker(ticker.upper())
        info = t.info
        if not info or len(info) <= 2:
            time.sleep(2)
            t = yf.Ticker(ticker.upper())
            info = t.info

        result["live_price"]         = info.get("currentPrice") or info.get("regularMarketPrice")
        result["analyst_low"]        = info.get("targetLowPrice")
        result["analyst_high"]       = info.get("targetHighPrice")
        result["shares_outstanding"] = info.get("sharesOutstanding")
        result["net_debt"]           = (info.get("totalDebt") or 0) - (info.get("totalCash") or 0)

        cf = t.cashflow
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
) -> float:
    if discount_rate <= terminal_growth:
        raise ValueError(f"Discount rate ({discount_rate:.1%}) must exceed terminal growth ({terminal_growth:.1%}).")
    base = fcf_history[0]
    fcfs = []
    for yr in range(1, years_projected + 1):
        g = growth_y1_3 if yr <= 3 else growth_y4_5
        fcfs.append(base * (1 + g) if yr == 1 else fcfs[-1] * (1 + g))
    pvs          = [f / (1 + discount_rate) ** yr for yr, f in enumerate(fcfs, 1)]
    tv           = fcfs[-1] * (1 + terminal_growth) / (discount_rate - terminal_growth)
    equity_value = sum(pvs) + tv / (1 + discount_rate) ** years_projected - net_debt
    return equity_value / shares_outstanding


# ---------------------------------------------------------------------------
# Single ticker run
# ---------------------------------------------------------------------------

def run_ticker(ticker: str, discount_rate: Optional[float], terminal_growth: float, years: int):
    ticker = ticker.upper()
    print(f"\n{'='*55}")
    print(f"  DCF Valuation — {ticker}")
    print(f"{'='*55}")
    print("  Fetching live data...")

    data         = fetch_yf(ticker)
    live_price   = data["live_price"]
    analyst_low  = data["analyst_low"]
    analyst_high = data["analyst_high"]
    shares       = data["shares_outstanding"]
    net_debt     = data["net_debt"]
    fcf_history  = data["fcf_history"]

    if not live_price:
        print("  ERROR: Could not fetch live price.")
        return
    if len(fcf_history) < 3:
        print("  SKIP: Fewer than 3 years of FCF history.")
        return
    if not shares:
        print("  SKIP: Shares outstanding not available.")
        return

    print(f"  Live price:      ${live_price:,.2f}")
    if analyst_low and analyst_high:
        print(f"  Analyst range:   ${analyst_low:,.2f} – ${analyst_high:,.2f}")

    stats       = _fcf_growth_stats(fcf_history)
    growth_y1_3 = stats["suggested_near"] if stats else 0.06
    growth_y4_5 = stats["suggested_long"] if stats else 0.04
    dr          = (discount_rate / 100) if discount_rate else 0.10
    tg          = terminal_growth / 100

    print(f"\n  Assumptions: WACC={dr:.1%}  terminal={tg:.1%}  years={years}")
    print(f"  FCF growth:  y1-3={growth_y1_3:.1%}  y4+={growth_y4_5:.1%}  (from historical CAGR)")

    try:
        fair_value = calculate_dcf(fcf_history, shares, net_debt, dr, tg, years, growth_y1_3, growth_y4_5)
    except ValueError as e:
        print(f"  ERROR: {e}")
        return

    pct = (fair_value / live_price - 1) * 100
    if fair_value > live_price * 1.10:
        verdict = "UNDERVALUED"
    elif fair_value < live_price * 0.90:
        verdict = "OVERVALUED"
    else:
        verdict = "FAIRLY VALUED"

    print(f"\n  DCF fair value:  ${fair_value:,.2f}  ({pct:+.1f}% vs price)")
    print(f"  Verdict:         {verdict}")

    if analyst_low and analyst_high:
        if analyst_low <= fair_value <= analyst_high:
            print(f"  In analyst range: YES")
        elif fair_value < analyst_low:
            print(f"  In analyst range: NO — {(fair_value/analyst_low-1)*100:.1f}% below low (${analyst_low:,.2f})")
        else:
            print(f"  In analyst range: NO — {(fair_value/analyst_high-1)*100:+.1f}% above high (${analyst_high:,.2f})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_DEFAULT_TICKERS = ["AAPL", "MSFT", "NKE", "PFE", "XOM"]


def main():
    parser = argparse.ArgumentParser(description="Standalone DCF valuation — no frontend required.")
    parser.add_argument("--ticker",          default=None,       help="Ticker to value (e.g. AAPL). Omit to run 5 default tickers.")
    parser.add_argument("--discount_rate",   type=float,         help="WACC %% override (default: 10)")
    parser.add_argument("--terminal_growth", type=float, default=2.5, help="Terminal growth rate %% (default: 2.5)")
    parser.add_argument("--years",           type=int,   default=5,   help="Years to project (default: 5)")
    args = parser.parse_args()

    tickers = [args.ticker] if args.ticker else _DEFAULT_TICKERS
    for t in tickers:
        run_ticker(t, args.discount_rate, args.terminal_growth, args.years)
    print()


if __name__ == "__main__":
    main()
