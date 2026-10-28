"""Tests for capcraft.monte_carlo.

Three kinds of check:

1. Exact checks. With volatility 0 there's no randomness, so every path
   must equal the time value of money answer from capcraft.tvm.
2. Statistical checks. GBM has closed-form answers for its mean, median,
   percentiles and probability of loss. Each simulated estimate must land
   within 4 standard errors of the exact value. The standard error is
   worked out from the sample size, not picked by hand, so the margin
   shrinks as n_sims grows. With fixed seeds the results are repeatable.
3. Structural checks: reproducibility, input validation, and how the
   bootstrap samples history.
"""
import math
from statistics import NormalDist

import numpy as np
import pytest

from capcraft import monte_carlo as mc
from capcraft import tvm

N = 200_000
Z = 4  # standard errors allowed


def lognormal_params(expected_return, vol, years):
    """Mean and SD of ln(V_T / V_0) under the module's GBM convention."""
    mu = math.log1p(expected_return)
    return (mu - 0.5 * vol ** 2) * years, vol * math.sqrt(years)


def quantile_and_se(s0, expected_return, vol, years, p, n):
    """Exact p-quantile of V_T and the standard error of a sample quantile
    from n draws: sqrt(p(1 - p) / n) / density at the quantile."""
    m, s = lognormal_params(expected_return, vol, years)
    z = NormalDist().inv_cdf(p)
    x = s0 * math.exp(m + s * z)
    density = NormalDist().pdf(z) / (x * s)
    return x, math.sqrt(p * (1 - p) / n) / density


# 1. Exact checks against time value of money


@pytest.mark.parametrize("steps_per_year", [1, 12, 252])
def test_zero_volatility_matches_future_value(steps_per_year):
    res = mc.simulate_gbm(10_000, 0.08, 0.0, years=10, steps_per_year=steps_per_year,
                          n_sims=50, seed=1)
    expected = tvm.future_value(10_000, 0.08, 10)
    assert np.allclose(res.terminal, expected, rtol=1e-10)


def test_zero_volatility_with_contributions_matches_annuity_math():
    # $10,000 today plus $500 at the end of every month for 10 years at 8% a year.
    res = mc.simulate_gbm(10_000, 0.08, 0.0, years=10, steps_per_year=12,
                          n_sims=10, contribution=500, seed=1)
    monthly = 1.08 ** (1 / 12) - 1
    expected = tvm.future_value(10_000, monthly, 120) + tvm.fv_annuity(500, monthly, 120)
    assert np.allclose(res.terminal, expected, rtol=1e-10)
    assert res.invested == 10_000 + 500 * 120


def test_zero_volatility_portfolio_matches_weighted_future_values():
    # Buy-and-hold with no randomness: each holding just compounds on its own.
    w, r = [0.6, 0.4], [0.09, 0.04]
    corr = [[1, 0.2], [0.2, 1]]
    res = mc.simulate_portfolio(1_000, w, r, [0.0, 0.0], corr, years=5,
                                n_sims=10, rebalance=False, seed=1)
    expected = sum(tvm.future_value(1_000 * wi, ri, 5) for wi, ri in zip(w, r))
    assert np.allclose(res.terminal, expected, rtol=1e-10)


# 2. Statistical checks against GBM's closed-form answers


def test_mean_terminal_matches_tvm_future_value():
    s0, r, vol, years = 1_000, 0.07, 0.20, 5
    res = mc.simulate_gbm(s0, r, vol, years, steps_per_year=12, n_sims=N, seed=42)
    exact = tvm.future_value(s0, r, years)
    se = res.terminal.std(ddof=1) / math.sqrt(N)
    assert abs(res.mean_terminal() - exact) < Z * se


def test_log_returns_have_the_right_mean_and_spread():
    s0, r, vol, years = 1_000, 0.07, 0.20, 5
    res = mc.simulate_gbm(s0, r, vol, years, steps_per_year=12, n_sims=N, seed=7)
    logret = np.log(res.terminal / s0)
    m, s = lognormal_params(r, vol, years)
    assert abs(logret.mean() - m) < Z * s / math.sqrt(N)
    assert abs(logret.std(ddof=1) - s) < Z * s / math.sqrt(2 * (N - 1))


