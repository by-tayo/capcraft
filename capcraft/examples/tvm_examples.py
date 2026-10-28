"""Worked examples for capcraft.tvm (ported from the original time_value.py).

Run: python examples/tvm_examples.py
"""
from capcraft import tvm
from capcraft.tvm import *  # noqa: F401,F403  (examples call functions unqualified)
from math import isclose

# Worked examples (all numbers made up)


def worked_examples():
    ex = {}

    # 1. $1,000 at 5% for 3 years
    ex["ib"] = interest_breakdown(1000, 0.05, 3)
    ex["pv1"] = present_value(1000, 0.05, 3)
    assert isclose(present_value(ex["ib"]["future_value"], 0.05, 3), 1000), "FV and PV must undo each other"
    assert isclose(move(1000, 0.05, 3, 0), ex["pv1"]) and isclose(move(1000, 0.05, 0, 3), ex["ib"]["future_value"])

    # 2. Uneven cash flows: $100, $200, $300 in years 1-3 at 5%
    ex["flows"] = [(1, 100), (2, 200), (3, 300)]
    ex["each"] = [present_value(a, 0.05, t) for t, a in ex["flows"]]
    ex["pv_flows"] = pv_cash_flows(ex["flows"], 0.05)
    assert isclose(ex["pv_flows"], sum(ex["each"]))

    # 3. Shortcuts, each checked against adding up every payment
    ex["ann"] = pv_annuity(1000, 0.06, 5)
    assert isclose(ex["ann"], pv_cash_flows(pattern_cash_flows(1000, 5), 0.06)), "Annuity shortcut must match the long way"

    ex["gann"] = pv_growing_annuity(1000, 0.06, 0.03, 5)
    assert isclose(ex["gann"], pv_cash_flows(pattern_cash_flows(1000, 5, growth=0.03), 0.06)), "Growing annuity must match"

    ex["perp"] = pv_perpetuity(1000, 0.05)
    assert abs(ex["perp"] - pv_annuity(1000, 0.05, 2000)) < 1e-6, "Perpetuity = very long annuity"

    ex["gperp"] = pv_growing_perpetuity(1000, 0.06, 0.03)
    assert abs(ex["gperp"] - pv_growing_annuity(1000, 0.06, 0.03, 5000)) < 1e-4, "Growing perpetuity = very long growing annuity"

    # 3b. Deferred annuity: 4 payments of $1,000 starting in year 3, at 6%
    ex["def_at2"] = pv_annuity(1000, 0.06, 4)
    ex["def_today"] = value_today(ex["def_at2"], 3, 0.06)
    assert isclose(ex["def_today"], pv_cash_flows(pattern_cash_flows(1000, 4, first_period=3), 0.06)), "Deferred annuity must match"

    # 4. Combination: $1,000 a year for years 1-5, then $1,500 a year forever from year 6, at 6%
    part1 = pv_annuity(1000, 0.06, 5)
    part2_at5 = pv_perpetuity(1500, 0.06)
    part2 = value_today(part2_at5, 6, 0.06)
    ex["combo"] = dict(part1=part1, part2_at5=part2_at5, part2=part2, total=part1 + part2)
    long_way = pv_cash_flows(pattern_cash_flows(1000, 5) + pattern_cash_flows(1500, 3000, first_period=6), 0.06)
    assert abs(ex["combo"]["total"] - long_way) < 1e-6, "Combination must match the long way"

    # 5. Annuity due: $500 at the START of each year for 6 years, at 5%
    ex["due"] = pv_annuity_due(500, 0.05, 6)
    ex["due_ordinary"] = pv_annuity(500, 0.05, 6)
    assert isclose(ex["due"], pv_cash_flows(pattern_cash_flows(500, 6, first_period=0), 0.05)), "Annuity due must match"

    # 6. Future value of an annuity: save $200 a year for 10 years at 7%
    ex["fva"] = fv_annuity(200, 0.07, 10)
    assert isclose(ex["fva"], pv_cash_flows(pattern_cash_flows(200, 10), 0.07, at_period=10)), "FV of annuity must match"
    assert isclose(ex["fva"], future_value(pv_annuity(200, 0.07, 10), 0.07, 10)), "FV = PV grown N periods"
    ex["fva_due"] = fv_annuity_due(200, 0.07, 10)

    # 7. Delayed perpetuity: $300 a year forever, first payment at year 5, at 6%
    ex["dperp_at4"] = pv_perpetuity(300, 0.06)
    ex["dperp_today"] = value_today(ex["dperp_at4"], 5, 0.06)
    #    Perpetuity due: $300 a year forever, first payment today, at 6%
    ex["perp_due"] = pv_perpetuity_due(300, 0.06)
    assert abs(ex["perp_due"] - pv_cash_flows(pattern_cash_flows(300, 3000, first_period=0), 0.06)) < 1e-6

    # 8. Price a stock from its pieces, with a CAPM rate
    r = capm_rate(0.04, 1.1, 0.06)
    p1 = pv_annuity(2.00, r, 5)                                  # $2.00 dividends, years 1-5
    p2_at5 = pv_annuity(2.50, r, 5)                              # $2.50 dividends, years 6-10
    p2 = value_today(p2_at5, 6, r)
    p3 = present_value(40, r, 10)                                # sell for $40 at year 10
    ex["stock"] = dict(r=r, p1=p1, p2_at5=p2_at5, p2=p2, p3=p3, total=p1 + p2 + p3)
    flows = pattern_cash_flows(2.00, 5) + pattern_cash_flows(2.50, 5, first_period=6) + [(10, 40)]
    assert isclose(ex["stock"]["total"], pv_cash_flows(flows, r)), "Stock price must match the long way"
    return ex


