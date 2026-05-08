# 10K Analyser

A web app that lets you type any US stock ticker and instantly see 10 years of quarterly financial data, standard ratios, AI commentary, and a DCF valuation — all in one place.

**Live app:** https://financial-trends-app-enhancedgit-6mnivetctn5a785hnrnx8o.streamlit.app

Inspired by simplywall.st — free, open source, and built for students and retail investors who want to understand a company's financials without paying for a Bloomberg terminal.

---

## What it does

- **Search by ticker or company name.** Type `AAPL`, `apple`, `nvidia`, or `johnson & johnson` and press Enter.
- **10 years of quarterly financials.** Revenue, Gross Profit, Operating Income, Net Income, Assets, Equity, Cash, Debt, Operating Cash Flow, Free Cash Flow — all charted quarter by quarter.
- **Year-over-year comparisons.** Every chart includes a YoY % panel comparing each quarter to the same quarter a year ago.
- **TTM trend line.** Trailing twelve months rolling sum smooths out seasonal noise.
- **Standard ratios.** Gross margin, operating margin, net margin, ROA, ROE, current ratio, debt/equity — computed automatically.
- **AI commentary.** Groq's Llama 3.3 70B summarises the numbers in plain English. Optional — everything else works without it.
- **DCF Valuation tab.** Runs a discounted cash flow model on live yfinance data with adjustable assumptions, a sensitivity chart, and comparison against the analyst price target range.

---

## How to run locally

**Requirements:** Python 3.10+

```bash
pip install -r requirements.txt
streamlit run app.py
```

Add your API keys to `.streamlit/secrets.toml` (copy from `.streamlit/secrets.toml.example`):

```toml
SEC_USER_AGENT = "Your Name your.email@example.com"
GROQ_API_KEY = "gsk_..."   # optional — get free at console.groq.com
```

---

## Project layout

```
├── app.py            # Streamlit UI — layout, tabs, charts, tables
├── sec_client.py     # SEC EDGAR downloader and disk cache
├── extract.py        # Raw SEC JSON → clean quarterly tables
├── metrics.py        # YoY growth, TTM, financial ratios
├── charts.py         # Plotly figures (dark theme)
├── ai_layer.py       # Groq LLM integration
├── styles.py         # Custom CSS
├── valuation.py      # DCF engine, live market data, evaluation runner
├── requirements.txt
├── .streamlit/
│   ├── config.toml
│   ├── secrets.toml          # Your keys (gitignored)
│   └── secrets.toml.example
├── .cache/           # Auto-created — SEC data cached 24h
└── data/
    ├── valuation_log.csv     # Log of every DCF run
    └── eval_results.csv      # Batch evaluation output
```

---

## Data sources

- **SEC EDGAR XBRL API** — public US government API, no key required. Returns every number a company has ever filed.
- **yfinance** — live price, analyst price targets, shares outstanding, FCF history.
- **Groq (Llama 3.3 70B)** — AI commentary. Free tier available.

---

## DCF Valuation

The valuation tab runs a standard multi-stage DCF:

1. Project FCF using company-specific historical CAGR (capped −5% to +20%)
2. Discount to present value using a sector-specific WACC (8–11%)
3. Terminal value via Gordon Growth Model
4. Equity value = enterprise value − net debt
5. Fair value per share = equity value ÷ shares outstanding

**Evaluation methodology:** DCF fair value is compared against the analyst price target range (low to high) sourced from Yahoo Finance. A result is scored `YES` if the DCF fair value falls within the analyst range, `NO` if outside, and `SKIP` if no range is available or DCF is not applicable (e.g. Financials).

**Evaluation results (100 non-financial US stocks, 8 sectors):**

| Result | Count |
|--------|-------|
| In range (YES) | 16 |
| Out of range (NO) | 83 |
| Skipped | 1 |

The 16 hits cluster in stable healthcare (PFE, MRK, GILD, ZTS) and cash-rich tech past peak growth (QCOM, CRM, NOW, INTU) — companies where the next 5 years roughly mirror the last 5 in FCF terms. The dominant failure pattern is that historical CAGR understates forward-looking analyst optimism, which is methodologically expected: our DCF is a reality check against what the company has done, not a forecast of what it will do.

---

## Known limitations

- **Assumption-sensitive.** Small changes to discount rate or terminal growth produce large fair value swings. The sensitivity chart makes this visible.
- **Not suitable for banks or REITs.** FCF-based DCF is mathematically inappropriate for financial companies. They are excluded from the evaluation.
- **yfinance data quality.** Patchy for smaller companies, ADRs, or unusual fiscal years.
- **US-listed companies only.** SEC EDGAR covers US filers only.
- **Analyst consensus as ground truth.** Both DCF and analyst models share structural assumptions, so the 16% agreement rate reflects convergence, not predictive accuracy.

---

## Disclaimer

This is a university project built for research and learning. Nothing here is investment advice.
