"""Discounted cash flow (DCF) valuation: what a business is worth today.

The idea is the same one behind every formula in tvm.py. A business is
worth the present value of the cash it will hand back to the people who
fund it. A DCF has three parts:

  1. Project free cash flow year by year      project_fcf()
  2. Pick a discount rate (usually WACC)      wacc(), cost_of_equity()
  3. Discount the projections and add a
     terminal value for everything after      dcf_valuation()

DCFModel bundles every assumption into one object, so sensitivity.py
can change one input at a time and see what happens to the value.

Formulas
--------
Unlevered free cash flow (cash available to both lenders and owners):

    FCF = EBIT x (1 - tax rate) + D&A - CapEx - change in net working capital

    EBIT x (1 - t) is called NOPAT (net operating profit after tax).
    D&A is added back because it is an expense that isn't a cash payment.
    CapEx and increases in working capital are cash going out.

Weighted average cost of capital (the discount rate for unlevered FCF):

    WACC = E/V x R_e + D/V x R_d x (1 - t)        V = E + D

    E and D are MARKET values of equity and debt. R_e usually comes from
    CAPM, R_e = r_f + beta x (E(R_mkt) - r_f), the same risk_return.capm
    used elsewhere in CapCraft. Debt's cost is taken after tax because
    interest is tax-deductible.

Terminal value, two standard methods:

    Gordon growth (perpetuity growth):
        TV_N = FCF_N x (1 + g) / (WACC - g)       needs g < WACC
        This is tvm.pv_growing_perpetuity with first payment FCF_N x (1 + g).

    Exit multiple:
        TV_N = EV/EBITDA multiple x EBITDA_N

Enterprise value and equity value:

    EV = sum of FCF_t / (1 + WACC)^t  +  TV_N / (1 + WACC)^N
    Equity value = EV - net debt                  net debt = debt - cash
    Value per share = equity value / diluted shares outstanding

Cross-checks reported with every valuation:
    implied exit multiple    TV_N / EBITDA_N         (when Gordon is used)
    implied perpetual growth g that makes Gordon give the same TV_N
                                                     (when a multiple is used)
    terminal value share     PV of TV / EV
If one method implies an unrealistic number under the other (for example
a 40x multiple, or growth above the long-run economy), the assumptions
need another look.

Assumptions and simplifications (state these whenever you show a result)
------------------------------------------------------------------------
* Rates, margins and percentages are DECIMALS: 25% -> 0.25.
* Years are whole periods. Year 1 is the first projected year and the
  valuation date is today, the end of year 0.
* End-of-year convention by default: each year's FCF arrives at the END
  of that year. With mid_year=True each FCF arrives halfway through its
  year (discounted at t - 0.5), a common way to reflect cash coming in
  all year. Gordon growth flows also arrive mid-year then. An exit
  multiple is a sale price at a single date, so it stays at the end of
  year N. Practitioners differ on that last point, so it is stated here.
* Tax is a flat rate on EBIT. A negative EBIT produces a tax credit. Loss
  carryforwards, deferred taxes and the interest tax shield inside FCF
  are not modeled (the shield is in WACC instead).
* D&A, CapEx and net working capital are fixed percentages of revenue
  (one number, or one per year). Working capital in year 0 is the first
  year's percentage times the base revenue.
* WACC is constant over the whole forecast, so the capital structure is
  assumed stable.
* The equity bridge only subtracts net debt. Preferred stock, minority
  interest, leases or pension deficits can be folded into net_debt if
  they matter.

For learning only. Not financial advice.
"""
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Sequence, Union

from . import risk_return as rr
from . import tvm

Number = Union[int, float]
PerYear = Union[Number, Sequence[Number]]


# Building blocks


def free_cash_flow(ebit, tax_rate, da, capex, delta_nwc):
    """FCF = EBIT x (1 - t) + D&A - CapEx - change in NWC."""
    _check_tax(tax_rate)
    return ebit * (1 - tax_rate) + da - capex - delta_nwc


def cost_of_equity(risk_free, beta, market_return):
    """CAPM cost of equity: r_f + beta x (E(R_mkt) - r_f)."""
    return rr.capm(risk_free, beta, market_return)


def wacc(equity_value, debt_value, cost_of_equity_rate, cost_of_debt, tax_rate):
    """WACC = E/V x R_e + D/V x R_d x (1 - t), using market values."""
    _check_tax(tax_rate)
    if equity_value < 0 or debt_value < 0:
        raise ValueError("Equity and debt values can't be negative")
    total = equity_value + debt_value
    if total <= 0:
        raise ValueError("Equity plus debt must be positive")
    return (equity_value / total * cost_of_equity_rate
            + debt_value / total * cost_of_debt * (1 - tax_rate))


def net_debt(total_debt, cash):
    """Net debt = debt - cash (negative when the company holds more cash than debt)."""
    return total_debt - cash


