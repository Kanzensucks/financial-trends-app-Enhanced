"""Ask Groq's Llama model to write plain-English insights about the numbers.

Two public functions:

    get_key_insights(ticker, summaries)
        -> 5 bullet points summarizing strengths, risks, and trends.
           Shown at the top of the page.

    get_statement_commentary(ticker, statement, summary)
        -> 2-3 sentences describing the trend of one statement.
           Shown above each tab's charts.

Both fall back to `None` if no Groq API key is configured - the app still
works without AI, just without the commentary panels.

Responses are cached on disk for 24 hours, keyed by ticker + a hash of the
numeric summary, so reloading the same company doesn't burn tokens.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import diskcache
import pandas as pd


CACHE_DIR = Path(__file__).parent / ".cache"
_cache = diskcache.Cache(str(CACHE_DIR))
MODEL = "llama-3.3-70b-versatile"


# --------------------------------------------------------------------------- #
# Groq client setup
# --------------------------------------------------------------------------- #

def _get_api_key() -> str | None:
    """Read the Groq API key from env var or Streamlit secrets. Returns None
    if neither is set - callers should handle that gracefully."""
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("GROQ_API_KEY") or None
    except Exception:
        return None


def _get_client():
    """Instantiate a Groq client, or return None if unavailable."""
    key = _get_api_key()
    if not key:
        return None
    try:
        from groq import Groq
        return Groq(api_key=key)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Prompt building helpers
# --------------------------------------------------------------------------- #

def summarize_df_for_llm(df: pd.DataFrame, value_cols: list[str]) -> dict:
    """Compress a quarterly DataFrame into a small JSON-friendly summary.

    We don't send the raw rows to the LLM - that would waste tokens. Instead
    we extract just the headline numbers for each metric: latest value,
    earliest value, min, max, and the latest YoY %.
    """
    if df is None or df.empty:
        return {}

    summary: dict = {}
    for col in value_cols:
        if col not in df.columns:
            continue
        series = df.dropna(subset=[col])
        if series.empty:
            continue

        latest_row = series.iloc[-1]
        earliest_row = series.iloc[0]
        entry = {
            "latest_period": _period(latest_row),
            "latest_value": _round(latest_row[col]),
            "earliest_period": _period(earliest_row),
            "earliest_value": _round(earliest_row[col]),
            "min": _round(series[col].min()),
            "max": _round(series[col].max()),
        }

        yoy_col = f"{col}_yoy"
        if yoy_col in series.columns:
            yoy_values = series[yoy_col].dropna()
            if not yoy_values.empty:
                entry["latest_yoy_pct"] = round(float(yoy_values.iloc[-1]) * 100, 1)
                entry["median_yoy_pct"] = round(float(yoy_values.median()) * 100, 1)

        summary[col] = entry
    return summary


def _period(row) -> str:
    try:
        return f"FY{int(row['fy'])} {row['fp']}"
    except Exception:
        return str(row.get("end"))


def _round(value) -> float | None:
    try:
        return round(float(value), 2)
    except Exception:
        return None


def _cache_key(ticker: str, kind: str, payload) -> str:
    """Build a stable cache key from the input summary."""
    payload_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    return f"ai:{kind}:{ticker}:{payload_hash}"


def _call_groq(messages: list[dict], max_tokens: int = 400) -> str | None:
    """Send a chat-completion request to Groq. Returns the response text,
    None if the client isn't configured, or an error string on failure."""
    client = _get_client()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=max_tokens,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        return f"(AI error: {e})"


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def get_key_insights(ticker: str, summaries: dict) -> list[str] | None:
    """Generate the 5 bullet-point headline insights for a ticker.

    Returns None if no API key is set, otherwise a list of 5 short strings.
    """
    if _get_api_key() is None:
        return None

    cache_key = _cache_key(ticker, "insights", summaries)
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    prompt = (
        f"You are a sharp financial analyst. Given this compact summary of {ticker}'s "
        f"quarterly SEC filings over ~10 years, produce exactly 5 bullet points covering: "
        f"(1) top strength, (2) top risk, (3) a notable inflection point or regime change, "
        f"(4) growth trajectory, (5) profitability trend.\n"
        f"Rules: each bullet must be under 25 words, reference at least one specific number, "
        f"no hedging, no disclaimers. Output only the bullets, one per line, prefixed with '• '.\n\n"
        f"Data (figures are raw USD unless noted):\n{json.dumps(summaries, indent=2, default=str)}"
    )
    text = _call_groq([{"role": "user", "content": prompt}], max_tokens=450)
    if not text:
        return None

    # Extract bullet lines, stripping leading markers
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    bullets = [l.lstrip("•-* ").strip() for l in lines if l.startswith(("•", "-", "*"))]
    if not bullets:
        bullets = lines[:5]

    _cache.set(cache_key, bullets, expire=86400)
    return bullets


def get_statement_commentary(ticker: str, statement_name: str, summary: dict) -> str | None:
    """Generate a 2-3 sentence trend commentary for one statement (income,
    balance, or cash flow). Returns None if no API key is configured."""
    if _get_api_key() is None or not summary:
        return None

    cache_key = _cache_key(ticker, f"comm:{statement_name}", summary)
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    prompt = (
        f"You are a sharp financial analyst. Write 2-3 sentences describing the trend in "
        f"{ticker}'s {statement_name} over the last ~10 years of quarterly filings. "
        f"Focus on year-over-year growth at the quarterly grain (same quarter vs prior-year "
        f"same quarter) and any inflection points. Reference at least two specific numbers. "
        f"No hedging, no disclaimers, no 'in conclusion'.\n\n"
        f"Data:\n{json.dumps(summary, indent=2, default=str)}"
    )
    text = _call_groq([{"role": "user", "content": prompt}], max_tokens=220)
    if not text:
        return None

    _cache.set(cache_key, text, expire=86400)
    return text
