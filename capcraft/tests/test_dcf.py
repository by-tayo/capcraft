"""Tests for capcraft.dcf.

1. A small model worked out by hand, line by line.
2. Identities that must hold exactly whatever the inputs:
   * flat FCF with 0% growth is a perpetuity, C / r, whatever the forecast length
   * FCF growing at g from year 1 with Gordon at the same g is C_1 / (r - g)
   * the Gordon terminal value equals adding up thousands of growing years
   * going Gordon -> implied multiple -> exit multiple gives the same value back
   * the mid-year convention multiplies every explicit PV by (1 + r)^0.5
3. Input validation.
"""
import math

import pytest

from capcraft import dcf
from capcraft import risk_return as rr
from capcraft import tvm


def approx(a, b, tol=1e-9):
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


# Hand-worked model: revenue 100, growing 10% for 2 years; EBIT margin 20%,
# tax 25%, D&A 5%, CapEx 6%, NWC 10% of revenue; WACC 10%, terminal growth 2%.
#
#   Year 1: revenue 110, EBIT 22, NOPAT 16.5, D&A 5.5, CapEx 6.6,
#           NWC 11 (was 10) so change 1.0          FCF = 16.5 + 5.5 - 6.6 - 1.0 = 14.40
#   Year 2: revenue 121, EBIT 24.2, NOPAT 18.15, D&A 6.05, CapEx 7.26,
#           NWC 12.1 so change 1.1                 FCF = 18.15 + 6.05 - 7.26 - 1.1 = 15.84
#   Terminal value at year 2 = 15.84 x 1.02 / (0.10 - 0.02) = 201.96
#   PV = 14.40 / 1.1 + 15.84 / 1.21 + 201.96 / 1.21 = 13.0909 + 13.0909 + 166.9091 = 193.0909
HAND = dict(base_revenue=100, revenue_growth=0.10, years=2, ebit_margin=0.20, tax_rate=0.25,
            da_pct=0.05, capex_pct=0.06, nwc_pct=0.10, discount_rate=0.10,
            terminal_growth=0.02, net_debt=30, shares_outstanding=10)


def test_hand_worked_projection():
    y1, y2 = dcf.DCFModel(**HAND).projection()
    assert approx(y1.revenue, 110) and approx(y2.revenue, 121)
    assert approx(y1.nopat, 16.5) and approx(y2.nopat, 18.15)
    assert approx(y1.delta_nwc, 1.0) and approx(y2.delta_nwc, 1.1)
    assert approx(y1.fcf, 14.40) and approx(y2.fcf, 15.84)
    assert approx(y2.ebitda, 24.2 + 6.05)


def test_hand_worked_valuation():
    res = dcf.DCFModel(**HAND).value()
    assert approx(res.terminal_value, 201.96)
    assert approx(res.pv_fcfs[0], 14.40 / 1.1) and approx(res.pv_fcfs[1], 15.84 / 1.21)
    assert approx(res.pv_terminal_value, 201.96 / 1.21)
    assert approx(res.enterprise_value, 14.40 / 1.1 + 15.84 / 1.21 + 201.96 / 1.21)
    assert approx(res.equity_value, res.enterprise_value - 30)
    assert approx(res.value_per_share, res.equity_value / 10)
    assert approx(res.implied_exit_multiple, 201.96 / (24.2 + 6.05))
    assert 0 < res.terminal_share < 1


def test_free_cash_flow_formula():
    assert approx(dcf.free_cash_flow(ebit=100, tax_rate=0.25, da=20, capex=30, delta_nwc=5), 60)
    # Every extra dollar of CapEx or working capital is a dollar less FCF.
    base = dcf.free_cash_flow(100, 0.25, 20, 30, 5)
    assert approx(dcf.free_cash_flow(100, 0.25, 20, 31, 5), base - 1)
    assert approx(dcf.free_cash_flow(100, 0.25, 20, 30, 6), base - 1)


def test_wacc_by_hand_and_edge_cases():
    # 60% equity at 10%, 40% debt at 5% before a 25% tax: 0.06 + 0.015
    assert approx(dcf.wacc(600, 400, 0.10, 0.05, 0.25), 0.075)
    assert approx(dcf.wacc(1_000, 0, 0.11, 0.05, 0.25), 0.11)          # all equity
    assert approx(dcf.wacc(0, 1_000, 0.11, 0.05, 0.25), 0.05 * 0.75)   # all debt