@pytest.mark.parametrize("p", [0.05, 0.50, 0.95])
def test_percentiles_match_lognormal_quantiles(p):
    s0, r, vol, years = 1_000, 0.07, 0.20, 5
    res = mc.simulate_gbm(s0, r, vol, years, steps_per_year=12, n_sims=N, seed=11)
    exact, se = quantile_and_se(s0, r, vol, years, p, N)
    assert abs(res.percentiles((100 * p,))[100 * p] - exact) < Z * se


def test_median_is_below_mean_because_of_volatility_drag():
    res = mc.simulate_gbm(1_000, 0.07, 0.30, 10, n_sims=50_000, seed=3)
    assert res.median_terminal() < res.mean_terminal()
    assert res.median_terminal() < tvm.future_value(1_000, 0.07, 10)


def test_probability_of_loss_matches_normal_cdf():
    s0, r, vol, years = 1_000, 0.05, 0.25, 3
    res = mc.simulate_gbm(s0, r, vol, years, n_sims=N, seed=5)
    m, s = lognormal_params(r, vol, years)
    exact = NormalDist().cdf(-m / s)
    se = math.sqrt(exact * (1 - exact) / N)
    assert abs(res.prob_loss() - exact) < Z * se


def test_value_at_risk_matches_lognormal_quantile():
    s0, r, vol, years = 1_000, 0.06, 0.18, 1
    res = mc.simulate_gbm(s0, r, vol, years, steps_per_year=252, n_sims=N, seed=9)
    q05, se = quantile_and_se(s0, r, vol, years, 0.05, N)
    assert abs(res.value_at_risk(0.95) - (s0 - q05)) < Z * se


def test_cvar_is_at_least_var_and_matches_the_tail_average():
    res = mc.simulate_gbm(1_000, 0.06, 0.25, 2, n_sims=50_000, seed=2)
    var, cvar = res.value_at_risk(0.95), res.conditional_value_at_risk(0.95)
    assert cvar >= var
    cutoff = np.percentile(res.terminal, 5)
    assert math.isclose(cvar, 1_000 - res.terminal[res.terminal <= cutoff].mean())


def test_rebalanced_portfolio_mean_matches_exact_formula():
    # Rebalanced every step, the expected growth per step is the weighted
    # average of each asset's expected growth, and steps are independent:
    #   E[V_T] = V_0 x (sum of w_i x (1 + r_i)^dt) ^ n_steps
    w, r, v = [0.5, 0.3, 0.2], [0.09, 0.05, 0.03], [0.22, 0.12, 0.05]
    corr = [[1, 0.4, 0.1], [0.4, 1, 0.2], [0.1, 0.2, 1]]
    res = mc.simulate_portfolio(1_000, w, r, v, corr, years=5, steps_per_year=12,
                                n_sims=N, rebalance=True, seed=21)
    per_step = sum(wi * (1 + ri) ** (1 / 12) for wi, ri in zip(w, r))
    exact = 1_000 * per_step ** 60
    se = res.terminal.std(ddof=1) / math.sqrt(N)
    assert abs(res.mean_terminal() - exact) < Z * se


def test_buy_and_hold_portfolio_mean_matches_weighted_future_values():
    w, r, v = [0.5, 0.3, 0.2], [0.09, 0.05, 0.03], [0.22, 0.12, 0.05]
    corr = [[1, 0.4, 0.1], [0.4, 1, 0.2], [0.1, 0.2, 1]]
    res = mc.simulate_portfolio(1_000, w, r, v, corr, years=5, n_sims=N,
                                rebalance=False, seed=22)
    exact = sum(tvm.future_value(1_000 * wi, ri, 5) for wi, ri in zip(w, r))
    se = res.terminal.std(ddof=1) / math.sqrt(N)
    assert abs(res.mean_terminal() - exact) < Z * se


