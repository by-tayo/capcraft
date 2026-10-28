"""Tests for capcraft.risk_return."""
import math

import pytest

from capcraft import risk_return as rr


def test_asset_return_splits_into_yields():
    r = rr.asset_return(40, 43, 1.20)
    assert math.isclose(r["capital_gain_yield"], 3 / 40)
    assert math.isclose(r["income_yield"], 1.20 / 40)
    assert math.isclose(r["total"], r["capital_gain_yield"] + r["income_yield"])


def test_asset_return_matches_total_profit():
    r = rr.asset_return(40, 43, 1.20)
    shares = 2000 / 40
    profit = rr.profit_from_return(r["total"], 2000)
    mv0, mv1 = rr.market_value(shares, 40), rr.market_value(shares, 43)
    income = shares * 1.20
    assert math.isclose(profit, rr.total_profit(mv0, mv1, income))


def test_return_after_share_change_spinoff():
    end_value = 46 + 0.5 * 10
    result = rr.return_after_share_change(end_value, 50, 1.0)
    assert math.isclose(result, (end_value - 50 + 1.0) / 50)


def test_expected_return_requires_probabilities_sum_to_one():
    with pytest.raises(ValueError):
        rr.expected_return([0.3, 0.3], [0.1, 0.2])


def test_scenario_variance_and_sd():
    probs, rets = [0.30, 0.50, 0.20], [0.25, 0.10, -0.15]
    er = rr.expected_return(probs, rets)
    var = rr.scenario_variance(probs, rets)
    assert math.isclose(rr.scenario_sd(probs, rets), math.sqrt(var))
    assert math.isclose(er, 0.30 * 0.25 + 0.50 * 0.10 + 0.20 * -0.15)


def test_historical_variance_uses_sample_convention():
    rets = [0.12, -0.04, 0.18, 0.07, 0.02]
    avg = rr.average_return(rets)
    expected_var = sum((r - avg) ** 2 for r in rets) / (len(rets) - 1)
    assert math.isclose(rr.historical_variance(rets), expected_var)


def test_portfolio_return_two_methods_agree():
    mv0 = [rr.market_value(60, 100), rr.market_value(200, 20)]
    mv1 = [rr.market_value(60, 106), rr.market_value(200, 19)]
    inc = [60 * 1.00, 0.0]
    w = rr.weights_from_values(mv0)
    r_x = rr.asset_return(100, 106, 1.00)["total"]
    r_y = rr.asset_return(20, 19, 0.0)["total"]
    m1 = rr.portfolio_return_by_dollars(mv0, mv1, inc)
    m2 = rr.portfolio_return(w, [r_x, r_y])
    assert math.isclose(m1, m2)


def test_portfolio_variance_two_matches_long_way():
    m = [0.12, -0.04, 0.18, 0.07, 0.02]
    n = [0.04, 0.08, 0.06, 0.03, 0.04]
    sd_m, sd_n = rr.historical_sd(m), rr.historical_sd(n)
    corr = rr.historical_correlation(m, n)
    var_p = rr.portfolio_variance_two(0.5, 0.5, sd_m, sd_n, corr)
    p_series = [0.5 * a + 0.5 * b for a, b in zip(m, n)]
    assert math.isclose(var_p, rr.historical_variance(p_series))


def test_portfolio_variance_matches_two_asset_formula_for_two_assets():
    w = [0.5, 0.5]
    s = [0.20, 0.20]
    corr = [[1, 0.3], [0.3, 1]]
    v_n = rr.portfolio_variance(w, s, corr)
    v2 = rr.portfolio_variance_two(0.5, 0.5, 0.20, 0.20, 0.3)
    assert math.isclose(v_n, v2)


def test_portfolio_variance_rejects_asymmetric_correlation_matrix():
    with pytest.raises(ValueError):
        rr.portfolio_variance([0.5, 0.5], [0.2, 0.2], [[1, 0.3], [0.5, 1]])


def test_relevant_risk_contributions_sum_to_portfolio_risk():
    m = [0.12, -0.04, 0.18, 0.07, 0.02]
    n = [0.04, 0.08, 0.06, 0.03, 0.04]
    sd_m, sd_n = rr.historical_sd(m), rr.historical_sd(n)
    corr = rr.historical_correlation(m, n)
    sd_p = rr.portfolio_sd(rr.portfolio_variance_two(0.5, 0.5, sd_m, sd_n, corr))
    p_series = [0.5 * a + 0.5 * b for a, b in zip(m, n)]
    corr_mp = rr.historical_correlation(m, p_series)
    corr_np = rr.historical_correlation(n, p_series)
    total = rr.portfolio_sd_from_contributions([0.5, 0.5], [sd_m, sd_n], [corr_mp, corr_np])
    assert math.isclose(total, sd_p)


def test_beta_and_idiosyncratic_risk_combine_like_right_triangle():
    sd, corr, sd_mkt = 0.24, 0.75, 0.15
    sys = rr.systematic_risk(sd, corr)
    idio = rr.idiosyncratic_risk(sd, corr)
    assert math.isclose(sys ** 2 + idio ** 2, sd ** 2)
    b = rr.beta(sd, corr, sd_mkt)
    assert math.isclose(b, sys / sd_mkt)


def test_capm_and_risk_premium():
    rf, beta_i, mkt = 0.04, 1.1, 0.09
    assert math.isclose(rr.capm(rf, beta_i, mkt), rf + beta_i * (mkt - rf))


def test_beta_from_expected_return_inverts_capm():
    rf, mkt = 0.04, 0.09
    implied_beta = rr.beta_from_expected_return(0.13, rf, mkt)
    assert math.isclose(rr.capm(rf, implied_beta, mkt), 0.13)


def test_portfolio_beta_agrees_with_portfolio_expected_return_via_capm():
    rf, mkt = 0.04, 0.09
    w, betas = [0.7, 0.3], [1.2, 0.4]
    erp_capm = rr.capm(rf, rr.portfolio_beta(w, betas), mkt)
    erp_avg = rr.portfolio_expected_return(w, [rr.capm(rf, b, mkt) for b in betas])
    assert math.isclose(erp_capm, erp_avg)


def test_equal_weight_risk_approaches_floor_as_n_grows():
    floor = 0.35 * math.sqrt(0.30)
    risk_50 = rr.equal_weight_risk(50, 0.35, 0.30)
    risk_1 = rr.equal_weight_risk(1, 0.35, 0.30)
    assert risk_1 > risk_50 > floor
    assert risk_50 - floor < risk_1 - floor


def test_is_diversified_detects_perfect_positive_correlation_as_not_diversified():
    sp = rr.portfolio_sd(rr.portfolio_variance_two(0.5, 0.5, 0.20, 0.20, 1.0))
    diversified, wavg = rr.is_diversified(sp, [0.5, 0.5], [0.20, 0.20])
    assert not diversified
    assert math.isclose(sp, wavg)