def money(x):
    return f"${x:,.2f}"


def main():
    ex = worked_examples()
    ib = ex["ib"]
    print("1. ONE AMOUNT ($1,000 at 5% for 3 years)")
    print(f"   Future value {money(ib['future_value'])}: total interest {money(ib['total_interest'])} = "
          f"simple {money(ib['simple_interest'])} + interest on interest {money(ib['interest_on_interest'])}")
    print(f"   $1,000 received in 3 years is worth {money(ex['pv1'])} today")

    print("\n2. UNEVEN CASH FLOWS ($100, $200, $300 in years 1-3 at 5%)")
    print(timeline(ex["flows"]))
    print("   " + " + ".join(money(v) for v in ex["each"]) + f" = {money(ex['pv_flows'])}")

    print("\n3. SHORTCUTS (value one period before the first payment)")
    print(f"   Annuity: $1,000 a year for 5 years at 6%            -> {money(ex['ann'])}")
    print(f"   Growing annuity: $1,000 growing 3%, 5 years, at 6%   -> {money(ex['gann'])}")
    print(f"   Perpetuity: $1,000 a year forever at 5%              -> {money(ex['perp'])}")
    print(f"   Growing perpetuity: $1,000 growing 3% forever, at 6% -> {money(ex['gperp'])}")
    print(f"   Deferred: 4 x $1,000 starting year 3 at 6%: {money(ex['def_at2'])} at year 2 "
          f"-> {money(ex['def_today'])} today")

    c = ex["combo"]
    print("\n4. COMBINATION ($1,000/yr for years 1-5, then $1,500/yr forever from year 6, at 6%)")
    print(f"   Annuity part today {money(c['part1'])} + perpetuity part {money(c['part2_at5'])} at year 5 "
          f"-> {money(c['part2'])} today = {money(c['total'])}")

    print("\n5. ANNUITY DUE ($500 at the start of each year for 6 years, at 5%)")
    print(f"   Ordinary annuity {money(ex['due_ordinary'])} x 1.05 = {money(ex['due'])} (first payment today)")

    print("\n6. FUTURE VALUE OF AN ANNUITY (save $200 a year for 10 years at 7%)")
    print(f"   On the day of the last deposit: {money(ex['fva'])}   (deposits at the start of each year: {money(ex['fva_due'])})")

    print("\n7. LATE AND EARLY PERPETUITIES ($300 a year forever at 6%)")
    print(f"   First payment at year 5: {money(ex['dperp_at4'])} at year 4 -> {money(ex['dperp_today'])} today")
    print(f"   First payment today: $300 + {money(ex['dperp_at4'])} = {money(ex['perp_due'])}")

    st = ex["stock"]
    print(f"\n8. STOCK PRICE FROM ITS PIECES (CAPM rate: 4% + 1.1 x 6% = {st['r']*100:.1f}%)")
    print(f"   $2.00 dividends yrs 1-5: {money(st['p1'])} + $2.50 dividends yrs 6-10: {money(st['p2_at5'])} at yr 5 -> {money(st['p2'])}"
          f" + $40 sale at yr 10: {money(st['p3'])} = {money(st['total'])}")
    print("\nAll cross-checks passed.")


if __name__ == "__main__":
    main()
