"""Monte Carlo simulation: thousands of possible futures for an investment.

Three ways to generate those futures:

  simulate_gbm()        one asset, prices follow geometric Brownian motion
  simulate_portfolio()  several correlated assets, rebalanced or buy-and-hold
  bootstrap_returns()   replay a real return history in random order

Each returns a SimulationResult holding every simulated path, with
methods for percentiles, probability of loss, value at risk (VaR) and
conditional value at risk (CVaR).

Formulas and assumptions
------------------------
Inputs are ANNUAL and DECIMAL: an 8% expected return is 0.08, a 15%
volatility is 0.15.

expected_return is the annual effective EXPECTED return, the same kind
of rate as tvm.future_value uses. The simulation is built so that the
AVERAGE outcome matches the TVM answer:

    E[V_T] = V_0 x (1 + r)^T

Geometric Brownian motion. Over a step of length dt (in years):

    V_{t+dt} = V_t x exp((mu - sigma^2 / 2) dt + sigma sqrt(dt) Z)

    mu    = ln(1 + r)       continuous drift that gives the average above
    sigma = annual volatility
    Z     = standard normal draw (correlated across assets, see below)

The sigma^2 / 2 term is the volatility drag. It makes the MEDIAN outcome
lower than the average:

    median V_T = V_0 x exp((mu - sigma^2 / 2) T)

So with sigma above 0, more than half of the paths finish below the
TVM answer even though the average matches it. The longer the horizon
and the higher the volatility, the bigger that gap.

What GBM assumes, and where it's wrong about markets:
  * log returns are normally distributed (real returns have fatter tails)
  * volatility and correlation stay constant (they rise in crises)
  * each step is independent of the last (no momentum or mean reversion)
bootstrap_returns() drops the normal-distribution assumption by
resampling real history, at the cost of assuming the future looks like
that history.

Correlated assets. Independent normal draws are mixed through the
Cholesky factor L of the correlation matrix (C = L L^T). That gives each
step's shocks the requested correlation. The matrix must be symmetric,
have 1s on the diagonal, and be positive semi-definite. Not every table
of pairwise correlations between -1 and +1 is a valid matrix.

Rebalancing. With rebalance=True the portfolio returns to its target
weights at every step:

    portfolio growth per step = sum of w_i x (asset i's growth that step)

With rebalance=False (buy-and-hold) each holding grows on its own and
the weights drift toward whichever assets did best.

Contributions. An optional fixed amount is added at the END of every
step, like an ordinary annuity. In buy-and-hold mode it is split across
the assets by the target weights. Contributions must be 0 or more.
Withdrawals aren't modeled yet.

Risk measures (on the terminal value V_T, against the total amount
invested = initial value + every contribution):
    probability of loss      P(V_T < invested)
    VaR at confidence c      invested - (the (1 - c) percentile of V_T)
    CVaR at confidence c     invested - (the average V_T in that worst
                             (1 - c) tail), also called expected shortfall
VaR and CVaR come back as positive numbers when they are losses. A
negative VaR means even the bad-case outcome finished above the amount
invested. CVaR is always at least as large as VaR.

Randomness. Pass seed= for reproducible results. With the same seed and
inputs, every run gives the same paths.

For learning only. Not financial advice.
"""
from dataclasses import dataclass
from math import ceil, isclose, sqrt

import numpy as np

from . import risk_return as rr

DEFAULT_PERCENTILES = (5, 25, 50, 75, 95)


# Result container


