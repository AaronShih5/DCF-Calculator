# dcf_valuation.py — 5-year unlevered DCF for Adobe -> enterprise value -> equity value -> price per share
import pandas as pd

from config import RAW_DIR, PROCESSED_DIR
from data_sources import PERIOD, _first_tag_value, yf_info

TICKER = "ADBE"

# ---- Reused inputs (hardcoded from upstream scripts; update manually if those change) ----
# From wacc.py: discount rate for unlevered FCF
WACC = 0.0966
# From build_drivers.py: ADBE effective tax rate (5y avg)
TAX_RATE = 0.189254
# From relever_beta.py: Yahoo total debt (USD)
TOTAL_DEBT_USD = 6_786_999_808

# ---- Assumptions ----
# PLACEHOLDER — confirm with team: annual revenue growth for forecast years 1-5, stepping down as the
# business matures toward the terminal growth rate
REVENUE_GROWTH = [0.10, 0.09, 0.08, 0.07, 0.06]
# PLACEHOLDER — confirm with team: perpetual growth after year 5, roughly long-run nominal GDP; a mature
# company can't outgrow the economy forever
TERMINAL_GROWTH_RATE = 0.025

# Gordon Growth divides by (WACC - g); if g >= WACC the formula implies infinite or negative value
assert WACC > TERMINAL_GROWTH_RATE, "WACC must exceed terminal growth for Gordon Growth to be valid"

# PLACEHOLDER — confirm with team: analyst consensus price target (same value as sensitivity.py)
ANALYST_CONSENSUS = 278.00
# Same window as the tax rate (config.TAX_LOOKBACK_YEARS): average the most recent 5 fiscal years
LOOKBACK_YEARS = 5

# ---- Historical actuals, read from build_drivers.py's output (not recomputed) ----
drivers = pd.read_csv(PROCESSED_DIR / "drivers.csv")
history = drivers[drivers.ticker == TICKER].sort_values("year").tail(LOOKBACK_YEARS).copy()
# Revenue still grows off the latest actual year; only the ratios are averaged
base = history.iloc[-1]
base_year, base_revenue = base.year, base.revenue

# Each line as a share of that year's revenue
history["op_margin"] = history.operating_income / history.revenue
history["da_pct"] = history.da / history.revenue
history["sbc_pct"] = history.sbc / history.revenue
history["capex_pct"] = history.capex.abs() / history.revenue
history["wc_pct"] = history.wc_change / history.revenue   # cash impact of working capital (positive = inflow)
history["fcf_margin"] = history.fcf / history.revenue


def average_ratio(col):
    """Mean of the yearly ratios over the years that have data, plus a label saying how many went in.
    Same idea as tax_rate.py: a single year can be distorted by a one-off (ABNB's FY2023 tax rate was
    -128% from a valuation-allowance release), so averaging several years gives a steadier base."""
    vals = history[col].dropna()
    return vals.mean(), f"{len(vals)}y avg"


# Hold the 5-year average ratios constant across the forecast and terminal year: each line scales with
# the size of the business, and the average reflects what ADBE sustains rather than any single year
(OP_MARGIN, OP_MARGIN_SRC), (DA_PCT, DA_SRC), (SBC_PCT, SBC_SRC), (CAPEX_PCT, CAPEX_SRC), (WC_PCT, WC_SRC) = (
    average_ratio(c) for c in ["op_margin", "da_pct", "sbc_pct", "capex_pct", "wc_pct"])

# ---- New data: cash, shares, price (same EDGAR raw files and Yahoo lookup as wacc.py / relever_beta.py) ----
balance = pd.read_csv(RAW_DIR / f"{TICKER}_balance.csv")
income = pd.read_csv(RAW_DIR / f"{TICKER}_income.csv")
bs_year = max(c for c in balance.columns if PERIOD.match(c))
is_year = max(c for c in income.columns if PERIOD.match(c))
cash = _first_tag_value(balance, "cash", ["us-gaap_CashAndCashEquivalentsAtCarryingValue",
                                          "ifrs-full_CashAndCashEquivalents"], bs_year)

