"""Tests for capcraft.risk_metrics: hand-worked numbers first, then identities
that must hold for any input."""
import math
import statistics
from statistics import NormalDist

import numpy as np
import pytest

from capcraft import risk_metrics as rm
from capcraft import risk_return as rr


def approx(a, b, tol=1e-9):
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


# Conversions, growth, annualizing


def test_periodic_rate_compounds_back_to_annual():
    assert approx((1 + rm.periodic_rate(0.08, 12)) ** 12, 1.08)
    assert approx(rm.periodic_rate(0.08, 1), 0.08)
    with pytest.raises(ValueError):
        rm.periodic_rate(-1.0)


def test_cumulative_growth_by_hand():
    assert rm.cumulative_growth([0.10, -0.20]) == pytest.approx([1.0, 1.10, 0.88])


def test_cagr_by_hand():
    assert approx(rm.cagr([0.10, 0.10], periods_per_year=1), 0.10)
    # 6 months of +1% is 1.01^6 over half a year, so 1.01^12 - 1 for a full year
    assert approx(rm.cagr([0.01] * 6, periods_per_year=12), 1.01 ** 12 - 1)
    # +50% then -50% loses money even though the average is 0%
    assert approx(rm.cagr([0.5, -0.5], periods_per_year=1), math.sqrt(0.75) - 1)


def test_cagr_rejects_total_loss_and_empty():
    with pytest.raises(ValueError, match="lost everything"):
        rm.cagr([0.1, -1.0])
    with pytest.raises(ValueError):
        rm.cagr([])


def test_annualized_return_methods():
    series = [0.03, -0.02, 0.05, 0.01, -0.04, 0.06]
    assert approx(rm.annualized_return(series, 12, "arithmetic"), statistics.mean(series) * 12)
    assert approx(rm.annualized_return(series, 12), rm.cagr(series, 12))
    flat = [0.01] * 12
    assert approx(rm.annualized_return(flat, 12), 1.01 ** 12 - 1)


def test_geometric_mean_never_exceeds_arithmetic_and_gap_is_about_half_variance():
    # -50% then +50% averages 0% but ends 25% down: geometric mean is sqrt(0.75) - 1
    assert approx(rm.geometric_mean_return([0.5, -0.5]), math.sqrt(0.75) - 1)
    assert approx(rm.geometric_mean_return([0.02] * 5), 0.02)       # no volatility, no drag
    series = np.random.default_rng(3).normal(0.01, 0.03, 600).tolist()
    gap = rr.average_return(series) - rm.geometric_mean_return(series)
    assert gap > 0
    assert abs(gap - rr.historical_variance(series) / 2) < 2e-4     # drag is about SD^2 / 2
    with pytest.raises(ValueError):
        rm.geometric_mean_return([0.1, -1.0])


def test_annualized_return_does_not_compound_the_average():
    # Regression test for the old behavior, (1 + average) ** 12 - 1, which
    # overstated: a series averaging 6% a month is not a 101% year.
    series = [0.12, -0.04, 0.18, 0.07, 0.02]
    old_style = (1 + statistics.mean(series)) ** 12 - 1
    assert rm.annualized_return(series, 12) < old_style


def test_unknown_annualization_method_rejected():
    with pytest.raises(ValueError, match="method"):
        rm.annualized_return([0.01, 0.02], 12, "magic")


def test_annualized_volatility_scales_with_sqrt_time():
    series = [0.02, -0.01, 0.03, 0.00, 0.01]
    assert approx(rm.annualized_volatility(series, 12), statistics.stdev(series) * math.sqrt(12))
    assert approx(rm.annualized_volatility(series, 252) / rm.annualized_volatility(series, 12),
                  math.sqrt(21))


# Sharpe and Sortino


def test_sharpe_by_hand():
    series = [0.02, 0.04]                      # mean 3%, sample SD = sqrt(0.0002)
    sd = math.sqrt(0.0002)
    assert approx(rm.sharpe_ratio(series, annualize=False), 0.03 / sd)
    assert approx(rm.sharpe_ratio(series, 0.01, annualize=False), 0.02 / sd)
    assert approx(rm.sharpe_ratio(series, 0.01, periods_per_year=12), 0.02 / sd * math.sqrt(12))


def test_sharpe_matches_statistics_module():
    series = [0.03, -0.01, 0.05, 0.02, 0.04]
    expected = (statistics.mean(series) - 0.001) / statistics.stdev(series)
    assert approx(rm.sharpe_ratio(series, 0.001, annualize=False), expected)


