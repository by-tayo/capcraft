"""Worked examples for capcraft.risk_return (ported from the original risk_return.py).

Run: python examples/risk_return_examples.py
"""
from capcraft.risk_return import *  # noqa: F401,F403
from math import sqrt, isclose

# Worked examples (the same numbers used in the guide)


def worked_examples():
    ex = {}

    # 1. One share: bought at $40, now $43, paid a $1.20 dividend; $2,000 invested
    r = asset_return(40, 43, 1.20)
    shares = 2000 / 40
    ex["single"] = dict(p0=40, p1=43, div=1.20, invested=2000, shares=shares,
                        mv0=market_value(shares, 40), mv1=market_value(shares, 43),
                        income=shares * 1.20, **r,
                        profit=profit_from_return(r["total"], 2000))
    assert isclose(ex["single"]["profit"],
                   total_profit(ex["single"]["mv0"], ex["single"]["mv1"], ex["single"]["income"]))

    # 1b. Spin-off: 1 share bought at $50; each share receives 0.5 NewCo share.
    #     End: parent $46, NewCo $10, $1 dividend on the parent share.
    end_value = 46 + 0.5 * 10
    ex["spinoff"] = dict(p0=50, parent_end=46, ratio=0.5, child_end=10, div=1.0,
                         end_value=end_value,
                         total=return_after_share_change(end_value, 50, 1.0))

    # 1c. 2-for-1 split: 1 share bought at $80 becomes 2 shares worth $42 each;
    #     $0.50 dividend on each new share.
    ex["split"] = dict(p0=80, new_shares=2, p_end=42, div_per_new=0.50,
                       end_value=2 * 42, divs=2 * 0.50,
                       total=return_after_share_change(2 * 42, 80, 2 * 0.50))

    # 2. Scenarios: strong year 25% (30%), normal 10% (50%), weak -15% (20%)
    probs, rets = [0.30, 0.50, 0.20], [0.25, 0.10, -0.15]
    ex["scen"] = dict(names=["Strong year", "Normal year", "Weak year"],
                      probs=probs, rets=rets,
                      er=expected_return(probs, rets),
                      var=scenario_variance(probs, rets),
                      sd=scenario_sd(probs, rets))

    # 3. History: Stock M over five years
    m = [0.12, -0.04, 0.18, 0.07, 0.02]
    ex["hist"] = dict(rets=m, avg=average_return(m), var=historical_variance(m),
                      sd=historical_sd(m))

    # 4. Portfolio return, both methods: $10,000 split 60/40
    mv0 = [market_value(60, 100), market_value(200, 20)]
    mv1 = [market_value(60, 106), market_value(200, 19)]
    inc = [60 * 1.00, 0.0]
    w = weights_from_values(mv0)
    r_x = asset_return(100, 106, 1.00)["total"]
    r_y = asset_return(20, 19, 0.0)["total"]
    m1 = portfolio_return_by_dollars(mv0, mv1, inc)
    m2 = portfolio_return(w, [r_x, r_y])
    assert isclose(m1, m2), "Method 1 and Method 2 must agree"
    ex["port"] = dict(mv0=mv0, mv1=mv1, inc=inc, w=w, r=[r_x, r_y],
                      profit=[total_profit(a, b, c) for a, b, c in zip(mv0, mv1, inc)],
                      m1=m1, m2=m2,
                      w_end=weights_from_values([b + 0 for b in mv1]))

    # 5. Expected portfolio return: 70% in the scenario stock, 30% in a 4% bond fund
    ex["eport"] = dict(w=[0.70, 0.30], er=[ex["scen"]["er"], 0.04],
                       erp=portfolio_expected_return([0.70, 0.30], [ex["scen"]["er"], 0.04]))

    # 6. Correlation and two-stock risk: Stock M (above) and Stock N
    n = [0.04, 0.08, 0.06, 0.03, 0.04]
    cov = historical_covariance(m, n)
    sd_m, sd_n = historical_sd(m), historical_sd(n)
    corr = correlation_from_cov(cov, sd_m, sd_n)
    var_p = portfolio_variance_two(0.5, 0.5, sd_m, sd_n, corr)
    sd_p = portfolio_sd(var_p)
    p_series = [0.5 * a + 0.5 * b for a, b in zip(m, n)]
    assert isclose(var_p, historical_variance(p_series)), "Formula must match the long way"
    div, wavg = is_diversified(sd_p, [0.5, 0.5], [sd_m, sd_n])
    avg_m, avg_n = average_return(m), average_return(n)
    ex["corr"] = dict(m=m, n=n, avg_m=avg_m, avg_n=avg_n,
                      gaps_m=[a - avg_m for a in m], gaps_n=[b - avg_n for b in n],
                      products=[(a - avg_m) * (b - avg_n) for a, b in zip(m, n)],
                      cov=cov, sd_m=sd_m, sd_n=sd_n, var_n=historical_variance(n),
                      corr=corr, var_p=var_p, sd_p=sd_p, p_series=p_series,
                      diversified=div, wavg=wavg)

    # 6b. Three assets: equal thirds, each 20% risk
    w3, s3 = [1 / 3] * 3, [0.20] * 3
    c3 = [[1, 0.5, -0.2], [0.5, 1, 0.1], [-0.2, 0.1, 1]]
    v3 = portfolio_variance(w3, s3, c3)
    ex["three"] = dict(corr=c3, var=v3, sd=portfolio_sd(v3))

    # 6c. How correlation changes risk: 50/50, both 20% risk
    ex["dial"] = [(rho, portfolio_sd(portfolio_variance_two(0.5, 0.5, 0.20, 0.20, rho)))
                  for rho in [-1, -0.5, 0, 0.5, 1]]

    # 7. Relevant risk in the 50/50 M + N portfolio
    corr_mp = historical_correlation(m, p_series)
    corr_np = historical_correlation(n, p_series)
    rr_m, rr_n = relevant_risk(sd_m, corr_mp), relevant_risk(sd_n, corr_np)
    total = portfolio_sd_from_contributions([0.5, 0.5], [sd_m, sd_n], [corr_mp, corr_np])
    assert isclose(total, sd_p), "Contributions must add up to portfolio risk"
    ex["relevant"] = dict(corr_mp=corr_mp, corr_np=corr_np, rr_m=rr_m, rr_n=rr_n,
                          contrib=[0.5 * rr_m, 0.5 * rr_n], total=total)
    return ex


