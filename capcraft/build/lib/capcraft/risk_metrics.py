"""Risk and performance metrics for any periodic return series.

Every function takes a list of periodic returns (decimals, one per
period), so they work the same on one asset, a whole portfolio
(Portfolio.period_returns()) or a benchmark.

Conventions
-----------
* Returns are decimals: 1% -> 0.01. Periods are equal length (monthly,
  daily, ...). periods_per_year says how many make a year: 12 monthly,
  52 weekly, 252 trading days.
* risk_free_rate arguments are PERIODIC rates, in the same period
  length as the returns. Convert a yearly rate first with
  periodic_rate(annual_rate, periods_per_year).
* Losses from VaR and CVaR come back as POSITIVE numbers (a 4% loss is
  0.04). A negative value means even the bad case was a gain.
* "Undefined" cases (zero volatility, no down periods) raise ValueError
  here. risk_metrics_summary() catches them and reports None instead,
  so one undefined number doesn't hide the rest.

Formulas and assumptions
------------------------
Annualized return, two honest ways:
    geometric (CAGR)   = (final growth of $1) ^ (periods_per_year / n) - 1
                         What an investor actually earned per year,
                         compounding included. This is the default.
    arithmetic         = average periodic return x periods_per_year
                         The simple yearly version. It is the usual input
                         to mean-variance work (the frontier in
                         portfolio.py uses it) but it is NOT the return an
                         investor earned: it ignores compounding.
Don't compare those two annual figures to measure volatility drag, since
one compounds and one doesn't. Compare them PER PERIOD instead:
    geometric_mean_return(r) <= average_return(r)   always,
with a gap of roughly (periodic SD)^2 / 2, the same drag seen in
monte_carlo.py. Also don't "annualize" by compounding the AVERAGE return,
(1 + average)^periods_per_year - 1. That is at least the CAGR and
overstates what was earned.

Annualized volatility = periodic SD x sqrt(periods_per_year). It
assumes returns are independent from one period to the next. If returns
tend to trend or reverse, this under- or over-states yearly risk.

Sharpe ratio  = (average periodic return - periodic risk-free rate) / periodic SD
    annualized by x sqrt(periods_per_year), the usual shortcut, with the
    same independence assumption as above. SD is the sample SD (T - 1).

Sortino ratio = (average periodic return - risk-free rate) / downside deviation
    downside deviation = sqrt(mean of min(0, R_t - MAR)^2) over ALL
    periods (periods above the minimum acceptable return, MAR, count as
    zero). It does not penalize upside swings the way Sharpe does.

Maximum drawdown. Build the growth of $1 through the returns, then take
the worst fall from a previous high:
    drawdown_t = value_t / running high_t - 1
Indices returned are positions in the growth path: 0 is the starting
value and k is the value after the k-th return. It depends on the ORDER
of returns, not only their average and spread.

Calmar ratio = CAGR / |max drawdown|.

Value at risk and expected shortfall of ONE period's return:
    historical VaR(c)  = -(the (1 - c) percentile of past returns)
    historical CVaR(c) = -(average of returns at or below that percentile)
    parametric VaR(c)  = -(mean + z_(1-c) x SD), assuming a normal curve
Historical needs enough data to have a tail (with 60 monthly returns,
the 5% tail is only 3 observations). Parametric understates risk when
real returns have fat tails. These are one-period figures, not the
multi-year terminal-value VaR in monte_carlo.py.

Beta, alpha and Treynor against a benchmark:
    beta   = Cov(asset, benchmark) / Var(benchmark)
    alpha  = (avg asset return - rf) - beta x (avg benchmark return - rf),
             Jensen's alpha, per period. Multiply by periods_per_year for
             a rough yearly figure.
    Treynor = (avg asset return - rf) / beta, per period.
    Treynor means little when beta is near zero or negative.

All of this describes the PAST. A strong Sharpe ratio on five years of
history is not a forecast.

For learning only. Not financial advice.
"""
from math import sqrt
from statistics import NormalDist

import numpy as np

from . import risk_return as rr


# Conversions


def periodic_rate(annual_rate, periods_per_year=12):
    """Per-period rate that compounds to an annual rate:
    (1 + annual) ^ (1 / periods_per_year) - 1."""
    if annual_rate <= -1:
        raise ValueError("Annual rate must be greater than -100%")
    return (1 + annual_rate) ** (1 / periods_per_year) - 1


# Growth, return and volatility


