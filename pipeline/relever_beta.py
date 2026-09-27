# relever_beta.py — relever the comps' median unlevered beta using Adobe's own capital structure
from data_sources import yf_info, fx_rate, normalize_currency

TICKER = "ADBE"

# From comps_beta.py: median unlevered beta of the 13 comps. Update manually if the comp set or data changes.
MEDIAN_UNLEVERED_BETA = 1.038
# From build_drivers.py: ADBE's effective tax rate (5y avg). Update manually if the tax lookback or data changes.
ADBE_TAX_RATE = 0.189254


# Same conversion as comps_beta.py so ADBE's D/E is measured exactly like the comps' D/E
def to_usd(value, currency):
    return value * fx_rate(currency) if value is not None else None


info = yf_info(TICKER)
# Yahoo quotes market cap in the trading currency and debt in the reporting currency (both USD for ADBE)
trading_ccy = normalize_currency(info.get("currency"))
reporting_ccy = normalize_currency(info.get("financialCurrency")) or trading_ccy
market_cap_usd = to_usd(info.get("marketCap"), trading_ccy)
total_debt_usd = to_usd(info.get("totalDebt"), reporting_ccy)

# D/E at market values: how much debt ADBE carries per dollar of equity
debt_to_equity = total_debt_usd / market_cap_usd

# Interest is tax-deductible, so only (1 - t) of the debt burden adds risk for shareholders
after_tax_leverage = (1 - ADBE_TAX_RATE) * debt_to_equity

# Relevering is the reverse of unlevering: start from the business-only risk the comps share
# (unlevered beta) and multiply by (1 + after-tax D/E) to add back the extra equity risk from
# ADBE's own debt. The result is the beta ADBE's shareholders face, which feeds CAPM.
relevered_beta = MEDIAN_UNLEVERED_BETA * (1 + after_tax_leverage)

print(f"{TICKER} total debt (USD):    {total_debt_usd:,.0f}")
print(f"{TICKER} market cap (USD):    {market_cap_usd:,.0f}")
print(f"{TICKER} D/E:                 {debt_to_equity:.4f}")
print(f"{TICKER} relevered beta:      {relevered_beta:.4f}")
