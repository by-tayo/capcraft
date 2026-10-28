"""Risk and return: expected return, variance, portfolio risk, beta, CAPM.

Every formula from the LAY/ERD "Math of Risk and Return" guide, as
plain Python. portfolio.py and the new risk_metrics build on these
rather than duplicating them.

Conventions
-----------
* Returns, standard deviations and weights are DECIMALS: 10% -> 0.10.
* Variances are in decimal-squared units (0.10 ** 2 = 0.01).
  Multiply by 10,000 to get "percent-squared" (0.01 -> 100 %^2).
* History-based variance and covariance divide by (T - 1), the
  sample convention.

Ported from the original risk_return.py teaching script. The
interactive calculator menu from that script is not carried over —
capcraft is meant to be driven by code (and later, a dashboard), not a
text menu. Worked examples now live in examples/risk_return_examples.py.
"""
from math import sqrt, isclose

TOL = 1e-9


# Input checks


def _check_same_length(*seqs):
    lengths = {len(s) for s in seqs}
    if len(lengths) != 1:
        raise ValueError(f"Inputs must be the same length, got lengths {sorted(lengths)}")


def _check_sums_to_one(values, name):
    total = sum(values)
    if not isclose(total, 1.0, abs_tol=1e-6):
        raise ValueError(f"{name} must add up to 1 (100%), got {total:.6f}")


def _check_min_periods(returns, minimum=2):
    if len(returns) < minimum:
        raise ValueError(f"Need at least {minimum} periods of returns, got {len(returns)}")


# 1. Return on one investment over one period


def market_value(units, price_per_unit):
    """Market value = number of units x price per unit."""
    return units * price_per_unit


def capital_gain(mv_begin, mv_end):
    """Capital gain (loss) = value at end - value at beginning."""
    return mv_end - mv_begin


def total_profit(mv_begin, mv_end, income=0.0):
    """Total profit = value at end - value at beginning + income received."""
    return mv_end - mv_begin + income


def asset_return(price_begin, price_end, income=0.0):
    """
    Return over one period, split into its two sources.

    total return       = (P_end - P_begin + C) / P_begin
    capital gain yield = (P_end - P_begin) / P_begin
    income yield       = C / P_begin   (the dividend yield, for a stock)
    """
    if price_begin <= 0:
        raise ValueError("Beginning price must be positive")
    cg_yield = (price_end - price_begin) / price_begin
    inc_yield = income / price_begin
    return {"total": cg_yield + inc_yield,
            "capital_gain_yield": cg_yield,
            "income_yield": inc_yield}


def return_after_share_change(value_at_end_of_one_original_share,
                              price_begin, dividends_received=0.0):
    """
    Return when the share changes shape during the period (a spin-off or
    a stock split). Follow ONE share you bought at the start:

        return = (value at end of everything that one share became
                  - price paid for it
                  + all dividends received on it) / price paid for it
    """
    if price_begin <= 0:
        raise ValueError("Beginning price must be positive")
    return (value_at_end_of_one_original_share - price_begin
            + dividends_received) / price_begin


def profit_from_return(period_return, amount_invested):
    """Total profit (loss) = return x amount invested."""
    return period_return * amount_invested


# 2. Expected return and risk when the possible outcomes are known


def expected_return(probabilities, returns):
    """E(R) = sum of (probability of each scenario x return in that scenario)."""
    _check_same_length(probabilities, returns)
    _check_sums_to_one(probabilities, "Probabilities")
    return sum(p * r for p, r in zip(probabilities, returns))


def scenario_variance(probabilities, returns):
    """Variance = sum of probability x (return - expected return) squared."""
    er = expected_return(probabilities, returns)
    return sum(p * (r - er) ** 2 for p, r in zip(probabilities, returns))


def scenario_sd(probabilities, returns):
    """Standard deviation (risk) = square root of the variance."""
    return sqrt(scenario_variance(probabilities, returns))


# 3. Average return and risk from past returns


def average_return(returns):
    """Arithmetic average = (R1 + R2 + ... + RT) / T."""
    _check_min_periods(returns, 1)
    return sum(returns) / len(returns)


def historical_variance(returns):
    """Variance = sum of (return - average) squared, divided by (T - 1)."""
    _check_min_periods(returns, 2)
    avg = average_return(returns)
    return sum((r - avg) ** 2 for r in returns) / (len(returns) - 1)


