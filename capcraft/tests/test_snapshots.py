"""Saved snapshots: served only as a labelled fallback, never invented.
All data below is invented test data written into a temporary folder."""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from capcraft_api import service, snapshots
from capcraft_api.main import app
from capcraft_api.providers import edgar, http
from test_providers import fake_network, make_facts

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import make_snapshot  # noqa: E402

c = TestClient(app)


@pytest.fixture
def snapdir(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPCRAFT_SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPCRAFT_SEC_USER_AGENT", "Test test@example.com")
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    http.clear_cache()
    return tmp_path


def save_fixture_company(snapdir, today="2026-01-02"):
    d = edgar.derive(make_facts())
    make_snapshot.write(snapdir / "companies" / "FIX.json", {
        "ticker": "FIX", "name": "Fixture Co", "cik": 1, "fiscal_year_end": d["fiscal_year_end"],
        "assumptions": d["assumptions"], "provenance": d["provenance"], "warnings": [], "taken_on": today})
    return d


def unreachable(monkeypatch):
    def boom(*a, **k):
        raise http.Unavailable("The data source answered with an error (503).")
    monkeypatch.setattr(http, "get_json", boom)


def test_empty_folder_means_no_snapshots_and_no_invented_data(snapdir):
    assert snapshots.list_companies() == [] and snapshots.get_company("MSFT") is None and snapshots.get_rates() is None


def test_damaged_or_incomplete_files_are_ignored(snapdir):
    (snapdir / "companies").mkdir()
    (snapdir / "companies" / "BAD.json").write_text("{not json")
    (snapdir / "companies" / "HALF.json").write_text(json.dumps({"ticker": "HALF"}))
    (snapdir / "rates.json").write_text(json.dumps({"risk_free": 0.04}))
    assert snapshots.list_companies() == [] and snapshots.get_company("BAD") is None and snapshots.get_rates() is None


def test_ticker_cannot_escape_the_snapshot_folder(snapdir):
    # A complete, valid-looking snapshot sitting OUTSIDE the folder must never be reachable.
    d = edgar.derive(make_facts())
    outside = {"ticker": "SECRET", "name": "Outside", "cik": 1, "fiscal_year_end": d["fiscal_year_end"],
               "assumptions": d["assumptions"], "provenance": d["provenance"], "taken_on": "2026-01-01"}
    (snapdir.parent / "SECRET.json").write_text(json.dumps(outside))
    (snapdir / "companies").mkdir()
    for bad in ("../../SECRET", "..\\..\\SECRET", "/SECRET", "..", "A/B"):
        assert snapshots.get_company(bad) is None, bad


def test_unreachable_service_falls_back_to_the_saved_copy_and_says_so(snapdir, monkeypatch):
    save_fixture_company(snapdir)
    unreachable(monkeypatch)
    j = c.get("/api/company/fix").json()
    assert j["source"] == "saved" and j["saved_on"] == "2026-01-02" and j["price"] is None
    assert j["assumptions"]["base_revenue"] == pytest.approx(1331.0)
    assert any("saved copy from 2026-01-02" in w and "could not be reached" in w for w in j["warnings"])


def test_no_live_setup_uses_the_snapshot_and_lists_it_as_a_capability(snapdir, monkeypatch):
    save_fixture_company(snapdir)
    monkeypatch.delenv("CAPCRAFT_SEC_USER_AGENT")
    j = c.get("/api/company/FIX").json()
    assert j["source"] == "saved" and any("not set up" in w for w in j["warnings"])
    caps = c.get("/api/capabilities").json()
    assert caps == {"company": True, "live_company": False, "saved_companies": ["FIX"], "price": False, "rates": False}


def test_live_data_wins_over_a_snapshot_when_available(snapdir, monkeypatch):
    save_fixture_company(snapdir)
    fake_network(monkeypatch)
    j = c.get("/api/company/FIX").json()
    assert j["source"] == "live" and j["saved_on"] is None


def test_snapshot_is_not_used_to_hide_real_problems(snapdir, monkeypatch):
    # An unknown ticker (404) and an unsuitable company (502) must stay errors even if a snapshot exists.
    save_fixture_company(snapdir)
    fake_network(monkeypatch)
    assert c.get("/api/company/NOPE").status_code == 404
    bank = make_facts()
    del bank["facts"]["us-gaap"]["Revenues"]
    fake_network(monkeypatch, facts=bank)
    assert c.get("/api/company/FIX").status_code == 502


def test_no_snapshot_and_unreachable_is_still_a_clear_error(snapdir, monkeypatch):
    unreachable(monkeypatch)
    r = c.get("/api/company/FIX")
    assert r.status_code == 502 and "503" in r.json()["detail"]


def test_rates_prefer_live_then_saved_then_none(snapdir, monkeypatch):
    assert c.get("/api/rates").json() == {"risk_free": None, "source": None, "saved_on": None}
    make_snapshot.write(snapdir / "rates.json", {"risk_free": {"value": 0.041, "as_of": "2026-01-01"}, "taken_on": "2026-01-02"})
    unreachable(monkeypatch)
    monkeypatch.setenv("FRED_API_KEY", "k")
    j = c.get("/api/rates").json()
    assert j["source"] == "saved" and j["risk_free"]["value"] == 0.041 and j["saved_on"] == "2026-01-02"
    monkeypatch.setattr(http, "get_json", lambda *a, **k: {"observations": [{"date": "2026-02-01", "value": "4.30"}]})
    j = c.get("/api/rates").json()
    assert j["source"] == "live" and j["risk_free"]["value"] == pytest.approx(0.043)


# The snapshot script


def test_make_snapshot_writes_files_the_app_can_read_back(snapdir, monkeypatch, capsys):
    fake_network(monkeypatch)
    monkeypatch.setenv("FRED_API_KEY", "k")
    real = http.get_json
    def with_fred(url, headers=None, ttl=0, timeout=0):
        if "stlouisfed" in url:
            return {"observations": [{"date": "2026-01-01", "value": "4.10"}]}
        return real(url, headers, ttl, timeout)
    monkeypatch.setattr(http, "get_json", with_fred)
    assert make_snapshot.main(["fix", "nope"], out=snapdir, today="2026-03-04") == 0
    out = capsys.readouterr().out
    assert "FIX: Fixture Co" in out and "NOPE: skipped" in out
    saved = json.loads((snapdir / "companies" / "FIX.json").read_text())
    assert saved["taken_on"] == "2026-03-04" and saved["assumptions"]["base_revenue"] == pytest.approx(1331.0)
    assert "price" not in saved                                  # prices are never saved
    assert not (snapdir / "companies" / "NOPE.json").exists()
    assert snapshots.list_companies() == ["FIX"] and snapshots.get_rates()["risk_free"]["value"] == pytest.approx(0.041)


def test_make_snapshot_returns_failure_when_nothing_could_be_saved(snapdir, monkeypatch):
    unreachable(monkeypatch)
    assert make_snapshot.main(["FIX"], out=snapdir, today="2026-03-04") == 1