# The 10-K's diluted share count is a full-year average, which overstates today's count after heavy
# buybacks. So take today's shares outstanding (Yahoo) and scale by FY2025's diluted/basic ratio
# to add back options and RSUs that would convert.
diluted_avg = _first_tag_value(income, "shares", ["us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding"], is_year)
basic_avg = _first_tag_value(income, "shares", ["us-gaap_WeightedAverageNumberOfSharesOutstandingBasic"], is_year)
info = yf_info(TICKER)
diluted_shares = info["sharesOutstanding"] * (diluted_avg / basic_avg)
current_price = info["currentPrice"]

# Base-case FCF as a share of revenue implied by the ratios above (FY2025 fcf / revenue)
BASE_FCF_MARGIN = OP_MARGIN * (1 - TAX_RATE) + DA_PCT + SBC_PCT - CAPEX_PCT + WC_PCT


def run_dcf(wacc=WACC, terminal_growth_rate=TERMINAL_GROWTH_RATE, fcf_margin_override=None):
    """Full DCF from revenue projection to price per share. Defaults reproduce the base case;
    fcf_margin_override replaces the FCF build with revenue x that margin (for stress-testing)."""
    if wacc <= terminal_growth_rate:
        raise ValueError("WACC must exceed terminal growth for Gordon Growth to be valid")

    # ---- Projection ----
    rows = []
    revenue = base_revenue
    for year, growth in enumerate(REVENUE_GROWTH, start=1):
        # Revenue compounds off the prior year
        revenue = revenue * (1 + growth)
        # EBIT at FY2025's operating margin; NOPAT = the profit left if ADBE had no debt and paid tax on all of it
        ebit = revenue * OP_MARGIN
        nopat = ebit * (1 - TAX_RATE)
        # Non-cash charges and reinvestment scale with revenue at FY2025 ratios
        da = revenue * DA_PCT
        sbc = revenue * SBC_PCT
        capex = revenue * CAPEX_PCT
        wc_change = revenue * WC_PCT
        # Same Unlevered FCF formula as build_drivers.py: NOPAT + D&A + SBC - capex - ΔNWC (wc_change is the cash impact)
        fcf = nopat + da + sbc - capex + wc_change
        if fcf_margin_override is not None:
            # Stress test: skip the line-by-line build and assume FCF is a flat share of revenue
            fcf = revenue * fcf_margin_override
        # A dollar received t years from now is worth 1 / (1 + WACC)^t today (end-of-year discounting)
        discount_factor = 1 / (1 + wacc) ** year
        rows.append(dict(year=year, growth=growth, revenue=revenue, ebit=ebit, nopat=nopat, da=da, sbc=sbc,
                         capex=capex, wc_change=wc_change, fcf=fcf, discount_factor=discount_factor,
                         pv_fcf=fcf * discount_factor))
    proj = pd.DataFrame(rows)

    # ---- Terminal value ----
    final = proj.iloc[-1]
    # Gordon Growth: value at end of year 5 of all FCF from year 6 onward, growing at g forever.
    # Year 6 FCF = year 5 FCF x (1 + g), capitalized at (WACC - g)
    terminal_value = final.fcf * (1 + terminal_growth_rate) / (wacc - terminal_growth_rate)
    # TV sits at the end of year 5, so it gets the same discount factor as year 5's FCF
    pv_terminal_value = terminal_value * final.discount_factor

    # ---- Enterprise value -> equity value -> per share ----
    # Enterprise value: what the operating business is worth to all capital providers (debt + equity)
    enterprise_value = proj.pv_fcf.sum() + pv_terminal_value
    # Equity holders get what's left after paying off debt, plus the cash the company already holds
    equity_value = enterprise_value - TOTAL_DEBT_USD + cash
    price_per_share = equity_value / diluted_shares

    return dict(proj=proj, terminal_value=terminal_value, pv_terminal_value=pv_terminal_value,
                enterprise_value=enterprise_value, equity_value=equity_value,
                price_per_share=price_per_share, upside=price_per_share / current_price - 1)