def historical_sd(returns):
    """Standard deviation (risk) = square root of the variance."""
    return sqrt(historical_variance(returns))


# 4. Portfolio return

def weights_from_values(market_values):
    """Weight of each holding = its market value / value of the whole portfolio."""
    total = sum(market_values)
    if total <= 0:
        raise ValueError("Total portfolio value must be positive")
    return [mv / total for mv in market_values]


def portfolio_return(weights, returns):
    """R_p = w1*R1 + w2*R2 + ... + wn*Rn."""
    _check_same_length(weights, returns)
    _check_sums_to_one(weights, "Weights")
    return sum(w * r for w, r in zip(weights, returns))


def portfolio_return_by_dollars(mv_begin_list, mv_end_list, income_list):
    """Method 1: add up every dollar of profit, divide by dollars invested."""
    _check_same_length(mv_begin_list, mv_end_list, income_list)
    profit = sum(total_profit(b, e, c)
                 for b, e, c in zip(mv_begin_list, mv_end_list, income_list))
    return profit / sum(mv_begin_list)


# 5. Expected return of a portfolio


def portfolio_expected_return(weights, expected_returns):
    """E(R_p) = w1*E(R1) + w2*E(R2) + ... + wn*E(Rn)."""
    return portfolio_return(weights, expected_returns)



# 6. Correlation and portfolio risk


def historical_covariance(returns_a, returns_b):
    """
    Covariance from past returns (sample convention):
    sum of (A's gap from its average x B's gap from its average) / (T - 1).
    """
    _check_same_length(returns_a, returns_b)
    _check_min_periods(returns_a, 2)
    avg_a, avg_b = average_return(returns_a), average_return(returns_b)
    return (sum((a - avg_a) * (b - avg_b) for a, b in zip(returns_a, returns_b))
            / (len(returns_a) - 1))


def correlation_from_cov(cov_ab, sd_a, sd_b):
    """Corr(A, B) = Cov(A, B) / (sd_A x sd_B). Always between -1 and +1."""
    if sd_a == 0 or sd_b == 0:
        raise ValueError("Correlation is undefined when a standard deviation is 0")
    return cov_ab / (sd_a * sd_b)


def historical_correlation(returns_a, returns_b):
    """Correlation computed straight from two series of past returns."""
    return correlation_from_cov(historical_covariance(returns_a, returns_b),
                                historical_sd(returns_a), historical_sd(returns_b))


def portfolio_variance_two(w_a, w_b, sd_a, sd_b, corr_ab):
    """sigma_p^2 = wA^2 sdA^2 + wB^2 sdB^2 + 2 wA wB corrAB sdA sdB."""
    _check_sums_to_one([w_a, w_b], "Weights")
    return (w_a ** 2 * sd_a ** 2 + w_b ** 2 * sd_b ** 2
            + 2 * w_a * w_b * corr_ab * sd_a * sd_b)


def portfolio_variance(weights, sds, corr):
    """
    Any number of assets: one squared term per asset, plus
    2 x wi x wj x corr_ij x sd_i x sd_j for every pair.
    `corr` is a full correlation matrix (list of lists, 1s on the diagonal).
    With 3 assets this is exactly the 3-asset formula.
    """
    n = len(weights)
    _check_same_length(weights, sds, corr)
    _check_sums_to_one(weights, "Weights")
    for row in corr:
        if len(row) != n:
            raise ValueError("Correlation matrix must be n x n")
    total = 0.0
    for i in range(n):
        total += weights[i] ** 2 * sds[i] ** 2
        for j in range(i + 1, n):
            if not isclose(corr[i][j], corr[j][i]):
                raise ValueError("Correlation matrix must be symmetric")
            total += 2 * weights[i] * weights[j] * corr[i][j] * sds[i] * sds[j]
    return total


def portfolio_sd(variance):
    """sigma_p = square root of the portfolio variance."""
    if variance < -TOL:
        raise ValueError("Variance cannot be negative; check the inputs")
    return sqrt(max(variance, 0.0))


def is_diversified(portfolio_sd_value, weights, sds):
    """
    Diversification test: the portfolio is diversified when its risk is
    LOWER than the weighted average of its holdings' risks.
    Returns (diversified?, weighted average risk).
    """
    weighted_avg = sum(w * s for w, s in zip(weights, sds))
    return portfolio_sd_value < weighted_avg - TOL, weighted_avg


