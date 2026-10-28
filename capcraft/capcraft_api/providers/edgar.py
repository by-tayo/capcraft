"""Turn a company's SEC filings into starting assumptions for the DCF.

Source: SEC EDGAR's free "company facts" data (annual 10-K figures, as the company
tagged them). No key is needed, but the SEC requires a contact string in the
User-Agent header: set CAPCRAFT_SEC_USER_AGENT to something like "Your Name you@example.com".

What the numbers are, plainly:
  * revenue_growth is the company's own compound growth over its last few
    reported years. It is HISTORY, not a forecast, and is capped to a sane range.
  * margins and percentages are averages of up to three recent years.
  * net debt uses reported borrowings and cash (plus short-term investments),
    and leaves out leases and pensions.
This method suits ordinary operating companies. Banks and insurers do not report
revenue or operating income this way, and the loader says so instead of guessing.
"""
import re
from datetime import date
from typing import Dict, List, Optional, Tuple

from . import http

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
TTL = 6 * 3600

REVENUE = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
           "RevenueFromContractWithCustomerIncludingAssessedTax"]
EBIT = ["OperatingIncomeLoss"]
PRETAX = ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
          "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"]
TAX = ["IncomeTaxExpenseBenefit"]
DA = ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "DepreciationAmortizationAndAccretionNet",
      "DepreciationAmortizationAndOther", "Depreciation"]
CAPEX = ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]
CUR_ASSETS = ["AssetsCurrent"]
CUR_LIAB = ["LiabilitiesCurrent"]
DEBT_TOTAL = ["LongTermDebt"]
DEBT_LONG = ["LongTermDebtNoncurrent"]
DEBT_SHORT = ["LongTermDebtCurrent", "DebtCurrent"]
CASH = ["CashAndCashEquivalentsAtCarryingValue"]
INVEST = ["MarketableSecuritiesCurrent", "ShortTermInvestments"]

GROWTH_RANGE = (-0.05, 0.30)   # the DCF tab's slider range
NWC_RANGE = (0.0, 0.40)


def user_agent() -> str:
    ua = http.env("CAPCRAFT_SEC_USER_AGENT")
    if not ua:
        raise http.NotConfigured('Set CAPCRAFT_SEC_USER_AGENT to "Your Name you@example.com" (the SEC asks for a contact).')
    return ua


def find_company(ticker: str) -> Tuple[int, str, str]:
    """(cik, ticker, company name) for a ticker symbol."""
    data = http.get_json(TICKERS_URL, {"User-Agent": user_agent()}, TTL)
    want = ticker.upper()
    for row in (data.values() if isinstance(data, dict) else data):
        if str(row.get("ticker", "")).upper() == want:
            return int(row["cik_str"]), want, str(row.get("title", want))
    raise http.NotFound(f"No SEC-registered company found for ticker '{ticker}'.")


def fetch_facts(cik: int) -> Dict:
    return http.get_json(FACTS_URL.format(cik=cik), {"User-Agent": user_agent()}, TTL)


# Reading the tagged facts


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def annual(facts: Dict, concepts: List[str], flow: bool = True, unit: str = "USD", taxonomy: str = "us-gaap") -> Dict[str, float]:
    """{period end date: value} for full fiscal years reported in 10-K filings.

    Several tags can carry the same line over the years (companies switch tags), so
    the tags are tried in order and fill in dates the earlier ones do not cover.
    When a year is reported more than once (restated), the latest filing wins."""
    out: Dict[str, Tuple[str, float]] = {}
    order: Dict[str, int] = {}
    for rank, concept in enumerate(concepts):
        rows = facts.get("facts", {}).get(taxonomy, {}).get(concept, {}).get("units", {}).get(unit, [])
        for r in rows:
            if not str(r.get("form", "")).startswith("10-K") or r.get("val") is None or "end" not in r:
                continue
            if flow:
                if "start" not in r or not 340 <= _days(r["start"], r["end"]) <= 380:
                    continue
            end, filed = r["end"], r.get("filed", "")
            if end in out and order[end] < rank:
                continue            # a higher-priority tag already covers this year
            if end not in out or order[end] > rank or filed >= out[end][0]:
                out[end] = (filed, float(r["val"]))
                order[end] = rank
    return {end: v for end, (_, v) in sorted(out.items())}


def _latest_shares(facts: Dict) -> Optional[Tuple[str, float]]:
    rows = facts.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])
    rows = [r for r in rows if r.get("val")]
    if not rows:
        return None
    r = max(rows, key=lambda x: (x.get("end", ""), x.get("filed", "")))
    return r["end"], float(r["val"])


def _last(d: Dict[str, float], n: int) -> List[Tuple[str, float]]:
    return list(d.items())[-n:]


def _avg_ratio(num: Dict[str, float], den: Dict[str, float], n: int = 3) -> Optional[float]:
    pairs = [num[e] / den[e] for e in den if e in num and den[e]]
    pairs = pairs[-n:]
    return sum(pairs) / len(pairs) if pairs else None


