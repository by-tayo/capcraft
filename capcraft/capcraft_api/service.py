"""The calculations behind each endpoint. No web code here: each function
takes a request model, calls the capcraft library, and returns a plain dict
shaped like the matching response model. NaN and infinity never leave this
module (they become None)."""
import math
import secrets
from dataclasses import asdict, replace
from typing import Dict, List, Optional

import numpy as np

from capcraft import data, dcf, monte_carlo as mc, risk_metrics as rm, risk_return as rr
from capcraft import sensitivity as sa
from capcraft.sample_data import SAMPLE_WEIGHTS, synthetic_price_csv

from . import __version__
from . import snapshots
from .providers import edgar, fred, http, prices
from .schemas import (MAX_ASSETS, MAX_FORECAST_YEARS, MAX_FRONTIER, MAX_ROWS, MAX_SIMS, MAX_YEARS,
                      DCFRequest, PlanRequest, WaccRequest, XrayRequest)

DISCLAIMER = ("For learning only. Not financial advice. Results come from simple models and from "
              "whatever inputs you supply; they are not predictions.")


def num(x) -> Optional[float]:
    """float(x), or None when x is missing, NaN or infinite."""
    if x is None:
        return None
    x = float(x)
    return x if math.isfinite(x) else None


def _attempt(fn, *a, **k):
    try:
        return fn(*a, **k)
    except ValueError:
        return None


def _pct(x, d=1):
    return f"{x * 100:.{d}f}%"


# Plan vs. reality


def plan(req: PlanRequest) -> Dict:
    seed = req.seed if req.seed is not None else secrets.randbelow(2 ** 31)
    steps = 12
    sim = mc.simulate_gbm(req.initial, req.expected_return, req.volatility, req.years, steps,
                          req.n_sims, req.monthly_contribution, seed)
    n_steps = req.years * steps

    m = (1 + req.expected_return) ** (1 / steps) - 1
    line, v = [req.initial], req.initial
    for _ in range(n_steps):
        v = v * (1 + m) + req.monthly_contribution
        line.append(v)

    qs = (5, 10, 25, 50, 75, 90, 95)
    bands = sim.percentile_bands((5, 25, 50, 75, 95))
    terminal = sim.terminal
    top = float(np.percentile(terminal, 99))
    edges = np.linspace(0, max(top, 1.0), 41)
    counts, _ = np.histogram(terminal[terminal <= edges[-1]], bins=edges)

    needed = None
    if req.goal is not None:
        needed = [{"confidence": c,
                   "monthly": mc.contribution_for_goal(req.initial, req.goal, c, req.expected_return,
                                                       req.volatility, req.years, steps, req.n_sims, seed)}
                  for c in (0.5, 0.8, 0.9)]
    return {
        "seed": seed, "n_sims": sim.n_sims, "years": req.years, "invested": sim.invested,
        "goal": req.goal, "straight_line_final": line[-1],
        "mean_final": sim.mean_terminal(), "median_final": sim.median_terminal(),
        "percentiles": {str(q): x for q, x in sim.percentiles(qs).items()},
        "prob_loss": sim.prob_loss(),
        "share_below_straight_line": float((terminal < line[-1]).mean()),
        "prob_goal": sim.prob_reaching(req.goal) if req.goal is not None else None,
        "value_at_risk_95": sim.value_at_risk(0.95),
        "conditional_value_at_risk_95": sim.conditional_value_at_risk(0.95),
        "needed_monthly": needed,
        "time": [round(float(t), 4) for t in sim.time_axis],
        "straight_line": [round(x, 2) for x in line],
        "bands": {f"p{q}": [round(float(x), 2) for x in b] for q, b in bands.items()},
        "sample_paths": [[round(float(x), 2) for x in row] for row in sim.paths[:30]],
        "histogram": {"edges": [float(e) for e in edges], "counts": [int(c) for c in counts],
                      "overflow": int((terminal > edges[-1]).sum())},
    }


# Portfolio X-ray


def sample() -> Dict:
    return {"csv_text": synthetic_price_csv(), "amounts": dict(SAMPLE_WEIGHTS), "benchmark": "MARKET",
            "synthetic": True,
            "note": "Made-up prices from a seeded random generator. Not real assets and not market history."}


def _growth(returns, name):
    return {"name": name, "values": [round(100 * g, 4) for g in rm.cumulative_growth(returns)]}


