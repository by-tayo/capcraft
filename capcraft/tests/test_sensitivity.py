"""Tests for capcraft.sensitivity, on simple functions with known answers
and then on real DCF and Monte Carlo models."""
import math

import numpy as np
import pytest

from capcraft import dcf
from capcraft import monte_carlo as mc
from capcraft import sensitivity as sa


def linear(a, b, c=0.0):
    return 3 * a - 2 * b + c


def safe_ratio(x, y):
    if y >= x:
        raise ValueError("y must be below x")
    return 1 / (x - y)


BASE = dict(a=1.0, b=2.0, c=0.5)


def test_one_way_on_a_linear_function():
    out = sa.one_way(linear, BASE, "a", [0, 1, 2])
    assert out == [(0, -3.5), (1, -0.5), (2, 2.5)]


def test_unknown_input_is_rejected():
    with pytest.raises(KeyError, match="Not an input"):
        sa.one_way(linear, BASE, "d", [1])


def test_two_way_grid_orientation_and_values():
    t = sa.two_way(linear, BASE, "a", [0, 1, 2], "b", [0, 10])
    assert t.grid.shape == (2, 3)  # rows follow b (y), columns follow a (x)
    assert t.grid[0, 2] == linear(2, 0, 0.5)
    assert t.grid[1, 0] == linear(0, 10, 0.5)
    assert t.base_output == linear(**BASE)
    assert t.as_rows()[1][0] == 10


def test_two_way_marks_impossible_combinations_as_nan():
    t = sa.two_way(safe_ratio, {"x": 0.1, "y": 0.02}, "x", [0.05, 0.10], "y", [0.02, 0.08])
    assert math.isclose(t.grid[0, 0], 1 / 0.03)
    assert np.isnan(t.grid[1, 0])        # y 0.08 >= x 0.05
    assert not np.isnan(t.grid[1, 1])


def test_two_way_needs_two_different_inputs():
    with pytest.raises(ValueError):
        sa.two_way(linear, BASE, "a", [1], "a", [2])


def test_tornado_ranks_by_swing_and_reports_both_sides():
    bars = sa.tornado(linear, BASE, {"a": (0, 2), "b": (1, 3), "c": (0, 1)})
    assert [b.param for b in bars] == ["a", "b", "c"]  # swings 6, 4, 1
    assert [b.swing for b in bars] == [6, 4, 1]
    b_bar = bars[1]
    assert b_bar.low_output > b_bar.high_output   # b has a negative effect
    assert b_bar.downside == -2 and b_bar.upside == 2
    assert all(b.base_output == linear(**BASE) for b in bars)


def test_elasticity_of_power_functions():
    assert math.isclose(sa.elasticity(lambda x: x ** 2, {"x": 3.0}, "x"), 2.0)
    # Central difference on x^3 gives 3 + h^2 exactly.
    assert math.isclose(sa.elasticity(lambda x: x ** 3, {"x": 2.0}, "x", bump=0.01), 3.0001)


def test_elasticity_undefined_at_zero():
    with pytest.raises(ValueError):
        sa.elasticity(lambda x: x + 1, {"x": 0.0}, "x")
    with pytest.raises(ValueError):
        sa.elasticity(lambda x: x - 1, {"x": 1.0}, "x")


# On a real DCF

MODEL = dcf.DCFModel(base_revenue=500, revenue_growth=[0.12, 0.10, 0.08, 0.06, 0.05],
                     ebit_margin=0.18, tax_rate=0.25, da_pct=0.04, capex_pct=0.05,
                     nwc_pct=0.10, discount_rate=0.09, terminal_growth=0.025,
                     net_debt=120, shares_outstanding=50)


def test_dcf_function_matches_model_value():
    f = sa.dcf_function("value_per_share")
    assert math.isclose(f(**sa.dcf_base(MODEL)), MODEL.value().value_per_share)
    ev = sa.dcf_function("enterprise_value")
    assert math.isclose(ev(**sa.dcf_base(MODEL)), MODEL.value().enterprise_value)