def terminal_value_gordon(final_fcf, discount_rate, growth):
    """Value at the end of year N of FCF growing at g forever after year N:
    FCF_N x (1 + g) / (r - g)."""
    if growth >= discount_rate:
        raise ValueError("Terminal growth must be below the discount rate, "
                         "or the terminal value would be infinite")
    return tvm.pv_growing_perpetuity(final_fcf * (1 + growth), discount_rate, growth)


def terminal_value_exit_multiple(final_ebitda, multiple):
    """Value at the end of year N as a multiple of that year's EBITDA."""
    if multiple < 0:
        raise ValueError("Exit multiple can't be negative")
    return multiple * final_ebitda


def discount_factor(rate, t):
    """1 / (1 + r)^t, the same discounting as tvm.present_value(1, r, t)."""
    if rate <= -1:
        raise ValueError("Discount rate must be greater than -100%")
    return 1 / (1 + rate) ** t


# 1. Projecting free cash flow


@dataclass
class ProjectionYear:
    """One projected year. All money values are in the same units as base revenue."""
    year: int
    revenue: float
    ebit: float
    taxes: float
    nopat: float
    da: float
    capex: float
    nwc: float
    delta_nwc: float
    fcf: float

    @property
    def ebitda(self):
        return self.ebit + self.da


def _per_year(value, n, name):
    if isinstance(value, (int, float)):
        return [float(value)] * n
    values = [float(v) for v in value]
    if len(values) != n:
        raise ValueError(f"{name} has {len(values)} values but the forecast is {n} years")
    return values


def _check_tax(t):
    if not 0 <= t < 1:
        raise ValueError("Tax rate must be at least 0% and below 100%")


def project_fcf(base_revenue, revenue_growth, ebit_margin, tax_rate, da_pct, capex_pct,
                nwc_pct, years=None) -> List[ProjectionYear]:
    """Project revenue and free cash flow year by year.

    base_revenue     revenue in year 0 (the last actual year)
    revenue_growth   one rate for every year, or a list with one rate per year
    ebit_margin      EBIT as a share of revenue (one number or one per year)
    tax_rate         flat tax rate on EBIT
    da_pct           depreciation & amortization as a share of revenue
    capex_pct        capital expenditure as a share of revenue
    nwc_pct          net working capital as a share of revenue. FCF subtracts
                     the CHANGE in working capital each year.
    years            forecast length. Needed when revenue_growth is one number.
    """
    if base_revenue <= 0:
        raise ValueError("Base revenue must be positive")
    if isinstance(revenue_growth, (int, float)):
        if years is None:
            raise ValueError("Give the number of years, or one growth rate per year")
        n = int(years)
    else:
        n = len(revenue_growth)
        if years is not None and int(years) != n:
            raise ValueError(f"years={years} but {n} growth rates were given")
    if n < 1:
        raise ValueError("Forecast needs at least 1 year")
    _check_tax(tax_rate)
    growth = _per_year(revenue_growth, n, "Revenue growth")
    margin = _per_year(ebit_margin, n, "EBIT margin")
    da_p = _per_year(da_pct, n, "D&A %")
    capex_p = _per_year(capex_pct, n, "CapEx %")
    nwc_p = _per_year(nwc_pct, n, "NWC %")
    if any(g <= -1 for g in growth):
        raise ValueError("Revenue growth must be greater than -100%")

    rows = []
    revenue = base_revenue
    nwc_prev = base_revenue * nwc_p[0]
    for i in range(n):
        revenue = revenue * (1 + growth[i])
        ebit = revenue * margin[i]
        taxes = ebit * tax_rate
        da = revenue * da_p[i]
        capex = revenue * capex_p[i]
        nwc = revenue * nwc_p[i]
        delta = nwc - nwc_prev
        fcf = free_cash_flow(ebit, tax_rate, da, capex, delta)
        rows.append(ProjectionYear(i + 1, revenue, ebit, taxes, ebit - taxes, da, capex,
                                   nwc, delta, fcf))
        nwc_prev = nwc
    return rows


# 2. Discounting into a value


@dataclass
class DCFResult:
    """Everything a valuation produces, kept together for display and checks."""
    discount_rate: float
    terminal_method: str
    fcfs: List[float]
    discount_times: List[float]
    pv_fcfs: List[float]
    terminal_value: float          # value at the END of year N of every flow after N
    pv_terminal_value: float
    enterprise_value: float
    net_debt: float
    equity_value: float
    shares_outstanding: Optional[float]
    value_per_share: Optional[float]
    terminal_growth: Optional[float]
    exit_multiple: Optional[float]
    implied_exit_multiple: Optional[float] = None
    implied_terminal_growth: Optional[float] = None
    projection: Optional[List[ProjectionYear]] = field(default=None, repr=False)

    @property
    def pv_explicit(self):
        """Present value of the years you projected one by one."""
        return sum(self.pv_fcfs)

    @property
    def terminal_share(self):
        """Share of enterprise value that comes from the terminal value."""
        return self.pv_terminal_value / self.enterprise_value if self.enterprise_value else None

    def to_dict(self):
        d = asdict(self)
        d.pop("projection", None)
        d["pv_explicit"] = self.pv_explicit
        d["terminal_share"] = self.terminal_share
        return d


