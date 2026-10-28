"""Tests for the live-data adapters. NO network is used.

The fixtures below are shaped like the SEC's "company facts" JSON (concept ->
units -> rows with start/end/val/form/filed) and like Alpha Vantage and FRED
responses, but every NUMBER IS INVENTED. These tests check my derivation logic and
error handling. They do not prove the real services still answer in this shape:
run scripts/check_live.py with real keys for that."""
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from capcraft_api.main import app
from capcraft_api.providers import edgar, fred, http, prices

FY = ["2020-12-31", "2021-12-31", "2022-12-31", "2023-12-31"]
REV = [1000e6, 1100e6, 1210e6, 1331e6]            # exactly 10% a year


def row(end, val, start=None, form="10-K", filed=None):
    r = {"end": end, "val": val, "form": form, "filed": filed or f"{int(end[:4]) + 1}-02-15"}
    if start is not None:
        r["start"] = start
    return r


def flows(vals, **kw):
    return {"units": {"USD": [row(e, v, start=f"{e[:4]}-01-01", **kw) for e, v in zip(FY, vals)]}}


def instants(vals):
    return {"units": {"USD": [row(e, v) for e, v in zip(FY, vals)]}}


def make_facts():
    gaap = {
        "Revenues": flows(REV),
        "OperatingIncomeLoss": flows([200e6, 220e6, 242e6, 266.2e6]),                  # 20% margin
        "IncomeTaxExpenseBenefit": flows([40e6, 44e6, 48.4e6, 53.24e6]),
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest":
            flows([200e6, 220e6, 242e6, 266.2e6]),                                      # 20% tax
        "DepreciationDepletionAndAmortization": flows([40e6, 44e6, 48.4e6, 53.24e6]),    # 4%
        "PaymentsToAcquirePropertyPlantAndEquipment": flows([60e6, 66e6, 72.6e6, 79.86e6]),  # 6%
        "AssetsCurrent": instants([500e6, 550e6, 600e6, 700e6]),
        "LiabilitiesCurrent": instants([300e6, 330e6, 360e6, 400e6]),                    # (700-400)/1331
        "LongTermDebt": instants([300e6] * 4),
        "CashAndCashEquivalentsAtCarryingValue": instants([100e6] * 3 + [150e6]),
        "MarketableSecuritiesCurrent": instants([0] * 3 + [50e6]),
    }
    dei = {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        {"end": "2024-02-01", "val": 90e6, "form": "10-K", "filed": "2024-02-15"},
        {"end": "2024-02-05", "val": 100e6, "form": "10-K", "filed": "2024-02-15"}]}}}
    return {"cik": 1, "entityName": "Fixture Co", "facts": {"us-gaap": gaap, "dei": dei}}


# Reading facts


def test_annual_keeps_only_full_years_from_10k_filings():
    f = make_facts()
    f["facts"]["us-gaap"]["Revenues"]["units"]["USD"] += [
        row("2023-03-31", 300e6, start="2023-01-01"),                    # a quarter
        row("2023-12-31", 9e6, start="2023-10-01"),                      # fourth quarter alone
        row("2024-03-31", 1e6, start="2024-01-01", form="10-Q"),         # not a 10-K
    ]
    got = edgar.annual(f, ["Revenues"])
    assert list(got) == FY and got["2023-12-31"] == 1331e6


def test_annual_latest_filing_wins_for_a_restated_year():
    f = make_facts()
    f["facts"]["us-gaap"]["Revenues"]["units"]["USD"].append(
        row("2022-12-31", 1215e6, start="2022-01-01", filed="2024-02-20"))
    assert edgar.annual(f, ["Revenues"])["2022-12-31"] == 1215e6


def test_annual_fills_gaps_from_a_later_tag_but_prefers_the_first():
    f = make_facts()
    g = f["facts"]["us-gaap"]
    g["RevenueFromContractWithCustomerExcludingAssessedTax"] = {"units": {"USD": [
        row("2023-12-31", 1400e6, start="2023-01-01"), row("2019-12-31", 900e6, start="2019-01-01")]}}
    got = edgar.annual(f, edgar.REVENUE)
    assert got["2023-12-31"] == 1400e6           # higher-priority tag wins the overlap
    assert got["2019-12-31"] == 900e6            # and the older tag's extra year is kept
    assert got["2021-12-31"] == 1100e6