def pct(x, d=2):
    return f"{x * 100:.{d}f}%"


def pct2(v, d=2):
    """Variance in percent-squared."""
    return f"{v * 10000:.{d}f} %^2"


def main():
    ex = worked_examples()

    s = ex["single"]
    print("1. ONE INVESTMENT")
    print(f"   Bought at ${s['p0']}, now ${s['p1']}, dividend ${s['div']:.2f}")
    print(f"   Capital gain yield {pct(s['capital_gain_yield'])} + dividend yield "
          f"{pct(s['income_yield'])} = total return {pct(s['total'])}")
    print(f"   On ${s['invested']:,}: profit ${s['profit']:,.2f}")
    print(f"   Spin-off return: {pct(ex['spinoff']['total'])}   "
          f"2-for-1 split return: {pct(ex['split']['total'])}")

    sc = ex["scen"]
    print("\n2. SCENARIOS")
    print(f"   Expected return {pct(sc['er'])}, variance {pct2(sc['var'])}, risk {pct(sc['sd'])}")

    h = ex["hist"]
    print("\n3. HISTORY (Stock M)")
    print(f"   Average {pct(h['avg'])}, variance {pct2(h['var'])}, risk {pct(h['sd'])}")

    p = ex["port"]
    print("\n4. PORTFOLIO RETURN")
    print(f"   Weights {[round(x, 2) for x in p['w']]}, returns {[pct(x) for x in p['r']]}")
    print(f"   Method 1 (dollars) {pct(p['m1'])} = Method 2 (weights) {pct(p['m2'])}")

    print("\n5. EXPECTED PORTFOLIO RETURN")
    print(f"   {pct(ex['eport']['erp'])}")

    c = ex["corr"]
    print("\n6. CORRELATION AND PORTFOLIO RISK (50/50 M + N)")
    print(f"   Cov {pct2(c['cov'])}, risk M {pct(c['sd_m'])}, risk N {pct(c['sd_n'])}, "
          f"correlation {c['corr']:.3f}")
    print(f"   Portfolio variance {pct2(c['var_p'])}, risk {pct(c['sd_p'])} vs weighted "
          f"average {pct(c['wavg'])} -> diversified: {c['diversified']}")
    print(f"   Three equal-weight stocks: risk {pct(ex['three']['sd'])}")
    print("   Correlation dial (50/50, both 20%): "
          + ", ".join(f"{rho:+.1f} -> {pct(sd, 1)}" for rho, sd in ex["dial"]))

    r = ex["relevant"]
    print("\n7. RELEVANT RISK")
    print(f"   M: {pct(r['rr_m'])} (corr with portfolio {r['corr_mp']:.3f})")
    print(f"   N: {pct(r['rr_n'])} (corr with portfolio {r['corr_np']:.3f})")
    print(f"   Weighted sum {pct(r['total'])} = portfolio risk {pct(c['sd_p'])}")

    x = worked_examples_part2()
    print("\n8. DIVERSIFICATION IN A BIG MARKET (each stock 35% risk, avg correlation 0.30)")
    print("   " + ", ".join(f"{n} stock{'s' if n > 1 else ''} -> {pct(s, 1)}" for n, s in x["curve"]))
    print(f"   Floor (market-wide risk): {pct(x['floor'], 1)}")
    print(f"   Market weights {[pct(w, 0) for w in x['mkt_w']]}")
    print("   Safe/market mixes: " + ", ".join(f"{pct(w, 0)} market -> {pct(e)} exp, {pct(s)} risk"
                                            for w, e, s in x["mixes"]))

    print("\n9. BETA")
    print(f"   Stock A: total {pct(x['sd_a'])}, systematic {pct(x['sys_a'])}, "
          f"company-specific {pct(x['idio_a'])}, beta {x['beta_a']:.2f}")
    print(f"   Portfolio beta (70% beta 1.2 + 30% beta 0.4): {x['beta_p']:.2f}")

    print("\n10. REQUIRED RETURN AND CAPM (rf 4%, market 9%)")
    print(f"   Risk-free {pct(x['rf'])} = real {pct(x['real'])} + inflation {pct(x['infl'])}")
    print(f"   Stock A: premium {pct(x['rp_a'])}, required {pct(x['capm_a'])}")
    print("   SML: " + ", ".join(f"beta {b:.1f} -> {pct(e, 1)}" for b, e in x["sml"]))
    print(f"   Expected 13% means beta {x['beta_back']:.1f}")
    print(f"   Portfolio required return {pct(x['erp_capm'])} = weighted average {pct(x['erp_avg'])}")
    print(f"   Stocks P and Q: betas {x['beta_pq'][0]:.2f} and {x['beta_pq'][1]:.2f}, "
          f"required {pct(x['req_pq'][0])} and {pct(x['req_pq'][1])}")
    print("\nAll cross-checks passed.")


