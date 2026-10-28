"""Tests for capcraft.sample_data."""
import pytest

from capcraft import data
from capcraft.sample_data import SAMPLE_WEIGHTS, synthetic_price_csv


def test_sample_csv_loads_and_has_the_expected_shape():
    dates, prices = data.read_prices(synthetic_price_csv())
    assert list(prices) == ["MARKET", "GROWTH", "STEADY", "BONDS", "RISKY"]
    assert len(dates) == 61 and dates[0] == "start"
    assert all(p[0] == 100.0 and len(p) == 61 and min(p) > 0 for p in prices.values())


def test_sample_csv_is_reproducible_and_seed_dependent():
    assert synthetic_price_csv(seed=3) == synthetic_price_csv(seed=3)
    assert synthetic_price_csv(seed=3) != synthetic_price_csv(seed=4)


def test_sample_csv_without_market_and_custom_length():
    _, prices = data.read_prices(synthetic_price_csv(months=24, with_market=False))
    assert "MARKET" not in prices and len(prices["BONDS"]) == 25


def test_sample_weights_sum_to_one_and_name_real_columns():
    assert abs(sum(SAMPLE_WEIGHTS.values()) - 1) < 1e-12
    _, prices = data.read_prices(synthetic_price_csv())
    assert set(SAMPLE_WEIGHTS) <= set(prices)


def test_too_few_months_rejected():
    with pytest.raises(ValueError):
        synthetic_price_csv(months=2)
