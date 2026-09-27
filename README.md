# DCF Calculator

A Python pipeline for a Citadel stock-pitch competition: pulls financial statements from SEC EDGAR and Yahoo Finance, builds a comparable-company set, and values the subject company (Adobe, ADBE) with a 5-year unlevered DCF. Tickers are configurable, and the pipeline works for US and foreign filers.

## Setup

```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install pandas yfinance edgartools
```

## Pipeline (run in order from the repo root)

| Step | File | What it does |
|---|---|---|
| — | `pipeline/config.py` | Target and comp tickers, tax assumptions, data paths. Change tickers here. |
| — | `pipeline/data_sources.py` | Shared fetch layer: EDGAR (10-K / 20-F / 40-F) with a yfinance fallback, normalized into one standard table per company, plus FX helpers. |
| 1 | `pipeline/pull_financials.py` | Pulls statements for the target companies. |
| 1 | `pipeline/comps_financials.py` | Pulls statements for the comp set. |
| 2 | `pipeline/comps_beta.py` | Comp market data in USD: levered/unlevered beta, debt, market cap, P/S, tax rate. |
| — | `pipeline/tax_rate.py` | Multi-year effective tax rate, with a statutory fallback. |
| 3 | `pipeline/build_drivers.py` | Historical per-year drivers (margins, D&A, SBC, capex, working capital) and unlevered FCF. |
| 4 | `pipeline/relever_beta.py` | Relevers the comps' median unlevered beta at ADBE's capital structure. |
| 5 | `pipeline/cost_of_equity.py` | CAPM cost of equity. |
| 6 | `pipeline/wacc.py` | Cost of debt, capital weights, WACC. |
| 7 | `pipeline/dcf_valuation.py` | 5-year DCF, Gordon Growth terminal value, implied price per share. |
| 8 | `pipeline/sensitivity.py` | Price sensitivity to WACC, terminal growth and FCF margin. |
| 9 | `pipeline/multiple_check.py` | Cross-checks the DCF's implied EV/EBITDA against the comps. |

## Data

- `data/raw/` — statements as pulled, one CSV per company per statement
- `data/fundamentals/` — normalized per-company tables used by the model
- `data/processed/` — pipeline outputs (`comps_beta_raw.csv`, `drivers.csv`)

Inputs marked `PLACEHOLDER` in the scripts (growth rates, risk-free rate, ERP, consensus target) still need to be confirmed.
