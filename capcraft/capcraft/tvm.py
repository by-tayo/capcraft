"""Time value of money: moving cash across time.

Future value, present value, uneven cash flows, annuities (ordinary,
due, and future value), perpetuities (regular, delayed, due),
combinations, and a CAPM required-return helper used by dcf.py.

Conventions
-----------
* Interest rates and growth rates are DECIMALS: 5%% -> 0.05.
* Time is counted in periods: t = 0 is today, t = 1 is one period away.
* The annuity and perpetuity shortcuts give a value ONE PERIOD BEFORE
  THE FIRST PAYMENT. If the first payment is at t, discount the
  shortcuts answer back from t - 1 to today with value_today().

Ported from the original time_value.py teaching script; worked
examples now live in examples/tvm_examples.py.
"""

from math import isclose

TOL = 1e-9


# Input checks


def _check_rate(r, name="Interest rate"):
    if r <= -1:
        raise ValueError(f"{name} must be greater than -100%")


def _check_periods(n, name="Number of periods"):
    if n < 0:
        raise ValueError(f"{name} can't be negative")


# 1. One amount: future value and present value


def future_value(amount, rate, periods):
    """FV = C x (1 + r)^n : what an amount grows to after n periods."""
    _check_rate(rate)
    _check_periods(periods)
    return amount * (1 + rate) ** periods


def present_value(amount, rate, periods):
    """PV = C / (1 + r)^n : what a future amount is worth n periods earlier."""
    _check_rate(rate)
    _check_periods(periods)
    return amount / (1 + rate) ** periods


def interest_breakdown(principal, rate, periods):
    """
    Splits the interest earned into:
      simple interest   = interest on the original amount only
      interest on interest = total interest - simple interest
    """
    fv = future_value(principal, rate, periods)
    total = fv - principal
    simple = principal * rate * periods
    return {"future_value": fv, "total_interest": total,
            "simple_interest": simple, "interest_on_interest": total - simple}


def move(amount, rate, from_period, to_period):
    """
    Move an amount from one point in time to another.
    Forward in time = compound; backward in time = discount.
    """
    gap = to_period - from_period
    _check_rate(rate)
    return amount * (1 + rate) ** gap


# 2. Several cash flows: add up each one's value


def pv_cash_flows(flows, rate, at_period=0):
    """
    Value of a list of cash flows at one point in time (today by default).
    `flows` is a list of (period, amount) pairs, e.g. [(1, 100), (2, 200)].
    """
    return sum(move(amount, rate, t, at_period) for t, amount in flows)


def timeline(flows, width=6):
    """Text drawing of a list of (period, amount) cash flows."""
    if not flows:
        return "(no cash flows)"
    last = max(t for t, _ in flows)
    by_t = {}
    for t, a in flows:
        by_t[t] = by_t.get(t, 0) + a
    top = "".join(f"{t:^{width + 4}}" for t in range(0, int(last) + 1))
    line = "".join("|" + "-" * (width + 3) for _ in range(0, int(last) + 1))
    vals = "".join(f"{(f'{by_t[t]:,.0f}' if t in by_t else ''):^{width + 4}}"
                   for t in range(0, int(last) + 1))
    return f"  Period: {top}\n          {line}\n  Cash:   {vals}"


# 3. Shortcuts for patterns (value is one period BEFORE the first payment)


def pv_annuity(payment, rate, n_payments):
    """Constant annuity: PV = C / r x [1 - 1 / (1 + r)^N]."""
    _check_rate(rate)
    _check_periods(n_payments, "Number of payments")
    if rate == 0:
        return payment * n_payments
    return payment / rate * (1 - 1 / (1 + rate) ** n_payments)


def pv_growing_annuity(first_payment, rate, growth, n_payments):
    """Growing annuity: PV = C / (r - g) x [1 - ((1 + g) / (1 + r))^N]."""
    _check_rate(rate)
    _check_rate(growth, "Growth rate")
    _check_periods(n_payments, "Number of payments")
    if isclose(rate, growth):
        # When r = g every payment is worth the same today: C / (1 + r) each
        return first_payment * n_payments / (1 + rate)
    return first_payment / (rate - growth) * (1 - ((1 + growth) / (1 + rate)) ** n_payments)


def pv_perpetuity(payment, rate):
    """Constant perpetuity: PV = C / r."""
    if rate <= 0:
        raise ValueError("A perpetuity needs an interest rate above 0%")
    return payment / rate


def pv_growing_perpetuity(first_payment, rate, growth):
    """Growing perpetuity: PV = C / (r - g). Only works when g < r."""
    if growth >= rate:
        raise ValueError("Growth rate must be lower than the interest rate, "
                         "or the value would be infinite")
    _check_rate(growth, "Growth rate")
    return first_payment / (rate - growth)


def value_today(value_one_period_before_first, first_payment_period, rate):
    """
    The shortcuts give a value at (first payment period - 1).
    Discount that back to today (period 0).
    """
    return move(value_one_period_before_first, rate, first_payment_period - 1, 0)


def pattern_cash_flows(payment, n_payments, first_period=1, growth=0.0):
    """List the individual payments of an annuity, so you can check the long way."""
    return [(first_period + k, payment * (1 + growth) ** k) for k in range(n_payments)]


# 4. Payments at the start, savings goals, and late or early perpetuities


def pv_annuity_due(payment, rate, n_payments):
    """Annuity due (first payment today): PV = ordinary annuity x (1 + r)."""
    return pv_annuity(payment, rate, n_payments) * (1 + rate)


def fv_annuity(payment, rate, n_payments):
    """Future value of an annuity, on the date of the LAST payment:
    FV = C x [(1 + r)^N - 1] / r."""
    _check_rate(rate)
    _check_periods(n_payments, "Number of payments")
    if rate == 0:
        return payment * n_payments
    return payment * ((1 + rate) ** n_payments - 1) / rate


def fv_annuity_due(payment, rate, n_payments):
    """Future value of an annuity due, one period after the last payment."""
    return fv_annuity(payment, rate, n_payments) * (1 + rate)


def pv_perpetuity_due(payment, rate):
    """Perpetuity whose first payment is today: today's payment + C / r."""
    return payment + pv_perpetuity(payment, rate)


def capm_rate(risk_free, beta, market_risk_premium):
    """Required return from CAPM: r = rf + beta x (market risk premium)."""
    return risk_free + beta * market_risk_premium
