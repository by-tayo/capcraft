"""Worked DCF and sensitivity example for a made-up company, Cedar Co.
Every number is invented for illustration. It is not a real company or a forecast.

Run: python examples/dcf_sensitivity_examples.py
"""
from capcraft import dcf
from capcraft import monte_carlo as mc
from capcraft import sensitivity as sa


def m(x):
    return f"{x:,.1f}"


def pct(x, d=1):
    return f"{x * 100:.{d}f}%"


def main():
    print("CEDAR CO (made up). Dollar amounts in $ millions, except per share.\n")

    # 1. Discount rate
    re = dcf.cost_of_equity(risk_free=0.04, beta=1.2, market_return=0.09)
    rate = dcf.wacc(equity_value=1_500, debt_value=500, cost_of_equity_rate=re,
                    cost_of_debt=0.06, tax_rate=0.25)
    print("1. DISCOUNT RATE")
    print(f"   Cost of equity (CAPM): 4% + 1.2 x (9% - 4%) = {pct(re)}")
    print(f"   WACC: 75% x {pct(re)} + 25% x 6% x (1 - 25%) = {pct(rate, 2)}")

    model = dcf.DCFModel(
        base_revenue=800, revenue_growth=[0.12, 0.10, 0.08, 0.06, 0.04],
        ebit_margin=[0.16, 0.17, 0.18, 0.18, 0.18], tax_rate=0.25,
        da_pct=0.04, capex_pct=0.05, nwc_pct=0.12, discount_rate=rate,
        terminal_growth=0.025, net_debt=dcf.net_debt(500, 80), shares_outstanding=60)
    res = model.value()

    # 2. Projection
    print("\n2. FREE CASH FLOW PROJECTION")
    print(f"   {'Year':>4} {'Revenue':>9} {'EBIT':>7} {'NOPAT':>7} {'D&A':>6} {'CapEx':>6} "
          f"{'chg NWC':>8} {'FCF':>7} {'PV':>7}")
    for row, pv in zip(res.projection, res.pv_fcfs):
        print(f"   {row.year:>4} {m(row.revenue):>9} {m(row.ebit):>7} {m(row.nopat):>7} "
              f"{m(row.da):>6} {m(row.capex):>6} {m(row.delta_nwc):>8} {m(row.fcf):>7} {m(pv):>7}")

    # 3. Value
    print("\n3. FROM CASH FLOWS TO A SHARE PRICE")
    print(f"   PV of years 1-5                          {m(res.pv_explicit):>8}")
    print(f"   Terminal value at year 5 (2.5% growth)   {m(res.terminal_value):>8}"
          f"  -> PV {m(res.pv_terminal_value)}")
    print(f"   Enterprise value                         {m(res.enterprise_value):>8}")
    print(f"   Less net debt ($500 debt - $80 cash)     {m(-res.net_debt):>8}")
    print(f"   Equity value                             {m(res.equity_value):>8}")
    print(f"   Value per share (60M shares)             ${res.value_per_share:>7.2f}")
    print(f"   Cross-checks: terminal value is {pct(res.terminal_share)} of EV; "
          f"it implies {res.implied_exit_multiple:.1f}x year-5 EBITDA")

    f = sa.dcf_function("value_per_share")
    base = sa.dcf_base(model)

    # 4. Two-way table
    waccs = [rate - 0.01, rate - 0.005, rate, rate + 0.005, rate + 0.01]
    growths = [0.015, 0.02, 0.025, 0.03, 0.035]
    table = sa.two_way(f, base, "discount_rate", waccs, "terminal_growth", growths)
    print("\n4. VALUE PER SHARE: WACC ACROSS, TERMINAL GROWTH DOWN")
    print("   growth " + "".join(f"{pct(w, 2):>9}" for w in waccs))
    for g, row in zip(growths, table.grid):
        print(f"   {pct(g):>6} " + "".join(f"{v:>9.2f}" for v in row))

    # 5. Tornado
    ranges = {
        "discount_rate": (rate - 0.01, rate + 0.01),
        "terminal_growth": (0.015, 0.035),
        "ebit_margin": (0.15, 0.21),
        "capex_pct": (0.04, 0.06),
        "nwc_pct": (0.09, 0.15),
        "tax_rate": (0.21, 0.28),
    }
    print("\n5. TORNADO: EACH INPUT MOVED ALONE, BIGGEST SWING FIRST")
    print(f"   Base value per share ${res.value_per_share:.2f}")
    for bar in sa.tornado(f, base, ranges):
        lo, hi = bar.low_input, bar.high_input
        print(f"   {bar.param:<16} {lo:>6.3f} to {hi:<6.3f} -> ${bar.low_output:>6.2f} to "
              f"${bar.high_output:>6.2f}  (swing ${bar.swing:.2f})")
    print("   EBIT margin is one number for every year here, so this flattens the"
          " year-by-year margins above.")

    # 6. Elasticities
    print("\n6. ELASTICITY: % CHANGE IN VALUE PER SHARE FOR A 1% CHANGE IN THE INPUT")
    for p in ("base_revenue", "discount_rate", "terminal_growth", "tax_rate"):
        print(f"   {p:<16} {sa.elasticity(f, base, p):+.2f}")
    print("   Revenue is above 1 because debt is fixed: equity holders get every")
    print("   extra dollar of enterprise value.")

    # 7. Sensitivity on a simulation
    print("\n7. MONTE CARLO SENSITIVITY: CHANCE OF A LOSS ON $10,000 OVER 5 YEARS")

    def p_loss(volatility):
        return mc.simulate_gbm(10_000, 0.07, volatility, years=5, n_sims=20_000,
                               seed=2026).prob_loss()

    for vol, p in sa.one_way(p_loss, {"volatility": 0.18}, "volatility", [0.10, 0.15, 0.20, 0.25, 0.30]):
        print(f"   volatility {pct(vol, 0):>4} -> {pct(p)}")
    print("   Every row uses the same random draws (same seed), so the trend comes from")
    print("   volatility, not from luck.")


if __name__ == "__main__":
    main()
