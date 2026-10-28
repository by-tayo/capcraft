"""Request and response models for the CapCraft API.

Every endpoint declares a response model, so the API's OpenAPI description
is exact and the frontend's TypeScript types can be generated from it.

Conventions (the same as the library): rates, returns, weights and
volatilities are DECIMALS, 5% -> 0.05. Dollar amounts are plain numbers.
A value that cannot be computed (an undefined ratio, an impossible grid
cell) is null, never NaN.
"""
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

# Limits keep a public demo from being asked for something enormous.
MAX_SIMS = 10_000
MAX_YEARS = 50
MAX_CSV_CHARS = 1_000_000
MAX_ASSETS = 25
MAX_ROWS = 3_000
MAX_FRONTIER = 20_000
MAX_FORECAST_YEARS = 15

PerYear = Union[float, List[float]]


# Plan vs. reality (Monte Carlo)


class PlanRequest(BaseModel):
    initial: float = Field(10_000, ge=0, le=1e9, description="Dollars invested today")
    monthly_contribution: float = Field(500, ge=0, le=1e7, description="Dollars added at the end of each month")
    years: int = Field(20, ge=1, le=MAX_YEARS)
    expected_return: float = Field(0.07, gt=-0.5, lt=1.0, description="Average yearly return the plan assumes")
    volatility: float = Field(0.15, ge=0, le=1.5, description="Yearly standard deviation of returns")
    goal: Optional[float] = Field(None, gt=0, le=1e12, description="Target dollar amount at the end")
    n_sims: int = Field(5_000, ge=100, le=MAX_SIMS)
    seed: Optional[int] = Field(None, ge=0, lt=2 ** 31, description="Set to reproduce a result exactly")


class Needed(BaseModel):
    confidence: float
    monthly: float


class Histogram(BaseModel):
    edges: List[float]
    counts: List[int]
    overflow: int = Field(description="Futures above the last bin edge")


class PlanResponse(BaseModel):
    seed: int
    n_sims: int
    years: int
    invested: float
    goal: Optional[float]
    straight_line_final: float = Field(description="Where the plan ends if every year earns exactly the average")
    mean_final: float
    median_final: float
    percentiles: Dict[str, float]
    prob_loss: float = Field(description="Share of futures ending below the dollars put in")
    share_below_straight_line: float
    prob_goal: Optional[float]
    value_at_risk_95: float
    conditional_value_at_risk_95: float
    needed_monthly: Optional[List[Needed]]
    time: List[float]
    straight_line: List[float]
    bands: Dict[str, List[float]]
    sample_paths: List[List[float]]
    histogram: Histogram


# Portfolio X-ray


class XrayRequest(BaseModel):
    csv_text: str = Field(max_length=MAX_CSV_CHARS, description="Price history, one column per asset (see data.py)")
    amounts: Optional[Dict[str, float]] = Field(None, description="Dollars or weights per asset; normalized. Equal if omitted")
    benchmark: Optional[str] = Field(None, description="Name of the price column to use as the market")
    periods_per_year: int = Field(12, description="12 monthly, 52 weekly, 252 daily, 4 quarterly, 1 yearly")
    risk_free_annual: float = Field(0.03, ge=-0.05, le=0.5)
    n_frontier: int = Field(3_000, ge=100, le=MAX_FRONTIER)
    seed: Optional[int] = Field(None, ge=0, lt=2 ** 31)

    @field_validator("periods_per_year")
    @classmethod
    def _ppy(cls, v):
        if v not in (1, 4, 12, 52, 252):
            raise ValueError("periods_per_year must be 1, 4, 12, 52 or 252")
        return v


class AssetRow(BaseModel):
    name: str
    weight: float
    annual_return: Optional[float] = Field(description="Compound growth per year (CAGR)")
    annual_risk: float
    sharpe: Optional[float]
    max_drawdown: float
    beta: Optional[float]
    own_risk_share: float = Field(description="Share of the portfolio's risk this holding adds")


class Correlation(BaseModel):
    names: List[str]
    matrix: List[List[float]]


class Series(BaseModel):
    name: str
    values: List[float]


class Metrics(BaseModel):
    n_periods: int
    average_periodic_return: float
    periodic_risk: float
    annualized_return: Optional[float]
    annualized_return_arithmetic: float
    annualized_volatility: float
    sharpe_ratio: Optional[float]
    sortino_ratio: Optional[float]
    calmar_ratio: Optional[float]
    max_drawdown: float
    max_drawdown_peak_index: int
    max_drawdown_trough_index: int
    max_drawdown_recovery_index: Optional[int]
    confidence: float
    historical_var: Optional[float]
    historical_cvar: Optional[float]
    parametric_var: Optional[float]
    beta_vs_benchmark: Optional[float] = None
    jensens_alpha_per_year: Optional[float] = None


