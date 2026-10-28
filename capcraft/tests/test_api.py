"""API tests: the endpoints must agree with the library, reject bad input
with a readable message, and never emit NaN or Infinity."""
import json
import math

import pytest
from fastapi.testclient import TestClient

from capcraft import dcf, monte_carlo as mc, tvm
from capcraft import sensitivity as sa
from capcraft_api.main import app

client = TestClient(app)
SAMPLE = client.get("/api/xray/sample").json()
XRAY = {"csv_text": SAMPLE["csv_text"], "amounts": SAMPLE["amounts"], "benchmark": "MARKET", "seed": 3}


def no_bad_numbers(text):
    json.loads(text, parse_constant=lambda c: pytest.fail(f"{c} in JSON"))


def test_health_and_meta():
    assert client.get("/api/health").json()["status"] == "ok"
    m = client.get("/api/meta").json()
    assert m["name"] == "CapCraft" and set(m["assumptions"]) == {"plan", "xray", "dcf"}
    assert m["limits"]["max_simulations"] == 10_000


# Plan


PLAN = {"initial": 10_000, "monthly_contribution": 500, "years": 20, "expected_return": 0.07,
        "volatility": 0.15, "goal": 400_000, "n_sims": 4_000, "seed": 5}


def test_plan_matches_library_and_is_reproducible():
    a = client.post("/api/plan", json=PLAN)
    b = client.post("/api/plan", json=PLAN)
    assert a.status_code == 200 and a.json() == b.json()
    no_bad_numbers(a.text)
    j = a.json()
    sim = mc.simulate_gbm(10_000, 0.07, 0.15, 20, 12, 4_000, 500, 5)
    assert math.isclose(j["mean_final"], sim.mean_terminal())
    assert math.isclose(j["prob_goal"], sim.prob_reaching(400_000))
    assert j["invested"] == 10_000 + 500 * 240


def test_plan_straight_line_matches_tvm_and_sits_above_the_median():
    j = client.post("/api/plan", json=PLAN).json()
    m = 1.07 ** (1 / 12) - 1                       # the monthly rate equivalent to 7% a year
    expected = tvm.future_value(10_000, 0.07, 20) + 500 * ((1 + m) ** 240 - 1) / m
    assert math.isclose(j["straight_line_final"], expected, rel_tol=1e-6)
    assert j["straight_line_final"] > j["median_final"]       # volatility drag
    assert j["share_below_straight_line"] > 0.5


def test_plan_required_contribution_hits_the_goal_at_that_confidence():
    j = client.post("/api/plan", json=PLAN).json()
    need = {n["confidence"]: n["monthly"] for n in j["needed_monthly"]}
    assert need[0.5] < need[0.8] < need[0.9]
    sim = mc.simulate_gbm(10_000, 0.07, 0.15, 20, 12, 4_000, need[0.8], 5)
    assert sim.prob_reaching(400_000) >= 0.8


def test_plan_shapes():
    j = client.post("/api/plan", json=PLAN).json()
    assert len(j["time"]) == 241 and all(len(b) == 241 for b in j["bands"].values())
    assert len(j["sample_paths"]) == 30
    assert sum(j["histogram"]["counts"]) + j["histogram"]["overflow"] == 4_000


def test_plan_without_goal_and_with_random_seed():
    j = client.post("/api/plan", json={"n_sims": 200}).json()
    assert j["goal"] is None and j["needed_monthly"] is None and j["prob_goal"] is None
    assert isinstance(j["seed"], int)


@pytest.mark.parametrize("bad", [{"n_sims": 10**6}, {"years": 99}, {"volatility": -1}, {"initial": -5}])
def test_plan_rejects_out_of_range_inputs(bad):
    assert client.post("/api/plan", json=bad).status_code == 422


# X-ray


def test_xray_matches_library_and_has_consistent_shapes():
    r = client.post("/api/xray", json=XRAY)
    assert r.status_code == 200
    no_bad_numbers(r.text)
    j = r.json()
    n = j["n_periods"]
    assert n == 60 and len(j["labels"]) == n + 1 == len(j["drawdown"])
    assert all(len(s["values"]) == n + 1 for s in j["growth"])
    assert [s["name"] for s in j["growth"]][0] == "Portfolio" and j["growth"][-1]["name"] == "MARKET"
    assert math.isclose(sum(a["weight"] for a in j["assets"]), 1.0)
    assert math.isclose(sum(a["own_risk_share"] for a in j["assets"]), 1.0)
    assert min(j["drawdown"]) == pytest.approx(j["metrics"]["max_drawdown"])
    assert j["metrics"]["beta_vs_benchmark"] is not None
    assert j["diversified"] and j["diversification_benefit"] > 0


def test_xray_portfolio_beta_is_weighted_average_of_asset_betas():
    j = client.post("/api/xray", json=XRAY).json()
    avg = sum(a["weight"] * a["beta"] for a in j["assets"])
    assert avg == pytest.approx(j["metrics"]["beta_vs_benchmark"], abs=1e-9)