def worked_examples_part2():
    x = {}
    rf, mkt, sd_m = 0.04, 0.09, 0.15
    x.update(rf=rf, mkt=mkt, sd_m=sd_m)

    # 8. Diversification curve: each stock 35% risk, average correlation 0.30
    x["curve"] = [(n, equal_weight_risk(n, 0.35, 0.30)) for n in (1, 2, 5, 10, 20, 30, 50)]
    x["floor"] = 0.35 * sqrt(0.30)
    x["curve_pts"] = [(n, equal_weight_risk(n, 0.35, 0.30)) for n in range(1, 51)]

    # Market weights in a made-up four-company world
    x["mkt_names"] = ["Cedar Co", "Delta Foods", "Elm Tech", "Fern Utilities"]
    x["mkt_prices"], x["mkt_shares"] = [25, 60, 15, 100], [40e6, 10e6, 20e6, 1e6]
    x["mkt_w"] = market_weights(x["mkt_prices"], x["mkt_shares"])
    assert isclose(sum(x["mkt_w"]), 1.0)

    # Two-bucket mixes
    x["mixes"] = [(w,) + safe_and_market_mix(w, rf, mkt, sd_m) for w in (0, 0.25, 0.5, 0.75, 1.0)]

    # 9. Beta: Stock A has 24% risk and 0.75 correlation with the market
    x["sd_a"], x["corr_a"] = 0.24, 0.75
    x["sys_a"] = systematic_risk(0.24, 0.75)
    x["idio_a"] = idiosyncratic_risk(0.24, 0.75)
    x["beta_a"] = beta(0.24, 0.75, sd_m)
    assert isclose(x["sys_a"] ** 2 + x["idio_a"] ** 2, 0.24 ** 2), "Risks must combine like a right triangle"
    x["beta_p"] = portfolio_beta([0.7, 0.3], [x["beta_a"], 0.4])

    # 10. Required return pieces and CAPM
    x["real"], x["infl"] = 0.01, 0.03
    assert isclose(nominal_risk_free(0.01, 0.03), rf)
    x["rp_a"] = risk_premium(x["beta_a"], mkt, rf)
    x["capm_a"] = capm(rf, x["beta_a"], mkt)
    x["sml"] = [(b, capm(rf, b, mkt)) for b in (0, 0.4, 1.0, 1.2, 1.8)]
    x["beta_back"] = beta_from_expected_return(0.13, rf, mkt)
    assert isclose(capm(rf, x["beta_back"], mkt), 0.13)
    w, betas = [0.7, 0.3], [x["beta_a"], 0.4]
    x["erp_capm"] = capm(rf, portfolio_beta(w, betas), mkt)
    x["erp_avg"] = portfolio_expected_return(w, [capm(rf, b, mkt) for b in betas])
    assert isclose(x["erp_capm"], x["erp_avg"]), "Both portfolio formulas must agree"

    # SML shifts for a beta-1.2 asset
    x["shift_rf"] = capm(0.05, 1.2, 0.10) - capm(rf, 1.2, mkt)
    x["shift_mrp"] = capm(rf, 1.2, 0.10) - capm(rf, 1.2, mkt)

    # 7. Same paid risk, different total risk: P (40%, corr 0.30) and Q (20%, corr 0.60)
    x["pq"] = [(0.40, 0.30), (0.20, 0.60)]
    x["sys_pq"] = [systematic_risk(s, c) for s, c in x["pq"]]
    x["idio_pq"] = [idiosyncratic_risk(s, c) for s, c in x["pq"]]
    x["beta_pq"] = [beta(s, c, sd_m) for s, c in x["pq"]]
    x["req_pq"] = [capm(rf, b, mkt) for b in x["beta_pq"]]
    assert isclose(x["sys_pq"][0], x["sys_pq"][1])
    return x




if __name__ == "__main__":
    main()