def xray(req: XrayRequest) -> Dict:
    seed = req.seed if req.seed is not None else secrets.randbelow(2 ** 31)
    dates, prices = data.read_prices(req.csv_text)
    n_rows = len(next(iter(prices.values())))
    if len(prices) > MAX_ASSETS + 1:
        raise ValueError(f"At most {MAX_ASSETS} assets are allowed here, got {len(prices)} columns")
    if n_rows > MAX_ROWS:
        raise ValueError(f"At most {MAX_ROWS} rows are allowed here, got {n_rows}")
    ppy = req.periods_per_year

    bench_returns = None
    if req.benchmark:
        if req.benchmark not in prices:
            raise ValueError(f"Benchmark '{req.benchmark}' isn't a column in your data "
                             f"(columns: {', '.join(prices)})")
        bench_prices = prices.pop(req.benchmark)
        bench_returns = data.prices_to_returns(bench_prices)
    if not prices:
        raise ValueError("No asset columns left after removing the benchmark")

    names = list(prices)
    if req.amounts is None:
        amounts = [1.0] * len(names)
    else:
        extra = [k for k in req.amounts if k not in prices]
        missing = [n for n in names if n not in req.amounts]
        if extra:
            raise ValueError(f"Amounts given for unknown assets: {', '.join(extra)}")
        if missing:
            raise ValueError(f"No amount given for: {', '.join(missing)}")
        amounts = [req.amounts[n] for n in names]
    if any(a < 0 for a in amounts):
        raise ValueError("Amounts can't be negative (short positions aren't supported here)")
    weights = rr.weights_from_values(amounts)

    pf = data.portfolio_from_prices(prices, weights, ppy)
    rf_period = rm.periodic_rate(req.risk_free_annual, ppy)
    port = pf.period_returns()
    metrics = pf.risk_metrics(rf_period, bench_returns)
    if "jensens_alpha_per_period" in metrics:
        metrics["jensens_alpha_per_year"] = metrics["jensens_alpha_per_period"] * ppy
    summary = pf.summary()
    port_risk = pf.risk()
    contrib = {r["name"]: r["contribution"] for r in pf.relevant_risk()}
    betas = pf.betas_vs(bench_returns) if bench_returns is not None else [None] * len(names)

    assets = []
    for h, b in zip(pf.holdings, betas):
        assets.append({
            "name": h.name, "weight": h.weight,
            "annual_return": num(_attempt(rm.annualized_return, h.returns, ppy)),
            "annual_risk": rm.annualized_volatility(h.returns, ppy),
            "sharpe": num(_attempt(rm.sharpe_ratio, h.returns, rf_period, ppy)),
            "max_drawdown": rm.max_drawdown(h.returns)["max_drawdown"],
            "beta": num(b),
            "own_risk_share": contrib[h.name] / port_risk if port_risk else 0.0,
        })

    growth = [_growth(port, "Portfolio")] + [_growth(h.returns, h.name) for h in pf.holdings]
    if bench_returns is not None:
        growth.append(_growth(bench_returns, req.benchmark))

    warnings: List[str] = []
    if pf.n_periods < 24:
        warnings.append(f"Only {pf.n_periods} periods of history. Ratios and the frontier from so little "
                        f"data are very uncertain.")
    series = dict(prices)
    if req.benchmark:
        series[req.benchmark] = bench_prices
    for n, p in series.items():
        worst = max(abs(b / a - 1) for a, b in zip(p, p[1:]))
        if worst > 0.4:
            warnings.append(f"{n} has a one-period move of {_pct(worst, 0)}. That can be real, or a "
                            f"stock split or data error. Check it, because it will dominate the risk numbers.")

    frontier = None
    if len(names) >= 2:
        f = pf.efficient_frontier(req.n_frontier, req.risk_free_annual, seed)
        n = len(names)
        step = max(1, (len(f.risks) - n) // 1500)
        idx = list(range(n, len(f.risks), step))
        sharpe = lambda i: num(f.sharpes[i])
        er, ee = f.efficient_edge()
        frontier = {
            "points": [{"annual_risk": float(f.risks[i]), "annual_return": float(f.returns[i]),
                        "sharpe": sharpe(i)} for i in idx],
            "edge": [{"annual_risk": float(x), "annual_return": float(y)} for x, y in zip(er, ee)],
            "assets": [{"annual_risk": float(f.risks[i]), "annual_return": float(f.returns[i]),
                        "name": names[i]} for i in range(n)],
            "current": {"annual_risk": summary["annualized_risk"],
                        "annual_return": summary["annualized_return_arithmetic"], "name": "Your mix"},
            "min_variance": f.min_variance(), "max_sharpe": f.max_sharpe(),
            "n_sampled": len(f.risks) - n,
        }
        warnings.append("The frontier plots average return x periods per year (arithmetic), so its returns "
                        "run a little higher than the compound growth rates in the table.")

    return {
        "seed": seed, "n_periods": pf.n_periods, "periods_per_year": ppy,
        "labels": dates if dates is not None else [str(i) for i in range(pf.n_periods + 1)],
        "assets": assets,
        "correlation": {"names": names, "matrix": pf.correlation_matrix().tolist()},
        "metrics": {k: (num(v) if isinstance(v, float) else v) for k, v in metrics.items()},
        "diversification_benefit": (summary["weighted_average_risk"] - port_risk) * ppy ** 0.5,
        "diversified": bool(summary["diversified"]),
        "growth": growth,
        "drawdown": rm.drawdown_series(port),
        "frontier": frontier,
        "warnings": warnings,
    }


# DCF


def _shift(value, delta):
    if isinstance(value, (int, float)):
        return value + delta
    return [v + delta for v in value]


def _model(req: DCFRequest) -> dcf.DCFModel:
    lists = any(isinstance(v, list) for v in (req.revenue_growth, req.ebit_margin, req.da_pct,
                                              req.capex_pct, req.nwc_pct))
    return dcf.DCFModel(
        base_revenue=req.base_revenue, revenue_growth=req.revenue_growth, ebit_margin=req.ebit_margin,
        tax_rate=req.tax_rate, da_pct=req.da_pct, capex_pct=req.capex_pct, nwc_pct=req.nwc_pct,
        discount_rate=req.discount_rate, years=None if lists else req.years,
        terminal_method=req.terminal_method, terminal_growth=req.terminal_growth,
        exit_multiple=req.exit_multiple, net_debt=req.net_debt,
        shares_outstanding=req.shares_outstanding, mid_year=req.mid_year)


def _metric(model) -> str:
    return "value_per_share" if model.shares_outstanding else "equity_value"


def _shifted_fn(model: dcf.DCFModel, metric: str):
    """Valuation as a function of a few knobs. Shifts are ADDED to every year's
    value, so year-by-year assumption lists keep their shape."""
    def f(discount_rate, terminal_growth, exit_multiple, growth_shift=0.0, margin_shift=0.0,
          capex_shift=0.0):
        m = replace(model, discount_rate=discount_rate, terminal_growth=terminal_growth,
                    exit_multiple=exit_multiple,
                    revenue_growth=_shift(model.revenue_growth, growth_shift),
                    ebit_margin=_shift(model.ebit_margin, margin_shift),
                    capex_pct=_shift(model.capex_pct, capex_shift))
        value = getattr(m.value(), metric)
        if value is None:
            raise ValueError(f"{metric} isn't available for this model")
        return value
    return f


def _solution(fn, *args, **kwargs) -> Dict:
    try:
        out = fn(*args, **kwargs)
    except ValueError as e:
        return {"available": False, "reason": str(e)}
    return {"available": True, "value": out["root"], "unique": out["unique"]}


def dcf_analysis(req: DCFRequest) -> Dict:
    model = _model(req)
    w, g, em = model.discount_rate, model.terminal_growth, model.exit_multiple
    gordon = model.terminal_method == "gordon"
    if gordon and g is None:
        raise ValueError("terminal_growth is required for the Gordon growth method")
    if not gordon and em is None:
        raise ValueError("exit_multiple is required for the exit multiple method")
    res = model.value()
    metric = _metric(model)

    fn = _shifted_fn(model, metric)
    base = {"discount_rate": w, "terminal_growth": g, "exit_multiple": em,
            "growth_shift": 0.0, "margin_shift": 0.0, "capex_shift": 0.0}

    xs = [round(w + d, 6) for d in (-0.02, -0.01, 0, 0.01, 0.02) if w + d > 0.01]
    if gordon:
        ypar, ylabel, ys = "terminal_growth", "Terminal growth", [round(g + d, 6) for d in (-0.01, -0.005, 0, 0.005, 0.01)]
    else:
        ypar, ylabel, ys = "exit_multiple", "Exit multiple", [round(em * k, 4) for k in (0.8, 0.9, 1, 1.1, 1.2)]
    table = sa.two_way(fn, base, "discount_rate", xs, ypar, ys)
    grid = {"metric": metric, "x_label": "Discount rate", "x_values": xs, "y_label": ylabel,
            "y_values": ys, "grid": [[num(c) for c in row] for row in table.grid],
            "base_output": table.base_output}

    ranges = {}
    lo_w = max(w - 0.01, (g + 0.005) if gordon else 0.005)
    ranges["discount_rate"] = ("Discount rate", (lo_w, w + 0.01), (_pct(lo_w), _pct(w + 0.01)))
    if gordon:
        hi_g = min(g + 0.01, w - 0.005)
        ranges["terminal_growth"] = ("Terminal growth", (g - 0.01, hi_g), (_pct(g - 0.01), _pct(hi_g)))
    else:
        ranges["exit_multiple"] = ("Exit multiple", (em * 0.8, em * 1.2), (f"{em * 0.8:.1f}x", f"{em * 1.2:.1f}x"))
    ranges["growth_shift"] = ("Revenue growth", (-0.03, 0.03), ("-3 pts", "+3 pts"))
    ranges["margin_shift"] = ("Operating margin", (-0.03, 0.03), ("-3 pts", "+3 pts"))
    ranges["capex_shift"] = ("Capital spending", (-0.01, 0.01), ("-1 pt", "+1 pt"))
    bars = sa.tornado(fn, base, {k: v[1] for k, v in ranges.items()})
    tornado = [{"param": b.param, "label": ranges[b.param][0], "low_label": ranges[b.param][2][0],
                "high_label": ranges[b.param][2][1], "low_output": b.low_output,
                "high_output": b.high_output, "swing": b.swing} for b in bars]

    reverse = None
    if req.market_price is not None:
        if not model.shares_outstanding:
            raise ValueError("A reverse DCF needs shares_outstanding to compare with a per-share price")
        growth = req.revenue_growth if isinstance(req.revenue_growth, list) else [req.revenue_growth]
        lo_r = (g + 0.005) if gordon else 0.005
        reverse = {
            "market_price": req.market_price, "model_value": res.value_per_share,
            "upside": res.value_per_share / req.market_price - 1,
            "model_average_growth": sum(growth) / len(growth),
            "implied_growth": _solution(sa.implied_dcf_input, model, "revenue_growth",
                                        req.market_price, -0.3, 0.6),
            "implied_discount_rate": _solution(sa.implied_dcf_input, model, "discount_rate",
                                               req.market_price, lo_r, 0.5),
        }

    projection = [{"year": r.year, "revenue": r.revenue, "ebit": r.ebit, "nopat": r.nopat, "da": r.da,
                   "capex": r.capex, "delta_nwc": r.delta_nwc, "fcf": r.fcf, "pv_fcf": pv}
                  for r, pv in zip(res.projection, res.pv_fcfs)]
    valuation = {
        "discount_rate": res.discount_rate, "terminal_method": res.terminal_method,
        "terminal_value": res.terminal_value, "pv_terminal_value": res.pv_terminal_value,
        "pv_explicit": res.pv_explicit, "enterprise_value": res.enterprise_value,
        "net_debt": res.net_debt, "equity_value": res.equity_value,
        "value_per_share": num(res.value_per_share), "terminal_share": num(res.terminal_share),
        "implied_exit_multiple": num(res.implied_exit_multiple),
        "implied_terminal_growth": num(res.implied_terminal_growth),
    }
    return {"metric": metric, "projection": projection, "valuation": valuation,
            "sensitivity": grid, "tornado": tornado, "reverse": reverse}


def wacc(req: WaccRequest) -> Dict:
    ke = dcf.cost_of_equity(req.risk_free, req.beta, req.market_return)
    total = req.equity_value + req.debt_value
    return {"cost_of_equity": ke,
            "wacc": dcf.wacc(req.equity_value, req.debt_value, ke, req.cost_of_debt, req.tax_rate),
            "equity_weight": req.equity_value / total if total else 0.0,
            "debt_weight": req.debt_value / total if total else 0.0}


# Meta


def meta() -> Dict:
    return {
        "name": "CapCraft", "version": __version__, "disclaimer": DISCLAIMER,
        "limits": {"max_simulations": MAX_SIMS, "max_years": MAX_YEARS, "max_assets": MAX_ASSETS,
                   "max_rows": MAX_ROWS, "max_frontier_mixes": MAX_FRONTIER,
                   "max_forecast_years": MAX_FORECAST_YEARS},
        "assumptions": {
            "plan": [
                "Returns follow geometric Brownian motion: each month's return is random, lognormal, "
                "and independent of the others. Real markets have fat tails and volatility clusters.",
                "The average return you enter is the MEAN outcome. The typical (median) outcome is lower "
                "because of volatility drag.",
                "Contributions are added at the end of each month. No taxes, fees or inflation.",
                "Required contributions are solved from the same simulation and seed, so they carry "
                "simulation noise. Raise the number of futures to reduce it.",
            ],
            "xray": [
                "Weights are held constant (rebalanced every period). Real buy-and-hold drifts.",
                "Risk is the sample standard deviation of past returns, annualized by the square root of "
                "periods per year, which assumes returns are independent over time.",
                "Beta is estimated by regression on the benchmark column you choose.",
                "The frontier is 'long-only mixes sampled at random', so min-risk and best-Sharpe are close "
                "approximations. They describe what WOULD have worked on this history, not what will work.",
            ],
            "dcf": [
                "Free cash flow = EBIT x (1 - tax) + D&A - CapEx - change in working capital.",
                "Terminal value is by Gordon growth or exit multiple. It is often most of the value: see "
                "the terminal share.",
                "The sensitivity grid and tornado change one or two inputs at a time and miss interactions. "
                "Tornado ranges are my defaults, not forecasts.",
                "A reverse DCF shows the constant growth (or discount rate) a market price implies with "
                "everything else unchanged. It is a question to investigate, not a verdict.",
            ],
        },
    }


# Live data


def capabilities() -> Dict:
    live = http.env("CAPCRAFT_SEC_USER_AGENT") is not None
    saved = snapshots.list_companies()
    return {"company": live or bool(saved), "live_company": live, "saved_companies": saved,
            "price": prices.configured(), "rates": fred.configured() or snapshots.get_rates() is not None}


def _from_snapshot(snap: Dict, why: str) -> Dict:
    return {"ticker": snap["ticker"], "name": snap["name"], "cik": snap["cik"],
            "fiscal_year_end": snap["fiscal_year_end"], "assumptions": snap["assumptions"], "price": None,
            "provenance": snap["provenance"], "source": "saved", "saved_on": snap["taken_on"],
            "warnings": list(snap.get("warnings", [])) + [
                f"{why} These numbers are a saved copy from {snap['taken_on']}. Type the current price by hand."]}


def company(ticker: str) -> Dict:
    if not edgar.TICKER_RE.match(ticker):
        raise ValueError("Enter a ticker symbol such as MSFT.")
    snap = snapshots.get_company(ticker)
    try:
        cik, sym, name = edgar.find_company(ticker)
        derived = edgar.derive(edgar.fetch_facts(cik))
    except http.NotConfigured:
        if snap:
            return _from_snapshot(snap, "Live lookups are not set up.")
        raise
    except http.Unavailable:
        if snap:
            return _from_snapshot(snap, "The live data source could not be reached.")
        raise
    warnings = list(derived["warnings"])
    price = None
    try:
        price = prices.latest_price(sym)
    except http.DataError as e:
        warnings.append(f"Share price unavailable: {e}")
    if price is None and prices.configured():
        warnings.append("No share price came back (the free daily limit may be used up). Type the price by hand.")
    return {"ticker": sym, "name": name, "cik": cik, "fiscal_year_end": derived["fiscal_year_end"],
            "assumptions": derived["assumptions"], "price": price, "provenance": derived["provenance"],
            "warnings": warnings, "source": "live", "saved_on": None}


def rates() -> Dict:
    try:
        live = fred.ten_year_yield()
    except http.Unavailable:
        live = None
    if live:
        return {"risk_free": live, "source": "live", "saved_on": None}
    snap = snapshots.get_rates()
    if snap:
        return {"risk_free": snap["risk_free"], "source": "saved", "saved_on": snap["taken_on"]}
    return {"risk_free": None, "source": None, "saved_on": None}
