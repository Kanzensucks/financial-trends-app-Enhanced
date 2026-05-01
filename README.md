# 10K Analyser

A small local website that lets you type any US stock ticker (or company
name) and instantly shows **10 years of quarterly financial data** with
pretty charts, year-over-year comparisons, trailing-twelve-month trends,
and AI-generated commentary.

Inspired by simplywall.st — but free, local, and yours.

![screenshot placeholder]

---

## What you can do with it

- **Search by ticker or name.** Type `AAPL`, `apple`, `nvidia`, `johnson`,
  or `berkshire` and press Enter — whichever you know, it finds the company.
- **See 10 years of quarters.** Revenue, Gross Profit, Operating Income,
  Net Income, Assets, Equity, Cash, Debt, Operating Cash Flow, Free Cash
  Flow — all broken down quarter by quarter.
- **Compare like quarters.** Every chart has a "YoY %" panel comparing each
  quarter to the *same quarter a year ago* — not the previous quarter —
  so seasonal businesses make sense at a glance.
- **See the annualized picture.** The "TTM" (trailing twelve months) line
  sums the last 4 quarters at every point, so you see the smooth underlying
  trend without the quarterly zig-zag.
- **Standard ratios.** Gross margin, operating margin, net margin, ROA,
  ROE, current ratio, debt/equity — computed automatically from the raw
  filings.
- **AI commentary.** Groq's Llama 3.3 70B reads the numbers and writes a
  short, plain-English summary of what's happening (strengths, risks,
  inflection points). Optional — the app works without it.
- **Financial statement tables** laid out the traditional way, with
  metrics as rows and periods as columns, newest first.

---

## What you need before you start

