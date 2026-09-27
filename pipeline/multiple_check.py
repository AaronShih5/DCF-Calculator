# multiple_check.py — sanity-check the DCF terminal value against the EV/EBITDA multiples peers trade at
#
# DCF guide p.47: cross-check the Gordon Growth terminal value by converting it into the EV/EBITDA
# multiple it implies. EV/EBITDA is the right lens because both sides are capital-structure-neutral:
# EV counts debt and equity holders, and EBITDA is earned before interest, so comps with very
# different leverage (IBM vs. SNOW) can be compared on the same basis.
#
# Two adjustments to EBITDA, applied identically to every comp and to ADBE:
# 1. Multi-year average (same window/fallback as tax_rate.py): one unusual year can wreck a single-year
#    multiple. DDOG's FY2025 GAAP EBITDA was ~$10M, which made its multiple ~8,570x; averaging several
#    years stops one depressed or inflated year from setting the number.
# 2. Add back stock-based compensation: SBC is a non-cash expense, so GAAP EBITDA understates the cash
#    earnings of SBC-heavy software companies, and by very different amounts across peers. Adding it back
#    puts every company on the same "adjusted EBITDA" basis, consistent with the DCF adding SBC back to FCF.
import pandas as pd

from config import COMPS, PROCESSED_DIR, TAX_LOOKBACK_YEARS
from data_sources import load_fundamentals, fx_rate
from dcf_valuation import run_dcf, TICKER, TOTAL_DEBT_USD, info


def average_recent(fund, values):
    """Average a metric over the most recent TAX_LOOKBACK_YEARS fiscal years that have clean data,
    using fewer years if that's all a ticker has. Returns (value, label) like tax_rate.py's tax_rate_source."""
    vals = values(fund.sort_index().tail(TAX_LOOKBACK_YEARS)).dropna()
    return (vals.mean(), f"{len(vals)}y avg") if len(vals) else (None, "no data")


def adjusted_ebitda_usd(ticker):
    """Multi-year average EBITDA (operating income + D&A) and SBC, in USD, from the same EDGAR
    fundamentals files build_drivers.py reads, so comps and ADBE use one definition."""
    fund = load_fundamentals(ticker)
    fx = fx_rate(fund.currency.iloc[-1])
    # EBITDA = EBIT + D&A: operating profit before non-cash depreciation/amortization and before financing.
    # A year only counts if both pieces are present (NaN in either drops that year).
    ebitda, ebitda_src = average_recent(fund, lambda d: d.operating_income + d.da)
    sbc, sbc_src = average_recent(fund, lambda d: d.sbc)
    ebitda_usd = ebitda * fx if ebitda is not None else None
    sbc_usd = sbc * fx if sbc is not None else 0.0
    # Adjusted EBITDA = average EBITDA + average SBC
    adjusted = ebitda_usd + sbc_usd if ebitda_usd is not None else None
    return dict(avg_ebitda_usd=ebitda_usd, ebitda_source=ebitda_src,
                avg_sbc_usd=sbc_usd, sbc_source=sbc_src, adj_ebitda_usd=adjusted)


# ---- Comps: EV / adjusted EBITDA ----
# Same EV approximation as the WACC weights (market cap + debt, no cash netting), from comps_beta.py's output
comps = pd.read_csv(PROCESSED_DIR / "comps_beta_raw.csv").set_index("ticker").loc[COMPS]
rows = []
for t in COMPS:
    m = adjusted_ebitda_usd(t)
    ev = comps.at[t, "market_cap_usd"] + comps.at[t, "total_debt_usd"]
    # All 13 comps are kept, whatever the result, so the median reflects the full peer set
    multiple = ev / m["adj_ebitda_usd"] if m["adj_ebitda_usd"] else None
    rows.append(dict(ticker=t, ev_usd=ev, **m, ev_adj_ebitda=multiple))
peers = pd.DataFrame(rows)
# Median, not mean: a few very expensive names (e.g. high-growth software) would drag a mean upward
peer_median = peers.ev_adj_ebitda.median()

# ---- ADBE: multiple implied by the DCF, on the same adjusted basis ----
dcf = run_dcf()
year5 = dcf["proj"].iloc[-1]
# Year-5 adjusted EBITDA projected exactly like the DCF: EBIT + D&A + SBC, each at its 5-year average ratio
ebitda_y5 = year5.ebit + year5.da + year5.sbc
# Terminal value is the business's value at the END of year 5, so it's divided by year-5 EBITDA
# (both measured at the same point in time). This is the "exit multiple" the DCF implicitly assumes.
implied_multiple = dcf["terminal_value"] / ebitda_y5
# Shown for reference only: discounted TV is in today's dollars but year-5 EBITDA is 5 years out,
# so this ratio mixes time periods and understates the implied multiple
implied_multiple_discounted = dcf["pv_terminal_value"] / ebitda_y5

# ADBE's own current trading multiple, on the same EV and adjusted-EBITDA definitions as the peers
adbe = adjusted_ebitda_usd(TICKER)
adbe_current_multiple = (info["marketCap"] + TOTAL_DEBT_USD) / adbe["adj_ebitda_usd"]

# ---- Output ----
B = 1e9
money = lambda x: "n/a" if pd.isna(x) else f"{x / B:,.2f}B"
print("Comps — EV / adjusted EBITDA (multi-year avg EBITDA + avg SBC, USD)")
print(peers.to_string(index=False, formatters={
    "ev_usd": lambda x: f"{x / B:,.1f}B", "avg_ebitda_usd": money, "avg_sbc_usd": money,
    "adj_ebitda_usd": money, "ev_adj_ebitda": lambda x: "n/a" if pd.isna(x) else f"{x:.1f}x"}))
print(f"\nPeer median EV/adj. EBITDA ({peers.ev_adj_ebitda.notna().sum()} comps):   {peer_median:.1f}x")

print(f"\n{TICKER} — multiple implied by the DCF")
print(f"  Terminal value (end of year 5):          {dcf['terminal_value'] / B:,.1f}B")
print(f"  Year-5 projected adj. EBITDA:             {ebitda_y5 / B:,.2f}B  (EBIT + D&A + SBC)")
print(f"  Implied terminal EV/adj. EBITDA:          {implied_multiple:.1f}x")
print(f"  (discounted TV / year-5 adj. EBITDA, for reference only: {implied_multiple_discounted:.1f}x)")
print(f"  {TICKER} current EV/adj. EBITDA:              {adbe_current_multiple:.1f}x  "
      f"(EBITDA {adbe['ebitda_source']}, SBC {adbe['sbc_source']})")

gap = implied_multiple / peer_median - 1
print(f"\nYour DCF implies {implied_multiple:.1f}x vs. peers trading at {peer_median:.1f}x — "
      f"{abs(gap):.0%} {'richer' if gap > 0 else 'cheaper'}")
