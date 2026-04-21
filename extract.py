"""Turn SEC's raw filing data into clean per-quarter tables.

SEC publishes each company's financials as a big JSON blob ("company facts").
Each number inside has a time period attached - e.g. "Revenue, Jan 1 to Mar 31".
This file reads that blob and produces three simple tables:

    income     - one row per quarter, one column per income-statement line
    balance    - one row per quarter-end snapshot, one column per balance-sheet line
    cashflow   - one row per quarter, one column per cash-flow line

The tricky bits that this file handles for you:

1. Different companies tag the same idea with different names (Apple switched
   from "SalesRevenueNet" to "RevenueFromContractWithCustomer..." around 2018).
   We look for all known aliases and use whichever one the company reports.

2. Many companies only report year-to-date numbers in their 10-Q filings, not
   the standalone quarter. So for Q2 they give you "Jan-Jun" (6 months), not
   just "Apr-Jun" (3 months). We subtract to get the single-quarter value.

3. 10-K annual filings never break out Q4 on its own. We derive Q4 as
   (Full-year total) minus (Jan-Sep year-to-date).

4. SEC tags comparative data from old periods with the *current* filing's
   fiscal-year label, which is misleading. We ignore that label entirely and
   group facts by their actual start/end dates instead.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

import pandas as pd


# --------------------------------------------------------------------------- #
# GAAP concept names we look for, in order of preference.
# Each key is the friendly name we use internally; each value is the list of
# official US-GAAP tags to try. First match with usable data wins, but we also
# merge entries from later aliases so a company that switched tags still gets
# continuous history.
# --------------------------------------------------------------------------- #

INCOME_CONCEPTS = {
    "Revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ],
    "CostOfRevenue": [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
    ],
    "GrossProfit": ["GrossProfit"],
    "OperatingIncome": ["OperatingIncomeLoss"],
    "NetIncome": ["NetIncomeLoss", "ProfitLoss"],
}

BALANCE_CONCEPTS = {
    "Assets": ["Assets"],
    "CurrentAssets": ["AssetsCurrent"],
    "Liabilities": ["Liabilities"],
    "CurrentLiabilities": ["LiabilitiesCurrent"],
    "Equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "Cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "LongTermDebt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "SharesOutstanding": ["CommonStockSharesOutstanding"],
}

CASHFLOW_CONCEPTS = {
    "OperatingCF": ["NetCashProvidedByUsedInOperatingActivities"],
    "InvestingCF": ["NetCashProvidedByUsedInInvestingActivities"],
    "FinancingCF": ["NetCashProvidedByUsedInFinancingActivities"],
    "CapEx": ["PaymentsToAcquirePropertyPlantAndEquipment"],
}


# --------------------------------------------------------------------------- #
# Low-level helpers
# --------------------------------------------------------------------------- #

def _collect_entries(facts: dict, aliases: Iterable[str]) -> list[dict]:
    """Gather all facts for the given aliases into one list.

    If a company switched from one GAAP tag to another, we merge both so the
    history is continuous. Each entry is a dict like:
        {"start": "2024-01-01", "end": "2024-03-31", "val": 1234, "accn": ...}
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    merged: list[dict] = []
    for alias in aliases:
        if alias not in us_gaap:
            continue
        units = us_gaap[alias].get("units", {})
        for unit in ("USD", "USD/shares", "shares"):
            if unit in units:
                merged.extend(units[unit])
                break
    return merged


def _days_between(start: str, end: str) -> int:
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days


def _classify_duration(days: int) -> str | None:
    """Bucket a period length into the XBRL duration we recognize."""
    if 80 <= days <= 100:
        return "3M"   # one quarter
    if 170 <= days <= 195:
        return "6M"   # year-to-date through Q2
    if 260 <= days <= 285:
        return "9M"   # year-to-date through Q3
    if 350 <= days <= 380:
        return "12M"  # full fiscal year
    return None


def _is_instant_fact(entry: dict) -> bool:
    """Balance-sheet facts are "instants" - a snapshot on a specific date."""
    if "start" not in entry:
        return True
    try:
        return _days_between(entry["start"], entry["end"]) <= 3
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Income statement + cash flow: flow metrics with durations
# --------------------------------------------------------------------------- #

