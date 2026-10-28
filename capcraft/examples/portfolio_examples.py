"""Worked portfolio-analysis example on SYNTHETIC data.

The prices below are generated from a seeded random number generator, so
they are not real assets and say nothing about real markets. The point is
to show the workflow: load prices, build a portfolio, read the metrics.

Run: python examples/portfolio_examples.py
"""
import io

from capcraft import data
from capcraft import risk_metrics as rm
from capcraft.sample_data import SAMPLE_WEIGHTS, synthetic_price_csv


def pct(x, d=1):
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def num(x, d=2):
    return "n/a" if x is None else f"{x:.{d}f}"


def main():
    print("SYNTHETIC DATA: 4 made-up assets and a made-up market, 60 months.\n")
    dates, prices = data.read_prices(io.StringIO(synthetic_price_csv()))
    market = data.prices_to_returns(prices.pop("MARKET"))
    portfolio = data.portfolio_from_prices(prices, weights=[SAMPLE_WEIGHTS[n] for n in prices])
    rf = rm.periodic_rate(0.03, 12)   # a 3% yearly risk-free rate, as a monthly rate

    print("1. THE PORTFOLIO")
    for h in portfolio.holdings:
        print(f"   {h.name:<7} weight {pct(h.weight, 0):>4}  monthly avg {pct(sum(h.returns) / len(h.returns), 2):>6}"
              f"  monthly risk {pct(rm.rr.historical_sd(h.returns), 2):>6}")
    s = portfolio.summary()
    print(f"   Portfolio: {pct(s['annualized_return'])} a year (CAGR), {pct(s['annualized_risk'])} yearly risk")
    print(f"   Diversified? {s['diversified']} (portfolio risk {pct(portfolio.risk(), 2)} a month "
          f"vs {pct(s['weighted_average_risk'], 2)} weighted average)")

    print("\n2. CORRELATIONS")
    corr = portfolio.correlation_matrix()
    print("   " + " " * 8 + "".join(f"{n:>8}" for n in portfolio.names))
    for name, row in zip(portfolio.names, corr):
        print(f"   {name:<8}" + "".join(f"{v:>8.2f}" for v in row))

    print("\n3. WHAT EACH HOLDING ADDS TO THE RISK")
    for r in portfolio.relevant_risk():
        print(f"   {r['name']:<7} weight {pct(r['weight'], 0):>4} but adds {pct(r['contribution'], 2):>6} "
              f"of the {pct(portfolio.risk(), 2)} monthly risk "
              f"({r['contribution'] / portfolio.risk():.0%} of it)")

    print("\n4. RISK METRICS (benchmark = the made-up market)")
    m = portfolio.risk_metrics(risk_free_rate=rf, benchmark_returns=market)
    print(f"   Sharpe {num(m['sharpe_ratio'])}   Sortino {num(m['sortino_ratio'])}   "
          f"Calmar {num(m['calmar_ratio'])}")
    print(f"   Worst drawdown {pct(m['max_drawdown'])} (from month {m['max_drawdown_peak_index']} "
          f"to month {m['max_drawdown_trough_index']}"
          + (f", recovered by month {m['max_drawdown_recovery_index']})" if m['max_drawdown_recovery_index']
             else ", not recovered)"))
    print(f"   One-month 95% VaR {pct(m['historical_var'])} (history), {pct(m['parametric_var'])} "
          f"(normal curve); CVaR {pct(m['historical_cvar'])}")
    print(f"   Beta {num(m['beta_vs_benchmark'])}   alpha {pct(m['jensens_alpha_per_period'] * 12)} a year (rough)")
    print("   Holding betas: " + ", ".join(f"{n} {b:.2f}" for n, b in
                                          zip(portfolio.names, portfolio.betas_vs(market))))
    print(f"   Beta check: weighted average of holding betas = {portfolio.beta(market):.2f}")

    print("\n5. EFFICIENT FRONTIER (20,000 random long-only mixes, 3% risk-free)")
    f = portfolio.efficient_frontier(20_000, risk_free_rate=0.03, seed=1)
    for label, mix in (("Lowest risk", f.min_variance()), ("Best Sharpe", f.max_sharpe())):
        w = ", ".join(f"{n} {pct(x, 0)}" for n, x in mix["weights"].items())
        print(f"   {label}: {pct(mix['annual_return'])} return, {pct(mix['annual_risk'])} risk, "
              f"Sharpe {mix['sharpe']:.2f}")
        print(f"      {w}")
    print("   These are the mixes that WOULD have worked best on these 60 months. Treat the")
    print("   best-Sharpe mix as a description of the past, not a recommendation.")


if __name__ == "__main__":
    main()