1. **Python 3.10 or newer** installed.
   On Windows: get it from [python.org](https://www.python.org/downloads/).
   On Mac: `brew install python` or use python.org.

2. **A Groq API key (optional, free).**
   Sign up at [console.groq.com](https://console.groq.com), click
   "API Keys", create one. It looks like `gsk_...`. Without it, the
   "AI Key Insights" panel is empty but everything else still works.

---

## Setup (one time, takes 2 minutes)

Open a terminal in the project folder, then:

1. **Install the dependencies.**

   Pick the command that works in YOUR terminal:

   | Terminal | Command |
   |----------|---------|
   | **PowerShell (Windows)** | `python -m pip install -r requirements.txt` |
   | **Command Prompt (Windows)** | `python -m pip install -r requirements.txt` |
   | **Mac / Linux terminal** | `pip install -r requirements.txt` |
   | **Nothing works?** | Use the full path: `C:\Python314\python.exe -m pip install -r requirements.txt` (adjust the path to wherever Python is installed on your machine) |

   > **"pip/python is not recognized"?** This means Python isn't on your
   > system PATH. Either use the full path as shown above, or re-run the
   > Python installer and check **"Add Python to PATH"** during setup.

2. **Create your secrets file.**

   Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`,
   open it in any text editor (Notepad, VS Code, etc.), and fill in:

   ```toml
   # SEC requires you to identify yourself with a descriptive User-Agent.
   # Any name + email works — it's not validated, just logged.
   SEC_USER_AGENT = "Your Name your.email@example.com"

   # Optional — paste your free Groq API key here to enable AI insights.
   GROQ_API_KEY = "gsk_your_key_here"
   ```

   How to copy the file by terminal, if you prefer:

   | Terminal | Command |
   |----------|---------|
   | **PowerShell** | `Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml` |
   | **Command Prompt** | `copy .streamlit\secrets.toml.example .streamlit\secrets.toml` |
   | **Mac / Linux** | `cp .streamlit/secrets.toml.example .streamlit/secrets.toml` |

That's it. No API registration, no database, no cloud account.

---

## Running it

Pick the command that works in YOUR terminal:

| Terminal | Command |
|----------|---------|
| **PowerShell (Windows)** | `python -m streamlit run app.py` |
| **Command Prompt (Windows)** | `python -m streamlit run app.py` |
| **Mac / Linux** | `streamlit run app.py` |
| **Nothing works?** | `C:\Python314\python.exe -m streamlit run app.py` (adjust path) |

Your browser opens at http://localhost:8501. To stop the app, press
**Ctrl+C** in the terminal.

> **Why `python -m streamlit` instead of just `streamlit`?** On Windows,
> the `streamlit` shortcut sometimes doesn't get added to your PATH.
> Running it through `python -m` always works as long as Python itself
> is on your PATH.

---

## How to use it

1. **Type a ticker or company name** in the sidebar search box and press
   **Enter**. Examples that work: `AAPL`, `apple`, `microsoft corp`,
   `NVDA`, `nvidia`, `BRK-B`, `berkshire`, `johnson & johnson`.
2. **Change the time range** with the "Years of history" slider (anywhere
   from 3 to 15 years). The charts update immediately.
3. **Switch the unit** between billions ($B) and millions ($M) for
   smaller companies. Also instant.
4. **Click between the five tabs** — Income, Balance Sheet, Cash Flow,
   Ratios, Raw Data. Each tab has:
   - An AI trend summary (if you set up Groq)
   - A 2x2 chart grid, each metric showing:
     - Quarterly bars (colored by quarter within the fiscal year)
     - Year-over-year % bars (green = up, red = down)
     - TTM line (trailing twelve months rolling sum)
   - A collapsible data table
5. **The Raw Data tab** has all four statements as proper pivot tables
   (metrics as rows, newest quarter on the left), plus a CSV download
   button and a toggle to show TTM values instead of per-quarter values.

---

## How it works under the hood

Five small Python files, one for each job:

| File | What it does |
|------|---|
| `app.py` | The Streamlit UI — layout, tabs, charts, tables. |
| `sec_client.py` | Talks to SEC EDGAR. Looks up tickers, downloads the JSON "company facts" blob, caches everything on disk for 24 hours. |
| `extract.py` | Reads the raw SEC JSON and turns it into clean quarterly tables. Handles the tricky bits like year-to-date vs per-quarter reporting and Q4 derivation. |
| `metrics.py` | Computes year-over-year growth, trailing twelve months, and standard financial ratios. |
| `charts.py` | Builds the Plotly figures with a consistent dark theme and monochromatic palette. |
| `ai_layer.py` | Sends a compact numeric summary to Groq and gets back plain-English commentary. Caches the responses too. |

### Where the data comes from

[SEC EDGAR's XBRL Company Facts API](https://data.sec.gov/api/xbrl/companyfacts/).
It's a public US government service — no signup, no API key, no trial
tier. It returns one JSON file per company containing every number they
have ever filed on form 10-K, 10-Q, 8-K, etc., with their reporting
periods attached.

### The one weird thing about SEC data

When a company files their annual 10-K, they include comparative numbers
from prior years. SEC tags those comparative numbers with the **current**
filing's fiscal-year label, which makes naive grouping by fiscal year
produce garbage (you'd see a 2018 period tagged as `fy=2020`).

`extract.py` sidesteps this by grouping facts on the actual `start` and
`end` dates of each period, never trusting the `fy` field. That's why
the code has comments like *"ignore the fy tag and pivot on the period
dates"* — it's working around a real data quirk, not over-engineering.

### Q4 is derived, not reported

10-K annual filings report the full fiscal year, never Q4 alone. We
compute Q4 as `FullYear − (Q1 + Q2 + Q3)`. That's the industry-standard
approach and the math always balances.

### Caching

- **SEC JSON** is cached on disk for 24 hours (`.cache/` folder).
- **Groq responses** are cached by (ticker + a hash of the numbers) for
  24 hours, so re-opening a company doesn't re-spend tokens.
- **The ticker lookup table** is also cached 24 hours.

Delete the `.cache/` folder at any time to force everything to re-download.

---

## Troubleshooting

**"Ticker 'XYZ' not found"** — SEC only has US-listed companies. Foreign
exchanges (LSE, HKEX, TSE, etc.) aren't in EDGAR.

**"Failed to fetch SEC data"** — most likely your `SEC_USER_AGENT` is
blank. SEC rejects requests without a descriptive User-Agent. Put any
name + email in `.streamlit/secrets.toml`.

**The AI Insights panel is empty** — you didn't set `GROQ_API_KEY`. Get
a free one at [console.groq.com](https://console.groq.com) and paste it
into `.streamlit/secrets.toml`. Or just ignore it — the rest works.

**Numbers look weird for a bank/REIT/insurance company** — those
industries use different GAAP line items (like "InterestIncomeOperating"
instead of "Revenue"). The app currently targets the standard
industrial/tech reporting convention. Check the Raw Data tab to see
what IS reported.

**Charts are mostly empty for a small company** — micro-caps sometimes
only file the bare minimum (NetIncome and balance sheet). The app shows
a "not reported" placeholder for missing metrics instead of an empty
chart.

---

## Project layout

```
10K-Analyser/
├── app.py                       # The Streamlit app
├── sec_client.py                # SEC EDGAR downloader
├── extract.py                   # Raw JSON → quarterly tables
├── metrics.py                   # YoY, TTM, ratios
├── charts.py                    # Plotly figures
├── ai_layer.py                  # Groq LLM integration
├── styles.py                    # Custom CSS
├── valuation.py                 # Valuation tab (DCF engine) — added
├── requirements.txt             # Python dependencies
├── .streamlit/
│   ├── config.toml              # Streamlit theme
│   ├── secrets.toml             # Your API keys (create this)
│   └── secrets.toml.example     # Template for the above
├── .cache/                      # Auto-created; contains cached downloads
└── data/                        # Auto-created; contains valuation logs
    ├── valuation_log.csv        # Log of every DCF run
    └── eval_results.csv         # Evaluation results (auto-generated)
```

---

## License / disclaimer

This is a personal project for learning and research. It's not investment
advice. SEC data is public domain. Groq API usage is governed by Groq's
terms of service.

---

## Valuation Module — Change Log

All changes live in one new file: `valuation.py`. The only modification
to the original codebase was adding one import line and one tab entry
in `app.py`.

---

### What was added

**New dependency**

`yfinance` was added to `requirements.txt`. It fetches live market data
(price, analyst targets, shares outstanding, cash flow history) directly
from Yahoo Finance.

---

**New tab: 💰 Valuation**

A sixth tab was added to the right of Raw Data. It is self-contained —
all logic lives in `valuation.py`.

---

**Live market data banner**

Three cards display at the top of the tab for any valid ticker:

| Card | Source | Notes |
|------|--------|-------|
| Live Price | yfinance `currentPrice` | Refreshed every 10 minutes |
| Analyst Consensus | yfinance `targetMeanPrice` | Mean of all covering analysts |
| Analyst Verdict | Derived | UNDER if target >10% above price, OVER if >10% below, else FAIR |

Both the Analyst Consensus and Analyst Verdict cards have an **ⓘ tooltip**
showing the data source and the exact number of analysts covering that
stock (e.g. `Yahoo Finance / 42 analysts`). The count comes from
`numberOfAnalystOpinions` — it is the real figure for that ticker, not
an estimate.

---

**DCF calculator**

Function: `calculate_dcf(fcf_history, shares_outstanding, net_debt,
discount_rate, terminal_growth, years_projected, growth_y1_3, growth_y4_5)`

Method:

1. Project FCF year-by-year — `growth_y1_3` for years 1–3, `growth_y4_5`
   for years 4 onwards.
2. Discount each year back to present value at `discount_rate`.
3. Terminal value via Gordon Growth Model:
   `TV = FCF_final × (1 + terminal_growth) / (discount_rate − terminal_growth)`
4. Enterprise value = sum of discounted FCFs + discounted terminal value.
5. Equity value = enterprise value − net debt.
6. Fair value per share = equity value ÷ shares outstanding.

Raises `ValueError` if `discount_rate ≤ terminal_growth`.

---

**Five assumption sliders**

| Slider | Range | Default | ⓘ Tooltip |
|--------|-------|---------|------------|
| Discount rate (WACC) | 5–15% | 10% | Generic guidance |
| Terminal growth rate | 0–4% | 2.5% | Generic guidance |
| Years projected | 3–10 | 5 | Generic guidance |
| FCF growth — years 1–3 | −5% to 20% | 6% | Stock-specific (from FCF history) |
| FCF growth — years 4+ | −5% to 15% | 4% | Stock-specific (from FCF history) |

The two FCF growth sliders show stock-specific recommendations derived
from the ticker's actual historical FCF data fetched via yfinance. The
suggested near-term rate is a weighted blend of the recent 2-year growth
and the full historical average (60/40). The suggested long-term rate
mean-reverts toward 3%.

---

**Results output**

After clicking Calculate, the tab shows:

- **DCF Fair Value** — as an `st.metric` with % delta vs current price
- **Current Price** — live from yfinance
- **Verdict** — UNDERVALUED / OVERVALUED / FAIRLY VALUED with colour coding
- **Sensitivity chart** — Plotly line chart sweeping discount rate 5–15%,
  with a dashed red line at the current price
- **AI Insight** — 2–3 sentence plain-English explanation from Groq
  Llama 3.3 70B, displayed beside the chart. Cached for 1 hour. Hidden
  if no API key is set.

---

**CSV run logger**

Every successful DCF calculation is appended to `data/valuation_log.csv`
with columns: `timestamp`, `ticker`, `method`, `fair_value`,
`current_price`, `verdict`, `analyst_target`, `analyst_verdict`,
`discount_rate`.

---

**Automated evaluation**

On the first page load of each browser session, a background thread
silently runs DCF on 30 real US tickers (5 per sector across Technology,
Healthcare, Consumer, Financials, Energy, and Industrials) using
standardised default assumptions. Results are written to
`data/eval_results.csv` with columns: `ticker`, `sector`, `live_price`,
`dcf_fair_value`, `analyst_target`, `dcf_verdict`, `analyst_verdict`,
`match`, all DCF assumption parameters, and a `note` for any skipped
tickers.

**Evaluation methodology:** analyst mean price target (aggregated by
Yahoo Finance from all covering analysts) is used as ground truth.
A ticker is scored as a match if the DCF verdict and analyst verdict
agree. This is an imperfect but immediately available external benchmark.
Forward returns would be a stronger ground truth but require a 12-month
lag.

---

### Known limitations

- **DCF is assumption-sensitive.** Small changes to the discount rate or
  terminal growth rate produce large swings in fair value. The sensitivity
  chart makes this visible.
- **Unreliable for certain company types.** Banks, REITs, and insurance
  companies use different capital structures where free cash flow does not
  capture value the same way. Early-stage or negative-FCF companies
  (e.g. high-growth tech) also produce unreliable DCF outputs.
- **yfinance data quality.** FCF history and analyst targets are sourced
  from Yahoo Finance via yfinance. Data can be patchy for smaller
  companies, foreign-listed ADRs, or companies with unusual fiscal years.
- **Analyst consensus bias.** Using analyst targets as ground truth
  introduces positive agreement bias — both DCF and analyst models share
  structural assumptions. The evaluation accuracy figure should be read
  as agreement rate, not predictive accuracy.
- **US-listed companies only.** The app sources fundamentals from SEC
  EDGAR, which only covers US-listed companies. The Valuation tab
  inherits this constraint.