def test_one_step_portfolio_variance_matches_lognormal_covariance():
    # Over one step, each asset's growth g_i is lognormal with
    #   E[g_i] = (1 + r_i)^dt
    #   Cov(g_i, g_j) = E[g_i] E[g_j] (exp(rho_ij sigma_i sigma_j dt) - 1)
    # so the portfolio's return variance is sum over i, j of w_i w_j Cov(g_i, g_j).
    # This is what checks that the correlation matrix is applied correctly.
    w, r, v = [0.5, 0.5], [0.08, 0.04], [0.30, 0.15]
    rho = -0.4
    corr = [[1, rho], [rho, 1]]
    res = mc.simulate_portfolio(1.0, w, r, v, corr, years=1, steps_per_year=1,
                                n_sims=N, seed=33)
    eg = [1 + ri for ri in r]
    cov = [[eg[i] * eg[j] * (math.exp(corr[i][j] * v[i] * v[j]) - 1) for j in range(2)]
           for i in range(2)]
    exact = sum(w[i] * w[j] * cov[i][j] for i in range(2) for j in range(2))
    sample = res.terminal.var(ddof=1)
    # The SE of a sample variance depends on the fourth moment, so estimate it from the data.
    dev2 = (res.terminal - res.terminal.mean()) ** 2
    se = dev2.std(ddof=1) / math.sqrt(N)
    assert abs(sample - exact) < Z * se


def test_negative_correlation_lowers_portfolio_risk():
    w, r, v = [0.5, 0.5], [0.07, 0.07], [0.20, 0.20]
    args = dict(years=1, steps_per_year=12, n_sims=50_000, seed=4)
    neg = mc.simulate_portfolio(1_000, w, r, v, [[1, -0.5], [-0.5, 1]], **args)
    pos = mc.simulate_portfolio(1_000, w, r, v, [[1, 0.9], [0.9, 1]], **args)
    assert neg.terminal.std() < pos.terminal.std()
    assert neg.value_at_risk() < pos.value_at_risk()


# 3. Structure, reproducibility and validation


def test_same_seed_same_paths_different_seed_different_paths():
    a = mc.simulate_gbm(1_000, 0.07, 0.2, 2, n_sims=100, seed=123)
    b = mc.simulate_gbm(1_000, 0.07, 0.2, 2, n_sims=100, seed=123)
    c = mc.simulate_gbm(1_000, 0.07, 0.2, 2, n_sims=100, seed=124)
    assert np.array_equal(a.paths, b.paths)
    assert not np.array_equal(a.paths, c.paths)


def test_single_asset_portfolio_equals_simulate_gbm():
    gbm = mc.simulate_gbm(1_000, 0.07, 0.2, 3, n_sims=500, contribution=50, seed=8)
    port = mc.simulate_portfolio(1_000, [1.0], [0.07], [0.2], [[1.0]], 3,
                                 n_sims=500, contribution=50, seed=8)
    assert np.allclose(gbm.paths, port.paths)


def test_rebalanced_and_buy_and_hold_agree_over_a_single_step():
    w, r, v = [0.7, 0.3], [0.08, 0.03], [0.2, 0.06]
    corr = [[1, 0.3], [0.3, 1]]
    a = mc.simulate_portfolio(1_000, w, r, v, corr, 1, steps_per_year=1,
                              n_sims=1_000, rebalance=True, seed=6)
    b = mc.simulate_portfolio(1_000, w, r, v, corr, 1, steps_per_year=1,
                              n_sims=1_000, rebalance=False, seed=6)
    assert np.allclose(a.terminal, b.terminal)


def test_paths_shape_time_axis_and_bands():
    res = mc.simulate_gbm(1_000, 0.07, 0.2, 2, steps_per_year=12, n_sims=300, seed=1)
    assert res.paths.shape == (300, 25)
    assert res.time_axis[-1] == 2.0
    bands = res.percentile_bands((5, 50, 95))
    assert all(len(b) == 25 for b in bands.values())
    assert np.all(bands[5] <= bands[50]) and np.all(bands[50] <= bands[95])
    assert np.allclose(res.paths[:, 0], 1_000)


def test_summary_has_every_headline_number():
    s = mc.simulate_gbm(1_000, 0.07, 0.2, 2, n_sims=1_000, seed=1).summary()
    for key in ("mean_terminal", "median_terminal", "percentiles", "prob_loss",
                "value_at_risk", "conditional_value_at_risk", "invested"):
        assert key in s


def test_perfectly_correlated_assets_are_accepted():
    # Correlation exactly +1 makes the matrix singular, so Cholesky fails.
    # The eigenvalue fallback has to take over.
    res = mc.simulate_portfolio(1_000, [0.5, 0.5], [0.07, 0.07], [0.2, 0.2],
                                [[1, 1], [1, 1]], 1, n_sims=1_000, seed=1)
    single = mc.simulate_gbm(1_000, 0.07, 0.2, 1, n_sims=1_000, seed=1)
    # Two identical, perfectly correlated assets have the same spread as one.
    assert math.isclose(res.terminal.std(), single.terminal.std(), rel_tol=0.1)