@dataclass
class SimulationResult:
    """Every simulated path plus what's needed to read them.

    paths has shape (n_sims, n_steps + 1). Column 0 is the starting value,
    and column k is the value after k steps (after that step's
    contribution).
    """
    paths: np.ndarray
    invested: float
    steps_per_year: int
    contribution: float = 0.0

    @property
    def n_sims(self):
        return self.paths.shape[0]

    @property
    def n_steps(self):
        return self.paths.shape[1] - 1

    @property
    def years(self):
        return self.n_steps / self.steps_per_year

    @property
    def terminal(self):
        """Value of each path at the end of the horizon."""
        return self.paths[:, -1]

    @property
    def time_axis(self):
        """Time in years for each column of paths (0 = today)."""
        return np.arange(self.n_steps + 1) / self.steps_per_year

    def mean_terminal(self):
        return float(self.terminal.mean())

    def median_terminal(self):
        return float(np.median(self.terminal))

    def percentiles(self, qs=DEFAULT_PERCENTILES):
        """Terminal value at each requested percentile, e.g. {5: ..., 95: ...}."""
        values = np.percentile(self.terminal, qs)
        return {q: float(v) for q, v in zip(qs, values)}

    def percentile_bands(self, qs=(5, 50, 95)):
        """Percentiles at every step, for a fan chart. Returns
        {q: array of length n_steps + 1}."""
        values = np.percentile(self.paths, qs, axis=0)
        return {q: v for q, v in zip(qs, values)}

    def prob_loss(self):
        """Share of paths that finish below the total amount invested."""
        return float((self.terminal < self.invested).mean())

    def prob_reaching(self, target):
        """Share of paths that finish at or above a target value."""
        return float((self.terminal >= target).mean())

    def value_at_risk(self, confidence=0.95):
        """Loss versus amount invested at the (1 - confidence) percentile."""
        _check_confidence(confidence)
        cutoff = np.percentile(self.terminal, 100 * (1 - confidence))
        return float(self.invested - cutoff)

    def conditional_value_at_risk(self, confidence=0.95):
        """Average loss versus amount invested across the worst
        (1 - confidence) share of paths (expected shortfall)."""
        _check_confidence(confidence)
        cutoff = np.percentile(self.terminal, 100 * (1 - confidence))
        tail = self.terminal[self.terminal <= cutoff]
        return float(self.invested - tail.mean())

    def summary(self, confidence=0.95, qs=DEFAULT_PERCENTILES):
        """Headline numbers as a plain dict (handy for printing or a dashboard)."""
        return {
            "n_sims": self.n_sims,
            "years": self.years,
            "invested": self.invested,
            "mean_terminal": self.mean_terminal(),
            "median_terminal": self.median_terminal(),
            "percentiles": self.percentiles(qs),
            "prob_loss": self.prob_loss(),
            "confidence": confidence,
            "value_at_risk": self.value_at_risk(confidence),
            "conditional_value_at_risk": self.conditional_value_at_risk(confidence),
        }


# Input checks


def _check_confidence(c):
    if not 0 < c < 1:
        raise ValueError("Confidence must be between 0 and 1, e.g. 0.95")


def _n_steps(years, steps_per_year):
    if years <= 0:
        raise ValueError("Years must be positive")
    if steps_per_year < 1 or int(steps_per_year) != steps_per_year:
        raise ValueError("Steps per year must be a whole number, 1 or more")
    n = years * steps_per_year
    if not isclose(n, round(n), abs_tol=1e-9):
        raise ValueError(f"years x steps_per_year must be a whole number of steps, got {n}")
    return int(round(n))


def _check_common(initial_value, n_sims, contribution):
    if initial_value < 0:
        raise ValueError("Initial value can't be negative")
    if contribution < 0:
        raise ValueError("Contribution can't be negative (withdrawals aren't modeled yet)")
    if initial_value == 0 and contribution == 0:
        raise ValueError("Need a starting value or a contribution, or there's nothing to simulate")
    if n_sims < 1 or int(n_sims) != n_sims:
        raise ValueError("Number of simulations must be a whole number, 1 or more")


def _check_return_and_vol(expected_return, volatility, name=""):
    label = f" for {name}" if name else ""
    if expected_return <= -1:
        raise ValueError(f"Expected return{label} must be greater than -100%")
    if volatility < 0:
        raise ValueError(f"Volatility{label} can't be negative")


def correlation_factor(correlation):
    """Matrix L with L @ L.T equal to the correlation matrix.

    Uses Cholesky when the matrix is strictly positive definite. Falls
    back to an eigenvalue factor when it is only positive SEMI-definite
    (for example, two assets with correlation exactly +1), which
    Cholesky can't handle. Raises ValueError for anything that isn't a
    valid correlation matrix."""
    c = np.asarray(correlation, dtype=float)
    if c.ndim != 2 or c.shape[0] != c.shape[1]:
        raise ValueError("Correlation matrix must be square (n x n)")
    if not np.allclose(c, c.T):
        raise ValueError("Correlation matrix must be symmetric")
    if not np.allclose(np.diag(c), 1.0):
        raise ValueError("Correlation matrix must have 1s on the diagonal")
    if np.any(c < -1 - 1e-12) or np.any(c > 1 + 1e-12):
        raise ValueError("Correlations must be between -1 and +1")
    try:
        return np.linalg.cholesky(c)
    except np.linalg.LinAlgError:
        eigvals, eigvecs = np.linalg.eigh(c)
        if eigvals.min() < -1e-10:
            raise ValueError("Correlation matrix isn't positive semi-definite: these pairwise "
                             "correlations can't all be true at the same time") from None
        return eigvecs * np.sqrt(np.clip(eigvals, 0.0, None))


