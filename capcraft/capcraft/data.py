"""Load price histories and turn them into the returns the rest of CapCraft uses.

Expected CSV layout (the file you would export from most finance sites):

    Date,AAA,BBB,CCC
    2024-01-31,100.00,50.00,20.00
    2024-02-29,103.00,49.00,20.50
    ...

* One header row. The first column is the date if it isn't a number;
  otherwise the file has no date column.
* One column of prices per asset, oldest row first, one row per period.
* Prices must be positive numbers, with no gaps. A row with any blank or
  non-numeric price is an error, not silently skipped, because dropping
  a row would make that period's return span two periods.

Returns are SIMPLE returns, price_t / price_(t-1) - 1. If the prices
are not adjusted for dividends and splits, the returns will be too low
on dividend dates or wildly wrong on split dates (a 2-for-1 split looks
like a 50% crash). Use adjusted close prices.

For learning only. Not financial advice.
"""
import csv
import io
from typing import Dict, List, Optional, Sequence, Tuple

from . import risk_return as rr
from .portfolio import Holding, Portfolio


def prices_to_returns(prices: Sequence[float]) -> List[float]:
    """Simple periodic returns from a list of prices (one fewer than prices)."""
    if len(prices) < 2:
        raise ValueError("Need at least 2 prices to compute a return")
    if any(p <= 0 for p in prices):
        raise ValueError("Prices must be positive")
    return [b / a - 1 for a, b in zip(prices, prices[1:])]


def _to_float(text, row, col):
    try:
        return float(text.replace(",", "").replace("$", "").strip())
    except ValueError:
        raise ValueError(f"Row {row}, column '{col}': '{text}' isn't a number") from None


def read_prices(source) -> Tuple[Optional[List[str]], Dict[str, List[float]]]:
    """Read a price CSV from a file path, a file-like object, or CSV text.

    Returns (dates or None, {asset name: prices})."""
    if isinstance(source, str):
        if "\n" in source or "," in source:
            handle = io.StringIO(source)
        else:
            handle = open(source, newline="", encoding="utf-8-sig")
    else:
        handle = source
    try:
        text = handle.read() if hasattr(handle, "read") else handle
        if isinstance(text, bytes):
            text = text.decode("utf-8-sig")
    finally:
        if handle is not source:
            handle.close()
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if len(rows) < 3:
        raise ValueError("Need a header row and at least 2 rows of prices")
    header, body = [c.strip() for c in rows[0]], rows[1:]

    has_dates = True
    try:
        float(body[0][0].replace(",", ""))
        has_dates = False
    except ValueError:
        pass
    first = 1 if has_dates else 0
    names = header[first:]
    if not names:
        raise ValueError("No price columns found")
    if len(set(names)) != len(names) or any(not n for n in names):
        raise ValueError("Every price column needs a unique, non-empty name")

    prices: Dict[str, List[float]] = {n: [] for n in names}
    dates: List[str] = []
    for i, row in enumerate(body, start=2):
        if len(row) != len(header):
            raise ValueError(f"Row {i} has {len(row)} values but the header has {len(header)}")
        if has_dates:
            dates.append(row[0].strip())
        for n, cell in zip(names, row[first:]):
            if not cell.strip():
                raise ValueError(f"Row {i}, column '{n}' is blank")
            prices[n].append(_to_float(cell, i, n))
    return (dates if has_dates else None), prices


def returns_from_prices(prices: Dict[str, List[float]]) -> Dict[str, List[float]]:
    """{name: prices} -> {name: returns}."""
    return {n: prices_to_returns(p) for n, p in prices.items()}


def portfolio_from_prices(prices: Dict[str, List[float]], weights: Optional[Sequence[float]] = None,
                          periods_per_year: int = 12) -> Portfolio:
    """Build a Portfolio from price histories. Equal weights if none are given."""
    names = list(prices)
    if weights is None:
        weights = [1 / len(names)] * len(names)
    rr._check_same_length(names, weights)
    returns = returns_from_prices(prices)
    return Portfolio([Holding(n, w, returns[n]) for n, w in zip(names, weights)], periods_per_year)
