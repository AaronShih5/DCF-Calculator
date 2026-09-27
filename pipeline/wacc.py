# wacc.py — Adobe's cost of debt, capital structure weights, and WACC
import pandas as pd

from config import RAW_DIR
from data_sources import PERIOD, _first_tag_value

TICKER = "ADBE"

# From cost_of_equity.py: CAPM cost of equity. Update if Rf, ERP or beta change.
COST_OF_EQUITY = 0.1013
# From relever_beta.py: Yahoo market cap and total debt (USD). Update if re-pulled.
MARKET_CAP_USD = 93_599_326_208
TOTAL_DEBT_USD = 6_786_999_808
# From build_drivers.py: ADBE effective tax rate (5y avg). Update if the tax lookback or data changes.
TAX_RATE = 0.189254

# Same EDGAR/XBRL income statement that pull_financials.py saved and build_drivers.py relies on;
# tags in priority order (last one covers IFRS filers if TICKER changes)
INTEREST_TAGS = ["us-gaap_InterestExpense", "us-gaap_InterestExpenseNonoperating",
                 "us-gaap_InterestExpenseDebt", "ifrs-full_FinanceCosts"]

income = pd.read_csv(RAW_DIR / f"{TICKER}_income.csv")
latest_year = max(c for c in income.columns if PERIOD.match(c))
interest_expense = _first_tag_value(income, "interest_expense", INTEREST_TAGS, latest_year)

# What lenders charge ADBE: a year's interest divided by the debt it's paid on
pretax_cost_of_debt = interest_expense / TOTAL_DEBT_USD
# Interest is tax-deductible, so each $1 of interest only costs ADBE (1 - t) after the tax saving
after_tax_cost_of_debt = pretax_cost_of_debt * (1 - TAX_RATE)

# Weights use market values, not book equity: WACC is the return investors require on what the firm
# is worth today, and market cap is what equity holders would actually pay/receive for their stake
firm_value = MARKET_CAP_USD + TOTAL_DEBT_USD
# Share of the firm funded by equity
equity_weight = MARKET_CAP_USD / firm_value
# Share of the firm funded by debt
debt_weight = TOTAL_DEBT_USD / firm_value

# WACC blends the two funding costs by how much of each ADBE uses; this is the discount rate
# for unlevered free cash flow, since those cash flows belong to both lenders and shareholders
wacc = equity_weight * COST_OF_EQUITY + debt_weight * after_tax_cost_of_debt

print(f"Interest expense (FY {latest_year}):  {interest_expense:,.0f}")
print(f"Pre-tax cost of debt:            {pretax_cost_of_debt:.2%}")
print(f"After-tax cost of debt:          {after_tax_cost_of_debt:.2%}")
print(f"E/V:                             {equity_weight:.2%}")
print(f"D/V:                             {debt_weight:.2%}")
print(f"WACC:                            {wacc:.2%}")
