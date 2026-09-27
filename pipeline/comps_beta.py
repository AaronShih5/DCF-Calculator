# comps_beta.py — levered beta, debt, market cap, P/S and tax rate for each comp, all in USD
import pandas as pd

from config import COMPS, PROCESSED_DIR
from data_sources import yf_info, fx_rate, normalize_currency
from tax_rate import tax_rate, statutory_rate


def to_usd(value, currency):
    return value * fx_rate(currency) if value is not None else None


def add_unlevered_beta(df):
    # Hamada: levered beta = unlevered beta * (1 + (1 - t) * D/E). Solving for unlevered beta strips out
    # the extra equity risk that comes from debt, leaving the risk of the business itself.
    # D/E uses market values, and both are already in USD so the ratio is currency-neutral.
    debt_to_equity = df["total_debt_usd"] / df["market_cap_usd"]
    # Interest is tax-deductible, so the government absorbs part of the debt burden; only (1 - t) of it
    # adds risk to shareholders.
    after_tax_leverage = (1 - df["tax_rate"]) * debt_to_equity
    # Dividing by (1 + after-tax leverage) reverses the amplification debt applies to beta.
    # A company with no debt gets a divisor of 1, so its unlevered beta equals its levered beta.
    df["unlevered_beta"] = df["levered_beta"] / (1 + after_tax_leverage)
    return df


rows = []
for t in COMPS:
    info = yf_info(t)
    # Yahoo quotes market cap in the trading currency but debt/revenue in the reporting currency
    # (e.g. SAP: USD vs EUR), and its own P/S field divides them without converting.
    trading_ccy = normalize_currency(info.get("currency"))
    reporting_ccy = normalize_currency(info.get("financialCurrency")) or trading_ccy

    beta = info.get("beta")
    mcap = to_usd(info.get("marketCap"), trading_ccy)
    debt = to_usd(info.get("totalDebt"), reporting_ccy)
    revenue = to_usd(info.get("totalRevenue"), reporting_ccy)
    price_to_sales = mcap / revenue if mcap and revenue else None
    try:
        tax, tax_source = tax_rate(t)
    except FileNotFoundError:
        tax, country = statutory_rate(t)
        tax_source = f"statutory ({country}); fundamentals not pulled"

    rows.append(dict(ticker=t, name=info.get("shortName"), country=info.get("country"),
                     trading_currency=trading_ccy, reporting_currency=reporting_ccy,
                     levered_beta=beta, market_cap_usd=mcap, total_debt_usd=debt,
                     revenue_usd=revenue, price_to_sales=price_to_sales,
                     tax_rate=tax, tax_rate_source=tax_source))

df = pd.DataFrame(rows)
df = add_unlevered_beta(df)
print(df.to_string())

print("\nLevered vs. unlevered beta:")
print(df[["ticker", "levered_beta", "unlevered_beta", "tax_rate_source"]].to_string(index=False))
# Median rather than mean, so one outlier (e.g. a high-beta name like SHOP or APP) doesn't drag the peer beta
print(f"\nMedian unlevered beta ({df['unlevered_beta'].notna().sum()} comps): {df['unlevered_beta'].median():.3f}")
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
df.to_csv(PROCESSED_DIR / "comps_beta_raw.csv", index=False)