def test_dcf_function_explains_missing_share_count():
    base = {**sa.dcf_base(MODEL), "shares_outstanding": None}
    with pytest.raises(ValueError, match="shares_outstanding"):
        sa.dcf_function("value_per_share")(**base)


def test_wacc_by_growth_table_behaves():
    t = sa.two_way(sa.dcf_function(), sa.dcf_base(MODEL),
                   "discount_rate", [0.025, 0.07, 0.08, 0.09, 0.10, 0.11],
                   "terminal_growth", [0.015, 0.02, 0.025, 0.03, 0.035])
    good = t.grid[:, 1:]
    assert np.all(np.diff(good, axis=1) < 0)   # higher WACC, lower value
    assert np.all(np.diff(good, axis=0) > 0)   # higher growth, higher value
    # In the 2.5% WACC column, growth of 1.5% and 2% is still below WACC (valid),
    # while 2.5%, 3% and 3.5% are at or above it (no finite value).
    assert not np.isnan(t.grid[:2, 0]).any()
    assert np.isnan(t.grid[2:, 0]).all()
    assert math.isclose(t.grid[2, 3], MODEL.value().value_per_share)  # base cell


def test_revenue_elasticity_of_enterprise_value_is_exactly_one():
    # Every cash flow is a percentage of revenue, so EV scales 1-for-1 with base revenue.
    ev = sa.dcf_function("enterprise_value")
    assert math.isclose(sa.elasticity(ev, sa.dcf_base(MODEL), "base_revenue"), 1.0)


def test_equity_is_more_sensitive_than_ev_when_there_is_debt():
    # Equity = EV - net debt, so its elasticity is EV / equity.
    res = MODEL.value()
    eq = sa.elasticity(sa.dcf_function("equity_value"), sa.dcf_base(MODEL), "base_revenue")
    assert math.isclose(eq, res.enterprise_value / res.equity_value)


def test_dcf_tornado_bars_match_direct_recalculation():
    ranges = {"discount_rate": (0.08, 0.10), "terminal_growth": (0.015, 0.035),
              "ebit_margin": (0.15, 0.21), "capex_pct": (0.04, 0.06)}
    bars = sa.tornado(sa.dcf_function(), sa.dcf_base(MODEL), ranges)
    for bar in bars:
        lo, hi = ranges[bar.param]
        assert math.isclose(bar.low_output, dcf.DCFModel(**{**sa.dcf_base(MODEL), bar.param: lo})
                            .value().value_per_share)
        assert math.isclose(bar.high_output, dcf.DCFModel(**{**sa.dcf_base(MODEL), bar.param: hi})
                            .value().value_per_share)
    swings = [b.swing for b in bars]
    assert swings == sorted(swings, reverse=True)


# On Monte Carlo, with common random numbers


def mc_mean(expected_return, volatility):
    return mc.simulate_gbm(10_000, expected_return, volatility, years=5,
                           n_sims=2_000, seed=99).mean_terminal()


def test_common_random_numbers_make_monte_carlo_sensitivity_smooth():
    # Same seed means the same shocks. Higher drift then lifts every path,
    # so the output must rise strictly with each step up in expected return.
    out = sa.one_way(mc_mean, {"expected_return": 0.06, "volatility": 0.2},
                     "expected_return", [0.02, 0.04, 0.06, 0.08, 0.10])
    values = [v for _, v in out]
    assert all(b > a for a, b in zip(values, values[1:]))


def test_monte_carlo_tornado_runs_on_probability_of_loss():
    def p_loss(expected_return, volatility):
        return mc.simulate_gbm(10_000, expected_return, volatility, years=5,
                               n_sims=5_000, seed=7).prob_loss()
    bars = sa.tornado(p_loss, {"expected_return": 0.07, "volatility": 0.18},
                      {"expected_return": (0.05, 0.09), "volatility": (0.12, 0.24)})
    vol = next(b for b in bars if b.param == "volatility")
    assert vol.high_output > vol.low_output   # more volatility, more chance of loss


