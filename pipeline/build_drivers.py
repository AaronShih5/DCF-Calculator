# build_drivers.py — step 2: turn canonical fundamentals into a clean per-year FCF driver table
import pandas as pd

from config import TARGETS, PROCESSED_DIR
from data_sources import load_fundamentals
from tax_rate import tax_rate


def zero_if_nan(x):
    return 0.0 if pd.isna(x) else x


def build(ticker):
    fund = load_fundamentals(ticker).sort_index()
    rate, rate_source = tax_rate(ticker, fund)

    rows = []
    for year, r in fund.iterrows():
        if pd.isna(r.revenue) or pd.isna(r.operating_income):
            continue
        reported_rate = (r.income_tax / r.pretax_income
                         if pd.notna(r.income_tax) and pd.notna(r.pretax_income) and r.pretax_income else None)
        # NOPAT uses the normalized rate; single-year rates swing with one-offs (e.g. valuation allowance releases)
        nopat = r.operating_income * (1 - rate)
        # cash impact of working capital: receivables up = cash out; deferred revenue / payables up = cash in
        wc = (-zero_if_nan(r.chg_receivables) + zero_if_nan(r.chg_deferred_revenue)
              + zero_if_nan(r.chg_payables_accrued))
        capex = abs(zero_if_nan(r.capex))
        # Standard Unlevered FCF: NOPAT + non-cash charges (D&A, SBC) - capex - change in operating NWC.
        # wc above is already the cash impact (NWC increase = negative), so "+ wc" is the "- ΔNWC" term.
        fcf = nopat + zero_if_nan(r.da) + zero_if_nan(r.sbc) - capex + wc

        rows.append(dict(
            ticker=ticker, year=year, currency=r.currency, revenue=r.revenue,
            operating_income=r.operating_income, op_margin=r.operating_income / r.revenue,
            operating_income_derived=bool(r.operating_income_derived),
            tax_rate=rate, tax_rate_source=rate_source, reported_tax_rate=reported_rate,
            da=r.da, sbc=r.sbc, capex=r.capex, wc_change=wc, nopat=nopat, fcf=fcf,
            ocf_actual=r.ocf,
            fcf_check=(r.ocf - capex) if pd.notna(r.ocf) else None,
        ))

    if not rows:
        print(f"⚠ {ticker}: 0 rows — revenue/operating income missing for every year")
    return pd.DataFrame(rows)


if __name__ == "__main__":
    results = []
    for t in TARGETS:
        try:
            df = build(t)
        except FileNotFoundError as e:
            print(f"⚠ {t}: {e}")
            continue
        if not df.empty:
            results.append(df)

    out = pd.concat(results, ignore_index=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(PROCESSED_DIR / "drivers.csv", index=False)
    latest = out.sort_values("year").groupby("ticker").tail(1)
    print(latest[["ticker", "year", "currency", "revenue", "op_margin", "tax_rate",
                  "tax_rate_source", "fcf", "fcf_check"]].to_string(index=False))
    print("\nTickers with data:", sorted(out.ticker.unique()))
