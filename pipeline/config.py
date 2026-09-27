# config.py — single place to change tickers and assumptions; every pipeline script reads from here
from pathlib import Path

IDENTITY = "Aaron Shih shihaaron40@gmail.com"   # SEC requires a name + email

# Any ticker works: US filers (10-K), foreign SEC filers (20-F / 40-F), or non-SEC listings
# with a Yahoo suffix (e.g. "CSU.TO", "REL.L", "SAP.DE"), which fall back to yfinance.
TARGETS = ["ABNB", "ADBE", "CPRT", "GEV", "NCLH", "NKE", "SBUX", "SPOT"]
COMPS = ["MSFT", "CRM", "INTU", "ADSK", "ZM", "SNOW", "SHOP", "DDOG", "SAP", "IBM", "DOCU", "NOW", "APP"]

N_YEARS = 10                 # annual periods to pull per company
TAX_LOOKBACK_YEARS = 5       # effective tax rate averages the most recent N fiscal years
TAX_RATE_BOUNDS = (0.0, 0.45)  # years outside this range (one-off benefits/charges) are ignored

# Combined (national + typical local) corporate rates, used only when no effective rate is computable
STATUTORY_TAX = {
    "United States": 0.25, "Canada": 0.265, "United Kingdom": 0.25, "Germany": 0.30,
    "France": 0.25, "Netherlands": 0.258, "Ireland": 0.125, "Switzerland": 0.196,
    "Sweden": 0.206, "Denmark": 0.22, "Luxembourg": 0.249, "Israel": 0.23,
    "Japan": 0.306, "Australia": 0.30, "India": 0.252, "China": 0.25,
}
DEFAULT_TAX = 0.25

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
FUND_DIR = ROOT / "data" / "fundamentals"
PROCESSED_DIR = ROOT / "data" / "processed"