def derive(facts: Dict) -> Dict:
    """Starting DCF assumptions from company facts. Returns
    {assumptions, provenance, warnings, fiscal_year_end}; raises DataError if the
    basics (revenue and operating income) are missing."""
    notes: List[str] = []
    prov: List[Dict[str, str]] = []
    rev = annual(facts, REVENUE)
    ebit = annual(facts, EBIT)
    if len(rev) < 2 or not ebit:
        raise http.DataError("This company does not report revenue and operating income the way this model needs "
                             "(common for banks and insurers). Enter the numbers by hand instead.")
    fy_end = list(rev)[-1]
    last_rev = rev[fy_end]
    if last_rev <= 0:
        raise http.DataError("Reported revenue is not positive, so a revenue-based DCF does not apply.")

    window = _last(rev, 4)
    span = len(window) - 1
    cagr = (window[-1][1] / window[0][1]) ** (1 / span) - 1 if window[0][1] > 0 else 0.0
    growth = min(max(cagr, GROWTH_RANGE[0]), GROWTH_RANGE[1])
    if growth != cagr:
        notes.append(f"Historical growth of {cagr * 100:.1f}% a year was capped to {growth * 100:.1f}% to stay in a plausible range.")
    if span < 3:
        notes.append(f"Only {span} year(s) of growth history were available.")
    prov.append({"field": "Revenue growth", "how": f"Compound yearly growth of revenue from {window[0][0][:4]} to {window[-1][0][:4]}. History, not a forecast."})
    prov.append({"field": "Revenue last year", "how": f"Revenue for the fiscal year ending {fy_end}, in $ millions."})

    margin = _avg_ratio(ebit, rev)
    if margin is None:
        raise http.DataError("Could not match operating income to revenue years.")
    if margin <= 0:
        notes.append("Operating margin is zero or negative, so this DCF will value the company at or below zero. Raise the margin to model a turnaround.")
    prov.append({"field": "Operating margin", "how": "Average of operating income / revenue over up to 3 recent years."})

    tax = _avg_ratio(annual(facts, TAX), annual(facts, PRETAX))
    if tax is None or not 0.05 <= tax <= 0.40:
        notes.append("Effective tax rate was missing or unusual, so 21% (the US federal rate) was used.")
        tax = 0.21
    prov.append({"field": "Tax rate", "how": "Average of income tax / pretax income over up to 3 years (21% if unusable)."})

    da = _avg_ratio(annual(facts, DA), rev)
    capex = _avg_ratio(annual(facts, CAPEX), rev)
    if da is None:
        near = sorted(k for k in facts.get("facts", {}).get("us-gaap", {})
                      if "Depreciation" in k or "Amortization" in k)[:6]
        hint = f" Tags in this filing that look related: {', '.join(near)}." if near else ""
        notes.append("Depreciation was not found; set to 0%. Check it." + hint)
    if capex is None:
        notes.append("Capital spending was not found; set to 0%. Check it.")
    prov.append({"field": "Depreciation and capital spending", "how": "Average share of revenue over up to 3 years, from the cash flow statement."})

    ca, cl = annual(facts, CUR_ASSETS, flow=False), annual(facts, CUR_LIAB, flow=False)
    nwc = None
    if fy_end in ca and fy_end in cl:
        nwc = (ca[fy_end] - cl[fy_end]) / last_rev
        clipped = min(max(nwc, NWC_RANGE[0]), NWC_RANGE[1])
        if clipped != nwc:
            notes.append(f"Working capital was {nwc * 100:.0f}% of revenue; capped to {clipped * 100:.0f}%.")
        nwc = clipped
    else:
        notes.append("Working capital was not found; set to 10% of revenue. Check it.")
        nwc = 0.10
    prov.append({"field": "Working capital", "how": "Current assets minus current liabilities, as a share of revenue, latest year."})

    def at(concepts):
        s = annual(facts, concepts, flow=False)
        return s.get(fy_end)

    debt = at(DEBT_TOTAL)
    if debt is None:
        parts = [at(DEBT_LONG), at(DEBT_SHORT)]
        debt = sum(p for p in parts if p is not None) if any(p is not None for p in parts) else None
    cash = sum(v for v in (at(CASH), at(INVEST)) if v is not None) if (at(CASH) is not None or at(INVEST) is not None) else None
    if debt is None or cash is None:
        notes.append("Debt or cash was not found; net debt was set from what was found. Check it.")
    net_debt = (debt or 0.0) - (cash or 0.0)
    prov.append({"field": "Net debt", "how": "Reported borrowings minus cash and short-term investments. Leases and pensions are left out."})

    shares = _latest_shares(facts)
    if shares is None:
        raise http.DataError("Could not find the number of shares outstanding.")
    prov.append({"field": "Shares outstanding", "how": f"Shares reported on the cover of the latest filing ({shares[0]})."})

    return {
        "fiscal_year_end": fy_end,
        "assumptions": {
            "base_revenue": last_rev / 1e6, "revenue_growth": growth, "ebit_margin": margin, "tax_rate": tax,
            "da_pct": da or 0.0, "capex_pct": capex or 0.0, "nwc_pct": nwc,
            "net_debt": net_debt / 1e6, "shares_outstanding": shares[1] / 1e6,
        },
        "provenance": prov, "warnings": notes,
    }


TICKER_RE = re.compile(r"^[A-Za-z][A-Za-z.\-]{0,9}$")