def test_impossible_correlation_matrix_is_rejected():
    # Each pair is between -1 and +1, but A~B and B~C strongly positive with
    # A~C strongly negative can't all hold at once.
    bad = [[1, 0.9, -0.9], [0.9, 1, 0.9], [-0.9, 0.9, 1]]
    with pytest.raises(ValueError, match="positive semi-definite"):
        mc.simulate_portfolio(1_000, [1 / 3] * 3, [0.07] * 3, [0.2] * 3, bad, 1, n_sims=10)


@pytest.mark.parametrize("corr, msg", [
    ([[1, 0.3], [0.5, 1]], "symmetric"),
    ([[0.9, 0.3], [0.3, 1]], "diagonal"),
    ([[1, 1.2], [1.2, 1]], "between -1 and \\+1"),
])
def test_invalid_correlation_matrices(corr, msg):
    with pytest.raises(ValueError, match=msg):
        mc.correlation_factor(corr)


@pytest.mark.parametrize("kwargs, msg", [
    (dict(initial_value=-1), "negative"),
    (dict(contribution=-10), "Contribution"),
    (dict(volatility=-0.1), "Volatility"),
    (dict(expected_return=-1.0), "greater than -100%"),
    (dict(years=1.5, steps_per_year=1), "whole number of steps"),
    (dict(years=0), "positive"),
    (dict(n_sims=0), "simulations"),
])
def test_simulate_gbm_rejects_bad_inputs(kwargs, msg):
    args = dict(initial_value=1_000, expected_return=0.07, volatility=0.2, years=1, n_sims=10)
    args.update(kwargs)
    with pytest.raises(ValueError, match=msg):
        mc.simulate_gbm(**args)


def test_portfolio_rejects_weights_that_dont_sum_to_one():
    with pytest.raises(ValueError, match="add up to 1"):
        mc.simulate_portfolio(1_000, [0.5, 0.4], [0.07, 0.05], [0.2, 0.1],
                              [[1, 0], [0, 1]], 1, n_sims=10)


def test_bad_confidence_level_rejected():
    res = mc.simulate_gbm(1_000, 0.07, 0.2, 1, n_sims=100, seed=1)
    with pytest.raises(ValueError):
        res.value_at_risk(1.0)


# Bootstrap


def test_bootstrap_of_a_constant_history_is_deterministic():
    res = mc.bootstrap_returns(1_000, [0.01] * 24, n_periods=36, n_sims=50, seed=1)
    assert np.allclose(res.terminal, tvm.future_value(1_000, 0.01, 36))


def test_bootstrap_only_produces_outcomes_from_the_history():
    history = [0.05, -0.03, 0.02, -0.08, 0.10]
    res = mc.bootstrap_returns(1_000, history, n_periods=1, n_sims=2_000, seed=1)
    allowed = {round(1_000 * (1 + h), 9) for h in history}
    assert {round(v, 9) for v in res.terminal} <= allowed


def test_bootstrap_mean_matches_history_average():
    history = [0.05, -0.03, 0.02, -0.08, 0.10, 0.01]
    res = mc.bootstrap_returns(1_000, history, n_periods=1, n_sims=N, seed=2)
    exact = 1_000 * (1 + np.mean(history))
    se = res.terminal.std(ddof=1) / math.sqrt(N)
    assert abs(res.mean_terminal() - exact) < Z * se


def test_block_bootstrap_keeps_runs_of_consecutive_periods():
    history = [0.001 * k for k in range(1, 13)]  # each return tells us its position
    res = mc.bootstrap_returns(1_000, history, n_periods=12, n_sims=500,
                               block_size=3, seed=3)
    returns = res.paths[:, 1:] / res.paths[:, :-1] - 1
    positions = np.rint(returns / 0.001).astype(int) - 1
    for block in range(4):
        chunk = positions[:, 3 * block: 3 * block + 3]
        assert np.all(np.diff(chunk, axis=1) == 1)


def test_full_length_block_replays_history_in_order():
    history = [0.04, -0.02, 0.03, 0.01]
    res = mc.bootstrap_returns(1_000, history, n_periods=4, n_sims=20,
                               block_size=4, seed=1)
    expected = 1_000 * np.prod([1 + h for h in history])
    assert np.allclose(res.terminal, expected)


