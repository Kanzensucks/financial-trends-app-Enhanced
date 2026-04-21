"""Build the Plotly charts used throughout the app.

Palette strategy: analogous cool range (indigo → blue → teal → cyan) for
quarterly bars, warm amber for TTM and highlights, semantic green/red for
directional growth. This gives visual variety while staying harmonious.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


# --------------------------------------------------------------------------- #
# Palette — analogous cool for bars, warm amber for highlights
# --------------------------------------------------------------------------- #

QUARTER_COLORS = {
    "Q1": "#6366F1",  # indigo
    "Q2": "#3B82F6",  # blue
    "Q3": "#14B8A6",  # teal
    "Q4": "#22D3EE",  # cyan
}

ACCENT = "#14B8A6"         # primary teal (ratio lines, area fills)
ACCENT_FILL = "rgba(20, 184, 166, 0.12)"
WARM = "#F59E0B"           # amber (TTM line, highlights)
WARM_FILL = "rgba(245, 158, 11, 0.10)"
POSITIVE = "#34D399"       # emerald green (softer than pure green)
NEGATIVE = "#FB7185"       # rose (softer than pure red)
TEXT = "#E2E8F0"
GRID = "#1E293B"
LINE_MUTED = "#94A3B8"


def _layout(height: int) -> dict:
    """Shared Plotly layout for every chart."""
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color=TEXT, size=12),
        margin=dict(l=50, r=20, t=18, b=30),
        hovermode="x unified",
        showlegend=False,
        height=height,
        xaxis=dict(gridcolor=GRID, showline=False, zeroline=False),
        yaxis=dict(gridcolor=GRID, showline=False, zeroline=False),
    )


def _period_label(row) -> str:
    try:
        return f"FY{int(row['fy'])} {row['fp']}"
    except Exception:
        return str(row.get("fp", ""))


# --------------------------------------------------------------------------- #
# Chart builders
# --------------------------------------------------------------------------- #

def trend_chart(df: pd.DataFrame, col: str, unit_divisor: float = 1e9, unit_label: str = "$B"):
    """Grouped bar chart colored by fiscal quarter (indigo→blue→teal→cyan)."""
    if df is None or df.empty or col not in df.columns:
        return None
    data = df.dropna(subset=[col]).copy()
    if data.empty:
        return None

    data["label"] = data.apply(_period_label, axis=1)
    data["y"] = data[col] / unit_divisor

    fig = go.Figure()
    for fp in ("Q1", "Q2", "Q3", "Q4"):
        subset = data[data["fp"] == fp]
        if subset.empty:
            continue
        fig.add_trace(go.Bar(
            x=subset["end"],
            y=subset["y"],
            name=fp,
            marker_color=QUARTER_COLORS[fp],
            marker_line=dict(width=0),
            customdata=subset["label"],
            hovertemplate="%{customdata}<br>%{y:.2f} " + unit_label + "<extra></extra>",
        ))

    # 4-quarter rolling average (muted line so it doesn't fight the bars)
    chronological = data.sort_values("end")
    rolling_avg = chronological["y"].rolling(4, min_periods=2).mean()
    fig.add_trace(go.Scatter(
        x=chronological["end"],
        y=rolling_avg,
        mode="lines",
        name="4Q avg",
        line=dict(color=LINE_MUTED, width=1.5, dash="dot"),
        hoverinfo="skip",
    ))

    layout = _layout(260)
    layout["showlegend"] = True
    fig.update_layout(
        **layout,
        barmode="group",
        bargap=0.15,
        legend=dict(
            orientation="h", x=1, xanchor="right", y=1.02,
            font=dict(size=10, color=LINE_MUTED),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    fig.update_yaxes(title=unit_label, tickprefix="$")
    return fig


def yoy_chart(df: pd.DataFrame, col: str):
    """Green/red bars of year-over-year % change, with outlier clipping."""
    yoy_col = f"{col}_yoy"
    if df is None or df.empty or yoy_col not in df.columns:
        return None
    data = df.dropna(subset=[yoy_col]).copy()
    if data.empty:
        return None

    data["pct_raw"] = data[yoy_col] * 100
    low_q, high_q = data["pct_raw"].quantile([0.05, 0.95])
    y_min = max(min(-50.0, low_q - 20), -300.0)
    y_max = min(max(50.0, high_q + 20), 300.0)

    data["pct"] = data["pct_raw"].clip(lower=y_min, upper=y_max)
    data["color"] = data["pct_raw"].apply(lambda v: POSITIVE if v >= 0 else NEGATIVE)
    data["label"] = data.apply(_period_label, axis=1)

    fig = go.Figure(go.Bar(
        x=data["end"],
        y=data["pct"],
        marker_color=data["color"],
        marker_line=dict(width=0),
        customdata=data[["label", "pct_raw"]].values,
        hovertemplate="%{customdata[0]}<br>YoY: %{customdata[1]:.1f}%<extra></extra>",
    ))
    fig.update_layout(**_layout(180))
    fig.update_yaxes(title="YoY %", ticksuffix="%", range=[y_min, y_max])
    fig.add_hline(y=0, line_color="#334155", line_width=1)
    return fig


def ttm_chart(df: pd.DataFrame, col: str, unit_divisor: float = 1e9, unit_label: str = "$B"):
    """Warm amber area-line for trailing twelve months — visually distinct from
    the cool-toned quarterly bars above it."""
    ttm_col = f"{col}_ttm"
    if df is None or df.empty or ttm_col not in df.columns:
        return None
    data = df.dropna(subset=[ttm_col]).copy()
    if data.empty:
        return None

    data["y"] = data[ttm_col] / unit_divisor
    data["label"] = data.apply(_period_label, axis=1)

    fig = go.Figure(go.Scatter(
        x=data["end"],
        y=data["y"],
        mode="lines",
        line=dict(color=WARM, width=2.5, shape="spline"),
        fill="tozeroy",
        fillcolor=WARM_FILL,
        customdata=data["label"],
        hovertemplate="%{customdata} (TTM)<br>%{y:.2f} " + unit_label + "<extra></extra>",
    ))
    fig.update_layout(**_layout(200))
    fig.update_yaxes(title=f"TTM {unit_label}", tickprefix="$")
    return fig


def ratio_line_chart(df: pd.DataFrame, col: str, is_pct: bool = True):
    """Smooth teal line chart for margins and ratios."""
    if df is None or df.empty or col not in df.columns:
        return None
    data = df.dropna(subset=[col]).copy()
    if data.empty:
        return None

    data["label"] = data.apply(_period_label, axis=1)
    multiplier = 100 if is_pct else 1
    suffix = "%" if is_pct else "x"
    fig = go.Figure(go.Scatter(
        x=data["end"],
        y=data[col] * multiplier,
        mode="lines+markers",
        line=dict(color=ACCENT, width=2.5, shape="spline"),
        marker=dict(size=5, color=ACCENT),
        fill="tozeroy",
        fillcolor=ACCENT_FILL,
        customdata=data["label"],
        hovertemplate="%{customdata}<br>%{y:.2f}" + suffix + "<extra></extra>",
    ))
    fig.update_layout(**_layout(240))
    if is_pct:
        fig.update_yaxes(ticksuffix="%")
    return fig
