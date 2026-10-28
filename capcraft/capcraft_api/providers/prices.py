"""Latest share price from Alpha Vantage (free key). Set ALPHAVANTAGE_API_KEY.
The free tier is small (a few dozen requests a day), so answers are cached."""
import urllib.parse
from typing import Dict, Optional

from . import http

URL = "https://www.alphavantage.co/query?"
TTL = 15 * 60


def configured() -> bool:
    return http.env("ALPHAVANTAGE_API_KEY") is not None


def latest_price(ticker: str) -> Optional[Dict]:
    """{'value': float, 'as_of': 'YYYY-MM-DD'} or None when no key is set or the
    provider has no quote (including when its daily limit is used up)."""
    key = http.env("ALPHAVANTAGE_API_KEY")
    if not key:
        return None
    url = URL + urllib.parse.urlencode({"function": "GLOBAL_QUOTE", "symbol": ticker, "apikey": key})
    data = http.get_json(url, ttl=TTL)
    for field in ("Error Message", "Information", "Note"):
        if data.get(field):     # the provider explains itself: limit reached, bad key, premium-only
            raise http.Unavailable(str(data[field])[:200])
    quote = data.get("Global Quote") or {}
    try:
        return {"value": float(quote["05. price"]), "as_of": quote.get("07. latest trading day", "")}
    except (KeyError, ValueError):
        return None   # rate limited, unknown symbol, or a changed response