def test_xray_frontier_brackets_the_current_mix_and_is_reproducible():
    a = client.post("/api/xray", json=XRAY).json()
    b = client.post("/api/xray", json=XRAY).json()
    assert a["frontier"] == b["frontier"]
    f = a["frontier"]
    assert f["min_variance"]["annual_risk"] <= f["current"]["annual_risk"] + 1e-9
    assert f["max_sharpe"]["sharpe"] >= max(p["sharpe"] for p in f["points"]) - 1e-9
    assert math.isclose(sum(f["max_sharpe"]["weights"].values()), 1.0)
    assert len(f["points"]) <= 1_600 and len(f["assets"]) == 4


def test_xray_without_benchmark_or_amounts():
    r = client.post("/api/xray", json={"csv_text": SAMPLE["csv_text"], "seed": 1})
    assert r.status_code == 200
    j = r.json()
    assert len(j["assets"]) == 5            # MARKET is then just another asset
    assert j["metrics"]["beta_vs_benchmark"] is None
    assert all(math.isclose(a["weight"], 0.2) for a in j["assets"])


def test_xray_single_asset_has_no_frontier():
    csv = "Date,AAA\nd0,100\nd1,101\nd2,99\nd3,103\nd4,104"
    j = client.post("/api/xray", json={"csv_text": csv}).json()
    assert j["frontier"] is None
    assert any("Only 4 periods" in w for w in j["warnings"])


def test_xray_warns_about_suspicious_jump():
    csv = "Date,AAA,BBB\n" + "\n".join(f"d{i},{p},{100 + i}" for i, p in
                                       enumerate([100, 101, 50, 51, 52, 53, 54]))
    j = client.post("/api/xray", json={"csv_text": csv}).json()
    assert any("AAA" in w and "split" in w for w in j["warnings"])


@pytest.mark.parametrize("body, text", [
    ({"csv_text": "Date,A\nd0,1"}, "at least 2 rows"),
    ({"csv_text": "Date,A,B\nd0,1,\nd1,2,3\nd2,3,4"}, "blank"),
    ({**XRAY, "benchmark": "NOPE"}, "isn't a column"),
    ({**XRAY, "amounts": {"GROWTH": 1}}, "No amount given"),
    ({**XRAY, "amounts": {**SAMPLE["amounts"], "ZZZ": 1}}, "unknown assets"),
    ({**XRAY, "amounts": {**SAMPLE["amounts"], "BONDS": -1}}, "negative"),
])
def test_xray_bad_input_gets_a_readable_422(body, text):
    r = client.post("/api/xray", json=body)
    assert r.status_code == 422 and text in json.dumps(r.json())


def test_xray_limits():
    assert client.post("/api/xray", json={**XRAY, "periods_per_year": 7}).status_code == 422
    assert client.post("/api/xray", json={**XRAY, "n_frontier": 10**7}).status_code == 422
    assert client.post("/api/xray", json={"csv_text": "x" * 1_000_001}).status_code == 422
    wide = "Date," + ",".join(f"A{i}" for i in range(30)) + "\n" + "\n".join(
        f"d{r}," + ",".join(str(100 + r) for _ in range(30)) for r in range(5))
    assert "At most" in client.post("/api/xray", json={"csv_text": wide}).text


# DCF


DCF = {"base_revenue": 500, "revenue_growth": [0.12, 0.10, 0.08, 0.06, 0.05], "years": None,
       "ebit_margin": 0.18, "tax_rate": 0.25, "da_pct": 0.04, "capex_pct": 0.05, "nwc_pct": 0.10,
       "discount_rate": 0.09, "terminal_growth": 0.025, "net_debt": 120, "shares_outstanding": 50}
MODEL = dcf.DCFModel(base_revenue=500, revenue_growth=[0.12, 0.10, 0.08, 0.06, 0.05], ebit_margin=0.18,
                     tax_rate=0.25, da_pct=0.04, capex_pct=0.05, nwc_pct=0.10, discount_rate=0.09,
                     terminal_growth=0.025, net_debt=120, shares_outstanding=50)


def test_dcf_matches_library():
    r = client.post("/api/dcf", json=DCF)
    assert r.status_code == 200
    no_bad_numbers(r.text)
    j, res = r.json(), MODEL.value()
    assert math.isclose(j["valuation"]["value_per_share"], res.value_per_share)
    assert math.isclose(j["valuation"]["terminal_share"], res.terminal_share)
    assert [round(p["fcf"], 9) for p in j["projection"]] == [round(x, 9) for x in res.fcfs]
    assert j["metric"] == "value_per_share"


def test_dcf_grid_centre_is_the_base_case_and_orientation_is_right():
    g = client.post("/api/dcf", json=DCF).json()["sensitivity"]
    assert math.isclose(g["grid"][2][2], g["base_output"])
    assert math.isclose(g["base_output"], MODEL.value().value_per_share)
    row = g["grid"][2]
    assert row == sorted(row, reverse=True)                      # higher discount rate, lower value
    assert [r[2] for r in g["grid"]] == sorted(r[2] for r in g["grid"])   # higher growth, higher value


