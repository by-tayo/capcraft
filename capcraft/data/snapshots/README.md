# Saved real data

This folder is filled by `python scripts/make_snapshot.py MSFT AAPL ...` (run it once, with your
keys, then commit the result). It is empty until you do: nothing here is ever made up.

    companies/<TICKER>.json   assumptions derived from SEC filings, with how each was derived
    rates.json                10-year Treasury yield from FRED (only if FRED_API_KEY is set)

Every file records the day it was taken (`taken_on`). The app labels anything served from here as "saved".
Share prices are deliberately not saved: Alpha Vantage's terms may not allow redistributing them.
