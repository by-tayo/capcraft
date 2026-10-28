"""Check that the live-data keys work. Run this ONCE before a demo:

    export CAPCRAFT_SEC_USER_AGENT="Your Name you@example.com"
    export ALPHAVANTAGE_API_KEY=...      # optional
    export FRED_API_KEY=...              # optional
    python scripts/check_live.py MSFT

It calls the real services and prints what each one returned, so you can compare
the numbers with the company's own filings. Keys are never printed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capcraft_api import service  # noqa: E402
from capcraft_api.providers import http  # noqa: E402


def main(ticker: str):
    print("Configured:", service.capabilities())
    try:
        c = service.company(ticker)
    except http.DataError as e:
        print("COMPANY: failed:", e)
        return 1
    print(f"\n{c['name']} ({c['ticker']}), fiscal year ending {c['fiscal_year_end']}")
    for k, v in c["assumptions"].items():
        print(f"  {k:<20} {v:,.4f}")
    print("  price:", c["price"])
    for w in c["warnings"]:
        print("  WARNING:", w)
    print("\nRates:", service.rates())
    print("\nNow check revenue, operating margin, shares and net debt against the company's latest 10-K.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "MSFT"))