if __name__ == "__main__":
    res = run_dcf()
    proj, terminal_value, pv_terminal_value = res["proj"], res["terminal_value"], res["pv_terminal_value"]
    enterprise_value, equity_value = res["enterprise_value"], res["equity_value"]
    price_per_share, upside = res["price_per_share"], res["upside"]

    # ---- Output ----
    B = 1e9
    print(f"{TICKER} DCF  (base year FY {base_year}, WACC {WACC:.2%}, terminal g {TERMINAL_GROWTH_RATE:.2%})\n")
    print("Historical ratios (% of revenue) and the average held constant in the forecast:")
    pct = lambda x: f"{x:.2%}"
    hist_table = history[["year", "revenue", "op_margin", "da_pct", "sbc_pct", "capex_pct", "wc_pct", "fcf_margin"]]
    print(hist_table.to_string(index=False, formatters={
        "revenue": lambda x: f"{x / B:,.2f}B", **{c: pct for c in hist_table.columns[2:]}}))
    print(f"{'Average':>10}  {'':>9}   op {OP_MARGIN:.2%} ({OP_MARGIN_SRC}), D&A {DA_PCT:.2%} ({DA_SRC}), "
          f"SBC {SBC_PCT:.2%} ({SBC_SRC}), capex {CAPEX_PCT:.2%} ({CAPEX_SRC}), WC {WC_PCT:+.2%} ({WC_SRC})")
    print(f"{'':>10}  {'':>9}   -> FCF margin {BASE_FCF_MARGIN:.2%} "
          f"(vs. FY {base_year} alone: {base.fcf / base.revenue:.2%})\n")
    print(f"{'Year':>4} {'Growth':>7} {'Revenue':>9} {'NOPAT':>8} {'FCF':>8} {'DF':>7} {'PV FCF':>8}   ($B)")
    print(f"{'FY25':>4} {'':>7} {base_revenue / B:9.2f} {base.nopat / B:8.2f} {base.fcf / B:8.2f}   (actual)")
    for _, r in proj.iterrows():
        print(f"{int(r.year):>4} {r.growth:7.1%} {r.revenue / B:9.2f} {r.nopat / B:8.2f} {r.fcf / B:8.2f} "
              f"{r.discount_factor:7.4f} {r.pv_fcf / B:8.2f}")

    print(f"\nSum of PV of FCF (yrs 1-5):      {proj.pv_fcf.sum() / B:10.2f}B")
    print(f"Terminal value (undiscounted):   {terminal_value / B:10.2f}B")
    print(f"Terminal value (discounted):     {pv_terminal_value / B:10.2f}B   ({pv_terminal_value / enterprise_value:.0%} of EV)")
    print(f"Enterprise value:                {enterprise_value / B:10.2f}B")
    print(f"  - Total debt:                  {TOTAL_DEBT_USD / B:10.2f}B")
    print(f"  + Cash & equivalents ({bs_year}): {cash / B:7.2f}B")
    print(f"Equity value:                    {equity_value / B:10.2f}B")
    print(f"Diluted shares:                  {diluted_shares / 1e6:10.1f}M")
    print(f"\nImplied price per share:         ${price_per_share:9.2f}")
    print(f"Current share price:             ${current_price:9.2f}")
    print(f"Upside / (downside):             {upside:+10.1%}")
    print(f"Analyst consensus:               ${ANALYST_CONSENSUS:9.2f}")
    print(f"vs. consensus:                   {price_per_share / ANALYST_CONSENSUS - 1:+10.1%}")
