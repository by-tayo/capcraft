"""Sensitivity analysis: which assumptions move the answer, and by how much.

A valuation or a simulation is only as good as its inputs. These tools
change inputs on purpose and record what happens to one output:

  one_way()     change one input across a list of values
  two_way()     change two inputs together, giving a grid, like the
                classic "WACC across, terminal growth down" DCF table
  tornado()     move every input from a low to a high value, one at a
                time, and rank them by how much the output swings
  elasticity()  % change in the output for a 1% change in one input

They work with any function that takes keyword arguments and returns a
number, so the same tools cover DCF, Monte Carlo and anything else:

    def price(discount_rate, terminal_growth):
        ...
        return value_per_share

    two_way(price, base={"discount_rate": 0.09, "terminal_growth": 0.025},
            param_x="discount_rate", values_x=[0.08, 0.09, 0.10],
            param_y="terminal_growth", values_y=[0.02, 0.025, 0.03])

For a dcf.DCFModel, dcf_function() and dcf_base() turn the model into
that kind of function plus its starting inputs.

Assumptions and conventions
---------------------------
* Changes are ONE AT A TIME (except two_way's pair). The other inputs
  stay at their base values. That shows each input's own effect, but
  it misses interactions, such as a higher growth rate mattering more
  when the discount rate is low. two_way() is there to show one such
  interaction.
* A tornado's low and high values should be equally plausible for each
  input (for example, the ends of a range you would bet on). Ranking
  inputs whose ranges are wildly different in plausibility makes the
  chart misleading.
* Elasticity uses a central difference: output at x(1 + h) and x(1 - h),
  divided by the 2h change in input. It is undefined at an input of 0.
* Combinations that can't be computed, such as terminal growth at or
  above the discount rate, become NaN in a two_way grid instead of
  stopping the whole table. one_way, tornado and elasticity still raise
  the error, because there a bad input usually means a typo.
* Monte Carlo outputs are noisy. When the function runs a simulation,
  pass a fixed seed so every scenario uses the same random draws
  ("common random numbers"). Then differences between scenarios come
  from the inputs, not from luck.

For learning only. Not financial advice.
"""
from dataclasses import asdict, dataclass
from typing import Callable, Dict, List, Sequence, Tuple

import numpy as np

from . import dcf as _dcf

Func = Callable[..., float]


def _call(func, base, **changes):
    unknown = set(changes) - set(base)
    if unknown:
        raise KeyError(f"Not an input of this model: {', '.join(sorted(unknown))}")
    return float(func(**{**base, **changes}))


# One input at a time


def one_way(func: Func, base: Dict, param: str, values: Sequence[float]) -> List[Tuple[float, float]]:
    """[(input value, output), ...] with every other input at its base value."""
    return [(v, _call(func, base, **{param: v})) for v in values]


@dataclass
class SensitivityTable:
    """A two-way grid. grid[i][j] is the output at values_y[i] and values_x[j]."""
    param_x: str
    values_x: List[float]
    param_y: str
    values_y: List[float]
    grid: np.ndarray
    base_output: float

    def as_rows(self):
        """Rows for printing or a dataframe: [[y, out_x1, out_x2, ...], ...]."""
        return [[y] + list(row) for y, row in zip(self.values_y, self.grid)]


def two_way(func: Func, base: Dict, param_x: str, values_x: Sequence[float],
            param_y: str, values_y: Sequence[float]) -> SensitivityTable:
    """Output for every combination of two inputs. Impossible combinations are NaN."""
    if param_x == param_y:
        raise ValueError("Pick two different inputs")
    grid = np.full((len(values_y), len(values_x)), np.nan)
    for i, y in enumerate(values_y):
        for j, x in enumerate(values_x):
            try:
                grid[i, j] = _call(func, base, **{param_x: x, param_y: y})
            except ValueError:
                pass  # e.g. terminal growth >= discount rate
    return SensitivityTable(param_x, list(values_x), param_y, list(values_y), grid,
                            _call(func, base))


# Ranking inputs


@dataclass
class TornadoBar:
    param: str
    low_input: float
    high_input: float
    low_output: float
    high_output: float
    base_output: float

    @property
    def swing(self):
        """Distance between the output at the low and the high input."""
        return abs(self.high_output - self.low_output)

    @property
    def downside(self):
        """Worst output across the two ends, minus the base output (0 or negative)."""
        return min(self.low_output, self.high_output) - self.base_output

    @property
    def upside(self):
        """Best output across the two ends, minus the base output (0 or positive)."""
        return max(self.low_output, self.high_output) - self.base_output


def tornado(func: Func, base: Dict, ranges: Dict[str, Tuple[float, float]]) -> List[TornadoBar]:
    """Move each input to its low and its high value, one at a time.
    Returns bars sorted from the biggest swing to the smallest."""
    base_out = _call(func, base)
    bars = [TornadoBar(p, lo, hi, _call(func, base, **{p: lo}), _call(func, base, **{p: hi}), base_out)
            for p, (lo, hi) in ranges.items()]
    return sorted(bars, key=lambda b: b.swing, reverse=True)


