# data_sources.py — pull annual statements for any ticker and normalize them into one canonical table.
#
# Source order: SEC EDGAR (10-K, 20-F, 40-F; US GAAP or IFRS) -> yfinance (any Yahoo ticker, ~4-5 years).
# Canonical sign convention, identical for every company and source:
#   revenue/income lines as reported; income_tax, da, sbc, capex are positive amounts;
#   chg_* fields are the change in the balance-sheet item (increase = positive).
import re
from functools import lru_cache

import pandas as pd
import yfinance as yf
from edgar import Company, set_identity
from edgar.xbrl import XBRLS

from config import IDENTITY, N_YEARS, RAW_DIR, FUND_DIR

set_identity(IDENTITY)

ANNUAL_FORMS = ["10-K", "20-F", "40-F"]
PERIOD = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# field -> (statement, EdgarTools standard_concept fallbacks, XBRL tags in priority order)
FIELDS = {
    "revenue": ("income", ["Revenue"], [
        "us-gaap_Revenues", "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap_RevenueFromContractWithCustomerIncludingAssessedTax", "us-gaap_SalesRevenueNet",
        "ifrs-full_Revenue"]),
    "gross_profit": ("income", ["GrossProfit"], ["us-gaap_GrossProfit", "ifrs-full_GrossProfit"]),
    "operating_expenses": ("income", [], ["us-gaap_OperatingExpenses"]),
    "sga": ("income", [], ["us-gaap_SellingGeneralAndAdministrativeExpense"]),
    "rnd": ("income", [], [
        "us-gaap_ResearchAndDevelopmentExpense",
        "us-gaap_ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"]),
    "operating_income": ("income", ["OperatingIncomeLoss"], [
        "us-gaap_OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities"]),
    "pretax_income": ("income", ["PretaxIncomeLoss"], [
        "us-gaap_IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "us-gaap_IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "ifrs-full_ProfitLossBeforeTax"]),
    "income_tax": ("income", ["IncomeTaxes"], [
        "us-gaap_IncomeTaxExpenseBenefit", "ifrs-full_IncomeTaxExpenseContinuingOperations"]),
    "net_income": ("income", ["NetIncome"], [
        "us-gaap_NetIncomeLoss", "ifrs-full_ProfitLossAttributableToOwnersOfParent"]),
    "da": ("cashflow", ["DepreciationExpense", "DepreciationAmortizationCF"], [
        "us-gaap_DepreciationDepletionAndAmortization", "us-gaap_DepreciationAmortizationAndAccretionNet",
        "us-gaap_DepreciationAndAmortization", "us-gaap_OtherDepreciationAndAmortization",
        "ifrs-full_AdjustmentsForDepreciationAndAmortisationExpense",
        "*_DepreciationAmortizationAndOther", "*_DepreciationAndAmortization"]),
    "sbc": ("cashflow", ["StockBasedCompensationExpense", "StockBasedCompensationCF"], [
        "us-gaap_ShareBasedCompensation", "us-gaap_AllocatedShareBasedCompensationExpense",
        "ifrs-full_AdjustmentsForSharebasedPayments", "us-gaap_StockOptionPlanExpense"]),
    "capex": ("cashflow", ["CapitalExpenses"], [
        "us-gaap_PaymentsToAcquirePropertyPlantAndEquipment", "us-gaap_PaymentsToAcquireProductiveAssets",
        "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "ifrs-full_PurchaseOfPropertyPlantAndEquipment",
        "ifrs-full_PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets"]),
    "ocf": ("cashflow", ["NetCashFromOperatingActivities"], [
        "us-gaap_NetCashProvidedByUsedInOperatingActivities",
        "us-gaap_NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        "ifrs-full_CashFlowsFromUsedInOperatingActivities"]),
    "chg_receivables": ("cashflow", ["ChangeInReceivables"], [
        "us-gaap_IncreaseDecreaseInAccountsReceivable", "us-gaap_IncreaseDecreaseInAccountsAndOtherReceivables",
        "us-gaap_IncreaseDecreaseInReceivables",
        "ifrs-full_AdjustmentsForDecreaseIncreaseInTradeAndOtherReceivables",
        "ifrs-full_AdjustmentsForDecreaseIncreaseInTradeAccountReceivable"]),
    "chg_deferred_revenue": ("cashflow", ["ChangeInDeferredRevenue"], [
        "us-gaap_IncreaseDecreaseInContractWithCustomerLiability", "us-gaap_IncreaseDecreaseInDeferredRevenue",
        "ifrs-full_AdjustmentsForIncreaseDecreaseInContractLiabilities",
        "ifrs-full_AdjustmentsForIncreaseDecreaseInDeferredIncome"]),
    "chg_payables_accrued": ("cashflow", [], [
        "us-gaap_IncreaseDecreaseInAccountsPayableAndAccruedLiabilities",
        "us-gaap_IncreaseDecreaseInOtherAccountsPayableAndAccruedLiabilities",
        "ifrs-full_AdjustmentsForIncreaseDecreaseInTradeAndOtherPayables"]),
}

# When no combined tag exists, sum the components (first tag found in each group).
# required=True means the first group must be present, so e.g. debt-cost "Amortization" alone never becomes D&A.
COMPONENTS = {
    "da": (True, [
        ["us-gaap_Depreciation", "ifrs-full_AdjustmentsForDepreciationExpense", "ifrs-full_AdjustmentsForDepreciation"],
        ["us-gaap_AmortizationOfIntangibleAssets", "us-gaap_AdjustmentForAmortization",
         "ifrs-full_AdjustmentsForAmortisationExpense", "ifrs-full_AdjustmentsForAmortisation", "us-gaap_Amortization"]]),
    "chg_payables_accrued": (False, [
        ["us-gaap_IncreaseDecreaseInAccountsPayable", "us-gaap_IncreaseDecreaseInAccountsPayableTrade",
         "ifrs-full_AdjustmentsForIncreaseDecreaseInTradeAccountPayable"],
        ["us-gaap_IncreaseDecreaseInAccruedLiabilities",
         "us-gaap_IncreaseDecreaseInAccruedLiabilitiesAndOtherOperatingLiabilities",
         "us-gaap_IncreaseDecreaseInOtherCurrentLiabilities"]]),
}

# Only used to derive operating income when a filer doesn't report it
HELPER_FIELDS = {"gross_profit", "operating_expenses", "sga", "rnd"}

# field -> (statement, yfinance row names in priority order, multiplier to canonical sign)
YF_FIELDS = {
    "revenue": ("income", ["Total Revenue", "Operating Revenue"], 1),
    "gross_profit": ("income", ["Gross Profit"], 1),
    "operating_expenses": ("income", ["Operating Expense"], 1),
    "sga": ("income", ["Selling General And Administration"], 1),
    "rnd": ("income", ["Research And Development"], 1),
    "operating_income": ("income", ["Operating Income"], 1),
    "pretax_income": ("income", ["Pretax Income"], 1),
    "income_tax": ("income", ["Tax Provision"], 1),
    "net_income": ("income", ["Net Income Common Stockholders", "Net Income"], 1),
    "da": ("cashflow", ["Depreciation And Amortization", "Depreciation Amortization Depletion"], 1),
    "sbc": ("cashflow", ["Stock Based Compensation"], 1),
    "capex": ("cashflow", ["Capital Expenditure", "Purchase Of PPE"], -1),
    "ocf": ("cashflow", ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"], 1),
    "chg_receivables": ("cashflow", ["Change In Receivables", "Changes In Account Receivables"], -1),
    "chg_deferred_revenue": ("cashflow", [], 1),
    "chg_payables_accrued": ("cashflow", ["Change In Payables And Accrued Expense", "Change In Payable"], 1),
}

MINOR_UNITS = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS"}


def _tag_sign(field, tag):
    # IFRS "DecreaseIncrease" tags report a decrease as positive, the reverse of US GAAP "IncreaseDecrease"
    return -1 if field.startswith("chg_") and "DecreaseIncrease" in tag else 1


def _single_value(rows, period):
    vals = rows[period].dropna() if period in rows else pd.Series(dtype=float)
    return float(vals.iloc[0]) if len(vals) == 1 else None


def _tag_rows(df, tag):
    # "*_Name" matches a company-specific extension tag such as msft_DepreciationAmortizationAndOther
    if tag.startswith("*_"):
        concept = df["concept"].astype(str)
        return df[concept.str.endswith(tag[1:]) & ~concept.str.startswith(("us-gaap_", "ifrs-full_"))]
    return df[df["concept"] == tag]


def _first_tag_value(df, field, tags, period):
    for tag in tags:
        rows = _tag_rows(df, tag)
        vals = rows[period].dropna()
        if len(vals):
            return float(vals.iloc[0]) * _tag_sign(field, tag)
    return None


def _edgar_value(df, field, period):
    _, std, tags = FIELDS[field]
    val = _first_tag_value(df, field, tags, period)
    if val is not None:
        return val
    if field in COMPONENTS:
        required, groups = COMPONENTS[field]
        parts = [_first_tag_value(df, field, g, period) for g in groups]
        if parts[0] is not None or (not required and any(p is not None for p in parts)):
            return sum(p for p in parts if p is not None)
    # standard_concept fallback only when exactly one row has a value; several means the mapping is ambiguous
    rows = df[df["standard_concept"].isin(std)]
    val = _single_value(rows, period)
    if val is None:
        return None
    tag = rows.loc[rows[period].notna(), "concept"].iloc[0]
    return val * _tag_sign(field, tag)


def _fetch_edgar(ticker, n_years):
    filings = Company(ticker).get_filings(form=ANNUAL_FORMS, amendments=False)
    if filings is None or len(filings) == 0:
        raise LookupError("no 10-K / 20-F / 40-F filings on EDGAR")
    filings = filings.head(n_years)
    stmts = XBRLS.from_filings(filings).statements
    getters = {"income": stmts.income_statement, "balance": stmts.balance_sheet,
               "cashflow": stmts.cash_flow_statement}
    raw = {}
    for name, get in getters.items():
        stmt = get(max_periods=n_years)
        raw[name] = stmt.to_dataframe(presentation=False) if stmt is not None else pd.DataFrame()
    return raw, filings[0].form


def _canonical_edgar(raw):
    inc = raw["income"]
    periods = sorted(c for c in inc.columns if PERIOD.match(str(c)))
    out = {}
    for period in periods:
        row = {}
        for field, (stmt, _, _) in FIELDS.items():
            df = raw[stmt]
            row[field] = _edgar_value(df, field, period) if period in df.columns else None
        out[period] = row
    return pd.DataFrame.from_dict(out, orient="index")


def _fetch_yf(ticker):
    tk = yf.Ticker(ticker)
    raw = {"income": tk.income_stmt, "balance": tk.balance_sheet, "cashflow": tk.cashflow}
    for name, df in raw.items():
        df.columns = [pd.Timestamp(c).strftime("%Y-%m-%d") for c in df.columns]
    if raw["income"].empty:
        raise LookupError("yfinance returned no income statement")
    return raw


def _canonical_yf(raw):
    periods = sorted(raw["income"].columns)
    out = {}
    for period in periods:
        row = {}
        for field, (stmt, names, sign) in YF_FIELDS.items():
            df = raw[stmt]
            row[field] = None
            for name in names:
                if name in df.index and period in df.columns and pd.notna(df.at[name, period]):
                    row[field] = float(df.at[name, period]) * sign
                    break
        out[period] = row
    return pd.DataFrame.from_dict(out, orient="index")


def _fill_operating_income(fund):
    oi = fund["operating_income"]
    from_opex = fund["gross_profit"] - fund["operating_expenses"]
    from_sga = fund["gross_profit"] - fund["sga"] - fund["rnd"].fillna(0)
    fund["operating_income_derived"] = oi.isna() & (from_opex.notna() | from_sga.notna())
    fund["operating_income"] = oi.fillna(from_opex).fillna(from_sga)
    return fund


def pull(ticker, n_years=N_YEARS):
    """Fetch statements for one ticker, save raw + canonical CSVs, and return the canonical table."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    FUND_DIR.mkdir(parents=True, exist_ok=True)

    fund = None
    try:
        raw, form = _fetch_edgar(ticker, n_years)
        fund, source = _canonical_edgar(raw), f"EDGAR {form}"
        if fund.empty or fund["revenue"].isna().all():
            print(f"  {ticker}: EDGAR data had no revenue line, trying yfinance")
            fund = None
    except Exception as e:
        print(f"  {ticker}: not usable on EDGAR ({type(e).__name__}: {e}), trying yfinance")
    if fund is None:
        raw = _fetch_yf(ticker)
        fund, source = _canonical_yf(raw), "yfinance"

    for name, df in raw.items():
        df.to_csv(RAW_DIR / f"{ticker}_{name}.csv", index=(source == "yfinance"))

    fund = fund.astype(float)
    fund = _fill_operating_income(fund)
    fund.index.name = "period"
    fund["source"] = source
    fund["currency"] = reporting_currency(ticker)
    fund.to_csv(FUND_DIR / f"{ticker}.csv")

    missing = [f for f in FIELDS if f not in HELPER_FIELDS and fund[f].isna().all()]
    note = f"; missing: {', '.join(missing)}" if missing else ""
    print(f"{ticker}: {len(fund)} periods from {source} ({fund['currency'].iloc[0]}){note}")
    return fund


def pull_all(tickers, n_years=N_YEARS):
    failed = []
    for t in tickers:
        try:
            pull(t, n_years)
        except Exception as e:
            print(f"{t}: FAILED ({type(e).__name__}: {e})")
            failed.append(t)
    if failed:
        print(f"\nFailed: {failed}")
    return failed


def load_fundamentals(ticker):
    path = FUND_DIR / f"{ticker}.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run pull_financials.py / comps_financials.py first")
    return pd.read_csv(path, index_col="period")


@lru_cache(maxsize=None)
def yf_info(ticker):
    try:
        return yf.Ticker(ticker).info or {}
    except Exception as e:
        print(f"  {ticker}: yfinance info unavailable ({type(e).__name__}: {e})")
        return {}


def normalize_currency(code):
    return MINOR_UNITS.get(code, code) if code else None


def reporting_currency(ticker):
    return normalize_currency(yf_info(ticker).get("financialCurrency"))


@lru_cache(maxsize=None)
def fx_rate(frm, to="USD"):
    """Units of `to` per one unit of `frm` (major currency units)."""
    frm, to = normalize_currency(frm), normalize_currency(to)
    if not frm or frm == to:
        return 1.0
    return float(yf.Ticker(f"{frm}{to}=X").fast_info["last_price"])