# Deriving assumptions, with every number worked by hand


def test_derive_matches_hand_calculation():
    d = edgar.derive(make_facts())
    a = d["assumptions"]
    assert d["fiscal_year_end"] == "2023-12-31"
    assert a["base_revenue"] == pytest.approx(1331.0)
    assert a["revenue_growth"] == pytest.approx(0.10)                  # (1331/1000)^(1/3) - 1
    assert a["ebit_margin"] == pytest.approx(0.20)
    assert a["tax_rate"] == pytest.approx(0.20)
    assert a["da_pct"] == pytest.approx(0.04) and a["capex_pct"] == pytest.approx(0.06)
    assert a["nwc_pct"] == pytest.approx(300 / 1331)
    assert a["net_debt"] == pytest.approx(300 - 150 - 50)             # debt - cash - short-term investments
    assert a["shares_outstanding"] == pytest.approx(100.0)            # the most recent cover date
    assert d["warnings"] == [] and len(d["provenance"]) >= 6


def test_derive_caps_extreme_growth_and_says_so():
    f = make_facts()
    f["facts"]["us-gaap"]["Revenues"] = flows([100e6, 400e6, 1600e6, 6400e6])    # 300% a year
    d = edgar.derive(f)
    assert d["assumptions"]["revenue_growth"] == 0.30
    assert any("capped" in w for w in d["warnings"])


def test_derive_uses_default_tax_and_warns_when_tax_data_is_missing():
    f = make_facts()
    del f["facts"]["us-gaap"]["IncomeTaxExpenseBenefit"]
    d = edgar.derive(f)
    assert d["assumptions"]["tax_rate"] == 0.21 and any("21%" in w for w in d["warnings"])


def test_derive_warns_about_negative_margin():
    f = make_facts()
    f["facts"]["us-gaap"]["OperatingIncomeLoss"] = flows([-50e6] * 4)
    d = edgar.derive(f)
    assert d["assumptions"]["ebit_margin"] < 0 and any("negative" in w for w in d["warnings"])


def test_derive_refuses_companies_without_revenue_and_operating_income():
    bank = make_facts()
    del bank["facts"]["us-gaap"]["Revenues"], bank["facts"]["us-gaap"]["OperatingIncomeLoss"]
    with pytest.raises(http.DataError, match="banks and insurers"):
        edgar.derive(bank)


def test_derive_refuses_when_shares_are_missing():
    f = make_facts()
    del f["facts"]["dei"]
    with pytest.raises(http.DataError, match="shares"):
        edgar.derive(f)


def test_derived_assumptions_run_through_the_dcf_endpoint():
    a = edgar.derive(make_facts())["assumptions"]
    body = {"base_revenue": a["base_revenue"], "revenue_growth": a["revenue_growth"], "years": 5,
            "ebit_margin": a["ebit_margin"], "tax_rate": a["tax_rate"], "da_pct": a["da_pct"],
            "capex_pct": a["capex_pct"], "nwc_pct": a["nwc_pct"], "discount_rate": 0.09, "terminal_growth": 0.025,
            "net_debt": a["net_debt"], "shares_outstanding": a["shares_outstanding"]}
    r = TestClient(app).post("/api/dcf", json=body)
    assert r.status_code == 200 and r.json()["valuation"]["value_per_share"] > 0


# Prices and rates


def test_price_parses_alpha_vantage_shape_and_survives_rate_limit(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "k")
    monkeypatch.setattr(http, "get_json", lambda *a, **k: {"Global Quote": {"05. price": "123.4500", "07. latest trading day": "2024-02-02"}})
    assert prices.latest_price("ZZZ") == {"value": 123.45, "as_of": "2024-02-02"}
    monkeypatch.setattr(http, "get_json", lambda *a, **k: {"Information": "rate limit reached"})
    with pytest.raises(http.Unavailable, match="rate limit reached"):     # the provider's reason is passed on
        prices.latest_price("ZZZ")
    monkeypatch.setattr(http, "get_json", lambda *a, **k: {"Global Quote": {}})   # unknown symbol
    assert prices.latest_price("ZZZ") is None
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY")
    assert prices.latest_price("ZZZ") is None and not prices.configured()