def elasticity(func: Func, base: Dict, param: str, bump: float = 0.01) -> float:
    """% change in output per 1% change in the input (central difference)."""
    x = base[param]
    if x == 0:
        raise ValueError(f"Elasticity is undefined when {param} is 0")
    out = _call(func, base)
    if out == 0:
        raise ValueError("Elasticity is undefined when the output is 0")
    up = _call(func, base, **{param: x * (1 + bump)})
    down = _call(func, base, **{param: x * (1 - bump)})
    return (up - down) / out / (2 * bump)


# DCF helpers


def dcf_function(output: str = "value_per_share") -> Func:
    """A function of DCFModel inputs that returns one output of the valuation:
    "value_per_share", "equity_value", "enterprise_value" or any other
    DCFResult field or property."""
    def run(**inputs):
        result = _dcf.DCFModel(**inputs).value()
        value = getattr(result, output)
        if value is None:
            raise ValueError(f"{output} isn't available for this model "
                             f"(value_per_share needs shares_outstanding)")
        return value
    return run


def dcf_base(model: "_dcf.DCFModel") -> Dict:
    """The model's inputs as a dict, ready to be the base for these tools."""
    return asdict(model)


# Working backward: what input makes the output equal a target?


def solve_input(func: Func, base: Dict, param: str, target: float, lo: float, hi: float,
                grid: int = 60, tol: float = 1e-12) -> Dict:
    """Find the value of one input that makes the output equal `target`
    (for example, the revenue growth a stock's price implies).

    The range lo..hi is scanned on `grid` points to find where the output
    crosses the target, and each crossing is then narrowed down by bisection.
    Points where the model can't be computed (such as terminal growth at or
    above the discount rate) are skipped. Returns a dict:

      root         the first solution found, scanning from lo to hi
      n_solutions  how many separate crossings were found
      unique       True if exactly one. If False, more than one input value
                   gives that output, so `root` is one of several answers.
      output       the model's output at root (equals target to within tol)

    Raises ValueError when no crossing exists in the range, saying what range
    of outputs the scan did produce. A solution that touches the target
    without crossing it (a double root) can be missed.
    """
    if not lo < hi:
        raise ValueError("lo must be below hi")
    if grid < 3:
        raise ValueError("grid must be at least 3")

    def gap(x):
        try:
            return _call(func, base, **{param: x}) - target
        except ValueError:
            return float("nan")

    xs = np.linspace(lo, hi, int(grid))
    gs = [gap(x) for x in xs]
    finite = [g for g in gs if g == g]
    if not finite:
        raise ValueError(f"The model couldn't be computed anywhere between {lo} and {hi}")
    brackets = []
    for i in range(len(xs) - 1):
        a, b = gs[i], gs[i + 1]
        if a != a or b != b:
            continue
        if a == 0:
            brackets.append((xs[i], xs[i]))
        elif a * b < 0:
            brackets.append((xs[i], xs[i + 1]))
    if gs[-1] == 0 and gs[-1] == gs[-1]:
        brackets.append((xs[-1], xs[-1]))
    if not brackets:
        raise ValueError(f"No value of {param} between {lo} and {hi} makes the output {target}; "
                         f"over that range the output only runs from {min(finite) + target:.6g} "
                         f"to {max(finite) + target:.6g}")
    a, b = brackets[0]
    if a != b:
        ga = gap(a)
        for _ in range(200):
            mid = (a + b) / 2
            gm = gap(mid)
            if gm != gm:
                raise ValueError("The model couldn't be computed inside the bracket; narrow lo and hi")
            if gm == 0 or (b - a) / 2 < tol:
                a = b = mid
                break
            if ga * gm < 0:
                b = mid
            else:
                a, ga = mid, gm
        a = b = (a + b) / 2
    return {"root": float(a), "n_solutions": len(brackets), "unique": len(brackets) == 1,
            "output": _call(func, base, **{param: a})}


def implied_dcf_input(model: "_dcf.DCFModel", param: str, price: float, lo: float, hi: float,
                      output: str = "value_per_share") -> Dict:
    """Reverse DCF: the value of one DCFModel input that makes the model's value
    per share equal a market price, with every other assumption left alone.

    Common uses: param="revenue_growth" (the constant yearly growth the price
    assumes over the forecast) or param="discount_rate" (the return the market
    is implicitly demanding). A list of growth rates in the model is replaced
    by one constant rate over the same number of years."""
    base = sa_base = asdict(model)
    if param == "revenue_growth" and not isinstance(model.revenue_growth, (int, float)):
        base = {**sa_base, "years": len(model.revenue_growth)}
    return solve_input(dcf_function(output), base, param, price, lo, hi)