def dcf_valuation(fcfs, discount_rate, terminal_method="gordon", terminal_growth=None,
                  exit_multiple=None, final_ebitda=None, net_debt=0.0,
                  shares_outstanding=None, mid_year=False) -> DCFResult:
    """Value a stream of projected free cash flows.

    fcfs                FCF for years 1..N
    discount_rate       usually WACC
    terminal_method     "gordon" (needs terminal_growth) or
                        "exit_multiple" (needs exit_multiple and final_ebitda)
    final_ebitda        year-N EBITDA. Required for an exit multiple. With
                        Gordon it's optional and only used to report the
                        implied exit multiple.
    net_debt            debt minus cash, subtracted to get equity value
    shares_outstanding  diluted share count, for value per share
    mid_year            discount each year's FCF at t - 0.5 instead of t
    """
    fcfs = [float(f) for f in fcfs]
    n = len(fcfs)
    if n < 1:
        raise ValueError("Need at least one year of projected cash flow")
    if discount_rate <= 0:
        raise ValueError("Discount rate must be positive")
    if shares_outstanding is not None and shares_outstanding <= 0:
        raise ValueError("Shares outstanding must be positive")

    r = discount_rate
    times = [t - 0.5 if mid_year else float(t) for t in range(1, n + 1)]
    pv_fcfs = [f * discount_factor(r, t) for f, t in zip(fcfs, times)]
    # Gordon flows arrive mid-year too under mid_year, worth (1 + r)^0.5 more at year N.
    timing = (1 + r) ** 0.5 if mid_year else 1.0

    implied_multiple = implied_growth = None
    if terminal_method == "gordon":
        if terminal_growth is None:
            raise ValueError("Gordon growth needs terminal_growth")
        tv = terminal_value_gordon(fcfs[-1], r, terminal_growth) * timing
        if final_ebitda:
            implied_multiple = tv / final_ebitda
    elif terminal_method == "exit_multiple":
        if exit_multiple is None or final_ebitda is None:
            raise ValueError("The exit multiple method needs exit_multiple and final_ebitda")
        tv = terminal_value_exit_multiple(final_ebitda, exit_multiple)
        implied_growth = implied_growth_from_terminal_value(tv / timing, fcfs[-1], r)
    else:
        raise ValueError('terminal_method must be "gordon" or "exit_multiple"')

    pv_tv = tv * discount_factor(r, n)
    ev = sum(pv_fcfs) + pv_tv
    equity = ev - net_debt
    per_share = equity / shares_outstanding if shares_outstanding else None
    return DCFResult(r, terminal_method, fcfs, times, pv_fcfs, tv, pv_tv, ev, net_debt,
                     equity, shares_outstanding, per_share, terminal_growth, exit_multiple,
                     implied_multiple, implied_growth)


def implied_growth_from_terminal_value(terminal_value, final_fcf, discount_rate):
    """Growth rate g that makes FCF_N x (1 + g) / (r - g) equal a terminal value.
    Solving for g: g = (TV x r - FCF_N) / (TV + FCF_N)."""
    denom = terminal_value + final_fcf
    if denom == 0:
        raise ValueError("Can't solve for growth when TV + FCF_N is 0")
    return (terminal_value * discount_rate - final_fcf) / denom


# 3. One object holding every assumption


@dataclass
class DCFModel:
    """Every assumption behind a DCF in one place.

    model = DCFModel(base_revenue=500, revenue_growth=[0.12, 0.10, 0.08, 0.06, 0.05],
                     ebit_margin=0.18, tax_rate=0.25, da_pct=0.04, capex_pct=0.05,
                     nwc_pct=0.10, discount_rate=0.09, terminal_growth=0.025,
                     net_debt=120, shares_outstanding=50)
    result = model.value()
    """
    base_revenue: float
    revenue_growth: PerYear
    ebit_margin: PerYear
    tax_rate: float
    da_pct: PerYear
    capex_pct: PerYear
    nwc_pct: PerYear
    discount_rate: float
    years: Optional[int] = None
    terminal_method: str = "gordon"
    terminal_growth: Optional[float] = 0.025
    exit_multiple: Optional[float] = None
    net_debt: float = 0.0
    shares_outstanding: Optional[float] = None
    mid_year: bool = False

    def projection(self) -> List[ProjectionYear]:
        return project_fcf(self.base_revenue, self.revenue_growth, self.ebit_margin,
                           self.tax_rate, self.da_pct, self.capex_pct, self.nwc_pct,
                           self.years)

    def value(self) -> DCFResult:
        rows = self.projection()
        result = dcf_valuation([row.fcf for row in rows], self.discount_rate,
                               self.terminal_method, self.terminal_growth, self.exit_multiple,
                               rows[-1].ebitda, self.net_debt, self.shares_outstanding,
                               self.mid_year)
        result.projection = rows
        return result
