"""Tests for capcraft.tvm. Every shortcut is checked against the long way
(summing each individual cash flow), the same cross-check style as the
original worked examples."""
import math

import pytest

from capcraft import tvm


def test_future_value_present_value_undo_each_other():
    fv = tvm.future_value(1000, 0.05, 3)
    assert math.isclose(tvm.present_value(fv, 0.05, 3), 1000)


def test_interest_breakdown_splits_correctly():
    b = tvm.interest_breakdown(1000, 0.05, 3)
    assert math.isclose(b["simple_interest"] + b["interest_on_interest"], b["total_interest"])
    assert math.isclose(b["future_value"] - 1000, b["total_interest"])


def test_move_forward_and_backward():
    assert math.isclose(tvm.move(1000, 0.05, 0, 3), tvm.future_value(1000, 0.05, 3))
    assert math.isclose(tvm.move(1000, 0.05, 3, 0), tvm.present_value(1000, 0.05, 3))


def test_pv_cash_flows_matches_sum_of_each():
    flows = [(1, 100), (2, 200), (3, 300)]
    each = [tvm.present_value(a, 0.05, t) for t, a in flows]
    assert math.isclose(tvm.pv_cash_flows(flows, 0.05), sum(each))


def test_annuity_matches_long_way():
    shortcut = tvm.pv_annuity(1000, 0.06, 5)
    long_way = tvm.pv_cash_flows(tvm.pattern_cash_flows(1000, 5), 0.06)
    assert math.isclose(shortcut, long_way)


def test_growing_annuity_matches_long_way():
    shortcut = tvm.pv_growing_annuity(1000, 0.06, 0.03, 5)
    long_way = tvm.pv_cash_flows(tvm.pattern_cash_flows(1000, 5, growth=0.03), 0.06)
    assert math.isclose(shortcut, long_way)


def test_growing_annuity_handles_rate_equals_growth():
    # when r == g every payment is worth C / (1+r) today
    result = tvm.pv_growing_annuity(1000, 0.05, 0.05, 4)
    expected = 1000 * 4 / 1.05
    assert math.isclose(result, expected)


def test_perpetuity_approximates_very_long_annuity():
    perp = tvm.pv_perpetuity(1000, 0.05)
    long_annuity = tvm.pv_annuity(1000, 0.05, 2000)
    assert abs(perp - long_annuity) < 1e-6


def test_growing_perpetuity_approximates_very_long_growing_annuity():
    gperp = tvm.pv_growing_perpetuity(1000, 0.06, 0.03)
    gannuity = tvm.pv_growing_annuity(1000, 0.06, 0.03, 5000)
    assert abs(gperp - gannuity) < 1e-4


def test_growing_perpetuity_rejects_growth_above_rate():
    with pytest.raises(ValueError):
        tvm.pv_growing_perpetuity(1000, 0.05, 0.06)


def test_deferred_annuity_matches_long_way():
    at2 = tvm.pv_annuity(1000, 0.06, 4)
    today = tvm.value_today(at2, 3, 0.06)
    long_way = tvm.pv_cash_flows(tvm.pattern_cash_flows(1000, 4, first_period=3), 0.06)
    assert math.isclose(today, long_way)


def test_annuity_due_matches_long_way():
    due = tvm.pv_annuity_due(500, 0.05, 6)
    long_way = tvm.pv_cash_flows(tvm.pattern_cash_flows(500, 6, first_period=0), 0.05)
    assert math.isclose(due, long_way)


def test_fv_annuity_matches_long_way_and_pv_relationship():
    fva = tvm.fv_annuity(200, 0.07, 10)
    long_way = tvm.pv_cash_flows(tvm.pattern_cash_flows(200, 10), 0.07, at_period=10)
    assert math.isclose(fva, long_way)
    assert math.isclose(fva, tvm.future_value(tvm.pv_annuity(200, 0.07, 10), 0.07, 10))


def test_perpetuity_due_matches_long_way():
    due = tvm.pv_perpetuity_due(300, 0.06)
    long_way = tvm.pv_cash_flows(tvm.pattern_cash_flows(300, 3000, first_period=0), 0.06)
    assert abs(due - long_way) < 1e-6


def test_capm_rate():
    assert math.isclose(tvm.capm_rate(0.04, 1.1, 0.06), 0.106)


def test_negative_rate_at_or_below_100_percent_rejected():
    with pytest.raises(ValueError):
        tvm.future_value(1000, -1.0, 3)


def test_negative_periods_rejected():
    with pytest.raises(ValueError):
        tvm.future_value(1000, 0.05, -1)


def test_zero_rate_annuity_is_just_payment_times_n():
    assert math.isclose(tvm.pv_annuity(100, 0.0, 5), 500)
    assert math.isclose(tvm.fv_annuity(100, 0.0, 5), 500)