def test_cost_of_equity_is_capm():
    assert approx(dcf.cost_of_equity(0.04, 1.2, 0.09), rr.capm(0.04, 1.2, 0.09))
    assert approx(dcf.cost_of_equity(0.04, 1.2, 0.09), 0.10)


def test_net_debt_and_net_cash():
    assert dcf.net_debt(150, 40) == 110
    res = dcf.dcf_valuation([10, 10], 0.1, terminal_growth=0.0, net_debt=dcf.net_debt(0, 25))
    assert approx(res.equity_value, res.enterprise_value + 25)  # net cash adds to equity


# Identities


@pytest.mark.parametrize("n", [1, 3, 10, 25])
def test_flat_fcf_with_zero_growth_is_a_perpetuity(n):
    res = dcf.dcf_valuation([50.0] * n, 0.08, terminal_growth=0.0)
    assert approx(res.enterprise_value, tvm.pv_perpetuity(50, 0.08))


@pytest.mark.parametrize("n", [1, 5, 12])
def test_fcf_growing_at_g_gives_growing_perpetuity(n):
    r, g, c1 = 0.09, 0.03, 40.0
    fcfs = [c1 * (1 + g) ** k for k in range(n)]
    res = dcf.dcf_valuation(fcfs, r, terminal_growth=g)
    assert approx(res.enterprise_value, tvm.pv_growing_perpetuity(c1, r, g))


def test_gordon_terminal_value_equals_adding_up_the_years():
    fcfs = [100, 110, 118, 125, 130]
    r, g = 0.10, 0.03
    res = dcf.dcf_valuation(fcfs, r, terminal_growth=g)
    tail = tvm.pattern_cash_flows(fcfs[-1] * (1 + g), 4_000, first_period=6, growth=g)
    long_way = tvm.pv_cash_flows(list(enumerate(fcfs, 1)) + tail, r)
    assert abs(res.enterprise_value - long_way) < 1e-6


def test_terminal_value_matches_growing_perpetuity_shortcut():
    assert approx(dcf.terminal_value_gordon(100, 0.09, 0.025),
                  tvm.pv_growing_perpetuity(102.5, 0.09, 0.025))


@pytest.mark.parametrize("mid_year", [False, True])
def test_gordon_and_exit_multiple_round_trip(mid_year):
    fcfs, ebitda, r, g = [80, 90, 97, 103], 160.0, 0.095, 0.025
    gordon = dcf.dcf_valuation(fcfs, r, terminal_growth=g, final_ebitda=ebitda, mid_year=mid_year)
    multiple = dcf.dcf_valuation(fcfs, r, "exit_multiple", exit_multiple=gordon.implied_exit_multiple,
                                 final_ebitda=ebitda, mid_year=mid_year)
    assert approx(multiple.enterprise_value, gordon.enterprise_value)
    assert approx(multiple.implied_terminal_growth, g)


def test_implied_growth_inverts_gordon():
    tv = dcf.terminal_value_gordon(75, 0.10, 0.03)
    assert approx(dcf.implied_growth_from_terminal_value(tv, 75, 0.10), 0.03)


def test_mid_year_scales_each_explicit_pv_by_half_a_year():
    fcfs, r = [100, 120, 130], 0.08
    end = dcf.dcf_valuation(fcfs, r, terminal_growth=0.02)
    mid = dcf.dcf_valuation(fcfs, r, terminal_growth=0.02, mid_year=True)
    assert mid.discount_times == [0.5, 1.5, 2.5]
    for a, b in zip(mid.pv_fcfs, end.pv_fcfs):
        assert approx(a, b * (1 + r) ** 0.5)
    # Gordon flows arrive mid-year too, so the whole value scales by the same factor.
    assert approx(mid.enterprise_value, end.enterprise_value * (1 + r) ** 0.5)


def test_mid_year_flat_perpetuity():
    res = dcf.dcf_valuation([50.0] * 4, 0.08, terminal_growth=0.0, mid_year=True)
    assert approx(res.enterprise_value, 50 / 0.08 * 1.08 ** 0.5)