# Path building


def _build_paths(initial_value, growth, contribution):
    """Turn per-step growth factors (n_sims, n_steps) into value paths
    (n_sims, n_steps + 1), adding the contribution at the end of each step."""
    n_sims, n_steps = growth.shape
    if contribution == 0:
        paths = np.empty((n_sims, n_steps + 1))
        paths[:, 0] = initial_value
        np.cumprod(growth, axis=1, out=paths[:, 1:])
        paths[:, 1:] *= initial_value
        return paths
    paths = np.empty((n_sims, n_steps + 1))
    paths[:, 0] = initial_value
    for t in range(n_steps):
        paths[:, t + 1] = paths[:, t] * growth[:, t] + contribution
    return paths


def _gbm_growth(expected_returns, volatilities, dt, shocks):
    """Per-step growth factors exp((mu - sigma^2/2) dt + sigma sqrt(dt) Z).
    shocks holds standard normal draws, already correlated, with the
    asset dimension last."""
    mu = np.log1p(np.asarray(expected_returns, dtype=float))
    sigma = np.asarray(volatilities, dtype=float)
    return np.exp((mu - 0.5 * sigma ** 2) * dt + sigma * sqrt(dt) * shocks)


# 1. One asset


def simulate_gbm(initial_value, expected_return, volatility, years, steps_per_year=12,
                 n_sims=10_000, contribution=0.0, seed=None):
    """Simulate one asset (or one fund) with geometric Brownian motion.

    initial_value     starting dollars
    expected_return   annual effective expected return, decimal
    volatility        annual standard deviation of returns, decimal
    years             horizon (years x steps_per_year must be whole)
    steps_per_year    12 = monthly steps, 252 = trading days, 1 = annual
    n_sims            number of paths
    contribution      dollars added at the end of every step
    seed              set for reproducible results
    """
    _check_common(initial_value, n_sims, contribution)
    _check_return_and_vol(expected_return, volatility)
    n_steps = _n_steps(years, steps_per_year)
    rng = np.random.default_rng(seed)
    shocks = rng.standard_normal((int(n_sims), n_steps))
    growth = _gbm_growth(expected_return, volatility, 1 / steps_per_year, shocks)
    paths = _build_paths(initial_value, growth, contribution)
    return SimulationResult(paths, initial_value + contribution * n_steps, steps_per_year, contribution)


# 2. A portfolio of correlated assets


def simulate_portfolio(initial_value, weights, expected_returns, volatilities, correlation,
                       years, steps_per_year=12, n_sims=10_000, contribution=0.0,
                       rebalance=True, seed=None):
    """Simulate a portfolio of correlated assets, each following GBM.

    weights, expected_returns, volatilities   one entry per asset (decimals)
    correlation                               n x n correlation matrix
    rebalance                                 True: back to target weights every step
                                              False: buy-and-hold, weights drift

    Every other argument works like simulate_gbm().
    """
    _check_common(initial_value, n_sims, contribution)
    rr._check_same_length(weights, expected_returns, volatilities, correlation)
    rr._check_sums_to_one(weights, "Weights")
    if any(w < 0 for w in weights):
        raise ValueError("Weights can't be negative (short positions aren't modeled)")
    for i, (er, vol) in enumerate(zip(expected_returns, volatilities), 1):
        _check_return_and_vol(er, vol, f"asset {i}")
    factor = correlation_factor(correlation)
    n_steps = _n_steps(years, steps_per_year)
    n_assets = len(weights)

    rng = np.random.default_rng(seed)
    independent = rng.standard_normal((int(n_sims), n_steps, n_assets))
    shocks = independent @ factor.T
    growth = _gbm_growth(expected_returns, volatilities, 1 / steps_per_year, shocks)
    w = np.asarray(weights, dtype=float)

    if rebalance:
        paths = _build_paths(initial_value, growth @ w, contribution)
    else:
        holdings = np.tile(initial_value * w, (int(n_sims), 1))
        paths = np.empty((int(n_sims), n_steps + 1))
        paths[:, 0] = initial_value
        for t in range(n_steps):
            holdings = holdings * growth[:, t, :] + contribution * w
            paths[:, t + 1] = holdings.sum(axis=1)
    return SimulationResult(paths, initial_value + contribution * n_steps, steps_per_year, contribution)