def test_dcf_tornado_is_sorted_and_checked_against_direct_recalculation():
    t = client.post("/api/dcf", json=DCF).json()["tornado"]
    assert [b["swing"] for b in t] == sorted((b["swing"] for b in t), reverse=True)
    w = next(b for b in t if b["param"] == "discount_rate")
    lo = dcf.DCFModel(**{**sa.dcf_base(MODEL), "discount_rate": 0.08}).value().value_per_share
    assert math.isclose(w["low_output"], lo)


def test_dcf_keeps_year_by_year_lists_when_shifting():
    # growth_shift +3 pts applied to a list equals a model with every year's rate + 0.03
    t = client.post("/api/dcf", json=DCF).json()["tornado"]
    g = next(b for b in t if b["param"] == "growth_shift")
    shifted = dcf.DCFModel(**{**sa.dcf_base(MODEL), "revenue_growth": [x + 0.03 for x in MODEL.revenue_growth]})
    assert math.isclose(g["high_output"], shifted.value().value_per_share)


def test_reverse_dcf_round_trip():
    price = MODEL.value().value_per_share
    r = client.post("/api/dcf", json={**DCF, "market_price": price}).json()["reverse"]
    assert abs(r["upside"]) < 1e-9
    assert r["implied_discount_rate"]["value"] == pytest.approx(0.09, abs=1e-8)
    assert r["implied_growth"]["available"] and r["implied_growth"]["unique"]


def test_reverse_dcf_expensive_stock_implies_more_growth_and_impossible_price_is_explained():
    value = MODEL.value().value_per_share
    pricey = client.post("/api/dcf", json={**DCF, "market_price": value * 1.5}).json()["reverse"]
    assert pricey["implied_growth"]["value"] > pricey["model_average_growth"]
    assert pricey["upside"] < 0
    absurd = client.post("/api/dcf", json={**DCF, "market_price": 1e8}).json()["reverse"]
    assert not absurd["implied_growth"]["available"] and "No value" in absurd["implied_growth"]["reason"]


def test_dcf_without_shares_falls_back_to_equity_value():
    j = client.post("/api/dcf", json={**DCF, "shares_outstanding": None}).json()
    assert j["metric"] == "equity_value" and j["valuation"]["value_per_share"] is None


def test_dcf_exit_multiple_method():
    body = {**DCF, "terminal_method": "exit_multiple", "exit_multiple": 10, "terminal_growth": None}
    j = client.post("/api/dcf", json=body).json()
    assert j["sensitivity"]["y_label"] == "Exit multiple"
    assert math.isclose(j["sensitivity"]["grid"][2][2], j["sensitivity"]["base_output"])
    assert j["valuation"]["implied_terminal_growth"] is not None


def test_dcf_impossible_grid_cells_are_null_not_nan():
    body = {**DCF, "discount_rate": 0.03, "terminal_growth": 0.025}
    r = client.post("/api/dcf", json=body)
    assert r.status_code == 200
    no_bad_numbers(r.text)
    assert any(c is None for row in r.json()["sensitivity"]["grid"] for c in row)


@pytest.mark.parametrize("body, text", [
    ({**DCF, "discount_rate": 0.02, "terminal_growth": 0.03}, "growth"),
    ({**DCF, "terminal_method": "exit_multiple", "exit_multiple": None}, "exit_multiple is required"),
    ({**DCF, "market_price": 10, "shares_outstanding": None}, "shares_outstanding"),
    ({**DCF, "ebit_margin": [0.1, 0.2, 0.3]}, "EBIT margin"),
])
def test_dcf_bad_inputs_get_readable_422(body, text):
    r = client.post("/api/dcf", json=body)
    assert r.status_code == 422 and text in json.dumps(r.json())


def test_wacc_matches_library():
    j = client.post("/api/wacc", json={}).json()
    ke = dcf.cost_of_equity(0.04, 1.0, 0.09)
    assert math.isclose(j["cost_of_equity"], ke)
    assert math.isclose(j["wacc"], dcf.wacc(1500, 500, ke, 0.06, 0.25))
    assert math.isclose(j["equity_weight"] + j["debt_weight"], 1.0)


def test_openapi_describes_every_endpoint_for_type_generation():
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/api/plan", "/api/xray", "/api/xray/sample", "/api/dcf", "/api/wacc", "/api/meta"} <= set(paths)


def test_dcf_grid_axes_are_centred_on_the_base_case_in_even_steps():
    g = client.post("/api/dcf", json=DCF).json()["sensitivity"]
    assert g["x_values"] == pytest.approx([0.07, 0.08, 0.09, 0.10, 0.11])
    assert g["y_values"] == pytest.approx([0.015, 0.02, 0.025, 0.03, 0.035])