def cumulative_growth(returns, start=1.0):
    """Growth of one unit compounded through the returns:
    [start, start x (1 + R1), start x (1 + R1)(1 + R2), ...]."""
    path = [start]
    for r in returns:
        path.append(path[-1] * (1 + r))
    return path


def cagr(returns, periods_per_year=12):
    """Compound annual growth rate of the whole return series."""
    if len(returns) < 1:
        raise ValueError("Need at least 1 return")
    growth = cumulative_growth(returns)[-1]
    if growth <= 0:
        raise ValueError("The investment lost everything, so CAGR is undefined")
    return growth ** (periods_per_year / len(returns)) - 1


def geometric_mean_return(returns):
    """The single per-period return that compounds to the same final value.
    Never above the arithmetic average; the gap is about SD^2 / 2."""
    if len(returns) < 1:
        raise ValueError("Need at least 1 return")
    growth = cumulative_growth(returns)[-1]
    if growth <= 0:
        raise ValueError("The investment lost everything, so the geometric mean is undefined")
    return growth ** (1 / len(returns)) - 1


def annualized_return(returns, periods_per_year=12, method="geometric"):
    """Yearly return. method="geometric" (default) is the CAGR;
    "arithmetic" is the average periodic return x periods_per_year."""
    if method == "geometric":
        return cagr(returns, periods_per_year)
    if method == "arithmetic":
        return rr.average_return(returns) * periods_per_year
    raise ValueError('method must be "geometric" or "arithmetic"')


def annualized_volatility(returns, periods_per_year=12):
    """Periodic SD x sqrt(periods_per_year)."""
    return rr.historical_sd(returns) * sqrt(periods_per_year)


# Risk-adjusted ratios


def sharpe_ratio(returns, risk_free_rate=0.0, periods_per_year=12, annualize=True):
    """Average excess return per unit of total risk."""
    avg_excess = rr.average_return(returns) - risk_free_rate
    sd = rr.historical_sd(returns)
    if sd == 0:
        raise ValueError("Standard deviation is 0, so the Sharpe ratio is undefined")
    ratio = avg_excess / sd
    return ratio * sqrt(periods_per_year) if annualize else ratio


def downside_deviation(returns, minimum_acceptable_return=0.0):
    """sqrt(mean of squared shortfalls below the minimum acceptable return)."""
    rr._check_min_periods(returns, 2)
    shortfalls = [min(0.0, r - minimum_acceptable_return) for r in returns]
    return sqrt(sum(s ** 2 for s in shortfalls) / len(returns))


def sortino_ratio(returns, risk_free_rate=0.0, minimum_acceptable_return=0.0,
                  periods_per_year=12, annualize=True):
    """Average excess return per unit of DOWNSIDE risk."""
    avg_excess = rr.average_return(returns) - risk_free_rate
    dd = downside_deviation(returns, minimum_acceptable_return)
    if dd == 0:
        raise ValueError("Downside deviation is 0, so the Sortino ratio is undefined")
    ratio = avg_excess / dd
    return ratio * sqrt(periods_per_year) if annualize else ratio


# Drawdown


def drawdown_series(returns):
    """Drawdown at every point of the growth path (0.0 at a new high,
    -0.2 when 20% below the previous high). Length is len(returns) + 1."""
    path = np.array(cumulative_growth(returns))
    running_high = np.maximum.accumulate(path)
    return (path / running_high - 1).tolist()


def max_drawdown(returns):
    """Worst fall from a previous high.

    Returns a dict:
      max_drawdown     negative number, or 0.0 if the series never fell
      peak_index       growth-path index of the high before the fall
      trough_index     growth-path index of the low
      recovery_index   first index back at or above the old high, or None
      growth_path      the full growth-of-$1 path
    """
    path = cumulative_growth(returns)
    dd = drawdown_series(returns)
    trough = int(np.argmin(dd))
    worst = dd[trough]
    if worst == 0:
        return {"max_drawdown": 0.0, "peak_index": 0, "trough_index": 0,
                "recovery_index": None, "growth_path": path}
    peak = int(np.argmax(path[:trough + 1]))
    recovery = next((i for i in range(trough + 1, len(path)) if path[i] >= path[peak]), None)
    return {"max_drawdown": worst, "peak_index": peak, "trough_index": trough,
            "recovery_index": recovery, "growth_path": path}


