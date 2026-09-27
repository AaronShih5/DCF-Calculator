# cost_of_equity.py — Adobe's cost of equity via CAPM

# PLACEHOLDER: 10-year US Treasury yield, Sept 2026. Confirm/update before final numbers.
RISK_FREE_RATE = 0.0518
# PLACEHOLDER: Damodaran implied equity risk premium. Confirm/update before final numbers.
EQUITY_RISK_PREMIUM = 0.045
# From relever_beta.py: comps' median unlevered beta relevered at ADBE's D/E. Update if that output changes.
RELEVERED_BETA = 1.099

# CAPM: investors demand at least the risk-free rate (the floor any investment must beat), plus
# compensation for market risk. The ERP is the extra return the overall market pays over risk-free;
# beta scales it to ADBE's sensitivity to the market (beta > 1 means more risk, so a higher premium).
cost_of_equity = RISK_FREE_RATE + RELEVERED_BETA * EQUITY_RISK_PREMIUM

print(f"Risk-free rate:        {RISK_FREE_RATE:.2%}")
print(f"Equity risk premium:   {EQUITY_RISK_PREMIUM:.2%}")
print(f"Relevered beta:        {RELEVERED_BETA:.3f}")
print(f"Cost of equity:        {cost_of_equity:.2%}")