def test_sharpe_undefined_with_no_volatility():
    with pytest.raises(ValueError, match="undefined"):
        rm.sharpe_ratio([0.01, 0.01, 0.01])


def test_downside_deviation_and_sortino_by_hand():
    series = [0.02, -0.01, 0.03, -0.03]
    dd = math.sqrt((0.01 ** 2 + 0.03 ** 2) / 4)
    assert approx(rm.downside_deviation(series), dd)
    assert approx(rm.sortino_ratio(series, annualize=False), 0.0025 / dd)
    # raising the bar (MAR) makes more periods count as shortfalls
    assert rm.downside_deviation(series, 0.02) > rm.downside_deviation(series, 0.0)


def test_sortino_ignores_upside_volatility_but_sharpe_does_not():
    base = [0.03, -0.02, 0.03, -0.02]             # average +0.5%
    wilder_upside = [0.11, -0.02, 0.11, -0.02]    # average +4.5%, same losses
    assert approx(rm.downside_deviation(base), rm.downside_deviation(wilder_upside))
    assert rr.historical_sd(wilder_upside) > rr.historical_sd(base)
    # Sharpe's denominator grew with the bigger upside swings; Sortino's did not.
    ratio_up = rm.sortino_ratio(wilder_upside, annualize=False) / rm.sortino_ratio(base, annualize=False)
    assert approx(ratio_up, rr.average_return(wilder_upside) / rr.average_return(base))


def test_sortino_undefined_without_down_periods():
    with pytest.raises(ValueError, match="undefined"):
        rm.sortino_ratio([0.01, 0.02, 0.03])


# Drawdown


def test_drawdown_series_by_hand():
    assert rm.drawdown_series([0.10, -0.20, -0.10, 0.50]) == pytest.approx([0, 0, -0.2, -0.28, 0])


def test_max_drawdown_by_hand_with_recovery():
    d = rm.max_drawdown([0.10, -0.20, -0.10, 0.50])
    assert approx(d["max_drawdown"], 0.792 / 1.10 - 1)
    assert (d["peak_index"], d["trough_index"], d["recovery_index"]) == (1, 3, 4)


def test_max_drawdown_without_recovery_and_peak_at_start():
    d = rm.max_drawdown([-0.10, 0.05])          # path 1, 0.90, 0.945
    assert approx(d["max_drawdown"], -0.10)
    assert (d["peak_index"], d["trough_index"], d["recovery_index"]) == (0, 1, None)


def test_max_drawdown_zero_when_never_down():
    d = rm.max_drawdown([0.01, 0.02, 0.03])
    assert d["max_drawdown"] == 0.0 and d["recovery_index"] is None


def test_max_drawdown_picks_the_deepest_of_several():
    # first fall is 10%, second is 30%
    d = rm.max_drawdown([0.10, -0.10, 0.30, -0.30, 0.05])
    # path 1, 1.10, 0.99, 1.287, 0.9009, 0.9459: the 30% fall from 1.287 beats the 10% fall from 1.10
    assert approx(d["max_drawdown"], -0.30)
    assert (d["peak_index"], d["trough_index"], d["recovery_index"]) == (3, 4, None)


def test_max_drawdown_depends_on_order_not_only_on_the_returns():
    a, b = [0.10, -0.10, 0.10, -0.10], [0.10, 0.10, -0.10, -0.10]
    assert approx(rr.average_return(a), rr.average_return(b))
    assert rm.max_drawdown(a)["max_drawdown"] > rm.max_drawdown(b)["max_drawdown"]


@pytest.mark.parametrize("seed", range(5))
def test_max_drawdown_invariants_on_random_series(seed):
    series = np.random.default_rng(seed).normal(0.005, 0.04, 60).tolist()
    d = rm.max_drawdown(series)
    path = d["growth_path"]
    assert d["max_drawdown"] <= 0
    assert d["peak_index"] <= d["trough_index"]
    assert approx(path[d["trough_index"]] / path[d["peak_index"]] - 1, d["max_drawdown"])
    assert path[d["peak_index"]] == max(path[:d["trough_index"] + 1])
    if d["recovery_index"] is not None:
        assert path[d["recovery_index"]] >= path[d["peak_index"]]


def test_calmar_by_hand_and_undefined_without_drawdown():
    series = [0.10, -0.20, -0.10, 0.50]
    assert approx(rm.calmar_ratio(series, 4), rm.cagr(series, 4) / 0.28)
    with pytest.raises(ValueError, match="no drawdown"):
        rm.calmar_ratio([0.01, 0.02])


# VaR