def calmar_ratio(returns, periods_per_year=12):
    """CAGR divided by the size of the worst drawdown."""
    worst = max_drawdown(returns)["max_drawdown"]
    if worst == 0:
        raise ValueError("There was no drawdown, so the Calmar ratio is undefined")
    return cagr(returns, periods_per_year) / abs(worst)


# One-period value at risk


def _check_confidence(c):
    if not 0 < c < 1:
        raise ValueError("Confidence must be between 0 and 1, e.g. 0.95")


def historical_var(returns, confidence=0.95):
    """Loss (positive number) that past returns exceeded only (1 - confidence)
    of the time."""
    _check_confidence(confidence)
    rr._check_min_periods(returns, 2)
    return float(-np.percentile(returns, 100 * (1 - confidence)))


def historical_cvar(returns, confidence=0.95):
    """Average loss (positive) across the worst (1 - confidence) share of periods."""
    _check_confidence(confidence)
    rr._check_min_periods(returns, 2)
    r = np.asarray(returns, dtype=float)
    cutoff = np.percentile(r, 100 * (1 - confidence))
    return float(-r[r <= cutoff].mean())


def parametric_var(returns, confidence=0.95):
    """VaR assuming returns follow a normal curve with the sample mean and SD."""
    _check_confidence(confidence)
    z = NormalDist().inv_cdf(1 - confidence)
    return -(rr.average_return(returns) + z * rr.historical_sd(returns))


# Against a benchmark


def beta_vs_benchmark(asset_returns, benchmark_returns):
    """Cov(asset, benchmark) / Var(benchmark)."""
    cov = rr.historical_covariance(asset_returns, benchmark_returns)
    var_bench = rr.historical_variance(benchmark_returns)
    if var_bench == 0:
        raise ValueError("The benchmark has 0 variance, so beta is undefined")
    return cov / var_bench


def jensens_alpha(asset_returns, benchmark_returns, risk_free_rate=0.0):
    """Per-period return beyond what the asset's beta explains."""
    b = beta_vs_benchmark(asset_returns, benchmark_returns)
    return ((rr.average_return(asset_returns) - risk_free_rate)
            - b * (rr.average_return(benchmark_returns) - risk_free_rate))


def treynor_ratio(asset_returns, benchmark_returns, risk_free_rate=0.0):
    """Per-period excess return per unit of beta."""
    b = beta_vs_benchmark(asset_returns, benchmark_returns)
    if b == 0:
        raise ValueError("Beta is 0, so the Treynor ratio is undefined")
    return (rr.average_return(asset_returns) - risk_free_rate) / b


# Everything at once


def risk_metrics_summary(returns, risk_free_rate=0.0, periods_per_year=12,
                         benchmark_returns=None, confidence=0.95):
    """Every metric above in one dict. A metric that can't be computed
    (zero volatility, no down periods...) is None instead of an error.

    risk_free_rate is per period. benchmark_returns adds beta, alpha and Treynor."""
    dd = max_drawdown(returns)

    def attempt(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError:
            return None

    out = {
        "n_periods": len(returns),
        "average_periodic_return": rr.average_return(returns),
        "periodic_risk": rr.historical_sd(returns),
        "annualized_return": attempt(annualized_return, returns, periods_per_year),
        "annualized_return_arithmetic": annualized_return(returns, periods_per_year, "arithmetic"),
        "annualized_volatility": annualized_volatility(returns, periods_per_year),
        "sharpe_ratio": attempt(sharpe_ratio, returns, risk_free_rate, periods_per_year),
        "sortino_ratio": attempt(sortino_ratio, returns, risk_free_rate,
                                 periods_per_year=periods_per_year),
        "max_drawdown": dd["max_drawdown"],
        "max_drawdown_peak_index": dd["peak_index"],
        "max_drawdown_trough_index": dd["trough_index"],
        "max_drawdown_recovery_index": dd["recovery_index"],
        "calmar_ratio": attempt(calmar_ratio, returns, periods_per_year),
        "confidence": confidence,
        "historical_var": attempt(historical_var, returns, confidence),
        "historical_cvar": attempt(historical_cvar, returns, confidence),
        "parametric_var": attempt(parametric_var, returns, confidence),
    }
    if benchmark_returns is not None:
        out["beta_vs_benchmark"] = beta_vs_benchmark(returns, benchmark_returns)
        out["jensens_alpha_per_period"] = jensens_alpha(returns, benchmark_returns, risk_free_rate)
        out["treynor_ratio_per_period"] = attempt(treynor_ratio, returns, benchmark_returns,
                                                  risk_free_rate)
    return out
