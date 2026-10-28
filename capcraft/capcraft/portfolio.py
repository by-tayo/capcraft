"""Portfolio: holdings with weights and return histories, analyzed together.

This module adds no new formulas for return, variance or beta. It calls
risk_return.py and risk_metrics.py, so each formula lives in exactly one
place. What it adds is bookkeeping (hold names, weights and histories
once) and portfolio-level tools: matrices, risk contributions, and an
efficient-frontier sampler.

Conventions
-----------
* Returns are periodic decimals (0.01 = 1%), one per period, with the
  same period length and the same dates for every holding.
* Weights must sum to 1. Negative weights (short positions) are allowed
  here; efficient_frontier() itself only explores long-only mixes.
* periods_per_year (default 12, monthly) only matters for annualizing.

Assumption to keep in mind: constant weights
--------------------------------------------
period_returns() applies the SAME weights in every period, as if the
portfolio were rebalanced back to target at each period's start. That is
the standard way to analyze a weighted portfolio from return histories.
A buy-and-hold portfolio would drift away from these weights, so its
real history would differ. Rebalancing frequency is not modeled.

Efficient frontier by sampling
------------------------------
efficient_frontier() draws thousands of random long-only weight mixes
and records each one's return, risk and Sharpe ratio. Return is the
average periodic return x periods_per_year, and risk comes from the
sample covariance matrix x periods_per_year. The best mixes found
trace the frontier's upper-left edge. Because the weights are sampled,
not solved for, the "minimum variance" and "maximum Sharpe" mixes are
close approximations. More samples get closer. The inputs are
past returns, and optimizers are good at finding the mix that WOULD
have worked best on that history, which is not the same as the mix that
will work best next. Expect the max-Sharpe mix to be concentrated and
fragile.

For learning only. Not financial advice.
"""
from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

from . import risk_metrics as rm
from . import risk_return as rr


@dataclass
class Holding:
    """One position: a name, its weight, and its history of periodic returns."""
    name: str
    weight: float
    returns: Sequence[float]
    beta: Optional[float] = None  # supplied beta versus the market, if known


@dataclass
class Frontier:
    """Result of efficient_frontier(). Row i of `weights` is mix i.
    The first len(names) mixes are the single-asset corners."""
    names: List[str]
    weights: np.ndarray
    returns: np.ndarray
    risks: np.ndarray
    sharpes: np.ndarray
    risk_free_rate: float

    def _mix(self, i):
        return {"weights": dict(zip(self.names, self.weights[i].tolist())),
                "annual_return": float(self.returns[i]), "annual_risk": float(self.risks[i]),
                "sharpe": float(self.sharpes[i])}

    def min_variance(self):
        """The sampled mix with the lowest risk."""
        return self._mix(int(np.argmin(self.risks)))

    def max_sharpe(self):
        """The sampled mix with the highest Sharpe ratio."""
        return self._mix(int(np.argmax(self.sharpes)))

    def efficient_edge(self, n_bins=40):
        """Highest-return mix at each risk level: (risks, returns) arrays for
        drawing the frontier line over the cloud of sampled mixes."""
        edges = np.linspace(self.risks.min(), self.risks.max(), n_bins + 1)
        which = np.clip(np.digitize(self.risks, edges) - 1, 0, n_bins - 1)
        best_risk, best_ret, high = [], [], -np.inf
        for b in range(n_bins):
            in_bin = np.where(which == b)[0]
            if len(in_bin):
                j = in_bin[np.argmax(self.returns[in_bin])]
                if self.returns[j] > high:  # keep only points that improve return
                    high = self.returns[j]
                    best_risk.append(self.risks[j])
                    best_ret.append(self.returns[j])
        return np.array(best_risk), np.array(best_ret)


