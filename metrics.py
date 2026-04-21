"""Derived numbers: year-over-year growth, trailing-twelve-months, and ratios.

Two growth concepts live here:

    YoY  - Year-over-year. Compares this quarter to the SAME quarter a year ago
           (Q1'25 vs Q1'24). Never compared to the previous quarter, because
           seasonal businesses make that comparison misleading.

    TTM  - Trailing twelve months. The sum of the last 4 quarters. Removes
           seasonality entirely and shows the annualized run-rate.
"""
from __future__ import annotations

import pandas as pd


def add_yoy(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """Add a `<col>_yoy` column with the year-over-year % change for each row.

    The math: for each fiscal period (Q1/Q2/Q3/Q4), sort by year and compute
    the percent change from one year to the next. This gives a TRUE
    same-quarter-prior-year comparison, immune to seasonality.
    """
    if df.empty or value_col not in df.columns:
        return df

    sorted_df = df.sort_values(["fp", "fy", "end"]).copy()
    yoy_col = f"{value_col}_yoy"
    sorted_df[yoy_col] = sorted_df.groupby("fp")[value_col].pct_change()
    return sorted_df.sort_values("end").reset_index(drop=True)


def add_ttm(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """Add `<col>_ttm` (rolling 4-quarter sum) and `<col>_ttm_yoy` (its YoY).

    The first three quarters of any time series are NaN because you need a
    full 4-quarter window to compute a trailing-twelve-month total.
    """
    if df.empty or value_col not in df.columns:
        return df

    sorted_df = df.sort_values("end").copy()
    ttm_col = f"{value_col}_ttm"
    sorted_df[ttm_col] = sorted_df[value_col].rolling(window=4, min_periods=4).sum()

    # Growth of the TTM line: each TTM vs the TTM 4 quarters earlier
    sorted_df[f"{ttm_col}_yoy"] = sorted_df[ttm_col].pct_change(periods=4)
    return sorted_df.reset_index(drop=True)


def compute_ratios(income: pd.DataFrame, balance: pd.DataFrame, cashflow: pd.DataFrame) -> pd.DataFrame:
    """Combine the three statements and compute the standard financial ratios.

    Returns one row per quarter with whichever ratios could be computed for
    that quarter (missing inputs become missing outputs, never errors).
    """
    if income.empty:
        return pd.DataFrame()

    # Build Free Cash Flow = Operating CF - Capital Expenditure
    cf = cashflow.copy() if not cashflow.empty else pd.DataFrame()
    if not cf.empty and "OperatingCF" in cf.columns:
        capex = cf["CapEx"].fillna(0) if "CapEx" in cf.columns else 0
        cf["FCF"] = cf["OperatingCF"] - capex

    # Merge income, cashflow, and balance onto a single wide frame keyed by `end`
    merged = income.copy()
    if not cf.empty:
        drop = [c for c in ("fy", "fp") if c in cf.columns]
        merged = pd.merge(merged, cf.drop(columns=drop, errors="ignore"), on="end", how="left", suffixes=("", "_cf"))
    if not balance.empty:
        drop = [c for c in ("fy", "fp") if c in balance.columns]
        merged = pd.merge(merged, balance.drop(columns=drop, errors="ignore"), on="end", how="left", suffixes=("", "_bs"))

    ratios = merged[["end", "fy", "fp"]].copy()

    # --- Margins (percent of revenue) ---
    revenue = merged["Revenue"] if "Revenue" in merged.columns else None
    if revenue is not None:
        if "GrossProfit" in merged.columns:
            ratios["GrossMargin"] = merged["GrossProfit"] / revenue
        if "OperatingIncome" in merged.columns:
            ratios["OperatingMargin"] = merged["OperatingIncome"] / revenue
        if "NetIncome" in merged.columns:
            ratios["NetMargin"] = merged["NetIncome"] / revenue
        if "FCF" in merged.columns:
            ratios["FCFMargin"] = merged["FCF"] / revenue

    # --- Returns (net income divided by various bases) ---
    if "NetIncome" in merged.columns:
        if "Assets" in merged.columns:
            ratios["ROA"] = merged["NetIncome"] / merged["Assets"]
        if "Equity" in merged.columns:
            ratios["ROE"] = merged["NetIncome"] / merged["Equity"]

    # --- Liquidity / leverage ---
    if "CurrentAssets" in merged.columns and "CurrentLiabilities" in merged.columns:
        ratios["CurrentRatio"] = merged["CurrentAssets"] / merged["CurrentLiabilities"]
    if "LongTermDebt" in merged.columns and "Equity" in merged.columns:
        ratios["DebtToEquity"] = merged["LongTermDebt"] / merged["Equity"]

    # Drop rows where nothing could be computed
    ratio_cols = [c for c in ratios.columns if c not in ("end", "fy", "fp")]
    if ratio_cols:
        ratios = ratios.dropna(how="all", subset=ratio_cols)
    return ratios.reset_index(drop=True)