# Working backward: solve_input and the reverse DCF


def test_solve_input_on_a_linear_function():
    out = sa.solve_input(linear, BASE, "a", target=10.0, lo=-10, hi=10)
    assert math.isclose(out["root"], (10 + 2 * 2.0 - 0.5) / 3, rel_tol=1e-9)   # 3a - 4 + 0.5 = 10
    assert out["unique"] and out["n_solutions"] == 1
    assert math.isclose(out["output"], 10.0)


def test_solve_input_reports_multiple_solutions():
    wavy = lambda x: x * x                    # equals 4 at both -2 and +2
    out = sa.solve_input(wavy, {"x": 0.0}, "x", target=4.0, lo=-5, hi=5)
    assert not out["unique"] and out["n_solutions"] == 2
    assert math.isclose(abs(out["root"]), 2.0, rel_tol=1e-9)
    assert math.isclose(sa.solve_input(wavy, {"x": 0.0}, "x", 4.0, 0, 5)["root"], 2.0, rel_tol=1e-9)


def test_solve_input_error_when_target_is_out_of_range_and_says_why():
    with pytest.raises(ValueError, match="only runs from"):
        sa.solve_input(linear, BASE, "a", target=1_000, lo=0, hi=10)


def test_solve_input_skips_points_the_model_cannot_compute():
    # safe_ratio raises when y >= x. Solve 1/(x - y) = 50 for x in a range that starts invalid.
    out = sa.solve_input(safe_ratio, {"x": 0.1, "y": 0.05}, "x", target=50.0, lo=0.0, hi=0.2)
    assert math.isclose(out["root"], 0.05 + 1 / 50, rel_tol=1e-9)


def test_solve_input_validation():
    with pytest.raises(ValueError):
        sa.solve_input(linear, BASE, "a", 1, lo=5, hi=1)
    with pytest.raises(ValueError, match="couldn't be computed anywhere"):
        sa.solve_input(safe_ratio, {"x": 0.1, "y": 0.5}, "y", 1, lo=0.2, hi=0.9)
    with pytest.raises(KeyError):
        sa.solve_input(linear, BASE, "zzz", 1, 0, 1)


def test_reverse_dcf_recovers_the_growth_that_made_the_price():
    # Price a company at 8% revenue growth, then ask what growth that price implies.
    truth = dcf.DCFModel(**{**sa.dcf_base(MODEL), "revenue_growth": 0.08, "years": 5})
    price = truth.value().value_per_share
    out = sa.implied_dcf_input(MODEL, "revenue_growth", price, lo=-0.2, hi=0.4)
    assert math.isclose(out["root"], 0.08, abs_tol=1e-9) and out["unique"]


def test_reverse_dcf_replaces_a_growth_list_with_one_constant_rate():
    out = sa.implied_dcf_input(MODEL, "revenue_growth", MODEL.value().value_per_share, -0.2, 0.4)
    avg_listed = sum(MODEL.revenue_growth) / len(MODEL.revenue_growth)
    assert 0.05 < out["root"] < 0.12 and abs(out["root"] - avg_listed) < 0.01
    # and the constant-rate model really does give back the price
    again = dcf.DCFModel(**{**sa.dcf_base(MODEL), "revenue_growth": out["root"], "years": 5})
    assert math.isclose(again.value().value_per_share, MODEL.value().value_per_share, rel_tol=1e-9)


def test_reverse_dcf_implied_discount_rate_round_trips():
    price = MODEL.value().value_per_share
    out = sa.implied_dcf_input(MODEL, "discount_rate", price, lo=0.03, hi=0.30)
    assert math.isclose(out["root"], 0.09, abs_tol=1e-9)


def test_reverse_dcf_price_impossible_to_justify_says_so():
    with pytest.raises(ValueError, match="No value of revenue_growth"):
        sa.implied_dcf_input(MODEL, "revenue_growth", 1e9, lo=-0.2, hi=0.4)