def test_historical_var_and_cvar_by_hand():
    series = [i / 100 for i in range(-10, 10)]      # -10% ... +9%, 20 values
    assert approx(rm.historical_var(series, 0.95), 0.0905)    # 5th percentile = -9.05%
    assert approx(rm.historical_cvar(series, 0.95), 0.10)     # only -10% is at or below it
    assert rm.historical_cvar(series, 0.95) >= rm.historical_var(series, 0.95)


def test_parametric_var_by_hand():
    series = [0.02, 0.04, 0.00, 0.06]
    z = NormalDist().inv_cdf(0.05)
    expected = -(statistics.mean(series) + z * statistics.stdev(series))
    assert approx(rm.parametric_var(series, 0.95), expected)


def test_parametric_and_historical_var_agree_on_normal_data():
    series = np.random.default_rng(0).normal(0.01, 0.04, 200_000)
    exact = 0.04 * NormalDist().inv_cdf(0.95) - 0.01
    assert abs(rm.parametric_var(series, 0.95) - exact) < 5e-4
    assert abs(rm.historical_var(series, 0.95) - exact) < 1e-3


def test_var_rises_with_confidence_and_validates_input():
    series = np.random.default_rng(1).normal(0.0, 0.05, 1000).tolist()
    assert rm.historical_var(series, 0.99) > rm.historical_var(series, 0.90)
    for bad in (0, 1, 1.5):
        with pytest.raises(ValueError):
            rm.historical_var(series, bad)


# Benchmark


BENCH = [0.04, -0.01, 0.02, 0.00, 0.05, -0.03]


def test_beta_alpha_treynor_for_a_constructed_asset():
    asset = [0.01 + 1.5 * b for b in BENCH]      # beta exactly 1.5, alpha exactly 1% per period
    assert approx(rm.beta_vs_benchmark(asset, BENCH), 1.5)
    assert approx(rm.jensens_alpha(asset, BENCH), 0.01)
    assert approx(rm.jensens_alpha(asset, BENCH, risk_free_rate=0.002), 0.01 + 0.002 * (1.5 - 1))
    assert approx(rm.treynor_ratio(asset, BENCH), statistics.mean(asset) / 1.5)


def test_beta_of_benchmark_against_itself_is_one_and_matches_risk_return_beta():
    assert approx(rm.beta_vs_benchmark(BENCH, BENCH), 1.0)
    asset = [0.05, -0.02, 0.03, 0.01, 0.06, -0.01]
    via_sd = rr.beta(rr.historical_sd(asset), rr.historical_correlation(asset, BENCH),
                     rr.historical_sd(BENCH))
    assert approx(rm.beta_vs_benchmark(asset, BENCH), via_sd)


def test_beta_edge_cases():
    with pytest.raises(ValueError, match="0 variance"):
        rm.beta_vs_benchmark([0.01, 0.02, 0.03], [0.01, 0.01, 0.01])
    uncorrelated = [0.01, -0.01, -0.01, 0.01]
    other = [0.02, 0.02, -0.02, -0.02]
    assert approx(rm.beta_vs_benchmark(uncorrelated, other), 0.0)
    with pytest.raises(ValueError, match="Beta is 0"):
        rm.treynor_ratio(uncorrelated, other)


# Summary


def test_summary_has_everything_and_matches_the_functions():
    series = [0.05, -0.08, 0.02, -0.03, 0.10, -0.01, 0.04, 0.02]
    s = rm.risk_metrics_summary(series, risk_free_rate=0.001, benchmark_returns=BENCH + [0.01, 0.02])
    assert approx(s["sharpe_ratio"], rm.sharpe_ratio(series, 0.001))
    assert approx(s["max_drawdown"], rm.max_drawdown(series)["max_drawdown"])
    assert approx(s["historical_var"], rm.historical_var(series))
    assert approx(s["annualized_return"], rm.cagr(series))
    for key in ("beta_vs_benchmark", "jensens_alpha_per_period", "treynor_ratio_per_period",
                "calmar_ratio", "sortino_ratio", "parametric_var", "historical_cvar"):
        assert s[key] is not None


def test_summary_reports_none_for_undefined_metrics_instead_of_failing():
    s = rm.risk_metrics_summary([0.01, 0.02, 0.03, 0.04])        # never down
    assert s["sortino_ratio"] is None and s["calmar_ratio"] is None
    assert s["max_drawdown"] == 0.0 and s["sharpe_ratio"] is not None
    flat = rm.risk_metrics_summary([0.01, 0.01, 0.01])           # no volatility
    assert flat["sharpe_ratio"] is None