class FrontierPoint(BaseModel):
    annual_risk: float
    annual_return: float
    sharpe: Optional[float] = None
    name: Optional[str] = None


class FrontierMix(BaseModel):
    weights: Dict[str, float]
    annual_return: float
    annual_risk: float
    sharpe: float


class FrontierOut(BaseModel):
    points: List[FrontierPoint]
    edge: List[FrontierPoint]
    assets: List[FrontierPoint]
    current: FrontierPoint
    min_variance: FrontierMix
    max_sharpe: FrontierMix
    n_sampled: int


class XrayResponse(BaseModel):
    seed: int
    n_periods: int
    periods_per_year: int
    labels: List[str] = Field(description="One label per point in the growth and drawdown series")
    assets: List[AssetRow]
    correlation: Correlation
    metrics: Metrics
    diversification_benefit: float = Field(description="Weighted-average holding risk minus portfolio risk, yearly")
    diversified: bool
    growth: List[Series] = Field(description="Growth of 100: the portfolio, each asset, and the benchmark if given")
    drawdown: List[float]
    frontier: Optional[FrontierOut]
    warnings: List[str]


class SampleResponse(BaseModel):
    csv_text: str
    amounts: Dict[str, float]
    benchmark: str
    synthetic: bool
    note: str


# DCF


class DCFRequest(BaseModel):
    base_revenue: float = Field(1_000, gt=0, le=1e12)
    revenue_growth: PerYear = Field(0.08, description="One rate for every year, or one per forecast year")
    years: Optional[int] = Field(5, ge=1, le=MAX_FORECAST_YEARS)
    ebit_margin: PerYear = 0.18
    tax_rate: float = Field(0.25, ge=0, lt=1)
    da_pct: PerYear = 0.04
    capex_pct: PerYear = 0.05
    nwc_pct: PerYear = 0.10
    discount_rate: float = Field(0.09, gt=0, lt=1)
    terminal_method: Literal["gordon", "exit_multiple"] = "gordon"
    terminal_growth: Optional[float] = Field(0.025, ge=-0.1, lt=1)
    exit_multiple: Optional[float] = Field(None, ge=0, le=200)
    net_debt: float = Field(0.0, ge=-1e12, le=1e12)
    shares_outstanding: Optional[float] = Field(None, gt=0, le=1e12)
    mid_year: bool = False
    market_price: Optional[float] = Field(None, gt=0, le=1e9, description="Per-share market price, for the reverse DCF")


class ProjectionRow(BaseModel):
    year: int
    revenue: float
    ebit: float
    nopat: float
    da: float
    capex: float
    delta_nwc: float
    fcf: float
    pv_fcf: float


class Valuation(BaseModel):
    discount_rate: float
    terminal_method: str
    terminal_value: float
    pv_terminal_value: float
    pv_explicit: float
    enterprise_value: float
    net_debt: float
    equity_value: float
    value_per_share: Optional[float]
    terminal_share: Optional[float]
    implied_exit_multiple: Optional[float]
    implied_terminal_growth: Optional[float]


class Grid(BaseModel):
    metric: str
    x_label: str
    x_values: List[float]
    y_label: str
    y_values: List[float]
    grid: List[List[Optional[float]]]
    base_output: float


class TornadoOut(BaseModel):
    param: str
    label: str
    low_label: str
    high_label: str
    low_output: float
    high_output: float
    swing: float


class ReverseSolution(BaseModel):
    available: bool
    value: Optional[float] = None
    reason: Optional[str] = None
    unique: Optional[bool] = None


class ReverseDCF(BaseModel):
    market_price: float
    model_value: float
    upside: float = Field(description="Model value per share / market price - 1")
    model_average_growth: float
    implied_growth: ReverseSolution
    implied_discount_rate: ReverseSolution


class DCFResponse(BaseModel):
    metric: str
    projection: List[ProjectionRow]
    valuation: Valuation
    sensitivity: Grid
    tornado: List[TornadoOut]
    reverse: Optional[ReverseDCF]


class WaccRequest(BaseModel):
    risk_free: float = Field(0.04, ge=-0.05, le=0.5)
    beta: float = Field(1.0, ge=-3, le=5)
    market_return: float = Field(0.09, ge=-0.5, le=1)
    equity_value: float = Field(1_500, ge=0, le=1e12)
    debt_value: float = Field(500, ge=0, le=1e12)
    cost_of_debt: float = Field(0.06, ge=0, le=1)
    tax_rate: float = Field(0.25, ge=0, lt=1)


class WaccResponse(BaseModel):
    cost_of_equity: float
    wacc: float
    equity_weight: float
    debt_weight: float


class Meta(BaseModel):
    name: str
    version: str
    disclaimer: str
    limits: Dict[str, int]
    assumptions: Dict[str, List[str]]
