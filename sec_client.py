"""Talk to SEC EDGAR to get company data.

EDGAR is free, no API key, no signup - you just need to send a polite
User-Agent header identifying yourself. SEC blocks default requests UA.

Two endpoints we use:
  1. /files/company_tickers.json   - the master list of US-listed tickers
  2. /api/xbrl/companyfacts/CIK####.json   - one company's full filing history

Both get cached on disk for 24 hours, so repeat lookups are instant and we
stay polite to SEC.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import diskcache
import requests


# On-disk cache (2 GB limit). Stores both the ticker lookup table and each
# company's full facts JSON so we don't re-download them constantly.
CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
_cache = diskcache.Cache(str(CACHE_DIR), size_limit=2 * 1024**3)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


def _user_agent() -> str:
    """Return the User-Agent to send with every SEC request.

    SEC wants a descriptive string like 'Your Name your@email.com'. We check
    environment variable first, then Streamlit secrets, then fall back to a
    generic dev value.
    """
    ua = os.environ.get("SEC_USER_AGENT")
    if ua:
        return ua
    try:
        import streamlit as st
        secret = st.secrets.get("SEC_USER_AGENT")
        if secret:
            return secret
    except Exception:
        pass
    return "10K-Analyser local-dev contact@example.com"


def _fetch_json(url: str) -> dict:
    """Download a JSON document from SEC, with a polite delay."""
    time.sleep(0.12)  # SEC rate limit is ~10 req/s; we stay well under
    headers = {"User-Agent": _user_agent(), "Accept-Encoding": "gzip, deflate"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


# --------------------------------------------------------------------------- #
# Ticker lookup
# --------------------------------------------------------------------------- #

def load_tickers_map() -> dict:
    """Return a dict mapping TICKER -> {cik, name} for every US-listed filer.

    Result is cached for 24 hours. Both dot and dash ticker variants are
    included (so 'BRK.B' and 'BRK-B' both resolve to Berkshire Hathaway).
    """
    cached = _cache.get("tickers_map")
    if cached is not None:
        return cached

    raw = _fetch_json(TICKERS_URL)
    result: dict = {}
    for entry in raw.values():
        ticker_upper = entry["ticker"].upper()
        ticker_dashed = ticker_upper.replace(".", "-")
        record = {
            "cik": str(entry["cik_str"]).zfill(10),
            "name": entry["title"],
        }
        result[ticker_upper] = record
        result[ticker_dashed] = record

    _cache.set("tickers_map", result, expire=86400)
    return result


def resolve_ticker(ticker: str) -> dict:
    """Look up a single ticker symbol. Raises ValueError if not found."""
    query = (ticker or "").upper().strip().replace(".", "-")
    if not query:
        raise ValueError("Ticker is empty.")
    tickers = load_tickers_map()
    if query not in tickers:
        raise ValueError(f"Ticker '{ticker}' not found (US-listed companies only).")
    return tickers[query]


def fuzzy_resolve(query: str) -> dict:
    """Look up a ticker OR company name. Tries these matches in order:

        1. Exact ticker:     'AAPL' -> Apple Inc.
        2. Ticker prefix:    'AAP'  -> AAP (Advance Auto Parts)
        3. Company name:     'apple' -> Apple Inc.

    Returns the same dict as resolve_ticker. Raises ValueError if nothing matches.
    """
    query = (query or "").strip()
    if not query:
        raise ValueError("Please enter a ticker or company name.")

    tickers = load_tickers_map()

    # 1. Exact ticker match
    exact = query.upper().replace(".", "-")
    if exact in tickers:
        return tickers[exact]

    # 2. Ticker prefix - pick the shortest ticker starting with this
    prefix_hits = [(t, info) for t, info in tickers.items() if t.startswith(exact)]
    if prefix_hits:
        prefix_hits.sort(key=lambda pair: len(pair[0]))
        return prefix_hits[0][1]

    # 3. Company name substring - prefer names that START with the query,
    #    then the shortest name (usually the canonical entry).
    query_lower = query.lower()
    name_hits = [(t, info) for t, info in tickers.items() if query_lower in info["name"].lower()]
    if name_hits:
        def score(pair):
            name_lower = pair[1]["name"].lower()
            starts_with_query = 0 if name_lower.startswith(query_lower) else 1
            return (starts_with_query, len(pair[1]["name"]))
        name_hits.sort(key=score)
        return name_hits[0][1]

    raise ValueError(f"Could not find a match for '{query}'.")


def search_options() -> list[tuple[str, str]]:
    """Return [(display_label, ticker), ...] for every unique company.

    Used to populate dropdowns. Each company appears once even if it has
    multiple ticker variants (dot vs dash).
    """
    cached = _cache.get("search_options")
    if cached is not None:
        return cached

    tickers = load_tickers_map()
    seen_by_cik: dict[str, tuple[str, str]] = {}
    for ticker, info in tickers.items():
        label = f"{ticker} — {info['name']}"
        cik = info["cik"]
        # Prefer the shorter ticker variant (e.g. "BRK-B" over the duplicate)
        if cik not in seen_by_cik or len(ticker) < len(seen_by_cik[cik][1]):
            seen_by_cik[cik] = (label, ticker)

    options = sorted(seen_by_cik.values(), key=lambda pair: pair[1])
    _cache.set("search_options", options, expire=86400)
    return options


# --------------------------------------------------------------------------- #
# Company facts download
# --------------------------------------------------------------------------- #

def get_company_facts(cik: str) -> dict:
    """Download the complete XBRL facts JSON for one CIK. Cached 24 hours."""
    cache_key = f"facts:{cik}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    data = _fetch_json(COMPANY_FACTS_URL.format(cik=cik))
    _cache.set(cache_key, data, expire=86400)
    return data
