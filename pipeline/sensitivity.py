# sensitivity.py — how ADBE's implied price moves with WACC, terminal growth, and the FCF margin
import pandas as pd

from dcf_valuation import run_dcf, WACC, TERMINAL_GROWTH_RATE, BASE_FCF_MARGIN, current_price

# PLACEHOLDER — confirm with team: analyst consensus price target (source/date to cite in the deck)
ANALYST_CONSENSUS = 278.00

# Integer steps then divide, so grid values are exact (0.085, not 0.08499999...)
WACC_GRID = [w / 1000 for w in range(80, 111, 5)]         # 8.0% -> 11.0%, 0.5% steps
GROWTH_GRID = [g / 1000 for g in range(15, 36, 5)]        # 1.5% -> 3.5%, 0.5% steps
FCF_MARGINS = [BASE_FCF_MARGIN, 0.35, 0.30]


def fmt_pct(x):
    return f"{x:.1%}"


# Table 1: every cell re-runs the full DCF with one WACC and one terminal growth rate
grid = pd.DataFrame(
    [[run_dcf(wacc=w, terminal_growth_rate=g)["price_per_share"] for g in GROWTH_GRID] for w in WACC_GRID],
    index=[fmt_pct(w) for w in WACC_GRID], columns=[fmt_pct(g) for g in GROWTH_GRID])
grid.index.name, grid.columns.name = "WACC", "Terminal g"

# Table 2: base WACC / terminal growth, but FCF forced to a flat share of revenue
margin_rows = []
for m in FCF_MARGINS:
    res = run_dcf(fcf_margin_override=m)
    label = f"{m:.2%}" + (" (base, FY2025 actual)" if m == BASE_FCF_MARGIN else "")
    margin_rows.append({"FCF margin": label, "Price / share": res["price_per_share"],
                        "vs. current": res["upside"],
                        "vs. consensus": res["price_per_share"] / ANALYST_CONSENSUS - 1})
margins = pd.DataFrame(margin_rows)

print(f"Current share price:   ${current_price:,.2f}")
print(f"Analyst consensus:     ${ANALYST_CONSENSUS:,.2f}")
print(f"Base case:             WACC {WACC:.2%}, terminal g {TERMINAL_GROWTH_RATE:.2%}, "
      f"FCF margin {BASE_FCF_MARGIN:.2%} -> ${run_dcf()['price_per_share']:,.2f}\n")

print("Table 1 — Implied price per share: WACC (rows) x terminal growth (columns)")
print(grid.map(lambda p: f"${p:,.0f}").to_string())

print(f"\nTable 2 — Implied price per share at base WACC {WACC:.2%} / terminal g {TERMINAL_GROWTH_RATE:.2%}, "
      f"FCF margin held flat")
print(margins.to_string(index=False, formatters={
    "Price / share": lambda p: f"${p:,.2f}", "vs. current": lambda x: f"{x:+.1%}",
    "vs. consensus": lambda x: f"{x:+.1%}"}))
