"""Tests for capcraft.portfolio. The portfolio class must agree with the plain
risk_return functions and with identities that hold for any data."""
import math

import numpy as np
import pytest

from capcraft import risk_metrics as rm
from capcraft import risk_return as rr
from capcraft.portfolio import Holding, Portfolio

M = [0.12, -0.04, 0.18, 0.07, 0.02]
N = [0.04, 0.08, 0.06, 0.03, 0.04]
BENCH = [0.06, 0.00, 0.09, 0.04, 0.01]


def approx(a, b, tol=1e-9):
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


@pytest.fixture
def mn():
    return Portfolio([Holding("M", 0.5, M), Holding("N", 0.5, N)])


@pytest.fixture
def three():
    rng = np.random.default_rng(5)
    r = rng.normal(0.008, [0.05, 0.03, 0.08], size=(60, 3))
    return Portfolio([Holding("A", 0.5, r[:, 0].tolist()), Holding("B", 0.3, r[:, 1].tolist()),
                      Holding("C", 0.2, r[:, 2].tolist())])


# Construction


def test_construction_validates_inputs():
    with pytest.raises(ValueError, match="at least one"):
        Portfolio([])
    with pytest.raises(ValueError, match="same number"):
        Portfolio([Holding("A", 0.5, [0.1, 0.2]), Holding("B", 0.5, [0.1])])
    with pytest.raises(ValueError, match="add up to 1"):
        Portfolio([Holding("A", 0.5, M), Holding("B", 0.4, N)])
    with pytest.raises(ValueError, match="unique"):
        Portfolio([Holding("A", 0.5, M), Holding("A", 0.5, N)])
    with pytest.raises(ValueError, match="periods_per_year"):
        Portfolio([Holding("A", 1.0, M)], periods_per_year=0)


def test_from_market_values_and_with_weights():
    p = Portfolio.from_market_values(["X", "Y"], [6000, 4000], [M, N])
    assert p.weights == pytest.approx([0.6, 0.4])
    q = p.with_weights([0.5, 0.5])
    assert q.weights == [0.5, 0.5] and p.weights == pytest.approx([0.6, 0.4])
    assert q.names == ["X", "Y"]


# Return and risk agree with risk_return.py


def test_period_returns_are_the_weighted_average_each_period(mn):
    assert mn.period_returns() == pytest.approx([0.5 * a + 0.5 * b for a, b in zip(M, N)])


def test_risk_matches_the_two_asset_formula(mn):
    sd_m, sd_n = rr.historical_sd(M), rr.historical_sd(N)
    corr = rr.historical_correlation(M, N)
    direct = rr.portfolio_sd(rr.portfolio_variance_two(0.5, 0.5, sd_m, sd_n, corr))
    assert approx(mn.risk(), direct)
    assert approx(mn.risk(), 0.040620192023179805)


def test_portfolio_variance_equals_variance_of_its_own_return_series(three):
    var, _ = three.variance()
    assert approx(var, rr.historical_variance(three.period_returns()))


def test_covariance_and_correlation_matrices_match_pairwise_functions(three):
    cov, corr = three.covariance_matrix(), three.correlation_matrix()
    series = three.returns_matrix()
    for i in range(3):
        assert approx(cov[i, i], rr.historical_variance(series[i]))
        assert approx(corr[i, i], 1.0)
        for j in range(3):
            assert approx(cov[i, j], rr.historical_covariance(series[i], series[j]))
            assert approx(corr[i, j], rr.historical_correlation(series[i], series[j]))
    assert np.allclose(cov, cov.T) and np.allclose(corr, corr.T)


def test_correlation_matrix_rejects_a_flat_series():
    p = Portfolio([Holding("A", 0.5, [0.01, 0.01, 0.01]), Holding("B", 0.5, [0.01, 0.02, 0.03])])
    with pytest.raises(ValueError, match="No variation.*A"):
        p.correlation_matrix()


def test_single_holding_portfolio():
    p = Portfolio([Holding("M", 1.0, M)])
    assert approx(p.risk(), rr.historical_sd(M))
    assert p.period_returns() == pytest.approx(M)
    assert p.covariance_matrix().shape == (1, 1)


def test_diversification_flag_and_weighted_average_risk(mn):
    diversified, wavg = mn.is_diversified()
    assert diversified
    assert approx(wavg, 0.5 * rr.historical_sd(M) + 0.5 * rr.historical_sd(N))
    same = Portfolio([Holding("A", 0.5, M), Holding("B", 0.5, [2 * x for x in M])])
    assert not same.is_diversified()[0]       # perfectly correlated


def test_relevant_risk_contributions_add_up_to_portfolio_risk(three):
    parts = three.relevant_risk()
    assert approx(sum(p["contribution"] for p in parts), three.risk())
    assert [p["name"] for p in parts] == ["A", "B", "C"]


def test_expected_return_defaults_to_historical_averages(mn):
    assert approx(mn.expected_return(), 0.5 * rr.average_return(M) + 0.5 * rr.average_return(N))
    assert approx(mn.expected_return([0.10, 0.04]), 0.07)
    assert approx(mn.average_return(), mn.expected_return())


# Annualizing


def test_annualized_return_is_geometric_by_default(mn):
    series = mn.period_returns()
    assert approx(mn.annualized_return(), rm.cagr(series, 12))
    assert approx(mn.annualized_return("arithmetic"), rr.average_return(series) * 12)
    assert mn.annualized_return() < (1 + mn.average_return()) ** 12 - 1   # not the old overstated figure