def build_duration_quarterly(facts: dict, concept_map: dict, years: int = 10) -> pd.DataFrame:
    """Build a long-format quarterly DataFrame for income-statement-style metrics.

    The algorithm, per metric:
      1. Collect all facts for every alias, then deduplicate by (start, end)
         keeping the most recent filing (handles restatements).
      2. For each 12-month FY entry, find the Q1/Q2/Q3 year-to-date entries
         that share the same fiscal-year start date.
      3. Subtract to get the standalone 3-month value for each quarter:
            Q1 = YTD at end of Q1
            Q2 = YTD at end of Q2  minus  Q1
            Q3 = YTD at end of Q3  minus  Q1 and Q2
            Q4 = full-year total    minus  YTD at end of Q3
      4. If YTD entries are missing, fall back to a standalone 3-month entry
         whose start date lines up with the previous quarter's end.
    """
    cutoff = datetime.today() - timedelta(days=365 * years + 120)
    rows: list[dict] = []

    for metric, aliases in concept_map.items():
        entries = _collect_entries(facts, aliases)
        if not entries:
            continue

        typed_entries = _parse_and_dedupe(entries)
        if not typed_entries:
            continue

        annual_entries = [e for e in typed_entries if e["dur"] == "12M"]

        for fy_entry in annual_entries:
            if fy_entry["end_dt"] < cutoff:
                continue
            quarter_rows = _derive_quarters_from_fy(fy_entry, typed_entries, metric)
            rows.extend(quarter_rows)

    if not rows:
        return pd.DataFrame(columns=["metric", "fy", "fp", "end", "value"])

    df = pd.DataFrame(rows)
    df["end"] = pd.to_datetime(df["end"])
    df = df.sort_values("end").drop_duplicates(subset=["metric", "fy", "fp"], keep="last")
    df = df[df["end"] >= pd.Timestamp(cutoff)]
    return df.sort_values("end").reset_index(drop=True)


def _parse_and_dedupe(raw_entries: list[dict]) -> list[dict]:
    """Parse dates, drop junk, and keep only the newest filing per period.

    Returns a list of dicts with the useful fields pre-computed:
        {raw, start_dt, end_dt, dur}
    """
    by_period: dict[tuple[str, str], dict] = {}
    for e in raw_entries:
        if "start" not in e or "end" not in e:
            continue
        try:
            start_dt = datetime.fromisoformat(e["start"])
            end_dt = datetime.fromisoformat(e["end"])
        except Exception:
            continue
        dur = _classify_duration((end_dt - start_dt).days)
        if dur is None:
            continue

        key = (e["start"], e["end"])
        previous = by_period.get(key)
        if previous is None or str(e.get("accn", "")) > str(previous["raw"].get("accn", "")):
            by_period[key] = {"raw": e, "start_dt": start_dt, "end_dt": end_dt, "dur": dur}
    return list(by_period.values())


def _derive_quarters_from_fy(fy_entry: dict, all_entries: list[dict], metric: str) -> list[dict]:
    """Given one fiscal-year entry, produce Q1-Q4 standalone values."""
    fy_start = fy_entry["start_dt"]
    fy_end = fy_entry["end_dt"]
    fy_value = float(fy_entry["raw"]["val"])
    fiscal_year = fy_end.year  # label the FY by the calendar year of its end

    def find(duration: str, start_date: datetime | None):
        """Find the single entry with a given duration that starts on the given date."""
        for e in all_entries:
            if e["dur"] != duration:
                continue
            if start_date is not None and abs((e["start_dt"] - start_date).days) > 2:
                continue
            return e
        return None

    # Preferred: year-to-date filings (all start at the fiscal-year start)
    q1_ytd = find("3M", fy_start)
    q2_ytd = find("6M", fy_start)
    q3_ytd = find("9M", fy_start)

    q1_value = float(q1_ytd["raw"]["val"]) if q1_ytd else None
    q1_end = q1_ytd["end_dt"] if q1_ytd else None

    # Q2 standalone
    q2_value = None
    q2_end = None
    if q2_ytd:
        q2_end = q2_ytd["end_dt"]
        if q1_value is not None:
            q2_value = float(q2_ytd["raw"]["val"]) - q1_value
    elif q1_value is not None:
        # Fallback: a standalone 3-month Q2 entry that starts right after Q1 ends
        q2_standalone = find("3M", q1_end)
        if q2_standalone:
            q2_value = float(q2_standalone["raw"]["val"])
            q2_end = q2_standalone["end_dt"]

    # Q3 standalone
    q3_value = None
    q3_end = None
    if q3_ytd:
        q3_end = q3_ytd["end_dt"]
        if q2_ytd:
            q3_value = float(q3_ytd["raw"]["val"]) - float(q2_ytd["raw"]["val"])
        elif q1_value is not None and q2_value is not None:
            q3_value = float(q3_ytd["raw"]["val"]) - q1_value - q2_value
    elif q2_end is not None:
        q3_standalone = find("3M", q2_end)
        if q3_standalone:
            q3_value = float(q3_standalone["raw"]["val"])
            q3_end = q3_standalone["end_dt"]

    # Q4 = full year - Q3 year-to-date
    q4_value = None
    if q3_ytd:
        q4_value = fy_value - float(q3_ytd["raw"]["val"])
    elif q1_value is not None and q2_value is not None and q3_value is not None:
        q4_value = fy_value - q1_value - q2_value - q3_value

    rows: list[dict] = []
    if q1_value is not None and q1_end is not None:
        rows.append({"metric": metric, "fy": fiscal_year, "fp": "Q1", "end": q1_end, "value": q1_value})
    if q2_value is not None and q2_end is not None:
        rows.append({"metric": metric, "fy": fiscal_year, "fp": "Q2", "end": q2_end, "value": q2_value})
    if q3_value is not None and q3_end is not None:
        rows.append({"metric": metric, "fy": fiscal_year, "fp": "Q3", "end": q3_end, "value": q3_value})
    if q4_value is not None:
        rows.append({"metric": metric, "fy": fiscal_year, "fp": "Q4", "end": fy_end, "value": q4_value})
    return rows