class Portfolio:
    """A collection of Holdings with one consistent history length.

        p = Portfolio([
            Holding("Stock A", 0.6, [0.03, -0.01, 0.05, 0.02]),
            Holding("Stock B", 0.4, [0.01,  0.02, 0.00, 0.04]),
        ])

    or from starting dollar amounts:

        p = Portfolio.from_market_values(["A", "B"], [6000, 4000], [returns_a, returns_b])
    """

    def __init__(self, holdings: Sequence[Holding], periods_per_year: int = 12):
        if not holdings:
            raise ValueError("A portfolio needs at least one holding")
        lengths = {len(h.returns) for h in holdings}
        if len(lengths) != 1:
            raise ValueError(f"Every holding must have the same number of return "
                             f"periods, got lengths {sorted(lengths)}")
        names = [h.name for h in holdings]
        if len(set(names)) != len(names):
            raise ValueError("Holding names must be unique")
        if periods_per_year < 1:
            raise ValueError("periods_per_year must be 1 or more")
        rr._check_sums_to_one([h.weight for h in holdings], "Holding weights")
        self.holdings = list(holdings)
        self.periods_per_year = periods_per_year

    @classmethod
    def from_market_values(cls, names, market_values, returns, betas=None, periods_per_year=12):
        """Build a Portfolio from starting dollar values instead of weights."""
        weights = rr.weights_from_values(market_values)
        betas = betas or [None] * len(names)
        holdings = [Holding(n, w, r, b) for n, w, r, b in zip(names, weights, returns, betas)]
        return cls(holdings, periods_per_year=periods_per_year)

    def with_weights(self, weights):
        """A copy of this portfolio with different weights (same histories)."""
        rr._check_same_length(weights, self.holdings)
        return Portfolio([Holding(h.name, w, h.returns, h.beta)
                          for h, w in zip(self.holdings, weights)], self.periods_per_year)

    # Lookups

    @property
    def names(self):
        return [h.name for h in self.holdings]

    @property
    def weights(self):
        return [h.weight for h in self.holdings]

    @property
    def n_periods(self):
        return len(self.holdings[0].returns)

    def returns_matrix(self):
        """One list per holding, in holding order."""
        return [list(h.returns) for h in self.holdings]

    def period_returns(self):
        """The portfolio's return in each period, w1 x R1[t] + w2 x R2[t] + ...
        with the same weights every period (see the module docstring)."""
        matrix = np.array(self.returns_matrix())
        return (np.array(self.weights) @ matrix).tolist()

    # Return and risk

    def average_return(self):
        """Average periodic portfolio return."""
        return rr.average_return(self.period_returns())

    def expected_return(self, expected_returns=None):
        """Weighted expected return. Pass each holding's own expected return
        (for example from CAPM), or it defaults to each holding's historical average."""
        if expected_returns is None:
            expected_returns = [rr.average_return(h.returns) for h in self.holdings]
        return rr.portfolio_expected_return(self.weights, expected_returns)

    def covariance_matrix(self):
        """Sample covariance matrix of the holdings' periodic returns (T - 1)."""
        return np.cov(np.array(self.returns_matrix()), ddof=1).reshape(len(self.holdings),
                                                                      len(self.holdings))

    def correlation_matrix(self):
        """Correlation matrix of the holdings' periodic returns."""
        cov = self.covariance_matrix()
        sd = np.sqrt(np.diag(cov))
        if np.any(sd == 0):
            zero = [n for n, s in zip(self.names, sd) if s == 0]
            raise ValueError(f"No variation in returns for: {', '.join(zero)}")
        return cov / np.outer(sd, sd)

    def variance(self):
        """(portfolio variance, correlation matrix as lists), computed with
        risk_return.portfolio_variance from each holding's SD and the
        correlation matrix."""
        sds = [rr.historical_sd(h.returns) for h in self.holdings]
        corr = self.correlation_matrix().tolist()
        return rr.portfolio_variance(self.weights, sds, corr), corr

    def risk(self):
        """Portfolio standard deviation per period."""
        var, _ = self.variance()
        return rr.portfolio_sd(var)

    def annualized_return(self, method="geometric"):
        """Yearly portfolio return: geometric (CAGR, default) or arithmetic.
        See risk_metrics.annualized_return."""
        return rm.annualized_return(self.period_returns(), self.periods_per_year, method)

    def annualized_risk(self):
        """Periodic risk x sqrt(periods_per_year), assuming returns are
        independent from one period to the next."""
        return self.risk() * self.periods_per_year ** 0.5

    def is_diversified(self):
        """(True if portfolio risk is below the weighted-average risk of its
        holdings, that weighted average)."""
        sds = [rr.historical_sd(h.returns) for h in self.holdings]
        return rr.is_diversified(self.risk(), self.weights, sds)

    def relevant_risk(self):
        """What each holding adds to portfolio risk. 'contribution' values
        add up to the portfolio's risk. One dict per holding."""
        port = self.period_returns()
        out = []
        for h in self.holdings:
            sd_i = rr.historical_sd(h.returns)
            corr_i_p = rr.historical_correlation(h.returns, port)
            relevant = rr.relevant_risk(sd_i, corr_i_p)
            out.append({"name": h.name, "weight": h.weight, "own_risk": sd_i,
                        "corr_with_portfolio": corr_i_p, "relevant_risk": relevant,
                        "contribution": h.weight * relevant})
        return out

    # Beta

    def betas_vs(self, benchmark_returns):
        """Each holding's beta, estimated against a benchmark return series."""
        if len(benchmark_returns) != self.n_periods:
            raise ValueError(f"Benchmark has {len(benchmark_returns)} periods but the "
                             f"portfolio has {self.n_periods}")
        return [rm.beta_vs_benchmark(h.returns, benchmark_returns) for h in self.holdings]

    def beta(self, benchmark_returns=None):
        """Portfolio beta: the weighted average of holding betas. Betas come
        from the benchmark if one is given, otherwise from each Holding's
        supplied beta."""
        if benchmark_returns is not None:
            betas = self.betas_vs(benchmark_returns)
        else:
            betas = [h.beta for h in self.holdings]
            missing = [h.name for h in self.holdings if h.beta is None]
            if missing:
                raise ValueError(f"Missing beta for: {', '.join(missing)}. Give each Holding a "
                                 f"beta, or pass benchmark_returns to estimate them.")
        return rr.portfolio_beta(self.weights, betas)

    # Metrics and frontier

    def risk_metrics(self, risk_free_rate=0.0, benchmark_returns=None, confidence=0.95):
        """Sharpe, Sortino, drawdown, VaR... for the portfolio's own returns.
        risk_free_rate is per period (see risk_metrics.periodic_rate)."""
        return rm.risk_metrics_summary(self.period_returns(), risk_free_rate,
                                       self.periods_per_year, benchmark_returns, confidence)

    def efficient_frontier(self, n_portfolios=5_000, risk_free_rate=0.0, seed=None):
        """Sample random long-only mixes of these holdings.

        risk_free_rate is ANNUAL here, because frontier numbers are annual."""
        n = len(self.holdings)
        if n < 2:
            raise ValueError("A frontier needs at least 2 holdings")
        if n_portfolios < 1:
            raise ValueError("n_portfolios must be 1 or more")
        rng = np.random.default_rng(seed)
        weights = np.vstack([np.eye(n), rng.dirichlet(np.ones(n), size=int(n_portfolios))])
        ppy = self.periods_per_year
        mu = np.array([rr.average_return(h.returns) for h in self.holdings]) * ppy
        cov = self.covariance_matrix() * ppy
        rets = weights @ mu
        risks = np.sqrt(np.einsum("ij,jk,ik->i", weights, cov, weights))
        with np.errstate(divide="ignore", invalid="ignore"):
            sharpes = np.where(risks > 0, (rets - risk_free_rate) / risks, np.nan)
        if np.all(np.isnan(sharpes)):
            raise ValueError("Every sampled mix has zero risk, so there is no frontier")
        sharpes = np.nan_to_num(sharpes, nan=-np.inf)
        return Frontier(self.names, weights, rets, risks, sharpes, risk_free_rate)

    def summary(self, risk_free_rate=0.0):
        """Headline numbers as a plain dict (for printing or a dashboard)."""
        diversified, weighted_avg_risk = self.is_diversified()
        return {
            "n_holdings": len(self.holdings),
            "names": self.names,
            "weights": self.weights,
            "average_periodic_return": self.average_return(),
            "periodic_risk": self.risk(),
            "annualized_return": self.annualized_return(),
            "annualized_return_arithmetic": self.annualized_return("arithmetic"),
            "annualized_risk": self.annualized_risk(),
            "weighted_average_risk": weighted_avg_risk,
            "diversified": diversified,
        }