def test_fred_skips_missing_days_and_converts_percent(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "k")
    monkeypatch.setattr(http, "get_json", lambda *a, **k: {"observations": [
        {"date": "2024-02-05", "value": "."}, {"date": "2024-02-02", "value": "4.25"}]})
    assert fred.ten_year_yield() == {"value": 0.0425, "as_of": "2024-02-02"}


def test_network_errors_do_not_leak_the_api_key(monkeypatch):
    http.clear_cache()

    def boom(*a, **k):
        raise urllib.error.HTTPError("https://x/?apikey=SECRET", 403, "no", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", boom)
    with pytest.raises(http.DataError) as e:
        http.get_json("https://x/?apikey=SECRET")
    assert "SECRET" not in str(e.value) and "403" in str(e.value)


# Endpoints


@pytest.fixture(autouse=True)
def empty_snapshot_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPCRAFT_SNAPSHOT_DIR", str(tmp_path / "none"))


def fake_network(monkeypatch, facts=None, price="50.00"):
    facts = facts or make_facts()

    def fetch(url, headers=None, ttl=0, timeout=0):
        if url == edgar.TICKERS_URL:
            return {"0": {"cik_str": 1, "ticker": "FIX", "title": "Fixture Co"}}
        if "companyfacts" in url:
            return facts
        if "alphavantage" in url:
            return {"Global Quote": {"05. price": price, "07. latest trading day": "2024-02-02"}}
        raise AssertionError(url)
    monkeypatch.setattr(http, "get_json", fetch)


def test_company_endpoint_end_to_end(monkeypatch):
    monkeypatch.setenv("CAPCRAFT_SEC_USER_AGENT", "Test test@example.com")
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "k")
    fake_network(monkeypatch)
    c = TestClient(app)
    j = c.get("/api/company/fix").json()
    assert j["ticker"] == "FIX" and j["name"] == "Fixture Co" and j["price"]["value"] == 50.0
    assert j["assumptions"]["base_revenue"] == pytest.approx(1331.0)
    json.loads(c.get("/api/company/FIX").text, parse_constant=lambda x: pytest.fail(x))
    caps = c.get("/api/capabilities").json()
    assert caps["company"] and caps["live_company"] and caps["price"] and not caps["rates"] and caps["saved_companies"] == []


def test_company_endpoint_without_price_key_still_works_and_without_contact_is_503(monkeypatch):
    monkeypatch.setenv("CAPCRAFT_SEC_USER_AGENT", "Test test@example.com")
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
    fake_network(monkeypatch)
    c = TestClient(app)
    assert c.get("/api/company/FIX").json()["price"] is None
    monkeypatch.delenv("CAPCRAFT_SEC_USER_AGENT")
    r = c.get("/api/company/FIX")
    assert r.status_code == 503 and "CAPCRAFT_SEC_USER_AGENT" in r.json()["detail"]


def test_company_endpoint_error_codes(monkeypatch):
    monkeypatch.setenv("CAPCRAFT_SEC_USER_AGENT", "Test test@example.com")
    fake_network(monkeypatch)
    c = TestClient(app)
    assert c.get("/api/company/NOPE").status_code == 404
    assert c.get("/api/company/1;DROP").status_code == 422
    bank = make_facts()
    del bank["facts"]["us-gaap"]["Revenues"]
    fake_network(monkeypatch, facts=bank)
    r = c.get("/api/company/FIX")
    assert r.status_code == 502 and "banks and insurers" in r.json()["detail"]


# Depreciation tags differ between companies


def test_depreciation_found_under_an_alternative_tag():
    facts = make_facts()
    gaap = facts["facts"]["us-gaap"]
    gaap["DepreciationAmortizationAndOther"] = gaap.pop("DepreciationDepletionAndAmortization")
    out = edgar.derive(facts)
    assert abs(out["assumptions"]["da_pct"] - 0.04) < 1e-9
    assert not any("Depreciation was not found" in n for n in out["warnings"])


def test_missing_depreciation_names_related_tags_so_the_right_one_can_be_added():
    facts = make_facts()
    gaap = facts["facts"]["us-gaap"]
    gaap["SomeOddAmortizationTag"] = gaap.pop("DepreciationDepletionAndAmortization")
    out = edgar.derive(facts)
    assert out["assumptions"]["da_pct"] == 0.0
    assert any("SomeOddAmortizationTag" in n for n in out["warnings"])