@pytest.mark.parametrize("kwargs, msg", [
    (dict(periodic_returns=[0.01]), "at least 2"),
    (dict(periodic_returns=[0.01, -1.0]), "-100%"),
    (dict(block_size=10), "Block size"),
    (dict(n_periods=0), "periods"),
])
def test_bootstrap_rejects_bad_inputs(kwargs, msg):
    args = dict(initial_value=1_000, periodic_returns=[0.01, 0.02, -0.01], n_periods=12, n_sims=10)
    args.update(kwargs)
    with pytest.raises(ValueError, match=msg):
        mc.bootstrap_returns(**args)


# Working backward: contribution_for_goal


def test_contribution_for_goal_without_volatility_matches_annuity_math():
    # No randomness: goal = FV(initial) + c x FV-annuity factor, solved for c.
    r, years, initial, goal = 0.07, 20, 5_000, 250_000
    monthly = (1 + r) ** (1 / 12) - 1
    exact = (goal - tvm.future_value(initial, monthly, 240)) / tvm.fv_annuity(1, monthly, 240)
    c = mc.contribution_for_goal(initial, goal, 0.8, r, 0.0, years, n_sims=200, seed=1)
    assert math.isclose(c, exact, rel_tol=1e-9)


def test_contribution_for_goal_is_zero_when_the_goal_is_already_covered():
    assert mc.contribution_for_goal(100_000, 50_000, 0.9, 0.05, 0.1, 10, n_sims=500, seed=1) == 0.0


@pytest.mark.parametrize("confidence", [0.5, 0.8, 0.95])
def test_contribution_for_goal_hits_the_confidence_and_no_less_would(confidence):
    args = dict(expected_return=0.07, volatility=0.16, years=15, n_sims=20_000, seed=7)
    goal = 300_000
    c = mc.contribution_for_goal(10_000, goal, confidence, **args)
    at = mc.simulate_gbm(10_000, contribution=c * (1 + 1e-9), **args)
    assert at.prob_reaching(goal) >= confidence                 # reaches the confidence level
    below = mc.simulate_gbm(10_000, contribution=c * 0.99, **args)
    assert below.prob_reaching(goal) < confidence               # and a bit less does not


def test_contribution_for_goal_rises_with_confidence_and_with_volatility():
    base = dict(initial_value=10_000, goal=300_000, expected_return=0.07, years=15,
                n_sims=10_000, seed=3)
    low = mc.contribution_for_goal(confidence=0.5, volatility=0.16, **base)
    high = mc.contribution_for_goal(confidence=0.9, volatility=0.16, **base)
    wild = mc.contribution_for_goal(confidence=0.9, volatility=0.30, **base)
    assert low < high < wild


def test_contribution_for_goal_with_no_starting_money():
    c = mc.contribution_for_goal(0, 100_000, 0.8, 0.06, 0.15, 20, n_sims=5_000, seed=2)
    res = mc.simulate_gbm(0, 0.06, 0.15, 20, n_sims=5_000, contribution=c * (1 + 1e-9), seed=2)
    assert res.prob_reaching(100_000) >= 0.8


@pytest.mark.parametrize("kwargs, msg", [
    (dict(goal=0), "Goal"),
    (dict(confidence=1.0), "Confidence"),
    (dict(confidence=0.0), "Confidence"),
])
def test_contribution_for_goal_validation(kwargs, msg):
    args = dict(initial_value=1_000, goal=10_000, confidence=0.8, expected_return=0.05,
                volatility=0.1, years=5, n_sims=100)
    args.update(kwargs)
    with pytest.raises(ValueError, match=msg):
        mc.contribution_for_goal(**args)


@pytest.mark.parametrize("n_sims, confidence", [(10, 0.85), (7, 0.5), (23, 0.9), (50, 0.95)])
def test_contribution_for_goal_never_falls_short_of_confidence_with_few_simulations(n_sims, confidence):
    # With few paths, rounding the quantile the wrong way leaves the answer one path short.
    args = dict(expected_return=0.06, volatility=0.25, years=10, n_sims=n_sims, seed=5)
    c = mc.contribution_for_goal(2_000, 80_000, confidence, **args)
    res = mc.simulate_gbm(2_000, contribution=c * (1 + 1e-9), **args)
    assert res.prob_reaching(80_000) >= confidence