# 3. Replaying history


def bootstrap_returns(initial_value, periodic_returns, n_periods, periods_per_year=12,
                      n_sims=10_000, contribution=0.0, block_size=1, seed=None):
    """Build paths by resampling a real history of periodic returns.

    periodic_returns   past returns, one per period, decimals (for example
                       Portfolio.period_returns() or a fund's monthly returns)
    n_periods          how many periods to simulate forward
    periods_per_year   how many of those periods make a year (labels only)
    block_size         1 = draw single periods at random (assumes no
                       pattern from one period to the next). Larger values
                       draw runs of consecutive periods, which keeps
                       streaks like a bad quarter together.

    No distribution is assumed, but nothing can happen that didn't happen
    in the history: the worst simulated period is the worst historical one.
    """
    _check_common(initial_value, n_sims, contribution)
    history = np.asarray(periodic_returns, dtype=float)
    if history.ndim != 1 or len(history) < 2:
        raise ValueError("Need at least 2 historical returns")
    if np.any(history <= -1):
        raise ValueError("A return of -100% or worse would wipe the investment out; check the data")
    if n_periods < 1 or int(n_periods) != n_periods:
        raise ValueError("Number of periods must be a whole number, 1 or more")
    if block_size < 1 or int(block_size) != block_size or block_size > len(history):
        raise ValueError(f"Block size must be a whole number from 1 to {len(history)}")
    n_periods, n_sims, block_size = int(n_periods), int(n_sims), int(block_size)

    rng = np.random.default_rng(seed)
    n_blocks = ceil(n_periods / block_size)
    starts = rng.integers(0, len(history) - block_size + 1, size=(n_sims, n_blocks))
    index = (starts[:, :, None] + np.arange(block_size)).reshape(n_sims, -1)[:, :n_periods]
    growth = 1 + history[index]
    paths = _build_paths(initial_value, growth, contribution)
    return SimulationResult(paths, initial_value + contribution * n_periods, periods_per_year, contribution)


# 4. Working backward: how much to save


def contribution_for_goal(initial_value, goal, confidence, expected_return, volatility, years,
                          steps_per_year=12, n_sims=10_000, seed=None):
    """The smallest contribution per step that reaches `goal` in at least
    `confidence` of the simulated futures (for example 0.80 for "80% of the time").

    This is solved exactly, with no trial and error. With the random shocks
    held fixed (same seed), each path's final value is a straight line in the
    contribution c:

        V_T = A + c x B

    A is where the path ends with no contributions (the starting value grown
    through that path's returns). B is what ONE unit contributed at the end of
    every step grows to on that path. Path i reaches the goal when
    c >= (goal - A_i) / B_i, so the answer is the `confidence` quantile of those
    per-path requirements (never below 0).

    Returns the amount per STEP (per month when steps_per_year is 12). The
    answer is only as good as the simulation: it depends on the expected
    return and volatility you assume, and the same GBM assumptions as
    simulate_gbm().
    """
    if goal <= 0:
        raise ValueError("Goal must be positive")
    _check_confidence(confidence)
    _check_common(initial_value, n_sims, contribution=0.0 if initial_value > 0 else 1.0)
    args = dict(expected_return=expected_return, volatility=volatility, years=years,
                steps_per_year=steps_per_year, n_sims=n_sims, seed=seed)
    if initial_value > 0:
        a = simulate_gbm(initial_value, contribution=0.0, **args).terminal
    else:
        a = np.zeros(int(n_sims))
    b = simulate_gbm(0.0, contribution=1.0, **args).terminal
    needed = np.maximum(0.0, (goal - a) / b)
    return float(np.quantile(needed, confidence, method="higher"))