# 7. Relevant risk: the risk a holding actually adds to a portfolio


def relevant_risk(sd_i, corr_i_p):
    """Relevant risk of asset i = sd_i x Corr(asset i, portfolio)."""
    return sd_i * corr_i_p


def portfolio_sd_from_contributions(weights, sds, corrs_with_portfolio):
    """sigma_p = sum of wi x sd_i x Corr(asset i, portfolio)."""
    _check_same_length(weights, sds, corrs_with_portfolio)
    return sum(w * relevant_risk(s, c)
               for w, s, c in zip(weights, sds, corrs_with_portfolio))


# 8. Diversification in a big market


def equal_weight_risk(n_holdings, sd_each, avg_corr):
    """
    Risk of an equal-weight portfolio of n similar holdings, each with the
    same risk (sd_each) and the same correlation with every other (avg_corr):
        sd_p = sd_each x sqrt(avg_corr + (1 - avg_corr) / n)
    As n grows, risk falls toward its floor, sd_each x sqrt(avg_corr).
    """
    if n_holdings < 1:
        raise ValueError("Need at least 1 holding")
    if not -1 <= avg_corr <= 1:
        raise ValueError("Correlation must be between -1 and +1")
    return sd_each * sqrt(avg_corr + (1 - avg_corr) / n_holdings)


def market_weights(prices, shares_outstanding):
    """Value weights: each asset's market value / total market value."""
    _check_same_length(prices, shares_outstanding)
    return weights_from_values([p * s for p, s in zip(prices, shares_outstanding)])


def safe_and_market_mix(w_market, risk_free, market_return, market_sd):
    """
    Two-bucket strategy: put w_market in the market portfolio and the rest
    in a risk-free asset. Returns (expected return, risk).
        E = rf + w x (E(R_mkt) - rf)      risk = w x sd_mkt
    """
    return (risk_free + w_market * (market_return - risk_free),
            w_market * market_sd)


# 9. Systematic risk and beta


def systematic_risk(sd_i, corr_i_mkt):
    """Systematic (market) risk of asset i = sd_i x Corr(asset i, market)."""
    return sd_i * corr_i_mkt


def idiosyncratic_risk(sd_i, corr_i_mkt):
    """
    Company-specific risk. Risks combine like the sides of a right triangle:
        total^2 = systematic^2 + company-specific^2
    so company-specific = sd_i x sqrt(1 - corr^2). (Subtracting the two
    percentages directly is a common shortcut, but it isn't correct.)
    """
    if not -1 <= corr_i_mkt <= 1:
        raise ValueError("Correlation must be between -1 and +1")
    return sd_i * sqrt(1 - corr_i_mkt ** 2)


def beta(sd_i, corr_i_mkt, sd_mkt):
    """Beta = sd_i x Corr(asset i, market) / sd_market."""
    if sd_mkt <= 0:
        raise ValueError("Market risk must be positive")
    return systematic_risk(sd_i, corr_i_mkt) / sd_mkt


def market_sd_from_assets(weights, sds, corrs_with_market):
    """sd_market = sum of wi x sd_i x Corr(asset i, market)."""
    return portfolio_sd_from_contributions(weights, sds, corrs_with_market)


def portfolio_beta(weights, betas):
    """Portfolio beta = w1 x beta1 + w2 x beta2 + ... (a plain weighted average)."""
    _check_same_length(weights, betas)
    _check_sums_to_one(weights, "Weights")
    return sum(w * b for w, b in zip(weights, betas))


# 10. Required return and CAPM


def nominal_risk_free(real_rate, expected_inflation):
    """Nominal risk-free rate is approximately real rate + expected inflation."""
    return real_rate + expected_inflation


def risk_premium(beta_i, market_return, risk_free):
    """Risk premium = beta x (E(R_mkt) - rf)."""
    return beta_i * (market_return - risk_free)


def capm(risk_free, beta_i, market_return):
    """CAPM: E(R_i) = rf + beta x (E(R_mkt) - rf)."""
    return risk_free + risk_premium(beta_i, market_return, risk_free)


def beta_from_expected_return(expected_return_i, risk_free, market_return):
    """Working CAPM backward: beta = (E(R_i) - rf) / (E(R_mkt) - rf)."""
    mrp = market_return - risk_free
    if mrp == 0:
        raise ValueError("Market risk premium can't be zero")
    return (expected_return_i - risk_free) / mrp
