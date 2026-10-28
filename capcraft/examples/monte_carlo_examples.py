"""Worked examples for capcraft.monte_carlo. All numbers are made up for
illustration; they are not forecasts.

Run: python examples/monte_carlo_examples.py
"""
from capcraft import monte_carlo as mc
from capcraft import tvm


def money(x):
    return f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}"


def risk_line(name, amount):
    """VaR and CVaR are losses versus the amount invested. A negative one
    means even the bad case finished above the amount invested."""
    if amount <= 0:
        return f"{name}: no loss (bad case still {money(-amount)} above invested)"
    return f"{name}: lose {money(amount)} vs invested"


def show(label, res, target=None):
    s = res.summary(confidence=0.95)
    p = s["percentiles"]
    print(f"   {label}")
    print(f"     Invested {money(s['invested'])}. Average outcome {money(s['mean_terminal'])}, "
          f"median {money(s['median_terminal'])}")
    print(f"     Bad case (5th percentile) {money(p[5])}, good case (95th) {money(p[95])}")
    print(f"     Chance of ending below what you put in: {s['prob_loss']:.1%}")
    print(f"     {risk_line('95% VaR', s['value_at_risk'])}")
    print(f"     {risk_line('95% CVaR', s['conditional_value_at_risk'])}")
    if target:
        print(f"     Chance of reaching {money(target)}: {res.prob_reaching(target):.1%}")


def main():
    seed = 2026

    print("1. ONE FUND, NO RANDOMNESS: Monte Carlo reduces to time value of money")
    flat = mc.simulate_gbm(10_000, 0.08, 0.0, years=10, n_sims=5, seed=seed)
    print(f"   $10,000 at 8% for 10 years, volatility 0: every path ends at {money(flat.terminal[0])}")
    print(f"   tvm.future_value(10_000, 0.08, 10) = {money(tvm.future_value(10_000, 0.08, 10))}")

    print("\n2. ONE FUND WITH RISK ($10,000 + $500 a month for 20 years, 8% expected, 16% volatility)")
    monthly = 1.08 ** (1 / 12) - 1
    plan = tvm.future_value(10_000, monthly, 240) + tvm.fv_annuity(500, monthly, 240)
    print(f"   Time value of money answer (a straight 8% every year): {money(plan)}")
    fund = mc.simulate_gbm(10_000, 0.08, 0.16, years=20, contribution=500, seed=seed)
    show("10,000 simulated paths:", fund, target=300_000)
    print("   The average matches the TVM answer, but the median lands below it. That gap is")
    print("   volatility drag: most paths finish below the straight-line plan.")

    print("\n3. A 60/40 PORTFOLIO (stocks 9% / 17% vol, bonds 4% / 6% vol, correlation 0.1)")
    weights, rets, vols = [0.6, 0.4], [0.09, 0.04], [0.17, 0.06]
    corr = [[1.0, 0.1], [0.1, 1.0]]
    rebal = mc.simulate_portfolio(10_000, weights, rets, vols, corr, years=20,
                                  contribution=500, rebalance=True, seed=seed)
    hold = mc.simulate_portfolio(10_000, weights, rets, vols, corr, years=20,
                                 contribution=500, rebalance=False, seed=seed)
    show("Rebalanced to 60/40 every month:", rebal, target=300_000)
    show("Buy-and-hold (weights drift toward stocks):", hold, target=300_000)

    print("\n4. REPLAYING HISTORY (bootstrap of Stock M's five annual returns)")
    history = [0.12, -0.04, 0.18, 0.07, 0.02]
    boot = mc.bootstrap_returns(10_000, history, n_periods=10, periods_per_year=1, seed=seed)
    show("$10,000 for 10 years, each year drawn at random from those five:", boot)
    print("   With only five years of history, the worst simulated year is -4%, so this")
    print("   understates risk. A bootstrap is only as good as the history behind it.")


if __name__ == "__main__":
    main()