# --------------------------------------------------------------------------- #
# Balance sheet: point-in-time snapshots
# --------------------------------------------------------------------------- #

def build_instant_quarterly(facts: dict, concept_map: dict, years: int = 10) -> pd.DataFrame:
    """Build a long-format DataFrame for balance-sheet items (instant facts)."""
    cutoff = datetime.today() - timedelta(days=365 * years + 120)
    rows: list[dict] = []

    for metric, aliases in concept_map.items():
        entries = _collect_entries(facts, aliases)
        if not entries:
            continue

        # Keep only instant facts with a valid fiscal-period tag, dedupe by end date
        by_end: dict[str, dict] = {}
        for e in entries:
            if not _is_instant_fact(e) or e.get("fp") not in ("Q1", "Q2", "Q3", "FY"):
                continue
            prev = by_end.get(e["end"])
            if prev is None or str(e.get("accn", "")) > str(prev.get("accn", "")):
                by_end[e["end"]] = e

        for e in by_end.values():
            rows.append({
                "metric": metric,
                "fy": int(e.get("fy")) if e.get("fy") is not None else None,
                "fp": e.get("fp"),
                "end": e["end"],
                "value": float(e["val"]),
            })

    if not rows:
        return pd.DataFrame(columns=["metric", "fy", "fp", "end", "value"])

    df = pd.DataFrame(rows)
    df["end"] = pd.to_datetime(df["end"])
    df = df[df["end"] >= pd.Timestamp(cutoff)]
    # A "FY" tag on an instant is really the Q4-end snapshot
    df["fp"] = df["fp"].replace({"FY": "Q4"})
    return df.sort_values("end").reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Public API: long -> wide transformation
# --------------------------------------------------------------------------- #

def pivot_to_wide(long_df: pd.DataFrame) -> pd.DataFrame:
    """Turn the long [metric, fy, fp, end, value] shape into wide columns
    so each metric becomes its own column while the time index is preserved.
    """
    if long_df.empty:
        return pd.DataFrame()
    wide = long_df.pivot_table(
        index=["end", "fy", "fp"],
        columns="metric",
        values="value",
        aggfunc="last",
    ).reset_index()
    wide.columns.name = None
    return wide.sort_values("end").reset_index(drop=True)


def build_all(facts: dict, years: int = 10) -> dict:
    """Top-level entry point. Returns a dict with three wide DataFrames."""
    return {
        "income": pivot_to_wide(build_duration_quarterly(facts, INCOME_CONCEPTS, years)),
        "balance": pivot_to_wide(build_instant_quarterly(facts, BALANCE_CONCEPTS, years)),
        "cashflow": pivot_to_wide(build_duration_quarterly(facts, CASHFLOW_CONCEPTS, years)),
    }


# Backwards-compat alias (older code called this `pivot_metrics`)
pivot_metrics = pivot_to_wide