def test_exit_multiple_stays_at_end_of_year_under_mid_year():
    fcfs, r = [10, 10, 10], 0.1
    a = dcf.dcf_valuation(fcfs, r, "exit_multiple", exit_multiple=8, final_ebitda=20)
    b = dcf.dcf_valuation(fcfs, r, "exit_multiple", exit_multiple=8, final_ebitda=20, mid_year=True)
    assert approx(a.pv_terminal_value, b.pv_terminal_value)
    assert approx(a.pv_terminal_value, 160 / 1.1 ** 3)


def test_value_falls_as_discount_rate_rises_and_rises_with_growth():
    base = dcf.DCFModel(**HAND)
    values = [dcf.DCFModel(**{**HAND, "discount_rate": r}).value().enterprise_value
              for r in (0.08, 0.09, 0.10, 0.11, 0.12)]
    assert values == sorted(values, reverse=True)
    growths = [dcf.DCFModel(**{**HAND, "terminal_growth": g}).value().enterprise_value
               for g in (0.0, 0.01, 0.02, 0.03)]
    assert growths == sorted(growths)
    assert base.value().enterprise_value == values[2]


def test_model_matches_manual_pipeline():
    model = dcf.DCFModel(base_revenue=500, revenue_growth=[0.12, 0.10, 0.08, 0.06, 0.05],
                         ebit_margin=[0.15, 0.16, 0.17, 0.18, 0.18], tax_rate=0.25,
                         da_pct=0.04, capex_pct=0.05, nwc_pct=0.10, discount_rate=0.09,
                         terminal_growth=0.025, net_debt=120, shares_outstanding=50)
    rows = model.projection()
    manual = dcf.dcf_valuation([r.fcf for r in rows], 0.09, terminal_growth=0.025,
                               final_ebitda=rows[-1].ebitda, net_debt=120, shares_outstanding=50)
    assert approx(model.value().value_per_share, manual.value_per_share)
    assert len(model.value().to_dict()["pv_fcfs"]) == 5


def test_per_year_margin_lists_are_used_year_by_year():
    rows = dcf.project_fcf(100, [0.0, 0.0], [0.10, 0.30], 0.0, 0.0, 0.0, 0.0)
    assert approx(rows[0].ebit, 10) and approx(rows[1].ebit, 30)


# Validation


def test_gordon_growth_must_be_below_discount_rate():
    with pytest.raises(ValueError, match="below the discount rate"):
        dcf.dcf_valuation([100], 0.05, terminal_growth=0.05)


@pytest.mark.parametrize("kwargs, msg", [
    (dict(terminal_method="gordon", terminal_growth=None), "terminal_growth"),
    (dict(terminal_method="exit_multiple"), "exit_multiple and final_ebitda"),
    (dict(terminal_method="liquidation"), "terminal_method"),
    (dict(discount_rate=0.0), "positive"),
    (dict(shares_outstanding=0), "Shares"),
])
def test_valuation_rejects_bad_inputs(kwargs, msg):
    args = dict(fcfs=[10, 11], discount_rate=0.1, terminal_growth=0.02)
    args.update(kwargs)
    with pytest.raises(ValueError, match=msg):
        dcf.dcf_valuation(**args)


@pytest.mark.parametrize("kwargs, msg", [
    (dict(years=None), "number of years"),
    (dict(revenue_growth=[0.1, 0.1], years=3), "growth rates"),
    (dict(ebit_margin=[0.2, 0.2, 0.2]), "EBIT margin"),
    (dict(tax_rate=1.0), "Tax rate"),
    (dict(base_revenue=0), "Base revenue"),
])
def test_projection_rejects_bad_inputs(kwargs, msg):
    args = dict(base_revenue=100, revenue_growth=0.1, years=2, ebit_margin=0.2, tax_rate=0.25,
                da_pct=0.05, capex_pct=0.06, nwc_pct=0.1)
    args.update(kwargs)
    with pytest.raises(ValueError, match=msg):
        dcf.project_fcf(**args)


def test_wacc_rejects_bad_inputs():
    with pytest.raises(ValueError):
        dcf.wacc(0, 0, 0.1, 0.05, 0.25)
    with pytest.raises(ValueError):
        dcf.wacc(-1, 100, 0.1, 0.05, 0.25)
