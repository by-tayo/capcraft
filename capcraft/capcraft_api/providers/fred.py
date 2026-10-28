"""The current 10-year US Treasury yield from FRED (free key). Set FRED_API_KEY.
Used only as a suggested risk-free rate; you can always type your own."""
import urllib.parse
from typing import Dict, Optional

from . import http

URL = "https://api.stlouisfed.org/fred/series/observations?"
SERIES = "DGS10"
TTL = 3 * 3600


def configured() -> bool:
    return http.env("FRED_API_KEY") is not None


def ten_year_yield() -> Optional[Dict]:
    """{'value': 0.0425, 'as_of': 'YYYY-MM-DD'} or None."""
    key = http.env("FRED_API_KEY")
    if not key:
        return None
    url = URL + urllib.parse.urlencode({"series_id": SERIES, "api_key": key, "file_type": "json",
                                        "sort_order": "desc", "limit": 10})
    data = http.get_json(url, ttl=TTL)
    for obs in data.get("observations", []):
        try:
            return {"value": float(obs["value"]) / 100, "as_of": obs["date"]}
        except (KeyError, ValueError):
            continue   # FRED writes "." on days with no reading
    return None
