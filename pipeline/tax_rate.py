# tax_rate.py — normalized tax rate per company: recent effective rate, else statutory rate for its country
import pandas as pd

from config import COMPS, TARGETS, TAX_LOOKBACK_YEARS, TAX_RATE_BOUNDS, STATUTORY_TAX, DEFAULT_TAX
from data_sources import load_fundamentals, yf_info


def statutory_rate(ticker):
    country = yf_info(ticker).get("country")
    return STATUTORY_TAX.get(country, DEFAULT_TAX), country


def tax_rate(ticker, fund=None):
    """Returns (rate, source). Averages yearly effective rates over the lookback window,
    skipping loss years and one-off years outside TAX_RATE_BOUNDS."""
    fund = load_fundamentals(ticker) if fund is None else fund
    recent = fund.sort_index().tail(TAX_LOOKBACK_YEARS)
    lo, hi = TAX_RATE_BOUNDS
    rates = []
    for _, r in recent.iterrows():
        if pd.notna(r.income_tax) and pd.notna(r.pretax_income) and r.pretax_income > 0:
            rate = r.income_tax / r.pretax_income
            if lo <= rate <= hi:
                rates.append(rate)
    if rates:
        return sum(rates) / len(rates), f"effective ({len(rates)}y avg)"
    rate, country = statutory_rate(ticker)
    return rate, f"statutory ({country or 'unknown country'})"


def tax_table(tickers):
    rows = []
    for t in tickers:
        try:
            rate, source = tax_rate(t)
        except FileNotFoundError as e:
            print(f"{t}: {e}")
            rate, source = None, "no data"
        rows.append(dict(ticker=t, tax_rate=rate, tax_rate_source=source))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    print(tax_table(TARGETS + COMPS).to_string())
