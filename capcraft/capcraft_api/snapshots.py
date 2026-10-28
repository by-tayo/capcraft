"""Saved copies of real data, written once by scripts/make_snapshot.py.

They let the app show real companies with no keys and no network. Every file
records the day it was taken, and anything served from here is labelled "saved"
so it is never mistaken for a live lookup. Nothing in this folder is ever made up:
if the folder is empty, the feature is simply absent."""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from .providers import http


def root() -> Path:
    override = http.env("CAPCRAFT_SNAPSHOT_DIR")
    return Path(override) if override else Path(__file__).resolve().parent.parent / "data" / "snapshots"


def _read(path: Path) -> Optional[Dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None   # missing or damaged: behave as if there is no snapshot


def get_company(ticker: str) -> Optional[Dict]:
    safe = "".join(c for c in ticker.upper() if c.isalnum() or c in ".-")
    if not safe or safe != ticker.upper():
        return None
    data = _read(root() / "companies" / f"{safe}.json")
    needed = ("ticker", "name", "cik", "fiscal_year_end", "assumptions", "provenance", "taken_on")
    return data if data and all(k in data for k in needed) else None


def list_companies() -> List[str]:
    d = root() / "companies"
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob("*.json")):
        if get_company(f.stem):
            out.append(f.stem)
    return out


def get_rates() -> Optional[Dict]:
    data = _read(root() / "rates.json")
    if data and isinstance(data.get("risk_free"), dict) and "taken_on" in data:
        return data
    return None
