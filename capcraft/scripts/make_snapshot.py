"""Save real data to data/snapshots/ so the app works with no keys and no network.

    export CAPCRAFT_SEC_USER_AGENT="Your Name you@example.com"
    export FRED_API_KEY=...                 # optional: also saves the 10-year Treasury yield
    python scripts/make_snapshot.py MSFT AAPL KO

Run it once, look at the printed numbers, then commit data/snapshots/. Share prices are
not saved (the price provider's terms may forbid it). A ticker that cannot be loaded is
skipped with a reason; nothing is written for it.
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from capcraft_api import snapshots  # noqa: E402
from capcraft_api.providers import edgar, fred, http  # noqa: E402


def write(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def save_company(ticker: str, out: Path, today: str) -> bool:
    try:
        cik, sym, name = edgar.find_company(ticker)
        d = edgar.derive(edgar.fetch_facts(cik))
    except http.DataError as e:
        print(f"  {ticker}: skipped: {e}")
        return False
    write(out / "companies" / f"{sym}.json", {
        "ticker": sym, "name": name, "cik": cik, "fiscal_year_end": d["fiscal_year_end"],
        "assumptions": d["assumptions"], "provenance": d["provenance"], "warnings": d["warnings"],
        "taken_on": today, "source": "SEC EDGAR company facts"})
    a = d["assumptions"]
    print(f"  {sym}: {name}, FY {d['fiscal_year_end']}: revenue ${a['base_revenue']:,.0f}M, growth {a['revenue_growth']:.1%}, "
          f"margin {a['ebit_margin']:.1%}, shares {a['shares_outstanding']:,.0f}M, net debt ${a['net_debt']:,.0f}M")
    for w in d["warnings"]:
        print(f"     warning: {w}")
    return True


def main(tickers, out: Path = None, today: str = None) -> int:
    out = out or snapshots.root()
    today = today or date.today().isoformat()
    print(f"Saving to {out}")
    saved = sum(save_company(t.upper(), out, today) for t in tickers)
    try:
        y = fred.ten_year_yield()
        if y:
            write(out / "rates.json", {"risk_free": y, "taken_on": today, "source": "FRED DGS10"})
            print(f"  10-year Treasury yield {y['value']:.2%} as of {y['as_of']}")
        elif fred.configured():
            print("  FRED returned no reading; rates not saved.")
    except http.DataError as e:
        print(f"  rates: skipped: {e}")
    print(f"Done: {saved} of {len(tickers)} companies saved. Compare the numbers with each company's 10-K before committing.")
    return 0 if saved else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1:]))