def test_annualized_risk_scales_with_sqrt_of_periods(mn):
    assert approx(mn.annualized_risk(), mn.risk() * math.sqrt(12))
    quarterly = Portfolio([Holding("M", 0.5, M), Holding("N", 0.5, N)], periods_per_year=4)
    assert approx(quarterly.annualized_risk(), mn.risk() * 2)


# Beta


def test_portfolio_beta_equals_beta_of_the_portfolio_series(mn):
    # Covariance is linear, so the weighted average of holding betas
    # must equal the beta of the blended return series.
    from_holdings = mn.beta(BENCH)
    from_series = rm.beta_vs_benchmark(mn.period_returns(), BENCH)
    assert approx(from_holdings, from_series)


def test_beta_with_supplied_values_and_missing_values():
    p = Portfolio([Holding("A", 0.7, M, beta=1.2), Holding("B", 0.3, N, beta=0.4)])
    assert approx(p.beta(), 0.7 * 1.2 + 0.3 * 0.4)
    q = Portfolio([Holding("A", 0.7, M, beta=1.2), Holding("B", 0.3, N)])
    with pytest.raises(ValueError, match="Missing beta for: B"):
        q.beta()
    assert approx(q.beta(BENCH), p.with_weights([0.7, 0.3]).beta(BENCH))   # benchmark path ignores supplied betas


def test_betas_vs_checks_length(mn):
    with pytest.raises(ValueError, match="periods"):
        mn.betas_vs(BENCH[:-1])


def test_risk_metrics_passthrough(mn):
    m = mn.risk_metrics(risk_free_rate=0.002, benchmark_returns=BENCH)
    series = mn.period_returns()
    assert approx(m["sharpe_ratio"], rm.sharpe_ratio(series, 0.002))
    assert approx(m["beta_vs_benchmark"], mn.beta(BENCH))
    assert m["sortino_ratio"] is None             # this blend never has a down month


def test_summary_keys(mn):
    s = mn.summary()
    assert s["names"] == ["M", "N"] and s["diversified"] is True
    assert approx(s["annualized_return"], mn.annualized_return())
    assert approx(s["annualized_return_arithmetic"], mn.average_return() * 12)


# Efficient frontier


def test_frontier_samples_are_valid_long_only_mixes(three):
    f = three.efficient_frontier(n_portfolios=2_000, seed=1)
    assert f.weights.shape == (3 + 2_000, 3)
    assert np.allclose(f.weights.sum(axis=1), 1.0) and (f.weights >= 0).all()
    assert np.allclose(f.weights[:3], np.eye(3))      # the single-asset corners come first


def test_frontier_numbers_match_direct_calculation(three):
    f = three.efficient_frontier(n_portfolios=50, risk_free_rate=0.02, seed=2)
    for i in (0, 4, 17, 40):
        mix = three.with_weights(f.weights[i].tolist())
        assert approx(f.risks[i], mix.annualized_risk())
        assert approx(f.returns[i], mix.annualized_return("arithmetic"))
        assert approx(f.sharpes[i], (f.returns[i] - 0.02) / f.risks[i])


def test_frontier_is_reproducible_with_a_seed(three):
    a = three.efficient_frontier(500, seed=9).weights
    b = three.efficient_frontier(500, seed=9).weights
    c = three.efficient_frontier(500, seed=10).weights
    assert np.array_equal(a, b) and not np.array_equal(a, c)


def test_frontier_beats_every_single_asset(three):
    f = three.efficient_frontier(3_000, risk_free_rate=0.01, seed=3)
    corner_risks, corner_sharpes = f.risks[:3], f.sharpes[:3]
    assert f.min_variance()["annual_risk"] <= corner_risks.min()
    assert f.max_sharpe()["sharpe"] >= corner_sharpes.max()
    assert approx(sum(f.max_sharpe()["weights"].values()), 1.0)


def test_sampled_minimum_variance_approaches_the_exact_two_asset_answer():
    # Exact minimum-variance weight for two assets (no short selling):
    #   w_A = (sd_B^2 - rho sd_A sd_B) / (sd_A^2 + sd_B^2 - 2 rho sd_A sd_B)
    p = Portfolio([Holding("M", 0.5, M), Holding("N", 0.5, N)])
    sa, sb, rho = rr.historical_sd(M), rr.historical_sd(N), rr.historical_correlation(M, N)
    w = (sb ** 2 - rho * sa * sb) / (sa ** 2 + sb ** 2 - 2 * rho * sa * sb)
    assert 0 < w < 1
    exact = math.sqrt(12) * rr.portfolio_sd(rr.portfolio_variance_two(w, 1 - w, sa, sb, rho))
    sampled = p.efficient_frontier(20_000, seed=4).min_variance()
    assert sampled["annual_risk"] >= exact - 1e-12          # nothing can beat the exact minimum
    assert sampled["annual_risk"] < exact * 1.01            # and sampling gets within 1%
    assert abs(sampled["weights"]["M"] - w) < 0.02


def test_efficient_edge_only_moves_up_and_right(three):
    risks, rets = three.efficient_frontier(4_000, seed=6).efficient_edge()
    assert len(risks) >= 3
    assert np.all(np.diff(rets) > 0) and np.all(np.diff(risks) >= 0)


def test_frontier_input_validation(three):
    with pytest.raises(ValueError, match="at least 2"):
        Portfolio([Holding("M", 1.0, M)]).efficient_frontier()
    with pytest.raises(ValueError, match="n_portfolios"):
        three.efficient_frontier(0)
