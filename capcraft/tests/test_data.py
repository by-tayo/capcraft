"""Tests for capcraft.data: CSV price loading and price-to-return conversion."""
import io
import math

import pytest

from capcraft import data
from capcraft import risk_return as rr

CSV = """Date,AAA,BBB
2024-01-31,100,50
2024-02-29,110,45
2024-03-31,99,54
"""


def test_prices_to_returns_by_hand():
    assert data.prices_to_returns([100, 110, 99]) == pytest.approx([0.10, -0.10])


def test_prices_to_returns_validation():
    with pytest.raises(ValueError, match="at least 2"):
        data.prices_to_returns([100])
    with pytest.raises(ValueError, match="positive"):
        data.prices_to_returns([100, 0, 50])


def test_read_prices_from_text_with_dates():
    dates, prices = data.read_prices(CSV)
    assert dates == ["2024-01-31", "2024-02-29", "2024-03-31"]
    assert prices == {"AAA": [100, 110, 99], "BBB": [50, 45, 54]}


def test_read_prices_without_a_date_column():
    dates, prices = data.read_prices("AAA,BBB\n100,50\n101,51\n102,52\n")
    assert dates is None and prices["BBB"] == [50, 51, 52]


def test_read_prices_handles_dollar_signs_commas_and_quotes():
    dates, prices = data.read_prices('Date,AAA\n2024-01-31,"$1,000.50"\n2024-02-29,"$1,010.00"\n')
    assert prices["AAA"] == [1000.5, 1010.0]


def test_read_prices_from_file_path_and_file_objects(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text(CSV, encoding="utf-8")
    assert data.read_prices(str(path))[1]["AAA"] == [100, 110, 99]
    assert data.read_prices(io.StringIO(CSV))[1]["AAA"] == [100, 110, 99]
    raw = io.BytesIO(("﻿" + CSV).encode("utf-8"))          # as an upload would arrive, with a BOM
    dates, prices = data.read_prices(raw)
    assert list(prices) == ["AAA", "BBB"] and len(dates) == 3


@pytest.mark.parametrize("text, msg", [
    ("Date,AAA\n2024-01-31,100\n", "at least 2 rows"),
    ("Date,AAA,BBB\n2024-01-31,100\n2024-02-29,101,50\n", "Row 2 has 2 values"),
    ("Date,AAA\n2024-01-31,100\n2024-02-29,\n", "Row 3, column 'AAA' is blank"),
    ("Date,AAA\n2024-01-31,100\n2024-02-29,n/a\n", "isn't a number"),
    ("Date,AAA,AAA\n2024-01-31,1,2\n2024-02-29,1,2\n", "unique"),
    ("Date\n2024-01-31\n2024-02-29\n", "No price columns"),
])
def test_read_prices_errors_are_specific(text, msg):
    with pytest.raises(ValueError, match=msg):
        data.read_prices(text)


def test_portfolio_from_prices_end_to_end():
    _, prices = data.read_prices(CSV)
    p = data.portfolio_from_prices(prices)
    assert p.names == ["AAA", "BBB"] and p.weights == [0.5, 0.5]
    assert p.holdings[1].returns == pytest.approx([-0.10, 0.20])
    expected = rr.portfolio_return([0.5, 0.5], [0.10, -0.10]), rr.portfolio_return([0.5, 0.5], [-0.10, 0.20])
    assert p.period_returns() == pytest.approx(expected)


def test_portfolio_from_prices_with_weights_and_period_length():
    _, prices = data.read_prices(CSV)
    p = data.portfolio_from_prices(prices, weights=[0.8, 0.2], periods_per_year=4)
    assert p.weights == [0.8, 0.2] and p.periods_per_year == 4
    with pytest.raises(ValueError):
        data.portfolio_from_prices(prices, weights=[1.0])


def test_prices_that_encode_known_returns_round_trip():
    rets = [0.03, -0.02, 0.05, 0.01]
    prices = [100.0]
    for r in rets:
        prices.append(prices[-1] * (1 + r))
    assert data.prices_to_returns(prices) == pytest.approx(rets)
    assert math.isclose(prices[-1], 100 * 1.03 * 0.98 * 1.05 * 1.01)
